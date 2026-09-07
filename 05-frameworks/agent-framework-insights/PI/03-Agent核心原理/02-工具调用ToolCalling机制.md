# 工具调用 Tool Calling 机制

> 模型不会直接"执行"任何东西——它只会在响应里吐出一段结构化的 `toolCall`（工具名 + JSON 参数）,真正把它变成一次文件读取或一次 shell 命令执行,是 `agent-loop.ts` 里一整套"准备 → 执行 → 收尾"流水线的工作。本篇拆开这条流水线,并用 `read`/`bash` 两个真实工具的实现讲清楚一个工具从 schema 定义到执行结果落回上下文的完整生命周期。

## 学习目标

- 理解工具在 pi 里的两层定义：`AgentTool`（引擎认识的执行契约）与 `ToolDefinition`（`coding-agent` 认识的、带渲染和提示词元数据的高层定义）,以及两者如何通过 `wrapToolDefinition` 互相转换。
- 搞清楚模型返回 `toolCall` 之后,`agent-loop.ts` 如何做参数校验、`beforeToolCall`/`afterToolCall` 钩子、实际执行、结果拼装这四个阶段。
- 理解并行执行（`parallel`）与串行执行（`sequential`）两种模式的调度差异,以及 `executionMode` 如何在工具粒度覆盖全局配置。
- 通读 `read.ts` 和 `bash.ts` 两个真实工具的实现,理解一个工具的输入输出结构长什么样。
- 掌握工具执行失败、参数截断、用户中断三种异常路径各自如何被兜底,不让整个 Agent 循环崩溃。

## 背景与设计动机

LLM 的"工具调用"本质上只是模型输出里的一段特殊内容块——在 `pi-ai` 的类型定义里,就是 `AssistantMessage.content` 数组里的一个 `ToolCall` 元素：

```typescript
// packages/ai/src/types.ts
export interface ToolCall {
	type: "toolCall";
	id: string;
	name: string;
	arguments: Record<string, any>;
	thoughtSignature?: string; // Google 专属:复用思考上下文的不透明签名
	namespace?: string;       // OpenAI Responses 命名空间,用于动态加载的工具
}
```

模型只是"声称"要调用某个工具、给出了它认为合适的参数——参数是否合法、工具是否存在、要不要真的执行,完全是宿主程序（也就是 `agent-loop.ts`）说了算。这个设计的核心动机是**安全边界**：绝不能假设模型给出的 JSON 是可信、完整、类型正确的。所以在真正调用 `tool.execute()` 之前,pi 至少做了三件事：schema 校验、可选的参数预处理（`prepareArguments`）、`beforeToolCall` 钩子（可能直接拦截）。这三层防御在下文会逐一展开。

## 核心机制详解

### 工具的两层定义

`packages/agent/src/types.ts` 里的 `AgentTool` 是引擎侧认识的最小契约：

```typescript
export interface AgentTool<TParameters extends TSchema = TSchema, TDetails = any> extends Tool<TParameters> {
	label: string;
	prepareArguments?: (args: unknown) => Static<TParameters>;
	execute: (
		toolCallId: string,
		params: Static<TParameters>,
		signal?: AbortSignal,
		onUpdate?: AgentToolUpdateCallback<TDetails>,
	) => Promise<AgentToolResult<TDetails>>;
	executionMode?: ToolExecutionMode;
}
```

而 `packages/coding-agent/src/core/extensions/types.ts` 里的 `ToolDefinition` 是 `coding-agent` 侧的高层定义,除了 `AgentTool` 的字段外还多了提示词相关的元数据（`promptSnippet`/`promptGuidelines`）和 TUI 渲染函数（`renderCall`/`renderResult`）：

```typescript
// packages/coding-agent/src/core/extensions/types.ts
export interface ToolDefinition<TParams extends TSchema = TSchema, TDetails = unknown, TState = any> {
	name: string;
	label: string;
	description: string;
	promptSnippet?: string;       // Available tools 里的一行摘要
	promptGuidelines?: string[];  // 追加到系统提示词 Guidelines 段的要点
	parameters: TParams;
	prepareArguments?: (args: unknown) => Static<TParams>;
	executionMode?: ToolExecutionMode;
	execute(
		toolCallId: string, params: Static<TParams>,
		signal: AbortSignal | undefined, onUpdate: AgentToolUpdateCallback<TDetails> | undefined,
		ctx: ExtensionContext, // 比 AgentTool.execute 多这一个参数
	): Promise<AgentToolResult<TDetails>>;
	renderCall?: (args: Static<TParams>, theme: Theme, context: ToolRenderContext<TState, Static<TParams>>) => Component;
	renderResult?: (result: AgentToolResult<TDetails>, options: ToolRenderResultOptions, theme: Theme, context: ToolRenderContext<TState, Static<TParams>>) => Component;
}
```

关键差异在 `execute` 的签名：`ToolDefinition.execute` 多接收一个 `ctx: ExtensionContext` 参数,可以拿到会话管理器、当前模型、扩展 API 等上下文信息;而 `AgentTool.execute` 完全不知道 `ExtensionContext` 的存在。两者之间的桥梁是 `tool-definition-wrapper.ts`：

```typescript
// packages/coding-agent/src/core/tools/tool-definition-wrapper.ts
export function wrapToolDefinition<TDetails = unknown>(
	definition: ToolDefinition<any, TDetails>,
	ctxFactory?: () => ExtensionContext,
): AgentTool<any, TDetails> {
	return {
		name: definition.name,
		label: definition.label,
		description: definition.description,
		parameters: definition.parameters,
		constrainedSampling: definition.constrainedSampling,
		prepareArguments: definition.prepareArguments,
		executionMode: definition.executionMode,
		execute: (toolCallId, params, signal, onUpdate, ctx?: ExtensionContext) =>
			definition.execute(toolCallId, params, signal, onUpdate, ctx ?? (ctxFactory?.() as ExtensionContext)),
	};
}
```

`wrapToolDefinition` 做的事情很朴素：丢掉渲染相关的字段,把 `execute` 包一层——如果调用方（也就是 `agent-loop.ts`）没有显式传 `ctx`,就用 `ctxFactory()` 现造一个。这就是为什么 `packages/agent` 完全不需要认识 `ExtensionContext` 这个类型,却依然能让 `coding-agent` 的工具带着丰富的上下文信息执行。反过来,`createToolDefinitionFromAgentTool` 提供了逆向转换,让一个裸的 `AgentTool` 也能被塞进要求 `ToolDefinition` 的注册表里（用于兼容外部直接传入 `AgentTool` 覆盖内建工具的场景）。

### 从模型吐出 toolCall 到执行完成:四个阶段

`agent-loop.ts` 把单个工具调用的处理拆成了 `prepareToolCall` → `executePreparedToolCall` → `finalizeExecutedToolCall` 三个函数外加统一的结果封装,对应四个逻辑阶段：

**阶段一:准备（校验 + `beforeToolCall`）**

```typescript
// packages/agent/src/agent-loop.ts
async function prepareToolCall(
	currentContext: AgentContext,
	assistantMessage: AssistantMessage,
	toolCall: AgentToolCall,
	config: AgentLoopConfig,
	signal: AbortSignal | undefined,
): Promise<PreparedToolCall | ImmediateToolCallOutcome> {
	const tool = currentContext.tools?.find((t) => t.name === toolCall.name);
	if (!tool) {
		return { kind: "immediate", result: createErrorToolResult(`Tool ${toolCall.name} not found`), isError: true };
	}
	try {
		const preparedToolCall = prepareToolCallArguments(tool, toolCall);
		const validatedArgs = validateToolArguments(tool, preparedToolCall);
		if (config.beforeToolCall) {
			const beforeResult = await config.beforeToolCall(
				{ assistantMessage, toolCall, args: validatedArgs, context: currentContext },
				signal,
			);
			if (signal?.aborted) {
				return { kind: "immediate", result: createErrorToolResult("Operation aborted"), isError: true };
			}
			if (beforeResult?.block) {
				const result = createErrorToolResult(beforeResult.reason || "Tool execution was blocked");
				if (beforeResult.terminate === true) result.terminate = true;
				return { kind: "immediate", result, isError: true };
			}
		}
		if (signal?.aborted) {
			return { kind: "immediate", result: createErrorToolResult("Operation aborted"), isError: true };
		}
		return { kind: "prepared", toolCall, tool, args: validatedArgs };
	} catch (error) {
		return { kind: "immediate", result: createErrorToolResult(error instanceof Error ? error.message : String(error)), isError: true };
	}
}
```

顺序是：**工具是否存在** → **`prepareArguments` 兼容性垫片**（比如老版本模型输出的字段名要映射到新 schema）→ **`validateToolArguments` 用 TypeBox 编译出的 validator 校验并做类型强转**（`packages/ai/src/utils/validation.ts` 里的 `validateToolArguments`,内部用 `Value.Convert` 做字符串到数字等的宽松转换,校验失败会抛出带字段路径的错误）→ **`beforeToolCall` 钩子**,它可以直接把这次调用拦下来（`{ block: true, reason, terminate? }`）。任何一步失败都会走 `kind: "immediate"` 分支——不再进入真正的 `execute()`,而是直接拼一个错误结果反馈给模型。这就是本篇开头强调的"模型的输出不可信"在代码里的具体体现。

**阶段二:执行**

```typescript
async function executePreparedToolCall(
	prepared: PreparedToolCall,
	signal: AbortSignal | undefined,
	emit: AgentEventSink,
): Promise<ExecutedToolCallOutcome> {
	const updateEvents: Promise<void>[] = [];
	let acceptingUpdates = true;
	try {
		const result = await prepared.tool.execute(
			prepared.toolCall.id,
			prepared.args as never,
			signal,
			(partialResult) => {
				if (!acceptingUpdates) return;
				updateEvents.push(Promise.resolve(emit({
					type: "tool_execution_update",
					toolCallId: prepared.toolCall.id,
					toolName: prepared.toolCall.name,
					args: prepared.toolCall.arguments,
					partialResult,
				})));
			},
		);
		acceptingUpdates = false;
		await Promise.all(updateEvents);
		return { result, isError: false };
	} catch (error) {
		acceptingUpdates = false;
		await Promise.all(updateEvents);
		return { result: createErrorToolResult(error instanceof Error ? error.message : String(error)), isError: true };
	} finally {
		acceptingUpdates = false;
	}
}
```

这里体现了 `AgentTool.execute` 契约的一个重要约定（见 `types.ts` 的注释）：**工具应该用抛异常表达失败,而不是自己在 `content` 里编码错误信息**。`executePreparedToolCall` 用 `try/catch` 统一把异常转成 `AgentToolResult`,调用方（`agent-loop.ts` 上层）不需要关心具体工具内部是怎么报错的。`onUpdate` 回调用于工具在执行过程中持续上报中间结果（比如 `bash` 工具在命令还没跑完时,不断把已产生的 stdout/stderr 通过 `tool_execution_update` 事件推给 UI,实现打字机式的输出预览）,`acceptingUpdates` 标志确保工具在 `execute()` 返回之后再调用 `onUpdate` 不会造成事件错序。

**阶段三:收尾（`afterToolCall`）**

```typescript
async function finalizeExecutedToolCall(
	currentContext, assistantMessage, prepared, executed, config, signal,
): Promise<FinalizedToolCallOutcome> {
	let result = executed.result;
	let isError = executed.isError;
	if (config.afterToolCall) {
		try {
			const afterResult = await config.afterToolCall(
				{ assistantMessage, toolCall: prepared.toolCall, args: prepared.args, result, isError, context: currentContext },
				signal,
			);
			if (afterResult) {
				result = {
					...result,
					content: afterResult.content ?? result.content,
					details: afterResult.details ?? result.details,
					usage: afterResult.usage ?? result.usage,
					terminate: afterResult.terminate ?? result.terminate,
				};
				isError = afterResult.isError ?? isError;
			}
		} catch (error) {
			result = createErrorToolResult(error instanceof Error ? error.message : String(error));
			isError = true;
		}
	}
	return { toolCall: prepared.toolCall, result, isError };
}
```

`afterToolCall` 是**逐字段覆盖**而非深合并——只有 `afterResult` 里显式给出的字段才会替换原结果,这在 `types.ts` 的 `AfterToolCallResult` 注释里写得很清楚。这一钩子正是 `packages/coding-agent` 实现扩展系统 `tool_result` 事件的落点（第六篇详述）,也是图片自动压缩等横切逻辑的挂载点。

**阶段四:统一封装成 `ToolResultMessage`**

```typescript
function createToolResultMessage(finalized: FinalizedToolCallOutcome): ToolResultMessage {
	return {
		role: "toolResult",
		toolCallId: finalized.toolCall.id,
		toolName: finalized.toolCall.name,
		content: finalized.result.content ?? [],
		details: finalized.result.details,
		usage: finalized.result.usage,
		...(finalized.result.addedToolNames?.length ? { addedToolNames: finalized.result.addedToolNames } : {}),
		isError: finalized.isError,
		timestamp: Date.now(),
	};
}
```

无论工具是被拦截、执行出错还是正常返回,最终都会被拍平成同一种 `ToolResultMessage` 结构塞回 `context.messages`,模型在下一次调用时会在上下文里看到这条结果——这就是"结果反馈"这一步在代码层面的落地。

### 并行 vs 串行:两种调度策略

`agent-loop.ts` 的 `executeToolCalls` 函数先判断走哪条路径：

```typescript
async function executeToolCalls(currentContext, assistantMessage, config, signal, emit): Promise<ExecutedToolCallBatch> {
	const toolCalls = assistantMessage.content.filter((c) => c.type === "toolCall");
	const hasSequentialToolCall = toolCalls.some(
		(tc) => currentContext.tools?.find((t) => t.name === tc.name)?.executionMode === "sequential",
	);
	if (config.toolExecution === "sequential" || hasSequentialToolCall) {
		return executeToolCallsSequential(currentContext, assistantMessage, toolCalls, config, signal, emit);
	}
	return executeToolCallsParallel(currentContext, assistantMessage, toolCalls, config, signal, emit);
}
```

只要这一批 `toolCall` 里**任意一个**工具声明了 `executionMode: "sequential"`,整批调用都会退化成串行执行——比如同时对同一个文件做多次 `edit`,并行跑可能导致写入顺序错乱,工具作者只需在自己的 `ToolDefinition` 上标注该字段,就能强制整批降级为串行,而不需要感知同批次里还有哪些工具。

并行模式（默认值,`Agent` 构造函数里 `this.toolExecution = runtimeOptions.toolExecution ?? "parallel"`）的实现方式是"预检串行 + 执行并发"：

```typescript
async function executeToolCallsParallel(currentContext, assistantMessage, toolCalls, config, signal, emit) {
	const finalizedCalls: FinalizedToolCallEntry[] = [];
	for (const toolCall of toolCalls) {
		await emit({ type: "tool_execution_start", ... }); // 按原始顺序依次触发(预检阶段)
		const preparation = await prepareToolCall(currentContext, assistantMessage, toolCall, config, signal);
		if (preparation.kind === "immediate") { /* 立即失败,不占并发名额 */ continue; }
		finalizedCalls.push(async () => {
			const executed = await executePreparedToolCall(preparation, signal, emit);
			const finalized = await finalizeExecutedToolCall(currentContext, assistantMessage, preparation, executed, config, signal);
			await emitToolExecutionEnd(finalized, emit); // 按完成顺序触发
			return finalized;
		});
	}
	// Promise.all 并发展开;之后按 assistant 消息的原始顺序把 toolResult 消息事件依次 emit
	const orderedFinalizedCalls = await Promise.all(
		finalizedCalls.map((entry) => (typeof entry === "function" ? entry() : Promise.resolve(entry))),
	);
}
```

`tool_execution_start` 是按 assistant 消息里的原始顺序（也就是"预检"阶段）依次触发的,而真正的执行是通过 `Promise.all` 并发展开的,`tool_execution_end` 则按**谁先执行完谁先触发**（完成顺序）。但最终代表工具结果、真正写入上下文的 `message_start`/`message_end`（`toolResult` 消息）事件,依然是`orderedFinalizedCalls` 按**原始顺序**遍历后依次 emit——这保证了无论并发执行的实际完成顺序如何,模型在下一轮看到的上下文里,工具结果始终和它发起的 `toolCall` 顺序一致。这个"预检顺序 / 完成顺序 / 落盘顺序"三者分离的设计,在 `packages/coding-agent/docs/extensions.md` 里也被明确写成了扩展开发者需要了解的行为保证。

## 关键代码解读

### `read` 工具:纯读取,零副作用

`packages/coding-agent/src/core/tools/read.ts` 定义了 schema：

```typescript
const readSchema = Type.Object({
	path: Type.String({ description: "Path to the file to read (relative or absolute)" }),
	offset: Type.Optional(Type.Number({ description: "Line number to start reading from (1-indexed)" })),
	limit: Type.Optional(Type.Number({ description: "Maximum number of lines to read" })),
});
```

`execute` 的核心逻辑（节选自完整实现）：

```typescript
async execute(_toolCallId, { path, offset, limit }, signal?, _onUpdate?, ctx?) {
	// ...Promise + abort 监听样板省略...
	const absolutePath = await resolveReadPathAsync(path, cwd);
	await ops.access(absolutePath);
	const mimeType = ops.detectImageMimeType ? await ops.detectImageMimeType(absolutePath) : undefined;
	if (mimeType) {
		// 图片:转 base64,塞进 ImageContent
	} else {
		const buffer = await ops.readFile(absolutePath);
		const allLines = buffer.toString("utf-8").split("\n");
		// 按 offset/limit 截取行范围,再用 truncateHead 做字节/行数双重截断
	}
	return { content, details };
}
```

几个值得注意的设计：

- **输入输出**：输入是 `{ path, offset?, limit? }`,输出是 `AgentToolResult`,`content` 数组里既可能是纯文本块也可能是图片块——`read` 工具同时承担"读文本文件"和"读图片附件"两种职责,靠检测 MIME 类型分流。
- **截断策略**：文本内容会经过 `truncateHead`（`truncate.ts`）做默认 `DEFAULT_MAX_LINES` 行 / `DEFAULT_MAX_BYTES` 字节的双重限制,并在被截断时附加形如 `[Showing lines 1-500 of 2000. Use offset=501 to continue.]` 的"续读指引",让模型知道如何用下一次调用接着往下读。
- **可插拔的 I/O 层与 abort**：`ReadOperations` 把 `readFile`/`access`/`detectImageMimeType` 抽象出来,默认走本地文件系统,`examples/extensions/ssh.ts` 之类的扩展可注入 SSH 远程实现;`execute` 内部用 `Promise` + `AbortSignal` 监听实现可中断读取,`aborted` 标志防止 abort 之后 `resolve`/`reject` 被重复或错序调用。

### `bash` 工具:有状态的长时间执行

```typescript
// packages/coding-agent/src/core/tools/bash.ts
const bashSchema = Type.Object({
	command: Type.String({ description: "Bash command to execute" }),
	timeout: Type.Optional(Type.Number({ description: "Timeout in seconds (optional, no default timeout)" })),
});
```

`bash` 工具的复杂度明显高于 `read`,因为它要处理长时间运行、流式输出、超时、abort 杀进程树等一系列问题。核心执行路径：

```typescript
async execute(_toolCallId, { command, timeout }, signal?, onUpdate?, ctx?) {
	const output = new OutputAccumulator({ tempFilePrefix: "pi-bash" });
	// handleData 把 stdout/stderr 追加进 output,并通过节流的 scheduleOutputUpdate() 触发 onUpdate
	const handleData = (data: Buffer) => { output.append(data); scheduleOutputUpdate(); };
	const result = await ops.exec(spawnContext.command, spawnContext.cwd, { onData: handleData, signal, timeout, env: spawnContext.env });
	const snapshot = await finishOutput();
	const { text: outputText, details } = formatOutput(snapshot);
	if (result.exitCode !== 0 && result.exitCode !== null) {
		throw new Error(appendStatus(outputText, `Command exited with code ${result.exitCode}`));
	}
	return { content: [{ type: "text", text: outputText }], details };
}
```

真正的进程创建逻辑封装在 `createLocalBashOperations()` 里（节选核心步骤）：

```typescript
const child = spawn(shellConfig.shell, [...], {
	cwd, detached: process.platform !== "win32", env: env ?? getShellEnv(),
	stdio: [commandFromStdin ? "pipe" : "ignore", "pipe", "pipe"], windowsHide: true,
});
if (child.pid) trackDetachedChildPid(child.pid);
const onAbort = () => { if (child.pid) killProcessTree(child.pid); }; // 杀整棵进程树,而非单个进程
if (timeoutMs !== undefined) {
	timeoutHandle = setTimeout(() => { timedOut = true; if (child.pid) killProcessTree(child.pid); }, timeoutMs);
}
if (signal) { if (signal.aborted) onAbort(); else signal.addEventListener("abort", onAbort, { once: true }); }
const exitCode = await waitForChildProcess(child);
if (signal?.aborted) throw new Error("aborted");
if (timedOut) throw new Error(`timeout:${timeout}`);
```

值得关注的几点：

- **进程树而非单进程**：`detached: true` + `killProcessTree(child.pid)` 确保 `abort` 或超时时,连子进程派生出的孙进程也会被杀掉,不会留下孤儿进程。
- **输出截断与落盘**：`OutputAccumulator` 在内存里累积输出,超过限制后会把完整输出写到临时文件（`fullOutputPath`）,返回给模型的文本只包含被截断的尾部加上"完整输出见 `fullOutputPath`"的提示——这与 `read` 工具"截断 + 续读指引"的思路一脉相承,都是在"喂给模型的 token 预算"和"不丢失信息"之间找平衡。
- **会话环境变量注入**：`resolveSpawnContext` 会把 `PI_SESSION_ID`、`PI_PROVIDER`、`PI_MODEL` 等环境变量注入子进程（除非 `exposeSessionEnvironment: false`）,这样 shell 脚本可以感知自己是被哪个模型、哪个会话调用的。
- **超时与退出码的区分处理**：超时（`timeout:${timeout}`）、被中止（`aborted`）、非零退出码三种情况都会被转换成 `throw new Error(...)`,最终被上一节讲的 `executePreparedToolCall` 统一 catch 成 `isError: true` 的工具结果,模型能看到具体是哪种失败。

### 执行失败/异常的完整路径总结

汇总本篇涉及的所有异常处理点：

| 异常来源 | 处理位置 | 结果 |
|---|---|---|
| 工具名不存在 | `prepareToolCall` | 立即返回错误结果,不执行 |
| 参数校验失败(`validateToolArguments` 抛错) | `prepareToolCall` 的 `catch` | 立即返回错误结果,附带字段级错误信息 |
| `beforeToolCall` 返回 `block: true` | `prepareToolCall` | 立即返回错误结果,`reason` 作为错误文本;可选 `terminate` 提前收尾整批 |
| 用户/系统中止(`signal.aborted`) | `prepareToolCall`、`executePreparedToolCall` | 返回 "Operation aborted" 错误结果 |
| `tool.execute()` 内部抛异常 | `executePreparedToolCall` 的 `catch` | 异常消息转为错误结果 |
| `afterToolCall` 钩子自身抛异常 | `finalizeExecutedToolCall` 的 `catch` | 覆盖为错误结果,原始执行结果被丢弃 |
| assistant 消息因 token 上限被截断(`stopReason === "length"`) | `failToolCallsFromTruncatedMessage` | 该消息里的**所有** `toolCall` 全部标记失败,提示模型重新完整地发起调用 |

这张表背后是一条一致的原则：**任何异常都要转换成一条正常的 `ToolResultMessage`（`isError: true`）反馈给模型,而不是让异常向上传播打断整个 Agent 循环**。唯一的例外是 `stopReason === "length"`——此时拒绝执行**全部**工具调用,因为截断可能发生在任意一个调用的参数中间,继续执行任何一个都有跑出错误副作用的风险(比如一个被截断成 `rm -rf /tm` 的路径参数)。

## 小结与思考题

工具调用机制可以归纳为一条流水线：**模型输出 `toolCall` → 找到对应 `AgentTool` → schema 校验/参数垫片 → `beforeToolCall` 可拦截 → `execute()` 真正执行(可流式上报进度)→ `afterToolCall` 可改写结果 → 统一封装成 `ToolResultMessage` 写回上下文**。并行执行是默认策略,但只要一个工具声明了 `executionMode: "sequential"`,整批就会降级为串行;无论何种模式,写回上下文的顺序始终与模型发起调用的顺序一致。

思考题：

1. 为什么 `validateToolArguments` 要在真正执行前做"类型强转"（比如把模型传来的字符串 `"3"` 转成数字 `3`）而不是直接判为校验失败？这种宽容策略可能带来什么风险？如果你要实现一个要求"同一数据库连接的多次查询必须按发起顺序执行"的工具,又会如何利用 `executionMode` 字段？
2. `read.ts` 和 `bash.ts` 都各自实现了一套"截断 + 提示模型如何继续"的逻辑,如果要把这套逻辑抽成一个所有工具都能复用的通用能力,你会把它加在 `AgentTool` 接口的哪个环节（`execute` 内部、`afterToolCall`,还是别的地方）？
