# 统一 LLM 接口设计原理

> `@earendil-works/pi-ai`（`packages/ai`）用一套与厂商无关的消息、工具调用、流式事件类型，把 OpenAI、Anthropic、Google、Bedrock 等十几种各自为政的 API 协议，统一成一份类型安全的 TypeScript 接口，让上层的 Agent 运行时完全不用关心"这次请求到底是谁在回答"。

## 学习目标

- 理解为什么多 Provider LLM 应用必须有一层统一抽象，而不是在业务代码里 if-else 分支处理每家 API。
- 读懂 `packages/ai/src/types.ts` 中 `Message`、`AssistantMessage`、`Tool`、`Model<TApi>` 等核心类型的真实定义与设计意图。
- 理解 `AssistantMessageEvent` 这套统一流式事件协议如何屏蔽不同厂商 SSE / WebSocket 协议的差异。
- 看懂 `packages/ai/src/index.ts` 的导出边界，明白 pi-ai 把"核心类型"、"Provider 工厂"、"API 实现"、"兼容层"拆成了几个独立的导入路径。
- 能画出一次 `stream()` 调用从统一接口到具体厂商协议的转换链路。

## 背景与设计动机

### 问题：每家 LLM API 都不一样

如果你直接对接过两家以上的 LLM 服务商，会很快撞到三类差异：

1. **消息格式不同**。OpenAI Responses API 用 `input` 数组和 `role: "developer"`；Anthropic Messages API 用 `system` 字段单独放系统提示词、`content` 里混排文本块和工具调用块；Google Generative AI 用 `contents` + `parts`；AWS Bedrock Converse API 又是另一套 `ContentBlock` 联合类型（见下一篇 Provider 适配器剖析里对 `bedrock-converse-stream.ts` 的详细分析）。
2. **工具调用（tool call）格式不同**。有的厂商把工具定义放在请求顶层的 `tools` 字段，有的要求 JSON Schema 必须标记 `strict`；工具返回结果有的用独立的 `tool` 角色消息，有的要求紧跟在助手消息后面。
3. **流式协议不同**。OpenAI 用 SSE 逐 token 推送 `delta`；Anthropic 用 `content_block_start/delta/stop` 三段式事件；Bedrock Converse Stream 走 AWS SDK 的 `ConverseStreamCommand`，返回的是 `contentBlockStart/contentBlockDelta/contentBlockStop/messageStop/metadata` 这样的事件流（见 `packages/ai/src/api/bedrock-converse-stream.ts:263-295`）。

如果不做统一层，Agent 运行时（`packages/agent`）、Coding Agent CLI（`packages/coding-agent`）等每一个消费者都要重新学习并适配这些差异，厂商一升级 API，所有消费者都要跟着改。pi-ai 把这些差异全部收敛到 `packages/ai/src/api/*.ts` 这一层 Provider 适配器内部，对外只暴露一套统一类型。

### 设计取舍：类型驱动而不是运行时探测

pi-ai 没有选择"运行时反射不同 Provider 的响应结构"，而是用 TypeScript 的可辨识联合（discriminated union）和映射类型（mapped types），在编译期就把"这是哪个 API"（`Api`）、"这个 Model 支持哪些 Option"（`ApiStreamOptions<TApi>`）关联起来。这样调用方写错了 API 特有的参数会在编译期报错，而不是等到运行时请求失败。

## 核心机制详解

### 1. 统一的消息类型：`Message`

`packages/ai/src/types.ts` 定义了三种消息角色，构成一次对话的完整历史：

```ts
// packages/ai/src/types.ts:409-455
export interface UserMessage {
	role: "user";
	content: string | (TextContent | ImageContent)[];
	timestamp: number;
}

export interface AssistantMessage {
	role: "assistant";
	content: (TextContent | ThinkingContent | ToolCall)[];
	api: Api;
	provider: ProviderId;
	model: string;
	usage: Usage;
	stopReason: StopReason;
	errorMessage?: string;
	timestamp: number;
}

export interface ToolResultMessage<TDetails = any> {
	role: "toolResult";
	toolCallId: string;
	toolName: string;
	content: (TextContent | ImageContent)[];
	isError: boolean;
	timestamp: number;
}

export type Message = UserMessage | AssistantMessage | ToolResultMessage;
```

注意几个关键设计：

- `AssistantMessage` 上直接带着 `api`、`provider`、`model` 三个字段——每一条助手消息都"自带来源标签"，这样多轮对话中途切换模型（比如从 Anthropic 切到 Bedrock 上的 Claude）也能被完整记录和回放。
- `content` 是一个联合类型数组，同一条助手消息里可以混排纯文本（`TextContent`）、推理过程（`ThinkingContent`，对应"思维链"/reasoning）、工具调用（`ToolCall`）。这直接对应了现代推理模型（如 Claude 的 extended thinking、OpenAI 的 reasoning）在一次回复里既要"想"又要"说"又要"调工具"的真实情况。
- `ToolResultMessage` 里的 `content` 同样支持 `TextContent | ImageContent`，因为有些工具（比如截图、浏览器操作）返回的是图片而不是文本。

### 2. 内容块类型：文本、思考、图片、工具调用

```ts
// packages/ai/src/types.ts:338-368
export interface TextContent {
	type: "text";
	text: string;
	textSignature?: string;
}

export interface ThinkingContent {
	type: "thinking";
	thinking: string;
	thinkingSignature?: string;
	redacted?: boolean;
}

export interface ImageContent {
	type: "image";
	data: string; // base64 编码的图片数据
	mimeType: string;
}

export interface ToolCall {
	type: "toolCall";
	id: string;
	name: string;
	arguments: Record<string, any>;
	thoughtSignature?: string; // Google 专用：复用思考上下文的不透明签名
	namespace?: string; // OpenAI Responses 命名空间工具专用
}
```

这里的 `textSignature`、`thinkingSignature`、`thoughtSignature` 都是"厂商专属但必须原样保留的不透明字段"——比如 Anthropic 要求把 `thinking` 块的签名原样传回去才能在多轮对话里复用同一段推理上下文；Google 用 `thoughtSignature` 做类似的事情。pi-ai 的做法不是把这些字段抹平（会丢信息），而是保留在统一类型里但标记为可选，各 Provider 适配器只用自己认识的那个字段。

### 3. 用量与终止原因：`Usage` / `StopReason`

```ts
// packages/ai/src/types.ts:370-393
export interface Usage {
	input: number;
	output: number;
	cacheRead: number;
	cacheWrite: number;
	cacheWrite1h?: number;
	reasoning?: number;
	totalTokens: number;
	cost: { input: number; output: number; cacheRead: number; cacheWrite: number; total: number };
}

export type StopReason = "pending" | "stop" | "length" | "toolUse" | "error" | "aborted" | "deferred";
```

`StopReason` 是一个只有 7 个取值的封闭联合类型。不管底层是 Bedrock 的 `BedrockStopReason.END_TURN`，还是 OpenAI 的 `finish_reason: "stop"`，还是 Anthropic 的 `stop_reason: "end_turn"`，Provider 适配器都要把它们**收窄映射**到这 7 个值之一。以 Bedrock 为例：

```ts
// packages/ai/src/api/bedrock-converse-stream.ts:1019-1034
function mapStopReason(reason: string | undefined): { stopReason: StopReason; errorMessage?: string } {
	switch (reason) {
		case BedrockStopReason.END_TURN:
		case BedrockStopReason.STOP_SEQUENCE:
			return { stopReason: "stop" };
		case BedrockStopReason.MAX_TOKENS:
		case BedrockStopReason.MODEL_CONTEXT_WINDOW_EXCEEDED:
			return { stopReason: "length" };
		case BedrockStopReason.TOOL_USE:
			return { stopReason: "toolUse" };
		default:
			return reason ? { stopReason: "error", errorMessage: `Provider stopped with: ${reason}` } : { stopReason: "error" };
	}
}
```

这样，Agent 运行时里判断"要不要继续调工具"只需要检查 `stopReason === "toolUse"`，完全不用知道这是哪家厂商返回的。

### 4. `Model<TApi>`：把 API 类型和厂商能力绑在一起

```ts
// packages/ai/src/types.ts:794-823（节选）
export interface Model<TApi extends Api> {
	id: string;
	name: string;
	api: TApi;
	provider: ProviderId;
	baseUrl: string;
	reasoning: boolean;
	thinkingLevelMap?: ThinkingLevelMap;
	input: ("text" | "image")[];
	cost: ModelCost;
	contextWindow: number;
	maxTokens: number;
	samplingParams?: Record<string, unknown>;
	compat?: TApi extends "openai-completions"
		? OpenAICompletionsCompat
		: TApi extends "openai-responses" | "azure-openai-responses" | "openai-codex-responses"
			? OpenAIResponsesCompat
			: TApi extends "anthropic-messages"
				? AnthropicMessagesCompat
				: TApi extends "bedrock-converse-stream"
					? BedrockCompat
					: never;
}
```

这是一个泛型接口，`TApi` 是一个受 `Api` 约束的类型参数。`compat` 字段用条件类型（conditional types）把"这个模型用哪种 API 协议"和"这种协议特有的兼容性开关"绑定在一起——比如只有 `openai-completions` 协议的模型才会有 `OpenAICompletionsCompat`（`supportsStore`、`thinkingFormat` 等字段，下一篇会展开讲这些字段如何被 `generate-models.ts` 自动推断）。这样调用方拿到一个 `Model<"bedrock-converse-stream">` 时，TypeScript 能自动收窄 `compat` 的类型为 `BedrockCompat`，写错字段名会直接编译报错。

### 5. 统一流式事件协议：`AssistantMessageEvent`

这是整个统一层里最关键的抽象。不管底层协议怎么推事件，Provider 适配器最终都要把响应"翻译"成下面这套可辨识联合类型：

```ts
// packages/ai/src/types.ts:523-539
export type AssistantMessageEvent =
	| { type: "start"; partial: AssistantMessage }
	| { type: "text_start"; contentIndex: number; partial: AssistantMessage }
	| { type: "text_delta"; contentIndex: number; delta: string; partial: AssistantMessage }
	| { type: "text_end"; contentIndex: number; content: string; partial: AssistantMessage }
	| { type: "thinking_start"; contentIndex: number; partial: AssistantMessage }
	| { type: "thinking_delta"; contentIndex: number; delta: string; partial: AssistantMessage }
	| { type: "thinking_end"; contentIndex: number; content: string; partial: AssistantMessage }
	| { type: "toolcall_start"; contentIndex: number; partial: AssistantMessage }
	| { type: "toolcall_delta"; contentIndex: number; delta: string; partial: AssistantMessage }
	| { type: "toolcall_end"; contentIndex: number; toolCall: ToolCall; partial: AssistantMessage }
	| { type: "done"; reason: Extract<StopReason, "stop" | "length" | "toolUse" | "deferred">; message: AssistantMessage }
	| { type: "error"; reason: Extract<StopReason, "aborted" | "error">; error: AssistantMessage };
```

代码注释里写明了协议契约（`types.ts:515-521`）："流必须先推 `start`，再推若干增量事件，最后以 `done`（携带最终成功的 `AssistantMessage`）或 `error`（携带 `stopReason` 为 `error`/`aborted` 且带 `errorMessage` 的 `AssistantMessage`）终止。"

这意味着：无论 Bedrock 用的是 AWS SDK 的 `contentBlockDelta` 事件，还是 OpenAI 用的是 SSE 的 `response.output_text.delta`，Provider 适配器的职责就是一个"事件翻译器"——把厂商自己的事件流逐个映射成上面这 12 种统一事件之一，再推入 pi-ai 自己的 `AssistantMessageEventStream`（定义在 `packages/ai/src/utils/event-stream.ts`，本篇不展开）。下一篇会具体看 Bedrock 适配器里 `handleContentBlockDelta` 等函数是怎么做这个翻译的。

### 6. `StreamFunction` 与按 API 精确类型化的 Options

```ts
// packages/ai/src/types.ts:320-324
export type StreamFunction<TApi extends Api = Api, TOptions extends StreamOptions = StreamOptions> = (
	model: Model<TApi>,
	context: Context,
	options?: TOptions,
) => AssistantMessageEventStream;
```

每一种 API 实现模块（`packages/ai/src/api/*.ts`）都必须导出符合 `ProviderStreams` 形状的 `stream` 和 `streamSimple` 两个函数：

```ts
// packages/ai/src/types.ts:268-277
export interface ProviderStreams {
	stream(model: Model<Api>, context: Context, options?: StreamOptions): AssistantMessageEventStream;
	streamSimple(model: Model<Api>, context: Context, options?: SimpleStreamOptions): AssistantMessageEventStream;
	fetchDeferred?(model: Model<Api>, handle: DeferredHandle, options?: DeferredFetchOptions): AssistantMessageEventStream;
	cancelDeferred?(model: Model<Api>, handle: DeferredHandle, options?: DeferredCancelOptions): Promise<void>;
}
```

`stream` 是"完全暴露厂商专属参数"的低层接口（比如 Bedrock 的 `BedrockOptions` 带 `region`、`profile`、`toolChoice` 等字段）；`streamSimple` 则是"跨厂商统一的推理等级"接口，用 `reasoning?: ThinkingLevel`（`"minimal" | "low" | "medium" | "high" | "xhigh" | "max"`）这个统一枚举来控制推理强度，具体怎么映射成每家 API 自己的参数格式，由适配器内部完成（下一篇会看到 Bedrock 的 `streamSimple` 如何把统一的 `reasoning` 换算成 Claude 的 `thinking.budget_tokens`）。

`ApiOptionsMap` 把已知 API 和它们各自的 Options 类型一一对应起来：

```ts
// packages/ai/src/types.ts:239-258（节选）
export interface ApiOptionsMap {
	"anthropic-messages": AnthropicOptions;
	"openai-completions": OpenAICompletionsOptions;
	"bedrock-converse-stream": BedrockOptions;
	// ...
}

export type ApiStreamOptions<TApi extends Api> = TApi extends keyof ApiOptionsMap
	? ApiOptionsMap[TApi]
	: StreamOptions & Record<string, unknown>;
```

这是一个条件类型 + 索引访问类型的组合：已知的 10 种 API（见 `KnownApi`）会精确解析出各自的 Options 类型；自定义/未知的 API 字符串（`Api = KnownApi | (string & {})`，这是一个"开放字符串字面量"技巧，允许运行时扩展自定义 Provider 而不破坏类型系统）则退化为通用的 `StreamOptions`。

### 7. `index.ts` 的导出边界：核心与外围分离

```ts
// packages/ai/src/index.ts:4-8（注释原文）
// Core only, side-effect free: no generated catalogs, no provider factories,
// no api-registry, no OAuth implementations, no compat. Provider factories
// live under "@earendil-works/pi-ai/providers/*", API implementations under
// "@earendil-works/pi-ai/api/*", the old global API under
// "@earendil-works/pi-ai/compat".
```

`packages/ai/src/index.ts`（对应包的默认导入路径 `@earendil-works/pi-ai`）只导出：类型定义（`types.ts`）、鉴权基础设施（`auth/*`）、模型集合的运行时容器（`models.ts`、`models-store.ts`）、各 API 模块的 Option 类型（仅类型，不含实现）、以及少量工具函数（`utils/*`）。它明确**不**包含：

- 生成的模型目录数据（`models.generated.ts` 走 `@earendil-works/pi-ai/providers/all`）；
- 具体 Provider 工厂函数（如 `amazonBedrockProvider()`，走 `@earendil-works/pi-ai/providers/*`）；
- 具体 API 协议实现（如 `bedrockConverseStreamApi()`，走 `@earendil-works/pi-ai/api/*`）；
- 历史遗留的全局单例 API（`stream()`/`complete()`/`getModel()` 等，走 `@earendil-works/pi-ai/compat`，详见下一篇）。

这样拆分导入路径的好处是**按需加载**：如果调用方只需要类型做静态检查，不需要把几十个 Provider 的模型目录、OAuth 实现全部打进最终产物。`packages/ai/src/compat.ts` 顶部的注释也印证了这一点——它是"临时的兼容入口，保留旧的全局 pi-ai API 面（`stream()`/`complete()` 加环境变量注入的 api-dispatch、api-registry、生成目录读取的 `getModel`/`getModels`/`getProviders`、按 API 的懒加载流包装器、图片生成），老应用把 import 从 `@earendil-works/pi-ai` 切到 `@earendil-works/pi-ai/compat` 就能原样运行；新代码用 `createModels()` 和 Provider 工厂。这个模块会在 coding-agent 的 ModelManager 迁移完成后删除。"

## 小结与思考题

pi-ai 的统一层不是靠运行时猜测或者字符串拼接去抹平厂商差异，而是用三层类型设计把差异**结构化**：`Message`/`Content` 联合类型统一了对话历史的形状，`StopReason`/`AssistantMessageEvent` 这两个封闭的可辨识联合把"这次回复怎么结束的"和"流式过程中发生了什么"收窄成有限的、跨厂商通用的取值集合，而 `Model<TApi>` 配合 `ApiOptionsMap`、条件类型则让"厂商专属的可选参数"依然能在类型层面被精确追踪，不会退化成 `any`。真正做协议转换脏活的代码全部下沉到 `packages/ai/src/api/*.ts` 里的具体适配器（下一篇详细拆解），统一层本身只负责定义"转换的目标形状是什么"。

思考题：

1. `Api` 类型定义为 `KnownApi | (string & {})`，而不是直接用字符串字面量联合类型 `KnownApi`。这样设计能带来什么好处？如果去掉 `(string & {})` 这部分只保留 `KnownApi`，第三方想接入一个 pi-ai 未内置支持的自定义 API（比如私有部署的模型网关）会遇到什么问题？
2. `AssistantMessage` 每次都携带 `api`/`provider`/`model` 三个字段，而不是把这些信息放在外层某个"会话元数据"对象里统一记录一次。结合多轮对话中途切换模型的场景，说说这样设计避免了什么潜在的 bug。
3. `ThinkingContent` 里的 `thinkingSignature` 和 `redacted` 字段是为了兼容哪类真实场景？如果统一层选择"直接丢弃厂商专属签名字段，只保留纯文本推理内容"，会破坏什么功能？
