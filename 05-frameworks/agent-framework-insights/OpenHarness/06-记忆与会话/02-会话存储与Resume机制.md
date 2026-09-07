# 会话存储与 Resume 机制

> OpenHarness 的会话持久化没有用数据库,就是一份 JSON 文件——但"每轮对话结束就落盘一次"这个时机选择,以及恢复时对消息列表做的一次"消毒"处理,才是这套机制真正的设计重点。本篇结合 `services/session_storage.py`、`services/session_backend.py` 和 `/resume` 命令的真实实现,讲清楚 `oh`/`ohmo` 的会话是怎么存、怎么找回来的。

## 学习目标

- 看懂一份会话快照 JSON 里到底存了哪些字段,以及为什么 `tool_metadata` 只持久化一个白名单子集而不是整个字典。
- 理解会话保存的触发时机——不是"退出时才存",而是每次用户提交一轮对话、无论正常结束还是因为 `max_turns` 被打断,都会落盘一次。
- 看懂 `/resume` 命令怎么区分"带参数恢复指定会话"和"不带参数列出会话供选择"两种用法,以及它在没有命名快照时如何回退到 `latest.json`。
- 理解 `sanitize_conversation_messages` 为什么必须在恢复历史消息时跑一遍——它在修复的是哪一类具体的损坏状态。
- 认识 `SessionBackend` 这层 Protocol 抽象的作用,以及它和本章第一篇讲的记忆存储在路径命名上的一致性。

## 背景与设计动机

会话存储要解决的问题和记忆存储表面相似(都是"把状态落到磁盘上"),但目的不同:记忆是要长期沉淀、可检索、可打分排序的知识;会话存储要解决的是"进程重启或用户主动 `/resume` 之后,怎么把上一轮对话的完整上下文原样接回来"——包括模型看到的每一条消息、当时用的模型和 system prompt、累计的 token 用量,以及一部分需要跨轮次延续的运行时状态(比如压缩检查点、任务聚焦状态)。

这意味着会话快照必须**足够完整**才能恢复对话,但又不能把 `tool_metadata` 这种运行时字典原样全塞进去——里面可能混着不可序列化的对象、连接句柄之类的临时状态。`services/session_storage.py` 用一份显式白名单解决了这个矛盾。

## 核心机制详解

### 会话快照:一份 JSON 里存了什么

`save_session_snapshot` 是唯一的写入入口,payload 结构一目了然:

```python
# src/openharness/services/session_storage.py
def save_session_snapshot(
    *, cwd: str | Path, model: str, system_prompt: str,
    messages: list[ConversationMessage], usage: UsageSnapshot,
    session_id: str | None = None, tool_metadata: dict[str, object] | None = None,
) -> Path:
    session_dir = get_project_session_dir(cwd)
    sid = session_id or uuid4().hex[:12]
    now = time.time()
    messages = sanitize_conversation_messages(messages)
    summary = ""
    for msg in messages:
        if msg.role == "user" and msg.text.strip():
            summary = msg.text.strip()[:80]
            break

    payload = {
        "session_id": sid,
        "cwd": str(Path(cwd).resolve()),
        "model": model,
        "system_prompt": system_prompt,
        "messages": [message.model_dump(mode="json") for message in messages],
        "usage": usage.model_dump(),
        "tool_metadata": _persistable_tool_metadata(tool_metadata),
        "created_at": now,
        "summary": summary,
        "message_count": len(messages),
    }
```

几个字段值得单独说明:

- **`system_prompt` 整份存了下来**,但这更多是留档/导出用途——恢复会话时(见下文)只是把 `messages` 塞回引擎,`system_prompt` 会在下一次真正提交新消息时,由 `build_runtime_system_prompt` 用**当前**的 `CLAUDE.md`、记忆、权限模式等重新构建一份新的,而不是复用快照里保存的旧版本。这是一个容易被忽略的点:恢复的是对话历史,不是当时的完整运行时环境。
- **`usage` 是 `UsageSnapshot`**(`input_tokens`/`output_tokens`),和成本追踪直接挂钩——每次落盘都带上截至当前的累计用量,这样即使进程重启,`/resume` 之后的用量统计也能从正确的基线继续,而不是清零重算。
- **`summary`** 只是取第一条用户消息文本的前 80 个字符,纯粹是给会话列表做展示用的,不参与任何检索逻辑——这一点和第一篇里记忆条目的 `description` 字段(会参与相关性打分)形成对比,会话快照本身没有做类似记忆那套启发式排序,`/resume` 列表就是简单按时间倒序。

`tool_metadata` 没有整份持久化,而是过了一遍白名单:

```python
# src/openharness/services/session_storage.py
_PERSISTED_TOOL_METADATA_KEYS = (
    "permission_mode", "read_file_state", "invoked_skills",
    "async_agent_state", "async_agent_tasks", "recent_work_log",
    "recent_verified_work", "task_focus_state",
    "compact_checkpoints", "compact_last",
)

def _persistable_tool_metadata(tool_metadata: dict[str, object] | None) -> dict[str, Any]:
    if not isinstance(tool_metadata, dict):
        return {}
    payload: dict[str, Any] = {}
    for key in _PERSISTED_TOOL_METADATA_KEYS:
        if key in tool_metadata:
            payload[key] = _sanitize_metadata(tool_metadata[key])
    return payload
```

只挑这 10 个 key 落盘,原因看名字就能猜到大半:`permission_mode`/`invoked_skills`/`task_focus_state` 这些是恢复对话后仍然有意义的"会话身份"状态;`compact_checkpoints`/`compact_last` 是压缩边界记录,恢复会话时需要知道"上次是从哪里压缩过的";而没有入选白名单的字段(比如各种运行时缓存、进程内句柄)就直接被丢弃——`_sanitize_metadata` 对入选的值做了一次递归清洗,把 `Path` 转成字符串、把 `set`/`tuple` 转成 `list`,保证整份 payload 是纯 JSON 可序列化的。这是一种显式的"状态分层":哪些运行时状态属于"应该跨进程重启存活的会话身份",哪些只是"这次进程运行期间的临时缓存",由这份白名单说了算,而不是靠隐式的可序列化判断。

### 存储路径:和记忆系统同一套哈希命名法

会话目录的定位函数和第一篇里记忆目录的定位函数用的是同一个模式:

```python
# src/openharness/services/session_storage.py
def get_project_session_dir(cwd: str | Path) -> Path:
    path = Path(cwd).resolve()
    digest = sha1(str(path).encode("utf-8")).hexdigest()[:12]
    session_dir = get_sessions_dir() / f"{path.name}-{digest}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir
```

对比第一篇的 `get_project_memory_dir`——同样是 `{目录名}-{sha1(绝对路径)[:12]}` 的组合作为文件夹名,同样落在 `get_data_dir()` 之下(会话是 `sessions/` 子目录,记忆是 `memory/` 子目录)。这个一致性不是巧合:两者都要解决"同名但不同路径的两个项目不能共用一个存储目录"这个问题,取路径哈希前 12 位加人类可读的目录名做前缀,既避免了冲突,文件夹名本身也还能大致看出对应哪个项目。

单次落盘会同时写两份文件:

```python
# src/openharness/services/session_storage.py
latest_path = session_dir / "latest.json"
atomic_write_text(latest_path, data)

session_path = session_dir / f"session-{sid}.json"
atomic_write_text(session_path, data)
```

`latest.json` 永远指向"这个项目最近一次的会话",`session-{sid}.json` 是按 id 永久保留的具名快照——这个双写策略直接决定了后面 `/resume` 命令的两种查找路径(见下文)。写入用的是 `atomic_write_text`,避免进程被中断时留下半写的 JSON 文件。

### 保存时机:每轮对话结束就落盘,不等会话退出

会话快照不是等用户敲 `/exit` 才保存的。`ui/runtime.py` 里,不管这一轮对话是正常走完、还是因为触发 `MaxTurnsExceeded` 被打断、还是走的是 `continue_pending` 续接分支,末尾都会调用一次 `save_snapshot`:

```python
# src/openharness/ui/runtime.py(节选,三处调用形态一致)
try:
    async for event in bundle.engine.submit_message(user_message or line):
        await render_event(event)
except MaxTurnsExceeded as exc:
    await print_system(f"Stopped after {exc.max_turns} turns (max_turns).")
    ...
    bundle.session_backend.save_snapshot(
        cwd=bundle.cwd, model=settings.model, system_prompt=system_prompt,
        messages=bundle.engine.messages, usage=bundle.engine.total_usage,
        session_id=bundle.session_id, tool_metadata=bundle.engine.tool_metadata,
    )
    sync_app_state(bundle)
    return True
bundle.session_backend.save_snapshot(
    cwd=bundle.cwd, model=settings.model, system_prompt=system_prompt,
    messages=bundle.engine.messages, usage=bundle.engine.total_usage,
    session_id=bundle.session_id, tool_metadata=bundle.engine.tool_metadata,
)
```

这个设计意味着会话持久化实际上是**每轮自动检查点**,而不是"退出前的一次性收尾动作"。好处很直接:进程崩溃、终端被关掉、机器断电,只要上一轮对话已经跑完,`/resume` 都能找回到那个点,最多丢失当前正在进行、还没跑完的这一轮。代价是每轮结束都要写一次 JSON——对于消息历史很长的会话,这是一次不小的 I/O,但 `atomic_write_text` 保证了不会因为频繁写入而破坏文件完整性。

### /resume:带参数找具体会话,不带参数列清单

`/resume` 命令的分支逻辑直接对应上一节"双写"的存储结构:

```python
# src/openharness/commands/registry.py
async def _resume_handler(args: str, context: CommandContext) -> CommandResult:
    tokens = args.strip().split()

    # /resume <session_id> — load a specific session
    if tokens:
        sid = tokens[0]
        snapshot = context.session_backend.load_by_id(context.cwd, sid)
        if snapshot is None:
            return CommandResult(message=f"Session not found: {sid}")
        messages = sanitize_conversation_messages(
            [ConversationMessage.model_validate(item) for item in snapshot.get("messages", [])]
        )
        context.engine.load_messages(messages)
        summary = snapshot.get("summary", "")[:60]
        return CommandResult(
            message=f"Restored {len(messages)} messages from session {sid}"
            + (f" ({summary})" if summary else ""),
            replay_messages=messages,
        )

    # /resume — list sessions (for the TUI to show a picker)
    sessions = context.session_backend.list_snapshots(context.cwd, limit=10)
    if not sessions:
        # Fall back to latest.json
        snapshot = context.session_backend.load_latest(context.cwd)
        ...
    ...
```

`load_by_id` 会先尝试按具名文件 `session-{session_id}.json` 查找,找不到时还有一层兜底——如果 `latest.json` 里记录的 `session_id` 恰好等于传入的 id,或者用户直接传的就是字面量 `"latest"`,也能命中(这段逻辑在 `session_storage.load_session_by_id` 里)。不带参数时走的是"列清单"分支:`list_snapshots` 优先扫描所有 `session-*.json`,按文件修改时间倒序取前 `limit` 条;如果一条具名快照都没有(比如项目里只跑过一次对话,还没产生第二次覆盖 `latest.json`),就直接退回到读 `latest.json` 直接恢复,而不是给用户看一个空列表。这个"没有历史就直接接上最近一次"的回退,是为了让单次会话的用户也能无感 `/resume`,不需要先经历一次"选择"的多余步骤。

### sanitize_conversation_messages:修复被打断的会话尾巴

无论是保存前还是恢复后,消息列表都会经过 `sanitize_conversation_messages`。它要处理的是一类具体场景:如果会话在模型刚发起一次工具调用(`tool_use`)、还没收到对应的 `tool_result` 时就被中断(比如进程崩溃、用户强制退出),持久化下来的最后一条助手消息就是一个"悬空"的工具调用请求。这种残缺的尾巴如果原样喂回给模型 API,兼容 OpenAI 协议的一些 provider 会直接拒绝这次请求:

```python
# src/openharness/engine/messages.py
def sanitize_conversation_messages(messages: list[ConversationMessage]) -> list[ConversationMessage]:
    """Normalize restored conversation history into a provider-safe sequence.

    This drops legacy empty assistant messages and trims malformed trailing tool
    turns, such as an assistant ``tool_use`` message that never received a
    matching user ``tool_result`` response. Those broken tails can happen when a
    session is interrupted mid-turn and would later cause OpenAI-compatible
    providers to reject the resumed conversation.
    """
    sanitized: list[ConversationMessage] = []
    pending_tool_use_ids: set[str] = set()
    pending_tool_use_index: int | None = None

    for message in messages:
        if message.role == "assistant" and message.is_effectively_empty():
            continue
        ...
        if pending_tool_use_ids:
            result_ids = {block.tool_use_id for block in tool_results}
            if message.role != "user" or not pending_tool_use_ids.issubset(result_ids):
                # 上一条 assistant 消息发起的 tool_use 没有被完整地响应,整条丢弃
                if pending_tool_use_index is not None and pending_tool_use_index < len(sanitized):
                    sanitized.pop(pending_tool_use_index)
                pending_tool_use_ids = set()
                pending_tool_use_index = None
            else:
                matched_pending_tool_results = True
                ...
        ...

    # 遍历结束时仍有未匹配的 tool_use,说明它就是消息列表的最后一条,同样要丢弃
    if pending_tool_use_ids and pending_tool_use_index is not None and pending_tool_use_index < len(sanitized):
        sanitized.pop(pending_tool_use_index)

    return sanitized
```

算法本质是一次单遍扫描的状态机:每当遇到一条带 `tool_use` 的助手消息,就记下它期望的 `tool_use_id` 集合和它在结果列表里的下标;下一条消息如果是携带了**完全匹配**这些 id 的 `tool_result` 的用户消息,就算这一对"请求-响应"完整,继续往下走;否则(不管是下一条消息角色不对,还是 `tool_result` 的 id 集合没有完全覆盖),就把之前记录的那条 `tool_use` 消息从已经收集的结果里弹出——因为一条只有请求没有响应的工具调用消息,单独留着没有意义。循环结束后如果还有没被匹配上的 `pending_tool_use_ids`(意味着它是消息列表的最后一条),同样要弹出。

同一个函数在两处被复用:`save_session_snapshot` 落盘前调用一次(防止把损坏状态写进快照),`load_session_snapshot`/`load_session_by_id` 读取后通过 `_sanitize_snapshot_payload` 再调用一次(兼容早期版本写入的、还没经过这道清洗的历史快照)。两端都做一遍,而不是只在一端做,是为了兼容"快照文件是老版本写的,读取时才第一次跑这个逻辑"的情况。

### 会话之外的另一份状态:轻量级 session memory

`services/session_storage.py` 存的是完整的、结构化的对话历史,专门给 `/resume` 用。但在压缩(compact)场景下,还有一份职责不同的轻量记录——`services/session_memory`,存的是一份人类可读的 Markdown 检查点,不是 JSON:

```python
# src/openharness/services/session_memory/__init__.py
def build_session_memory_document(
    messages: list[ConversationMessage], *, tool_metadata: dict[str, object] | None = None,
) -> str:
    state = tool_metadata.get("task_focus_state") if isinstance(tool_metadata, dict) else None
    goal = str(state.get("goal") or "").strip() if isinstance(state, dict) else ""
    ...
    lines = ["# Session Memory", ""]
    lines.extend(["## Current State", goal or "(no current goal recorded)", ""])
    ...
    lines.extend(["## Recent Conversation", *_recent_message_lines(messages), ""])
    text = "\n".join(lines).strip() + "\n"
    if len(text) > MAX_SESSION_MEMORY_CHARS:
        text = text[:MAX_SESSION_MEMORY_CHARS].rsplit("\n", 1)[0]
        text += "\n\n> Session memory was truncated to stay within budget.\n"
    return text
```

这份文档每轮对话后都会重写一次(`update_session_memory_file`),内容包括当前目标(`task_focus_state.goal`)、下一步计划、已验证的工作、活跃产物,以及最近若干条消息的一句话摘要,总长度硬顶在 12000 字符。它真正的用途出现在 `services/compact/__init__.py`——上下文压缩发生时,`_build_file_session_memory_message` 会把这份 Markdown 转换成一条注入消息塞回压缩后的上下文里,充当"跨压缩边界"的连续性锚点:

```python
# src/openharness/services/session_memory/__init__.py
def session_memory_to_compact_text(content: str) -> str:
    stripped = content.strip()
    if not stripped:
        return ""
    if estimate_tokens(stripped) > 4_000:
        stripped = stripped[:MAX_SESSION_MEMORY_CHARS].rsplit("\n", 1)[0]
    return "Session memory checkpoint from earlier in this conversation:\n" + stripped
```

也就是说,`session_storage`(JSON,完整历史,服务 `/resume`)和 `session_memory`(Markdown,精简摘要,服务上下文压缩)是两套并行存在、目的不同的持久化机制,不要把它们混为一谈。真正的自动压缩(auto-compact)逻辑本身在 `services/compact/`(约 1700 行),和引擎层的上下文管理耦合得比较深,已经超出本篇"存储层"的范围,这里只交代它读取 session memory 的这一个接口,不展开压缩触发条件和消息裁剪算法本身。

### SessionBackend:为什么不直接调用 session_storage 里的函数

`services/session_backend.py` 定义了一个 `SessionBackend` Protocol,把 `session_storage.py` 里的自由函数包了一层:

```python
# src/openharness/services/session_backend.py
class SessionBackend(Protocol):
    def get_session_dir(self, cwd: str | Path) -> Path: ...
    def save_snapshot(self, *, cwd, model, system_prompt, messages, usage, session_id=None, tool_metadata=None) -> Path: ...
    def load_latest(self, cwd: str | Path) -> dict | None: ...
    def list_snapshots(self, cwd: str | Path, limit: int = 20) -> list[dict]: ...
    def load_by_id(self, cwd: str | Path, session_id: str) -> dict | None: ...
    def export_markdown(self, *, cwd, messages) -> Path: ...


@dataclass(frozen=True)
class OpenHarnessSessionBackend:
    """Default session backend backed by ``~/.openharness/data/sessions``."""
    def save_snapshot(self, *, cwd, model, system_prompt, messages, usage, session_id=None, tool_metadata=None) -> Path:
        return session_storage.save_session_snapshot(
            cwd=cwd, model=model, system_prompt=system_prompt, messages=messages,
            usage=usage, session_id=session_id, tool_metadata=tool_metadata,
        )
    ...

DEFAULT_SESSION_BACKEND: SessionBackend = OpenHarnessSessionBackend()
```

`ui/runtime.py`、`ui/backend_host.py`、`commands/registry.py` 里凡是要保存/读取会话的地方,拿到的都是 `CommandContext.session_backend` 或 `RuntimeBundle.session_backend`,而不是直接 `import session_storage`。当前代码库里只有 `OpenHarnessSessionBackend` 这一个实现,`DEFAULT_SESSION_BACKEND` 作为默认值处处可以被覆盖注入——这是标准的依赖注入写法,为将来接入不同的会话存储方式(比如网关侧需要跨多个前端共享的分布式存储)留了一个替换点,但截至目前这版代码,只是一层薄薄的转发。

## 常见问题/易踩坑

- **`/resume` 恢复的是消息历史,不是运行环境快照**——`system_prompt` 字段虽然存了,但下一次真正提交消息时会被 `build_runtime_system_prompt` 用当前的 `CLAUDE.md`/记忆/权限设置重新生成,如果这期间项目的 `CLAUDE.md` 变了,恢复后的对话看到的是新版本而不是当时保存的那份。
- **`tool_metadata` 只持久化白名单里的 10 个 key**——如果需要让某种运行时状态"跨会话重启存活",必须显式加进 `_PERSISTED_TOOL_METADATA_KEYS`,否则悄悄丢掉,不会有任何报错提示。
- **`session_storage` 的 JSON 快照和 `session_memory` 的 Markdown 检查点是两套独立文件**,分别落在 `sessions/` 和 `session-memory/` 两个目录下,排查问题时不要把两者的内容当成同一份状态的两种表示。

## 小结

会话存储本身没有用到任何特殊技术——JSON 文件、`atomic_write_text`、哈希命名的目录,足以支撑"每轮自动落盘、随时 `/resume`"这套体验。真正决定它可靠性的是几个具体细节:白名单式持久化 `tool_metadata` 避免序列化黑洞、每轮结束(而不是退出时)就保存以最小化崩溃丢失的对话量、`sanitize_conversation_messages` 在保存和恢复两端各跑一遍来修复被中断的工具调用尾巴,以及 `SessionBackend` 这层薄抽象为未来替换存储实现留出的空间。下一篇会转向个性化系统——对话里冒出来的一句 SSH 命令、一个 conda 环境名,是怎么被悄悄提炼出来、又是怎么在下次会话里被自动用上的。
