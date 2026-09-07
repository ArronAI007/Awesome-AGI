# 核心概念：Context、Service、Plugin

> Cordis 不是一个"启动脚本 + 依赖注入容器"的常规组合，而是把整个应用本身建模成一棵可增删的插件树：每个插件声明它提供什么、需要什么，框架据此自动算出谁先启动、谁后启动。dsh 的模型适配器、工具注册表、会话日志、甚至 Agent 循环本身，全部是挂在这棵树上的插件——没有一处是"框架核心不可替换的部分"。

## 学习目标

- 理解 Cordis 里 Plugin 的三种合法形态（函数、对象、`Service` 子类），以及它们各自适用的场景。
- 理解 Context 作为"服务仓库"的本质：`ctx.<key>` 是怎么从一个 Proxy 读取到具体服务实例的。
- 理解 `inject` 声明依赖的机制：一个插件如何声明它需要哪些服务才能启动，Cordis 又如何据此自动排出加载顺序，而不是靠 `cordis.yml` 里的书写顺序。
- 通读 dsh 仓库里两个真实的、体量很小的插件实现，建立"一个完整插件长什么样"的具体印象。
- 知道 `declare module` 声明合并在这里解决的编译期问题，以及它在运行时其实"什么都不做"这件容易被误解的事实。

## 背景与设计动机

设想没有 Cordis 会怎样。一个 Agent Harness 至少要装配：模型适配器、工具注册表、会话持久化、沙箱策略、审批流程、遥测……如果这些能力用普通的 `import` + 手写初始化函数拼在一起，你很快会撞上两类问题：

第一类是**启动顺序的手工维护**。工具注册表要在系统提示词组装器之后启动（因为它要往提示词里塞工具 schema），审批流程要在工具注册表之后启动。这些依赖关系一旦超过五六个模块，手写的启动顺序表就会变成一份没人敢改的脆弱清单——改错顺序，轻则某个服务读到 `undefined`，重则整个进程在启动时崩溃。

第二类是**能力的不可替换性**。如果"用 SQLite 存会话"和"用本地文件系统存会话"是两份分别写死在初始化代码里的实现，想要换一个持久化后端，就得去改调用方的每一处引用。

Cordis 用一个统一的答案解决了这两类问题：**每个能力都以服务名字的方式存在于 Context 中，插件用 `inject` 声明它需要哪些服务名字，Cordis 自动解析谁先谁后**。调用方永远只认"这里有一个叫 `tools` 的服务"，不认"这个服务具体是哪个类的实例"——`docs/cordis-primer.md` 把这条原则概括成一句话：

> A context is a repository of services... other plugins find services via key instead of importing a concrete implementation.

这也是 `docs/architecture.md` 敢说"没有特权核心可以打补丁"的底气：dsh 的模型适配器、Agent 循环、会话日志全部是插件，替换任何一层都不需要碰调用方代码。

## 核心机制详解

### 插件的三种形态

Cordis 接受三种写法作为"一个插件"，`docs/cordis-tutorial/01-first-plugin.md` 给出了并排对照：

```ts
// docs/cordis-tutorial/01-first-plugin.md
import { Service, type Context } from '@deepseek-ai/cordis'

// 1. Function plugin (what you just wrote).
export function apply(ctx: Context) {}

// 2. Object plugin: an object with an `apply` method.
export const objectPlugin = {
  name: 'object-plugin',
  apply(ctx: Context) {},
}

// 3. Class plugin: a Service subclass (covered in chapter 3).
export class MyService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'myTutorialService')
  }
}
```

三种形态在 Cordis 内部被统一抽象成 `Plugin` 类型（`vendor/cordis/src/registry.ts`）：

```ts
// vendor/cordis/src/registry.ts
/** Supported plugin entrypoint shapes. */
type Plugin<T = any> =
  | Plugin.Function<T>
  | Plugin.Constructor<T>
  | Plugin.Object<T>

namespace Plugin {
  export interface Base<T = any> {
    name?: string
    Config?: StandardSchemaV1<any, T>
    inject?: Inject
    provide?: string | string[]
    intercept?: Dict<boolean>
  }
  export interface Function<T = any> extends Base<T> {
    (ctx: Context, config: T): any
  }
  export interface Constructor<T = any> extends Base<T> {
    new (ctx: Context, config: T): any
  }
  export interface Object<T = any> extends Base<T> {
    apply(ctx: Context, config: T): any
  }
}
```

三种形态对应三种使用场景：**函数插件**是最常见的写法，没有状态、只在加载时执行一段注册逻辑（本章后面的 `session-stats` 就是这一类）；**对象插件**和函数插件等价，只是把 `apply` 方法和一些元数据打包成一个对象，常见于需要在配置文件里直接内联一段逻辑的场合；**类插件**（`Service` 子类）用于插件本身就是一个要被其他插件持有引用、调用方法的长生命周期服务——下一节详细展开。

无论哪种形态，`name`、`inject`、`provide` 这些字段的语义是共享的：`inject` 声明启动前置条件，`provide` 声明插件对外发布的服务名字，两者共同构成了 Cordis 解析加载顺序的全部依据——**配置文件里的书写顺序不参与这个决策**。`docs/cordis-tutorial/01-first-plugin.md` 特别强调了这一点：

> Entries start concurrently, so list position guarantees nothing about which plugin loads first; ordering comes from service dependencies (`inject`), not from position in the file.

### Context：服务仓库与 `ctx.<key>` 访问

Context 在源码里的定位很直白，`docs/cordis-api/context.md`（由 `scripts/gen-cordis-catalog.ts` 从 `vendor/cordis/src/context.ts` 生成）这样描述它：

> A context is a proxy: normal property reads go through the service resolver, while `extend()`, `isolate()`, and `intercept()` create scoped child contexts without mutating their parent.

也就是说，`ctx.tools`、`ctx.llm`、`ctx.sessions` 这些属性访问，表面上是普通的对象属性读取，实际上都会先经过一层 Proxy 拦截，去服务仓库里查找当前作用域下名字为 `tools`/`llm`/`sessions` 的实现。这一层"查找"而非"直接持有引用"的间接性，正是插件之间解耦的关键：两个互不认识、甚至互不 `import` 对方类型的插件，只要都认识同一个服务名字，就能协作。

读写这个仓库的底层原语是 `ctx.get` / `ctx.provide`（`docs/cordis-api/context.md`，源码在 `vendor/cordis/src/reflect.ts`）：

```ts
// vendor/cordis/src/reflect.ts（docs/cordis-api/context.md 摘录）
/**
 * Read a service from the store without the inject requirement.
 * @param strict — when `true` (default), only return implementations
 * whose providing fiber is currently active.
 * @returns the service value, or `undefined` when not (yet) provided.
 */
get<K extends string & keyof this>(name: K, strict?: boolean): undefined | this[K]

/**
 * Register a service implementation owned by the current fiber.
 * The service becomes visible to dependents in the same isolation scope
 * once the fiber is active; it is unregistered (waking dependents) when
 * the returned disposer runs or the fiber unloads.
 * @returns a disposer that unregisters the service.
 */
provide<K extends string & keyof this>(name: K, value: undefined | this[K]): () => void
```

`ctx.<key>` 的语法糖背后就是 `ctx.get(key)`；而 `Service` 子类的 `super(ctx, name)` 背后就是调用了 `ctx.provide(name, this)`。`provide` 返回的是一个**注销函数**——这不是随手设计的返回值，而是本章第三篇要讲的"注册即副作用"原则在最底层的体现：谁提供了服务，谁就自动获得了收回它的手柄。

### `inject`：声明依赖，让 Cordis 算加载顺序

`docs/cordis-tutorial/03-services.md` 用一个 `greeter`/`consumer` 的最小例子讲清楚了这条机制。提供服务的一方：

```ts
// docs/cordis-tutorial/03-services.md
import { Service, type Context } from '@deepseek-ai/cordis'

declare module '@deepseek-ai/cordis' {
  interface Context {
    greeter: GreeterService
  }
}

export class GreeterService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'greeter')
  }
  greet(who: string) {
    return `Hello, ${who}!`
  }
}

export const name = 'greeter'
export function apply(ctx: Context) {
  ctx.plugin(GreeterService)
}
```

消费服务的一方：

```ts
// docs/cordis-tutorial/03-services.md
import type { Context } from '@deepseek-ai/cordis'

export const name = 'consumer'
export const inject = ['greeter']

export function apply(ctx: Context) {
  console.log(ctx.greeter.greet('world'))
}
```

`inject = ['greeter']` 意味着：Cordis 会把这个插件的 Fiber（下一篇会讲到，一个 Fiber 就是"一个已加载插件实例的运行时句柄"）挂在 `PENDING` 状态，直到 `greeter` 服务真正存在，才会真正调用 `apply`。教程原文强调了两点很反直觉但很重要的行为：

> Load order in `cordis.yml` does not matter — dependencies, not file order, decide when plugins start.

以及依赖关系不是一次性的启动检查，而是**运行时持续追踪**的：

> If a required service disappears while the app runs — its provider was unloaded or hot-replaced — every dependent plugin is unloaded too, and loads again when the service returns.

这意味着热重载（HMR）一个服务提供者时，所有依赖它的插件会先被自动卸载、等新实现就位后再自动重新加载——不需要任何人手写"服务替换时该怎么办"的逻辑，这条链路完全由 `inject` 关系驱动。

对于并非硬性依赖、可以在服务缺失时优雅降级的场景，`inject` 不是唯一选项。教程给出的替代方案是在使用点直接调用 `ctx.get`：

```ts
// docs/cordis-tutorial/03-services.md
export function apply(ctx: Context) {
  // undefined when no provider is loaded; the plugin still runs.
  const greeter = ctx.get('greeter')
  console.log(greeter?.greet('maybe') ?? 'no greeter available')
}
```

`inject` 是"没有它我就不该启动"，`ctx.get` 是"没有它我也能正常运行，只是少一项能力"——选择哪一种，取决于这项能力对插件本身是不是必需的。

### 一个真实的最小插件：`dsh-session-stats`

教程里的例子足够讲清楚机制，但看一眼 dsh 自己仓库里体量最小的真实插件，会更直观地知道"一个能上生产的插件到底有多薄"。`packages/session/session-stats/src/index.ts` 全文只有 29 行：

```ts
// packages/session/session-stats/src/index.ts
/**
 * Function plugin registering the `sessionStats` projection unit: whole-log
 * turn/step counts and LLM/tool/first-token/decode wall times served through
 * the session-projection seam (registry snapshot, change feed, and every
 * projection carrier), so clients render full-session figures that paging and
 * compaction cannot change. The plugin owns only the fold; delivery is the
 * seam's.
 *
 * @module @deepseek-ai/dsh-session-stats
 */

import type { Context } from '@deepseek-ai/cordis'
import { sessionStatsProjectionDefinition } from './projection.ts'

export type * from './types.ts'

/** Cordis plugin name. */
export const name = 'session-stats'
/** The projection registry is the plugin's whole purpose; without it the fiber stays pending. */
export const inject = ['sessionProjections']

/**
 * Register the `sessionStats` unit; the registration is an effect on this
 * plugin's fiber, so unloading removes the key.
 * @param ctx - registrant context carrying the projection registry.
 */
export function apply(ctx: Context): void {
  ctx.sessionProjections.register(sessionStatsProjectionDefinition)
}
```

逐段来看：

- **`inject = ['sessionProjections']`**：这个插件唯一的存在理由就是往 `sessionProjections` 服务里注册一个"投影单元"，所以它对这个服务是硬依赖——一旦宿主没有装配会话投影服务，这个插件永远停在 `PENDING`，什么都不做，也不会报错。
- **`apply(ctx)` 只做一行事**：调用 `ctx.sessionProjections.register(...)`，把真正的统计逻辑（读取整段会话日志、折叠出轮次/步数计数和耗时）委托给 `./projection.ts` 里的纯函数定义。插件文件本身不关心"怎么统计"，只关心"往哪个服务里挂"。
- 注释里那句 "the registration is an effect on this plugin's fiber, so unloading removes the key" 已经在预告下一篇的内容：`register()` 的返回值不是这里被丢弃了，而是内部已经自动绑定到了当前插件的生命周期上。

对比一下另一个同样极简、但用 `ctx.effect()` 显式包裹注册调用的例子，`packages/session-query/session-log-export/src/index.ts`：

```ts
// packages/session-query/session-log-export/src/index.ts
import type { Context } from '@deepseek-ai/cordis'
import type { CommandResult } from '@deepseek-ai/dsh-commands'

export const name = 'session-log-download'
export const inject = ['commands']

const REQUESTED: CommandResult = {
  kind: 'success',
  text: 'Session log download requested.',
}

export function apply(ctx: Context): void {
  ctx.effect(() => ctx.commands.register({
    name: 'export',
    description: 'Download this Session log as a ZIP archive',
    handler: invocation => Promise.resolve(invocation.rawInput.trim() === ''
      ? REQUESTED
      : { kind: 'error', text: 'The Web /export command does not accept a path.' }),
  }), 'session-log-download: command')
}
```

两个例子的共性远大于差异：`inject` 声明一个硬依赖服务名字，`apply` 里只做"注册一件东西"这一件事。差异只是 `ctx.tools`/`ctx.sessionProjections`/`ctx.commands` 这类注册表的 `register()` 方法本身是否已经内部调用了 `ctx.effect()`——`dsh-commands` 的作者选择让调用方显式包一层，`dsh-session-projections` 的作者选择在 `register()` 内部就做好。这正是下一篇要讲的话题。

### 一个真实的 Service Definition：`SpillStore`

`Service` 子类不只是"class 形态的插件"，它还承担着**定义一个服务契约**的角色。`packages/spill/spill/src/index.ts` 是一个体量刚好合适、语义清晰的例子：

```ts
// packages/spill/spill/src/index.ts
import { Context, Service } from '@deepseek-ai/cordis'
import type { SaveTextSpill, SpillRef } from './types.ts'

declare module '@deepseek-ai/cordis' {
  interface Context {
    spillStore: SpillStore
  }
}

/**
 * Abstract spill storage service. Subclass, implement {@link saveText}, and load
 * the subclass as a plugin — it registers as `ctx.spillStore` (one
 * implementation per context; loading a second throws, cordis' standard
 * duplicate-service behavior).
 */
export abstract class SpillStore extends Service {
  constructor(ctx: Context) {
    super(ctx, 'spillStore')
  }

  abstract saveText(input: SaveTextSpill): Promise<SpillRef>
}

export default SpillStore
```

这段代码演示了一种很常见的 dsh 内部分层模式：`packages/spill/spill` 这个包本身**不提供任何具体实现**，它只声明"存在一个叫 `spillStore` 的服务，这个服务必须有一个 `saveText` 方法"——`saveText` 是 `abstract`，永远不会被这个包自己调用。真正的实现（比如把内容存到本地文件系统的 `dsh-spill-local`）是另一个独立的包，去 `extends SpillStore` 并实现 `saveText`。

这正是 `docs/architecture.md` 里"Capability seam"（能力接缝）概念的三个角色之一：**Service Definition**（这里的 `SpillStore` 抽象类）声明契约是什么，**Service Provider**（`dsh-spill-local` 之类的包）实现契约怎么做，**Consumer**（某个需要落盘超长文本的工具）通过 `ctx.spillStore` 使用契约。三者可以合并在一个包里（就像前面的 `session-stats`），也可以像这里一样被拆成三个独立的包——拆开的好处是，换一个存储后端只需要换 Provider 包，Consumer 和 Definition 都不用动。

值得留意的还有 `declare module '@deepseek-ai/cordis' { interface Context { spillStore: SpillStore } }` 这段**声明合并**。它不生成任何运行时代码——即使删掉它，`ctx.provide('spillStore', this)` 依然会正常工作，`ctx.spillStore` 依然能在运行时读到值。它唯一的作用是让 TypeScript 编译器知道"`Context` 接口上多了一个 `spillStore` 字段，类型是 `SpillStore`"，这样任何插件写 `ctx.spillStore.saveText(...)` 时才会有类型检查和自动补全。`docs/cordis-tutorial/03-services.md` 对这一点的措辞很精确：

> It generates no code; without it the service still works at runtime, but consumers lose type safety.

## 常见问题/易踩坑

- **"我的插件什么都没打印，也没报错"**：几乎总是因为 `inject` 列出的某个服务名字没有被任何插件提供，Fiber 停在了 `PENDING` 状态——这是一个合法状态，不是错误，Cordis 不会因此报警。下一篇会讲怎么用 `ctx.registry` 遍历 Fiber 状态来诊断这种情况。
- **服务名字冲突**：`SpillStore` 的注释里写得很清楚——"one implementation per context; loading a second throws"，同一个 Context 下重复 `provide` 同一个服务名字会直接抛错，这是 Cordis 的标准行为，不需要额外写重复检测代码。
- **把 `inject` 和 `import` 混为一谈**：`inject` 声明的是**运行时服务依赖**，不是编译期类型依赖。一个插件完全可以 `import type {} from '@deepseek-ai/dsh-tools'` 只是为了拿到类型声明合并（第二篇会讲到这一点），却完全不把 `'tools'` 放进自己的 `inject` 数组——这意味着它对这个服务只是"如果有就用类型信息"，不是"启动前必须等它"。

## 小结

Cordis 的核心心智模型可以归纳成一句话：**Context 是一个按名字索引的服务仓库，Plugin 是往这个仓库里读写的独立单元，`inject` 是插件对仓库内容的显式依赖声明**。三种插件形态（函数、对象、类）只是"往仓库里写"这件事的三种语法，`Service` 基类额外承担了"定义一个可被继承、可被替换的服务契约"的角色。真实的 dsh 代码——无论是 29 行的 `session-stats` 还是抽象的 `SpillStore`——都严格遵循这套心智模型，这也是为什么本章开头说"没有一处是框架核心不可替换的部分"：换掉任何一个服务名字背后的实现，都只是换一个插件，而不是改一处特殊逻辑。

下一篇《Typed Events 与四种派发模式》会讲清楚：当插件之间不需要"直接调用对方方法"、只需要"通知对方发生了什么、或者请对方决定要不要拦截"时，Cordis 提供的另一套通信机制——Typed Events——是怎么工作的。
