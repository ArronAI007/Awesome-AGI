# turn_context 前奏与轮内状态机

> `run_conversation` 曾经以近 470 行的直线式设置代码开头——stdio 守护、重试计数器归零、用户消息清洗、todo/nudge 计数器水合、system prompt 恢复或重建、预压缩、`pre_llm_call` 插件 hook、外部记忆预取、崩溃可恢复持久化——然后才真正进入工具调用循环。`agent/turn_context.py` 把这一整段"只运行一次、不回头引用循环体、产出一组固定值供循环消费"的前奏，抽成了一个独立函数 `build_turn_context()` 和一个数据类 `TurnContext`。本篇逐段读这份前奏，重点是 system prompt 的恢复/重建判断和预压缩的触发时机。

## 学习目标

- 理解 `build_turn_context()`（`agent/turn_context.py:508`）按什么顺序做了哪些"每轮一次"的准备工作，以及模块文档字符串给出的抽取动机。
- 理解 `TurnContext` 数据类（`agent/turn_context.py:480`）里每个字段的含义，以及主循环怎么消费它们。
- 理解 system prompt "恢复或重建"的判断链路：`agent._cached_system_prompt is None` 这个外层判断，与 `_restore_or_build_system_prompt()`（`agent/conversation_loop.py:870`）内部四种存储状态（missing/null/empty/present）的区分。
- 理解预压缩（preflight compression）在前奏阶段的触发条件——本文只讲"什么时候触发"，压缩算法本身留给第六章。
- 理解 `pre_llm_call` 插件 hook 在前奏里的挂载点和它产出的内容如何汇入本轮的 API 请求。
- 理解"崩溃可恢复持久化"具体指的是哪一次落盘调用，以及它为什么被安排在前奏的最后一步。

## 为什么要抽成一个独立函数

`agent/turn_context.py` 的模块文档字符串直接给出了动机，不需要过度推测：

```python
# agent/turn_context.py:1-23
"""Per-turn setup for ``run_conversation`` (the turn prologue).

``run_conversation`` opened with ~470 lines of straight-line setup before the
tool-calling loop ever started: stdio guarding, runtime-main wiring, retry-counter
resets, user-message sanitization, todo/nudge-counter hydration, system-prompt
restore-or-build, session-row creation (before compression, whose DB writes
reference the row), preflight context compression, the ``pre_llm_call`` plugin
hook, external-memory prefetch, and crash-resilience persistence (last, so the
user row is written once with its final ``api_content`` sidecar).

All of that is *prologue* — it runs once per turn, has no back-references into the
loop, and produces a fixed set of values the loop then consumes. ``TurnContext``
captures those produced values; ``build_turn_context`` performs the setup work and
returns one. ``run_conversation`` is left to unpack the context and run the loop,
shrinking the orchestrator by the full prologue.

The builder still mutates ``agent`` heavily (counters, thread id, cached prompt,
session DB) exactly as the inline code did — those side effects are the point. The
``TurnContext`` it returns carries only the *locals* the loop reads back.

Behavior is identical to the original inline prologue; this is a pure
move-and-name refactor with no semantic change.
"""
```

判断"这段代码该不该被抽出去"的标准写得很清楚："只运行一次、不回头引用循环体、产出一组固定值"——这是**行为不变的纯搬移重构**（"move-and-name refactor with no semantic change"），目的是把 `run_conversation` 这个巨型函数瘦身，而不是引入一层新的抽象契约。`build_turn_context` 依然会重度修改 `agent` 实例的属性（计数器、线程 id、缓存的 system prompt、session DB 行）——这些副作用本身就是前奏要做的事；只有循环体真正要读回的值，才通过返回的 `TurnContext` 传递。

## `TurnContext`：前奏产出、循环消费的固定值集合

```python
# agent/turn_context.py:480-506
class TurnContext:
    """Values produced by the turn prologue and consumed by the turn loop."""

    # Sanitized inbound message (surrogates stripped).
    user_message: str
    # Clean message preserved for transcripts / memory queries (no nudge injection).
    original_user_message: Any
    # Working message list for this turn (loop appends to it).
    messages: List[Dict[str, Any]]
    # May be reset to None by preflight compression (new session created).
    conversation_history: Optional[List[Dict[str, Any]]]
    # Cached system prompt active for this turn (may be rebuilt by compression).
    active_system_prompt: Optional[str]
    # Task / turn identifiers.
    effective_task_id: str
    turn_id: str
    # Index of the current user turn within ``messages``.
    current_turn_user_idx: int
    # Whether the post-turn memory review should fire.
    should_review_memory: bool = False
    # Context contributed by ``pre_llm_call`` plugins (appended to user message).
    plugin_user_context: str = ""
    # External-memory prefetch result, reused across loop iterations.
    ext_prefetch_cache: str = ""
    # Turn-start preflight already proved an immediate retry ineffective.
    preflight_compression_blocked: bool = False
```

`agent/conversation_loop.py` 里 `run_conversation()` 拿到 `_ctx = build_turn_context(...)` 之后，第一件事就是把这些字段解包成局部变量（`agent/conversation_loop.py:1933-1943`），随后整个 `while` 循环只读写这些局部变量和 `agent` 属性，不再关心 `TurnContext` 本身。

## 前奏的执行顺序

按 `build_turn_context()` 函数体的真实顺序（`agent/turn_context.py:508` 起），前奏大致做了以下这些事，逐一都能在代码里找到对应位置：

1. **stdio 守护**：`install_safe_stdio()`（第一行），防止 headless/daemon 环境下 `OSError: Broken pipe` 打断整个进程。
2. **恢复被其他路径 rotate 过的会话**：`recover_rotated_compression_session(agent)`，如果发现历史被其他压缩路径 rotate 过，用恢复出的 `conversation_history` 覆盖传入值。
3. **绑定日志/写入上下文**：`set_session_context(agent.session_id)`、`set_current_write_origin(...)`，让本线程的日志记录能带上 `session_id`。
4. **恢复主 runtime**：`agent._restore_primary_runtime()`——如果上一轮激活了 fallback，这里尝试切回主 provider（第三篇详细讲这个函数）。
5. **MCP 工具刷新**：between-turns 检查是否有新连上的 MCP server，把它们并入本轮的工具快照。
6. **用户消息清洗**：`sanitize_surrogates(user_message)`，剥离非法代理字符。
7. **重试计数器与迭代预算归零**（`agent/turn_context.py:647-692`）：`_invalid_tool_retries`/`_invalid_json_retries`/`_empty_content_retries`/`_incomplete_scratchpad_retries`/`_codex_incomplete_retries`/`_thinking_prefill_retries` 等全部清零，`agent.iteration_budget = IterationBudget(agent.max_iterations)` 重新构造。
8. **组装本轮用户消息**、**todo 存储水合**（`agent._hydrate_todo_store(conversation_history)`，仅在 `_todo_store` 为空时触发）、**记忆 nudge 计数器水合**（按历史里用户轮次数回填 `_turns_since_memory`）。
9. **system prompt 恢复或重建**（下一节详细讲）。
10. **建库/建会话行**（`agent._ensure_db_session()`），必须安排在 system prompt 缓存写好**之后**——注释明确解释了原因（下一节引用）。
11. **闲置触发的压缩**（`idle_compact_after_seconds` 配置项，按墙钟空闲时间触发，与下面的预压缩是两条独立机制）。
12. **预压缩**（下一节详细讲）。
13. **`pre_llm_call` 插件 hook**（下一节详细讲）。
14. **外部记忆预取**（`agent._memory_manager.prefetch_all(_query)`，跳过"寒暄类"的 trivial prompt）。
15. **崩溃可恢复持久化**（本篇最后一节）。
16. 返回 `TurnContext`。

## system prompt：恢复还是重建

`build_turn_context()` 里对 system prompt 的判断非常简短——只在**完全没有缓存**时才调用恢复/重建函数：

```python
# agent/turn_context.py:820-824
# ── System prompt (cached per session for prefix caching) ──
if agent._cached_system_prompt is None:
    restore_or_build_system_prompt(agent, system_message, conversation_history)

active_system_prompt = agent._cached_system_prompt
```

也就是说：只要 `agent` 实例在进程内还留着上一轮缓存的 system prompt（同一个长驻 CLI 会话、同一个被网关缓存复用的 agent 实例），本轮完全跳过恢复/重建，直接复用内存里的值——这是 Anthropic prompt-cache 前缀命中率的关键前提。真正的"恢复还是重建"判断发生在 `agent._cached_system_prompt is None` 这个分支内部，也就是 `_restore_or_build_system_prompt()`（`agent/conversation_loop.py:870`）。

这个函数的文档字符串给出了一份"三态区分"：

```python
# agent/conversation_loop.py:870-896
def _restore_or_build_system_prompt(agent, system_message, conversation_history):
    """Restore the cached system prompt from the session DB or build it fresh.
    ...
    Three-way state distinction for the stored row, surfaced via logs so
    silent prefix-cache misses are visible in ``agent.log``:

      * ``missing`` — no session row yet (legitimate first turn).
      * ``null``   — row exists, ``system_prompt`` column is NULL.
        Legacy session predating system-prompt persistence, or a migration
        leftover.  Warns when ``conversation_history`` is non-empty.
      * ``empty``  — row exists, ``system_prompt`` column is the empty
        string.  Indicates a previous-turn write that ran but stored
        nothing (silent persistence bug).  Always warns.
      * ``present`` — row exists with a usable prompt → reused verbatim.
    """
```

（实际还有第四种运行时状态 `stale_runtime`，见下）流程是：

1. 如果历史非空且 `agent._session_db` 存在，读一次 `session_row.get("system_prompt")`，按上面四态之一给 `stored_state` 赋值。
2. 只有 `stored_state == "present"` **并且** `_stored_prompt_matches_runtime(agent, stored_prompt)`（校验模型/provider 等运行时身份没变）才真正复用：

```python
# agent/conversation_loop.py:919-1021（节选，含删减）
if stored_prompt and _stored_prompt_matches_runtime(agent, stored_prompt):
    ...
    # 一次性的 Bot Chat 能力纪元升级检查：命中则强制重建一次
    if _bot_stale:
        agent._cached_system_prompt = agent._build_system_prompt(system_message)
        ...
        return
    # 继续沿用上一轮同一份 system prompt，保证 Anthropic 缓存前缀完全一致
    agent._cached_system_prompt = stored_prompt
    from agent.system_prompt import restore_plugin_prompt_sections
    restore_plugin_prompt_sections(agent, stored_prompt)
    from agent.system_prompt import reconstruct_static_prefix
    reconstruct_static_prefix(agent, system_message=system_message)
    return
if stored_prompt:
    stored_state = "stale_runtime"
    logger.info("Stored system prompt for session %s has stale runtime identity; "
                "rebuilding for model=%s provider=%s.", ...)
if conversation_history and stored_state in ("null", "empty"):
    logger.warning("Stored system prompt for session %s is %s; rebuilding "
                    "from scratch this turn. Prefix cache will miss until "
                    "the rebuild persists...", agent.session_id, stored_state)
# First turn of a new session (or recovering from a broken stored
# prompt) — build from scratch.
agent._cached_system_prompt = agent._build_system_prompt(system_message)
...
if agent._session_db:
    agent._session_db.update_system_prompt(agent.session_id, agent._cached_system_prompt)
```

也就是说，只要满足以下**任意一个**条件，就会走"重建"分支：会话行不存在（真正的首轮）、存储值是 `NULL`/空字符串（历史写入失败的遗留问题）、或者存储的 prompt 与当前运行时身份不匹配（`stale_runtime`——比如 `/model` 切换了模型/provider）。重建之后立刻把新 prompt 写回 `session_db`，这样下一轮如果这个 agent 实例被网关重新构造（gateway 每轮构造一个新 `AIAgent`，靠这次 DB 往返恢复缓存），依然能命中 `present` 分支，避免每轮都重建导致 prompt-cache 前缀持续 miss。

Bot Chat 场景还有一条特殊的"能力纪元"重建路径：当 skills/toolsets/MCP/SOUL/角色名单等能力面发生变化时，即使 `stored_prompt` 存在且运行时身份匹配，也会因为 `stored_prompt_capability_stale()` 命中而强制重建一次——这是"存在但过期"这第五种状态的实际处理方式，只是它没有被算进上面文档字符串列出的四态里。

## 预压缩：只讲触发时机

`build_turn_context()` 里的预压缩分成两段独立逻辑：

**闲置触发的压缩**（`agent/turn_context.py:872` 附近），仅在 `compression_idle_compact_after_seconds` 配置且距离上次活动的墙钟时间超过阈值时触发一次，与下面的"预压缩"是两套独立开关。

**真正的预压缩（preflight compression）**门槛用一个更轻量的预检查前置：

```python
# agent/turn_context.py:951-968（节选）
# ── Preflight context compression ──
# Gate the (expensive) full token estimate behind a cheap pre-check.
if (
    agent.compression_enabled
    and not _review_fork_first_request_pending(agent)
    and _should_run_preflight_estimate(
        messages,
        agent.context_compressor.protect_first_n,
        agent.context_compressor.protect_last_n,
        agent.context_compressor.threshold_tokens,
    )
):
    _preflight_tokens = _preflight_request_tokens(agent, messages, active_system_prompt or "")
    ...
```

也就是说：只有在压缩功能开启、且当前不是"后台复审 fork 的第一次请求"、且 `_should_run_preflight_estimate()` 这个便宜的粗估（消息数量/受保护窗口）先通过之后，才会真正调用较昂贵的 `_preflight_request_tokens()` 去精确估算本轮请求的 token 数——这是"用一个便宜的门槛守住一个昂贵的估算"的常见模式。估算出的 token 数还会经过 `should_defer_preflight_to_real_usage()`、`get_active_compression_failure_cooldown()` 等多重门槛（冷却期、上一次真实 provider 返回的 prompt tokens）才最终决定是否真的触发压缩。压缩算法本身（`agent._compress_context`）留给第六章展开，本篇只需要记住：**预压缩的触发点在前奏阶段，早于第一次模型调用**，一旦触发会重写 `messages`/`conversation_history` 并重新锚定 `current_turn_user_idx`。

## `pre_llm_call` 插件 hook

```python
# agent/turn_context.py:1325-1341（节选）
# Plugin hook: pre_llm_call (context injected into user message, not system prompt).
plugin_user_context = ""
from hermes_cli.lifecycle import invoke_hook as _invoke_hook
_pre_results = _invoke_hook(
    "pre_llm_call",
    session_id=agent.session_id,
    task_id=effective_task_id,
    turn_id=turn_id,
    user_message=original_user_message,
    conversation_history=list(messages),
    is_first_turn=(not bool(conversation_history)),
    model=agent.model,
    platform=getattr(agent, "platform", None) or "",
    parent_session_id=getattr(agent, "_parent_session_id", None) or "",
    sender_id=getattr(agent, "_user_id", None) or "",
)
```

每个插件返回的 `context` 片段会被拼接成 `plugin_user_context`，过大的输出会通过 `spill_if_oversized()` 溢写到磁盘（防止一个失控插件把每一轮的 prompt 都撑爆）。这份内容**不会**进入 system prompt（那样会破坏 prompt-cache 前缀），而是和外部记忆预取的结果一起，只注入本轮用户消息的 **API 发送副本**（`compose_user_api_content()`），存储的干净内容保持不变——这正是下面"崩溃可恢复持久化"要落盘的 `api_content` sidecar 存在的原因。插件系统本身（`hermes_cli.plugins`/`invoke_hook` 的实现、`VALID_HOOKS` 契约）留给第八章展开。

## 外部记忆预取与崩溃可恢复持久化

外部记忆预取只在非"寒暄类"输入上触发，并把结果缓存进 `ext_prefetch_cache`，供循环内重复使用（避免每次重试都重新查询记忆库）：

```python
# agent/turn_context.py:1434-1445（节选）
ext_prefetch_cache = ""
if agent._memory_manager:
    _query = original_user_message if isinstance(original_user_message, str) else ""
    if not is_trivial_prompt(_query):
        ext_prefetch_cache = agent._memory_manager.prefetch_all(_query) or ""
```

前奏的最后一步是"崩溃可恢复持久化"——把这一轮刚追加的用户消息（连同上面组装出的 `api_content` sidecar）提前写入 `session_db`，赶在第一次模型调用之前：

```python
# agent/turn_context.py:1514-1530（节选）
# Crash-resilience: persist the inbound user turn before the first LLM
# call. Runs after preflight compression (which rewrites history anyway)
# and after prefetch/pre_llm_call, so the user row is written once with
# its final api_content instead of being re-written mid-turn.
def _ensure_and_persist() -> None:
    agent._ensure_db_session()
    agent._persist_session(messages, conversation_history)

if persist_lock is None:
    _ensure_and_persist()
else:
    with persist_lock:
        _ensure_and_persist()
```

安排在前奏最后一步，而不是更早，是为了避免"写两次"：如果放在预压缩或 `pre_llm_call` hook 之前，压缩重写历史、hook 组装 `api_content` 之后还要再补一次写；放在最后，一次落盘就带着这一轮用户消息最终确定的字节内容，即便进程在第一次模型调用中途崩溃，重启后恢复出的历史也是这一轮真正发出去的样子。

## 关键代码解读

- `build_turn_context()`（`agent/turn_context.py:508`）：前奏的主函数，按本文列出的 16 步顺序执行，返回 `TurnContext`。
- `TurnContext`（`agent/turn_context.py:480`）：循环体读取的固定字段集合，字段本身的注释就说明了各自的产出来源。
- `_restore_or_build_system_prompt()`（`agent/conversation_loop.py:870`）：`missing`/`null`/`empty`/`present`/`stale_runtime` 五态判断，只有 `present` 且运行时身份匹配才真正复用缓存。
- `_should_run_preflight_estimate()` + `_preflight_request_tokens()`：预压缩的"便宜门槛守住昂贵估算"两段式判断。
- `_ensure_and_persist()`（前奏内部闭包函数）：崩溃可恢复持久化的实际落盘调用，安排在前奏最后一步。

## 小结与思考题

`build_turn_context()` 是一次目的明确的"纯搬移重构"：把 `run_conversation` 里只运行一次、不回头引用循环体的准备工作抽成独立函数，副作用（修改 `agent` 属性）保持不变，只把循环真正要读的值收进 `TurnContext`。system prompt 的恢复/重建判断是这份前奏里最精细的一段逻辑，靠"运行时身份匹配 + 存储状态四态区分"来最大化 prompt-cache 命中率；预压缩靠"便宜估算门槛 + 冷却期"来避免每轮都跑一次昂贵的 token 精算；`pre_llm_call` hook 的产出严格限定只注入 API 发送副本而不进入 system prompt 或持久化内容，是维持 prompt-cache 前缀稳定性的又一处细节。

思考题：

1. 为什么 system prompt 的重建判断要同时检查"运行时身份是否匹配"而不仅仅是"存储值是否存在"？如果只检查存在性，`/model` 切换模型后会出现什么问题？
2. 崩溃可恢复持久化被安排在预压缩、`pre_llm_call` hook 之后，而不是在用户消息刚追加进 `messages` 时立刻执行——这个顺序权衡了"多写一次的开销"和"崩溃恢复窗口的长短"，你认为还有没有更早、开销更小的可行落盘点？
3. `pre_llm_call` hook 的输出只进入 API 发送副本（`api_content`），不进入存储内容——如果某个插件的输出本身应该被记忆/检索到，这个设计会带来什么限制？
