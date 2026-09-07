# ReactLoopAgent 总览：kick → turn → step

> `dsh` 的整个 Agent 引擎最终都收敛到一个类——`packages/core/agent-loop/src/agent.ts` 里的 `ReactLoopAgent`。它把"驱动一次对话"拆成三层严格嵌套的调用：`kick()` 反复开新 turn 直到没有排队输入，`turn()` 在一个 turn 内反复做 step 直到没有模型该做的事，`step()` 发一次模型请求并把它触发的工具调用执行完。这三层不是随意的代码组织，而是分别对应"会话该不该继续""一次用户可见交互的边界在哪""ReAct 循环的最小单元是什么"三个不同的问题。

## 学习目标

- 理解 `kick → turn → step → buildRequest` 四层调用结构各自的职责边界，以及为什么工具调用（ReAct 循环）发生在 step 层而不会产生新的 turn。
- 搞清楚一次 `kick()` 是被什么触发的：`Agent.send/followup/steer/inject` 如何把消息放进 `Inbox`，又如何唤醒一个空闲的 driver。
- 通读 `turn()` 的真实实现，理解"turn 何时该结束"这件事为什么由多个信号（`inbox` 是否还有排队消息、`agent/turn-stopping` 串行钩子、`max-tokens` 的粘滞性）共同决定，而不是一个简单的布尔判断。
- 通读 `step()` 的真实实现，理解一次模型调用如何通过 `BlockAssembler` 组装、工具调用如何触发下一次 step 而不是下一次 turn。
- 理解 `Phase` 状态机（`idle` / `maintenance` / `running`）如何让"取消""唤醒重入""维护任务"这些并发场景不互相踩踏。

## 背景与设计动机

如果只看"Agent 要做的事"，最朴素的实现是一个 `while` 循环：读一条用户消息，发给模型，模型如果要调用工具就执行工具、把结果拼回上下文，再发一次模型，直到模型不再要求工具调用为止，然后等待下一条用户消息。

但真实系统里这个"朴素循环"要同时满足好几件在朴素版本里互相打架的需求：

- **用户中途插话（steering）**：模型还在执行工具时，用户又发来一条新消息，该在当前工具批次执行完后立刻处理，还是等到"整轮结束"？
- **多步 ReAct 但不重复开销**：一次工具调用之后模型往往需要再调用一次模型才能给出最终答案——这是"同一次交互"的延续，不应该被记成一次新的用户交互。
- **可恢复的粒度**：进程崩溃、网络中断后从哪里续上？如果只有一层"大循环"，恢复点的语义会很模糊。
- **可取消、可维护**：用户点了停止按钮，或者系统要在空闲期做一次会话压缩（compaction）之类的维护任务，这些操作需要一个明确的"当前状态"可查询、可等待。

`ReactLoopAgent` 用两层边界解决了这些问题：**turn** 是"一次用户可见的交互"，从 `turn/start` 到 `turn/end`，只要模型还有没执行完的工具调用、或者用户在此期间又发来了新的"steering"输入，这个 turn 就不结束；**step** 是"一次模型调用 + 它触发的工具执行"，是 ReAct 循环的最小单元。多步工具调用在 step 层展开，不产生新 turn；只有全新的、独立的用户输入才开一个新 turn。

## 核心机制详解

### 四层调用结构总览

```typescript
// packages/core/agent-loop/src/agent.ts
private async kick(): Promise<void> {
  try {
    while (await this.turn()) {}
  } catch (_error) {
    // Reported failures and cancellation are contained at the driver boundary.
  } finally {
    /* v8 ignore next -- kick owns a running phase until this driver boundary */
    if (this.phase.kind === 'running') {
      const { turn, wakeRequested } = this.phase
      this.setPhase({ kind: 'idle', lastTurn: turn })
      if (wakeRequested && this.inbox.hasPending) this.wakeDriver()
    }
  }
}
```

`kick()` 本身极其朴素——就是"反复 `turn()`，直到它返回 `false`"。真正复杂的逻辑都被推到了 `turn()` 内部：`turn()` 返回 `true` 表示"inbox 里还有排队消息，值得再开一个新 turn"；返回 `false` 表示"暂时没有更多要做的事了"。`kick()` 唯一要操心的是收尾：无论 `turn()` 正常结束还是抛出异常（取消、致命错误），`finally` 块都要把 `phase` 收回 `idle`，并且检查在这期间是否有"唤醒请求"被压后（`wakeRequested`）——如果有，且 inbox 确实还有东西，就立刻再开一轮 `wakeDriver()`。这是为了应对"driver 正在收尾的同时，外部又发来了一条新消息"的竞态。

调用链条因此是：

```
wakeDriver() → kick() → while(turn()) → turn() 内部 while 循环 → step() → buildRequest()
```

`turn()` 每一轮 while 循环对应一个 step；`step()` 内部还有一个更小的 `while (true)` 循环，专门用于"模型请求失败后由插件决定是否重试"（下一篇会展开）。`buildRequest()` 不是循环的一部分，而是 `step()` 每次发起请求前调用的纯组装函数，负责把会话历史、系统提示词、工具 schema 拼成一个不可变的 `GenerateOptions`。

### 谁触发 kick：Inbox 与 Phase 状态机

`ReactLoopAgent` 从不主动"轮询"——它完全是事件驱动的。触发点是 `Agent` 接口暴露的四个写入方法：

```typescript
// packages/core/agent-loop/src/agent.ts
send(message: UserMessage, target: InboxTarget, wakeup: boolean): void {
  const wakingAfterAbort = wakeup && this.phase.kind !== 'idle' && this.phase.abort.signal.aborted
  const resolvedTarget = wakingAfterAbort ? 'next-turn' : target
  this.inbox.splice(resolvedTarget, Infinity, 0, [message])
  if (wakeup) this.wakeDriver(wakingAfterAbort)
}

followup(input: UserMessage): void {
  this.send(input, 'next-turn', true)
}

steer(input: UserMessage): void {
  this.send(input, 'next-step', true)
}

inject(input: UserMessage): void {
  this.send(input, 'next-step', false)
}
```

四个方法本质上都是 `send()` 的不同参数组合，区别在于两件事：**放进哪个 inbox 队列**（`next-turn` 表示"作为独立的新一轮交互处理"，`next-step` 表示"塞进当前 turn 的下一个 step 里一起处理"）和**是否唤醒 driver**。`followup()` 是最常见的"用户发了一条新消息"——独立开新 turn 并唤醒；`steer()` 是"用户在模型思考/执行工具期间又插了一句话"——不开新 turn，塞进下一个 step，并唤醒；`inject()` 是"系统自己往上下文里加东西"（文件变更通知、定时任务提醒等），同样进 `next-step`，但不唤醒——如果 driver 当前是空闲的，这条注入会静静等到下一次 `followup`/`steer` 唤醒它才会被消费。

真正的调度逻辑在 `wakeDriver()`：

```typescript
// packages/core/agent-loop/src/agent.ts
private wakeDriver(wakeAfterAbort = false): void {
  if (this.phase.kind !== 'idle') {
    const reason = this.phase.abort.signal.reason as AgentCancelCause | undefined
    if (reason?.kind !== 'disposed' && (this.phase.kind === 'maintenance' || wakeAfterAbort)) {
      this.phase.wakeRequested = true
    }
    return
  }
  const driver = Promise.withResolvers<void>()
  this.activityDone = driver.promise
  this.setPhase({
    kind: 'running',
    abort: new AbortController(),
    turn: this.phase.lastTurn,
    step: 0,
    wakeRequested: false,
  })
  this.loopCtx.agents.withInitiator(this, () => this.kick()).then(driver.resolve, driver.reject)
}
```

只有当 `phase.kind === 'idle'` 时，`wakeDriver()` 才会真正启动一个新的 `kick()`。如果 agent 当前正在跑维护任务（`maintenance`）或者刚被取消但还没收尾完（`wakeAfterAbort`），唤醒请求会被"记账"到 `wakeRequested` 上，等到那个活动结束时再补一次唤醒；如果 agent 已经在正常运行（既非 idle 也非上述两种延迟场景），说明它自己会在下一个 step 边界主动去 `claim` inbox，不需要外部再插手。`Phase` 这个判别联合类型正是这套状态机的核心：

```typescript
// packages/core/agent-loop/src/agent.ts
type Phase =
  | { kind: 'idle'; lastTurn: number }
  | {
    kind: 'maintenance'
    abort: AbortController
    lastTurn: number
    wakeRequested: boolean
  }
  | { kind: 'running'; abort: AbortController; turn: number; step: number; wakeRequested: boolean }
```

三种状态里都携带 `lastTurn` 或 `turn`，保证"driver 结束时应该从哪个 turn 号继续"永远是可查询的；`running` 和 `maintenance` 都携带一个独立的 `AbortController`，这样 `cancel()` 可以精确地只打断当前这一次活动，而不会误伤下一次唤醒。

### turn()：一次用户可见交互的边界

```typescript
// packages/core/agent-loop/src/agent.ts（节选，省略部分注释）
private async turn(): Promise<boolean> {
  const phase = this.phase
  const { signal } = phase.abort
  const turn = phase.turn + 1
  this.session.append('turn/start', { turn })
  phase.turn = turn
  let turnEnds: TurnEndReason | null = null
  let target: InboxTarget = 'next-turn'
  try {
    while (true) {
      const step = phase.step + 1
      const decision = await this.preStep(target, { turn, step })
      if (decision.kind === 'reject') {
        turnEnds = { kind: 'blocked' }
        return false
      }
      if (turnEnds && decision.messages.length === 0) break
      if (phase.step === 0 && decision.messages.length === 0) {
        turnEnds = { kind: 'completed' }
        return false
      }
      this.session.append('step/start', { turn, step })
      phase.step = step
      try {
        for (const message of decision.messages) {
          this.session.append('user/message', message, { surfaceOp: 'append' })
        }
        const stepEnd = await this.step(decision.assembly)
        if (turnEnds === null || turnEnds.kind !== 'max-tokens') turnEnds = stepEnd
      } finally {
        this.session.append('step/end', { turn, step })
      }
      if (turnEnds && this.inbox.nextStep.length === 0) {
        await this.dispatch.serial('agent/turn-stopping', { turn, signal })
      }
      if (turnEnds && this.inbox.nextStep.length === 0) break
      target = 'next-step'
    }
  } finally {
    this.session.append('turn/end', { turn, reason: turnEnds! })
  }
  if (!this.inbox.hasPending) return false
  phase.abort = new AbortController()
  phase.wakeRequested = false
  phase.step = 0
  return true
}
```

拆开来看，`turn()` 内部有一个 `while (true)` 循环，每一轮先调用 `preStep()`（下一节展开）去认领 inbox 里排队的消息、组装系统提示词与动态上下文。`preStep` 的返回值有两种：`reject`（某个 `agent/pre-step` 监听器直接拒绝了这一步，比如权限审批未通过），此时 turn 以 `blocked` 收尾；`enter`（正常进入），携带这一步要喂给模型的 `messages`。

几个容易忽略但很关键的边界条件：

- **第一次唤醒但没有实际消息**：`phase.step === 0 && decision.messages.length === 0`——比如一条 steering 消息在还没被 claim 之前就被取消了——这个 turn 直接以 `completed` 收尾，且**不消耗一次模型调用**（"An enter decision rewritten to empty still owns the initial turn boundary, but it spends no model call"）。
- **max-tokens 的粘滞性**：`if (turnEnds === null || turnEnds.kind !== 'max-tokens') turnEnds = stepEnd`——一旦某个 step 因为触达输出 token 上限而结束，即使后续 step 正常 `completed`，turn 的最终结论也不会被"降级"覆盖掉。这保证了"这次交互曾经被截断过"这一事实不会在日志里丢失。
- **`agent/turn-stopping` 是否该真正停下由数据决定**：当 `turnEnds` 已经有结论、且 `inbox.nextStep` 里没有新消息时，`turn()` 才会去问一遍 `agent/turn-stopping` 这个 **serial**（严格顺序、可等待）钩子——它不是一个可以直接投票否决的钩子，想让 turn 继续的监听器要调用 `agent.steer(...)` 往 `next-step` 里塞一条新消息，`turn()` 之后会重新读一遍 inbox，只要发现有新东西就继续走下一轮 step。这是一处很讲究的设计：**监听器的调用顺序不能改变结果**，因为最终是不是继续完全取决于 inbox 里有没有数据，不取决于谁先谁后调用了 `steer`。

turn 结束后，`finally` 块无条件写一条 `turn/end` 事件——不管是正常完成、被拒绝、被取消还是抛出异常，这条收尾记录总会写下（异常路径见下一段）。最后，如果 inbox 里还有排队消息（比如用户在这个 turn 进行期间又发来了 `followup`），`turn()` 会重置一个新的 `AbortController` 并返回 `true`，`kick()` 的外层 `while` 循环就会立刻开始下一个 turn。

turn 的异常收尾同样值得一读：

```typescript
// packages/core/agent-loop/src/agent.ts
} catch (error: unknown) {
  if (signal.aborted) {
    turnEnds = { kind: 'aborted', reason: signal.reason as AgentCancelCause }
    throw error
  }
  turnEnds = {
    kind: 'error',
    error: error instanceof LlmError
      ? error.failure
      : { message: errorChain(error), code: 'UNKNOWN' },
  }
  this.throwError(error)
}
```

`TurnEndReason` 是一个 merge-extensible 的判别联合（定义在 `packages/core/session/src/types.ts` 的 `TurnEndReasonMap` 里，下一篇详细展开），涵盖 `completed`/`aborted`/`blocked`/`error`/`max-tokens`/`interrupted` 六种收尾方式——每一种都对应一类可以事后重放、审计的真实原因，而不是笼统的"成功/失败"。

### preStep()：认领消息、组装上下文、可被拦截

```typescript
// packages/core/agent-loop/src/agent.ts
private async preStep(target: InboxTarget, position: { turn: number; step: number }): Promise<PreparedStep> {
  const signal = this.phase.abort.signal
  const claimed = this.inbox.claim(target, position.turn)
  const assembly = await this.loopCtx.systemPrompt.assemble(assembleContextFor(this, signal))
  signal.throwIfAborted()
  const sections = renderContextSections(assembly)
  const context = this.runtimeContext.project(joinContextSections(sections), sections)
  const decision = await this.dispatch.waterfall(
    'agent/pre-step', { messages: claimed, ...position, signal },
    (): Promise<PreStepDecision> => Promise.resolve<PreStepDecision>({
      kind: 'enter',
      messages: context === undefined ? claimed : [...claimed, context],
    }),
  )
  signal.throwIfAborted()
  return decision.kind === 'reject' ? decision : { ...decision, assembly }
}
```

`preStep()` 做了三件事：从 `Inbox.claim()` 取出这一步真正要处理的消息（`target === 'next-turn'` 时，还会顺带取一条排队的独立 turn 输入）；组装系统提示词和"运行时上下文快照"（比如当前工作目录、时间等会变化的动态信息，由 `RuntimeContextProjection` 负责去重——只有内容真的变了才追加一条新的 `user/message`，见第二篇）；最后把这一切通过 `agent/pre-step` **waterfall**（洋葱模型中间件）钩子交给插件决定"是放行还是拦截"。这正是权限审批、compaction 触发（下一篇会讲 `compaction-basic` 就是挂在这个钩子上）等横切逻辑的挂载点。

### step()：一次模型调用与它触发的工具执行

```typescript
// packages/core/agent-loop/src/agent.ts（节选）
private async step(assembly: PromptAssembly): Promise<StepEndReason | null> {
  const { turn, step, abort: { signal } } = this.phase
  const system = renderPrompt(assembly)

  while (true) {
    const { request, preparedCall } = await this.buildRequest(
      turn, step, assembly.tools, system, this.session.deriveMessages(), signal,
    )
    const assembler = new BlockAssembler()
    const chunkSeqs: number[] = []
    const stream = preparedCall?.stream(request) ?? this.loopCtx.llm.stream(request)
    for await (const chunk of stream) {
      chunkSeqs.push(this.session.append('assistant/chunk', { turn, step, chunk }).seq)
      assembler.push(chunk)
    }
    const finish = assembler.finish
    if (finish.kind === 'error' || finish.kind === 'aborted') {
      const action = await this.dispatch.waterfall(
        'agent/request-error', { turn, step, provider: request.provider, failure: finish.failure,
          retryPolicy: preparedCall?.retryPolicy, signal },
        () => Promise.resolve<RequestErrorAction>(undefined),
      )
      if (action?.kind !== 'retry') {
        throw new LlmError(finish.failure.message, finish.failure.code, finish.failure)
      }
      continue
    }

    const message = createAssistantMessage({ content: assembler.blocks(), source: { /* ... */ } })
    this.session.append('assistant/message', { turn, step, message, /* usage */ },
      { surfaceOp: 'append', sourceEventSeqs: chunkSeqs })
    if (finish.kind === 'max-tokens') return { kind: 'max-tokens' }

    const toolCalls = message.content.filter(block => block.type === 'tool-call')
    if (toolCalls.length === 0) return { kind: 'completed' }
    const { concluded } = await executeToolCalls(
      this.loopCtx, turn, step, toolCalls, signal,
      context => this.inbox.splice('next-step', this.inbox.nextStep.length, 0, [context]),
    )
    return concluded ? { kind: 'completed' } : null
  }
}
```

`step()` 内部还有一层 `while (true)`——这一层只服务于"模型请求失败后，插件通过 `agent/request-error` 决定重试"（下一篇细讲），一次成功的请求会走到 `continue` 之外的正常路径然后 `return`。抛开重试逻辑，一次 step 的骨架是：`buildRequest()` 组装冻结的请求 → 用 `BlockAssembler` 消费流式 chunk（每个原始 chunk 都先落盘再喂给组装器，第三篇细讲）→ 组装出完整的 `AssistantMessage` 并落盘 → 如果这条消息里没有 `tool-call` 内容块，step 直接 `completed`；如果有，调用 `executeToolCalls()` 执行它们。

**这里就是"为什么工具调用不会产生新 turn"的答案**：`step()` 返回值只有三种——`{ kind: 'completed' }`、`{ kind: 'max-tokens' }`、或者 `null`。`null` 恰恰对应"工具执行完了，但没有一个工具结果显式声明 `concludesTurn: true`"，这意味着模型大概率还要针对工具结果再说点什么。`turn()` 外层循环看到 `step()` 返回 `null` 时，不会去开一个新 turn，而是把 `target` 切成 `'next-step'` 后继续同一个 `while` 循环，进入下一次 `preStep()` → `step()`。真正驱动"要不要再来一轮模型调用"的开关是 `concluded`：只要工具批次里任何一个结果携带 `concludesTurn: true`（比如"任务已完成，退出循环"类工具），`executeToolCalls` 就会返回 `concluded: true`，这一步就以 `completed` 收尾，turn 的外层循环再去检查 inbox、决定是否该收尾整个 turn。

### 为什么是两层而不是一层

把这一节的机制串起来看：

- **turn 层**回答的问题是"这轮用户可见的交互，什么时候算真正结束"——它需要知道 inbox 里是否还有排队的 steering 消息、是否要问一次 `agent/turn-stopping`、以及要不要把 `max-tokens` 这种"曾经被截断"的事实粘滞地带到最终结论里。这些都是**跨越多次模型调用**的状态。
- **step 层**回答的问题是"这一次模型调用本身该怎么被消费、它触发的工具调用怎么被执行、执行完之后要不要再喂给模型一次"——这些都是**单次模型调用局部**的逻辑，天然应该被抽成一个独立的函数，并且需要能在失败时原地重试（`step()` 内部的 `while` 循环）。

如果把两层揉进一个大循环，`max-tokens` 粘滞判断、`agent/turn-stopping` 钩子的调用时机、ReAct 多步的"继续同一个 turn 还是开新 turn"这几件事就会互相耦合，任何一处调整都容易牵连另一处。分成 `turn()` 和 `step()` 之后，`turn/start`、`turn/end`、`step/start`、`step/end` 四类事件在会话日志里天然形成了一个可以精确回放、精确定位"崩溃发生在哪个 turn 的哪个 step"的树状结构——这也是下一篇要讲的"会话事件溯源"的直接基础。

## 常见问题/易踩坑

- **`steer()` 和 `inject()` 的核心区别是"是否唤醒 driver"，不是"是否影响下一步"**——两者都进 `next-step` 队列，区别只在于 driver 处于 idle 时，`steer()` 会立刻唤醒它开始一个新 turn，而 `inject()` 会安静地等到别的唤醒发生。如果只调用 `inject()` 而 agent 一直 idle，这条消息可能永远不会被消费。
- **`Phase.wakeRequested` 是"延迟到活动结束才补发"的唤醒**，而不是"立刻打断当前活动"。真正的打断只能通过 `cancel()` 触发对应 `AbortController.abort()`。
- **`turn()` 返回 `false` 不代表这个 agent 从此不再工作**——它只代表"当前这一次 `kick()` 里已经没有更多 turn 可开了"，`kick()` 结束后一旦 inbox 又有新消息进来，新的 `wakeDriver()` 会重新触发新一轮 `kick()`。
