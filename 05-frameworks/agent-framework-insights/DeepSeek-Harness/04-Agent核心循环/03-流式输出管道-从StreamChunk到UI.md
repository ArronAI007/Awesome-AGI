# 流式输出管道：从 StreamChunk 到 UI

> 一个模型输出的字符，从 DeepSeek 服务端的 SSE 报文，到浏览器里打字机式跳出来的文字，中间要经过五层完全独立的"重组"：Provider 把裸字节解析成协议无关的 `StreamChunk`，`LlmRuntime` 用一个 waterfall 中间件链包一层，`ReactLoopAgent.step()` 用 `BlockAssembler` 边组装边落盘，Host 把会话事件重新打包成 WebSocket 帧推给浏览器,Client 又用一个几乎一模一样的累加器把 chunk 重新拼回可渲染的块。本篇按数据实际流动的顺序，逐层拆开这条管道，并回答一个看似浪费、其实是核心设计取舍的问题：**为什么每一个原始 chunk 都要被原样落盘一次**。

## 学习目标

- 理解 `StreamChunk` 这个协议无关的中间表示长什么样，以及 `DeepSeekAdapter.stream()` 如何把 SSE 字节流转换成它。
- 理解 `LlmRuntime` 的 `'llm/stream'` waterfall 中间件链的作用——它是插件（比如下一篇的 checkpoint 策略）介入"模型请求即将发出"这一时刻的唯一入口。
- 通读 `BlockAssembler` 的真实实现，理解它如何把碎片化的 `block-start`/`text-delta`/`tool-call-delta`/`block-end` 等六种 chunk 类型，增量组装成完整的 `ContentBlock[]`。
- 理解"原始 chunk 全部落盘"这个设计决策背后的取舍：用日志体量换取逐 token 级别的回放保真度。
- 理解 Host 如何把 `session/event` 重新打包成 WebSocket 帧（`FrameQueue`/`mux`），以及 Client 侧的 `PartialAccumulator` 为什么要独立于 `BlockAssembler` 再实现一遍几乎相同的折叠逻辑。

## 背景与设计动机

流式输出（streaming）本身不难——大多数 LLM SDK 都提供"边生成边吐"的能力。真正难的是把这件事嵌进一个需要"完整历史可回放、可持久化、可在多个消费者之间转发"的系统里，会同时冒出几个互相牵制的需求：

- **协议要统一**：DeepSeek、`pi-ai` 等不同 provider 的原始流格式各不相同（SSE 字段名、分块粒度都不一样），Agent 循环不该关心这些差异。
- **既要流式展示、又要有一个"最终定型"的消息**：UI 需要边到边渲染的原始 delta，但会话历史（第二篇讲的 Surface）只应该记一条组装完整的 `assistant/message`，不能把中间态污染进正式历史。
- **可靠重放优先于存储效率**：调试一次异常输出（比如模型在某个 token 处莫名其妙换了语言，或者一次奇怪的工具调用参数是怎么被拼出来的），最有效的手段是能看到逐 token 的原始流，而不是只有组装完的最终结果。
- **多端消费**：同一份流式输出，既要喂给持久化的会话日志，又要喂给可能同时打开的多个浏览器标签/多个客户端。

`dsh` 的解法是让每一层都做且只做自己该做的事：Provider 只管协议转换，`LlmRuntime` 只管中间件编排，`ReactLoopAgent` 只管"边落盘边组装"，Host 只管"把会话事件搬运到 WebSocket 帧"，Client 只管"把帧再折叠成可渲染的 UI 状态"。下面按这个顺序展开。

## 核心机制详解

### 第一层 Provider → Adapter：把 SSE 字节流转换成 StreamChunk

`packages/llm/llm-deepseek/src/sse.ts` 里的 `parseSse()` 负责把裸的 SSE 字节流解析成 DeepSeek 协议的原始文本负载：

```typescript
// packages/llm/llm-deepseek/src/sse.ts
export async function* parseSse(
  stream: ReadableStream<BufferSource>,
  onComment?: (comment: string) => void,
): AsyncGenerator<string> {
  const events = stream
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(new EventSourceParserStream({ onComment }))
  for await (const { data } of events) {
    yield data
    if (data === DONE) return
  }
  throw new LlmError('SSE stream ended without [DONE]', 'STREAM_CLOSED')
}
```

注意它把"帧重组"（分块可能在任意字节边界断开，甚至断在一个 UTF-8 多字节字符中间）完全委托给了 `eventsource-parser` 这个第三方库，自己只保留了一条 DeepSeek 协议特有的规则：**必须显式收到 `[DONE]` 才算流正常结束**，如果 EOF 之前没看到它，说明响应被截断，直接 `throw` 一个 `LlmError('STREAM_CLOSED')`——这是"流看起来正常结束、但其实是网络层面被截断"这类隐蔽故障的第一道防线。

再往上一层，`DeepSeekAdapter.stream()`（`packages/llm/llm-deepseek/src/adapter.ts`）把这些原始 payload 经过 `translate()` 转换成协议无关的 `StreamChunk`，并且套了一层空闲超时看门狗：

```typescript
// packages/llm/llm-deepseek/src/adapter.ts（节选）
async * stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
  const connection = this.config.options()
  const apiKey = await this.config.resolveApiKey(connection)
  const consumer = new AbortController()
  const upstream = options.signal === undefined ? consumer.signal : AbortSignal.any([options.signal, consumer.signal])
  using watchdog = idleWatchdog(upstream, connection.streamIdleTimeoutMs, STREAM_IDLE_TIMEOUT_CODE)
  const iterator = this.request(options, watchdog.signal, connection, apiKey, userId, () => { watchdog.pulse() })[Symbol.asyncIterator]()
  try {
    while (true) {
      const result = await watchdog.next(iterator)
      if (result.done) { exhausted = true; return }
      yield result.value
    }
  } catch (error: unknown) {
    if (timeoutOf(watchdog.signal, STREAM_IDLE_TIMEOUT_CODE) !== undefined) {
      throw new LlmError(`DeepSeek stream idle timeout after ${connection.streamIdleTimeoutMs}ms`, 'TIMEOUT', { cause: error })
    }
    if (options.signal?.aborted) throw new LlmError('DeepSeek request aborted by caller', 'ABORTED', { cause: error })
    if (error instanceof LlmError) throw error
    throw new LlmError(`DeepSeek API stream from ${connection.baseURL} failed`, 'TRANSPORT', { cause: error })
  } finally {
    consumer.abort('DeepSeek stream consumer stopped')
    if (!exhausted && iterator.return !== undefined) { try { await iterator.return() } catch {} }
  }
}
```

一个信号（`upstream`）同时服务两件事：调用方主动取消（`options.signal`）和空闲看门狗超时（`idleWatchdog` 内部的 `watchdog.signal`），两者用 `AbortSignal.any` 融合成一个。`catch` 块里的判断顺序也是精心设计的——先判断是不是看门狗超时（映射成 `TIMEOUT`），再判断是不是调用方主动取消（映射成 `ABORTED`），最后才是兜底的 `TRANSPORT`——这保证了同一次失败，无论真实原因是什么，最终抛出的 `LlmError` 都带着一个稳定、可被后续重试逻辑（第五篇）用来做路由判断的 `code`，而不是一段自然语言消息。

### 第二层 Adapter → LlmRuntime：一个可被中间件插入的 waterfall

`LlmRuntime`（`packages/llm/llm/src/index.ts`）并不直接把 adapter 的流原样吐出去,而是包了一层 Cordis 的 `waterfall` 中间件链：

```typescript
// packages/llm/llm/src/index.ts
private streamWithRegistration(
  options: GenerateOptions,
  prepared?: { registration: AdapterRegistration; config: LlmCallConfig },
): AsyncIterable<StreamChunk> {
  return this.ctx.waterfall(
    this,
    'llm/stream',
    options,
    () => this.adapterStream(options, prepared),
  )
}
```

`'llm/stream'` 这个事件名的类型签名是：

```typescript
// packages/llm/llm/src/index.ts
'llm/stream'(this: LlmRuntime, options: GenerateOptions, next: () => AsyncIterable<StreamChunk>): AsyncIterable<StreamChunk>
```

任何插件都可以监听这个事件,拿到 `next()`（代表"更内层中间件或者最终 adapter 会返回的流"）,决定原样转发、包一层新的 `AsyncIterable` 再返回，甚至完全替换掉。下一篇要讲的 `session-checkpoint-policy` 正是挂在这里——它在真正调用 `next()`（也就是真正向 provider 发起请求）之前，先做一次会话落盘 `flush`，实现"发模型请求前必须先把请求本身持久化"的 fail-closed 语义：

```typescript
// packages/session/session-checkpoint-policy/src/index.ts
function afterCheckpoint(ctx: Context, session: Session, next: () => AsyncIterable<StreamChunk>): AsyncIterable<StreamChunk> {
  return (async function* (): AsyncIterable<StreamChunk> {
    await ctx.sessions.flush(session)
    yield* next()
  })()
}
ctx.on('llm/stream', (options, next): AsyncIterable<StreamChunk> => {
  if (options.sessionId === undefined) return next()
  const session = ctx.sessions.get(options.sessionId)
  return session === undefined ? next() : afterCheckpoint(ctx, session, next)
})
```

`adapterStream()`（waterfall 链条最内层的默认实现）本身还负责把"adapter 选择失败""迭代器构造失败""迭代过程中途抛异常"这三类完全不同来源的失败，统一收敛成一种协议——一个 `{ type: 'finish', reason: { kind: 'error' | 'aborted', failure } }` 的终止 chunk，而不是让异常直接从 `AsyncGenerator` 里抛出来打断消费者的 `for await`：

```typescript
// packages/llm/llm/src/index.ts（节选）
function adapterFailureChunk(error: unknown, signal?: AbortSignal): StreamChunk {
  const failure = normalizeLlmFailure(error)
  return {
    type: 'finish',
    reason: signal?.aborted || failure.code === 'ABORTED' ? { kind: 'aborted', failure } : { kind: 'error', failure },
  }
}
```

这意味着 `ReactLoopAgent.step()` 消费流的时候永远只需要处理"正常的 chunk"和"一条携带失败信息的 `finish` chunk"两种情况,不需要额外套 `try/catch` 来兜底 adapter 层面的各种抛异常方式——这也是为下一篇的重试机制铺路：重试判断的输入永远是一条结构化的 `finish` chunk，不是裸的 JS 异常。

### 第三层 LlmRuntime → Agent Loop：边落盘边组装

回到第一篇讲过的 `step()`,这是整条管道里**唯一同时做"落盘"和"组装"两件事**的一层：

```typescript
// packages/core/agent-loop/src/agent.ts（节选）
const assembler = new BlockAssembler()
const chunkSeqs: number[] = []
const stream = preparedCall?.stream(request) ?? this.loopCtx.llm.stream(request)
for await (const chunk of stream) {
  chunkSeqs.push(this.session.append('assistant/chunk', { turn, step, chunk }).seq)
  assembler.push(chunk)
}
```

每一个 chunk 到达时,**先**被写进会话日志（`session.append('assistant/chunk', ...)`),拿到它的 `seq`,**再**喂给 `BlockAssembler.push()`。顺序不能颠倒:落盘是权威记录,组装只是这次内存里的即时消费——即使 `BlockAssembler` 因为某种 bug 组装出错,日志里仍然保留着逐 chunk 的原始事实,足够事后重新跑一遍投影逻辑来定位问题。收集到的 `chunkSeqs`（每条 `assistant/chunk` 事件的日志序号）之后会被记录进最终 `assistant/message` 事件的 `sourceEventSeqs` 里——这就是第二篇讲过的"血缘关系"在流式场景下的具体体现:一条组装完的消息,精确知道自己是由哪些原始 chunk 拼出来的。

`BlockAssembler` 本身（`packages/llm/llm/src/assembler.ts`）是这条管道里真正的"折叠算法"核心:

```typescript
// packages/llm/llm/src/assembler.ts
push(chunk: StreamChunk): void {
  switch (chunk.type) {
    case 'block-start': {
      if (!this.partials.has(chunk.index)) {
        this.order.push(chunk.index)
        this.partials.set(chunk.index, { blockType: chunk.blockType, text: '', toolCallArguments: '' })
      }
      return
    }
    case 'text-delta':
    case 'reasoning-delta': {
      const partial = this.ensure(chunk.index, chunk.type === 'text-delta' ? 'text' : 'reasoning')
      if (partial.block) return // closed by block-end; ignore stragglers
      partial.text += chunk.text
      return
    }
    case 'tool-call-delta': {
      const partial = this.ensure(chunk.index, 'tool-call')
      if (partial.block) return
      partial.toolCallId = chunk.id
      if (chunk.name) partial.toolCallName = chunk.name
      partial.toolCallArguments += chunk.argumentsDelta
      return
    }
    case 'block-end': {
      const partial = this.ensure(chunk.index, chunk.block.type)
      if (partial.block) return
      partial.block = chunk.block
      return
    }
    case 'usage': { this._usage = chunk.usage; return }
    case 'finish': { this._finish = chunk.reason; this._replayState = chunk.replayState; return }
    default: return assertNever(chunk, 'BlockAssembler.push')
  }
}
```

`StreamChunk` 是一个按 `index`（内容块在这条消息里的位置）分片的增量协议,`BlockAssembler` 用一个 `Map<number, PartialBlock>` 按 `index` 维护每个内容块自己的组装状态——文本类块（`text`/`reasoning`）是简单的字符串累加,工具调用块是"调用 id + 名字 + 参数 JSON 片段"三个字段各自累加,直到一条 `block-end` 到达把这个 `index` "钉死"成最终的 `ContentBlock`。**"第一次关闭生效,之后的迟到 delta 被忽略"**（`if (partial.block) return`）是一条专门针对畸形流的防御:如果某个 provider 的实现有 bug,在 `block-end` 之后又发来同一个 `index` 的 delta,这条防线保证最终组装结果和当时流式展示给用户看到的内容完全一致,不会因为迟到数据而产生"UI 上看到的和存进历史的不一样"的诡异错位。

`blocks()` 还处理了一个边界情况:

```typescript
// packages/llm/llm/src/assembler.ts
blocks(): ContentBlock[] {
  const blocks = this.order.map(index => this.assemble(this.mustGet(index), index))
  return this.finish.kind === 'max-tokens'
    ? blocks.filter(block => block.type !== 'tool-call')
    : blocks
}
```

如果这一步是被输出 token 上限截断的（`max-tokens`),组装结果里的工具调用块会被整体过滤掉——一个被截断的工具调用参数（比如一个被截成一半的文件路径字符串)如果被当真执行,后果可能是危险的,所以宁可让模型"这一步什么工具都没调用",也不要执行一个残缺的调用。

### 第四层 Session events → Host：把日志事件重新打包成 WebSocket 帧

`assistant/chunk` 事件落盘之后会同步触发 `session/event` 观察者钩子,Host 端的 `packages/host/apiproxy/src/api-proxy.ts` 就是这些观察者之一——它把每一条会话事件重新包装成一个可以在 WebSocket 上传输的帧,推进一个简单的异步队列:

```typescript
// packages/host/apiproxy/src/api-proxy.ts（节选）
class FrameQueue<F> {
  private buffer: F[] = []
  private waiter: (() => void) | undefined
  private done = false
  push(item: F): void {
    if (this.done) return
    this.buffer.push(item)
    this.waiter?.()
  }
  async *iterate(signal: AbortSignal, cleanup: () => void): AsyncGenerator<F> {
    // ... 阻塞等待新帧,直到 abort 或 end
  }
}
```

```typescript
// packages/host/apiproxy/src/api-proxy.ts（events.mux 节选）
ctx.on('session/event', (session: Session, event: SessionEvent) => {
  // ... 维护 openCalls 表用于结果视图配对
  const view = viewFor(ctx, event, callId => openCalls.get(session.id)?.get(callId) ?? backscanArgs(session.events, callId), ctx.agents.get(session.id))
  queue.push(frame({ type: 'session/event', sessionId: session.id, event, ...view === undefined ? {} : { view } }))
})
```

`events.mux` 这个 RPC 方法被调用时,会先把"当前所有会话的订阅基线"（`subscribeSession`,携带每个会话已有的 `lastSeq`,让重连的客户端知道自己该从哪个 seq 之后继续接收）一次性推进队列,再挂上 `session/event` 监听器持续转发后续新事件——这是"快照 + 增量"这套模式在传输层的又一次复现（和第二篇 `deriveMessages()` 的缓存策略、`RuntimeContextProjection` 的重建逻辑同源）。`WebSocketDownlinks.pump()`（`packages/client/connection/src/websocket-downlink.ts`）在 Node 侧把这个异步帧流通过 `ws` 库真正发到浏览器:

```typescript
// packages/client/connection/src/websocket-downlink.ts（节选）
private async pump<F extends Frame>(socket: WebSocket, frames: AsyncIterable<RpcRequest<F>>, abort: AbortController): Promise<void> {
  try {
    for await (const frame of frames) await send(socket, frame)
  } catch (error) {
    if (!abort.signal.aborted) { try { await send(socket, failureFrame(error)) } catch {} }
  } finally {
    abort.abort()
    if (socket.readyState === WebSocket.OPEN) socket.close()
  }
}
```

### 第五层 Client：再折叠一次,服务于渲染而非历史

浏览器收到的 `session/event` 帧里,如果 `event.type === 'assistant/chunk'`,客户端并不会直接把裸 chunk 塞进 DOM——它需要一个和 `BlockAssembler` 几乎同构、但服务于不同目的的折叠器。`packages/client/runtime/src/client/sessions/partial.ts` 的 `PartialAccumulator` 正是这样一个"客户端专属的 BlockAssembler"：

```typescript
// packages/client/runtime/src/client/sessions/partial.ts（节选）
push(chunk: StreamChunk): boolean {
  switch (chunk.type) {
    case 'block-start': { this.blocks[chunk.index] = emptyAssistantBlock(chunk.blockType); this.changed = true; return true }
    case 'text-delta': {
      const prev = this.blocks[chunk.index]
      this.blocks[chunk.index] = { kind: 'text', text: (prev?.kind === 'text' ? prev.text : '') + chunk.text }
      this.changed = true
      return true
    }
    // ... reasoning-delta / tool-call-delta 同构
    case 'block-end': { this.blocks[chunk.index] = toAssistantBlock(chunk.block); this.changed = true; return true }
    default: return false // usage / finish 不改变可见块
  }
}
```

它和服务端 `BlockAssembler` 的核心折叠逻辑几乎一致（按 `index` 累加文本/参数片段,`block-end` 钉死最终形态),但两者是完全独立的两套实现,分别服务两种不同的消费场景：`BlockAssembler` 的产物要进入会话历史（`assistant/message`),必须严格、完整、可被下一次请求复用；`PartialAccumulator` 的产物只是一份"临时的 UI 快照"（`toPartial()` 返回的 `PartialAssistant`),一旦对应的 `assistant/message`（组装完的最终版本)事件到达,这份临时快照就会被直接丢弃、由权威版本取代。**同一份流式数据在两处被分别、独立地折叠**,这正是"每一层只信任自己收到的原始输入,不跨层共享可变中间状态"这条原则的体现——客户端完全可以只依赖 `session/event` 帧本身重建出正确的显示状态,不需要以任何方式信任服务端"已经算好的中间结果"。

### 为什么要把每个原始 chunk 都落盘

把整条链路串起来看,这个问题的答案已经比较清楚了:

- **回放保真度**:`assistant/chunk` 事件是唯一保留了"模型输出到底是怎么一小块一小块吐出来的"这一事实的地方。组装完的 `assistant/message` 只保留最终结果,一旦丢弃了原始 chunk,像"某个工具调用的参数在流式过程中是不是被两次不同的 delta 修改过"这类调试线索就永久丢失了。
- **崩溃恢复的精确性**:如果进程在收到一半 chunk 时崩溃,重启后可以从日志里看到"这一步收到了多少 chunk、组装到了什么程度",而不是只知道"这一步没有留下任何 assistant/message,所以整体重来"。
- **多消费者的解耦**:Host 转发给 Client 的正是这条 `assistant/chunk` 序列,如果服务端不落盘、只做内存转发,一旦浏览器中途刷新重连,唯一能补上"刚才漏掉的流式片段"的办法就是重新读一遍持久化日志——这要求 chunk 本身必须是持久化事实,不能只是转瞬即逝的内存事件。

这个设计的代价是显而易见的:一次几百 token 的回复可能对应几十上百条 `assistant/chunk` 事件,日志体量会明显膨胀。`dsh` 选择用"日志体量"换"逐 token 级别的回放保真度与多端一致性",这是一个典型的、值得在自己的系统设计中借鉴的权衡取向:**能被完整重放，本身就是一种可观测性**。

## 小结

- 流式管道分五层：Provider 协议转换（`parseSse` + `translate`）→ `LlmRuntime` 的 `'llm/stream'` waterfall（中间件可介入,如 checkpoint）→ Agent Loop 边落盘边组装（`BlockAssembler` + `assistant/chunk` 落盘）→ Host 把会话事件重打包成 WebSocket 帧（`FrameQueue`/`mux`）→ Client 独立再折叠一次服务于渲染（`PartialAccumulator`）。
- `BlockAssembler` 按内容块 `index` 维护增量组装状态,`block-end` 到达即钉死,之后的迟到 delta 被忽略;`max-tokens` 截断时会把不完整的工具调用块整体过滤掉。
- 每个原始 chunk 落盘是"用存储换回放保真度与多端一致性"的明确取舍,不是实现上的偶然。
