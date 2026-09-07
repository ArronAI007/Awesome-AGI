# 模型与 Provider 配置速览

> OpenClaw 的引导流程有一条几乎不近人情的硬性规则：“every path establishes inference first”——不管你是通过 CLI、macOS App 还是 Linux 桌面伴侣程序开始设置，OpenClaw 都会先探测你已有的模型访问方式、等你选定一个连接、拿这个连接跑一次**真实的模型补全**，只有这次补全成功了，才会往下配置 workspace、Gateway、channel 这些其余的一切。没有一条推理路径能被正常使用，OpenClaw 就不会真正启动——这不是产品的某个小细节，而是整个 Onboarding 设计的第一原则。

## 学习目标

- 理解 Model Provider 在 OpenClaw 里是一层独立的抽象：`provider/model` 形式的模型引用、托管 API 与本地运行时（Ollama/LM Studio/vLLM 等）共用同一套配置体系。
- 分清“官方 Provider 插件”和“通过 `models.providers` 自定义配置”这两条路径的边界：前者自带模型目录、不需要手写模型元数据，后者用于自定义端点或代理。
- 读懂 Onboarding 的“先验证推理、再配置其余”这条硬规则具体是怎么落地的：检测→选择→真实补全验证→持久化。
- 知道“重新认证/新增 Provider”和“切换默认模型”是两件不同的事——新增一个 Provider 的凭证，并不会顺手把它变成默认模型。
- 明确本篇只建立第一手直觉，Provider 插件的 SDK 契约、模型能力元数据的完整规则，留给第 05 章深入。

## 背景与设计动机

OpenClaw 支持的模型提供方数量相当可观——`docs/concepts/model-providers.md` 里列出的官方 Provider 插件加上“其他 bundled provider”表格，加起来有三四十家，从 OpenAI、Anthropic 这类头部厂商，到 Moonshot、Z.AI、Volcano Engine 这类区域性厂商，再到 Ollama、LM Studio、vLLM 这类完全跑在本机的本地推理服务。如果每接入一家就要在核心代码里写一段专属逻辑，核心很快会被“供应商适配代码”淹没。

OpenClaw 的解法和它在 Channels 上的思路是一致的：把“某个具体 Provider 怎么鉴权、怎么拉模型目录、怎么处理它专属的请求参数”这些逻辑，下放给 Provider 插件自己实现，核心只保留一个通用的推理循环。`docs/concepts/model-providers.md` 说得很直接：

> Most provider-specific logic lives in provider plugins (`registerProvider(...)`) while OpenClaw keeps the generic inference loop. Plugins own onboarding, model catalogs, auth env-var mapping, transport/config normalization, tool-schema cleanup, failover classification, OAuth refresh, usage reporting, thinking/reasoning profiles, and more.

这也解释了为什么官方 Provider 数量能做到几十家却不显臃肿：核心永远只面对一个统一接口，增量成本被摊给了插件本身，而不是摊给每一次模型请求（呼应 VISION.md“两层两条门槛”的插件哲学）。

但不管接了多少家 Provider，Onboarding 的第一道关卡永远是同一个：必须先有一条**验证过的、真实可用**的推理路径。这条设计的动机也很直接——一个连不上模型的 agent，后面配置的 channel、workspace、skill 全都没有意义；与其让用户在配置完一大堆东西之后才发现模型调不通，不如把这道验证挪到最前面。

## 核心机制详解

### `provider/model`：一个统一的模型引用格式

不管背后是托管 API 还是本地服务，OpenClaw 里所有模型都用同一种引用格式表达：`provider/model`，例如 `anthropic/claude-opus-5`、`ollama/llama3.3`、`opencode/claude-opus-4-6`。`docs/concepts/model-providers.md` 的“Quick rules”一节把几条基础规则列在了最前面：

> - Model refs use `provider/model` (example: `opencode/claude-opus-4-6`).
> - `agents.defaults.models` stores aliases and per-model settings; `agents.defaults.modelPolicy.allow` is the optional explicit override allowlist.
> - CLI helpers: `openclaw onboard`, `openclaw models list`, `openclaw models set <provider/model>`.

配置一个模型作为默认值，写法上非常朴素：

```json5
// openclaw.json 节选（docs/concepts/model-providers.md）
{
  agents: { defaults: { model: { primary: "anthropic/claude-opus-5" } } },
}
```

### 官方 Provider 插件 vs. 自定义 `models.providers`

这是理解模型配置时最容易搞混的一条边界。文档明确划了线：

> Official provider plugins publish their own model catalog rows. These providers require **no** `models.providers` model entries; enable the provider plugin, set auth, and pick a model. Use `models.providers` only for explicit custom providers or narrow request settings such as timeouts.

也就是说，如果你用的是 OpenAI、Anthropic、Moonshot 这类“官方插件已经支持”的 Provider，你需要做的只是启用插件、配好鉴权、选一个模型——插件自己会把可用模型目录、上下文窗口大小、是否支持视觉输入这些元数据都注册好，不需要你手写。只有当你要接入一个官方插件没有覆盖的自定义端点（比如一个私有部署的 OpenAI 兼容代理），才需要自己在 `models.providers` 里声明：

```json5
// openclaw.json 节选：自定义 OpenAI 兼容代理（docs/concepts/model-providers.md）
{
  models: {
    providers: {
      lmstudio: {
        baseUrl: "http://localhost:1234/v1",
        apiKey: "${LM_API_TOKEN}",
        api: "openai-completions",
        models: [
          {
            id: "my-local-model",
            name: "Local Model",
            reasoning: false,
            input: ["text"],
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
            contextWindow: 200000,
            maxTokens: 8192,
          },
        ],
      },
    },
  },
}
```

值得留意的是，即便是这类自定义配置，`docs/concepts/model-providers.md` 也给出了未声明字段的合理默认值（`reasoning: false`、`input: ["text"]`、cost 全部为 0），而不是要求你把每个字段都填满——降低了接一个陌生 OpenAI 兼容端点的门槛。

本地推理服务（Ollama、LM Studio、vLLM、llama.cpp、SGLang）走的是同一套 `provider/model` 语法，只是鉴权环节通常是可选的：

```bash
# 安装 Ollama、拉取模型
ollama pull llama3.3
```

```json5
// openclaw.json 节选：本地 Ollama（docs/concepts/model-providers.md）
{
  agents: {
    defaults: { model: { primary: "ollama/llama3.3" } },
  },
}
```

### Onboarding 里的推理验证闸门

`docs/start/onboarding-overview.md` 描述的引导阶段，核心动作就两步：探测已有的模型访问方式，然后对你选定的那一个，跑一次真实补全：

> The guided inference phase establishes only:
>
> 1. **Model provider and auth** — detected access or a verified provider sign-in, API key, or token
> 2. **Verified inference** — a real completion on the default agent's effective model

`docs/start/wizard.md` 把 Quick Start 流程拆解得更细，值得逐步对照：

> 1. Choose **Quick start** after the one-line security pointer.
> 2. Detect configured models, API-key environment variables, supported local AI CLIs, and already installed tool-capable models from reachable Ollama or LM Studio servers on the Gateway host. This read-only pass never downloads a model.
> 3. Choose the detected connection you want, or select a supported provider. Only that connection is tested with a real completion. If it fails, review the error and choose whether to retry, select another provider, or skip.
> ...
> 5. Save the verified route, prepare the agent workspace, and persist Gateway settings.
> 6. Start the Gateway in the foreground and open the browser dashboard.

这里有几个细节值得点出来。第一，“detect”这一步是**只读**的——它不会下载模型、不会跑推理、不会写任何配置，纯粹是探测你机器上已经有哪些可用的凭证或本地服务。第二，“test”这一步只针对你**选定**的那一个连接，不会挨个尝试所有探测到的选项。第三，失败不会自动切换到下一个候选——`docs/cli/onboard.md` 补充了这条：

> The selected connection runs a real completion. If it fails, the error is shown and the picker waits for your next choice. Cancellation stops the attempt without trying another provider.

也就是说，验证失败之后，OpenClaw 不会替你“聪明地”换一个 Provider 重试，而是把错误原样展示出来，把决定权交还给操作者。这跟前面几篇反复出现的设计取向是一致的：自动化只做“探测”，不做“替你做决定”。

### 一个容易误解的地方：新增鉴权不等于切换默认模型

配置多个 Provider 之后，一个常见的直觉误区是“我刚给某个 Provider 配了新的 API key，它是不是就成默认模型了”。文档专门用一个 Accordion 把这条反直觉的规则单独强调出来：

> `openclaw configure` preserves an existing `agents.defaults.model.primary` when you add or reauth a provider. `openclaw models auth login` does the same unless you pass `--set-default`. Provider plugins may still return a recommended default model in their auth config patch, but OpenClaw treats that as "make this model available" when a primary model already exists, not "replace the current primary model."
>
> To intentionally switch the default model, use `openclaw models set <provider/model>` or `openclaw models auth login --provider <id> --set-default`.

这背后的逻辑是：“添加一种新的模型访问方式”和“把这种访问方式设为默认”是两个不同强度的操作，前者应该是无副作用的（“多一个选项而已”），后者才应该真正改变 agent 的行为。如果每次重新认证一个 Provider 都悄悄换掉了默认模型，操作者很容易在毫无预警的情况下发现 agent 突然换了一个完全不同性格的模型在跑——这类“静默行为变化”正是 OpenClaw 整体设计里刻意规避的东西。

### 非交互式场景：同一套闸门，不能绕过

自动化脚本/CI 场景下，onboarding 支持 `--non-interactive`，但“先验证推理”这条闸门并没有因此被绕过——只是验证的输入换成了命令行参数和环境变量：

```bash
# 非交互式配置 OpenAI（docs/cli/onboard.md 节选）
export OPENAI_API_KEY="your-provider-key"
openclaw onboard --non-interactive --accept-risk --skip-health \
  --auth-choice openai-api-key \
  --secret-input-mode ref
```

这里 `--secret-input-mode ref` 值得多说一句：它让新增的凭证以“引用”而不是明文的形式存进配置——`keyRef: { source: "env", provider: "default", id: "OPENAI_API_KEY" }`，真正的密钥值仍然只存在于环境变量里，配置文件本身不落盘明文密钥。`--accept-risk` 是另一道必须显式跨过的门槛，它承认“agent 很强大、给它完整系统访问权限是有风险的”这一事实，但它**不会**替你批准需要额外能力审查的插件安装——如果本地设置需要一个尚未安装的外部 Provider 运行时（比如 OpenAI 场景下的 Codex 插件），非交互式 onboarding 会在需要能力审查的地方直接停下来，提示你先手动审查并安装：

```bash
# 先审查并预装所需插件，再重跑 onboarding（docs/cli/onboard.md 节选）
openclaw plugins install codex --accept-capabilities
openclaw onboard --non-interactive --accept-risk --skip-health \
  --auth-choice openai-api-key --secret-input-mode ref
```

这条设计和前面“首次自动引导、之后必须显式操作”的思路是同一种取舍：`--accept-risk` 只覆盖“这个 agent 本身很强大”这一层风险确认，不能顺带跨过“要不要信任这个具体插件”这一层单独的审查动作。

## 常见问题/易踩坑

- **以为装好某个 Provider 插件、配好 key，agent 就自动开始用它**：配置了鉴权只是“让这个模型可用”，要真正启用还需要显式 `openclaw models set <provider/model>` 或在 onboarding/`configure` 里选中它作为 primary。
- **在自定义 `models.providers` 里漏填 `contextWindow` 导致上下文预算算错**：未声明的 `contextWindow` 会保持“未设置”状态而不是套用某个隐藏默认值，如果既没有发现机制也没有手写这项元数据，上下文预算会退回 200000 token 的标准兜底值——不确定的话建议显式填写，匹配你这个代理/模型的真实限制。
- **本地模型只是“安装在磁盘上”却没有实际跑起来，以为 OpenClaw 能自动发现它**：以 Ollama 为例，OpenClaw 的检测读的是运行中服务的“已加载模型”状态（`/api/ps`），只是安装在磁盘上但没有加载的模型需要显式走 **Choose connection → Local only** 配置，而不是自动被发现。

## 小结

OpenClaw 把“具体某个 Provider 怎么鉴权、怎么请求”的复杂度都交给了 Provider 插件，核心只维护一个通用的 `provider/model` 引用格式和一条推理循环；而不管背后接了多少家供应商，Onboarding 永远坚持“先验证一条真实可用的推理路径，再谈其余配置”这条第一原则，并且把“新增可用模型”和“切换默认模型”严格区分开，避免行为的静默变化。Provider 插件 SDK 的完整契约、模型能力元数据的详细规则、以及故障转移（model failover）机制，留给第 05 章深入。下一篇是本章最后一篇，也是最重要的一篇——在正式拆开任何一个子系统之前，先把 OpenClaw 的安全基线和信任模型看清楚：入站消息默认不可信、工具默认在宿主机上跑、Gateway 鉴权对本地和远程连接一视同仁，这几条字面写在 VISION.md 和 SECURITY.md 里的规则，决定了后面每一章讨论具体机制时的默认假设。
