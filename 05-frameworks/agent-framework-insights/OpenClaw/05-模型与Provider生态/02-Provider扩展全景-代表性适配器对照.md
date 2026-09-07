# Provider 扩展全景与代表性适配器对照

> `extensions/` 目录下有 154 个子目录，其中 79 个在自己的 `openclaw.plugin.json` 里声明了 `providers` 字段，49 个进一步声明了完整的 `modelCatalog`——也就是真正参与 OpenClaw 统一推理循环的"模型 Provider"。这篇先给出这批扩展的全景分类，再精读 DeepSeek、Amazon Bedrock、Anthropic、GitHub Copilot 四个有代表性的适配器，讲清楚 `docs/plugins/sdk-provider-plugins.md` 定义的 Provider 插件契约到底要求实现什么，以及 API Key 直连、云 IAM 角色、OAuth 订阅复用这三种截然不同的认证方式，是怎么被同一层 Hook 收敛掉的。

## 学习目标

- 建立一份基于实际目录扫描的 Provider 扩展全景分类，而不是凭印象猜测。
- 读懂 `defineSingleProviderPluginEntry` 这个最小化封装的真实应用（DeepSeek 插件），理解一个模型 Provider 插件最少需要实现哪几项。
- 对照 Amazon Bedrock 插件的 `auth: []` 与 `resolveConfigApiKey`，理解"云 IAM/角色鉴权"在这套契约里是怎么被表达的——它和"API Key 直连"用的是同一个 Hook 位置，但语义完全不同。
- 对照 Anthropic 的 OAuth 订阅登录与 GitHub Copilot 的 Provider/Harness 双插件拆分，理解"订阅复用"在浅层（Provider）和深层（Agent Harness）两种扩展面上分别是怎么做的。
- 认识 Provider Replay/Stream Family Builder 这一层"减少重复实现"的复用机制，理解厂商差异是怎么被收敛成少数几条可复用策略的。

## 背景与设计动机

第 01 篇讲了 OpenClaw 核心侧怎么消费一个 Provider（推理循环、失败转移、认证轮换），这一篇转向插件作者视角：要让一个新的模型来源接入 OpenClaw，具体要写哪些代码？`docs/plugins/sdk-provider-plugins.md` 给出的答案是——**一个最小可用的文本 Provider 只需要 `id`、`label`、`auth`、`catalog` 四项**：

> A minimal text provider needs an `id`, `label`, `auth`, and `catalog`. `catalog` is the provider-owned runtime/config hook; it can call live vendor APIs and returns `models.providers` entries.

但"最小可用"和"生产级别"之间差距很大：Amazon Bedrock 插件要处理 SigV4/Bearer 双认证模式、AWS 区域推断、Guardrail 配置；GitHub Copilot 要处理 OAuth 刷新和运行时身份头；Anthropic 要同时支撑 API Key、OAuth 订阅登录、Claude CLI 复用三条路径。这些差异最终都落回到同一张 Hook 表上——`catalog`、`resolveConfigApiKey`、`wrapStreamFn`、`classifyFailoverReason`、`resolveThinkingProfile` 等等——区别只在于每个插件往这些 Hook 里塞了多少逻辑。

## 核心机制详解

### 1. 全景扫描：79 个声明 Provider，49 个是完整模型目录

在仓库根目录跑一次结构化扫描（而不是逐个打开 154 个目录）就能看清全貌：

```bash
$ ls -d extensions/*/ | wc -l
154
$ grep -l '"providers"' extensions/*/openclaw.plugin.json | wc -l
79
$ grep -l '"modelCatalog"' extensions/*/openclaw.plugin.json | wc -l
49
```

79 与 49 之间的差集,大多是只提供语音（`azure-speech`、`deepgram`、`elevenlabs`、`fish-audio-speech`）、图像/视频生成（`image-generation-core`、`pixverse`、`runway`）等非文本能力的 Provider——它们同样走 `registerProvider`/`register*Provider` 这套注册机制,但不携带聊天模型目录。下面这份分类只覆盖那 49 个声明了 `modelCatalog` 的文本模型 Provider,按认证/部署形态归类(名称均来自实际扫描结果,不做归纳之外的补充):

**云厂商托管类**——模型托管在云厂商基础设施上,鉴权走云厂商自己的凭证体系而非厂商自定义 API Key:
`amazon-bedrock`、`amazon-bedrock-mantle`(AWS)、`google`(含 Vertex AI 的 Application Default Credentials 路径)。

**国产模型类**——面向中国大陆或双语市场的模型厂商:
`deepseek`、`qwen`、`moonshot`(月之暗面 Kimi)、`zai`(智谱 GLM)、`tencent`、`volcengine`(火山引擎/豆包)、`byteplus`(火山引擎国际版)、`xiaomi`、`qianfan`(百度千帆)、`longcat`、`stepfun`、`minimax`。

**聚合网关/推理托管类**——不直接生产模型,而是转发或托管第三方开源模型:
`openrouter`、`vercel-ai-gateway`、`litellm`、`kilocode`、`opencode`/`opencode-go`、`groq`、`cerebras`、`together`、`fireworks`、`deepinfra`、`novita`、`featherless`、`huggingface`、`gmi`、`nvidia`、`chutes`、`arcee`、`cohere`、`mistral`、`baseten`、`synthetic`、`venice`。

**订阅复用类**——认证复用的是一个已有的产品订阅账号,而不是厂商专门发的 API Key:
`anthropic`(Claude Pro/Max OAuth 或 Claude CLI 复用)、`github-copilot`(GitHub Copilot 订阅 OAuth)、`xai`(SuperGrok/X Premium OAuth)、`minimax`(旗下 `minimax-portal` 走 OAuth 令牌)、`openrouter`(同时支持 OAuth 和 API Key)、`chutes`(同时支持 `CHUTES_API_KEY` 和 `CHUTES_OAUTH_TOKEN`)。

**本地/自托管类**——模型跑在用户自己控制的进程或局域网服务器上:
`ollama`、`lmstudio`、`vllm`、`sglang`、`llama-cpp`。

这五类之间不是互斥的(比如 `openrouter` 既是聚合网关又支持订阅式 OAuth),但足以说明一件事:**OpenClaw 的 Provider 契约必须同时容纳"厂商直连 API Key""云厂商 IAM 凭证链""产品订阅 OAuth""本地无鉴权服务"这四种完全不同的信任模型**,下面几节挑四个代表性插件,看这层契约具体是怎么把差异吸收掉的。

### 2. 最小实现范本:DeepSeek 插件

DeepSeek 插件是这套契约里"教科书级别"的简单例子——只做一件事(文本推理),用一种认证方式(API Key),`extensions/deepseek/index.ts` 全文不到 60 行:

```ts
// extensions/deepseek/index.ts:15-54(节选)
export default defineSingleProviderPluginEntry({
  id: PROVIDER_ID,
  name: "DeepSeek Provider",
  manifest,
  provider: {
    label: "DeepSeek",
    docsPath: "/providers/deepseek",
    manifestAuth: { applyConfig: applyDeepSeekConfig },
    catalog: {
      discoveryMode: "strict",
      buildProvider: buildDeepSeekProvider,
      buildStaticProvider: buildDeepSeekProvider,
      liveModelDiscovery: true,
    },
    matchesContextOverflowError: ({ errorMessage }) =>
      /\bdeepseek\b.*(?:input.*too long|context.*exceed)/i.test(errorMessage),
    ...buildProviderReplayFamilyHooks({ family: "openai-compatible", dropReasoningFromHistory: false }),
    ...buildProviderToolCompatFamilyHooks("deepseek"),
    wrapStreamFn: (ctx) => createDeepSeekV4ThinkingWrapper(ctx.streamFn, ctx.thinkingLevel),
    resolveThinkingProfile: ({ modelId }) => resolveDeepSeekV4ThinkingProfile(modelId),
    resolveUsageAuth: async (ctx) => {
      const apiKey = ctx.resolveApiKeyFromConfigAndStore({ envDirect: [ctx.env.DEEPSEEK_API_KEY] });
      return apiKey ? { token: apiKey } : null;
    },
    fetchUsageSnapshot: async (ctx) => await fetchDeepSeekUsage(ctx.token, ctx.timeoutMs, ctx.fetchFn),
  },
});
```

`defineSingleProviderPluginEntry` 正是 SDK 文档里推荐的窄接口:

> For bundled providers that only register one text provider with API-key auth plus a single catalog-backed runtime, prefer the narrower `defineSingleProviderPluginEntry(...)` helper.

模型目录本身不是手写的 JS 数组,而是从 `openclaw.plugin.json` 的 `modelCatalog.providers.deepseek` 字段里解析出来的——`extensions/deepseek/models.ts` 里 `buildManifestModelProviderConfig()` 把清单驱动的声明式配置转成运行时结构:

```json
// extensions/deepseek/openclaw.plugin.json:29-53(节选)
"models": [
  {
    "id": "deepseek-v4-flash",
    "reasoning": true,
    "input": ["text"],
    "contextWindow": 1000000,
    "maxTokens": 384000,
    "cost": { "input": 0.14, "output": 0.28, "cacheRead": 0.0028, "cacheWrite": 0 },
    "compat": { "supportsUsageInStreaming": true, "supportsReasoningEffort": true, "codeMode": "preferred" }
  }
]
```

这种"清单驱动"的写法把模型元数据(定价、上下文窗口、能力开关)和运行时逻辑(怎么发请求、怎么判定思考等级)彻底分开——第 01 篇里 `manifest-planner.ts` 消费的正是这份 JSON 清单。`liveModelDiscovery: true` 让 DeepSeek 的模型目录不完全依赖手写清单,还能实时探测厂商的 `/models` 端点;`discoveryMode: "strict"` 则要求发现失败时如实报告失败,而不是悄悄退回静态种子数据冒充一次成功刷新。

### 3. 云 IAM 凭证链:Amazon Bedrock 的 `auth: []`

Bedrock 插件在 `registerProvider` 调用里,`auth` 字段是空数组:

```ts
// extensions/amazon-bedrock/register.sync.runtime.ts:506-510(节选)
api.registerProvider({
  id: providerId,
  label: "Amazon Bedrock",
  docsPath: "/providers/models",
  auth: [],
  // ...
  resolveConfigApiKey: ({ env }) => resolveBedrockConfigApiKey(env),
```

这不是"忘了写鉴权",而是因为 Bedrock 走的根本不是"用户交互式填一个 Key"的模式——它复用的是 AWS SDK 自己的默认凭证链(Profile、环境变量、ECS Task Role、Web Identity Token 等)。`resolveConfigApiKey` 只是去读几个 AWS 环境变量,判断"这条凭证链有没有配置好",真正的签名和凭证解析工作留给 AWS SDK 在发请求时自己完成。这与第 01 篇提到的"Provider 插件自己决定认证语义"完全对应:**同一个 Hook 位置(`resolveConfigApiKey`/`auth`),在 DeepSeek 那里装的是一把真实的 API Key,在 Bedrock 这里装的却是"环境是否已授权"这个布尔判断**。

Bedrock 插件真正复杂的地方在 `wrapStreamFn`——它要在流式请求管线里叠加一层又一层厂商特定的补丁:按 ARN 或模型 ID 判断是不是 Claude 模型从而决定要不要走 Prompt Cache 断点注入、按 `serviceTier` 参数决定要不要包一层 `service_tier` 请求补丁、按模型代际(Opus 4.7+、Claude Fable 5)决定要不要从请求体里剔除 `temperature` 字段:

```ts
// extensions/amazon-bedrock/register.sync.runtime.ts:698-711(节选)
classifyFailoverReason: ({ errorMessage }) => {
  if (/ThrottlingException|Too many concurrent requests/i.test(errorMessage)) {
    return "rate_limit";
  }
  if (/ModelNotReadyException/i.test(errorMessage)) {
    return "overloaded";
  }
  if (deprecatedTemperatureValidationRe.test(errorMessage)) {
    return "format";
  }
  return undefined;
},
```

这正是第 01 篇说的"失败分类是插件自己的责任"落地成的具体代码:AWS 的 `ThrottlingException`、`ModelNotReadyException` 这些厂商专属异常名,只有 Bedrock 插件自己知道该映射成 OpenClaw 统一的哪一种失败原因。

### 4. 订阅复用的两种深度:Anthropic OAuth vs GitHub Copilot 的双插件拆分

Anthropic 插件同时暴露三条鉴权路径,`docs/concepts/model-providers.md` 里写得很直接:

> Direct public Anthropic requests support the shared `/fast` toggle... Preferred Claude CLI config keeps the model ref canonical and selects the CLI backend separately... Claude CLI reuse (`claude -p`) is a sanctioned OpenClaw integration path.

也就是说,`anthropic/claude-opus-5` 这一个模型引用背后,可能走的是"直接 API Key 请求""Claude Pro/Max 账号 OAuth 登录后请求官方 API""调用本地已登录的 `claude` CLI 二进制"三条完全不同的通路,但对上层调用者(推理循环、失败转移)来说都是同一个 `provider/model`。这三条路径都还停留在**Provider 层**——它们复用的是官方 API 的请求协议,只是换了拿到有效凭证的方式。

GitHub Copilot 则展示了订阅复用的另一种、更深的做法。仓库里实际有三个 Copilot 相关扩展:`github-copilot`、`copilot`、`copilot-proxy`。其中 `github-copilot` 是一个标准的 Provider 插件,声明了完整的 `modelCatalog`,认证走的是 GitHub token 的 OAuth 流程:

```ts
// extensions/github-copilot/index.ts:44-49(节选)
const COPILOT_ENV_VARS: [string, string, string] = [
  "COPILOT_GITHUB_TOKEN",
  "GH_TOKEN",
  "GITHUB_TOKEN",
];
const DEFAULT_COPILOT_PROFILE_ID = "github-copilot:github";
```

它参与的是和 DeepSeek、Bedrock 一样的普通推理循环——`wrapCopilotProviderStream`、`buildGithubCopilotReplayPolicy` 这些都是本篇前面讲的同一套 Hook。而 `copilot` 插件走的是完全不同的注册路径——它调用的是 `registerAgentHarness`,不是 `registerProvider`:

```ts
// extensions/copilot/index.ts:48-57(节选)
api.registerAgentHarness(
  createCopilotAgentHarness({
    ...(poolOptions ? { poolOptions } : {}),
    sessionStore: { /* ... */ },
  }),
);
```

`docs/plugins/sdk-provider-plugins.md` 里的提示框解释了这两种注册方式的分界:

> Provider plugins add models to OpenClaw's normal inference loop. If the model must run through a native agent daemon that owns threads, compaction, or tool events, pair the provider with an agent harness instead of putting daemon protocol details in core.

`copilot` 这个 Harness 插件接管的是整条会话生命周期——线程、压缩、工具事件全部由 GitHub Copilot 自己的 SDK/CLI daemon 拥有,OpenClaw 只是把用户输入转发进去、把输出事件转发回来。这是一种比"Provider 层认证复用"深得多的集成方式:模型不再是"OpenClaw 推理循环里的一个可插拔厂商",而是"另一个完整的 Agent 运行时,OpenClaw 只负责桥接"。同样走 Harness 深度集成路径的还有 `codex`(OpenAI Codex 订阅),它的运行时细节和"Codex 原生集成"这个主题关系更密切,留到第 06 章展开。

### 5. Replay/Stream Family Builder:把厂商差异收敛成几条可复用策略

即便认证方式各不相同,不同 Provider 在"怎么清洗历史消息以适配厂商的消息格式要求"这件事上,往往可以归并成少数几条策略。`docs/plugins/sdk-provider-plugins.md` 列出了目前内置的几个 Replay Family:

| Family | 覆盖的行为 | 已知使用者 |
| --- | --- | --- |
| `openai-compatible` | 工具调用 ID 清洗、assistant-先行顺序修复 | `moonshot`、`ollama`、`xai`、`zai`、`deepseek` |
| `anthropic-by-model` | 按 `modelId` 识别 Claude,只对 Claude 模型做思考块清洗 | `amazon-bedrock` |
| `native-anthropic-by-model` | 同上,外加工具调用 ID 的原生保真 | `anthropic-vertex`、`clawrouter` |
| `google-gemini` | 原生 Gemini 回放校验与思考签名清洗 | `google`、`google-gemini-cli` |
| `hybrid-anthropic-openai` | 一个插件里混合 Anthropic 消息面和 OpenAI 兼容面 | `minimax` |

DeepSeek 插件用的正是 `buildProviderReplayFamilyHooks({ family: "openai-compatible", dropReasoningFromHistory: false })`,Bedrock 用的是 `anthropic-by-model`(因为同一个 Bedrock Provider 底下既有 Claude 模型也有其他厂商模型,只有 Claude 模型才需要那套思考块清洗逻辑)。这层复用机制的价值在于:**新增一个"又一个 OpenAI 兼容代理"类型的 Provider,不需要重新发明一遍工具调用 ID 清洗逻辑**,只要声明自己属于哪个 Family 就够了——这也是为什么本篇开头的全景分类里,"聚合网关类"和"国产模型类"能有这么多成员却不需要各自维护一份独立的回放策略代码。

## 常见问题/易踩坑

- **把 `auth: []` 误读成"这个 Provider 不需要鉴权"**:Bedrock 的空数组只是说明它不使用 OpenClaw 标准的交互式 API Key/OAuth 登录流程,真正的凭证判定逻辑在 `resolveConfigApiKey` 和 AWS SDK 默认凭证链里,不代表可以匿名访问。
- **混淆 `github-copilot` 和 `copilot` 两个插件**:前者是参与普通推理循环的模型 Provider(`github-copilot/*` 模型引用),后者是接管整条 Agent 会话生命周期的 Harness,二者认证复用的都是 GitHub Copilot 订阅,但集成深度完全不同,配置和排障路径也不一样。
- **给一个新 Provider 手写回放清洗逻辑,而不先检查现有 Family 能不能覆盖**:5 个内置 Family 已经覆盖了 OpenAI 兼容、Anthropic 消息、Gemini 原生、混合面等主流协议形态,新增 Provider 前应该先确认自己是不是能直接复用其中一个,而不是从零实现。

## 小结

154 个扩展目录里,只有约三分之一(49 个)声明了完整的文本模型目录,它们按认证/部署形态可以归成云厂商托管、国产模型、聚合网关、订阅复用、本地自托管五类——但无论哪一类,最终都要落回 `docs/plugins/sdk-provider-plugins.md` 定义的同一套 Hook 契约:`catalog` 声明模型目录、`resolveConfigApiKey`/`auth` 声明鉴权语义、`classifyFailoverReason` 声明错误分类、`wrapStreamFn` 承载厂商特定的请求补丁,而 Replay/Stream Family Builder 进一步把"怎么清洗历史消息"这类高重复度的逻辑收敛成少数几条可声明式复用的策略。GitHub Copilot 的 Provider/Harness 双插件拆分也说明了一件事:模型接入 OpenClaw 有"参与统一推理循环"和"接管整个 Agent 运行时"两种深度,后者已经不是这一章的主题——它属于下一章要讲的 Codex 原生集成与工具/Skills/Plugins/MCP 生态的一部分。这一章的最后一篇,回到核心推理循环本身,看喂给模型的 System Prompt 到底是怎么拼出来的。
