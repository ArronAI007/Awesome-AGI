# 会话事件溯源：Session Event Log 与 Surface

> `dsh` 里没有一个专门维护"当前对话消息列表"的可变数组——`Session` 只有一份 append-only 的事件日志，模型看到的消息历史是每次从这份日志"折叠"（fold）出来的派生结果。这不是性能上的偷懒，而是一个明确的架构决定：`packages/core/session/src/types.ts` 的文档注释里写得很直白——"Message history is derived from this log"。本篇拆开这份日志的事件词表、"Surface"这个居于日志与消息历史之间的中间层，以及为什么这套 event-sourcing + snapshot 的组合能同时支撑回放、压缩与审计三件事。

## 学习目标

- 理解 `SessionEventMap` 里各类事件（`turn/start`、`user/message`、`assistant/chunk`、`tool/call`、`request/header` 等）分别记录了什么语义，哪些是"日志专用、不产生消息"的记录，哪些会真正进入模型看到的历史。
- 理解 Surface 概念：`SurfaceEventType` 只包含三种事件（`user/message`/`assistant/message`/`tool/result`），以及 `SurfaceOp` 的 `append` 与 `{ op: 'replace' }` 两种写入方式分别对应什么场景。
- 通读 `Session.append()` 与 `foldSurface()`/`SurfaceManager` 的真实实现，理解"日志不可变，但可见视图可以折叠重写"这句话在代码层面具体是怎么落地的。
- 理解 `Session.deriveMessages()` 的增量缓存策略：为什么一次调用的开销是 O(新增节点数) 而不是 O(全部历史)。
- 通过 `RuntimeContextProjection` 这个具体案例，理解插件如何"只读日志、增量维护自己的投影状态"，而不需要维护一份独立的、可能与日志失配的可变状态。

## 背景与设计动机

如果 Agent 循环自己维护一个 `messages: Message[]` 数组，每次工具调用完就 `push` 一条结果，看起来最直接。但这样做会立刻遇到几个绕不开的问题：

- **回放与审计**：崩溃后重启，怎么知道模型上一次到底看到了什么？如果历史只存在于内存数组里，唯一能确认的办法是相信"数组和实际发生的事一致"，但一旦中途有 bug 篡改了数组内容，这个假设就会静默失效。
- **压缩（compaction）**：要把一段历史"折叠"成一条摘要，如果历史本身就是唯一的可变数组，这个操作要么直接破坏性地删除原文（丢失可审计性），要么就得额外维护一份"原始历史"用于审计——这又制造了第二份需要保持同步的状态。
- **流式重放保真度**：调试一次异常的模型输出，往往需要看到逐 token 的原始流，而不是组装完的最终结果——这类"原始但不产生消息"的记录，天然就不该和"产生消息"的记录混在同一种存储里。

`dsh` 的答案是：**日志是唯一权威来源，一切派生视图都是对日志的纯函数折叠**。`Session` 只暴露一个 `append()` 写入口，历史消息（`deriveMessages()`）、请求头（`requestHeader()`）、模型路由信息（`requestContext()`）全部是从日志某个前缀"折叠"出来的缓存投影，压缩不是删除，而是用一种叫 `replace` 的写入方式，往日志里追加一条新事件去"遮蔽"（shadow）一段旧的可见范围，原始事件仍然完整保留在日志里。

## 核心机制详解

### SessionEventMap：日志里到底记录了什么

`packages/core/session/src/types.ts` 定义了完整的事件词表（`SessionEventMap` 接口），这是一个 merge-extensible 的类型——插件可以通过 TypeScript 的 `declare module` 合并进自己的事件类型（前一篇里 `agent/inbox/spliced` 就是 `packages/core/agent` 合并进来的）。核心事件按语义可以分成四类：

**turn/step 边界标记**：

```typescript
// packages/core/session/src/types.ts
'turn/start': { turn: number }
'turn/end': { turn: number; reason: TurnEndReason }
'step/start': { turn: number; step: number }
'step/end': { turn: number; step: number }
```

这四类事件不产生任何模型可见消息，纯粹是"这里是一个 turn/step 的开始或结束"的书签，供回放和调试定位。

**产生模型消息的三类事件**（下一节展开细节）：

```typescript
'user/message': UserMessage
'assistant/message': { turn: number; step: number; message: AssistantMessage; usage?: TokenUsage }
'tool/result': { turn: number; step: number; message: ToolResultMessage; error?: {...}; meta?: JsonValue }
```

**原始流与调用记录**：

```typescript
'assistant/chunk': { turn: number; step: number; chunk: StreamChunk }
'tool/call': { turn: number; step: number; callId: CallId; name: string; arguments: string }
```

`assistant/chunk` 记录的是**逐 token 的原始流**，`tool/call` 记录的是模型发出的**原始调用**（`arguments` 是模型输出的原始 JSON 字符串，未解析）——这两类都不是"消息"，但对回放保真度至关重要（第三篇细讲）。

**请求状态与日志专用记录**：

```typescript
'request/header': { header: EpochHeader; reason: RequestHeaderReason }
'request/context': RequestContext
'todo/write': { todos: TodoItem[] }
'session/end-seed': Record<string, never>
```

`request/header` 记录的是"下一次请求会用的完整配置"（provider、model、渲染好的 system prompt、工具 schema），`RequestHeaderReason` 的三个取值——`'initial'`（日志的第一条 header）、`'resume'`（同一个日志上，这个进程实例第一次发请求，比如进程重启后）、`'change'`（后续请求换了配置）——精确记录了"配置在什么时候真的变了"，而不是每次请求都重复写一遍。

值得注意的是 `ignorable` 标记（定义在 `SessionEvent` 类型上）：一个读取者遇到不认识的事件类型时，默认必须拒绝重建整个会话（因为这条事件可能改变了后续内容该如何解读），只有显式标了 `ignorable: true` 的纯信息性记录才允许被安全跳过。这是"宁可过度保守也不能悄悄丢数据"的设计取向。

### Surface：日志与"模型可见历史"之间的中间层

三类产生消息的事件——`user/message`、`assistant/message`、`tool/result`——共同构成了 **Surface**（`SurfaceEventType`）。Surface 不是另一份存储，而是日志之上的一层"当前哪些事件仍然可见"的索引：

```typescript
// packages/core/session/src/types.ts
export type SurfaceOp =
  | 'append'
  | { op: 'replace'; start: number; end: number }
```

`append` 是最常见的写法——事件追加到 surface 尾部，比如一条正常的用户消息或模型回复。`{ op: 'replace', start, end }` 则是用一个新节点，把 `start` 到 `end`（按 surface 上的相对顺序，闻及两端都必须是当前 surface 上真实存在的节点）这一段整体替换掉——这正是压缩机制的底层写入原语（第四篇会看到 `compaction-basic` 如何用它把一大段历史换成一条摘要）。

Surface 的折叠逻辑在 `packages/core/session/src/surface.ts` 的 `foldSurface()`（一次性折叠整份日志）和 `SurfaceManager`（增量维护，`Session` 内部持有的实例）里：

```typescript
// packages/core/session/src/surface.ts
export function foldSurface(events: readonly SessionEvent[]): SurfaceFoldResult {
  const state = createFoldState()
  const replacements: SurfaceFoldReplacement[] = []
  for (const [index, event] of events.entries()) {
    const replacement = applySurfaceEvent(state, event, index, events, 0)
    if (replacement !== undefined) replacements.push(replacement)
  }
  return { nodes: [...state.nodes], replacements }
}
```

`applySurfacePlan` 的核心操作只有两行：

```typescript
// packages/core/session/src/surface.ts
if (plan?.kind === 'append') {
  state.nodes.push(plan.seq)
} else if (plan?.kind === 'replace') {
  state.nodes.splice(plan.startIdx, plan.endIdx - plan.startIdx + 1, plan.seq)
  state.replaceGeneration += 1
}
```

`append` 就是往 `nodes`（当前可见的事件 seq 列表）尾部追加一个 seq；`replace` 是用 `Array.splice` 把一段连续的旧 seq 整体换成一个新 seq——**注意这只是修改"当前可见的索引"，被替换掉的旧事件本身仍然原样留在日志（`events`/`this.log`）里，从来没有被删除或修改**。每发生一次 `replace`，`replaceGeneration` 就加一，这个计数器后面会用来判断"派生消息缓存是否需要重新构建"。

写入 Surface 有严格的正确性校验，比如替换操作要求新事件的 `sourceEventSeqs` 必须**完整覆盖**被遮蔽的每一个旧 seq：

```typescript
// packages/core/session/src/surface.ts
const missing = shadowedSeqs.filter(seq => !sources.has(seq))
if (missing.length > 0) {
  throw new Error(`surface replace: sourceEventSeqs must include every shadowed surface node; missing ${missing.join(', ')}`)
}
```

这保证了"这条摘要替换了哪些原始事件"这一血缘关系在日志层面是可验证的，不是靠约定，而是 `Session.append()` 内部真的会拒绝不满足这个约束的写入。

### deriveEventMessage：Surface 节点到 Message 的投影规则

一个 Surface 上的事件如何变成模型看到的一条 `Message`，规则集中在一个纯函数里：

```typescript
// packages/core/session/src/surface.ts
export function deriveEventMessage(event: SessionEvent): Message | null {
  switch (event.type) {
    case 'user/message': {
      return event.data
    }
    case 'assistant/message': {
      if (event.data.message.content.length === 0) return null
      return event.data.message
    }
    case 'tool/result': {
      return event.data.message
    }
    default:
      return null
  }
}
```

三条规则里藏着一个不起眼但很重要的细节：`assistant/message` 如果 `content` 是空数组，会返回 `null`——即"这个 surface 节点存在，但不产生任何消息"。这对应一种特殊场景：一次 step 因为 `max-tokens` 被截断，模型这一步什么内容都没产出、只携带了一份 usage 统计,这类事件被记录下来（为了 usage 账目完整）,但绝不能在派生历史里插入一条空的 assistant 轮次——那会让下一次请求的消息序列出现语义上没有意义的空发言。

### deriveMessages()：增量缓存的派生历史

`Session.deriveMessages()` 是外部真正拿到"当前完整消息历史"的唯一入口，`buildRequest()` 每次组装请求前都会调用它。它的实现刻意做了增量缓存：

```typescript
// packages/core/session/src/index.ts
deriveMessages(): Message[] {
  const surface = this.surface
  const nodes = surface.nodes
  const generation = surface.replaceGeneration
  if (generation !== this.derivedGeneration) {
    this.derived = []
    this.derivedNodes = 0
    this.derivedGeneration = generation
  }
  for (const seq of nodes.slice(this.derivedNodes)) {
    const msg = this.deriveEventMessage(this.log[seq]!)
    if (msg) this.derived.push(msg)
  }
  this.derivedNodes = nodes.length
  return [...this.derived]
}
```

逻辑是：只要 `replaceGeneration`（前面提到的、每次 `replace` 都会自增的计数器）没变，说明这段时间只发生了 `append`，那就只需要把"上次已经投影过的位置"之后的新节点投影一遍、追加进缓存数组；如果 `replaceGeneration` 变了（发生过一次压缩替换），说明整个 surface 的节点排列可能被重新调整过，缓存被整体清空重建。这让"没有压缩发生的正常对话"每次调用的开销只有 O(新增节点数)，而不是每次都要把整份历史重新投影一遍——对一个可能有几千条事件的长会话来说，这个差别是数量级的。

同一套"缓存 + 增量重新折叠"的模式还出现在 `requestHeader()`（缓存最近一次 `request/header` 折叠结果）和 `requestContext()`（缓存最近一次 `request/context`）上，三者都遵循相同的原则：**日志是唯一权威源，任何派生状态都可以随时从某个前缀重新算出来，缓存只是一个性能优化，绝不是另一份独立事实**。

### Session.append()：唯一写入口的强校验

所有这些投影能保持正确的前提，是 `append()` 这一个方法把好几层校验焊死在了写入路径上：

```typescript
// packages/core/session/src/index.ts（节选）
append<T extends SessionEventType>(
  type: T,
  data: SessionEventMap[T],
  ...opts: T extends SurfaceEventType ? [opts: SurfaceIntent] : []
): SessionEvent<T> {
  const dataSnapshot = snapshotJsonValue(data)
  if (dataSnapshot === undefined) {
    throw new Error(`session event "${type}" carries non-JSON-serializable data`)
  }
  // ...
  const event = deepFreeze({
    type, seq: this.log.length, time: Date.now(), data: dataSnapshot,
    ...(surfaceMetadataSnapshot as { surfaceOp?: unknown; sourceEventSeqs?: unknown }),
  } as unknown as SessionEvent<T>)
  this.surfaceManager.validateNext(event as SessionEvent)
  // ...
  this.log.push(event as SessionEvent)
  // ...
  return event
}
```

三个值得注意的点：**类型层面的强制**——TypeScript 的条件类型 `T extends SurfaceEventType ? [opts: SurfaceIntent] : []` 让"三种 surface 事件必须带 `surfaceOp`，其余事件禁止带"这个约束在编译期就能被检查到，不需要等运行时才发现某个事件漏写了 `surfaceOp`；**运行时的 JSON 无损校验**——`snapshotJsonValue` 会拒绝 `BigInt`、函数、`Symbol`、循环引用等一切不能被无损序列化成 JSON 的值,因为日志必须能被逐字节持久化和重放；**deepFreeze**——一旦事件写进日志,连它自身都是深度冻结的,任何后续代码都不可能"悄悄改一下已经落盘的历史"。

### 案例：RuntimeContextProjection——只读日志、增量维护自己的投影

前一篇提到 `preStep()` 会调用 `this.runtimeContext.project(...)` 生成一条"运行时上下文快照"（当前工作目录、时间等易变信息），它的实现完整体现了"从日志重建投影"这套方法论该怎么落地：

```typescript
// packages/core/agent-loop/src/runtime-context.ts
export class RuntimeContextProjection {
  private retained: { seq: number; text: string | undefined } | null | undefined

  constructor(ctx: Context, session: Session) {
    const surface = new Set(session.surface.nodes)
    for (let index = session.events.length - 1; index >= 0; index -= 1) {
      const event = session.events[index]
      if (event?.type !== 'user/message' || !isOwned(event.data)) continue
      this.retained ??= null
      if (surface.has(event.seq)) {
        this.retained = { seq: event.seq, text: textOf(event.data) }
        break
      }
    }
    ctx.on('session/event', (subject, event) => {
      if (subject !== session) return
      if (event.type === 'user/message' && isOwned(event.data)) {
        this.retained = { seq: event.seq, text: textOf(event.data) }
      } else if (this.retained
        && isReplacementSurfaceEvent(event)
        && event.sourceEventSeqs?.includes(this.retained.seq) === true) {
        this.retained = null
      }
    })
  }

  project(current: string, sections: readonly ContextSnapshotSection[]): UserMessage | undefined {
    if (this.retained === undefined && current.length === 0) return
    const snapshot = current.length === 0 ? CLEARED : current
    if (this.retained?.text === snapshot) return
    return createUserMessage({ /* ... */ })
  }
}
```

构造函数先做**一次性回溯**：从日志尾部往前扫，找到这个插件自己写过的、且仍然在当前 surface 上可见的最近一条快照，重建出 `retained` 状态——这是"进程重启/resume 后如何恢复内存态投影"的标准做法。此后完全靠订阅 `session/event`（`Session` 每次 `append()` 成功后同步触发的观察者钩子）**增量维护**：看到自己写的新快照就更新 `retained`；如果某次压缩的 `replace` 事件"吃掉"了自己上次记的那条快照（`sourceEventSeqs` 里包含了它），就把 `retained` 清空——这样下次 `project()` 会重新生成一条新快照而不是继续假装旧快照还在。

`project()` 本身是一个纯粹的"去重"判断：只有当渲染出来的当前上下文文本和已经记住的上一条快照不同时，才返回一条新的 `UserMessage` 交给 `preStep()` 去追加；完全相同就返回 `undefined`，什么都不做——避免每一步都往历史里塞一条内容重复的上下文消息。

## 小结

- 会话的唯一事实来源是一份 append-only、深度冻结、强 JSON 校验的事件日志；`SessionEventMap` 里的事件分为"产生消息"（三种 Surface 事件）和"不产生消息但记录过程"（边界标记、原始 chunk、请求头快照等）两大类。
- Surface 是日志之上的一层可重写索引：`append` 追加、`{ op: 'replace' }` 替换，替换只改变"当前可见范围",从不删除或修改原始事件——这就是"日志不可变、但可见视图可以折叠"的具体实现。
- `deriveMessages()`、`requestHeader()`、`requestContext()` 都是"缓存 + 按需增量重折叠"的派生投影,而不是独立维护的可变状态；`replaceGeneration` 是判断"要不要整体重建缓存"的信号。
- 任何需要"记住点什么、跨进程重启也要对得上"的插件，都应该参照 `RuntimeContextProjection` 的写法：构造时从日志回溯重建一次性状态，之后订阅 `session/event` 增量维护，绝不自己另开一份独立于日志的持久状态。
