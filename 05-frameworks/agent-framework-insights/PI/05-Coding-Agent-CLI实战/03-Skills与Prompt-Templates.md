# Skills 与 Prompt Templates

> 同样是"把一段可复用的东西交给 Agent"，Skills（技能）和 Prompt Templates（提示词模板）解决的是两个不同的问题：一个是"模型按需自己决定要不要用的能力包"，一个是"用户主动敲 `/name` 展开的固定提示词"。本篇基于 `docs/skills.md` 和 `docs/prompt-templates.md` 把两者的格式、加载机制和适用场景讲清楚。

## 学习目标

- 说清楚 Skill 与 Prompt Template 的本质区别：谁来决定"要不要用"、内容如何进入上下文。
- 掌握 `SKILL.md` 的目录结构、frontmatter 字段（`name`/`description`/`license`/`compatibility`/`metadata`/`allowed-tools`/`disable-model-invocation`）与命名规则。
- 掌握 Prompt Template 的 Markdown 格式、frontmatter 字段（`description`/`argument-hint`）与参数占位符语法（`$1`、`$@`、`${1:-default}` 等）。
- 知道两者各自的加载位置、发现规则，以及如何从 Claude Code / OpenAI Codex 迁移已有的 skills 目录。
- 能分别写出一个可用的 SKILL.md 和一个带参数默认值的 Prompt Template。

## 核心区别一览

| 维度 | Skills | Prompt Templates |
|------|--------|-------------------|
| 触发方式 | 模型根据任务自动判断是否加载（渐进式披露），或用户显式 `/skill:name` | 用户主动输入 `/name` 展开 |
| 内容形态 | 一个目录（`SKILL.md` + 脚本 + 参考文档 + 资源文件） | 单个 Markdown 文件 |
| 何时进入上下文 | 启动时只有"名称+描述"常驻系统提示词；命中任务后模型用 `read` 工具按需加载完整 `SKILL.md` | 用户敲命令的那一刻，文件内容（含参数替换）直接展开成一条消息 |
| 典型用途 | 需要配套脚本/参考资料的复杂能力（PDF 处理、浏览器自动化） | 固定的、参数化的指令模板（"审查这个 PR"、"生成一个组件"） |
| 是否支持参数 | 支持（`/skill:name args` 里的 `args` 会作为 `User: <args>` 追加在技能内容后面） | 支持，且有专门的占位符语法（`$1`、`${1:-default}` 等） |

一句话总结:Skills 是"渐进式披露"（progressive disclosure）——默认只占极小的上下文（一条描述），真正用到时才加载完整内容;Prompt Templates 是"文本宏"——一敲命令就整段展开,没有"按需"这一步。

## Skills

### 加载位置与发现规则

pi 实现了 [Agent Skills 标准](https://agentskills.io/specification)，对大多数不合规之处只警告、不拒绝加载。一个例外：pi 允许 Skill 名字与其所在目录名不一致（标准要求两者必须一致），因为这条规则对"多个 Agent 工具共用同一批 skills 目录"的场景并不友好。

pi 从以下位置加载 Skills：

- 全局:`~/.pi/agent/skills/`、`~/.agents/skills/`
- 项目（仅在项目被信任后）:`cwd` 及其祖先目录（直到 git 仓库根或文件系统根）下的 `.pi/skills/`、`.agents/skills/`
- 包:`package.json` 里的 `skills/` 目录或 `pi.skills` 字段（见下一篇《Pi Package 生态与分发》）
- 配置:`settings.json` 的 `skills` 数组（可以是文件或目录）
- CLI:`--skill <path>`（可重复传入，即使加了 `--no-skills` 这类显式路径依然会加载）

发现细则:
- 在 `~/.pi/agent/skills/` 和 `.pi/skills/` 里,直接放在根目录的 `.md` 文件会被当作独立技能发现;
- 所有位置里,包含 `SKILL.md` 的目录都会被递归发现;
- 在 `~/.agents/skills/` 和项目 `.agents/skills/` 里,根目录的 `.md` 文件会被**忽略**（这是与前一条的差异点）。

用 `--no-skills` 可以关闭自动发现（显式传入的 `--skill` 路径仍然生效）。

要复用 Claude Code 或 OpenAI Codex 的 skills 目录，在 `settings.json` 里直接把它们的路径加进 `skills` 数组即可：

```json
{
  "skills": ["~/.claude/skills", "~/.codex/skills"]
}
```

项目级的 Claude Code skills 则加进 `.pi/settings.json`：

```json
{
  "skills": ["../.claude/skills"]
}
```

### 工作流程

1. 启动时,pi 扫描所有 skill 位置,只提取每个技能的 `name` 和 `description`。
2. 系统提示词里按 [规范格式](https://agentskills.io/integrate-skills) 列出所有可用技能的 XML 描述。
3. 当任务匹配某个技能的描述时,模型会用 `read` 工具加载完整的 `SKILL.md`（模型不一定每次都会主动这么做,可以通过提示词引导,或者用户直接敲 `/skill:name` 强制加载）。
4. 模型按 `SKILL.md` 里的指示行动,并用相对路径引用技能目录里的脚本和资源文件。

这套机制被称为"渐进式披露"（progressive disclosure）：只有描述常驻上下文，完整指令按需加载，避免几十个技能的完整内容把上下文预算全部占满。

### Skill 命令

技能会自动注册为 `/skill:name` 命令：

```bash
/skill:brave-search           # 加载并执行该技能
/skill:pdf-tools extract      # 加载技能并附带参数
```

命令后面的参数会被追加到技能内容末尾，格式为 `User: <args>`。

是否启用 skill 命令可以在交互模式的 `/settings` 里切换，或写进 `settings.json`：

```json
{ "enableSkillCommands": true }
```

### SKILL.md 结构与 frontmatter

一个技能就是一个包含 `SKILL.md` 的目录，其余文件完全自由组织：

```
my-skill/
├── SKILL.md              # 必需：frontmatter + 指令正文
├── scripts/              # 辅助脚本
│   └── process.sh
├── references/           # 按需加载的详细文档
│   └── api-reference.md
└── assets/
    └── template.json
```

`SKILL.md` 本身是标准 frontmatter + Markdown：

````markdown
---
name: my-skill
description: What this skill does and when to use it. Be specific.
---

# My Skill

## Setup

Run once before first use:
```bash
cd /path/to/skill && npm install
```

## Usage

```bash
./scripts/process.sh <input>
```
````

正文里引用同目录资源用相对路径，例如 `[the reference guide](references/REFERENCE.md)`。

frontmatter 字段（按 [Agent Skills 规范](https://agentskills.io/specification#frontmatter-required)）：

| 字段 | 是否必需 | 说明 |
|------|---------|------|
| `name` | 是 | 最长 64 字符，小写字母/数字/连字符。pi 不要求这个值与父目录名一致（标准要求一致，但这对共享技能目录不友好） |
| `description` | 是 | 最长 1024 字符，说明技能做什么、什么时候该用 |
| `license` | 否 | 许可证名称或指向已打包许可证文件的引用 |
| `compatibility` | 否 | 最长 500 字符，环境要求说明 |
| `metadata` | 否 | 任意键值对 |
| `allowed-tools` | 否 | 空格分隔的预授权工具列表（实验性） |
| `disable-model-invocation` | 否 | 为 `true` 时该技能对模型隐藏，只能靠用户手动 `/skill:name` 调用 |

**命名规则**：1-64 个字符；只能是小写字母、数字、连字符；不能以连字符开头或结尾；不能有连续连字符。合法示例：`pdf-processing`、`data-analysis`、`code-review`；非法示例：`PDF-Processing`、`-pdf`、`pdf--processing`。

**description 的写法**：这是模型决定"要不要加载"这个技能的唯一依据，必须具体。好的写法："Extracts text and tables from PDF files, fills PDF forms, and merges multiple PDFs. Use when working with PDF documents."；不好的写法："Helps with PDFs."（信息量太少，模型无法判断何时该用）。

### 校验规则

pi 会按 Agent Skills 标准校验技能，大多数问题只警告、仍然加载：名字超过 64 字符或含非法字符、名字以连字符开头/结尾或含连续连字符、description 超过 1024 字符。未知的 frontmatter 字段会被忽略。**唯一的例外**：缺少 `description` 的技能不会被加载。不同位置出现同名技能时会警告并保留最先发现的那一个。

## Prompt Templates

### 加载位置

- 全局:`~/.pi/agent/prompts/*.md`
- 项目（仅在项目被信任后）:`.pi/prompts/*.md`
- 包:`package.json` 里的 `prompts/` 目录或 `pi.prompts` 字段
- 配置:`settings.json` 的 `prompts` 数组
- CLI:`--prompt-template <path>`（可重复）

用 `--no-prompt-templates` 关闭自动发现。

**注意**：`prompts/` 目录下的发现是**非递归**的，如果想放在子目录里，需要通过 `prompts` 配置项或 package manifest 显式指定路径。

### 格式

文件名（去掉 `.md` 后缀）就是命令名，`review.md` 对应 `/review`：

```markdown
---
description: Review staged git changes
---
Review the staged changes (`git diff --cached`). Focus on:
- Bugs and logic errors
- Security issues
- Error handling gaps
```

- `description` 可选，缺省时取正文第一个非空行作为描述。
- `argument-hint` 可选，设置后会在自动补全下拉列表里显示在描述之前，用 `<尖括号>` 标注必填参数、`[方括号]` 标注可选参数：

```markdown
---
description: Review PRs from URLs with structured issue and code analysis
argument-hint: "<PR-URL>"
---
```

补全下拉列表里会渲染成：

```
→ pr   <PR-URL>       — Review PRs from URLs with structured issue and code analysis
  is   <issue>        — Analyze GitHub issues (bugs or feature requests)
  wr   [instructions] — Finish the current task end-to-end
  cl   — Audit changelog entries before release
```

### 用法与参数占位符

在编辑器里输入 `/` 加模板名即可，自动补全会显示所有可用模板及其描述：

```
/review                           # 展开 review.md
/component Button                 # 带参数展开
/component Button "click handler" # 多个参数
```

支持的占位符语法：

- `$1`、`$2`、……：按位置取参数
- `$@` 或 `$ARGUMENTS`：拼接所有参数
- `${1:-default}`：第 1 个参数存在且非空时使用该参数，否则用 `default`
- `${@:-default}` 或 `${ARGUMENTS:-default}`：所有参数存在且非空时使用，否则用 `default`
- `${@:N}`：从第 N 个位置（1-indexed）开始的所有参数
- `${@:N:L}`：从第 N 个位置开始、取 `L` 个参数

示例：

```markdown
---
description: Create a component
---
Create a React component named $1 with features: $@
```

默认值对可选参数很有用：

```markdown
Summarize the current state in ${1:-7} bullet points.
```

调用方式：`/component Button "onClick handler" "disabled support"`。

## 该用哪一个

- 需要配套脚本、参考文档、需要模型"自己判断什么时候该用"的复杂能力（例如 PDF 处理、浏览器自动化、某个内部系统的操作手册）→ 用 **Skill**。
- 只是想把一段常用的、结构固定的指令绑定到一个快捷命令上，偶尔带几个参数（例如"审查暂存区的改动""按某个模板创建组件"）→ 用 **Prompt Template**。
- 两者可以组合：Prompt Template 里的正文完全可以是"请加载并执行 `xxx` 技能，参数是……"这样的引导文字。

## 动手练习

1. 在 `~/.pi/agent/skills/git-commit-helper/SKILL.md` 创建一个技能，`description` 写清楚"什么时候该用"（例如"生成规范的 conventional commit 提交信息，在用户要求写 commit message 时使用"），正文里给出几条具体规则。启动一个新会话，观察系统提示词里是否出现了这个技能的描述，再用 `/skill:git-commit-helper` 强制加载验证内容正确。
2. 在 `~/.pi/agent/prompts/explain.md` 创建一个 Prompt Template，要求：`argument-hint` 标注一个必填参数（文件路径）和一个可选参数（详细程度，默认值为 `"简要"`），正文用 `$1` 和 `${2:-简要}` 组合出"请以 <详细程度> 的方式解释 <文件路径> 这个文件的作用"。在编辑器里分别用 `/explain src/index.ts` 和 `/explain src/index.ts 详细` 验证两种展开结果。

## 小结

Skills 和 Prompt Templates 都是"把可复用内容交给 Agent"的机制，但设计目标不同：Skill 面向"模型自主判断、按需加载"的复杂能力包，靠渐进式披露控制上下文成本，`SKILL.md` 的 frontmatter 只有 `name`/`description` 是必需的，其余字段（`license`/`compatibility`/`metadata`/`allowed-tools`/`disable-model-invocation`）用来补充元信息或收窄可见性；Prompt Template 面向"用户主动触发的固定/参数化指令"，一个 Markdown 文件对应一个 `/name` 命令，支持位置参数、默认值和切片语法，但不支持子目录递归发现。两者都可以来自全局目录、项目目录、pi package 或 `settings.json` 显式配置,也都可以通过 `--no-skills`/`--no-prompt-templates` 整体关闭自动发现。
