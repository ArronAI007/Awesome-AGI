# Model Providers 抽象与 Failover

> OpenClaw 把"模型来源"统一抽象成 **Provider**：不管背后是一次 HTTPS API 调用、一条走 AWS SDK 默认凭证链的 SigV4 签名请求，还是一个本地 `llama-server` 进程，调用方看到的都只是一个 `provider/model` 引用外加一组标准化的运行时 Hook。这篇讲清楚这层抽象具体长什么样、谁来承担"厂商特定逻辑"，以及一次请求失败之后，OpenClaw 是怎么决定"要不要换认证、要不要换模型"的。

## 学习目标

- 理解 `provider/model` 引用格式背后的设计前提：Provider 插件自己声明模型目录、鉴权方式、失败分类等所有厂商特定行为，OpenClaw 核心只保留一条通用的推理循环。
- 读懂 `src/provider-runtime/operation-retry.ts` 里 `executeProviderOperationWithRetry` 的重试判定逻辑，以及它和"模型失败转移"（model failover）是两套不同粒度的恢复机制。
- 读懂 `src/model-picker/apply-session-model-selection.ts` 在整条链路里扮演的角色——用户主动切模型（`/model`）与配置默认值/自动回退，为什么在失败处理策略上被区别对待。
- 理解 `src/model-catalog/` 和 `packages/model-catalog-core` 如何把多个 Provider 插件各自声明的模型目录，合并成一份规范化的、支持远程覆盖更新的目录。
- 理解模型失败转移的两阶段设计——先在同一 Provider 内部轮换鉴权 profile，再才考虑切换到下一个配置的备选模型——以及"用户显式选择"和"配置默认值"在这条链路上为什么走的是完全不同的严格度策略。

## 背景与设计动机

OpenClaw 支持的模型来源数量级远超典型单一云厂商 SDK：`docs/providers/` 目录下有超过 60 篇独立的 provider 文档，`extensions/` 目录里以模型为主业务的插件也有几十个。如果把这些厂商的鉴权方式、请求协议、限流语义、思考模式全部硬编码进核心推理循环，核心代码会迅速变成一张巨大的 if-else 表。OpenClaw 的解法和很多多模型框架一致：把"厂商是谁"这件事完全下放给插件，核心只认一份统一契约。

`docs/concepts/model-providers.md` 把这条边界写得很直接：

> Most provider-specific logic lives in provider plugins (`registerProvider(...)`) while OpenClaw keeps the generic inference loop. Plugins own onboarding, model catalogs, auth env-var mapping, transport/config normalization, tool-schema cleanup, failover classification, OAuth refresh, usage reporting, thinking/reasoning profiles, and more.

这句话里"failover classification"（失败分类）这个词组值得单独拎出来：OpenClaw 自己并不知道"哪种错误消息意味着限流、哪种意味着账号被封"，这些判定逻辑本身也是每个 Provider 插件通过 `classifyFailoverReason`/`matchesContextOverflowError` 这类 Hook 自己声明的（后面第 02 篇会展开这层插件契约）。核心运行时只负责"拿到分类结果之后该怎么办"——这正是本篇要讲的失败转移状态机。

模型引用的命名空间设计也体现了同一个思路：

> Model refs use `provider/model` (example: `opencode/claude-opus-4-6`).

`provider` 前缀既是路由键，也是插件加载的触发条件——`modelSupport.modelPrefixes` 这类清单让 OpenClaw 在运行时钩子还没建立之前，就能从形如 `acme-large` 的裸模型 ID 猜出该加载哪个插件（这在第 02 篇的 SDK 契约里有具体例子）。托管在云端的模型和本地跑的 GGUF 模型，在这层引用上完全没有区别：`ollama/llama3.3`、`lmstudio/openai/gpt-oss-20b` 和 `anthropic/claude-opus-5` 是同一种记号。

## 核心机制详解

### 1. Provider 运行时的两类重试：操作级 vs 会话级

`src/provider-runtime/` 目录只有两个文件，`operation-retry.ts` 是其中的核心。它导出的 `executeProviderOperationWithRetry` 是一个通用的"给某个 Provider 的辅助操作加退避重试"的工具函数：

```ts
// src/provider-runtime/operation-retry.ts:6-14
export type ProviderOperationRetryStage = "read" | "poll" | "download" | "create";

export type TransientProviderRetryParams = {
  error: unknown;
  message: string;
  provider: string;
  apiKeyIndex: number;
  attemptNumber: number;
  stage?: ProviderOperationRetryStage;
};
```

它按 `stage` 区分默认策略：

```ts
// src/provider-runtime/operation-retry.ts:50-54
function defaultTransientProviderRetryForStage(
  stage: ProviderOperationRetryStage,
): TransientProviderRetryConfig | undefined {
  return stage === "create" ? undefined : true;
}
```

`read`/`poll`/`download` 三类操作默认开启重试，`create`（比如触发一次有副作用的创建型请求）默认不重试——这是一个很朴素但容易被忽略的原则：**幂等的读操作可以安全重试，有副作用的创建操作不能凭空多试一次**。判断"这个错误是不是暂时性的"这件事，同样有一套集中定义的规则：

```ts
// src/provider-runtime/operation-retry.ts:152-154
export function isTransientProviderHttpStatus(status: number): boolean {
  return status === 429 || status === 500 || status === 502 || status === 503 || status === 504;
}
```

配合 DNS 错误码（`ENOTFOUND`）、超时错误名（`TimeoutError`/`RequestTimeoutError`）、以及消息文本里的 `fetch failed` 等信号，`isTransientProviderOperationError()` 把"值不值得重试"收敛成一处可复用的判定逻辑，注释里特别说明了共享的重要性：

> Canonical transient HTTP status predicate for provider operations. Shared by structured-error classification and the guarded POST gate so these paths cannot drift.

注意这里的"重试"和下一节讲的"模型失败转移"（model failover）是两套完全不同粒度的恢复机制：`operation-retry.ts` 面向的是 Provider 插件内部的辅助操作（比如目录发现请求、轮询一个异步生成任务的状态），重试范围是同一个 Provider、同一个凭证、几百毫秒到几秒的指数退避；而失败转移面向的是主推理流的失败——它可能跨越认证 profile、甚至跨越整个 Provider。

### 2. 用户会话选择模型：`apply-session-model-selection.ts`

当用户执行 `/model openai/gpt-5.5 -s` 或者 Gateway 收到 `sessions.patch` 请求时，真正落地这次选择的入口是 `src/model-picker/apply-session-model-selection.ts` 里的 `ApplySessionModelSelectionParams`：

```ts
// src/model-picker/apply-session-model-selection.ts:41-72（节选）
export type SessionModelSelectionRequest = {
  provider: string;
  model: string;
  isDefault: boolean;
  alias?: string;
  profileOverride?: string;
  runtime: { kind: "unchanged" } | { kind: "clear" } | { kind: "set"; runtime: string };
};

export type ApplySessionModelSelectionParams = {
  cfg: OpenClawConfig;
  agentId: string;
  sessionKey: string;
  // ...
  defaultProvider: string;
  defaultModel: string;
  currentProvider: string;
  currentModel: string;
  modelPolicy?: ModelVisibilityPolicy;
  modelCatalog: readonly ModelCatalogEntry[];
  // ...
  request: SessionModelSelectionRequest;
  markLiveSwitchPending: true;
};
```

这个函数把"选中的目标"（`request`）和"当前会话状态"（`currentProvider`/`currentModel`）、"配置默认值"（`defaultProvider`/`defaultModel`）、"模型可见性策略"（`modelPolicy`，即 `agents.defaults.modelPolicy.allow` 那份允许列表）放在同一次调用里做校验和落盘。`markLiveSwitchPending: true` 这个字段名直接呼应了 `docs/concepts/model-failover.md` 里"Live model switching"一节的规则：**只有用户主动发起的模型变更才会标记一次 pending live switch**，系统自身触发的失败转移、心跳覆盖或压缩都不会。这也是为什么下一节要单独讲"选择来源"（selection source）——同一个 `provider/model`，来自用户显式选择和来自配置默认值，在失败之后的处理策略上是不对称的。

### 3. 模型目录是怎么拼出来的：`model-catalog-core` + `manifest-planner`

在讨论"选哪个模型"之前，OpenClaw 得先知道"有哪些模型可选"。每个 Provider 插件在自己的 `openclaw.plugin.json` 里声明一份 `modelCatalog.providers.<id>.models[]`（第 02 篇会看到 DeepSeek 插件的具体例子），这些分散的声明需要被合并成一份规范化的目录。`src/model-catalog/manifest-planner.ts` 负责这件事：

```ts
// src/model-catalog/manifest-planner.ts:1-2, 38-51（节选）
// Manifest model-catalog planner turns plugin catalog declarations into normalized rows and suppressions.
import { normalizeModelCatalogProviderRows } from "@openclaw/model-catalog-core/model-catalog-normalize";
import {
  buildModelCatalogMergeKey,
  normalizeModelCatalogProviderId,
} from "@openclaw/model-catalog-core/model-catalog-refs";
// ...
type ManifestModelCatalogConflict = {
  mergeKey: string;
  ref: string;
  provider: string;
  modelId: string;
  firstPluginId: string;
  secondPluginId: string;
};
```

`ManifestModelCatalogConflict` 这个类型说明了一件事：多个插件完全可能声明同一个 `provider/model` 组合（比如一个厂商被拆成"标准版"和"编码计划版"两个插件，各自都想登记同一条模型），planner 需要显式检测并记录这种冲突，而不是让后声明的静默覆盖前一个。真正的字段级归一化（大小写、别名、定价单位换算）下沉到了 `packages/model-catalog-core` 这个独立包里的 `model-catalog-normalize.ts`/`model-catalog-refs.ts`/`model-catalog-pricing.ts`，保持"目录规划逻辑"和"字段规范化规则"两层关注点分离。

这份本地拼装的目录之上还有一层**远程覆盖**：`docs/concepts/models.md` 的"Hosted catalog updates"一节说明 Gateway 启动时会向公开的 [`openclaw/catalog`](https://github.com/openclaw/catalog) 仓库发一次后台 JSON `GET`，之后最多每六小时检查一次：

> The Gateway makes one background JSON `GET` at startup and then checks at most every six hours. The request sends no prompts, credentials, model usage, or configuration payload beyond the normal HTTP user agent and conditional cache headers... Remote data can update or add models only for providers declared by installed plugin manifests. It cannot supply API base URLs or request headers.

这条边界很关键：远程目录只能**补全元数据**（比如定价、上下文窗口这些描述性字段），不能凭空引入一个未安装插件的 Provider，也不能替换请求所需的 `baseUrl`/`headers`。`src/model-catalog/remote-overlay.ts`/`remote-refresh.ts`/`remote-store.ts` 这几个文件对应的正是这一层：拉取、缓存、按插件声明的 provider 范围做过滤。

### 4. 失败转移的两阶段模型

`docs/concepts/model-failover.md` 开门见山地给出了整体结构：

> OpenClaw handles failures in two stages:
> 1. **Auth profile rotation** within the current provider.
> 2. **Model fallback** to the next model in `agents.defaults.model.fallbacks`.

第一阶段是"同一个 Provider、换一把钥匙"：如果 Anthropic 配置了多个 API Key 或者多个 OAuth 账号，一次限流失败会先尝试轮换到下一个可用的鉴权 profile，而不是立刻放弃这个 Provider。第二阶段才是"换一个模型"，按 `agents.defaults.model.fallbacks` 里配置的顺序逐个尝试。这个顺序本身也不是每次都从头走一遍——OpenClaw 在两次切换之间还插了一层"同模型有限恢复"：

> Before rotating profiles or changing models, the runner attempts bounded same-model recovery for temporary rate limits and provider failures. It continues the existing transcript, preserving partial output and completed work.

也就是说，真实的恢复顺序是：**原地重试（同模型同 profile）→ 认证 profile 轮换（同 Provider 换钥匙）→ 模型回退（换 Provider/模型）**，一层比一层"贵"，只有在便宜的恢复手段确认无效之后才会升级到更贵的那层。

### 5. 选择来源决定了要不要走 fallback 链

`docs/concepts/models.md` 里有一张表把不同来源的模型选择在失败处理上的差异讲得很清楚：

| Source | Behavior |
| --- | --- |
| 配置默认值（`agents.defaults.model.primary`） | 正常起点，走 `agents.defaults.model.fallbacks` |
| 自动回退（`modelOverrideSource: "auto"`） | 临时恢复态，会周期性探测原始主模型是否恢复 |
| 用户会话选择（`/model`、`sessions.patch`） | 精确且严格：这个 provider/model 不可用就直接报错，不会静默换到别的配置模型 |
| Cron `--model` | 视为该任务的主模型，仍走配置好的 fallbacks，除非任务自带 `fallbacks: []` |

这张表背后的设计意图在 `model-failover.md` 里说得很直白：

> User-driven model overrides are treated as exact selections for fallback policy, so an unreachable selected provider surfaces as a failure instead of being masked by `agents.defaults.model.fallbacks`.

换句话说，"用户明确要这个模型"和"系统帮你挑一个能用的模型"是两种不同的契约。如果把二者混为一谈，用户手动切换到某个模型排查问题时，系统却偷偷跑到了另一个模型上应答，这种"看起来成功但其实文不对题"的情况远比一次可见的失败更危险。这也是第 3 节里 `markLiveSwitchPending`/`modelOverrideSource: "user"` 这些字段存在的意义：把"是谁触发的这次选择"作为一等公民信息保留下来，供失败处理逻辑区分对待。

### 6. 冷却时间与账单熔断：错误分类落地成具体数字

Provider 插件通过 `classifyFailoverReason` 把原始错误消息归类成 `rate_limit`/`overloaded`/`billing`/`auth`/`model_not_found` 等几种标准原因（第 02 篇会看到 Bedrock 插件里 `ThrottlingException` → `"rate_limit"`、`ModelNotReadyException` → `"overloaded"` 的具体映射代码）。分类结果落地到冷却策略上是一组具体、随失败次数递增的数字：

> - 1st failure: 30 seconds
> - 2nd failure: 1 minute
> - 3rd+ failure: 5 minutes (cap)

账单类失败（余额不足、信用点耗尽）则走一条更长的"禁用"窗口而不是短冷却：

> Billing/credit failures... are treated as failover-worthy. OpenClaw marks the credential as **disabled** for ten minutes initially and rotates to the next eligible profile/provider.

这里有个容易忽略的细节：`model-failover.md` 特别指出账单失败判定不完全依赖 HTTP 状态码——"Not every billing-shaped response is `402`, and not every HTTP `402` lands here"，因为不同 Provider 对同一类错误返回的状态码并不统一（有的用 `401`/`403` 表达欠费）。这再次印证了"错误分类是 Provider 插件的责任"这条边界：核心运行时只消费分类结果（`rate_limit`/`billing`/...），具体怎么从一段厂商特定的错误文本里识别出这个分类，交给最了解这个厂商的插件去做。

### 7. 认证 profile 的轮换顺序与会话粘性

当一个 Provider 配置了多个 profile（多个 API Key、多个 OAuth 账号），轮换顺序遵循一套固定优先级：

> - **Primary key:** profile type (**OAuth, then static token, then API key**).
> - **Secondary key for OAuth:** profiles with a currently usable access token before profiles whose access token is expired.
> - **Next key:** `usageStats.lastUsed` (oldest first, within each type/state tier).
> - **Cooldown/disabled profiles** are moved to the end.

但轮换并不意味着每次请求都换一把钥匙——OpenClaw 会把自动选中的 profile **粘在会话上**，理由很直接："to keep provider caches warm"。只有在会话被重置、发生了一次压缩、或者当前 profile 进入冷却/禁用状态时，这次粘性绑定才会被重新评估。用户通过 `/model …@<profileId> -s` 手动指定的 profile 待遇更高——它是一个"用户 pin"，即便临时因为限流被轮换到别的 profile，冷却结束后系统会自动切回这个手动指定的 profile，而不需要用户再操作一次。

## 常见问题/易踩坑

- **把"认证 profile 轮换"和"模型回退"当成一回事**：前者发生在同一个 Provider 内部（换钥匙），后者才是切换到 `agents.defaults.model.fallbacks` 里的下一个模型（换厂商/换模型）。诊断一次失败转移时，先看是哪个阶段没扛住，再决定该加认证 profile 还是加 fallback 模型。
- **以为用户手动 `/model` 选择的模型不可用时会自动换到别的模型**：不会。这是刻意设计的"严格"语义——用户选择的模型失败就直接报错，绝不会静默地用另一个模型的回答冒充用户想要的那个模型的回答。只有配置默认值和 cron 任务的主模型才会走 fallback 链。
- **把账单类失败和普通限流混为一谈去调冷却时间**：账单失败走的是固定 10 分钟起步的禁用窗口，且不是所有 `402`/`403` 都属于这一类——具体判定要看 Provider 插件的 `classifyFailoverReason` 返回值，不能只凭 HTTP 状态码猜。

## 小结

OpenClaw 把模型来源统一抽象成 `provider/model` 引用，把"这个厂商怎么鉴权、怎么分类错误、怎么发现模型"这些差异全部下放到 Provider 插件，核心运行时只保留一条通用的推理循环和一套失败转移状态机：先原地重试，再在同一 Provider 内轮换认证 profile，最后才按配置好的顺序切换模型；而"是谁发起了这次模型选择"（配置默认值 vs 用户显式选择）从一开始就被当作一等公民信息保留下来，决定了失败之后是可以静默回退还是必须可见地报错。这一整套抽象之所以能保持核心代码干净，前提是 Provider 插件侧要遵守一套明确的 SDK 契约——下一篇就转向这层契约本身：155 个 `extensions/` 目录里到底有多少是模型 Provider，它们各自的认证方式（API Key 直连、云 IAM 角色、OAuth 订阅复用）又是怎么被同一套 Hook 收敛掉的。
