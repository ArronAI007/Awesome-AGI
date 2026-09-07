# Provider 适配器实现剖析

> 以 Amazon Bedrock 为具体案例，拆解一个 pi-ai Provider 适配器真正要做的四件事——请求转换、响应转换、流式事件转换、错误映射——并顺带讲清楚 API Key 认证和 OAuth 认证这两条不同的鉴权路径是如何在同一套 `ProviderAuth` 接口下并存的。

## 学习目标

- 理解 pi-ai 里"Provider"（业务与鉴权外壳）和"API 实现"（协议转换内核）两层职责的划分，以及 `bedrock-provider.ts` 这个 6 行文件为什么长这样。
- 通读 `api/bedrock-converse-stream.ts` 的 `stream()` 函数，说清楚一次请求从 pi 统一 `Context` 到 AWS `ConverseStreamCommand` 再到统一 `AssistantMessageEvent` 的完整转换链路。
- 理解 `compat.ts` 在新旧两套架构（`createModels()`/`Provider` vs 历史遗留的全局 `stream()`/`complete()`）之间扮演的桥接角色。
- 区分 API Key 鉴权（`ApiKeyAuth`）和 OAuth 鉴权（`OAuthAuth`）在接口设计和使用场景上的本质不同，并能讲出 Anthropic OAuth（PKCE + 本地回调服务器）的具体步骤。
- 知道 `env-api-keys.ts` 是怎么从环境变量里找到每个 Provider 对应的 API Key 的。

## 背景与设计动机

上一篇讲了 pi-ai 统一层"定义了什么形状"，这一篇讲"谁来把厂商协议转换成这个形状"。pi-ai 把这件事拆成了两层：

- **API 实现层**（`packages/ai/src/api/*.ts`）：纯粹的协议转换代码，输入统一的 `Context` + `StreamOptions`，输出统一的 `AssistantMessageEventStream`。这一层不关心鉴权怎么来的、模型目录长什么样，只认"给我一个 `Model<TApi>` 和已经解析好的 `apiKey`/`headers`，我就能发请求"。
- **Provider 层**（`packages/ai/src/providers/*.ts`）：业务外壳，负责三件事——声明这个厂商有哪些模型（`models: AMAZON_BEDROCK_MODELS`）、声明怎么登录/取凭证（`auth: ProviderAuth`）、把模型列表和鉴权与某个 API 实现绑定起来（`api: bedrockConverseStreamApi()`）。

这样拆分的好处是：同一个 API 协议可能被多个 Provider 复用。比如 `anthropic-messages` 这个协议实现，除了官方 Anthropic 之外，Fireworks、OpenRouter 上的部分 Claude 模型也在走同一套 `api/anthropic-messages.ts`，只是 `baseUrl`、`compat` 兼容性开关、鉴权方式不同——这些差异被建模成 `Model.compat` 数据（上一篇提到的 `AnthropicMessagesCompat`），而不是复制一份协议实现代码。

## 核心机制详解

### 1. `bedrock-provider.ts`：一个历史遗留的薄转发文件

题面里提到的 `packages/ai/src/bedrock-provider.ts` 只有 6 行：

```ts
// packages/ai/src/bedrock-provider.ts
import { stream, streamSimple } from "./api/bedrock-converse-stream.ts";

export const bedrockProviderModule = {
	stream,
	streamSimple,
};
```

它只是把 `api/bedrock-converse-stream.ts` 导出的 `stream`/`streamSimple` 重新打包成一个 `{ stream, streamSimple }` 对象。真正定义"Amazon Bedrock 作为一个 Provider 该怎么鉴权、有哪些模型"的文件是 `packages/ai/src/providers/amazon-bedrock.ts`，这是本文重点分析的对象。看到一个几行的顶层文件时，不要假设它就是全部实现——先用 `grep`/`codegraph` 确认有没有更完整的同名或近似命名文件。

### 2. Provider 工厂：`amazonBedrockProvider()`

```ts
// packages/ai/src/providers/amazon-bedrock.ts:82-90
export function amazonBedrockProvider(): Provider<"bedrock-converse-stream"> {
	return createProvider({
		id: "amazon-bedrock",
		name: "Amazon Bedrock",
		auth: { apiKey: bedrockAuth },
		models: Object.values(AMAZON_BEDROCK_MODELS),
		api: bedrockConverseStreamApi(),
	});
}
```

`createProvider()`（定义在 `packages/ai/src/models.ts:762`）是所有内置 Provider 共用的工厂函数，它把 `id`/`name`/`auth`/`models`/`api` 这几项输入组装成一个符合 `Provider<TApi>` 接口的对象：

```ts
// packages/ai/src/models.ts:97-149（节选）
export interface Provider<TApi extends Api = Api> {
	readonly id: string;
	readonly name: string;
	readonly auth: ProviderAuth;
	getModels(): readonly Model<TApi>[];
	refreshModels?(context: RefreshModelsContext): Promise<void>;
	filterModels?(models: readonly Model<TApi>[], credential: Credential | undefined): readonly Model<TApi>[];
	stream<T extends TApi>(model: Model<T>, context: Context, options?: ApiStreamOptions<T>): AssistantMessageEventStream;
	streamSimple(model: Model<TApi>, context: Context, options?: SimpleStreamOptions): AssistantMessageEventStream;
	fetchDeferred?(...): AssistantMessageEventStream;
	cancelDeferred?(...): Promise<void>;
}
```

`createProvider()` 内部按 `model.api` 把请求分发给正确的协议实现（`api: ProviderStreams | Partial<Record<TApi, ProviderStreams>>` 这个参数既支持"一个 Provider 只用一种协议"，也支持"一个 Provider 混用多种协议"的情况，`models.ts:775-792` 的 `apiFor()`/`dispatch()` 就是做这个分发的）。Bedrock 只用一种协议，所以直接传入 `bedrockConverseStreamApi()` 这个单一实现。

### 3. API 实现层：`api/bedrock-converse-stream.ts` 的四件事

这是本文的核心。`stream()` 函数（`packages/ai/src/api/bedrock-converse-stream.ts:107-327`）做的事情可以拆成四块。

#### 3.1 请求转换：从统一 `Context` 到 AWS `ConverseStreamCommand`

`convertMessages()` 把 pi 的 `Context.messages`（`UserMessage`/`AssistantMessage`/`ToolResultMessage` 的数组）转换成 AWS SDK 要的 `Message[]`：

```ts
// packages/ai/src/api/bedrock-converse-stream.ts:817-828（节选）
function convertMessages(
	context: Context,
	model: Model<"bedrock-converse-stream">,
	cacheRetention: CacheRetention,
	env?: ProviderEnv,
): Message[] {
	const result: Message[] = [];
	const transformedMessages = transformMessages(context.messages, model, normalizeToolCallId);
	for (let i = 0; i < transformedMessages.length; i++) {
		const m = transformedMessages[i];
		switch (m.role) {
			case "user": { /* TextContent/ImageContent -> ContentBlock */ }
			case "assistant": { /* TextContent/ToolCall/ThinkingContent -> ContentBlock */ }
			case "toolResult": { /* 连续的 toolResult 消息合并进同一条 user 消息 */ }
		}
	}
	// ...
}
```

这段代码里有几个值得注意的"厂商特殊要求"：

- **工具结果必须合并**：Bedrock 要求所有 `toolResult` 内容块都放在同一条 `user` 消息里，代码用一个内层 `while` 循环向前看（look-ahead），把连续的 `toolResult` 消息合并（`bedrock-converse-stream.ts:938-953`），而 pi 统一的 `Context.messages` 里这些结果本来是分开的独立消息。
- **思考块的签名兼容性**：只有 Anthropic Claude 模型支持 `reasoningContent.reasoningText.signature` 字段（`supportsThinkingSignature()`），其它模型（OpenAI、Qwen、Minimax 等跑在 Bedrock 上时）如果带上这个字段会直接报错，所以非 Claude 模型的思考内容会退化成普通 `reasoningContent`（不带签名）甚至纯文本块。
- **空内容占位符**：Bedrock 拒绝空的文本块和空的内容数组，代码定义了 `EMPTY_TEXT_PLACEHOLDER = "<empty>"` 兜底（比如被中止请求留下的空助手消息）。
- **Prompt Cache 断点注入**：`buildSystemPrompt()` 和 `convertMessages()` 末尾都会在满足条件（Claude 3.5 Haiku / 3.7 Sonnet / 4.x / 5.x 系列，见 `supportsPromptCaching()`）时插入 `cachePoint: { type: CachePointType.DEFAULT, ... }` 内容块，把 pi 统一的 `cacheRetention: "short" | "long" | "none"` 选项翻译成 Bedrock 的缓存断点机制。

工具 Schema 的转换也在这一层完成：

```ts
// packages/ai/src/api/bedrock-converse-stream.ts:982-1000（节选）
function convertToolConfig(tools, toolChoice, supportsStrictMode): ToolConfiguration | undefined {
	if (!tools?.length) return undefined;
	const bedrockTools: BedrockTool[] = tools.map((tool) => ({
		toolSpec: {
			name: tool.name,
			description: tool.description,
			inputSchema: { json: tool.parameters as unknown as DocumentType },
			...(resolveJsonSchemaStrictSampling(tool, supportsStrictMode) === true ? { strict: true } : {}),
		},
	}));
	// toolChoice: "auto" | "any" | { type: "tool"; name } -> Bedrock 的 ToolChoice 联合类型
}
```

统一的 `Tool { name, description, parameters }`（上一篇提到的 `types.ts` 定义）被逐字段映射进 Bedrock 的 `toolSpec`。

#### 3.2 鉴权与连接参数解析

Bedrock 比大多数 HTTP API 复杂的地方在于它同时支持"AWS SDK 默认凭证链"和"Bearer Token"两种完全不同的鉴权模式，`stream()` 的前半部分（`bedrock-converse-stream.ts:140-221`）专门处理这个：

- 优先级：模型 ID 中嵌入的 ARN 区域 > 显式 `region` 选项 > 环境变量 `AWS_REGION`/`AWS_DEFAULT_REGION` > SDK 默认链。
- Bearer Token 路径：`options.bearerToken || options.apiKey || AWS_BEARER_TOKEN_BEDROCK` 任一存在时，跳过 SigV4 签名，改用 `config.token = { token: bearerToken }` 和 `authSchemePreference: ["httpBearerAuth"]`。
- 显式配置的 `profile`（或 `AWS_PROFILE`）必须优先于环境变量里的 `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`——代码注释直接引用了一个真实 issue（`#6957`）来解释这个优先级为什么这样定。

这部分体现了一个适配器要做的"隐性工作"：不仅要转换消息格式,还要吃透厂商 SDK 自己的凭证解析规则，避免和 pi 自己的鉴权解析（见第 5 节）打架。

#### 3.3 流式事件转换：AWS 事件 → 统一 `AssistantMessageEvent`

`stream()` 主循环遍历 AWS SDK 返回的 `response.stream`，按事件类型分发给几个 `handle*` 函数：

```ts
// packages/ai/src/api/bedrock-converse-stream.ts:263-295（节选）
for await (const item of response.stream!) {
	if (item.messageStart) {
		stream.push({ type: "start", partial: output });
	} else if (item.contentBlockStart) {
		handleContentBlockStart(item.contentBlockStart, blocks, output, stream);
	} else if (item.contentBlockDelta) {
		handleContentBlockDelta(item.contentBlockDelta, blocks, output, stream);
	} else if (item.contentBlockStop) {
		handleContentBlockStop(item.contentBlockStop, blocks, output, stream);
	} else if (item.messageStop) {
		output.rawStopReason = item.messageStop.stopReason;
		const { stopReason, errorMessage } = mapStopReason(item.messageStop.stopReason);
		output.stopReason = stopReason;
	} else if (item.metadata) {
		handleMetadata(item.metadata, model, output);
	}
	// ... internalServerException / modelStreamErrorException / validationException / throttlingException 直接 throw
}
```

`handleContentBlockDelta()`（`bedrock-converse-stream.ts:531-587`）是翻译逻辑最密集的地方：它检查 `delta.text` / `delta.toolUse` / `delta.reasoningContent` 三选一，分别对应推出 `text_delta`、`toolcall_delta`、`thinking_delta` 三种统一事件。工具调用的参数是边到达边拼接的 JSON 片段，用 `parseStreamingJson()`（`utils/json-parse.ts`）做"容错的流式 JSON 解析"，让上游能在参数还没收完整时就先拿到部分可用的对象。`handleMetadata()` 则把 AWS 返回的 `usage.inputTokens/outputTokens/cacheReadInputTokens/cacheWriteInputTokens` 映射进统一的 `Usage`，并调用 `calculateCost()`（`models.ts`）按 `Model.cost` 费率算出美元成本——这一步同样是"厂商字段名 → 统一字段名"的翻译。

#### 3.4 错误映射

```ts
// packages/ai/src/api/bedrock-converse-stream.ts:335-374（节选）
const BEDROCK_ERROR_PREFIXES: Record<string, string> = {
	InternalServerException: "Internal server error",
	ModelStreamErrorException: "Model stream error",
	ValidationException: "Validation error",
	ThrottlingException: "Throttling error",
	ServiceUnavailableException: "Service unavailable",
};

function formatBedrockError(error: unknown): string {
	const norm = normalizeProviderError(error);
	const core = !norm.messageCarriesBody && norm.status !== undefined && norm.body !== undefined
		? `${norm.status}: ${norm.body}`
		: norm.message;
	if (error instanceof BedrockRuntimeServiceException) {
		const prefix = BEDROCK_ERROR_PREFIXES[error.name] ?? error.name;
		return `${prefix}: ${core}`;
	}
	return core;
}
```

代码注释解释了为什么要保留这个"人类可读前缀"格式：下游的重试逻辑（`agent-session` 里的 `isRetryableAssistantError`）用简单的字符串正则（如 `server.?error`、`service.?unavailable`）去匹配 `errorMessage`，所以错误映射不仅要"看得懂"，还要**保持稳定的字符串格式**,否则会破坏跨 Provider 通用的重试判断逻辑。`stream()` 的 `catch` 块统一把结果落到 `output.stopReason = options.signal?.aborted ? "aborted" : "error"`，再通过 `{ type: "error", ... }` 事件推出——这正是上一篇讲的 `AssistantMessageEvent` 终止协议。

### 4. `compat.ts`：新旧两套架构之间的桥

`packages/ai/src/compat.ts` 顶部注释说得很直白：这是一个"临时兼容入口"，用来让还没升级到 `createModels()`/`Provider` 新架构的老代码继续用 `stream()`/`complete()` 这种全局函数调用方式。它做了三件事：

1. **API 实现注册表**：`BUILTIN_APIS` 数组把 10 个已知 API 字符串和各自的懒加载工厂函数绑在一起（`compat.ts:178-189`），`registerBuiltInApiProviders()` 把它们注册进一个内部 `Map`，`registerApiProvider()`/`getApiProvider()` 提供运行时的增删查——这套注册表机制早于本篇讲的 `Provider`/`createProvider()` 架构存在。
2. **环境变量自动注入**：`withEnvApiKey()`（`compat.ts:222-230`）在调用方没有显式传 `apiKey` 时，自动调用 `getEnvApiKey(model.provider, options?.env)` 去环境变量里找一个能用的 Key，这是全局 `stream()`/`complete()` 函数"不需要先调用鉴权解析就能直接发请求"体验的来源。
3. **`getModel`/`getModels`/`getProviders` 废弃别名**：直接指向新架构里的 `getBuiltinModel`/`getBuiltinModels`/`getBuiltinProviders`（定义在 `providers/all.ts`，下一篇细讲），保证老代码调用签名不变但底层数据源已经切换到生成的目录。

`compat.ts` 文件顶部注释原文说明了它的生命周期："This module is deleted with the coding-agent ModelManager migration"——也就是说它是一个**迁移期的过渡代码**，理解它的意义在于看懂 pi-ai 是怎么在保持向后兼容的同时逐步把调用方迁移到 `Provider`/`Models` 这套更规范的接口上的，而不是把它当作长期稳定的推荐用法。

### 5. 鉴权：API Key 与 OAuth 的接口设计

`packages/ai/src/auth/types.ts` 把每个 Provider 的鉴权能力定义成：

```ts
// packages/ai/src/auth/types.ts:237-240
export interface ProviderAuth {
	apiKey?: ApiKeyAuth;
	oauth?: OAuthAuth;
}
```

两者可以同时存在（比如 Anthropic 官方既支持直接填 API Key，也支持用 Claude Pro/Max 订阅走 OAuth 登录）。

**API Key 鉴权**（`ApiKeyAuth`）的核心方法是 `resolve()`：给定"已存的凭证 + 环境上下文"，返回请求需要的 `{ apiKey, headers, baseUrl }`。Bedrock 的实现很典型：

```ts
// packages/ai/src/providers/amazon-bedrock.ts:54-79（节选）
const bedrockAuth: ApiKeyAuth = {
	name: "AWS credentials or bearer token",
	login: async (interaction) => { /* 交互式选择：bearer-token / aws-profile / credential-chain */ },
	resolve: async ({ ctx, credential, signal }) => {
		if (credential?.key) return { auth: { apiKey: credential.key }, env: credential.env, source: "stored credential" };
		if (await env("AWS_BEARER_TOKEN_BEDROCK")) return { auth: {}, source: "AWS_BEARER_TOKEN_BEDROCK" };
		if (credential?.env?.AWS_PROFILE ?? (await env("AWS_PROFILE"))) return { auth: {}, source: "AWS_PROFILE" };
		if ((await env("AWS_ACCESS_KEY_ID")) && (await env("AWS_SECRET_ACCESS_KEY"))) return { auth: {}, source: "AWS access keys" };
		if (await env("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")) return { auth: {}, source: "ECS task role" };
		if (await env("AWS_WEB_IDENTITY_TOKEN_FILE")) return { auth: {}, source: "web identity token" };
		return undefined;
	},
};
```

注意 `resolve()` 大部分分支返回的 `auth: {}` 是**空对象**——因为 AWS 凭证链（Profile、IAM Role、ECS Task Role、Web Identity Token）本来就是 AWS SDK 自己在发请求时才会去解析的"环境态"凭证，pi 不需要（也不应该）把它们读出来塞进请求参数里，只需要告诉调用方"这个 Provider 已经配置好了、来源是什么"（`source` 字段用于状态展示 UI）。真正决定要不要发送这些凭证的逻辑，落在第 3.2 节说的 `api/bedrock-converse-stream.ts` 内部对 `options.env` 的读取上。这是 API Key 鉴权里"显式 Key"和"环境态凭证"两种子情况共用同一个接口、但语义不同的例子。

**OAuth 鉴权**（`OAuthAuth`）则完全是另一套生命周期，接口定义：

```ts
// packages/ai/src/auth/types.ts:206-230
export interface OAuthAuth {
	name: string;
	isSubscription?: boolean;
	login(interaction: ProviderAuthInteraction): Promise<OAuthCredential>;
	refresh(credential: OAuthCredential, signal: AbortSignal): Promise<OAuthCredential>;
	toAuth(credential: OAuthCredential): Promise<ModelAuth>;
}
```

以 Anthropic 的实现（`packages/ai/src/auth/oauth/anthropic.ts`）为例，`login()` 走的是标准 PKCE（Proof Key for Code Exchange，一种防止授权码被截获重放的 OAuth 扩展）授权码流程：

1. `generatePKCE()`（`auth/oauth/pkce.ts`）用 Web Crypto API 生成随机 `verifier`，并对它做 SHA-256 得到 `challenge`。
2. 在本地 `127.0.0.1:53692/callback` 启动一个临时 HTTP 服务器等待授权回调（`startCallbackServer()`），同时把授权 URL（`https://claude.ai/oauth/authorize?...code_challenge=...`）通过 `interaction.notify({ type: "auth_url", ... })` 交给上层 UI 展示或自动打开浏览器；如果用户所在环境打不开本地回调（比如远程开发机），也支持手动粘贴回调 URL 或授权码（`manual_code` 提示）。
3. 拿到 `code` 后，用 `code_verifier` 向 `https://platform.claude.com/v1/oauth/token` 换取 `access_token`/`refresh_token`（`exchangeAuthorizationCode()`）。
4. `refresh()` 用存量的 `refresh_token` 重新换取新的 access token,由 `Models.getAuth()` 在需要时自动调用（见 `auth/types.ts:219-222` 的注释：这是一个网络调用，`Models` 会在存储锁内运行它，防止并发请求重复刷新同一个即将过期的 token）。
5. `toAuth()` 是一个**无副作用的纯映射**：把已经有效的 `OAuthCredential` 转成请求要用的 `ModelAuth`，Anthropic 这里就是简单的 `{ apiKey: credential.access }`——即最终请求层面，OAuth access token 和普通 API Key 走的是同一个 `Authorization`/`apiKey` 通道,协议实现代码不需要区分它到底是哪种方式拿到的。

**两者的本质区别**：API Key 鉴权是"静态凭证 + 可选的环境态自动发现"，没有过期/刷新的概念（哪怕是 AWS 临时 Session Token,过期后也是重新走凭证链而不是 pi 内部的 refresh 流程）；OAuth 鉴权则天然带有"访问令牌会过期、需要用刷新令牌换新"的生命周期，`OAuthAuth.refresh()` 就是为这个生命周期专门设计的接口方法。pi-ai 目前内置的 OAuth 流程覆盖 Anthropic（Claude Pro/Max 订阅）、GitHub Copilot、OpenAI Codex、Kimi Coding、OpenRouter、xAI、Radius 等按订阅或个人账号登录的场景（见 `packages/ai/src/auth/oauth/` 目录）。

`packages/ai/src/oauth.ts` 本身只是一个"类型转发文件"（只 re-export 类型，不含实现），真正的 OAuth 流程逻辑在 `auth/oauth/*.ts`；而 `packages/ai/src/bun-oauth.ts` 的作用是给"编译成单文件 Bun 可执行程序"这种发行形态服务的：

```ts
// packages/ai/src/bun-oauth.ts
export function registerBunOAuthFlows(): void {
	registerBundledOAuthFlowLoaders({
		anthropic: () => anthropicOAuth,
		openaiCodex: () => openaiCodexOAuth,
		githubCopilot: () => githubCopilotOAuth,
		openrouter: () => openRouterOAuth,
		kimiCoding: () => kimiCodingOAuth,
		xai: () => xaiOAuth,
		radius: createRadiusOAuth,
	});
}
```

普通 Node.js 环境下这些 OAuth 实现可以用动态 `import()` 按需加载；但打包成 Bun 单文件可执行程序后动态 `import()` 的行为会受限，所以需要显式地把每个 OAuth 实现"静态注册"进一个加载器表（`registerBundledOAuthFlowLoaders`），确保它们被打进最终的二进制文件里。

### 6. `env-api-keys.ts`：环境变量里的 API Key 怎么被找到

```ts
// packages/ai/src/env-api-keys.ts:79-116（节选）
const envMap: Record<string, string> = {
	openai: "OPENAI_API_KEY",
	deepseek: "DEEPSEEK_API_KEY",
	google: "GEMINI_API_KEY",
	"google-vertex": "GOOGLE_CLOUD_API_KEY",
	groq: "GROQ_API_KEY",
	openrouter: "OPENROUTER_API_KEY",
	mistral: "MISTRAL_API_KEY",
	// ... 共三十余个 Provider
};
```

`getEnvApiKey(provider, env)` 的查找顺序（`env-api-keys.ts:144-188`）：

1. 先查 `getApiKeyEnvVars(provider)` 返回的一个或多个候选环境变量名——大多数 Provider 只有一个（如 `OPENAI_API_KEY`），但 `anthropic` 特殊，有三个候选（`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_OAUTH_TOKEN`、`ANTHROPIC_API_KEY`），代码注释解释 `ANTHROPIC_AUTH_TOKEN` 会参与"是否已配置"的状态展示，但 `getEnvApiKey()` 本身会跳过它,因为它必须作为 `Authorization: Bearer` 头传递而不是普通 `apiKey` 字段。
2. 如果是 `google-vertex`，走一条特殊分支：检查 Application Default Credentials（ADC）文件是否存在（`hasVertexAdcCredentials()`，默认路径 `~/.config/gcloud/application_default_credentials.json`）加上 `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` 是否配置，三者都满足时返回一个哨兵字符串 `"<authenticated>"`（不是真正的 Key,只是标记"已通过环境完成鉴权"）。
3. 如果是 `amazon-bedrock`，同样返回哨兵值 `"<authenticated>"`，判断条件覆盖 `AWS_PROFILE`、`AWS_ACCESS_KEY_ID`+`AWS_SECRET_ACCESS_KEY`、`AWS_BEARER_TOKEN_BEDROCK`、ECS Task Role 两种 URI 环境变量、`AWS_WEB_IDENTITY_TOKEN_FILE` 六种来源之一。

这套逻辑和上面 Bedrock 的 `bedrockAuth.resolve()` 覆盖的判断条件几乎一致，但服务的调用路径不同：`env-api-keys.ts` 主要被 `compat.ts` 里的 `withEnvApiKey()`（历史全局 API 路径）调用；而 `Models.getAuth()`（新架构路径）走的是每个 Provider 自己的 `ApiKeyAuth.resolve()`。两条路径在"从哪些环境变量能识别出鉴权已配置"这件事上保持了行为一致，这也是为什么读这部分代码时会看到逻辑重复——这是新旧架构过渡期的正常现象,而不是维护疏漏。

## 小结与思考题

一个 pi-ai Provider 适配器由两部分组成:`providers/*.ts` 里的薄外壳负责声明"有哪些模型、怎么鉴权",`api/*.ts` 里的实现负责真正的协议转换,具体拆成请求转换（统一 `Context`/`Tool` → 厂商专属请求体）、鉴权与连接参数解析、流式事件转换（厂商专属事件 → 统一 `AssistantMessageEvent`）、错误映射（厂商专属异常 → 统一 `StopReason`+`errorMessage`）四个子任务,Bedrock 适配器在这四个子任务上都因为 AWS 生态的特殊性（SigV4/Bearer 双认证模式、Converse Stream 事件结构、Claude-only 的签名字段）而写了不少针对性代码。鉴权方面,`ApiKeyAuth`/`OAuthAuth` 两个接口分别对应"静态或环境态凭证"和"会过期需要刷新的令牌"两种完全不同的生命周期,`compat.ts` 和 `env-api-keys.ts` 则是理解 pi-ai 从历史全局 API 向 `Provider`/`Models` 新架构迁移过程中留下的桥接层代码。

思考题:

1. `convertMessages()` 里把连续的 `toolResult` 消息合并成一条 Bedrock `user` 消息,这个"合并"逻辑如果放在上一篇讲的统一层（`types.ts`）里,让 `Context.messages` 本身就强制要求同一批工具结果放在一条消息里,会带来什么好处和坏处？为什么 pi-ai 选择让每个 Provider 各自处理这种厂商专属的结构要求？
2. `bedrockAuth.resolve()` 对大多数环境态凭证分支都返回 `auth: {}`（空对象）,把真正的凭证读取工作留给 AWS SDK 自己。如果一个新 Provider 的鉴权方式是"每次请求都需要用一个短期有效的签名 URL"（类似某些云函数网关）,你会把这个签名逻辑放在 `ApiKeyAuth.resolve()` 里还是放在对应的 `api/*.ts` 协议实现里？为什么？
3. `compat.ts` 明确写了"这个模块会在 ModelManager 迁移完成后删除"。假设你现在要新增一个 Provider,应该优先适配 `createProvider()`/`Provider` 这套新接口,还是顺便也要在 `compat.ts` 的 `BUILTIN_APIS` 里注册一份？读一下 `compat.ts:198-211` 的 `registerBuiltInApiProviders()`/`resetApiProviders()` 再回答。
