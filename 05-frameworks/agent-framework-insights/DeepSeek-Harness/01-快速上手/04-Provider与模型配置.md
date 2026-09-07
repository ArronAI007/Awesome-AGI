# Provider 与模型配置

> `dsh` 从不在核心引擎里 import `deepseek-official` 或任何具体厂商的 SDK——`packages/llm/llm` 定义的是一套厂商无关的请求/流式响应词汇表，`llm-deepseek`、`llm-pi-ai` 只是往这套词汇表上注册路由的两个平级实现。换模型、换厂商，本质上是"注册了哪些 Provider 路由"的问题，而不是改核心代码的问题；而"用哪个 Key"这件事，则被完全下放给上一篇讲过的 `credentials` Seam。

## 学习目标

- 理解 `packages/llm/llm` 这个包扮演的角色：厂商无关的 `GenerateOptions`/`StreamChunk` 词汇表，而不是任何具体厂商的封装。
- 认识 `LlmCallConfig`（`provider`/`model`/`reasoningEffort`/`temperature`/`maxTokens`/`stop`）这组字段，以及它们如何被记录进会话日志的 `EpochHeader`。
- 读懂 `llm-deepseek` 适配器如何解析连接参数：Key 从 `credentials` 来，非敏感偏好从 `settings` 来，两者被显式拼在一起才构成一次请求的完整配置。
- 知道 `llm-pi-ai` 这个"第二个适配器"的作用——它验证了同一套 Seam 能不能装下一个完全不同风格的 Provider（一个插件管理一整个 provider 字典，而不是一个插件对应一个 provider）。
- 理解为什么"设置"（settings）与"凭证"（credentials）在配置模型时依然是两条独立的路径,而不会因为要配置模型就合并到一起。

## 背景与设计动机

如果一个 Agent 引擎的核心循环里直接 `import { OpenAI } from 'openai'` 之类的具体 SDK，换一个模型厂商就意味着改核心代码、重新测试整条链路。`dsh` 的做法是把"LLM 能力"做成典型的三元 Seam：`packages/llm/llm` 只定义接口（`GenerateOptions` 请求什么样、`StreamChunk` 响应流什么样），具体厂商的适配器（`llm-deepseek`、`llm-pi-ai`）各自实现这套接口并"注册"一个或多个 Provider 路由，核心的 `agent-loop` 只认路由名字，不认具体实现类。这套设计的检验标准很朴素：**如果只有一个适配器实现，你无法判断接口设计得是否足够通用**——`llm-pi-ai` 的存在本身就是"这套接口能不能装下第二种、风格完全不同的实现"的活文档。

## 核心机制详解

### `packages/llm/llm`：厂商无关的请求词汇表

一次模型调用的完整参数由 `GenerateOptions` 描述，它不认识任何具体厂商的字段名：

```typescript
// packages/llm/llm/src/types.ts
export interface GenerateOptions {
  /** Registered provider route selecting the adapter instance. */
  provider: string
  model: string
  /** Adapter-owned reasoning effort selected for this exact model. */
  reasoningEffort?: ReasoningEffortId
  messages: Message[]
  system?: string
  tools?: ToolSchema[]
  temperature?: number
  maxTokens?: number
  stop?: string[]
  signal?: AbortSignal
  sessionId?: Branded<'SessionId'>
  purpose?: 'compaction' | 'session-title'
}
```

`provider` 字段是一个字符串路由 key（比如 `'deepseek-official'`），核心循环只用这个字符串去查找注册过的适配器实例,完全不关心这个适配器内部是调 HTTP 还是调某个 SDK。响应侧同理，`StreamChunk` 是一套和具体厂商 SSE 格式无关的增量事件：

```typescript
// packages/llm/llm/src/types.ts
export type StreamChunk =
  | { type: 'block-start'; index: number; blockType: ContentBlockType }
  | { type: 'text-delta'; index: number; text: string }
  | { type: 'reasoning-delta'; index: number; text: string }
  | { type: 'tool-call-delta'; index: number; id: CallId; name?: string; argumentsDelta: string }
  | { type: 'block-end'; index: number; block: ContentBlock }
  | { type: 'usage'; usage: TokenUsage }
  | { type: 'finish'; reason: FinishReason; replayState?: unknown }
```

模块顶部注释点明了这份词汇表的设计取舍：

```typescript
// packages/llm/llm/src/types.ts
/**
 * Canonical provider-neutral message and streaming vocabulary for the loop,
 * session log, and plugins. Adapters alone translate provider wire messages;
 * mapped interfaces make the content, source, and finish unions extensible.
 */
```

也就是说只有适配器才知道怎么把某个厂商的原始响应翻译成这套词汇；一旦翻译完成，会话日志、UI 渲染、压缩逻辑看到的永远是同一种结构，不需要为每个厂商写一套平行逻辑。`ContentBlockMap`、`FinishReasonMap` 这些接口特意设计成"可通过 TypeScript 声明合并扩展的字典"（`merge-extensible`），比如未来新增一种 `reasoning` 之外的内容块类型，只需要给 `ContentBlockMap` 声明合并一个新 key，而不需要改动这个联合类型的每一个消费者。

### `LlmCallConfig`：一次对话真正"可配置"的那几个字段

一次会话请求里，provider/model/reasoningEffort 这些"跨请求保持不变、影响缓存复用"的字段被单独抽出成 `LlmCallConfig`：

```typescript
// packages/llm/llm/src/call-config.ts
/**
 * Provider, model, reasoning effort, and sampling scalars of one conversation's
 * requests. Every field maps 1:1 onto the same-named `GenerateOptions` field;
 * the loop builds requests from the logged header rather than accepting these
 * per call.
 */
export interface LlmCallConfig {
  provider: string
  model: string
  reasoningEffort?: ReasoningEffortId
  temperature?: number
  maxTokens?: number
  stop?: string[]
}
```

关键的一句在注释里：**「the loop builds requests from the logged header rather than accepting these per call」**——`agent-loop` 并不是每次调用都从某个"当前配置"变量里读 provider/model，而是从会话日志里记录的 `EpochHeader` 重建出这份配置。`packages/core/session/src/types.ts` 里 `EpochHeader` 正是把 `LlmCallConfig` 包了一层：

```typescript
// packages/core/session/src/types.ts（节选）
export interface EpochHeader {
  config: LlmCallConfig
  adapterDefaults?: LlmCallConfigAdapterDefaults
}
```

`adapterDefaults` 标记的是"这个字段的值不是用户显式指定的，而是适配器解析出来的默认值"（比如用户没传 `reasoningEffort`，适配器按模型自己的默认策略填了 `high`）。`packages/core/agent-loop/src/agent.ts` 里有一处专门"剥掉适配器默认值"的函数，用在向插件征询下一次请求配置的时候：

```typescript
// packages/core/agent-loop/src/agent.ts
/** Remove adapter-derived values before plugins propose the next request config. */
function requestProposal(header: EpochHeader): LlmCallConfig {
  if (header.adapterDefaults === undefined) return header.config
  const proposal = { ...header.config }
  if (header.adapterDefaults.reasoningEffort === true) delete proposal.reasoningEffort
  if (header.adapterDefaults.maxTokens === true) delete proposal.maxTokens
  return proposal
}
```

这样做的意义是：如果 `reasoningEffort` 是适配器自己填的默认值而不是用户显式选择的，那么在征询"是否要切换模型/参数"时就不应该把这个隐式默认值当成"用户锁定的值"再传回去——否则切换模型之后，上一个模型的隐式默认反而会被误当成显式配置继续沿用。`LlmCallConfig` 的字段是否发生了实质变化，靠 `callConfigEquals` 逐字段比较来判定，只有真正变化时才会在会话日志里追加一条新的请求头快照，这也是"Model-visible ⟺ logged"这条工程规则的一处具体落地——任何影响模型请求的配置都必须能从日志里重建。

### `llm-deepseek`：DeepSeek 官方适配器怎么组装一次连接

`llm-deepseek` 这个插件的模块注释一句话概括了它的职责：

```typescript
// packages/llm/llm-deepseek/src/index.ts
/**
 * Register a {@link DeepSeekAdapter} for the `deepseek-official` provider route on
 * `ctx.llm`, with connection facts resolved per request instead of frozen at
 * load: the plugin layers its `cordis.yml` entry config under the optional
 * `llm-deepseek` user-settings section (`ctx.settings`) and resolves the API
 * key through the optional credential seam (`ctx.credentials`), ...
 */
```

它的 `Config` 接口里，**没有任何字段直接是密钥本身**，只有一个"密钥引用名"：

```typescript
// packages/llm/llm-deepseek/src/index.ts
export interface Config {
  /** Credential reference (environment-variable name) resolved per request; defaults to `DEEPSEEK_API_KEY`. */
  apiKeyEnv?: string
  /** Endpoint base; falls back to $DEEPSEEK_BASE_URL from a trusted environment layer, then the public API. */
  baseURL?: string
  thinking?: 'enabled' | 'disabled'
  reasoningEffort?: 'off' | 'high' | 'max'
  maxTokens?: number
  defaultContextWindow?: number
  models?: DeepSeekCatalogModel[]
  streamIdleTimeoutMs?: number
  retryPolicy?: RetryPolicyConfig
}
```

真正解析出连接参数的地方是 `resolveAdapterOptions`——注意它接收的是"配置"和"环境层"两个独立参数,而密钥的真正取值在这个函数之外的 `resolveApiKey` 才发生：

```typescript
// packages/llm/llm-deepseek/src/index.ts（节选）
export function resolveAdapterOptions(config: Config, environment?: LaunchEnvironmentSnapshot): ResolvedDeepSeekOptions {
  ...
  return {
    apiKeyEnv: credentialRef(config.apiKeyEnv ?? DEFAULT_API_KEY_ENV),
    baseURL: config.baseURL
      ?? environment?.get(BASE_URL_ENV)?.value
      ?? PUBLIC_BASE_URL,
    defaults: {
      thinking: config.thinking,
      reasoningEffort: config.reasoningEffort,
    },
    maxTokens: config.maxTokens ?? DEFAULT_MAX_TOKENS,
    defaultContextWindow: config.defaultContextWindow ?? DEFAULT_CONTEXT_WINDOW,
    models: resolveModels(config.models),
    streamIdleTimeoutMs,
    retryPolicy: resolveRetryPolicy(config.retryPolicy, 'llm-deepseek: retryPolicy'),
  }
}
```

而真正去 `ctx.credentials` 拿密钥值,是在每次请求即将发出时才发生的：

```typescript
// packages/llm/llm-deepseek/src/index.ts（节选）
const resolveApiKey = async (connection: ResolvedDeepSeekOptions): Promise<string> => {
  const ref = connection.apiKeyEnv
  const credentials = ctx.get('credentials')
  if (credentials !== undefined) {
    const hit = await credentials.resolve(ref)
    if (hit !== undefined) return assertUsableApiKey(hit.value, 'llm-deepseek', ref)
  } else {
    const ambient = launchEnvironmentOf(ctx).get(ref)
    if (ambient !== undefined && ambient.value.length > 0) {
      return assertUsableApiKey(ambient.value, 'llm-deepseek', ref)
    }
  }
  throw new LlmError(
    `llm-deepseek: no API key for provider route "${PROVIDER}"; store ${ref} through the credentials`
    + ` service (the web Models page writes it), or export ${ref} in the launching environment`,
    'MISSING_CREDENTIAL',
  )
}
```

这正是上一篇讲过的凭证优先级链条在具体消费者身上的落地：如果 `credentials` Seam 存在（正常安装下 `dsh-base` 会挂载 `credentials-local`），就走它的完整优先级解析；如果整个 Seam 都没挂载（一个极简的自定义 Profile），才退化成直接读取进程环境。**每次请求都重新解析一次**，而不是在插件加载时缓存下来——这就是为什么在 Web UI 的 Models 页面改一次 Key，下一次对话立刻生效，不需要重启进程。

非敏感的偏好（`baseURL`、`thinking`、`reasoningEffort` 默认值、模型目录……）走的是另一条路——`installSettingsSection` 把插件自己声明的 `Config` schema 注册成一个用户设置命名空间：

```typescript
// packages/llm/llm-deepseek/src/index.ts（节选）
installSettingsSection(ctx, NS, Config, config, {
  setSource: (source) => {
    current = source
  },
  onChange: ensureRegistrationFacts,
})
```

`packages/settings/settings` 的 README 说明了这套 Seam 的读取顺序：**schema 默认值 → 该插件在 `cordis.yml` entry 里写的 `config`（作为 `base`）→ 用户在设置界面写的覆盖（`user` 层）**。也就是说同一个 `baseURL` 字段，`cordis.yml` 里可以写一个部署级默认，用户在 Web UI 的设置页面可以再覆盖一次，两者互不冲突,`ctx.settings` 会按这个顺序把它们合并成一份解析结果——这条链路和 `credentials` 的"继承环境 > 托管文件 > `.env`"优先级链条是两套完全独立的机制，一套管"这个值是多少"，一套管"这个密钥的真实内容是什么"。

### `llm-pi-ai`：验证同一套 Seam 能装下另一种适配器风格

`llm-deepseek` 是"一个插件对应一个 Provider 路由"的写法；`llm-pi-ai` 则完全是另一种拓扑——**一个插件实例管理一整个 Provider 路由字典**，模块注释里的配置示例把这一点讲得很清楚：

```typescript
// packages/llm/llm-pi-ai/src/index.ts（节选）
/**
 * ```yaml
 * - id: llm
 *   name: '@deepseek-ai/dsh-llm-pi-ai'
 *   config:
 *     providers:
 *       # Catalog route: everything but the credential comes from pi-ai.
 *       openai:
 *         apiKeyEnv: OPENAI_API_KEY
 *       # Hand-declared route: pi-ai ships nothing under this key.
 *       acme-gateway:
 *         displayName: Acme Gateway
 *         apiKeyEnv: ACME_GATEWAY_API_KEY
 *         api: openai-completions
 *         baseURL: https://gateway.acme.example/v1
 *         compat:
 *           thinkingFormat: deepseek
 *         models:
 *           - id: acme-large
 *             contextWindow: 65536
 * ```
 */
```

一个 `providers` 字典里既能声明"这个路由名对应 pi-ai 内置认识的某个厂商目录"（`openai` 这种 catalog route，端点、协议、模型目录全部继承自 pi-ai 自己的知识），也能声明"pi-ai 完全不认识、需要手工补全端点和模型清单"的路由（`acme-gateway` 这种手写 route）。这恰恰是对 `packages/llm/llm` 这套接口设计的一次交叉验证：`llm-deepseek` 证明了接口能装下"官方直连、单一路由"的场景，`llm-pi-ai` 证明了同一套接口也能装下"多路由、部分继承第三方目录、部分手写"的更复杂场景——如果接口设计得不够通用，第二个适配器往往要绕开接口另起一套逻辑，而 `llm-pi-ai` 没有这么做，它一样是通过 `ctx.llm.registerAdapter()` 注册路由。

### 怎么切换/配置模型

结合以上几点，实际配置模型的入口有三层，优先级从低到高：

1. **Bundle 自带的默认层**：`dsh-base`/`dsh-web-app` 的 `cordis.patch.yml` 里 `llm-deepseek` 这一行的 `config`（部署默认，比如把 `models` 目录限定成公司内部批准的几个模型）；
2. **用户设置（`ctx.settings`）**：Web UI 的 Models 设置页面写的覆盖，落在 `llm-deepseek` 命名空间的用户层；
3. **凭证（`ctx.credentials`）**：只负责 `apiKeyEnv` 指向的那个引用名背后的真实密钥值，和上面两层完全独立。

一次对话具体用哪个 `provider`/`model`/`reasoningEffort`，则记录在会话自己的 `EpochHeader` 里，由 `agent-loop` 在每个 turn 边界读取、比较、决定是否需要追加新的请求头快照——这部分完整的状态机属于 Agent 核心循环的范畴，第 04 章会继续深入。

## 常见问题/易踩坑

- **改了 Web UI 的模型设置没生效**：先确认改的是不是 `cordis.yml`/Bundle 层（那是部署级默认，理论上应该被用户层覆盖）；如果确实没生效，检查 `installSettingsSection` 的 `onChange` 回调有没有被正确触发——某些"注册时捕获的事实"（比如 `retryPolicy`）需要显式 `replace()` 重新注册路由才能生效，纯粹改配置读取路径是不够的。
- **以为密钥可以直接写在 `cordis.yml` 的 `apiKeyEnv` 里**：`apiKeyEnv` 永远是一个环境变量名（引用），不是密钥值本身；真正的值要么在启动环境里，要么在 `$DSH_HOME/.credentials.yaml` 里，参见第 01 篇。
- **给 `llm-pi-ai` 声明了一个路由但没生效**：检查路由名有没有和其他已注册的路由冲突，以及 `models` 数组里的字段是否符合 schema（比如 `id` 不能为空、`contextWindow` 必须是正整数）——`resolveModels`/`resolveAdapterOptions` 这类函数在装配阶段就会对这些值做严格校验,校验失败会直接抛错而不是静默忽略。

## 小结

`dsh` 把"模型能力"拆成了一个厂商无关的接口层（`GenerateOptions`/`StreamChunk`/`LlmCallConfig`）和若干平级的适配器实现（`llm-deepseek`、`llm-pi-ai`）,核心循环只认注册进来的 Provider 路由字符串。一次请求真正用什么参数,由记录在会话日志里的 `EpochHeader` 决定,而不是某个全局可变状态；密钥的真实值永远走 `credentials` Seam，非敏感偏好永远走 `settings` Seam,两者刻意保持独立,即使在配置同一个模型 Provider 时也不会合流。下一篇会转向另一个同样"故意拆成正交旋钮"的领域——权限预设,看 `sandbox` 模式和 `approval` 策略如何组合成用户可见的几个开关。
