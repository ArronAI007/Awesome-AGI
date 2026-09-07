# Provider 与模型配置

> Pi 本身不生产智能，它是一层统一的"模型路由器"——本篇讲清楚它能接多少种模型来源，以及怎么接自己的。

## 学习目标

- 理解 Pi 支持的订阅制登录与 API Key 两大类认证方式，以及内置 provider 清单
- 掌握凭证解析优先级和 `key` 字段支持的多种取值语法
- 会通过 `~/.pi/agent/models.json` 添加自定义模型条目（Ollama、vLLM、LM Studio 等）
- 了解通过扩展注册自定义 Provider 和 OAuth 流程的基本思路
- 了解本地 llama.cpp 路由的适用场景与基本用法

## 内置 Provider：订阅制与 API Key 两条路

Pi 内置了多个模型来源的支持，认证方式分两大类。

### 订阅制登录

在交互模式下运行 `/login`，然后选择一个 provider。内置支持的订阅制登录包括：

- ChatGPT Plus/Pro（Codex）—— 需要对应订阅，官方在 [Codex for OSS](https://developers.openai.com/community/codex-for-oss) 中背书了这类第三方 harness 用法
- Claude Pro/Max —— 走 Anthropic 的 [extra usage](https://claude.ai/settings/usage) 额度按 token 计费，不占用套餐内常规额度
- GitHub Copilot —— 登录时对 github.com 直接回车，或输入企业版 Server 域名；若提示"model not supported"，需要先在 VS Code 的 Copilot Chat 模型选择器里手动为该模型点击 "Enable"
- xAI（Grok/X 订阅）—— 运行 `/login xai` 后选择 "Use a subscription"；也可以选 "Use an API key" 走 `XAI_API_KEY`
- OpenRouter —— 运行 `/login openrouter` 走 PKCE 授权流程，会生成一个由你自己掌控、从 OpenRouter 账户余额扣费的 API Key；在 SSH 等无法回环访问本地端口的远程环境下，需要手动把跳转 URL 或授权码粘贴进登录提示
- Radius —— 一种动态的 `pi-messages` 网关，`/login radius` 会把 OAuth token 存进 `auth.json`，模型目录独立刷新并缓存在 `models-store.json`

`/logout` 清除凭证。所有 token 存放在 `~/.pi/agent/auth.json`，过期自动刷新（OpenRouter 例外，它生成的是不会自动过期的用户自控密钥）。

### API Key 认证

Pi 支持的 API Key provider 数量相当庞大，覆盖主流云厂商和一大批国内外模型服务。下面摘录部分核心条目（完整列表以 [`packages/ai/src/env-api-keys.ts`](https://github.com/earendil-works/pi-mono/blob/main/packages/ai/src/env-api-keys.ts) 为准）：

| Provider | 环境变量 | `auth.json` 键 |
|----------|----------|------------------|
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic` |
| OpenAI | `OPENAI_API_KEY` | `openai` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek` |
| Google Gemini | `GEMINI_API_KEY` | `google` |
| Amazon Bedrock | `AWS_BEARER_TOKEN_BEDROCK` | `amazon-bedrock` |
| Mistral | `MISTRAL_API_KEY` | `mistral` |
| Groq | `GROQ_API_KEY` | `groq` |
| Cerebras | `CEREBRAS_API_KEY` | `cerebras` |
| xAI | `XAI_API_KEY` | `xai` |
| OpenRouter | `OPENROUTER_API_KEY` | `openrouter` |
| Vercel AI Gateway | `AI_GATEWAY_API_KEY` | `vercel-ai-gateway` |
| Hugging Face | `HF_TOKEN` | `huggingface` |
| Fireworks / Together AI / Baseten | `FIREWORKS_API_KEY` / `TOGETHER_API_KEY` / `BASETEN_API_KEY` | 对应键名 |
| 智谱 ZAI（国际/国内两版）、MiniMax（国际/国内）、Qwen Token Plan（国际/个人版/国内）、小米 MiMo 等 | 各自专属环境变量 | 各自专属键名 |

使用方式同样是启动前设置环境变量：

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pi
```

也可以直接写入 `~/.pi/agent/auth.json`（文件权限 `0600`，仅当前用户可读写）：

```json
{
  "anthropic": { "type": "api_key", "key": "sk-ant-..." },
  "openai": { "type": "api_key", "key": "sk-..." },
  "deepseek": { "type": "api_key", "key": "sk-..." }
}
```

**凭证解析优先级（从高到低）**：

1. CLI 的 `--api-key` 参数
2. `auth.json` 中的条目（无论是 API Key 还是 OAuth token）
3. 环境变量
4. `models.json` 中自定义 provider 的密钥配置

### `key` 字段的取值语法

无论是 `auth.json` 还是 `models.json`，密钥字段都支持四种写法：

- **执行 shell 命令**：以 `!` 开头，整个值作为命令执行，取其 stdout（在进程生命周期内缓存）
  ```json
  { "type": "api_key", "key": "!security find-generic-password -ws 'anthropic'" }
  { "type": "api_key", "key": "!op read 'op://vault/item/credential'" }
  ```
- **环境变量插值**：`$ENV_VAR` 或 `${ENV_VAR}`，也可以嵌在更长的字面量里；缺失的变量会导致该值无法解析
- **转义**：`$$` 输出字面量 `$`，`$!` 输出字面量 `!`（不会触发命令执行）
- **字面量**：直接使用，注意纯大写字符串会被当作字面量而非环境变量，环境变量必须写成 `$VAR` 的形式

对于本地无鉴权服务（比如 Ollama），`apiKey` 只是一个占位符——因为 Pi 仍然要求模型"看起来配置了认证"才会出现在 `/model` 选择器里，哪怕本地服务器根本不检查这个值。

## 云厂商 Provider

除了直接对接模型厂商，Pi 也支持几种云上路由方式，包括 Azure OpenAI（通过 `AZURE_OPENAI_API_KEY`/`AZURE_OPENAI_BASE_URL`）、Amazon Bedrock（支持 AWS Profile、IAM Key、Bearer Token 等多种凭证来源，并针对 Claude 模型自动开启 Prompt 缓存）、Cloudflare AI Gateway/Workers AI，以及使用 Application Default Credentials 的 Google Vertex AI。这些云厂商各有专属的环境变量组合，属于进阶配置场景,详细参数对照表可以直接查阅仓库文档 `packages/coding-agent/docs/providers.md`,这里不逐一展开，重点放在日常最常用的自定义模型和自定义 Provider 上。

## 自定义模型：`models.json`

如果你想接入 Ollama、vLLM、LM Studio 或任何符合支持协议的服务，不需要写扩展代码,只需编辑 `~/.pi/agent/models.json`。这个文件**每次打开 `/model` 时都会重新加载**，编辑期间无需重启 Pi。

最简形式，只需要 `id`：

```json
{
  "providers": {
    "ollama": {
      "baseUrl": "http://localhost:11434/v1",
      "api": "openai-completions",
      "apiKey": "ollama",
      "models": [
        { "id": "llama3.1:8b" },
        { "id": "qwen2.5-coder:7b" }
      ]
    }
  }
}
```

Pi 支持的 `api` 类型（决定用哪种流式协议解析响应）：

| API 值 | 说明 |
|--------|------|
| `openai-completions` | OpenAI Chat Completions，兼容性最好 |
| `openai-responses` | OpenAI Responses API |
| `anthropic-messages` | Anthropic Messages API |
| `google-generative-ai` | Google Generative AI |

一些 OpenAI 兼容服务器（常见于 Ollama、vLLM、SGLang）不支持 `developer` 角色或 `reasoning_effort` 参数，这时需要用 `compat` 字段声明兼容性：

```json
{
  "providers": {
    "ollama": {
      "baseUrl": "http://localhost:11434/v1",
      "api": "openai-completions",
      "apiKey": "ollama",
      "compat": {
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": false
      },
      "models": [{ "id": "gpt-oss:20b", "reasoning": true }]
    }
  }
}
```

模型级别还可以配置更多字段，例如展示名称 `name`、上下文窗口 `contextWindow`、最大输出 `maxTokens`、单价 `cost`，以及描述模型对不同 thinking level 支持情况的 `thinkingLevelMap`（例如某个模型只支持 `high` 和 `max` 两档思考强度，中间档位就用 `null` 显式标记为不支持）。

`models.json` 还可以**覆盖内置 provider**而不重新定义模型列表——比如把 Anthropic 的请求路由到自建代理：

```json
{
  "providers": {
    "anthropic": {
      "baseUrl": "https://my-proxy.example.com/v1"
    }
  }
}
```

或者用 `modelOverrides` 精细调整某个内置模型（如更改展示名、启用更大的上下文窗口），而不影响该 provider 下的其他模型。这些能力共同构成了一套"不用写代码就能扩展模型来源"的配置层，适合日常接入本地模型或企业代理场景。

## 自定义 Provider：扩展与 OAuth

当 `models.json` 的声明式配置不够用——比如需要自定义鉴权流程、非标准流式协议、动态发现模型列表——就需要写一个扩展（Extension，Pi 用 TypeScript 编写的插件模块），通过 `pi.registerProvider()` 注册。

最简单的场景是给已有 provider 换个 baseUrl 或加请求头（走代理）：

```typescript
pi.registerProvider("anthropic", {
  baseUrl: "https://proxy.example.com"
});
```

注册全新 provider 时，如果提供了 `models` 字段，它会**整体替换**该 provider 原有的模型列表（区别于 `models.json` 的合并语义）：

```typescript
pi.registerProvider("my-llm", {
  baseUrl: "https://api.my-llm.com/v1",
  apiKey: "$MY_LLM_API_KEY",
  api: "openai-completions",
  models: [
    {
      id: "my-llm-large",
      name: "My LLM Large",
      reasoning: true,
      input: ["text", "image"],
      cost: { input: 3.0, output: 15.0, cacheRead: 0.3, cacheWrite: 3.75 },
      contextWindow: 200000,
      maxTokens: 16384
    }
  ]
});
```

如果模型列表需要从远程接口动态获取，扩展的工厂函数可以是 `async` 的——Pi 会等待工厂函数执行完毕再继续启动流程，确保该 provider 在交互式启动和 `pi --list-models` 时都已经就绪。

### OAuth 流程要点

企业内部 SSO、私有模型网关这类需要自定义登录流程的场景，可以通过 `oauth` 字段接入 `/login`：

```typescript
pi.registerProvider("corporate-ai", {
  baseUrl: "https://ai.corp.com/v1",
  api: "openai-responses",
  models: [...],
  oauth: {
    name: "Corporate AI (SSO)",
    async login(callbacks) {
      // 通过 callbacks.onAuth / onDeviceCode / onPrompt / onSelect
      // 与用户交互，换取 access/refresh token
    },
    async refreshToken(credentials, signal) {
      // 用 refresh token 换取新的 access token
    },
    getApiKey(credentials) {
      return credentials.access;
    }
  }
});
```

注册完成后，用户就可以像使用内置 provider 一样运行 `/login corporate-ai`。Pi 提供了 `onAuth`（打开浏览器授权页）、`onDeviceCode`（展示设备码流程）、`onPrompt`（提示用户手动输入）、`onSelect`（弹出选择器，比如让用户在"浏览器 OAuth"和"设备码"之间选择）四类 UI 无关的交互回调，凭证最终持久化在 `~/.pi/agent/auth.json` 中，格式为 `{ refresh, access, expires }`。

如果 provider 的 API 协议既不是 OpenAI 兼容也不是 Anthropic 兼容，还可以实现 `streamSimple` 自定义流式处理逻辑，逐步推送 `text_delta`/`toolcall_delta`/`thinking_delta` 等事件——这属于更底层的多模型 API 层话题，会在《04-多模型统一层-pi-ai》模块结合源码详细讲解，本篇只需要知道这个扩展点存在。

## 本地 llama.cpp 路由

如果你想完全离线、在自己的机器（或局域网内的服务器）上跑开源模型，Pi 内置了对 [llama.cpp](https://github.com/ggml-org/llama.cpp) 路由服务器的支持。这个路由服务器能自动发现多个 GGUF 格式模型文件，并按需加载/卸载，避免同时把所有模型都塞进显存。

启动路由（注意**不要**传 `--model`/`-m`，否则会进入单模型模式而不是路由模式）：

```bash
llama-server \
  --models-dir ~/models \
  --no-models-autoload \
  --jinja \
  --host 127.0.0.1 \
  --port 8080 \
  -ngl 999 \
  -c 32768
```

其中 `--jinja` 用于启用兼容的聊天模板和工具调用能力，`-ngl 999` 尽量把更多层卸载到 GPU，`-c 32768` 设置每个已加载模型的上下文窗口（省略则使用模型原生上下文，可能占用大量显存）。

在 Pi 里配置连接：

```text
/login llama.cpp
```

输入路由地址（默认 `http://127.0.0.1:8080`）和可选的 API Key，也可以用环境变量代替：

```bash
export LLAMA_BASE_URL=http://127.0.0.1:8080
export LLAMA_API_KEY=optional-secret
pi
```

之后用 `/llama` 管理已发现的模型：选中一个未加载的模型即可加载，选中已加载的模型则卸载；也可以选择"Download model…"直接搜索 Hugging Face 并下载指定量化版本。**只有已加载的模型才会出现在 `/model` 里**，加载完成后记得再执行一次 `/model` 选中它。

这个能力最适合的场景是：本地开发调试、隐私敏感场景不希望数据出网、或者单纯想用消费级显卡跑量化过的开源模型做低成本试验。生产级或高质量代码生成任务，通常还是云端商业模型（Claude、GPT 系列等）效果更稳定。

## 动手练习

1. 用 `pi --list-models` 查看当前已认证、可用的模型清单，观察哪些 provider 出现在里面。
2. 在 `~/.pi/agent/models.json` 中添加一个占位的自定义 Ollama 条目（即使本地没有安装 Ollama），保存后运行 `pi --list-models ollama` 确认它能被正确解析（未配置认证时应显示为不可用）。
3.（可选，需要本地已安装 llama.cpp）按上文步骤启动一次路由服务器，用 `curl http://127.0.0.1:8080/health` 验证服务已就绪，再在 Pi 中执行 `/login llama.cpp` 和 `/llama` 走一遍加载模型的流程。

## 小结

Pi 的模型接入分三个层次：内置 provider（订阅登录或环境变量/`auth.json` 即可用）、声明式自定义模型（编辑 `models.json`，无需写代码，适合本地服务和简单代理场景）、以及扩展级自定义 Provider（`pi.registerProvider()`，支持自定义 OAuth、自定义流式协议，适合企业级或非标准 API 场景）。凭证解析统一遵循"CLI 参数 > `auth.json` > 环境变量 > `models.json` 内联密钥"的优先级，`key`/`apiKey` 字段支持命令执行、环境变量插值、转义和字面量四种写法。本地 llama.cpp 路由则为离线/隐私场景提供了官方支持的接入方式。

延伸阅读：多模型统一 API 层（`packages/ai`）如何在内部抽象这些差异化协议，见《04-多模型统一层-pi-ai》模块；扩展系统的完整能力边界见《05-Coding-Agent-CLI实战》模块。
