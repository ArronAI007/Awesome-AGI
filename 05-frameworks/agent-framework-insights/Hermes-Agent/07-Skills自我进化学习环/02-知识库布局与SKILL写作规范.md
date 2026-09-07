# 知识库布局与 SKILL 写作规范

> 上一篇讲了 `/learn` 怎么把一段经验变成一次 agent 回合,这一篇讲那次回合最终写出来的东西长什么样。Hermes 的技能格式兼容 [agentskills.io](https://agentskills.io) 开放标准,但在这之上叠了一套自己的"硬性标准"(AGENTS.md 里称之为 HARDLINE):`description` 必须压在 60 字符以内,正文要按固定的 section 顺序写,新建技能时这条规则甚至由代码强制拒绝,不是靠自觉。更有意思的是材料大小带来的两种归宿——小材料写成一份紧凑的 SKILL.md,大材料(书、论文集、规范文档)写成"索引 + 按需加载的 references/ 子文件"这种知识库布局。本篇把这套目录结构、frontmatter 字段、写作规范,连同两个从仓库里读到的真实 SKILL.md 例子,一次讲清楚。

## 学习目标

- 掌握 SKILL.md 的目录结构约定:`SKILL.md` 必需,`references/`/`templates/`/`scripts/`/`assets/` 按需存在。
- 掌握 frontmatter 的标准字段及其限制,尤其是 `description` 的两级限制——agentskills.io 兼容的 1024 字符软上限,和 Hermes 自己新建技能时强制的 60 字符硬上限。
- 理解正文的"现代 section 顺序"规范,以及为什么这套顺序被要求"omit a section only if it genuinely has no content"而不是随便省略。
- 说清楚"小材料→单文件 SKILL.md"与"大材料→知识库布局(索引 + `references/` 按需加载)"的区别,以及这背后"避免把大量内容一次性塞进 context"的设计思想。
- 能从仓库真实的 `skills/` 目录里认出一份符合规范的 SKILL.md,并知道它引用的支持文件是怎么按需加载的。
- 知道 Hermes 与 agentskills.io 开放标准的兼容点在哪里。

## 目录结构:一个技能就是一个目录

`tools/skills_tool.py` 的模块 docstring 直接给出了这套结构的全貌:

```python
# tools/skills_tool.py:1-26(节选)
"""
This module provides tools for listing and viewing skill documents.
Skills are organized as directories containing a SKILL.md file (the main instructions)
and optional supporting files like references, templates, and examples.

Inspired by Anthropic's Claude Skills system with progressive disclosure architecture:
- Metadata (name ≤64 chars, description ≤1024 chars) - shown in skills_list
- Full Instructions - loaded via skill_view when needed
- Linked Files (references, templates) - loaded on demand

Directory Structure:
    skills/
    ├── my-skill/
    │   ├── SKILL.md           # Main instructions (required)
    │   ├── references/        # Supporting documentation
    │   │   ├── api.md
    │   │   └── examples.md
    │   ├── templates/         # Templates for output
    │   │   └── template.md
    │   └── assets/            # Supplementary files (agentskills.io standard)
    └── category/              # Category folder for organization
        └── another-skill/
            └── SKILL.md
"""
```

仓库里技能分两大类目录,`AGENTS.md` 里写得很明确:

- **`skills/`** —— 默认随包加载的内置技能,按领域分类(`skills/github/`、`skills/mlops/`、`skills/research/` 等)。
- **`optional-skills/`** —— 更重或更小众、默认不启用的技能,需要用户显式 `hermes skills install official/<category>/<skill>` 安装。

除此之外还有第三种落点——`~/.hermes/skills/`,这是 `/learn` 和 `skill_manage(action="create")` 真正写入的位置,对应"用户自建技能"这个所有权层级(细节见第三篇 curator 一章)。三种落点共享同一套 SKILL.md 格式,但只有 `~/.hermes/skills/` 下的技能才会被 curator 纳入生命周期管理。

## Frontmatter:字段与两级 description 限制

`AGENTS.md` 里专门有一节列出标准字段:

```
# AGENTS.md:1008-1018(节选)
Standard fields: name, description, version, author, license,
platforms (OS-gating list: [macos], [linux, macos], ...),
metadata.hermes.tags, metadata.hermes.category,
metadata.hermes.related_skills, metadata.hermes.config (config.yaml
settings the skill needs — stored under skills.config.<key>, prompted
during setup, injected at load time).

Top-level tags: and category: are also accepted and mirrored from
metadata.hermes.* by the loader.
```

一份符合规范的 frontmatter 长这样(取自 `skills/research/arxiv/SKILL.md`):

```yaml
---
name: arxiv
description: "Search arXiv papers by keyword, author, category, or ID."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Research, Arxiv, Papers, Academic, Science, API]
    related_skills: [ocr-and-documents]
---
```

### `description` 的两级限制:一个软上限,一个硬拒绝

`tools/skill_manager_tool.py` 里有两个常量:

```python
# tools/skill_manager_tool.py:195, 547
MAX_DESCRIPTION_LENGTH = 1024
MAX_SKILL_CONTENT_CHARS = 100_000   # ~36k tokens at 2.75 chars/token
```

`1024` 是 agentskills.io 兼容层面的软上限——任何超过这个长度的 `description` 都会被拒绝,不管是新建还是修改。但 Hermes 在这之上叠了一条自己的硬规则:**新建技能时**,`description` 必须再压到 60 字符以内,这条规则直接写在校验函数里,不是靠文档自觉:

```python
# tools/skill_manager_tool.py:600-648(节选)
def _validate_frontmatter(content: str, *, new_skill: bool = False) -> Optional[str]:
    """
    ...
    When ``new_skill`` is True (create path only), the description must
    also fit the 60-char system-prompt budget (SKILL_PROMPT_DESC_LIMIT)
    so newly authored skills never lose routing signal to index
    truncation. Edit and patch paths deliberately skip this so existing
    over-limit skills remain maintainable while their descriptions are
    cleaned up.
    """
    ...
    desc = str(parsed["description"])
    if len(desc) > MAX_DESCRIPTION_LENGTH:
        return f"Description exceeds {MAX_DESCRIPTION_LENGTH} characters."
    if new_skill and len(desc.strip().strip("'\"")) > SKILL_PROMPT_DESC_LIMIT:
        return (
            f"Description is {len(desc.strip())} chars — new skills must fit the "
            f"{SKILL_PROMPT_DESC_LIMIT}-char system-prompt budget (one sentence, "
            f"trigger first, ends with a period). The skill index truncates "
            f"longer descriptions to {SKILL_PROMPT_DESC_LIMIT - 3} chars + '...', "
            f"destroying the routing signal. Move detail into the skill body."
        )
```

`SKILL_PROMPT_DESC_LIMIT = 60` 定义在 `agent/skill_utils.py`。这条规则只在 `action="create"` 路径上硬拒绝,`patch`/`edit` 路径故意放过——目的是让存量的、历史遗留的超长描述仍然可维护,同时保证**新增的**技能不会一开始就带着一个会被截断的描述。`AGENTS.md` 里的 HARDLINE 标准把这条规则的动机讲得更直白:

```
# AGENTS.md:1026-1038(节选)
1. **`description` ≤ 60 characters, one sentence, ends with a period.**
   Long descriptions bloat skill listings and dilute the model's
   attention when many skills are loaded. State the capability, not
   the implementation. No marketing words ("powerful",
   "comprehensive", "seamless", "advanced"). Don't repeat the skill
   name.
```

也就是说,常驻在系统提示词里的"技能目录"只放得下每个技能名字 + 一句被截断到 60 字符的描述——超过这个长度的部分会被直接砍掉、永远不会被模型看到,这是模型判断"要不要加载这个技能"的唯一依据。写超了不是审美问题,是"这个技能可能永远不会被触发"的功能性 bug。

其余 HARDLINE 规则还包括:正文引用能力时必须点名 Hermes 已封装的工具(`terminal`/`read_file`/`search_files`/`patch`/`web_extract` 等),不能让模型在 prose 里直接说 `grep`/`cat`/`sed`;`platforms:` 字段要跟脚本里实际用到的系统调用对齐(`osascript`→macos,`apt`/`systemctl`→linux);正文长度目标"简单技能约 100 行、复杂技能约 200 行",硬上限是 `MAX_SKILL_CONTENT_CHARS`(10 万字符,约 3.6 万 token)。

## 正文的"现代 section 顺序"

`AGENTS.md` 规定的顺序,同时也是 `/learn` 的 `_AUTHORING_STANDARDS` 内嵌进 prompt 里的顺序:

```
# <Human Title>            — 2-3 句话:做什么、不做什么、关键依赖立场
## When to Use             — 具体触发短语的列表
## Prerequisites           — 环境变量、安装步骤、凭证
## How to Run              — 通过 Hermes 工具framing的规范调用方式
## Quick Reference         — 扁平的命令/接口清单,不带叙述
## Procedure               — 带编号的步骤,命令要能直接复制执行
## Pitfalls                — 已知限制、看起来像 bug 其实不是的地方
## Verification            — 一条能证明技能生效的检查
```

规则原文特别强调"omit a section only if it genuinely has no content"——不是每个技能都要凑齐全部八段,但省略必须是因为这一段真的没内容可写,而不是图省事。这条顺序背后是同一套"降低模型认知负担"的思路:每个技能的正文都长得差不多,模型不需要每次重新适应一种新的文档结构。

## 两种归宿:小材料写单文件,大材料写知识库布局

`/learn` 的 `_KNOWLEDGE_SKILL_STANDARDS`(见上一篇)明确区分了两种材料该产出什么形状:

- **小材料/工作流**(一段调试经验、一个 API 的用法)→ 一份紧凑的 SKILL.md,把所有内容直接写在正文里。
- **大材料**(一本书、一堆论文、一份规范文档)→ **知识库布局**:一份精简的 SKILL.md 索引 + 按章节/主题拆分的 `references/*.md` 文件,SKILL.md 只保留"核心心智模型 + 每个 reference 文件的一句话索引",完整内容分散在 `references/` 里,靠 `skill_view(name, file_path=...)` 按需加载。

这个分支决策背后的设计思想,和第一篇提到的"Skill 目录本身要廉价、正文才昂贵"是同一件事的另一种体现——只不过这次不是"目录 vs 正文"的两层,而是"SKILL.md 索引 vs references/ 子文件"的两层。原始规范原文:

```python
# agent/learn_prompt.py:113-147(节选,_KNOWLEDGE_SKILL_STANDARDS)
When the source is a large body of prose rather than a workflow, do NOT cram
it into one SKILL.md and do NOT reduce it to a lossy summary. Author an
expansive skill:

- SKILL.md is a lean core, always loaded in full: the source's central mental
  models and the decision rules worth having in every session, followed by an
  index of every reference file with a one-line "load this when ..."
  description. Keep SKILL.md itself within the normal size bar; the bulk
  lives in `references/`.
- One file per chapter or major topic under `references/` ..., each added with
  `skill_manage` write_file. Distill STRUCTURE, not summary: frameworks,
  definitions, decision rules, anti-patterns, key numbers and tables, with
  chapter/section refs back to the source.
- Process large sources incrementally: inventory the chapters/topics first,
  then read, distill, and persist ONE chapter or topic at a time before moving
  to the next. Never load an entire large corpus into conversation context at
  once.
- SKILL.md must tell the reader to load a chapter on demand with
  `skill_view` (file_path="references/<file>") — reference files cost
  nothing until a question actually needs them.
- Synthesize, never reproduce: the output is structured notes ABOUT the
  source, not a copy of it. No verbatim passages beyond a short quoted
  phrase. This is both the quality bar and the copyright line.
```

值得注意的两点:第一,这套"精简索引 + 按需加载 references"的布局借鉴自开源项目 `virgiliojr94/book-to-skill`(MIT 协议),`/learn` 的实现在注释里明确写了出处;第二,"synthesize, never reproduce"这条既是质量要求(蒸馏出结构而不是复制原文),也直接是版权红线——不能大段照抄原文。第三,处理大材料时要求"一次一个章节地读、蒸馏、落盘",而不是一次性把整本书塞进对话上下文再统一处理——这既是工程约束(避免撑爆上下文),也是质量约束(逐章处理能给出更细的、带章节引用的笔记,而不是一次性摘要出的粗粒度概括)。

## 真实例子:一份单文件技能

`skills/research/arxiv/SKILL.md` 是"小材料→单文件"这一类的典型样本——一个纯 API 用法说明,没有配套脚本,`## Quick Reference` 直接是一张命令表:

```markdown
---
name: arxiv
description: "Search arXiv papers by keyword, author, category, or ID."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Research, Arxiv, Papers, Academic, Science, API]
    related_skills: [ocr-and-documents]
---

# arXiv Research

Search and retrieve academic papers from arXiv via their free REST API. No
API key, no dependencies — just curl.

## Quick Reference

| Action | Command |
|--------|---------|
| Search papers | `curl "https://export.arxiv.org/api/query?search_query=all:QUERY&max_results=5"` |
| Get specific paper | `curl "https://export.arxiv.org/api/query?id_list=2402.03300"` |
...
```

这份文件全长不到 100 行,`description` 严格卡在 60 字符以内,正文没有 `references/`——因为一个 REST API 的用法本来就不需要拆成多个子文件。

`skills/productivity/pdf/SKILL.md` 则展示了"支持文件"这一层是怎么工作的:它的目录下有 `scripts/`(十几个 argparse CLI 脚本)和 `references/forms.md`(AcroForm 表单的详细说明),SKILL.md 正文只在需要时才提一句"表单细节见 `references/forms.md`",不会把表单排版的全部细节直接写进主文件。这不是本篇讲的"知识库布局"那种极端案例(pdf 技能仍然是"一个类别的完整操作手册",不是"一本书拆成的索引"),但它体现的是同一个原则:**篇幅超出正文舒适区的内容,一律挪到按需加载的支持文件里**,SKILL.md 本身只保留导航信息。

## agentskills.io 兼容性

`tools/skills_tool.py` 的 docstring 直接标注"SKILL.md Format (YAML Frontmatter, agentskills.io compatible)",`assets/` 目录也明确注明是"agentskills.io standard"引入的约定。README 里同样把这一点当作一句卖点写了出来:

```
# README.md:26(节选)
... Compatible with the agentskills.io open standard.
```

对使用者的实际意义是:符合 agentskills.io 规范写出来的 SKILL.md(比如从别的兼容工具导出的技能包),理论上可以直接放进 `~/.hermes/skills/` 或 `skills/` 目录被 Hermes 识别加载,不需要做格式转换。Hermes 自己的 HARDLINE 标准(60 字符 description、固定 section 顺序等)是在这个开放标准之上叠加的**更严格**的一层约定,只在仓库内建技能的评审中强制,并不是加载器会拒绝不符合它的外部技能——`_validate_frontmatter` 的硬校验只卡 `MAX_DESCRIPTION_LENGTH=1024`(标准兼容层),60 字符那道更严的关卡只在 `new_skill=True`(即本地新建)时触发。

## 小结与思考题

Hermes 的技能格式在 agentskills.io 开放标准的基础上,叠加了一套自己的强制标准:frontmatter 的 `description` 有两级限制——1024 字符是保持标准兼容的软上限,60 字符是新建技能时代码硬拒绝的门槛,理由是系统提示词里常驻的技能目录会把描述截断到这个长度,超出部分永远不会被模型看到。正文按固定的"标题→When to Use→Prerequisites→How to Run→Quick Reference→Procedure→Pitfalls→Verification"顺序组织,允许省略但要求省略必须有实质理由。材料体量决定了产出形态:小材料写成一份自包含的 SKILL.md,大材料(书、论文集、规范文档)写成"精简索引 + 按需加载的 `references/` 子文件"这种知识库布局,核心思路是**避免把还没被查询到的内容一次性塞进上下文**——索引常驻、细节按需,索引本身也不允许无限膨胀。

思考题:

1. `_validate_frontmatter` 里 60 字符的硬拒绝只发生在 `new_skill=True`(即 `action="create"`)路径,`patch`/`edit` 故意放过存量超长描述。如果你要在不破坏"历史技能可维护"这条设计意图的前提下,推动存量技能逐步收敛到 60 字符以内,你会在哪一层加这个提醒——校验函数、curator 的复审 prompt,还是别的地方?
2. 知识库布局要求"一次只处理一个章节,不要把整个大材料一次性塞进对话上下文",这对模型的"逐章一致性"提出了要求——如果材料里前后章节对同一个概念有不同表述,模型分批蒸馏时怎么保证 `references/` 里的多个文件不会互相矛盾?这是 `/learn` 这套机制目前没有覆盖到的问题吗?
