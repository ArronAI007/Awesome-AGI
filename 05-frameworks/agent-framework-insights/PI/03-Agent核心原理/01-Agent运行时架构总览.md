# Agent 运行时架构总览

> pi 的 Agent 不是一个黑盒的"智能体框架"，而是一个分层清晰的状态机：`packages/agent` 提供无 UI、无 CLI 依赖的纯运行时"引擎"，`packages/coding-agent` 在引擎之上组装出工具、系统提示词、会话持久化和扩展系统，构成可以直接跑的"整车"。本篇从源码出发，搭出这套分层的骨架，为后面五篇的细节展开打地基。

## 学习目标

- 理解 `packages/agent`（引擎）与 `packages/coding-agent`（整车）之间的职责边界，以及为什么要这样切分。
- 掌握 `Agent` 类、`agentLoop`/`runAgentLoop` 函数、`AgentContext`/`AgentState` 等核心数据结构各自的职责。
- 能画出一次"用户输入 → 模型调用 → 工具执行 → 结果反馈 → 再次调用模型"的完整时序。
- 读懂 `types.ts` 里 `AgentMessage`、`AgentTool`、`AgentEvent` 等关键类型定义,并知道它们在真实代码路径中怎么被使用。
- 为后续「工具调用机制」「对话循环与消息状态机」「会话与持久化」「压缩」「扩展点」五篇建立统一的知识地图。

## 背景与设计动机

### 为什么要分成"引擎"和"整车"两个包

在 `/tmp/pi-repo/packages` 目录下,与 Agent 直接相关的两个包是：

- `packages/agent`（对外发布为 `@earendil-works/pi-agent-core`）：只关心"给定一段对话上下文和一组工具,如何驱动模型对话、执行工具、产出事件流"。它不知道什么是终端 UI、什么是 `.pi/` 配置目录、什么是 `read`/`bash` 这些具体工具的实现——它只认识抽象的 `AgentTool` 接口。
- `packages/coding-agent`（对外发布为 `@earendil-works/pi-coding-agent`，也就是 `pi` CLI 的核心）：在 `packages/agent` 之上,把 `read`、`bash`、`edit`、`write` 等具体工具（见 `packages/coding-agent/src/core/tools/`）、系统提示词构建（`system-prompt.ts`）、会话持久化（`session-manager.ts`）、扩展系统（`extensions/`）、TUI 渲染都组装起来,变成一个可以在终端里跑的编码助手。

这不是随意的模块划分,而是一种关注点分离：`agent-loop.ts` 里一行注释点明了这个设计的核心约束——

```typescript
// packages/agent/src/agent-loop.ts
/**
 * Agent loop that works with AgentMessage throughout.
 * Transforms to Message[] only at the LLM call boundary.
 */
```

也就是说,循环内部全程使用可扩展的 `AgentMessage` 联合类型（可以是纯 LLM 消息,也可以是 `packages/coding-agent` 自定义的 `bashExecution`、`custom` 等消息类型）,只有在真正要调用 LLM 的那一刻才收窄成 `pi-ai` 认识的 `Message[]`。这样一来,`packages/agent` 就不需要知道 `packages/coding-agent` 定义了哪些自定义消息类型,`packages/coding-agent` 也可以随意扩展消息种类而不用改动底层循环逻辑。这是通过 TypeScript 的**声明合并（declaration merging）**实现的（见 `packages/agent/src/types.ts` 的 `CustomAgentMessages` 接口,以及 `packages/coding-agent/src/core/messages.ts` 里对它的扩展,细节在下一篇展开）。

### 引擎能单独复用吗

能。`packages/agent` 对 Node.js 运行时的依赖被隔离在 `node.ts` 一个文件里：

```typescript
// packages/agent/src/node.ts
export { NodeExecutionEnv } from "./harness/env/nodejs.ts";
export * from "./index.ts";
```

`index.ts` 是包的主入口,不含任何 Node 专属 API,理论上可以在其他 JS 运行时（比如浏览器、Workers）中运行 Agent 循环本身,只要提供了合适的 `streamFn`。这也是为什么 `packages/agent` 里还有一个 `proxy.ts`——它实现了一个"通过服务器代理调用 LLM"的 `StreamFn`,用于客户端不直接持有 API Key、而是把请求转发给后端网关的场景（Web 客户端 `packages/client` 就是这么用的）。

## 核心机制详解

### 数据结构地图

`packages/agent/src/types.ts` 定义了整个引擎的"词汇表"。先看最基础的三个：

```typescript
// packages/agent/src/types.ts
/** Context snapshot passed into the low-level agent loop. */
export interface AgentContext {
	/** System prompt included with the request. */
	systemPrompt: string;
	/** Transcript visible to the model. */
	messages: AgentMessage[];
	/** Tools available for this run. */
	tools?: AgentTool<any>[];
}
```

`AgentContext` 就是"这一次要发给模型看的完整状态"：系统提示词、迄今为止的对话记录、当前可用的工具列表。它是一个**快照**——`agentLoop` 每次运行都会基于当前状态构造一份新的 `AgentContext`,而不是持有一个可变的全局对象,这与用户全局规则里"不可变优先"的原则是一致的。

```typescript
export type AgentMessage = Message | CustomAgentMessages[keyof CustomAgentMessages];
```

`AgentMessage` 是 `pi-ai` 的标准 `Message`（`UserMessage | AssistantMessage | ToolResultMessage`）再加上宿主应用通过声明合并注入的自定义消息类型的并集。引擎本身只对标准 `Message` 有特殊处理（比如判断 `role === "assistant"` 来做校验）,自定义类型会原样在 `messages` 数组里流转,直到 `convertToLlm` 把它们转成标准消息或过滤掉。

```typescript
/** Tool definition used by the agent runtime. */
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

`AgentTool` 扩展了 `pi-ai` 里最基础的 `Tool<TParameters>`（只有 `name`/`description`/`parameters` 三个字段,用于告诉模型"这个工具长什么样"）,加上了运行时才需要的部分：`execute` 函数、可选的参数预处理钩子 `prepareArguments`、以及并行/串行执行模式的声明 `executionMode`。这是引擎层和"整车"层的关键契合点——`packages/coding-agent/src/core/tools/read.ts` 等具体工具最终都会被包装成这个接口（下一篇详细拆解）。

再看运行时状态：

```typescript
/** Public agent state. */
export interface AgentState {
	systemPrompt: string;
	model: Model<any>;
	thinkingLevel: ThinkingLevel;
	set tools(tools: AgentTool<any>[]);
	get tools(): AgentTool<any>[];
	set messages(messages: AgentMessage[]);
	get messages(): AgentMessage[];
	readonly isStreaming: boolean;
	readonly streamingMessage?: AgentMessage;
	readonly pendingToolCalls: ReadonlySet<string>;
	readonly errorMessage?: string;
}
```

`AgentState` 是 `Agent` 类对外暴露的"当前状态"视图。注意 `tools` 和 `messages` 用的是 getter/setter 而非普通字段——`agent.ts` 里的实现在 setter 里做了 `.slice()` 拷贝：

```typescript
// packages/agent/src/agent.ts
set tools(nextTools: AgentTool<any>[]) {
	tools = nextTools.slice();
},
...
set messages(nextMessages: AgentMessage[]) {
	messages = nextMessages.slice();
},
```

这保证了外部代码把一个数组赋值给 `agent.state.tools = myTools` 之后,`myTools` 这个原始数组的后续修改不会"悄悄"影响到 Agent 内部状态,是防止引用逃逸导致的隐式副作用的一个具体实践。

最后是事件类型,它是 UI 层（无论是 TUI、RPC 还是 Web 客户端）观察 Agent 内部发生了什么的唯一渠道：

```typescript
export type AgentEvent =
	| { type: "agent_start" }
	| { type: "agent_end"; messages: AgentMessage[] }
	| { type: "turn_start" }
	| { type: "turn_end"; message: AgentMessage; toolResults: ToolResultMessage[] }
	| { type: "message_start"; message: AgentMessage }
	| { type: "message_update"; message: AgentMessage; assistantMessageEvent: AssistantMessageEvent }
	| { type: "message_end"; message: AgentMessage }
	| { type: "tool_execution_start"; toolCallId: string; toolName: string; args: any }
	| { type: "tool_execution_update"; toolCallId: string; toolName: string; args: any; partialResult: any }
	| { type: "tool_execution_end"; toolCallId: string; toolName: string; result: any; isError: boolean };
```

这是一个三层的生命周期嵌套：`agent`（一整次 `prompt()`/`continue()` 调用）包含若干 `turn`（一次模型回复 + 该回复引发的工具调用）,`turn` 内部又包含若干 `message`（用户消息、助手消息、工具结果消息）的开始/更新/结束,以及并行发生的 `tool_execution` 生命周期。下一篇会深入 `tool_execution_*` 系列事件,第三篇会深入 `message_*` 系列事件。

### `Agent` 类:有状态的引擎外壳

`agent-loop.ts` 里的 `agentLoop`/`runAgentLoop` 是**无状态**的纯函数式循环——给定 `prompts` 和 `context`,跑完返回新增的消息列表。而 `agent.ts` 里的 `Agent` 类是这层纯函数之上的**有状态封装**,它持有会话记录、当前模型、当前思考级别,并对外暴露 `prompt()`、`continue()`、`steer()`、`followUp()`、`abort()` 等更符合直觉的 API：

```typescript
// packages/agent/src/agent.ts
export class Agent {
	private _state: MutableAgentState;
	private readonly listeners = new Set<(event: AgentEvent, signal: AbortSignal) => Promise<void> | void>();
	private readonly steeringQueue: PendingMessageQueue;
	private readonly followUpQueue: PendingMessageQueue;
	...
}
```

`Agent` 构造函数里最重要的一步是把用户传入的各种回调（`beforeToolCall`、`afterToolCall`、`shouldStopAfterTurn`、`convertToLlm` 等）保存下来,在每次运行时通过 `createLoopConfig()` 组装成一份 `AgentLoopConfig` 传给底层的 `runAgentLoop`：

```typescript
private createLoopConfig(options: { skipInitialSteeringPoll?: boolean } = {}): AgentLoopConfig {
	...
	return {
		model: this._state.model,
		reasoning: this._state.thinkingLevel === "off" ? undefined : this._state.thinkingLevel,
		sessionId: this.sessionId,
		...
		beforeToolCall: this.beforeToolCall,
		afterToolCall: this.afterToolCall,
		shouldStopAfterTurn: shouldStopAfterTurn
			? async (context) => await shouldStopAfterTurn(context, this.signal)
			: undefined,
		convertToLlm: this.convertToLlm,
		transformContext: this.transformContext,
		getSteeringMessages: async () => { ... },
		getFollowUpMessages: async () => this.followUpQueue.drain(),
	};
}
```

也就是说：`Agent` 类本身不实现任何"决策逻辑",它只是把状态（当前模型、当前消息列表、待处理队列）翻译成配置对象,真正的循环推进逻辑全部委托给 `agent-loop.ts` 里的纯函数。这是一个典型的"状态对象 + 无状态算法"分层,好处是 `agent-loop.ts` 的核心流程可以脱离 `Agent` 类被单独测试和复用（`packages/coding-agent` 里的 `AgentSession` 正是这样直接持有一个 `Agent` 实例,再在其上叠加会话持久化和扩展钩子,细节见第四、六篇）。

`packages/coding-agent` 里 `AgentSession` 与 `Agent` 的关系,是本篇提到的"整车装引擎"的一个直接例证——`AgentSession` 构造时会拿到一个已经配置好的 `Agent` 实例：

```typescript
// packages/coding-agent/src/core/agent-session.ts
export class AgentSession {
	readonly agent: Agent;
	readonly sessionManager: SessionManager;
	...
	constructor(config: AgentSessionConfig) {
		this.agent = config.agent;
		this.sessionManager = config.sessionManager;
		...
		this._unsubscribeAgent = this.agent.subscribe(this._handleAgentEvent);
		this._installAgentToolHooks();
		...
	}
}
```

`AgentSession` 通过 `agent.subscribe()` 监听所有 `AgentEvent`,用来做会话落盘（第四篇）、自动压缩触发（第五篇）；通过给 `agent.beforeToolCall`/`agent.afterToolCall` 赋值,把扩展系统的 `tool_call`/`tool_result` 事件（第六篇）接入到引擎的工具执行钩子上。整车的每一项能力,几乎都能在引擎暴露的这几个扩展点上找到对应的挂载方式。

## 关键代码解读

### 一次完整对话的时序

以下是"用户输入一句话 → 模型可能调用工具 → 工具结果喂回模型 → 最终产出回复"的完整链路,对照 `packages/agent/src/agent-loop.ts` 里的 `runLoop`：

```text
User                 Agent 类                agent-loop.ts (runLoop)         LLM Provider          Tool
 |                      |                            |                          |                  |
 | prompt("修复bug")     |                            |                          |                  |
 |--------------------->|                            |                          |                  |
 |                      | runAgentLoop(prompts, ctx) |                          |                  |
 |                      |--------------------------->|                          |                  |
 |                      |                            | emit(agent_start)        |                  |
 |                      |                            | emit(turn_start)         |                  |
 |                      |                            | emit(message_start/end)  |  (echo 用户消息) |                  |
 |                      |                            |                          |                  |
 |                      |                            | streamAssistantResponse()|                  |
 |                      |                            |------------------------->|                  |
 |                      |                            |   emit(message_start)    |  流式返回 text/  |                  |
 |                      |                            |<--text_delta/tool_call---|  toolCall 片段    |                  |
 |                      |                            |   emit(message_update)*N |                  |                  |
 |                      |                            |<---- done/error ---------|                  |
 |                      |                            |   emit(message_end)      |                  |                  |
 |                      |                            |                          |                  |
 |                      |                            | 发现 toolCall            |                  |                  |
 |                      |                            | executeToolCalls()------------------------->|
 |                      |                            |   emit(tool_execution_start)                |  执行 read/bash/…  |
 |                      |                            |<----------------------- 结果 ----------------|
 |                      |                            |   emit(tool_execution_end)                  |
 |                      |                            |   emit(message_start/end) (toolResult 消息)  |
 |                      |                            |                          |                  |
 |                      |                            | emit(turn_end)           |                  |
 |                      |                            | hasMoreToolCalls? 是 → 回到循环开头再次请求模型 |
 |                      |                            | 否 → emit(agent_end)     |                  |
 |                      |<---------------------------|                          |                  |
 |<---回调 listener------|                            |                          |                  |
```

这张图对应的正是 `runLoop` 函数体的结构（`packages/agent/src/agent-loop.ts` 第 155-275 行）,其核心是一个**双层循环**：

```typescript
// packages/agent/src/agent-loop.ts（节选,含省略）
while (true) {
	let hasMoreToolCalls = true;

	while (hasMoreToolCalls || pendingMessages.length > 0) {
		// 1. 注入 steering 消息(用户在模型思考时插话)
		// 2. 调用模型,拿到一条 assistant 消息
		const message = await streamAssistantResponse(currentContext, config, signal, emit, streamFunction);
		newMessages.push(message);

		if (message.stopReason === "error" || message.stopReason === "aborted") {
			await emit({ type: "turn_end", message, toolResults: [] });
			await emit({ type: "agent_end", messages: newMessages });
			return;
		}

		// 3. 从 assistant 消息里取出 toolCall 内容块
		const toolCalls = message.content.filter((c) => c.type === "toolCall");
		const toolResults: ToolResultMessage[] = [];
		hasMoreToolCalls = false;
		if (toolCalls.length > 0) {
			const executedToolBatch =
				message.stopReason === "length"
					? await failToolCallsFromTruncatedMessage(toolCalls, emit)
					: await executeToolCalls(currentContext, message, config, signal, emit);
			toolResults.push(...executedToolBatch.messages);
			hasMoreToolCalls = !executedToolBatch.terminate;
			for (const result of toolResults) {
				currentContext.messages.push(result);
				newMessages.push(result);
			}
		}

		await emit({ type: "turn_end", message, toolResults });
		// 4. shouldStopAfterTurn / prepareNextTurn 钩子,决定是否继续、是否换模型
		// 5. 拉取新的 steering 消息,若有则继续内层循环
	}

	// 内层循环退出意味着"这一轮没有工具调用、也没有待处理消息"
	// 6. 检查是否有 follow-up 消息排队,有的话继续外层循环
	const followUpMessages = (await config.getFollowUpMessages?.()) || [];
	if (followUpMessages.length > 0) {
		pendingMessages = followUpMessages;
		continue;
	}
	break;
}
await emit({ type: "agent_end", messages: newMessages });
```

内层循环的终止条件是`!hasMoreToolCalls && pendingMessages.length === 0`——即模型这次回复没有工具调用（真正说完了话）,且没有排队的 steering 消息。外层循环则用于处理"agent 已经打算收尾,但这时候有 follow-up 消息排队"的场景（比如用户在等待过程中又发了一条新消息,选择让它在当前回合真正结束后才被处理,而不是打断当前回合）。`hasMoreToolCalls` 还受 `executedToolBatch.terminate` 影响——如果所有工具结果都标记了 `terminate: true`（例如被 `beforeToolCall` 钩子拦截并要求提前终止）,即便还有后续工具调用逻辑上"应该"继续,循环也会提前退出。

### `streamAssistantResponse`:从事件流到一条完整消息

```typescript
// packages/agent/src/agent-loop.ts
async function streamAssistantResponse(
	context: AgentContext,
	config: AgentLoopConfig,
	signal: AbortSignal | undefined,
	emit: AgentEventSink,
	streamFunction: StreamFn,
): Promise<AssistantMessage> {
	let messages = context.messages;
	if (config.transformContext) {
		messages = await config.transformContext(messages, signal);
	}
	const llmMessages = await config.convertToLlm(messages);
	const llmContext: Context = { systemPrompt: context.systemPrompt, messages: llmMessages, tools: context.tools };
	const resolvedApiKey =
		(config.getApiKey ? await config.getApiKey(config.model.provider) : undefined) || config.apiKey;
	const response = await streamFunction(config.model, llmContext, { ...config, apiKey: resolvedApiKey, signal });

	let partialMessage: AssistantMessage | null = null;
	let addedPartial = false;
	for await (const event of response) {
		switch (event.type) {
			case "start":
				partialMessage = event.partial;
				context.messages.push(partialMessage);
				addedPartial = true;
				await emit({ type: "message_start", message: { ...partialMessage } });
				break;
			case "text_start": case "text_delta": case "text_end":
			case "thinking_start": case "thinking_delta": case "thinking_end":
			case "toolcall_start": case "toolcall_delta": case "toolcall_end":
				if (partialMessage) {
					partialMessage = event.partial;
					context.messages[context.messages.length - 1] = partialMessage;
					await emit({ type: "message_update", assistantMessageEvent: event, message: { ...partialMessage } });
				}
				break;
			case "done": case "error": {
				const finalMessage = await response.result();
				// ...落地 finalMessage,emit message_end,return
			}
		}
	}
	// ...
}
```

这个函数体现了"引擎只认识 `AgentMessage[]`,只在调用模型这一刻转成 `Message[]`"的边界:先经过可选的 `transformContext`（AgentMessage 级别的裁剪/注入,第五篇压缩正是挂在这里）,再经过 `convertToLlm`（收窄成标准 `Message[]`,第三篇详细讲各种自定义消息如何被转换）,然后调用 `streamFunction`——也就是下一节要讲的 `StreamFn`,得到一个异步事件流并逐步把 `partialMessage` 更新进 `context.messages` 的最后一个元素、同时对外 `emit` 出 `message_update` 事件供 UI 实时渲染打字机效果。这条链路正是第三篇「对话循环与消息状态机」要深入的部分。

### `StreamFn`:引擎与具体 LLM Provider 的唯一接缝

```typescript
// packages/agent/src/types.ts
export type StreamFn = (
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
) => AssistantMessageEventStream | Promise<AssistantMessageEventStream>;
```

引擎不关心 `streamFn` 内部是直接调用 Anthropic/OpenAI API,还是像 `packages/agent/src/proxy.ts` 里的 `streamProxy` 那样把请求转发给自建后端网关。`stream-fn.ts` 只提供了一个全局默认值的存取器：

```typescript
// packages/agent/src/stream-fn.ts
let defaultStreamFn: StreamFn | undefined;

export function setDefaultStreamFn(streamFn: StreamFn | undefined): void {
	defaultStreamFn = streamFn;
}

export function getDefaultStreamFn(): StreamFn {
	if (!defaultStreamFn) {
		throw new Error("No default stream function configured. Pass streamFn explicitly or call setDefaultStreamFn().");
	}
	return defaultStreamFn;
}
```

`packages/coding-agent` 在启动时会调用 `setDefaultStreamFn()` 注入真正对接多家模型 Provider 的实现（`@earendil-works/pi-ai` 里的 `streamSimple`,详见第四模块「多模型统一层 pi-ai」）。这一层解耦意味着：只要实现符合 `StreamFn` 契约的函数（文档注释明确要求"不能抛异常,失败必须编码进返回的事件流里,以 `stopReason: "error"|"aborted"` 收尾"）,就可以把 pi 的 Agent 引擎接到任意模型后端上,`streamProxy` 就是一个官方给出的范例实现。

## 小结与思考题

本篇建立了三个层次的心智模型：

1. **类型层**（`types.ts`）：`AgentContext`/`AgentMessage`/`AgentTool`/`AgentState`/`AgentEvent` 构成了整个引擎的词汇表,`AgentMessage` 通过声明合并对上层开放扩展。
2. **循环层**（`agent-loop.ts`）：`runLoop` 双层循环驱动"模型响应 → 工具执行 → 再次响应"的推进,`streamAssistantResponse` 是引擎与 `StreamFn` 唯一的接缝。
3. **外壳层**（`agent.ts`）：`Agent` 类把无状态的循环函数包装成有状态、可订阅、可 steer/follow-up 的对象,是 `packages/coding-agent` 组装"整车"时直接持有的引擎实例。

思考题：

1. 如果你要给 pi 增加一种全新的 `AgentMessage` 类型（比如一种"系统告警"消息）,需要修改 `packages/agent` 的哪些文件？为什么理想情况下应该是零修改,只需要在 `packages/coding-agent` 里做声明合并和 `convertToLlm` 扩展?
2. `runLoop` 里外层循环（处理 follow-up）和内层循环（处理 steering + tool calls）为什么要分成两层而不是合并成一层？如果合并会有什么问题？
3. `Agent.reset()` 方法里为什么要先检查 `this.activeRun` 是否存在、存在就抛错？这体现了什么并发安全约束？
