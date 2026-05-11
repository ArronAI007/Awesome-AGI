# 三、架构

---

## 3.1 整体架构概览

Claude Code 的整体架构可以分为四个层次：

```
┌─────────────────────────────────────────────────────────┐
│  用户界面层（UI Layer）                                    │
│  ├─ 终端 CLI                                             │
│  ├─ VS Code / JetBrains 扩展                              │
│  ├─ 桌面应用                                             │
│  └─ 浏览器 / Slack                                       │
├─────────────────────────────────────────────────────────┤
│  扩展与集成层（Extension Layer）                           │
│  ├─ Skills（技能）                                        │
│  ├─ MCP（外部服务连接）                                    │
│  ├─ Hooks（工作流钩子）                                    │
│  └─ Subagents（子智能体）                                  │
├─────────────────────────────────────────────────────────┤
│  核心智能体层（Core Agent Layer）                          │
│  ├─ Agentic Loop（智能体循环）                             │
│  ├─ Context Management（上下文管理）                       │
│  ├─ Permission System（权限系统）                          │
│  └─ Memory System（记忆系统）                              │
├─────────────────────────────────────────────────────────┤
│  基础设施层（Infrastructure Layer）                        │
│  ├─ Models（Claude 模型）                                 │
│  ├─ Tools（内置工具集）                                    │
│  ├─ LSP / Code Intelligence（代码智能）                    │
│  └─ Git Integration（Git 集成）                            │
└─────────────────────────────────────────────────────────┘
```

---

## 3.2 核心架构：Agentic Loop（智能体循环）

Claude Code 最核心的架构设计是 **Agentic Loop**，这是一个持续运行的循环，将用户的自然语言指令转化为一系列工具调用，最终完成复杂任务。

### 3.2.1 三阶段循环

```
┌───────────────────────────────────────────────────────────┐
│                    Agentic Loop                           │
│                                                           │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│   │  ① 收集上下文 │───→│  ② 执行动作   │───→│  ③ 验证结果  │  │
│   │  (Gather)   │    │   (Take)    │    │  (Verify)   │  │
│   └─────────────┘    └─────────────┘    └─────────────┘  │
│          ↑                                    │           │
│          └────────────────────────────────────┘           │
│                      （循环往复）                           │
│                                                           │
│   用户可以随时中断循环，提供额外上下文或调整方向              │
└───────────────────────────────────────────────────────────┘
```

### 3.2.2 各阶段详解

**① 收集上下文（Gather Context）**

Claude 使用工具来了解项目状态和任务需求：

- `Glob` / `Grep` —— 搜索相关文件
- `Read` —— 读取文件内容
- `Bash` —— 运行命令获取信息（如 `git status`、`npm test`）
- `WebSearch` / `WebFetch` —— 搜索网络资源
- `LSP` —— 代码导航（定义跳转、引用查找）

**② 执行动作（Take Action）**

基于收集的上下文，Claude 决定并执行操作：

- `Edit` —— 修改文件内容
- `Bash` —— 运行命令（编译、测试、部署）
- `Write` —— 创建新文件
- `Agent` —— 委派任务给子智能体

**③ 验证结果（Verify Results）**

执行后验证结果是否符合预期：

- `Bash` —— 运行测试验证
- `Read` —— 检查修改后的文件
- `LSP` —— 检查类型错误和警告
- 推理 —— 判断任务是否完成，是否需要继续循环

### 3.2.3 循环的自适应特性

Agentic Loop 不是固定的流程，而是**自适应**的：

| 任务类型 | 循环行为 |
|---------|---------|
| **简单提问** | 仅需收集上下文，一次循环结束 |
| **Bug 修复** | 多次完整循环：定位 → 修复 → 测试 → 验证 |
| **代码重构** | 大量验证循环，确保每次修改后功能正确 |
| **探索性任务** | 以收集上下文为主，循环次数不确定 |
| **批量修改** | `/batch` Skill 将任务分解为多个子任务并行执行 |

### 3.2.4 用户与循环的交互

用户是整个循环的参与者，而不仅仅是观察者：

- **随时中断**：在循环的任何阶段，用户可以输入新指令调整方向
- **中途纠正**：如果 Claude 的理解有误，用户可以直接纠正
- **批准/拒绝**：敏感操作需要用户确认
- **计划模式**：复杂任务可以先进入 `/plan` 模式，审查计划后再执行

---

## 3.3 双组件驱动架构

Agentic Loop 由两大核心组件驱动：

### 3.3.1 Models（模型层）

**作用**：理解代码、推理任务、制定计划

Claude Code 使用 Claude 系列大语言模型：

| 模型别名 | 对应模型 | 特点 | 适用场景 |
|---------|---------|------|---------|
| `sonnet` | Sonnet 4.6（API）/ 4.5（第三方） | 平衡性能与速度 | 日常编码任务 |
| `opus` | Opus 4.7（API）/ 4.6（第三方） | 最强推理能力 | 复杂架构决策 |
| `haiku` | Haiku | 快速、低成本 | 简单任务、子智能体 |
| `best` | 当前最强模型（opus） | 最高能力 | 需要最强推理时 |
| `opusplan` | 计划用 opus，执行用 sonnet | 智能切换 | 复杂任务的计划与执行 |
| `sonnet[1m]` | Sonnet + 1M 上下文 | 超长上下文 | 处理大量代码 |
| `opus[1m]` | Opus + 1M 上下文 | 超长上下文 + 强推理 | 大型项目分析 |

**模型切换方式：**
```bash
# 启动时指定
claude --model opus

# 会话中切换
/model sonnet

# 环境变量
export ANTHROPIC_MODEL=sonnet

# 配置文件 settings.json
{
  "model": "opus"
}
```

### 3.3.2 Tools（工具层）

**作用**：让 Claude 能够实际"动手"操作环境和代码

没有工具的 Claude 只能生成文本，有了工具的 Claude 才能真正执行任务。

**工具调用流程：**
```
用户输入 → Claude 推理 → 选择工具 → 执行工具 → 获取结果 → 推理下一步 → ...
```

---

## 3.4 工具分类体系

Claude Code 内置工具分为五大类别：

### 3.4.1 文件操作类

| 工具 | 功能 | 需权限 |
|------|------|--------|
| `Read` | 读取文件内容 | 否 |
| `Edit` | 精确编辑文件特定位置 | 是 |
| `Write` | 创建新文件 | 是 |
| `Glob` | 按模式查找文件 | 否 |
| `Grep` | 正则搜索文件内容 | 否 |

### 3.4.2 搜索与探索类

| 工具 | 功能 | 需权限 |
|------|------|--------|
| `Glob` | 按 glob 模式查找文件 | 否 |
| `Grep` | 在文件内容中搜索正则表达式 | 否 |
| `LSP` | 代码智能（定义跳转、引用查找、类型检查） | 否 |
| `WebSearch` | 搜索网络 | 否 |
| `WebFetch` | 获取网页内容 | 否 |

### 3.4.3 执行类

| 工具 | 功能 | 需权限 |
|------|------|--------|
| `Bash` | 执行 shell 命令 | 是 |
| `CronCreate` | 创建定时任务 | 否 |
| `CronDelete` | 删除定时任务 | 否 |
| `CronList` | 列出定时任务 | 否 |

**Bash 工具行为：**
- 默认在 Bash shell 中执行（Windows 上可用 PowerShell）
- 支持长时间运行的命令（如服务器启动）
- 可在沙盒环境中运行（WSL 2 支持）
- 支持交互式命令（通过 PTY）
- 命令输出会反馈到 Agentic Loop 中

### 3.4.4 Web 类

| 工具 | 功能 | 需权限 |
|------|------|--------|
| `WebSearch` | 搜索网页获取信息 | 否 |
| `WebFetch` | 获取特定网页内容 | 否 |

> WebFetch 调用前会进行域名安全检查，可通过 `skipWebFetchPreflight: true` 跳过。

### 3.4.5 代码智能类

| 工具 | 功能 | 需权限 |
|------|------|--------|
| `LSP` | 通过语言服务器提供代码智能 | 否 |

**LSP 功能：**
- 跳转到定义（Go to Definition）
- 查找引用（Find References）
- 类型检查和错误报告
- 代码补全建议

需要安装对应语言的 [code intelligence plugin](https://code.claude.com/docs/en/discover-plugins)。

### 3.4.6 编排与交互类

| 工具 | 功能 | 需权限 |
|------|------|--------|
| `Agent` | 生成子智能体处理任务 | 否 |
| `AskUserQuestion` | 向用户询问多选题 | 否 |
| `EnterPlanMode` | 进入计划模式 | 否 |
| `ExitPlanMode` | 退出计划模式 | 是 |
| `EnterWorktree` | 创建/进入 Git worktree | 否 |
| `ExitWorktree` | 退出 worktree | 否 |

---

## 3.5 上下文管理架构

### 3.5.1 上下文来源

Claude Code 启动时自动加载以下上下文：

| 来源 | 加载时机 | 内容 |
|------|---------|------|
| **项目文件** | 按需 | 当前目录及子目录中的文件 |
| **终端环境** | 启动时 | 环境变量、可执行命令 |
| **Git 状态** | 启动时 | 分支、未提交更改、近期提交 |
| **CLAUDE.md** | 启动时 | 项目特定指令（前 200 行或 25KB） |
| **Auto Memory** | 启动时 | Claude 自动保存的学习内容 |
| **Skills** | 按需 | 匹配的技能文件 |

### 3.5.2 CLAUDE.md 加载层次

CLAUDE.md 文件可以存在于多个层级，按优先级合并：

| 层级 | 路径 | 范围 | 共享 |
|------|------|------|------|
| Managed（管理策略） | `/Library/Application Support/ClaudeCode/CLAUDE.md` 等 | 组织范围 | 所有用户 |
| Project（项目级） | `./CLAUDE.md` 或 `./.claude/CLAUDE.md` | 当前项目 | 团队成员 |
| User（用户级） | `~/.claude/CLAUDE.md` | 所有项目 | 仅你 |
| Local（本地级） | `./CLAUDE.local.md` | 当前项目 | 仅你（.gitignore） |

**加载规则：**
- 上层目录的 CLAUDE.md 在启动时**完整加载**
- 子目录中的 CLAUDE.md **按需加载**（当 Claude 读取该目录文件时）
- 更具体的层级优先级更高

---

## 3.6 扩展架构

Claude Code 的核心架构之上支持多层扩展：

### 3.6.1 Skills（技能）

**作用**：可复用的基于提示的工作流

- 通过 `SKILL.md` 文件定义
- 包含 YAML frontmatter（描述何时使用）和 Markdown 内容（指令）
- 可以使用动态上下文注入（如 `` !`git diff HEAD` ``）
- 支持用户级（`~/.claude/skills/`）和项目级（`.claude/skills/`）

### 3.6.2 MCP（Model Context Protocol）

**作用**：连接外部服务（数据库、API、云服务等）

- 遵循 MCP 开放标准
- 支持 stdio、HTTP、SSE 等多种传输方式
- 可通过 `claude mcp add` 命令添加
- 支持 managed MCP 配置（企业部署）

### 3.6.3 Hooks（钩子）

**作用**：自动化工作流触发器

- 在 Claude Code 生命周期的特定点触发
- 支持 shell 命令、HTTP 端点、LLM 提示三种类型
- 可以阻止、修改或记录工具调用
- 事件包括：`SessionStart`、`UserPromptSubmit`、`PreToolUse`、`PostToolUse`、`Stop` 等

### 3.6.4 Subagents（子智能体）

**作用**：委派任务，保持主会话上下文干净

- 每个子智能体有自己的上下文窗口
- 可以配置自定义系统提示、工具限制、模型选择
- 内置子智能体：Explore（只读探索）、Plan（计划研究）、General-purpose（通用）
- 子智能体不能嵌套（不能生成子智能体的子智能体）

---

## 3.7 设置与配置的层次架构

Claude Code 采用**多层作用域系统**管理配置：

### 3.7.1 配置作用域

| 作用域 | 路径 | 影响范围 | 优先级 |
|--------|------|---------|--------|
| **Managed** | 服务器管理 / MDM / 系统文件 | 机器上所有用户 | 最高（不可覆盖） |
| **命令行参数** | `claude --model opus` | 当前会话 | 高 |
| **Local** | `.claude/settings.local.json` | 当前项目（仅你） | 中-高 |
| **Project** | `.claude/settings.json` | 当前项目（团队） | 中 |
| **User** | `~/.claude/settings.json` | 所有项目 | 低 |

### 3.7.2 各功能的作用域位置

| 功能 | User 位置 | Project 位置 | Local 位置 |
|------|----------|-------------|-----------|
| Settings | `~/.claude/settings.json` | `.claude/settings.json` | `.claude/settings.local.json` |
| Subagents | `~/.claude/agents/` | `.claude/agents/` | — |
| MCP | `~/.claude.json` | `.mcp.json` | `~/.claude.json` |
| CLAUDE.md | `~/.claude/CLAUDE.md` | `CLAUDE.md` / `.claude/CLAUDE.md` | `CLAUDE.local.md` |
| Skills | `~/.claude/skills/` | `.claude/skills/` | — |

> Windows 上 `~/.claude` 解析为 `%USERPROFILE%\.claude`

### 3.7.3 合并规则

- **标量值**：更具体的层级覆盖更通用的层级
- **数组**：合并并去重
- **对象**：深度合并
- **Managed 设置**：最高优先级，不可被用户或项目设置覆盖
