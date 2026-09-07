# Typed Events：四种派发模式与 waterfall 语义

> 服务方法调用要求调用方"认识"这个服务；而 dsh 里大量的拦截点——要不要放行一次工具调用、要不要重写这一步喂给模型的消息、请求失败了要不要重试——都需要"完全不认识对方、甚至不知道对方存不存在"的插件之间协作。Cordis 的 Typed Events 就是为这类协作设计的，而 `emit`、`parallel`、`serial`、`bail`、`waterfall` 五种派发模式的区别，本质上都是在回答同一个问题：多个监听器之间，谁等谁、谁能改谁的结果、谁能一票否决。

## 学习目标

- 分清 `emit`/`parallel`/`serial`/`bail`/`waterfall` 五种派发模式在"是否等待"、"派发顺序"、"是否有返回值"三个维度上的具体差异。
- 理解 waterfall 是"环绕式中间件"：监听器拿到的最后一个参数是 `next()`，调用它才会把控制权交给下一个监听器（或默认行为）。
- 记住 dsh 自己在 `AGENTS.md` 里明确写出的铁律——waterfall 监听器必须调用 `next()` 才能委托，不调用就是主动短路。
- 理解 Typed Events 依赖 TypeScript 声明合并（`interface Events`）才能让 `ctx.on`/`ctx.emit` 类型安全，并能在 dsh 真实源码里找到这种声明长什么样。
- 通读 dsh 真实的 `agent/pre-step` 和 `tools/pre-execute` 两个 waterfall 事件，从声明、真实派发点到真实监听器写法，走完一条事件的完整生命周期。

## 背景与设计动机

第一篇里 `session-stats` 插件通过 `inject` 直接拿到 `ctx.sessionProjections` 服务，调用它的 `register()` 方法——这是"直接调用"：调用方明确知道自己在跟谁打交道，方法签名是双方共同的契约。

但 dsh 里有一整类场景不适合这种模式。以工具执行流程为例：审批策略要在工具真正执行前决定"允许/拒绝/询问用户"，超时策略要包一层计时逻辑，观测策略要在结果出来后记一笔日志——这些策略插件彼此互不相识，甚至不知道对方是否被装配进了当前部署。如果用直接方法调用来实现，工具注册表就得写成"依次调用审批策略.check() → 超时策略.wrap() → 观测策略.record()"这种硬编码链条，新增一个策略插件就要去改这条链条本身。

Cordis 的答案是**事件**：工具注册表只负责在关键时刻广播一个事件（比如"这个调用即将执行"），不关心、也不需要知道谁在监听。任意数量的策略插件可以独立地挂上监听器，互相之间零耦合，注册表代码本身永远不用因为"多了一个策略"而改动。`docs/architecture.md` 把这条原则写进了"新行为该挂在哪里"的判断表里：

> Intercept a request, tool, or turn → use its `agent/*` or `tools/*` event

但"广播一个事件"本身不够——不同的拦截场景需要不同的协作语义。审批场景需要"任意一个监听器都能一票拒绝，且要等它异步判断完"；日志场景只需要"通知一下，不关心谁处理、也不用等"；重写请求配置的场景需要"每个监听器都能在前一个监听器处理完的基础上继续改"。这就是为什么 Cordis 不是只有一种 `emit`，而是提供了五种语义不同的派发模式。

## 核心机制详解

### 五种派发模式的语义对照

`docs/cordis-primer.md` 用一张表概括了四种主要模式（`bail` 是 `serial` 的同步版本，`docs/cordis-tutorial/04-events.md` 里补全为五种）：

| Mode | Awaited? | Dispatch Order | Has Return Value? |
|---|---|---|---|
| `emit` | No | listeners observe in registration order | No |
| `waterfall` | No（自身同步返回，但监听器可以是 async） | listeners observe in registration order | Yes |
| `parallel` | Yes | all listeners observe the event in parallel | No |
| `serial` | Yes | listeners observe in registration order | Yes |

对应的调用方法签名，来自 `docs/cordis-api/events.md`（源码 `vendor/cordis/src/events.ts`）：

```ts
// vendor/cordis/src/events.ts（docs/cordis-api/events.md 摘录）
/** Dispatch an event synchronously, ignoring listener return values. */
emit<K extends keyof Events>(name: K, ...args: Parameters<Events[K]>): void

/** Dispatch an event, running all listeners concurrently. */
parallel<K extends keyof Events>(name: K, ...args: Parameters<Events[K]>): Promise<void>

/** Dispatch an event, awaiting listeners in order until one bails. */
serial<K extends keyof Events>(name: K, ...args: Parameters<Events[K]>): Promisify<ReturnType<Events[K]>>

/** Dispatch an event, calling listeners in order until one bails. */
bail<K extends keyof Events>(name: K, ...args: Parameters<Events[K]>): ReturnType<Events[K]>

/** Dispatch an event whose last argument is a `next` continuation. */
waterfall<K extends keyof Events>(name: K, ...args: Parameters<Events[K]>): ReturnType<Events[K]>
```

选择哪种模式取决于你要回答的问题：

- **`emit`**——"通知一下就好，我不关心结果，也不等你处理完"。适合日志、遥测这类纯观察场景。
- **`parallel`**——"所有人都要处理完，但你们互不影响，我等你们全部完成"。适合多个互相独立的收尾动作。
- **`serial` / `bail`**——"按注册顺序依次问，谁先给出一个非 `null`/`false`/`undefined` 的答案，谁的答案就是最终结果，后面的不再问"。适合"多个候选人抢答，第一个接受的赢"的场景。`bail` 是它的同步版本。
- **`waterfall`**——"每个人都在前一个人的结果基础上继续加工，谁都可以选择'到此为止，我来决定最终结果'"。适合审批、拦截、重写这类"层层设卡"的场景，本篇下面重点展开。

### 声明合并：让 `ctx.on` / `ctx.emit` 类型安全

和第一篇的 `interface Context` 一样，事件也需要一段声明合并才能让 TypeScript 知道某个事件名字对应什么参数和返回类型。`docs/cordis-tutorial/04-events.md` 给出了一个最小可运行的例子：

```ts
// docs/cordis-tutorial/04-events.md
declare module '@deepseek-ai/cordis' {
  interface Context {
    stats: StatsService
  }
  interface Events {
    'stats/report'(name: string, count: number): void
  }
}
```

这一段声明合并的价值在于：写下 `ctx.emit('stats/report', name, next)` 或者 `ctx.on('stats/report', (name, count) => {...})` 时，TypeScript 会强制校验事件名字拼写正确，且回调函数的参数类型必须匹配。如果一个包只想使用另一个包声明的事件，却不想在运行时依赖它（比如没有把它放进 `inject`），教程给出的做法是一句不产生任何运行时效果的类型导入：

```ts
// docs/cordis-tutorial/04-events.md
import type {} from './stats.ts'
```

dsh 真实代码里的声明合并比教程例子更严格：每个事件的 JSDoc 都必须标注 `@mode` 标签，说明它究竟是用哪种模式派发的。`packages/core/agent/src/runtime-types.ts` 里 `agent/pre-step` 的真实声明：

```ts
// packages/core/agent/src/runtime-types.ts
interface Events {
    /**
     * Reject a proposed step or replace the messages that enter it. Calling
     * `next()` preserves the current messages.
     * @param payload.agent - the agent proposing the step.
     * @param payload.messages - messages removed from the inbox for this step.
     * @param payload.turn - the turn that will own the step.
     * @param payload.step - the step proposed by the loop.
     * @param payload.signal - the current turn's cancellation signal.
     * @mode waterfall
     */
    'agent/pre-step'(
      this: Scoped<Agent>,
      payload: { agent: Agent; messages: UserMessage[]; turn: number; step: number; signal: AbortSignal },
      next: () => Promise<PreStepDecision>,
    ): Promise<PreStepDecision>
}
```

这条 `@mode waterfall` 标签不是纯文档装饰——`docs/cordis-primer.md` 提到"生成的目录会核对声明和实际派发点是否一致"（"the generated catalog can check declarations against dispatch sites"），也就是说文档和代码之间有一条自动校验的链路，防止文档漂移。

### waterfall 深入：环绕式中间件与 `next()`

`waterfall` 是本章要重点吃透的一种模式，因为它承担了 dsh 里几乎所有"拦截/重写"场景。`docs/cordis-primer.md` 给出了精确的语义描述：

> `ctx.waterfall` is around-middleware. A listener receives `(...args, next)`. Call `next()` to delegate the possibly wrapped result to the next service; return without `next()` to short-circuit. Values propagate through `next()`'s return value.

用 `docs/cordis-tutorial/04-events.md` 的最小例子直观感受一下这个"环绕"结构：

```ts
// docs/cordis-tutorial/04-events.md
declare module '@deepseek-ai/cordis' {
  interface Events {
    'demo/transform'(input: string, next: () => Promise<string>): Promise<string>
  }
}

export function apply(ctx: Context) {
  // Listener 1: wrap the downstream result.
  ctx.on('demo/transform', async (input, next) => {
    const downstream = await next()
    return downstream.toUpperCase()
  })

  // Listener 2: short-circuit when it owns the decision.
  ctx.on('demo/transform', async (input, next) => {
    if (input.includes('blocked')) return '** blocked **'
    return next()
  })

  void (async () => {
    console.log(await ctx.waterfall('demo/transform', 'hello', async () => 'hello'))
    console.log(await ctx.waterfall('demo/transform', 'blocked words', async () => 'blocked words'))
  })()
}
```

运行结果是：

```
HELLO
** BLOCKED **
```

拆开第二行走一遍调用栈：监听器 1 先执行，它调用 `next()`，这一步会调用监听器 2；监听器 2 发现输入包含 `blocked`，**不调用 `next()`**，直接返回替换文本——传给 `ctx.waterfall` 的默认函数（"最内层的默认行为"）根本没有机会执行；监听器 1 拿到监听器 2 返回的替换文本后，在它经过自己身边的这一刻把它转成大写。教程把这套行为总结成一条铁律：

> a waterfall listener that only observes or annotates must call `next()`; returning without it is a deliberate short-circuit. Forgetting `next()` in a logging listener silently swallows the default behavior for everyone downstream.

这条铁律在 dsh 自己的 `AGENTS.md` 里被写成了仓库级别的强制规范，而不只是文档建议：

> **Waterfall listeners MUST call `next()`** to delegate; returning without it short-circuits the chain.

之所以要写成铁律，是因为这个坑极其隐蔽：一个只想"记一笔日志"的监听器，如果忘了在回调最后写 `return next()`，表面上什么错误都不会抛出，但它背后的默认行为、以及注册在它之后的所有监听器都会被静默吞掉——这在生产环境里排查起来非常痛苦，因为现象只是"某个功能诡异地不生效了"，看不到任何报错。

### 真实案例一：`agent/pre-step` 的派发与拦截

`agent/pre-step` 是 dsh Agent 循环里"模型即将看到什么消息"的拦截点。真实的派发代码在 `packages/core/agent-loop/src/agent.ts`：

```ts
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

这里的第三个参数就是 waterfall 的"最内层默认行为"：如果没有任何插件监听 `agent/pre-step`，或者所有监听器都乖乖调用了 `next()`，最终的决策就是"进入这一步，消息是刚从收件箱取出的消息加上渲染好的上下文"。任何插件只要挂一个监听器，就能在这个默认行为的基础上追加内容、或者整个拒绝这一步。

`packages/core/agent-loop/tests/interception.spec.ts` 里有一段专门写来演示"native hook 插件本质上就是一个挂在这些事件接缝上的普通 Cordis 插件"的示例，值得完整看一遍，因为它一次性展示了三个不同的拦截点：

```ts
// packages/core/agent-loop/tests/interception.spec.ts
const NativeGuard = {
  name: 'native-guard',
  apply(ctx: Context) {
    // 1. SessionStart: seed a standing instruction.
    ctx.on('agent/session-start', ({ agent, source }) => {
      agent.inject(createUserMessage({
        content: [{ type: 'text', text: `policy active (started: ${source})` }],
        source: { kind: 'plugin', plugin: 'native-guard' },
      }))
    })
    // 2. PreStep: reject a forbidden prompt, annotate the rest.
    ctx.on('agent/pre-step', async ({ messages }, next): Promise<PreStepDecision> => {
      const text = messages.flatMap(message => message.content)
        .map(b => (b.type === 'text' ? b.text : '')).join('')
      if (text.includes('rm -rf')) {
        return { kind: 'reject' }
      }
      return next()
    })
    // 3. PreToolUse: deny a dangerous tool by name.
    ctx.on('tools/pre-execute', async (exec, next): Promise<PreToolDecision> => {
      if (exec.name === 'danger') return { kind: 'deny', reason: 'danger tool denied' }
      return next()
    })
    // 4. PostToolUse: attach context after a tool runs.
    // ...
  },
}
```

这段代码印证了本章的核心论点：所谓"钩子系统"，在 Cordis 里根本不需要一套专门的 hook 协议或者外部命令通道——它就是一个普普通通的插件，`apply(ctx)` 里挂几个 `ctx.on(...)`。第 2 步的写法完美示范了铁律：命中危险模式时直接 `return { kind: 'reject' }`（短路，不调用 `next()`）；没命中时必须 `return next()`（委托），少写这一行，后续所有监听器和默认行为都会被吞掉。

### 真实案例二：`tools/pre-execute` 权限拦截

`tools/pre-execute` 是工具真正执行前的最后一道闸门，声明在 `packages/core/tools/src/index.ts`：

```ts
// packages/core/tools/src/index.ts
interface Events {
  /**
   * Allow, deny, or ask before dispatch. `next()` delegates to allow; missing
   * approval support turns `ask` into denial. Async gates must observe
   * `exec.signal`; the registry rechecks cancellation after they settle but
   * never abandons their promise.
   * @param exec - the pending call (name, parsed arguments, caller agent).
   * @mode waterfall
   */
  'tools/pre-execute'(this: Scoped<ToolRuntime>, exec: ToolExecution, next: () => Promise<PreToolDecision>): Promise<PreToolDecision>
}
```

`packages/core/agent-loop/tests/interception.spec.ts` 里一个更完整的端到端测试展示了它在真实调用链路里的效果——注册一个"危险工具"，再挂一个监听器拒绝它，断言模型最终看到的是一条 `isError: true` 的工具结果，而不是工具真的被执行了：

```ts
// packages/core/agent-loop/tests/interception.spec.ts
describe('tools/pre-execute gate (native-plugin permission pattern, end-to-end through the loop)', () => {
  it('deny short-circuits dispatch into an isError result the model sees', async () => {
    const adapter = new MockAdapter([toolCallResponse('c1', 'danger', {}), textResponse('ok')])
    const ctx = await harness(adapter)
    let ran = false
    ctx.tools.register(defineContentToolFixture({
      name: 'danger', description: 'danger', parameters: {},
      async execute() { ran = true; return [{ type: 'text', text: 'should not run' }] },
    }))
    const agent = ctx.agentLoop.create(SessionId('a1'), { provider: 'mock', model: 'mock' })

    ctx.on('tools/pre-execute', async (exec, next): Promise<PreToolDecision> => {
      if (exec.name === 'danger') return { kind: 'deny', reason: 'blocked dangerous tool' }
      return next()
    })

    send(agent, 'go')
    await waitForIdle(ctx, agent)

    expect(ran).toBe(false)
    const result = events(agent).find(e => e.type === 'tool/result')
    expect(result?.type === 'tool/result' && result.data.message.content[0].isError).toBe(true)
  })
})
```

`ran` 最终是 `false` 证明工具体本身从未被调用——`deny` 决策在真正的执行代码前就短路掉了整条链路，这正是 waterfall 模式"由数据决定结果，而不是由监听器顺序决定结果"的具体体现：只要某一个监听器决定 `deny`，无论它挂载的先后顺序，结果都是一致的拒绝。

## 常见问题/易踩坑

- **忘记调用 `next()`**：如前所述，这是 waterfall 场景下最隐蔽的错误，表现为"某个功能诡异地失效了但没有任何报错"。写 waterfall 监听器时，先问自己"这次调用我是要接管决策，还是只是路过看一眼"，前者才允许省略 `next()`。
- **把 `emit` 当成"广播后能拿到处理结果"**：`emit` 的返回类型是 `void`——即使监听器返回了 Promise 或者某个值，调用方也拿不到、也不会等它完成。需要收集结果或者等待完成，应该用 `parallel`（不需要结果）或 `serial`（需要按顺序抢答出一个结果）。
- **声明合并写少了 `@mode`**：dsh 的仓库规范要求每个新增事件的 JSDoc 都带 `@mode` 标签并且和实际派发方法（`ctx.emit`/`ctx.waterfall`/…）保持一致，生成的文档目录会做一致性校验——写事件声明时把这个标签当成强制字段，而不是可选注释。

## 小结

Typed Events 解决的是"互不相识的插件之间如何协作"这个问题：`emit` 是单向广播，`parallel`/`serial`/`bail` 面向"多个独立处理者各自反馈"或"多个候选人抢答"的场景，`waterfall` 面向"层层设卡、每一层都能在前一层基础上继续加工或者直接一票否决"的拦截场景。声明合并（`interface Events`）是让这套动态调度在编译期依然类型安全的机制，它本身不产生任何运行时代码。dsh 真实的 `agent/pre-step` 和 `tools/pre-execute` 两条链路证明了这套机制在生产代码里的样子：声明处有精确的 `@mode` 标注，派发处把"默认行为"作为 waterfall 的最内层函数传入，监听处严格遵守"接管就短路、路过就 `next()`"的铁律。

下一篇《Registrations are Effects》会回答一个自然会浮现的问题：`ctx.on(...)` 挂上去的这些监听器，插件被卸载的时候去哪儿了？答案就是本章反复出现的那个词——effect。
