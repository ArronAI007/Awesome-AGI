# QueryEngine 总览：流式工具调用循环

> `oh` 的整个 Agent 引擎最终收敛到 `src/openharness/engine/query.py` 里一个不起眼的异步生成器函数——`run_query()`。`QueryEngine`（`engine/query_engine.py`）看起来像"引擎"，但它其实只是一层薄壳：持有对话历史、组装 `QueryContext`、把控制权交给 `run_query()`，再把流式事件转发给上层 UI。真正的"模型 → 工具 → 模型"循环，连同重试可见性、自动压缩触发、成本累加，全部装在这一个 `while` 循环里。

## 学习目标

- 理解 `QueryEngine` 与 `run_query()` 的分工边界：为什么"引擎"是壳，循环的心脏在另一个文件里。
- 通读 `run_query()` 的真实实现，搞清楚一次用户输入是如何被组装成请求（system prompt + 历史消息 + 工具 schema）、如何消费流式返回、工具调用如何被识别并派发执行、结果又是如何写回消息历史触发下一轮模型调用的。
- 弄清楚循环的四种终止路径：模型不再要求工具、模型返回空消息、不可恢复的 API 错误、达到 `max_turns` 上限。
- 理解 retry/backoff 逻辑实际发生在哪一层（不是 `run_query()` 本身），以及它是如何通过 `ApiRetryEvent` 把重试过程"透传"给 UI 的。
- 看懂单工具顺序执行与多工具并发执行两条路径为什么要分开写，以及 `asyncio.gather(..., return_exceptions=True)` 背后要规避的真实协议约束。

## 背景与设计动机

一个最朴素的 Agent 循环写法是：把用户消息、历史、工具 schema 拼给模型，模型如果要调工具就执行、把结果拼回去，再发一次模型，直到模型不再要求工具为止。`oh` 的 `run_query()` 骨架确实就是这个朴素循环，但真实系统要在这个骨架上叠加好几件事，且不能让它们互相绞在一起：

- **流式响应要能实时展示**，同时还要能在流式过程中识别出"这次请求失败了，需要重试"——重试本身也要能流式地告知用户"正在重试第几次、还要等几秒"。
- **上下文会不可避免地变长**，在每次真正发起模型请求之前，必须先检查一次"是否已经接近上下文窗口上限"，需要时先做自动压缩，压缩失败或压缩后仍然超限时还要有兜底路径。
- **多个工具调用可能并发触发**，但工具执行结果必须一一对应地喂回去——如果某个工具执行抛异常，不能让整批工具调用因为一个协程失败而被取消，导致模型侧出现"有 `tool_use` 没有对应 `tool_result`"这种会被 Provider 直接拒绝请求的破损状态。
- **循环必须有硬性终止条件**，否则一个死循环的模型（不断要求同一个工具）会无限跑下去。

`oh` 的做法是把这些关注点在 `run_query()` 内部按顺序线性铺开，而不是拆成好几层嵌套的状态机（这一点与 DeepSeek-Harness 的 `kick → turn → step` 三层设计形成有趣的对比，后面会展开）。整个函数只有一层 `while`，但每一轮循环内部依次做压缩检查、图片预处理、模型请求、工具执行——顺序本身就是设计。

## 核心机制详解

### QueryEngine 是壳，run_query 是心脏

```python
# src/openharness/engine/query_engine.py
async def submit_message(self, prompt: str | ConversationMessage) -> AsyncIterator[StreamEvent]:
    """Append a user message and execute the query loop."""
    user_message = (
        prompt
        if isinstance(prompt, ConversationMessage)
        else ConversationMessage.from_user_text(prompt)
    )
    ...
    self._messages = sanitize_conversation_messages(self._messages)
    self._messages.append(user_message)
    ...
    context = QueryContext(
        api_client=self._api_client,
        tool_registry=self._tool_registry,
        permission_checker=self._permission_checker,
        cwd=self._cwd,
        model=self._model,
        system_prompt=self._system_prompt,
        max_tokens=self._max_tokens,
        effort=self._effort,
        context_window_tokens=self._context_window_tokens,
        auto_compact_threshold_tokens=self._auto_compact_threshold_tokens,
        max_turns=self._max_turns,
        permission_prompt=self._permission_prompt,
        ask_user_prompt=self._ask_user_prompt,
        hook_executor=self._hook_executor,
        tool_metadata=self._tool_metadata,
    )
    query_messages = list(self._messages)
    ...
    try:
        async for event, usage in run_query(context, query_messages):
            if isinstance(event, AssistantTurnComplete):
                self._messages = list(query_messages)
            if usage is not None:
                self._cost_tracker.add(usage)
            yield event
    finally:
        await self._update_session_memory()
        await self._extract_durable_memories()
        self._schedule_auto_dream()
```

`QueryEngine` 自己不做任何"要不要继续调模型"的判断。它做的事情很朴素：把用户输入规范化并追加到历史（先调用 `sanitize_conversation_messages()`，第三篇会细讲它为什么必须在每次提交前跑一遍）；把当前会话状态打包成一个不可变的 `QueryContext`；把消息列表的**一份拷贝**（`query_messages = list(self._messages)`）连同 context 一起交给 `run_query()`；然后原样转发 `run_query()` 产出的每一个 `StreamEvent`，只在看到 `AssistantTurnComplete` 事件时才把 `query_messages`（`run_query()` 会原地修改这份列表）同步回 `self._messages`。`finally` 块里挂的会话记忆持久化、durable memory 抽取、auto-dream 调度都是第六章的话题，这里只需要知道：无论循环正常结束还是异常退出，这些收尾动作都会执行。

这个分工意味着：`QueryEngine` 负责"一个会话跨多次用户输入的生命周期"，`run_query()` 负责"一次用户输入触发的、可能包含多轮工具调用的完整循环"。理解这一点后再去读 `run_query()`，就不会被它 1000 多行的文件规模吓到——真正的循环逻辑其实很短，篇幅大部分花在工具调用产生的"记忆carry-over"辅助函数上（`_record_tool_carryover` 等，这部分留给第三篇讲上下文管理）。

### run_query()：一轮 while 里的完整闭环

```python
# src/openharness/engine/query.py（节选，保留循环骨架）
turn_count = 0
while context.max_turns is None or turn_count < context.max_turns:
    turn_count += 1
    ...
    # --- auto-compact check before calling the model ---------------
    async for event, usage in _stream_compaction(trigger="auto"):
        yield event, usage
    compacted_messages, was_compacted = last_compaction_result
    if compacted_messages is not messages:
        messages[:] = compacted_messages
    # ---------------------------------------------------------------

    # --- image preprocessing: convert ImageBlocks to text for non-vision models ---
    async for event in _preprocess_images_in_messages(messages, context):
        yield event, None
    # -----------------------------------------------------------------------------

    final_message: ConversationMessage | None = None
    usage = UsageSnapshot()

    try:
        async for event in context.api_client.stream_message(
            ApiMessageRequest(
                model=context.model,
                messages=messages,
                system_prompt=context.system_prompt,
                max_tokens=effective_max_tokens,
                tools=context.tool_registry.to_api_schema(),
                effort=context.effort,
            )
        ):
            if isinstance(event, ApiTextDeltaEvent):
                yield AssistantTextDelta(text=event.text), None
                continue
            if isinstance(event, ApiRetryEvent):
                yield StatusEvent(message=(...)), None
                continue
            if isinstance(event, ApiMessageCompleteEvent):
                final_message = event.message
                usage = event.usage
    except Exception as exc:
        ...
```

这段代码把请求的组装方式暴露得很直白：`ApiMessageRequest` 就是"system prompt + 历史消息 + 工具 schema"的完整打包——`messages` 是当前这轮循环维护的、被原地修改（`messages[:]= ...`、`messages.append(...)`）的消息列表；`context.tool_registry.to_api_schema()` 现取现算，意味着工具集合可以在会话过程中动态变化（比如 MCP server 连接/断开）而不需要重建 context；`system_prompt` 每轮都会重新传入，为后续（比如动态注入运行时信息）留了空间。

`while` 循环体本身的执行顺序就是设计意图的直接体现：**先检查是否要压缩，再做图片预处理，最后才真正发起模型请求**。压缩检查（`_stream_compaction(trigger="auto")`）内部调用的是 `services/compact` 模块的 `auto_compact_if_needed()`（第三篇详细拆解），它通过一个 `asyncio.Queue` 把压缩过程中的中间进度事件（`CompactProgressEvent`）实时转发出来，而不是等压缩完全做完才一次性返回——这样即便压缩本身要调一次 LLM 做摘要，UI 也能展示"正在压缩"这样的过渡状态而不是卡住。

流式事件的三路分发（`ApiTextDeltaEvent` / `ApiRetryEvent` / `ApiMessageCompleteEvent`）是 `run_query()` 与底层 API 客户端之间的契约——这三个类型定义在 `api/client.py`，是所有 Provider 适配器都必须产出的统一格式（下一篇详细展开）。`run_query()` 完全不关心这次请求底层走的是 Anthropic 原生协议还是 OpenAI Chat Completions，它只认这三种事件。

### 请求失败之后：完成 token 上限的自愈重试

```python
# src/openharness/engine/query.py
except Exception as exc:
    error_msg = str(exc)
    if _is_completion_token_limit_error(exc):
        supported_limit = _extract_completion_token_limit(exc)
        if supported_limit is not None and effective_max_tokens > supported_limit:
            previous_max_tokens = effective_max_tokens
            effective_max_tokens = supported_limit
            yield StatusEvent(message=(...)), None
            turn_count = max(0, turn_count - 1)
            continue
    if not reactive_compact_attempted and _is_prompt_too_long_error(exc):
        reactive_compact_attempted = True
        yield StatusEvent(message=REACTIVE_COMPACT_STATUS_MESSAGE), None
        async for event, usage in _stream_compaction(trigger="reactive", force=True):
            yield event, usage
        compacted_messages, was_compacted = last_compaction_result
        if compacted_messages is not messages:
            messages[:] = compacted_messages
        if was_compacted:
            continue
    if "connect" in error_msg.lower() or "timeout" in error_msg.lower() or "network" in error_msg.lower():
        yield ErrorEvent(message=f"Network error: {error_msg}. ..."), None
    else:
        yield ErrorEvent(message=f"API error: {error_msg}"), None
    return
```

这里有两条值得细看的"自愈"路径，都不是泛泛的 try/except：

第一条针对**服务端拒绝过大的 `max_tokens`**。`_extract_completion_token_limit()` 用一组正则去解析类似"supports at most 128000 completion tokens"这样的错误文案，抓出服务端真正接受的上限，然后把 `effective_max_tokens` 下调到这个值重试——注意 `turn_count = max(0, turn_count - 1)`，这次失败重试**不计入** `max_turns`，因为它本质上是同一次逻辑请求的参数修正，不是模型真的多做了一轮推理。这条路径解释了为什么函数开头要先算一个 `_bounded_completion_tokens()`：那是"启动时的保守估计"，这里是"运行时被服务端纠正"，两道防线配合，避免用户配置了一个过大的 `max_tokens` 导致每一轮都失败。

第二条针对**上下文超限**（`_is_prompt_too_long_error()` 用一长串关键词覆盖不同 Provider 各自的报错文案，比如 "context_length_exceeded"、"reduce the length of the messages"）。这条路径只会触发一次（`reactive_compact_attempted` 是个一次性标志位），强制执行一次全量压缩（`force=True`），压缩成功就 `continue` 重新进入 `while` 循环重新请求；这是与"每轮开始前的主动压缩检查"完全独立的**被动兜底**——主动检查基于 token 估算，估算天然不精确，被动兜底则是"服务端已经明确告诉你超了"之后的最后一道保险。

其余错误（网络问题、其他 API 错误）没有自愈路径，直接 `yield ErrorEvent(...)` 后 `return`——循环终止，交还控制权给上层决定要不要整体重试。

### 谁负责真正的 retry/backoff：不在这一层

`run_query()` 里处理的 `ApiRetryEvent` 只是**转发**，真正产生这个事件的重试逻辑在更底层的 API 客户端里：

```python
# src/openharness/api/client.py
MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds
MAX_DELAY = 30.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}

async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            self._refresh_client_auth()
            async for event in self._stream_once(request):
                yield event
            return  # Success
        except OpenHarnessApiError:
            raise  # Auth errors are not retried
        except Exception as exc:
            last_error = exc
            if attempt >= MAX_RETRIES or not _is_retryable(exc):
                ...
                raise RequestFailure(str(exc)) from exc
            delay = _get_retry_delay(attempt, exc)
            ...
            yield ApiRetryEvent(
                message=str(exc), attempt=attempt + 1,
                max_attempts=MAX_RETRIES + 1, delay_seconds=delay,
            )
            await asyncio.sleep(delay)
```

`_get_retry_delay()` 是标准的指数退避加抖动：`min(BASE_DELAY * (2 ** attempt), MAX_DELAY)` 再叠加最多 25% 的随机抖动，同时会优先尊重服务端返回的 `Retry-After` 头。这段逻辑的关键设计是**认证错误（`OpenHarnessApiError`）直接向上抛出、绝不重试**——重试一个错误的 API Key 没有任何意义，只会浪费时间。这个 retry 循环是每一个 `SupportsStreamingMessages` 实现都要各自维护的（下一篇会看到 `OpenAICompatibleClient`、`CodexApiClient` 都各自拷贝了一份结构几乎相同但状态码集合不同的重试逻辑）——`run_query()` 对这一切一无所知，它只是被动接收 `ApiRetryEvent` 并转成 `StatusEvent` 展示给用户"正在重试第几次、还要等几秒"。这是一处刻意的关注点分离：**重试策略是"怎么把一次请求打成功"的问题，属于传输层**；`run_query()` 关心的是"请求成功之后拿到的完整助手消息该怎么驱动下一步"，属于编排层。

### 工具调用的识别与派发：单工具与多工具两条路径

```python
# src/openharness/engine/query.py
if not final_message.tool_uses:
    if context.hook_executor is not None:
        await context.hook_executor.execute(HookEvent.STOP, {...})
    return

tool_calls = final_message.tool_uses

if len(tool_calls) == 1:
    tc = tool_calls[0]
    yield ToolExecutionStarted(tool_name=tc.name, tool_input=tc.input), None
    try:
        result = await _execute_tool_call(context, tc.name, tc.id, tc.input)
    except Exception as exc:
        result = ToolResultBlock(tool_use_id=tc.id, content=f"Tool {tc.name} failed: ...", is_error=True)
    yield ToolExecutionCompleted(tool_name=tc.name, output=result.content, is_error=result.is_error, ...), None
    tool_results = [result]
else:
    for tc in tool_calls:
        yield ToolExecutionStarted(tool_name=tc.name, tool_input=tc.input), None

    async def _run(tc):
        return await _execute_tool_call(context, tc.name, tc.id, tc.input)

    raw_results = await asyncio.gather(*[_run(tc) for tc in tool_calls], return_exceptions=True)
    tool_results = []
    for tc, result in zip(tool_calls, raw_results):
        if isinstance(result, BaseException):
            result = ToolResultBlock(tool_use_id=tc.id, content=f"Tool {tc.name} failed: ...", is_error=True)
        tool_results.append(result)
    for tc, result in zip(tool_calls, tool_results):
        yield ToolExecutionCompleted(...), None

messages.append(ConversationMessage(role="user", content=tool_results))
```

第一件要判断的事：`final_message.tool_uses` 是空列表——这是循环最自然的终止条件，模型给出了一段纯文本回答，没有再要求任何工具。这时会触发 `HookEvent.STOP` 钩子（供插件/hook 在会话自然结束时做收尾），然后函数直接 `return`，`while` 循环不会再跑下一轮。

单工具与多工具两条路径的区别，表面上是"要不要用 `asyncio.gather`"，实质是**流式反馈的粒度**。单工具路径先 `yield ToolExecutionStarted` 再 `await` 执行再 `yield ToolExecutionCompleted`，UI 能实时看到"工具正在跑"；多工具路径为了并发，必须先把所有 `ToolExecutionStarted` 一次性 `yield` 完，再统一 `gather`，再统一 `yield` 所有 `ToolExecutionCompleted`——这是并发执行必然带来的粒度损失，代码注释里也直白地写了取舍。

真正值得记住的一处细节是注释里点出的协议约束：`asyncio.gather(..., return_exceptions=True)`。如果不传这个参数，gather 中一旦有一个协程抛异常，其余尚未完成的协程会被取消（cancelled），这些工具调用就永远不会产生 `tool_result`；而 Anthropic（以及大多数遵循同一约定的 Provider）的 API 会直接拒绝下一轮请求，因为消息历史里存在没有匹配 `tool_result` 的 `tool_use` 块。所以这里宁可让每个工具调用各自失败、各自变成一条 `is_error=True` 的 `ToolResultBlock`，也不能让整批工具调用因为一个协程的异常而"消失"。

不管走哪条路径，最后都殊途同归：所有工具结果被打包进**一条 `role="user"` 的消息**追加到 `messages`，然后 `while` 循环自然进入下一轮——不需要任何显式的"要不要继续"判断，因为下一轮请求会把这条新消息带给模型，模型的响应本身就决定了循环是否继续。这也是为什么 `oh` 的循环比 DeepSeek-Harness 的 `kick/turn/step` 三层设计更"扁平"：`oh` 没有区分"用户可见交互边界"与"ReAct 最小单元"，一次用户输入触发的所有轮次都算在同一个 `run_query()` 调用、同一个 `turn_count` 计数里，工具调用产生的下一轮模型请求与用户主动发起的下一轮请求，在这个模型里没有结构性区别——代价是"用户中途插话"这类场景需要在更上层（`QueryEngine`/UI）处理，`run_query()` 本身不提供 steer/inject 这样的接口。

### 四种终止路径与 max_turns 硬限制

把前面几节串起来，`run_query()` 只有四种方式退出这个 `while` 循环：

1. **模型不再要求工具**（`final_message.tool_uses` 为空）——自然完成，`return`。
2. **模型返回了实质为空的助手消息**（`final_message.is_effectively_empty()`）——视为异常状态，落一条 `ErrorEvent` 并直接 `return`，避免把一条空消息写进历史污染后续请求。
3. **不可恢复的 API 错误**（网络问题、认证失败、无法通过 token 上限/上下文压缩自愈的错误）——落 `ErrorEvent` 后 `return`。
4. **`turn_count` 达到 `context.max_turns`**——`while` 循环条件不满足自然退出，函数末尾显式 `raise MaxTurnsExceeded(context.max_turns)`。`max_turns` 默认值在 `QueryContext` dataclass 里是 200，但 `QueryEngine` 构造时的默认值是 8——这个差异值得留意：`QueryContext.max_turns` 的 200 是一个"几乎不会触发"的安全阀默认值，真正生效的限制来自上层显式传入的 `QueryEngine(max_turns=8, ...)`。

`MaxTurnsExceeded` 是一个专门的异常类型（携带 `max_turns` 数值），而不是一个笼统的 `RuntimeError`——这让上层调用方可以精确捕获"是不是撞到了轮次上限"，而不用去解析异常消息字符串。

## 小结

`run_query()` 用一个单层 `while` 循环把"组装请求 → 消费流式响应 → 识别工具调用 → 并发执行并写回结果"这条链路串了起来，循环体内部的执行顺序（先压缩检查、再图片预处理、再模型请求）本身就承载了设计意图。重试与退避被下沉到更底层的 API 客户端里，`run_query()` 只负责把重试事件转发给用户；工具调用的执行则要在"流式反馈粒度"和"并发效率"之间做取舍，并且必须用 `return_exceptions=True` 规避 Provider 对"悬空 `tool_use`"的硬性拒绝。

这一篇始终没有细讲的是：`context.api_client.stream_message()` 背后，`AnthropicApiClient`、`OpenAICompatibleClient`、`CodexApiClient`、`CopilotClient` 这四个具体实现是怎么把差异悬殊的厂商协议，收敛成 `run_query()` 认识的那三种统一事件（`ApiTextDeltaEvent` / `ApiRetryEvent` / `ApiMessageCompleteEvent`）的。下一篇就沿着这条线，拆解 `oh` 的 Provider 抽象层与"workflow + profile"这套多模型适配设计。
