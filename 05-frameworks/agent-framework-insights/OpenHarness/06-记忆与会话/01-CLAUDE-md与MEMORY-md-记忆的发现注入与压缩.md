# CLAUDE.md 与 MEMORY.md：记忆的发现、注入与压缩

> OpenHarness 的"记忆"其实是两套并行但职责完全不同的系统:`CLAUDE.md` 是静态的、人写的项目约定,靠向上遍历目录树来发现;`MEMORY.md` 加一堆结构化的 `.md` 记忆文件,是动态的、可以被 Agent 自己写入和淘汰的长期知识库,靠启发式打分来决定哪些值得塞进本轮的上下文。README 里"Memory / Session"一节把它们并列成两条 bullet 不是巧合——本篇把这两条路径,以及围绕它们的发现、排序、去重、注入、回写全流程,结合真实源码讲清楚。

## 学习目标

- 看懂 `discover_claude_md_files` 怎么从 `cwd` 向上遍历目录树发现 `CLAUDE.md`、`.claude/CLAUDE.md` 和 `.claude/rules/*.md`,以及这个顺序为什么重要。
- 理解 `MEMORY.md` 在 OpenHarness 里的真实定位——它只是一份索引,真正的记忆内容分散在同目录下的一堆独立 `.md` 文件里,每个文件都有一份 schema-v1 的 YAML frontmatter。
- 理解记忆条目怎么被 `scan_memory_files` 发现、被 `find_relevant_memories` 打分排序、又怎么通过 `select_relevant_memories`/`format_relevant_memories` 注入到 system prompt,以及 `mark_memory_used` 怎么把"被召回过"反馈回打分公式。
- 弄清楚"project 记忆""team 记忆""agent 记忆"这三个概念在代码里到底是不是一回事——它们是三条独立的存储路径,彼此正交,不是简单的"单 agent vs 多 agent"划分。
- 知道 LLM 驱动的自动记忆提炼(`services/memory_extract`)怎么把当前这套发现/排序机制串成一个完整的闭环。

## 背景与设计动机

`build_runtime_system_prompt`(`src/openharness/prompts/context.py`)是整条链路的汇合点,它把好几类"注入到 system prompt 里的上下文"依次拼接起来:基础 system prompt、权限模式说明、技能列表、`CLAUDE.md`、本地个性化规则(下一篇会讲)、issue/PR 上下文,最后才是记忆。这个顺序本身就是一种设计声明——项目约定(`CLAUDE.md`)排在记忆之前,意味着"这是谁定的规矩"比"Agent 自己攒的经验"优先级更高。

`CLAUDE.md` 和 `MEMORY.md` 要解决的是两个不同性质的问题:

- **发现问题**:项目的"该怎么做"写在哪?可能在项目根目录,可能在某个上级目录(monorepo 场景),也可能被拆成多份规则文件——这是 `CLAUDE.md` 系统要解决的。
- **选择问题**:如果一个项目跑了几十次会话,攒下几十条记忆,当前这一轮对话只有几千 token 的预算,该塞哪几条?这是 `MEMORY.md` + 相关性排序系统要解决的,`CLAUDE.md` 不需要考虑这个问题,因为它假设项目约定文件本来就不多、不大。

## 核心机制详解

### CLAUDE.md 发现:向上遍历目录树

`discover_claude_md_files` 的实现只有 20 多行,但把"发现顺序即优先级"这件事做得很直接:

```python
# src/openharness/prompts/claudemd.py
def discover_claude_md_files(cwd: str | Path) -> list[Path]:
    """Discover relevant CLAUDE.md instruction files from the cwd upward."""
    current = Path(cwd).resolve()
    results: list[Path] = []
    seen: set[Path] = set()

    for directory in [current, *current.parents]:
        for candidate in (
            directory / "CLAUDE.md",
            directory / ".claude" / "CLAUDE.md",
        ):
            if candidate.exists() and candidate not in seen:
                results.append(candidate)
                seen.add(candidate)

        rules_dir = directory / ".claude" / "rules"
        if rules_dir.is_dir():
            for rule in sorted(rules_dir.glob("*.md")):
                if rule not in seen:
                    results.append(rule)
                    seen.add(rule)

        if directory.parent == directory:
            break

    return results
```

三个细节值得拆开看:

1. **遍历顺序是 `[current, *current.parents]`**——当前工作目录先被检查,然后逐级往上到文件系统根。这意味着结果列表里,离 `cwd`最近的文件排在最前面。`load_claude_md_prompt` 直接按这个顺序拼接成 Markdown 段落,没有再做优先级排序或去重覆盖——所以在 monorepo 里,子目录的 `CLAUDE.md` 和根目录的 `CLAUDE.md` 会**同时**出现在 system prompt 里,子目录的先出现。这是一种"叠加"而不是"覆盖"的语义,和很多约定系统(比如 `.eslintrc` 的就近覆盖)不同,需要项目自己保证多份文件不冲突。
2. **每一级目录还会检查两种写法**:裸的 `CLAUDE.md` 和 `.claude/CLAUDE.md`,以及 `.claude/rules/*.md` 整个目录。后者是把单文件的"项目说明书"泛化成了多文件的规则集合——这和 Claude Code 生态里 `.claude/rules/` 目录的用法一致,允许团队把编码风格、测试规范、安全规则拆成独立文件分别维护,而不是全部塞进一个越来越臃肿的 `CLAUDE.md`。
3. **`if directory.parent == directory: break`** 是标准的"到达文件系统根"判断(比如 `/` 的 parent 还是 `/`),防止死循环。

加载阶段做了长度截断,避免单个巨大文件把上下文预算吃满:

```python
# src/openharness/prompts/claudemd.py
def load_claude_md_prompt(cwd: str | Path, *, max_chars_per_file: int = 12000) -> str | None:
    """Load discovered instruction files into one prompt section."""
    files = discover_claude_md_files(cwd)
    if not files:
        return None

    lines = ["# Project Instructions"]
    for path in files:
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars_per_file:
            content = content[:max_chars_per_file] + "\n...[truncated]..."
        lines.extend(["", f"## {path}", "```md", content.strip(), "```"])
    return "\n".join(lines)
```

每个文件独立截断到 12000 字符,而不是对拼接后的总长度做一次性截断——这样即使发现了 5 份规则文件,也不会因为第一份特别长就把后面几份完全挤掉。

值得一提的是,这套发现机制不是对所有场景都强制生效的:协调者(coordinator)体系里定义的每种子代理(`agent_definitions.py`)都带一个 `omit_claude_md: bool = False` 开关,专门用来给某些子代理(比如一个只做只读代码审查、不需要知道项目"怎么改代码"约定的窄任务 worker)跳过这段注入,省出上下文预算。CLI 的 `/init` 命令(`commands/registry.py`)会在项目里还没有 `CLAUDE.md` 时,顺手创建一份最小模板,同时初始化项目记忆目录和空的 `MEMORY.md`——这一步基本对标 Claude Code 的 `/init`。

### MEMORY.md 是索引,不是记忆体

和 `CLAUDE.md` 不同,`MEMORY.md` 本身不存放记忆内容,它只是一份指向其他文件的目录页。真正的记忆是同目录下一堆独立的 `.md` 文件,每份都以 YAML frontmatter 开头,遵循 schema-v1:

```python
# src/openharness/memory/schema.py
SCHEMA_VERSION = 1

MemoryType = Literal["user", "feedback", "project", "reference"]
MemoryScope = Literal["private", "project", "team"]

FRONTMATTER_FIELDS = (
    "schema_version", "id", "name", "description", "type", "scope",
    "category", "importance", "source", "signature", "created_at",
    "updated_at", "ttl_days", "disabled", "supersedes", "tags",
)
```

字段里几个设计点:

- `ttl_days` + `is_memory_expired`:记忆可以设置过期时间,过期后 `scan_memory_files` 默认会把它过滤掉(除非显式传 `include_expired=True`)——这是给"这条信息只在某个阶段有效"的记忆(比如"当前正在排查某个 bug,临时约定"）一个自然消亡的机制。
- `signature` + `compute_memory_signature`:对正文做归一化(转小写、折叠空白、去标点)后连同 `type`/`category` 一起算 SHA-256,`add_memory_entry` 用这个签名做去重——语义相同但措辞略有差异的两条记忆会被判定为同一条,直接更新旧文件而不是新建一份。
- `supersedes`:允许一条新记忆声明"取代"哪些旧记忆 id,配合下面会讲的过期/淘汰机制,支撑记忆随项目演进而更新而不是无限堆积。

`MEMORY.md` 本身作为索引,注入时也有长度保护——`truncate_entrypoint_content` 同时按行数(默认 200 行)和字节数(默认 25000 字节)两个维度截断,任一超限就在结尾追加一段警告文本,提醒模型"只加载了一部分,把明细放到独立主题文件里,索引条目保持一行":

```python
# src/openharness/memory/schema.py
def truncate_entrypoint_content(
    raw: str, *, max_lines: int = MAX_ENTRYPOINT_LINES, max_bytes: int = MAX_ENTRYPOINT_BYTES,
) -> EntrypointView:
    lines = raw.splitlines()
    was_line_truncated = len(lines) > max_lines
    text = "\n".join(lines[:max_lines])
    encoded = text.encode("utf-8")
    was_byte_truncated = len(encoded) > max_bytes
    ...
```

这份策略还配了一段固定文本 `MEMORY_POLICY_LINES`,每次都会跟着 `MEMORY.md` 一起注入到 system prompt,直接用自然语言告诉模型该怎么用这套系统:只存"不能从当前文件/文档/git 历史/工具输出里廉价推导出来"的信息、遇到矛盾要更新而不是重复记一条、用户说"忽略记忆"就不能再引用记忆内容、记忆可能过时要和当前项目状态核对、不能把密钥和私人上下文写进团队记忆。这段策略文本本质上是把"记忆该怎么维护"这件事也交给了模型自己去执行,而不是靠外部代码强制。

### 记忆怎么被发现、打分、注入

完整链路是 `scan_memory_files` → `find_relevant_memories` → `select_relevant_memories` → `format_relevant_memories` → `mark_memory_used`,五个函数分别对应"发现候选""打分排序""应用可选的二次筛选""渲染成 prompt 文本""记录被使用过"。

`scan_memory_files` 只是简单地 glob 当前记忆目录下所有 `.md`(排除 `MEMORY.md` 本身),解析 frontmatter,过滤掉禁用和过期的条目,按修改时间倒序:

```python
# src/openharness/memory/scan.py
def scan_memory_files(
    cwd: str | Path, *, max_files: int | None = 50,
    include_disabled: bool = False, include_expired: bool = False,
    memory_dir: str | Path | None = None,
) -> list[MemoryHeader]:
    memory_dir = Path(memory_dir) if memory_dir is not None else get_project_memory_dir(cwd)
    headers: list[MemoryHeader] = []
    for path in memory_dir.glob("*.md"):
        if path.name == "MEMORY.md":
            continue
        ...
    headers.sort(key=lambda item: item.modified_at, reverse=True)
    return headers[:max_files] if max_files is not None else headers
```

真正的相关性打分在 `search.py` 里,是一个纯启发式、不依赖任何外部索引的实现:

```python
# src/openharness/memory/search.py
def find_relevant_memories(query: str, cwd: str | Path, *, max_results: int = 5) -> list[MemoryHeader]:
    tokens = _tokenize(query)
    ...
    for header in scan_memory_files(cwd, max_files=100):
        meta = f"{header.title} {header.description}".lower()
        body = header.body_preview.lower()
        meta_hits = sum(1 for t in tokens if t in meta)
        body_hits = sum(1 for t in tokens if t in body)
        usage = get_memory_usage(cwd, header.id, memory_dir=header.path.parent)
        score = (
            meta_hits * 2.0
            + body_hits
            + header.importance * 0.4
            + min(int(usage["use_count"]), 5) * 0.1
            + _recency_boost(header)
        )
        if meta_hits or body_hits:
            scored.append((score, header))
    scored.sort(key=lambda item: (-item[0], -item[1].modified_at))
    return [header for _, header in scored[:max_results]]


def _tokenize(text: str) -> set[str]:
    ascii_tokens = {t for t in re.findall(r"[A-Za-z0-9_]+", text.lower()) if len(t) >= 3}
    han_chars = set(re.findall(r"[一-鿿㐀-䶿]", text))
    return ascii_tokens | han_chars
```

这里的 `_tokenize` 对中日韩文本做了特殊处理——不是像 ASCII token 那样要求长度≥3,而是把每个汉字都当作一个独立的检索单元。这和某些同类项目里用 SQLite FTS5 + 自定义 CJK bigram tokenizer 解决同一个问题的思路完全不同:OpenHarness 这里没有引入全文索引,就是一次性 `re.findall` 扫描字符集,简单但足够应付"记忆文件数量通常是几十到几百"这个量级。打分公式本身也值得注意:元数据(标题+描述)命中权重是正文的 2 倍,外加 `importance`(记忆自带的重要度标注)、`use_count`(封顶 5 次,`* 0.1`)、以及 14/30 天内更新过的新鲜度加成——命中次数越多的记忆,后续越容易被召回,是一个很轻量的正反馈。

`select_relevant_memories`(`relevance.py`)在这层启发式排序之上,还留了一个可选的二次筛选钩子:

```python
# src/openharness/memory/relevance.py
def select_relevant_memories(
    query: str, cwd: str | Path, *, max_results: int = 5,
    already_surfaced: set[str] | None = None,
    selector: MemorySelector | None = None,
) -> list[RelevantMemory]:
    surfaced = already_surfaced or set()
    heuristic = [
        header for header in find_relevant_memories(query, cwd, max_results=max(10, max_results * 3))
        if (header.relative_path or str(header.path)) not in surfaced
    ]
    selected = _apply_selector(query, heuristic, selector=selector, max_results=max_results)
    ...
```

先用启发式打分取出 `max_results * 3` 条候选(留出冗余),`selector` 是一个可选的 `Callable[[str, list[MemoryHeader]], list[str]]`——如果调用方传入一个真正调用模型做二次排序的函数(比如把候选清单丢给一次侧路的模型调用,让它按路径返回排序结果),`_apply_selector` 会优先采用模型给出的顺序,不足的部分再用启发式结果补齐。当前 `build_runtime_system_prompt` 里调用 `select_relevant_memories` 时没有传 `selector`,所以运行时走的是纯启发式路径;这个参数更像是给未来或自定义集成留的扩展点。

渲染阶段 `format_relevant_memories` 会给每条记忆加一个新鲜度提示——只有 24 小时以上没更新的记忆才会附带警告文案:

```python
# src/openharness/memory/schema.py
def memory_freshness_text(mtime: float, *, now: float | None = None) -> str:
    days = memory_age_days(mtime, now=now)
    if days <= 1:
        return ""
    return (
        f"This memory is {days} days old. Memories are point-in-time observations; "
        "verify claims against the current project state before treating them as facts."
    )
```

最后,只要这一轮真的有记忆被选中注入,`mark_memory_used` 就会把它们的使用次数 +1、更新 `last_used_at`,写回同目录下的 `usage_index.json`——这个文件正是上面打分公式里 `get_memory_usage(...)["use_count"]` 的数据来源,形成"被召回 → 使用计数上升 → 更容易再被召回"的闭环。

### 三条独立的存储路径:project / team / agent 记忆

代码库里同时出现了三个和"记忆"相关但语义不同的目录概念,容易被误当成同一件事的三种视角,实际上它们是三条完全独立、互不感知的存储路径:

| 概念 | 定位函数 | 存储位置 | 是否自动注入 system prompt |
|---|---|---|---|
| **project 记忆**(默认) | `get_project_memory_dir` | `~/.openharness/data/memory/<项目名>-<sha1(cwd)[:12]>/` | 是——本篇讲的整条 scan/relevance 流程 |
| **team 记忆**(一种 `scope`) | `get_team_memory_dir` | 上面那个目录下的 `team/` 子目录 | 否,除非普通条目 frontmatter 里 `scope: team` |
| **agent 记忆**(按 agent_type) | `get_agent_memory_dir` | 按 `scope` 参数分别落在项目记忆目录下的 `agent/<type>/`、`~/.openharness/data/agent-memory/<type>/` 或项目内 `.openharness/agent-memory-local/<type>/` | 否,仅通过 `/memory agent` 命令手动管理 |

"team 记忆"不是一个独立的记忆系统,而是普通记忆条目的一种 `scope` 取值——`add_memory_entry` 在 `scope == "team"` 时会先跑一遍秘密扫描,再把文件写进项目记忆目录下的 `team/` 子目录:

```python
# src/openharness/memory/manager.py
if scope == "team":
    from openharness.memory.team import check_team_memory_secrets, ensure_team_memory_vault
    secret_error = check_team_memory_secrets(content)
    if secret_error:
        raise ValueError(secret_error)
    memory_dir = ensure_team_memory_vault(cwd)
```

`team.py` 里的 `SECRET_RULES` 覆盖了私钥、AWS/GitHub/OpenAI/Anthropic 密钥格式,以及"看起来像密钥赋值"的通用模式;`validate_team_memory_write_path` 还做了路径穿越和符号链接逃逸校验,保证写入目标不会跳出团队记忆目录。需要说明的是:在这版代码里,"team 记忆"仅仅意味着"这份内容通过了秘密扫描、被隔离存放在一个约定目录里",没有找到额外的跨机器同步或推送逻辑——它依然是每台机器本地的 `~/.openharness/data/...` 目录,如果团队真的要共享这份记忆,还得靠外部机制(比如把这个目录纳入版本控制)自己解决。

"agent 记忆"(`memory/agent.py`)则是完全不同维度的东西——它是**按协调者体系里定义的子代理类型**(比如某个专门做代码审查的 agent persona)分别开辟的记忆保管库,而不是"多智能体共享"的意思。每个 `agent_type` 可以选择三种作用域之一:`user`(全局,跨项目共享)、`project`(挂在当前项目记忆目录下的 `agent/<type>/`)、`local`(挂在项目内的 `.openharness/agent-memory-local/<type>/`,不进版本库但和 repo 物理绑定)。它还配了一套"从快照初始化"的机制:

```python
# src/openharness/memory/agent.py
def initialize_agent_memory_from_snapshot(
    cwd: str | Path, agent_type: str, scope: AgentMemoryScope, *, replace: bool = False,
) -> Path | None:
    snapshot_dir = get_agent_snapshot_dir(cwd, agent_type)
    if not snapshot_dir.exists():
        return None
    target = ensure_agent_memory_vault(cwd, agent_type, scope)
    ...
    for src in snapshot_dir.rglob("*.md"):
        ...
        if replace or not dest.exists() or _is_default_agent_index(dest):
            shutil.copy2(src, dest)
    return target
```

也就是说,项目可以预先在 `.openharness/agent-memory-snapshots/<agent_type>/` 里放一份"出厂记忆"(比如给"代码审查" persona 预置一套团队审查标准),新会话第一次用到这个 agent 类型时可以从快照初始化。但要强调的是:这套机制目前只通过 `/memory agent` 命令手动触发管理,**没有**接入 `build_runtime_system_prompt` 的自动注入流程——它是为协调者体系里的子代理身份持久化预留的基础设施,不是"多智能体共同维护一份记忆"的意思,后续讲多智能体协作的章节会再回来讨论协调者本身怎么使用这套机制。

### 闭环的最后一块:LLM 驱动的自动提炼

前面讲的都是"记忆已经存在,怎么被发现和注入"。记忆最初从哪来?除了用户手动调用 `add_memory_entry`(比如通过 `/memory add`),`services/memory_extract` 还提供了一条自动化路径:每轮对话结束后,如果 `settings.memory.auto_extract_enabled` 打开,就会额外发起一次侧路模型调用,让模型判断"这轮对话里有没有值得长期记住的、无法从文件/git 历史里廉价推导出的事实":

```python
# src/openharness/services/memory_extract/__init__.py
EXTRACTION_SYSTEM_PROMPT = """You maintain OpenHarness durable memory.
Save only stable, future-useful facts that are not derivable from current files,
git history, or documentation. Prefer updating existing memories conceptually
over duplicating them. Do not save secrets. If nothing is worth saving, return
{"memories": []}.
"""
```

模型返回的 JSON 记录经 `parse_extraction_records` 解析后,直接调用本篇前面讲过的 `add_memory_entry` 写入——也就是说,自动提炼出来的记忆和手写的记忆走的是完全同一套 schema、同一套去重签名、同一套 scan/relevance 注入流程,没有单独的"AI 记忆"通道。`has_memory_writes_since` 还做了一层防重入检查:如果这轮对话里模型自己已经用 `write_file`/`edit_file` 直接写过记忆文件,就跳过这次额外的提炼调用,避免同一轮对话被记两遍。这套自动提炼是"记忆的自动写入闭环",和下一篇要讲的"从对话里提炼环境事实"是两套独立系统,容易被混为一谈,下一篇会专门辨析。

## 常见问题/易踩坑

- **`CLAUDE.md` 是叠加不是覆盖**:monorepo 里子目录和根目录的 `CLAUDE.md` 会同时注入,如果两份文件对同一件事给出矛盾的指令,模型看到的是叠加后的文本,不会自动"就近覆盖"。规则冲突需要项目自己维护一致性,或者把差异化的部分拆到 `.claude/rules/` 里明确分工。
- **记忆条目数量上去之后,`scan_memory_files(max_files=100)` 这个上限可能截断掉冷门但相关的记忆**——排序发生在截断之前的 100 条候选里,如果项目记忆文件超过这个数字,末尾的部分永远进不了打分环节。
- **`auto_extract_enabled` 默认是关闭的**(`MemorySettings.auto_extract_enabled: bool = False`),不打开这个开关,记忆只能靠手动 `/memory add` 或模型主动调用写文件工具产生。

## 小结

这一篇把 OpenHarness 记忆系统里"从发现到注入"的完整链路过了一遍:`CLAUDE.md` 靠向上遍历目录树 + `.claude/rules/` 目录发现静态约定;`MEMORY.md` 只是索引,真正的记忆条目是一堆带 schema-v1 frontmatter 的独立文件,靠启发式打分(元数据权重、重要度、使用次数、新鲜度)决定谁能进入本轮上下文,并通过 `mark_memory_used` 形成使用反馈闭环;project/team/agent 三种"记忆"实际上是三条正交的存储路径,不能简单类比成"单 agent vs 多 agent";而 `services/memory_extract` 则把这条链路和模型自身的判断力接了起来,让记忆可以在对话结束后自动生长。下一篇会转向会话本身——`session_id` 怎么落盘、`/resume` 怎么找回历史对话、以及被中断的会话尾巴是怎么被修复的。
