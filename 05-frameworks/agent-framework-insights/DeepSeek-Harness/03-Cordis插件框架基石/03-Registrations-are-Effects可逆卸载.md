# Registrations are Effects：可逆的注册与卸载

> dsh 的 `AGENTS.md` 里有一条只用一句话概括的架构原则："Registrations are effects：every contribution goes through `ctx.effect()` / `ctx.on()`；a registry's `register()` returns the disposer。"这句话背后是一整套让"卸载一个插件"这件事变得绝对安全的机制——不管这个插件注册过多少个工具、挂过多少个监听器、起过多少个定时器，卸载时全部原样撤销，不多不少，不留垃圾状态。本篇拆开这套机制，并用一个真实的 HMR-safety 测试证明它确实做到了。

## 学习目标

- 理解 `ctx.effect()` 的契约：立即执行一段代码，收集它产生的清理函数（disposer），在卸载时统一回收。
- 理解 Fiber 状态机（`PENDING → LOADING → ACTIVE → UNLOADING → DISPOSED`）以及 `dispose()` 到底等到什么时候才算完成。
- 认识到 `ctx.on()`、`ctx.plugin()`、以及 dsh 各个注册表的 `register()` 方法**本身就是** effect 的封装，而不是需要额外手写 `ctx.effect()` 的特例。
- 知道"注册即副作用"这条原则解决的三个真实问题：热重载、测试隔离、子代理/多会话场景下的干净拆除。
- 读懂并能自己写出 dsh 规范要求的"HMR-safety 测试"：卸载贡献者插件的 Fiber，断言它的贡献被完整撤销。

## 背景与设计动机

先想象一个反面案例。假设一个插件在 `apply(ctx)` 里做了这些事：往工具注册表里塞了一个工具、订阅了一个事件、起了一个 `setInterval` 心跳。如果这个插件要被卸载——可能是因为配置热重载换了一个新版本，可能是因为一次单元测试结束后要清理现场，可能是因为一个子代理会话结束需要回收它专属的能力集合——谁来负责把这三件事全部撤销？如果答案是"卸载逻辑要挨个手写"，那么这份卸载代码永远会滞后于新增的注册代码：新加一个订阅，忘了在卸载里对应加一行注销，就是一个内存泄漏或者残留监听器的 bug，而且往往只在长时间运行或者反复热重载后才会暴露出来。

Cordis 的答案是把"注册"这个动作本身重新定义成"registration is an effect"：**任何通过 `ctx.effect()`（或者内部已经用它包装的 API，比如 `ctx.on()`、`ctx.plugin()`）做的贡献，天然携带一个撤销它的手柄，这个手柄被自动绑定到发起注册的那个插件实例（Fiber）上**。插件作者不需要记住"我注册了什么，所以我要在某处注销什么"——只需要用 Cordis 提供的 API 去注册，撤销就是免费的、自动的。

这个设计在 dsh 里直接服务于三个真实场景：

1. **热重载（HMR）**：`@deepseek-ai/cordis-plugin-hmr` 监听文件改动，卸载旧插件、加载新代码——如果旧插件的注册不能被干净撤销，热重载后系统里会同时存在"旧工具的残留注册"和"新工具的注册"，行为诡异且难以复现。
2. **测试隔离**：dsh 的测试大量依赖"创建一个 Context，加载被测插件，断言行为，然后 dispose 掉整个 Fiber 树"这套模式——如果 dispose 不能保证清空所有副作用，测试之间就会互相污染。
3. **子代理/多会话隔离**：一个会话结束、一个子代理完成任务，它专属的工具集合、提示词片段、事件监听都要被干净地拆掉，不能影响其他仍在运行的会话。

## 核心机制详解

### `ctx.effect()` 的契约

`docs/cordis-api/fiber.md`（源码 `vendor/cordis/src/fiber.ts`）给出了这个方法的精确契约：

```ts
// vendor/cordis/src/fiber.ts（docs/cordis-api/fiber.md 摘录）
/**
 * Register a cleanup-aware effect on this fiber.
 *
 * `execute` runs immediately; the disposers it produces are collected and
 * run (in reverse order) either when the returned disposer is called or
 * when the fiber unloads, whichever comes first. Calling the disposer twice
 * is a no-op. Throws `CordisError('INACTIVE_EFFECT')` if the fiber is
 * already disposed, and `TypeError` if `execute` returns an invalid shape.
 *
 * @param execute — the effect body; see {@link Effect} for accepted shapes.
 * @returns a disposer that tears the effect down and settles once done.
 */
effect(execute: () => SyncEffect, label?: string): Disposable<Promise<void>>
effect(execute: () => Effect, label?: string): AsyncDisposable<Promise<void>>
```

拆开这段契约的三个关键点：

- **`execute` 立即运行**：`ctx.effect(fn)` 不是"注册一个稍后才执行的回调"，`fn` 会在调用 `ctx.effect` 的这一刻就同步执行。
- **返回值决定清理动作**：`fn` 返回的（或者 Promise resolve 出的）函数会被收集起来，在"卸载时"或者"手动调用 effect 返回的那个撤销函数时"执行——二者谁先发生就先触发。
- **清理按逆序执行**：如果一个 Fiber 注册了多个 effect，卸载时会按照和注册顺序相反的顺序去清理——这和很多语言里 `defer`/析构函数的直觉是一致的：后申请的资源先释放。

`vendor/cordis/src/fiber.ts` 里 `effect()` 实现的核心片段印证了"收集 disposer、逆序清理"这句话不是文档修饰，而是真实代码行为：

```ts
// vendor/cordis/src/fiber.ts
const disposables: Disposable[] = []
let disposing = false
let disposalTask: void | Promise<void>
const dispose = () => {
  if (disposing) return disposalTask
  disposing = true
  let task!: void | Promise<void>
  for (const disposable of disposables.splice(0).reverse()) {
    if (task) {
      task = task.then(() => runDisposable(disposable))
    } else {
      const result = runDisposable(disposable)
      if (isObject(result) && 'then' in result) {
        task = result as any
      }
    }
  }
  return disposalTask = task
}
```

`disposables.splice(0).reverse()` 这一行就是"逆序清理"的字面实现；`disposing` 这个标志位保证了"调用两次撤销函数是空操作"这条契约。`docs/cordis-tutorial/02-lifecycle-and-effects.md` 补充了一条容易被忽视的排序细节：

> disposers start in reverse registration order, but multiple **async** disposers run concurrently. If teardown steps must run in sequence, keep them in one disposer and await them there.

也就是说"逆序"只保证**启动顺序**是逆序的，如果多个清理函数都是异步的，它们实际完成的先后顺序并不保证严格逆序——需要严格顺序的清理步骤，应该写在同一个 disposer 里手动 `await`。

用教程里的心跳例子直观感受一下这套契约：

```ts
// docs/cordis-tutorial/02-lifecycle-and-effects.md
function heartbeat(ctx: Context) {
  console.log('heartbeat plugin loading')
  ctx.effect(() => {
    const timer = setInterval(() => console.log('tick'), 200)
    return () => {
      clearInterval(timer)
      console.log('heartbeat cleaned up')
    }
  })
}

export function apply(ctx: Context) {
  const fiber = ctx.plugin(heartbeat)
  ctx.effect(() => {
    const timer = setTimeout(async () => {
      await fiber.dispose()
      console.log('disposed')
      process.exit(0)
    }, 700)
    return () => clearTimeout(timer)
  })
}
```

`setInterval` 是 Cordis **完全不知道**的资源——没有任何内建机制会自动清理它。`ctx.effect()` 存在的意义正是把这类"框架管不到"的资源包一层：申请资源、返回释放函数，剩下的事交给 Fiber 的生命周期。运行输出会依次打印 `heartbeat plugin loading` → 三次 `tick` → `heartbeat cleaned up` → `disposed`，`heartbeat cleaned up` 一定发生在 `disposed` 之前——因为 `fiber.dispose()` 是一个会等待清理完成才 resolve 的异步操作，下一节展开讲这一点。

### Fiber 状态机

每个被加载的插件实例都有一个对应的 Fiber，`docs/cordis-tutorial/02-lifecycle-and-effects.md` 给出了它的状态迁移图：

```
PENDING → LOADING → ACTIVE → UNLOADING → DISPOSED
                 ↘ FAILED
```

- **PENDING**——已声明，但 `inject` 要求的某个服务还不存在。这是第一篇提到的"插件什么都没打印也没报错"的正常状态，不是异常。
- **LOADING / ACTIVE**——`apply` 正在执行 / 已经执行完成。
- **FAILED**——`apply` 本身抛错，或者配置校验没通过。
- **UNLOADING / DISPOSED**——清理函数正在执行 / 全部清理完毕。

`fiber.dispose()` 的契约（`docs/cordis-api/fiber.md`）是"卸载插件，然后等清理彻底完成才 resolve"：

```ts
// vendor/cordis/src/fiber.ts（docs/cordis-api/fiber.md 摘录）
/** Dispose this fiber: unload the plugin, then settle once cleanup finished. */
public readonly dispose: () => Promise<void>
```

`vendor/cordis/src/fiber.ts` 里 `_unload()` 的真实实现印证了这一点——它会等待这个 Fiber 收集到的**所有** disposer（包括异步的）全部结束，任何一个 disposer 抛错都不会阻塞其他 disposer，而是记录到日志里：

```ts
// vendor/cordis/src/fiber.ts
private async _unload() {
  await Promise.all(this._disposables.clear().map(async (dispose) => {
    try {
      await composeError(async (info) => {
        await Promise.resolve()
        info.error = new Error()
        await runDisposable(dispose)
      }, this._runner.getOuterStack)
    } catch (reason) {
      this.ctx.logger.error(reason)
    }
  }))
  this.store = undefined
  // ...
}
```

`docs/cordis-tutorial/02-lifecycle-and-effects.md` 还补充了一条对于理解"子插件"很关键的语义：`fiber.dispose()` 会"递归卸载它挂载的任何子插件"（"recursively unloads any child plugins it mounted"）——一个插件通过 `ctx.plugin(child)` 挂载的子插件，本身就是一个 effect（挂载即注册、卸载即撤销），所以整棵插件子树的拆除只需要 dispose 根节点。

### 内建 API 天然是 effect

`docs/cordis-tutorial/02-lifecycle-and-effects.md` 明确指出，日常写插件时几乎不需要手写 `ctx.effect()`，因为常用的注册 API 内部已经用它包装好了：

> You rarely write `ctx.effect()` yourself, because the built-in registration APIs are effects already:
> - `ctx.on(event, listener)` — the listener is removed on unload.
> - `ctx.plugin(child)` — the child is disposed with its parent.
> - Service registrations are effects. Harness registries such as `ctx.tools.register(...)` also attach their returned disposers to the calling plugin, so they unwind automatically.

第一篇结尾看到的 `dsh-tools` 的 `register()` 方法，内部正是这样实现的（`packages/core/tools/src/index.ts`）：

```ts
// packages/core/tools/src/index.ts
/**
 * Register globally or in the calling agent scope. Scoped tools shadow
 * globals; duplicates within one layer and the reserved `run_code` name fail.
 * @returns the exact disposer that unregisters the tool.
 */
register(definition: ToolDefinition): () => void {
  const name = definition.name
  // ...省略参数校验...
  return this.layers.effect(
    this.ctx,
    layer => layer.tools.insert(name, definition),
    { label: 'tools.register()' },
  )
}
```

`this.layers.effect(this.ctx, ...)` 是 `dsh-tools` 内部对 `ctx.effect()` 的一层封装（附带一个 `label`，用于诊断），但本质就是把"往内部层级结构里插入一条工具定义"包成一个 effect，绑定在调用 `register()` 时的当前 Fiber 上。这也解释了第一篇 `session-stats` 插件里那句注释的准确含义：

> the registration is an effect on this plugin's fiber, so unloading removes the key

调用方完全不需要知道 `register()` 内部具体怎么实现 effect，只需要知道**它返回的那个函数就是撤销手柄**——`packages/AGENTS.md` 把这一点写成了仓库规范：

> **Registry contributions prove disposal** through the HMR-safety test required by testing policy: dispose the fiber and observe removal.

### 真实案例：HMR-safety 测试

`docs/testing.md` 把这条规范讲得非常具体，而不是空泛的"记得测试"：

> Every registry gets an HMR-safety test (dispose the contributing fiber, assert cleanup).

`packages/core/tools/tests/tools.spec.ts` 里就有一个完全符合这条规范描述的真实测试，标题直接写明了它验证的是什么：

```ts
// packages/core/tools/tests/tools.spec.ts
it('rejects duplicate names and unregisters on fiber dispose (HMR safety)', async () => {
  const ctx = await setup()
  ctx.tools.register(echoTool)
  expect(() => ctx.tools.register(echoTool)).toThrow('already registered')

  const fiber = await ctx.plugin(Object.assign((inner: Context) => {
    inner.tools.register({ ...echoTool, name: 'scoped' })
  }, { inject: ['tools'] }))
  expect(ctx.tools.schemas().map(t => t.name)).toEqual(['echo', 'scoped'])

  await fiber.dispose()
  expect(ctx.tools.schemas().map(t => t.name)).toEqual(['echo'])
})
```

逐段解读这个测试在做什么：

1. 先在根 Context 上注册一个 `echo` 工具，顺手验证"重复注册同名工具会报错"这条边界行为。
2. 用 `ctx.plugin(...)` 挂载一个**子插件**，这个子插件在自己的 `apply` 里又注册了一个叫 `scoped` 的工具——这一步拿到的 `fiber` 就是这个子插件专属的运行时句柄。
3. 断言此时全局工具列表是 `['echo', 'scoped']`——两个工具都在。
4. **核心断言发生在这里**：`await fiber.dispose()`，只卸载刚才那个子插件，不碰根 Context。
5. 再次读取工具列表，此时变成了 `['echo']`——`scoped` 工具随着它的贡献者 Fiber 一起消失了，而 `echo` 因为是在根 Fiber 上注册的，完全不受影响。

这个测试没有写任何手动清理代码，`scoped` 工具的消失完全是 `ctx.tools.register()` 内部 effect 封装自动触发的结果——这正是"注册即副作用"原则要证明的东西：**注册者是谁，卸载谁的 Fiber，谁的贡献就消失，且仅消失这一份贡献**。同一份测试文件里紧接着还有一个更直白的例子，验证 `register()` 返回值本身就是可调用的撤销函数：

```ts
// packages/core/tools/tests/tools.spec.ts
it('returns a callable disposer from register() that unregisters the tool', async () => {
  const ctx = await setup()
  ctx.tools.register(echoTool)

  const dispose = ctx.tools.register({ ...echoTool, name: 'disposable' })
  expect(ctx.tools.schemas().map(t => t.name)).toEqual(['echo', 'disposable'])

  dispose()
  expect(ctx.tools.schemas().map(t => t.name)).toEqual(['echo'])
})
```

两个测试合起来说明：撤销一份注册有两条等价路径——要么直接调用 `register()` 返回的撤销函数，要么卸载发起这次注册的整个 Fiber。后者是前者的"批量版本"：一个 Fiber 在其生命周期内做过的所有注册，会随着这个 Fiber 被 dispose 而一次性、按逆序全部撤销。

## 常见问题/易踩坑

- **绕开 Cordis API 直接持有资源**：如果一个插件里直接 `setInterval(...)` 或者手动往某个第三方库的事件总线上 `addListener(...)`，却没有用 `ctx.effect()` 包一层，这份资源永远不会随插件卸载而释放——这正是心跳例子存在的意义，凡是 Cordis 管不到的资源，都需要开发者自己用 `ctx.effect()` 显式声明。
- **误以为"逆序"是严格串行的保证**：多个 disposer 中若混有异步操作，只有**启动**顺序是逆序的，实际完成时间不保证严格逆序；需要严格先后关系的清理步骤要写进同一个 disposer 里手动 `await`。
- **给注册表新增能力时忘记写 HMR-safety 测试**：`packages/AGENTS.md` 把这条列为规范而不是建议——任何新增的"注册表"（拥有 `register()`/`insert()` 之类方法、允许其他插件往里贡献内容的服务）都应该配一个"卸载贡献者 Fiber、断言内容消失"的测试，这是证明该注册表遵守了"注册即副作用"原则的唯一方式。

## 小结

"Registrations are effects" 把插件卸载从一件需要手写清理代码、容易遗漏的苦活，变成了框架层面的默认行为：`ctx.effect()` 是最底层的原语——立即执行、收集 disposer、逆序清理；`ctx.on()`、`ctx.plugin()`，以及 dsh 各个注册表的 `register()` 方法都是对它的封装，调用方拿到的返回值本身就是撤销手柄。真实的 HMR-safety 测试（`packages/core/tools/tests/tools.spec.ts`）用最直接的方式证明了这套契约：卸载贡献者的 Fiber，它贡献的内容精确地消失，其他 Fiber 的贡献毫发无损。

这条原则也是本章最后一篇要讲的"Profile / Bundle / Preset 装配机制"能够成立的前提——一个会话结束时要拆掉它专属的整套 Agent 组合、一个热重载要替换某一层补丁而不影响其他层，靠的都是同一套"注册即副作用"的基础设施。
