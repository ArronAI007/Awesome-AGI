# 中断与轮内改口 Steering

> 用户在 agent 正在流式输出或执行工具时又发来一条消息,系统该怎么处理？hermes-agent 提供了三种不同粒度的机制：`interrupt()`/`hard_interrupt()` 是硬中断,直接砍掉当前请求并清空待处理状态;`steer()` 是"轻量插话",把文字注入到当前正在执行的工具批次结束后的结果里,不打断任何正在进行的操作;`redirect()` 介于两者之间——取消当前的模型请求但保留已完成的消息和部分可见输出,把用户的纠正作为新一轮追加内容,让同一个逻辑轮次"改口重来"。本篇逐一拆解这三种机制的触发路径、状态字段与适用场景。

## 学习目标

- 理解 `agent/interrupt_compat.py` 这个兼容层解决的具体问题:新旧两代"停止"接口如何共存。
- 理解 `hard_interrupt()`（硬中断)的完整传播路径:从跨线程信号、到子代理递归中断、到 Codex app-server 的私有中断协议。
- 理解 `steer()`（软插话)和 `redirect()`（轮内改口)的区别:前者不打断任何操作只是排队等待注入点,后者会主动取消模型请求但保留已产生的内容。
- 理解 `_drain_pending_redirect()`/`_drain_pending_steer()` 在主循环里的消费位置,以及 `_apply_active_turn_redirect()` 如何把"被打断的部分回复"安全地转换成可重放的消息。
- 能用真实测试用例(`tests/agent/test_interrupt_compat.py`)佐证上述行为,而不是仅凭源码推测。

## `agent/interrupt_compat.py`：新旧接口的兼容层

这个模块只有 64 行,docstring 很直白：`"""Compatibility helper for explicit agent stop producers."""`。它要解决的问题是：`AIAgent` 现在暴露的是 `hard_interrupt(message=None, *, tool_reason=None)`,但历史上（以及一些第三方/测试用的 agent 替身)只实现了旧签名 `interrupt(message=None)`。核心函数 `request_hard_interrupt()` 做特性探测,优先用新接口,退化到旧接口：

```python
# agent/interrupt_compat.py:25-64（节选）
def request_hard_interrupt(
    agent: Any, message: str | None = None, *, tool_reason: str | None = None,
) -> bool:
    """Request an explicit stop, falling back to the legacy interrupt ABI.

    New agents expose ``hard_interrupt(message=None)``. Third-party agents and
    old test doubles may only expose ``interrupt(message=None)``; keep those
    usable without sending newer keyword arguments they do not know.

    ``message`` is diagnostic/control-plane text. ``tool_reason`` is a trusted,
    fixed category that may be exposed in model-visible tool cancellation
    output. It is only forwarded when the modern callable explicitly supports
    that channel.
    """
    try:
        inspect.getattr_static(agent, "hard_interrupt")
    except AttributeError:
        interrupt = None
    else:
        interrupt = getattr(agent, "hard_interrupt", None)
    if not callable(interrupt):
        interrupt = getattr(agent, "interrupt", None)
    if not callable(interrupt):
        return False
    kwargs = {}
    if tool_reason is not None and _accepts_keyword(interrupt, "tool_reason"):
        kwargs["tool_reason"] = tool_reason
    if message is None:
        interrupt(**kwargs)
    else:
        interrupt(message, **kwargs)
    return True
```

两个细节值得注意：一是用 `inspect.getattr_static()` 而不是普通 `getattr()` 做存在性探测——注释解释这是为了不把一个动态 `__getattr__` 代理(尤其是未 spec 的 `MagicMock`,它对任何属性访问都会返回一个可调用的 Mock)误判成"真的实现了新 ABI"。真实测试 `test_dynamic_proxy_does_not_fabricate_hard_interrupt_support`(`tests/agent/test_interrupt_compat.py:70-76`)验证了这一点：对一个裸 `MagicMock()` 调用 `request_hard_interrupt`,它会被路由到 `interrupt()` 而不是凭空"发现"一个 `hard_interrupt()`。二是 `tool_reason` 这个参数只有在目标可调用对象**显式**支持它时才会被传入(通过 `inspect.signature` 检查形参名或 `**kwargs`),这是因为 `tool_reason` 是"可能出现在模型可见的工具取消输出里的、经过审查的固定分类文案",而 `message` 是任意的诊断/控制面文本——旧接口不应该意外把 `tool_reason` 当成位置参数塞进 `message` 里。

`request_hard_interrupt()` 被 `tools/delegate_tool.py` 用来响应 TUI 上"中断某个子代理"的操作(测试 `test_tui_subagent_interrupt_is_an_explicit_hard_stop` 验证了这一点),也被 `AIAgent.interrupt()` 自身在向子代理传播中断时调用（见下文)。

## 硬中断：`interrupt()` / `hard_interrupt()`

`AIAgent.interrupt()`(`run_agent.py:3281`)是真正完整实现中断逻辑的方法,`hard_interrupt()` 只是它的一个语义化封装：

```python
# run_agent.py:3443-3462
def hard_interrupt(
    self, message: Optional[str] = None, *, tool_reason: Optional[str] = None,
) -> None:
    """Request an explicit stop while preserving ``interrupt()`` ABI.

    Frontends can feature-detect this method and fall back to the legacy
    ``interrupt()`` signature for synthetic or third-party agents.
    """
    # Deliberately bypass dynamic dispatch: subclasses written against the
    # legacy interrupt(message=None) ABI may override interrupt without the
    # newer keyword-only hard_cancel argument.
    AIAgent.interrupt(self, message, hard_cancel=True, tool_reason=tool_reason)
```

`hard_interrupt()` 显式调用 `AIAgent.interrupt`(类名限定,不是 `self.interrupt`)——这是为了绕开可能覆写了 `interrupt()` 的子类,防止一个只认识旧签名的子类实现悄悄吞掉 `hard_cancel=True` 这个关键参数。

`interrupt(message=None, *, hard_cancel=False, tool_reason=None)` 内部按 `hard_cancel` 是否为真,决定这次中断的"工具取消理由"文案,并设置几个跨线程状态字段：

```python
# run_agent.py:3349-3364（节选）
_redirect_lock = getattr(self, "_pending_redirect_lock", None)
if _redirect_lock is not None:
    with _redirect_lock:
        self._interrupt_requested = True
        self._interrupt_message = message
        self._tool_interrupt_reason = tool_interrupt_reason
        if hard_cancel:
            _admit_hard_cancel()
        self._pending_redirect = None
```

注意最后一行 `self._pending_redirect = None`——**硬中断会清空任何尚未消费的 pending redirect**,因为下文要讲的"轮内改口"是"这个轮次修正后继续",而硬中断意味着"这个轮次不再继续了",两者语义冲突,后者优先。随后 `interrupt()` 依次做四件事:

1. **对 Codex app-server 特判**——如果 `api_mode == "codex_app_server"`,不使用 Hermes 自己的线程信号,而是调用 Codex session 的私有 `request_interrupt()`(`run_agent.py:3366-3378`),因为该模式下整个轮次由 Codex 子进程自己驱动,Hermes 侧的线程标志位对它不起作用。
2. **打断正在进行的内联请求**——`agent._active_request_abort("interrupt_abort")`,用于"cron 轮次在对话线程本身发起请求"这种不走标准 worker 线程的场景。
3. **向工具层广播中断信号**——`_set_interrupt(True, tid, reason=...)`,不仅作用于主执行线程(`self._execution_thread_id`),还会遍历所有正在跑并发工具的 worker 线程 id(`_tool_worker_threads`),确保一个正在执行网络 I/O 的终端命令也能感知到中断,而不必等到自己的超时。
4. **递归传播给所有子代理**(`self._active_children`)——`hard_cancel` 为真时用 `request_hard_interrupt()` 传播(走上面讲的兼容层),否则用普通 `child.interrupt(message)`。

`clear_interrupt(*, preserve_redirect=False)`(`run_agent.py:3464`)负责收尾清理,`preserve_redirect=True` 是一个专供对话循环内部使用的特殊模式——"conversation loop 有意取消一次模型请求、为的是用同一个逻辑轮次重建请求"时使用,不清空 `_pending_redirect`;公开的硬停止路径永远用默认值,清空一切,包括顺带丢弃任何 pending 的 `/steer`(注释解释："A hard interrupt supersedes any pending /steer — the steer was meant for the agent's next tool-call iteration, which will no longer happen.")。

## 软插话：`steer()`

```python
# run_agent.py:3521-3538
def steer(self, text: str) -> bool:
    """
    Inject a user message into the next tool result without interrupting.

    Unlike interrupt(), this does NOT stop the current tool call. The
    text is stashed and the agent loop appends it to the LAST tool
    result's content once the current tool batch finishes. The model
    sees the steer as part of the tool output on its next iteration.

    Thread-safe: callable from gateway/CLI/TUI threads. Multiple calls
    before the drain point concatenate with newlines.
    """
```

`steer()` 只做一件事：把文本追加到 `agent._pending_steer`(加锁,多次调用用换行拼接),完全不碰 `_interrupt_requested`、不发任何中断信号。它是最"温和"的机制——当前正在执行的工具调用(哪怕是个耗时很久的终端命令)会正常跑完,不会被提前打断。

消费点在主循环里有两处,分别对应"steer 到达时机"的两种情况。第一处是**每次进入新一轮模型调用之前**的"pre-API drain":

```python
# agent/conversation_loop.py:2115-2151（节选）
# ── Pre-API-call /steer drain ──────────────────────────────────
# If a /steer arrived during the previous API call (while the model
# was thinking), drain it now — before we build api_messages — so
# the model sees the steer text on THIS iteration.  Without this,
# steers sent during an API call only land after the NEXT tool batch,
# which may never come if the model returns a final response.
_pre_api_steer = agent._drain_pending_steer()
if _pre_api_steer:
    for _si in range(len(messages) - 1, -1, -1):
        _sm = messages[_si]
        if isinstance(_sm, dict) and _sm.get("role") == "tool":
            from agent.prompt_builder import format_steer_marker
            marker = format_steer_marker(_pre_api_steer)
            existing = _sm.get("content", "")
            _sm["content"] = existing + marker if isinstance(existing, str) else ...
            _injected = True
            break
    if not _injected:
        # No tool message to inject into — put it back so
        # the post-tool-execution drain picks it up later.
        ...
```

这段注释解释了为什么需要"提前 drain"：如果一个 `/steer` 是在模型正在思考(还没触发工具调用)时到达的,只在"工具批次结束后"才消费它是不够的——因为模型这一次也许根本不会再调用工具、直接给出最终回复,那样 pending 的 steer 就永远等不到注入点。所以循环体在**每次准备发起新一轮模型请求之前**都会先尝试 drain 一次,反向扫描 `messages` 找到最近的一条 `tool` 角色消息,把 steer 文本追加进它的 `content`(用 `format_steer_marker()` 包装,让模型能区分"这是工具的真实输出"还是"用户中途插的话")。如果连一条 tool 消息都还不存在(比如这是第一次迭代,模型还没调用过任何工具),就把文本放回 `_pending_steer`,交给后面工具批次结束后的另一处 drain 逻辑。

## 轮内改口：`redirect()`

`redirect()` 是三者中语义最丰富的一个,docstring 直接给出了它在三种子场景下的不同行为：

```python
# run_agent.py:3557-3570
def redirect(self, text: str) -> bool:
    """Redirect the active turn without converting it into a new task.

    During a normal Hermes model request this cancels only that request;
    the conversation loop retains completed messages/tool results, records
    the displayed partial reasoning as plain assistant context, appends the
    correction as a real user message, and retries. During tool execution
    it degrades to ``steer()`` so the tool can finish at a safe boundary.
    Codex app-server has a native ``turn/steer`` operation and uses it
    directly instead of cancelling.

    Returns ``False`` when there is no live turn or the text is empty, so
    surfaces can fall back to their existing next-turn queue.
    """
```

三条路径在源码里体现为三个连续的分支：

1. **Codex app-server**:直接调用 `_codex_session.request_steer(cleaned)`(`run_agent.py:3577-3592`),因为 Codex 有自己原生的"轮内插话"协议,不需要 Hermes 侧模拟。
2. **正在执行工具**:`if getattr(self, "_executing_tools", False): return self.steer(cleaned)`(`run_agent.py:3597-3598`)——注释写得很明确："Never kill a tool merely to deliver conversational guidance."`redirect()` 在工具执行期间会**自动降级为 `steer()`**,这是理解"redirect 和 steer 到底谁包含谁"的关键：redirect 不是 steer 的对立面,而是"在模型请求阶段表现为主动取消 + 重建,在工具执行阶段表现得和 steer 完全一样"。
3. **模型请求正在进行中**(`_model_request_active.is_set()`):把文本存进 `_pending_redirect`,置位 `_interrupt_requested = True`,并调用 `_abort_active_request("redirect_abort")` 只中断这一次模型请求(不广播给工具 worker 或子代理——`redirect()` 注释明确写着"Do not fan out to tool workers or child agents as interrupt() does",`run_agent.py:3633-3634`)。

被取消的模型请求留下的"部分可见回复"由 `_apply_active_turn_redirect()`(`agent/conversation_loop.py:378`)处理成安全可重放的消息。这个函数本身是一段值得精读的"血泪教训"代码：

```python
# agent/conversation_loop.py:378-414（节选）
def _apply_active_turn_redirect(agent, messages, text) -> None:
    """Append a provider-safe checkpoint and correction to the live turn.

    ...
    INVARIANT — raw chain-of-thought must never be serialized into replayable
    message content. Streamed reasoning is display-only state: it may be shown
    live, but it does not re-enter the transcript as assistant (or user) text.
    An assistant turn whose content inlines its own chain-of-thought reads to
    Anthropic's output classifier as reasoning-injection/prefill jailbreak,
    and because the poisoned checkpoint is persisted and replayed on every
    subsequent call, the session dies permanently with deterministic
    "Provider returned an empty response" storms that no retry, nudge, or
    empty-recovery branch can escape (July 2026: four sessions bricked this
    way; every reasoning-free checkpoint that week was untouched...).
    """
```

它只把**可见的文本**(`agent._strip_think_blocks(...)`剥掉思维链之后剩下的部分)拼进一个 "`[This response was interrupted by a user correction.]`" 的 scaffold,附着在**用户纠正消息的 `api_content` sidecar** 上,而不是写进被打断的那条 assistant 消息本身——注释里记录了一次真实事故：把打断说明写进 assistant 行的 `content`,会让模型把这段 scaffold 当成"自己上一次真实说过的话"并模仿它、自我复制出幽灵消息行,连续四个会话因此被永久性"变砖"（每次请求都触发 provider 返回空响应的死循环)。这段代码是"崩溃恢复必须对 provider 的重放语义极度谨慎"的一个具体范例。

`_apply_active_turn_redirect()` 在主循环里的消费点位于 while 循环最开头：

```python
# agent/conversation_loop.py:2029-2038
while (api_call_count < agent.max_iterations and agent.iteration_budget.remaining > 0) or agent._budget_grace_call:
    _redirect_text = agent._drain_pending_redirect()
    if _redirect_text:
        _apply_active_turn_redirect(agent, messages, _redirect_text)
        if isinstance(original_user_message, str):
            original_user_message = (
                f"{original_user_message}\n\nUser correction during the turn: {_redirect_text}"
            )
        agent._persist_session(messages, conversation_history)
```

也就是说,`redirect()` 触发的"取消当前模型请求"和"用修正文本重建请求"这两件事,在时间上是**异步解耦**的：`redirect()` 本身只负责设置状态并中断请求,真正把纠正文本转换成消息、追加进 `messages`、重新持久化,发生在循环下一次迭代开始时的 `_drain_pending_redirect()` 调用点——这也是为什么 `interrupt()` 和 `redirect()` 共用同一把 `_pending_redirect_lock`(源码注释："A hard stop and redirect share one lock so /stop cannot race with an accepted correction and accidentally turn itself into a retry.")。

## 硬中断与软改口的适用场景对比

| | `interrupt()`/`hard_interrupt()` | `redirect()` | `steer()` |
|---|---|---|---|
| 是否停止当前操作 | 是——广播给模型请求、工具 worker、子代理 | 仅停止模型请求;工具执行期间自动降级为 `steer()` | 否,从不打断任何操作 |
| 语义 | "这个轮次到此为止" | "这个轮次改口重来" | "在下一个安全节点插一句话" |
| 状态字段 | `_interrupt_requested`/`_hard_interrupt_requested`/清空 `_pending_redirect`/`_pending_steer` | `_pending_redirect` + `_interrupt_requested`(仅中断模型请求) | `_pending_steer` |
| 子代理传播 | 是(递归 `request_hard_interrupt`/`interrupt`) | 否 | 否 |
| Codex app-server 下的行为 | 调用 `_codex_session.request_interrupt()` | 调用 `_codex_session.request_steer()` | 由 Codex 原生处理(Hermes 侧不接管) |

一句话总结适用场景：用户明确要求"停下"（Ctrl+C、点了停止按钮)用硬中断;用户觉得模型理解错了、想让它"改个方向重新说"用 `redirect()`;用户只是想在模型正在执行一系列工具调用时顺嘴补充一点信息、不希望打断正在进行的操作,用 `steer()`。三者共享同一把锁,但清空/保留彼此状态的规则(硬中断清空 pending redirect 和 steer;redirect 和 steer 互不清空对方)体现了"停止优先级最高,改口和插话可以共存"的设计取向。

## 关键代码解读

`tests/agent/test_interrupt_compat.py` 提供了对 `request_hard_interrupt()` 行为最精确的第一手验证,尤其是这个用例展示了硬中断如何在真实的 `AIAgent` 子类上正确地设置一整套状态,而不经过被覆写的旧版 `interrupt()`：

```python
# tests/agent/test_interrupt_compat.py:79-107（节选）
def test_inherited_hard_interrupt_bypasses_legacy_subclass_override() -> None:
    from run_agent import AIAgent

    class LegacySubclass(AIAgent):
        def interrupt(self, message: str | None = None) -> None:  # type: ignore[override]
            self.legacy_calls.append(message)

    agent = LegacySubclass()
    assert request_hard_interrupt(agent, "stop now") is True

    assert agent.legacy_calls == []
    assert agent._hard_interrupt_requested.is_set()
    assert agent._interrupt_requested is True
    assert agent._interrupt_message == "stop now"
```

`agent.legacy_calls == []` 证明了 `hard_interrupt()` 确实绕过了子类覆写的 `interrupt()`,直接命中 `AIAgent.interrupt` 本体、正确设置了 `_hard_interrupt_requested`/`_interrupt_requested`/`_interrupt_message` 这几个跨线程可见的状态字段——这是"显式类名调用绕开动态派发"这个技巧在真实场景下确实生效的证据,而不只是源码注释里的一句自我声明。

## 小结与思考题

hermes-agent 用三个层次的强度处理"轮内用户插话"：`interrupt()`/`hard_interrupt()` 是硬停止,跨线程广播、递归传播给子代理、清空一切待处理状态;`redirect()` 是"改口重来",只取消模型请求本身,把已产生的可见内容转换成安全的重放消息,在工具执行期间自动降级为更温和的 `steer()`;`steer()` 是最温和的插话,只等待一个安全的注入点(下一次模型调用前,或者当前工具批次结束后),从不主动打断任何操作。三者共享 `_pending_redirect_lock`/`_pending_steer_lock` 保证互斥安全,`agent/interrupt_compat.py` 这个薄兼容层则保证新旧两代"停止" ABI 可以在同一个代码库里共存。这与 PI 课程里"对话循环与消息状态机"一文讨论的 `steer()`/`followUp()`/`inject()` 三分法(按"放进哪个队列"和"是否唤醒 driver"两个维度区分)是同一个问题的不同解法——hermes 没有显式的 inbox 队列和 driver 唤醒状态机,而是用几个跨线程共享的 pending 变量 + 锁 + 主循环开头的 drain 调用点,达到类似的效果。

思考题：

1. `redirect()` 在"正在执行工具"时会自动降级为 `steer()`,但两者往消息里注入文本的方式并不完全一样(`redirect` 走 `_pending_redirect` → `_apply_active_turn_redirect`,`steer` 走 `_pending_steer` → 追加进最近一条 tool 消息)。如果 `redirect()` 触发降级时,恰好也已经有一条 `_pending_steer` 在排队,两条文本最终会以什么顺序、什么形式合并进 `messages`？
2. `_apply_active_turn_redirect()` 的注释记录了"把打断说明写进 assistant 行导致会话变砖"的真实事故。如果你要新增一种"轮内插话"变体,在设计它往消息列表里写什么内容时,应该提前检查哪些不变量,才能避免重蹈这个覆辙？
3. 硬中断清空 `_pending_redirect` 和 `_pending_steer`,但两个"插话"机制(`redirect`/`steer`)彼此并不清空对方。这种"停止具有最高优先级,插话之间互不干扰"的设计,在什么场景下可能让用户感到意外(比如连续发了一条 redirect 又发了一条 steer)？
