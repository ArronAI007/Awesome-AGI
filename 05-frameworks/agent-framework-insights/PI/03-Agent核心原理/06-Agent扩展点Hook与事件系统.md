# Agent 扩展点 Hook 与事件系统

> pi 的每一个"看起来像内置功能"的行为——权限确认、危险命令拦截、自定义压缩、自定义工具——几乎都是通过同一套扩展事件系统实现的,而不是硬编码在核心逻辑里的特殊分支。本篇讲清楚这套事件系统在底层是怎么接到 `packages/agent` 引擎的关键节点上的,以及如何用一个真实、可运行的扩展示例把这套机制串起来。

## 学习目标

- 理解扩展系统的整体生命周期：从 `project_trust` 到 `session_start` 到每一轮对话内的 `tool_call`/`tool_result`,再到 `session_shutdown`。
- 搞清楚 `ExtensionAPI`/`ExtensionRunner`/`ExtensionContext` 三者的分工,以及扩展加载机制（`jiti` 动态加载 TypeScript）。
- 理解 `packages/coding-agent` 是如何把扩展系统的 `tool_call`/`tool_result` 事件,通过 `Agent.beforeToolCall`/`Agent.afterToolCall` 这两个引擎级挂载点接进 `packages/agent` 内核的——这是"整车给引擎装传感器"的具体案例。
- 能读懂并解释 `protected-paths.ts` 这个真实扩展示例的完整逻辑。
- 知道如何注册自定义工具（`registerTool`）,以及自定义工具与内置工具在执行链路上的异同。

## 背景与设计动机

如果每新增一种"钩子需求"（权限确认、危险命令拦截、自定义 UI 反馈)都要往 `agent-loop.ts` 或 `AgentSession` 核心代码里加一个新的 if 分支,这个核心模块很快会变得又臃肿又难维护,而且普通用户完全没有能力扩展它。pi 的解法是反过来：**核心循环只暴露少量、通用、组合式的扩展点**（`beforeToolCall`/`afterToolCall`/`shouldStopAfterTurn`/`getSteeringMessages` 等,详见第一、二篇),真正五花八门的业务逻辑（权限确认对话框、危险命令黑名单、Git 检出点、SSH 远程执行……)全部下放到 `packages/coding-agent` 的扩展系统里,以普通 TypeScript 模块的形式动态加载。核心永远不需要知道某个具体扩展在做什么,扩展也永远不需要碰 `agent-loop.ts` 一行代码。

## 核心机制详解

### 扩展的加载与生命周期

扩展是导出一个默认工厂函数的 TypeScript 模块,存放在 `~/.pi/agent/extensions/`（全局）或 `.pi/extensions/`（项目本地,需要项目被信任之后才会加载）：

```typescript
// 最小可运行的扩展骨架
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	pi.on("session_start", async (_event, ctx) => {
		ctx.ui.notify("Extension loaded!", "info");
	});
}
```

`packages/coding-agent/src/core/extensions/loader.ts` 用 [jiti](https://github.com/unjs/jiti) 动态加载这些模块,不需要预编译：

```typescript
// packages/coding-agent/src/core/extensions/loader.ts(节选)
const jiti = createJiti(import.meta.url, { ... });
const module = await jiti.import(extensionPath, { default: true });
```

这意味着扩展可以直接写 TypeScript、可以用 `node:fs`/`node:path` 等内置模块,也可以在扩展目录放一个 `package.json` + `npm install` 引入第三方依赖——加载时机完全在运行时,这也是为什么 `/reload` 命令能做到"编辑扩展代码后立即热重载,不需要重启 pi 进程"。

生命周期上,`packages/coding-agent/docs/extensions.md` 给出的顺序图是理解这套系统的关键坐标系：

```text
pi 启动
  ├─► project_trust(仅用户/全局扩展和 CLI -e 扩展参与,在项目资源加载之前)
  ├─► session_start { reason: "startup" }
  └─► resources_discover { reason: "startup" }

用户发送 prompt ──────────────────────────────┐
  ├─► input(可拦截、转换或直接处理)              │
  ├─► before_agent_start(可注入消息、改写系统提示词)
  ├─► agent_start                              │
  │   ┌── turn(模型调用工具时重复) ──┐          │
  │   ├─► turn_start                │          │
  │   ├─► context(可修改消息)        │          │
  │   │   LLM 响应,可能调用工具:      │          │
  │   │     ├─► tool_execution_start │          │
  │   │     ├─► tool_call(可拦截)    │          │
  │   │     ├─► tool_execution_update│          │
  │   │     ├─► tool_result(可修改)  │          │
  │   │     └─► tool_execution_end   │          │
  │   └─► turn_end                  │          │
  ├─► agent_end                                │
  └─► agent_settled(确认不会再自动继续)          │
用户发送下一条 prompt ◄──────────────────────────┘
```

这张图里最重要的两组区分：其一,`agent_end` 只代表"这次底层循环跑完了",pi 可能紧接着自动重试、自动压缩后重试、或者处理排队的 follow-up 消息——只有 `agent_settled` 才代表真正闲下来（对应第三篇讲的 `agent_end` vs "settled"语义区分)；其二,`tool_call`（可拦截,在真正执行前触发)和 `tool_result`（可修改,在执行完之后触发)是两个独立事件,分别对应第二篇讲的 `beforeToolCall`/`afterToolCall` 钩子。

### `ExtensionAPI`/`ExtensionContext`:扩展看到的两张"脸"

扩展工厂函数拿到的 `pi: ExtensionAPI` 主要提供订阅事件和注册能力的方法：

```typescript
// packages/coding-agent/src/core/extensions/types.ts(节选)
export interface ExtensionAPI {
	on(event: "tool_call", handler: ExtensionHandler<ToolCallEvent, ToolCallEventResult>): void;
	on(event: "tool_result", handler: ExtensionHandler<ToolResultEvent, ToolResultEventResult>): void;
	on(event: "before_agent_start", handler: ExtensionHandler<BeforeAgentStartEvent, BeforeAgentStartEventResult>): void;
	on(event: "session_before_compact", handler: ExtensionHandler<SessionBeforeCompactEvent, SessionBeforeCompactResult>): void;
	// ...其余二十余种事件,逐一对应上面生命周期图里的每个节点
	registerTool<TParams extends TSchema = TSchema, TDetails = unknown, TState = any>(
		tool: ToolDefinition<TParams, TDetails, TState>,
	): void;
	registerCommand(name: string, options: Omit<RegisteredCommand, "name" | "sourceInfo">): void;
	registerShortcut(shortcut: KeyId, options: { description?: string; handler: (ctx: ExtensionContext) => Promise<void> | void }): void;
	registerFlag(name: string, options: { description?: string; type: "boolean" | "string"; default?: boolean | string }): void;
	getFlag(name: string): boolean | string | undefined;
}
```

而每个事件处理函数的第二个参数 `ctx: ExtensionContext` 是"运行时快照"——包含 `ctx.ui`（弹窗、通知、状态栏)、`ctx.sessionManager`（只读会话访问,详见第四篇)、`ctx.model`/`ctx.thinkingLevel`、`ctx.signal`（当前轮次的中止信号,详见第三篇)、`ctx.cwd`、`ctx.mode`（`"tui" | "rpc" | "json" | "print"`)等。命令处理函数额外拿到 `ExtensionCommandContext`,多出 `ctx.newSession()`/`ctx.fork()`/`ctx.navigateTree()`/`ctx.waitForIdle()` 等只能在命令里安全调用的方法——文档特别强调这些方法不能放进事件处理器里调用,因为可能造成死锁。

### `tool_call`/`tool_result` 如何接进引擎:`_installAgentToolHooks`

这是本篇最关键的一段"整车装引擎"的代码。`packages/coding-agent/src/core/agent-session.ts` 在构造时,把扩展系统的两个事件包装成第一、二篇讲过的引擎级钩子 `Agent.beforeToolCall`/`Agent.afterToolCall`：

```typescript
// packages/coding-agent/src/core/agent-session.ts
private _installAgentToolHooks(): void {
	this.agent.beforeToolCall = async ({ toolCall, args }) => {
		const runner = this._extensionRunner;
		if (!runner.hasHandlers("tool_call")) return undefined; // 没人注册过 tool_call,直接放行,零开销
		try {
			return await runner.emitToolCall({
				type: "tool_call",
				toolName: toolCall.name,
				toolCallId: toolCall.id,
				input: args as Record<string, unknown>,
			});
		} catch (err) {
			if (err instanceof Error) throw err;
			throw new Error(`Extension failed, blocking execution: ${String(err)}`);
		}
	};

	this.agent.afterToolCall = async ({ toolCall, args, result, isError }) => {
		const runner = this._extensionRunner;
		const hookResult = runner.hasHandlers("tool_result")
			? await runner.emitToolResult({
					type: "tool_result", toolName: toolCall.name, toolCallId: toolCall.id,
					input: args as Record<string, unknown>,
					content: result.content, details: result.details, isError, usage: result.usage,
				})
			: undefined;
		const content = hookResult?.content ?? result.content ?? [];
		const normalizedContent = await normalizeToolResultImages(content, { autoResizeImages: this.settingsManager.getImageAutoResize() });
		if (!hookResult && normalizedContent === content) return undefined; // 无变化,不产生覆盖
		// ...把 hookResult 和图片归一化结果合并成 AfterToolCallResult 返回
	};
}
```

这段代码回答了一个贯穿全课程的问题——"扩展系统是怎么长在引擎上的"：`Agent` 类本身完全不知道有"扩展"这个概念存在,它只认识 `AgentLoopConfig.beforeToolCall`/`afterToolCall` 这两个类型化的回调（第二篇详细拆解过它们在 `agent-loop.ts` 里的调用位置)。`AgentSession` 在构造时把这两个回调**赋值**成"去问扩展系统有没有人关心这次调用"的适配器函数。`runner.hasHandlers("tool_call")` 这一行还顺带做了性能优化——如果没有任何扩展注册过 `tool_call` 监听器,直接跳过整个事件分发流程,不产生额外开销。这正是第一篇里提到的"每一项整车能力,都能在引擎暴露的扩展点上找到对应挂载方式"的具体实证。

`tool_call` 事件的输入是可变的：

```typescript
pi.on("tool_call", async (event, ctx) => {
	if (isToolCallEventType("bash", event)) {
		event.input.command = `source ~/.profile\n${event.input.command}`; // 原地修改,影响真正执行的参数
		if (event.input.command.includes("rm -rf")) {
			return { block: true, reason: "Dangerous command", terminate: true };
		}
	}
});
```

`event.input` 直接原地修改就会影响真正传给 `tool.execute()` 的参数（且**不会**重新走一遍 schema 校验),多个扩展的 `tool_call` 处理器按加载顺序依次看到前一个处理器修改后的结果——这是一种"责任链"式的中间件模式,与 Express/Koa 这类 Web 框架的中间件设计如出一辙,只是这里中间件处理的是工具调用而不是 HTTP 请求。

### 一个真实、完整的扩展示例:路径保护

`packages/coding-agent/examples/extensions/protected-paths.ts` 是一个可以直接复制去用的完整示例：

```typescript
/**
 * Protected Paths Extension
 *
 * Blocks write and edit operations to protected paths.
 * Useful for preventing accidental modifications to sensitive files.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
	const protectedPaths = [".env", ".git/", "node_modules/"];

	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName !== "write" && event.toolName !== "edit") {
			return undefined; // 不关心其他工具,直接放行
		}
		const path = event.input.path as string;
		const isProtected = protectedPaths.some((p) => path.includes(p));
		if (isProtected) {
			if (ctx.hasUI) {
				ctx.ui.notify(`Blocked write to protected path: ${path}`, "warning");
			}
			return { block: true, reason: `Path "${path}" is protected` };
		}
		return undefined;
	});
}
```

逐行拆解:

1. `pi.on("tool_call", handler)` 订阅"工具即将执行"事件——这正是上一节讲的、被 `AgentSession.beforeToolCall` 适配进引擎的那个钩子。
2. 只对 `write`/`edit` 两个工具名感兴趣,其余工具（`read`/`bash`/`grep`……)一律 `return undefined`——`undefined` 在 `ToolCallEventResult` 语义里代表"不拦截,正常放行",这与第二篇讲的 `beforeToolCall` 返回值语义完全对应。
3. `event.input.path` 的类型来自内置工具 `write`/`edit` 的参数 schema（`{ path: string, ... }`),这里直接用 `as string` 断言;更类型安全的写法是用文档里提到的 `isToolCallEventType("write", event)` 做类型收窄。
4. 命中黑名单时,先用 `ctx.hasUI` 判断当前是否处于有交互界面的模式（TUI/RPC),避免在无 UI 的 `print`/`json` 模式下调用 `ctx.ui.notify` 产生无意义的副作用,再返回 `{ block: true, reason }`。
5. 这个 `reason` 字符串最终会变成第二篇讲过的 `createErrorToolResult(reason)`——一条 `isError: true` 的 `ToolResultMessage`,反馈给模型,模型看到"这条路径受保护"这句话之后,通常会主动放弃继续尝试写这个文件,或者向用户解释情况并请求许可。

这个 12 行的示例,完整覆盖了"事件订阅 → 条件过滤 → 读取可变输入 → 判断 UI 可用性 → 返回拦截结果"这一整套扩展开发的标准动作,是官方文档里被反复引用的入门范例。

### 注册自定义工具:`registerTool`

除了拦截/修改内置工具,扩展也可以注册全新的工具,让模型可以调用：

```typescript
import { Type } from "typebox";

pi.registerTool({
	name: "greet",
	label: "Greet",
	description: "Greet someone by name",
	parameters: Type.Object({ name: Type.String({ description: "Name to greet" }) }),
	async execute(toolCallId, params, signal, onUpdate, ctx) {
		return { content: [{ type: "text", text: `Hello, ${params.name}!` }], details: {} };
	},
});
```

`registerTool` 接收的正是第二篇讲过的 `ToolDefinition` 类型——参数用 TypeBox schema 定义（`parameters: Type.Object({...})`),`execute` 签名比 `AgentTool.execute` 多一个 `ctx: ExtensionContext` 参数。这份 `ToolDefinition` 最终同样会经过 `wrapToolDefinition` 被转换成引擎认识的 `AgentTool`,和内置的 `read`/`bash`/`edit`/`write` 走的是完全相同的执行流水线（schema 校验 → `beforeToolCall` → `execute` → `afterToolCall` → 封装成 `ToolResultMessage`)——**内置工具和扩展注册的自定义工具,在引擎眼里没有任何区别**,这也是为什么本文档系列第二篇讲的整套工具调用机制,可以不加改动地直接套用在你自己写的扩展工具上。文档特别提到 `registerTool()` 可以在 `session_start` 或运行期间随时调用,新工具立即对模型可见,不需要 `/reload`。

### 拦截结果的语义小结

|事件|可返回内容|典型语义|
|---|---|---|
|`tool_call`|`{ block?: boolean, reason?: string, terminate?: boolean }`|拦截即将执行的工具调用|
|`tool_result`|`{ content?, details?, isError?, usage? }`(部分字段覆盖)|修改已执行完毕的工具结果|
|`before_agent_start`|`{ message?, systemPrompt? }`|注入消息、改写系统提示词|
|`context`|`{ messages }`|非破坏性地修改即将发给模型的消息副本|
|`session_before_compact`|`{ cancel? } \| { compaction }`|取消或接管压缩(见第五篇)|
|`input`|`{ action: "continue" \| "transform" \| "handled", ... }`|拦截、改写或完全接管用户输入|

这张表覆盖了绝大多数扩展开发的常见需求入口,和第一至五篇讲过的引擎机制逐一对应：`tool_call`/`tool_result` 对应第二篇的工具调用流水线,`before_agent_start`/`context` 对应第三篇的消息状态机,`session_before_compact` 对应第五篇的压缩流程。

## 关键代码解读

### 为什么 `tool_call` 能看到"同步"的会话状态

`extensions.md` 提到一个容易被忽视但很重要的保证：在 `tool_call` 触发之前,pi 会先等待此前已经产生的 Agent 事件在 `AgentSession` 里完全处理完毕（会话落盘、状态更新等),这样 `ctx.sessionManager` 在 `tool_call` 处理器里看到的数据,已经反映了触发这次工具调用的那条 assistant 消息。但在默认的**并行**工具执行模式下（第二篇讲过),同一条 assistant 消息里的多个 `toolCall` 是先统一预检、再并发执行的,所以 `tool_call` 处理器**不保证**能看到同一批次里"兄弟工具调用"已经产生的结果——这直接对应第二篇讲的"预检顺序 / 完成顺序 / 落盘顺序三者分离"的调度模型,扩展开发者写涉及多工具协同判断的逻辑时必须考虑到这一点。

## 小结与思考题

扩展系统的本质是：核心引擎（`packages/agent`)只暴露少量类型化、组合式的回调钩子（`beforeToolCall`/`afterToolCall`/`convertToLlm`/`getSteeringMessages` 等),`packages/coding-agent` 的 `AgentSession` 把这些钩子适配成一套面向普通开发者的事件系统（`pi.on(eventName, handler)`),再通过 `jiti` 动态加载用户/项目目录下的 TypeScript 扩展模块。自定义工具通过 `registerTool` 注册后,与内置工具共享完全相同的执行流水线,不存在"内置工具享有特权"的情况。

思考题：

1. `protected-paths.ts` 示例里,`isProtected` 的判断用的是简单的字符串 `includes`。如果攻击者传入一个经过路径穿越拼接的路径（比如 `./safe/../.env`),这个判断会被绕过吗？如果要写得更健壮,你会如何改造？
2. 如果一个扩展同时注册了 `tool_call` 拦截和 `registerTool` 自定义工具,并且自定义工具的名字恰好和被拦截的内置工具重名,基于本篇讲的"内置工具和自定义工具共享同一条流水线"的结论，你认为会发生什么？
3. `before_agent_start` 和 `context` 都能修改即将发给模型的内容,但触发时机和粒度不同（前者只在一次 `prompt()` 发起时触发一次、可以注入持久化消息;后者在每一轮请求前都会触发、只影响这一次请求的非破坏性副本)。如果你要实现"永久隐藏所有历史里的某个字段"和"临时压缩掉本轮请求中过长的某条工具结果"这两个需求，分别应该挂在哪个事件上？
