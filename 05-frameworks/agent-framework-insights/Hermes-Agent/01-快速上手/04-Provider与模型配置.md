# Provider 与模型配置

> `hermes model` 一条命令就能切换模型,不改一行代码——背后是一套"Provider Profile"注册体系:每个 Provider 的接入方式、鉴权、请求怪癖都被声明成一份可插拔的 Profile,而不是散落在各处的 if/else。本篇讲清楚这套体系怎么组织、怎么发现、怎么覆盖。

## 学习目标

- 理解 `hermes model` 背后 Provider/模型切换的用户体验和大致原理
- 掌握 Provider Profile 是什么:一个 `ProviderProfile` 数据类实例,而不是配置文件
- 理解 Profile 的发现顺序——bundled 插件、`$HERMES_HOME` 用户插件、pip entry point 三层来源,以及"后写入者覆盖先写入者"的真实覆盖规则
- 知道非 OpenAI 兼容协议的厂商(Anthropic、Bedrock、Codex)为什么需要单独的 transport 模块,而不是靠 Profile 打个补丁
- 认识 Nous Portal 作为"省事选项"解决的具体问题

## `hermes model`:切换模型的用户体验

安装配置好之后,切换 provider 和模型是一条命令的事:

```bash
hermes model
```

这会弹出一个交互式选择器,列出所有已注册的 Provider 及其模型;也可以在会话内用等价的 `/model [provider:model]` 直接指定。根目录 README 的说法是:

> Use any model you want — Nous Portal, OpenRouter, OpenAI, your own endpoint, and many others. Switch with `hermes model` — no code changes, no lock-in.

而中文版 README 列出了一批具体接入的厂商:Nous Portal、OpenRouter(200+ 模型)、NVIDIA NIM(Nemotron)、小米 MiMo、z.ai/GLM、Kimi/Moonshot、MiniMax、Hugging Face、OpenAI,以及任意自定义端点。这些都不是靠散落的 `if provider == "xxx"` 判断堆出来的,而是统一注册在 `providers/` 这套体系里。

## Provider Profile:声明式的厂商适配层

`providers/README.md` 一句话概括了这套体系的设计目的:

> Each provider is declared once as a `ProviderProfile`. Every other layer — auth resolution, transport kwargs, model listing, runtime routing — reads from these profiles instead of maintaining its own parallel data.

`providers/` 目录本身很薄,只有三个文件:`base.py`(`ProviderProfile` 数据类定义)、`__init__.py`(注册表:`register_provider()`、`get_provider_profile()`、`list_providers()`)、`README.md`。**真正的 Profile 实例**并不写在这里,而是作为插件放在 `plugins/model-providers/<name>/` 下——截至本课程编写时,这个目录下有近 40 个 provider 目录,包括 `anthropic`、`bedrock`、`deepseek`、`gemini`、`nous`、`openrouter`、`openai-codex`、`zai`、`xai` 等等。

每个 Provider 插件目录的标准结构是:

```
plugins/model-providers/deepseek/
├── __init__.py      # 定义 ProviderProfile 实例,调用 register_provider()
└── plugin.yaml       # 清单:name, kind, version, description, author
```

`plugin.yaml` 只是元数据,真正的行为都在 `__init__.py` 里。一个真实的例子——DeepSeek 的 Profile,不仅声明了基础字段,还重写了一个钩子方法来处理该厂商特有的请求格式:

```python
# plugins/model-providers/deepseek/__init__.py
class DeepSeekProfile(ProviderProfile):
    """DeepSeek — extra_body.thinking + top-level reasoning_effort."""

    def build_api_kwargs_extras(
        self, *, reasoning_config: dict | None = None, model: str | None = None, **context
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        extra_body: dict[str, Any] = {}
        top_level: dict[str, Any] = {}
        if not _model_supports_thinking(model):
            return extra_body, top_level
        ...
        extra_body["thinking"] = {"type": "enabled" if enabled else "disabled"}
        ...
        return extra_body, top_level


deepseek = DeepSeekProfile(
    name="deepseek",
    aliases=("deepseek-chat",),
    env_vars=("DEEPSEEK_API_KEY",),
    display_name="DeepSeek",
    description="DeepSeek — native DeepSeek API",
    signup_url="https://platform.deepseek.com/",
    fallback_models=("deepseek-v4-pro", "deepseek-v4-flash"),
    base_url="https://api.deepseek.com/v1",
    default_aux_model="deepseek-v4-flash",
)

register_provider(deepseek)
```

这个例子里的注释解释了一个真实的历史故障(#15700、#17212、#17825):DeepSeek 的 V4 模型系列默认开启"思考模式",一旦 `extra_body.thinking` 没显式设置,API 就会开始要求后续轮次把 `reasoning_content` 原样回传,和 Hermes 重放历史消息的方式冲突,导致 HTTP 400。`build_api_kwargs_extras` 就是把这个厂商特有的怪癖封装在 Profile 内部,而不是污染通用的请求构造逻辑。

`providers/README.md` 里列出的可重写钩子还包括:

| Hook | 用途 |
|------|------|
| `get_hostname()` | 基于 URL 的厂商检测,默认从 `base_url` 推导 |
| `prepare_messages(msgs)` | 厂商特定的消息预处理(比如 Qwen 把消息规范化为分段列表、注入 `cache_control`) |
| `build_extra_body(**ctx)` | 厂商特定的 `extra_body`(OpenRouter 的 provider 偏好、Gemini 的 `thinking_config`) |
| `build_api_kwargs_extras(**ctx)` | 返回 `(extra_body 追加项, 顶层 kwargs)`,比如 Kimi 把 `reasoning_effort` 放在顶层,Qwen 拆成 `enable_thinking`/`thinking_budget` |
| `fetch_models(*, api_key)` | 拉取实时模型目录,默认请求 `{models_url or base_url}/models`,Bedrock、Anthropic OAuth 目录、OpenRouter 公开目录等场景需要重写 |

## 发现顺序与覆盖规则

`providers/__init__.py` 的 `_discover_providers()` 精确描述了三层来源的发现顺序和覆盖优先级:

```python
# providers/__init__.py
def _discover_providers() -> None:
    """Populate the registry by importing every provider plugin.

    Order:
      1. Bundled plugins at ``<repo>/plugins/model-providers/<name>/``
      2. User plugins at ``$HERMES_HOME/plugins/model-providers/<name>/``
      3. Legacy per-file modules at ``providers/<name>.py`` (back-compat)
    """
```

而在这三步**之前**,还有一个"步骤 0"——扫描 pip 安装的第三方包通过 `hermes_agent.plugins` entry point 组注册的 Provider。把完整顺序(从先到后)排出来是:

1. **pip entry point 插件**(最先加载,优先级最低)
2. **仓库自带的 bundled 插件**(`plugins/model-providers/<name>/`)
3. **用户插件**(`$HERMES_HOME/plugins/model-providers/<name>/`,优先级最高)
4. 兼容旧版的单文件 Profile(`providers/<name>.py`,极少使用)

`register_provider()` 的实现是**后注册者覆盖先注册者**(last-writer-wins),源码里的注释直接点明了这个顺序为什么这样安排:

```python
# providers/__init__.py（register_provider 与 _discover_entry_point_providers 的注释节选)
"""Register a provider profile by name and aliases.

Later registrations with the same name replace earlier ones — so user
plugins under ``$HERMES_HOME/plugins/model-providers/`` can override
bundled profiles without editing repo code.
"""
...
# Discovered FIRST, i.e. lowest precedence: because
# ``register_provider()`` is last-writer-wins, running this before the
# filesystem steps means a bundled or ``$HERMES_HOME`` profile of the
# same name always overrides a pip-installed one. That prevents a
# third-party package from silently hijacking a first-party provider
# name (e.g. ``openrouter``) while still letting pip packages add
# genuinely new providers.
```

这是一个值得记住的设计原则:**发现顺序刻意把"信任度最低的来源"放在最前面**——先加载 pip 第三方包,是为了让它处于"最容易被覆盖"的位置,防止一个恶意或写错的第三方包用同名 Provider 顶替掉仓库自带的可信实现(比如伪装成官方的 `openrouter`)。真正想要覆盖内置行为的,是本地用户或团队自己维护的 `$HERMES_HOME/plugins/model-providers/`,它天然是最后加载、优先级最高的一层。

新增一个 Provider 的完整流程,`plugins/model-providers/README.md` 给出了模板:

```python
# plugins/model-providers/<your_provider>/__init__.py
from providers import register_provider
from providers.base import ProviderProfile

my_provider = ProviderProfile(
    name="your-provider",
    aliases=("alias1", "alias2"),
    display_name="Your Provider",
    description="One-line description shown in the setup picker",
    signup_url="https://your-provider.example.com/keys",
    env_vars=("YOUR_PROVIDER_API_KEY", "YOUR_PROVIDER_BASE_URL"),
    base_url="https://api.your-provider.example.com/v1",
    default_aux_model="your-cheap-model",
)

register_provider(my_provider)
```

配上一份 `plugin.yaml` 清单即可——`auth.py`、`config.py`、`models.py`、`doctor.py`、`model_metadata.py`、`runtime_provider.py` 以及 chat_completions transport 全部会自动从注册表里读取这个新 Profile,不需要改任何一处调用方代码。

## 非 OpenAI 兼容厂商:专门的 transport 模块

`ProviderProfile` 这套体系解决的是"OpenAI 兼容协议下的厂商差异"——绝大多数 Provider 走同一条 `agent/transports/chat_completions.py` 请求路径,Profile 的钩子只负责微调请求体细节。但对于**协议本身就不兼容 OpenAI Chat Completions** 的厂商,Hermes 会给它们单独的 transport 实现,而不是硬塞进 Profile 的钩子里。`agent/transports/` 目录下能看到:

```
agent/transports/
├── anthropic.py           # Anthropic Messages API
├── bedrock.py             # Amazon Bedrock
├── chat_completions.py    # OpenAI 兼容协议(绝大多数 Provider 走这条路)
├── codex.py                # OpenAI Codex / Responses API
├── codex_app_server.py     # Codex app-server 运行时
└── ...
```

这是一条清晰的边界:**协议层面的差异用独立 transport 模块解决,请求参数/怪癖层面的差异用 Provider Profile 的钩子解决**。这条边界会在第 04 章(多 Provider 与工具系统)结合 `run_agent.py` 里 `provider_profile=<ProviderProfile>` 参数传递路径进一步展开。

## Nous Portal:省事选项

如果你不想为模型、网页搜索、图像生成、TTS、云浏览器分别去五个不同的地方申请 API Key,Nous Research 自己的 **Nous Portal** 提供了"一个订阅走天下"的选项:

```bash
hermes setup --portal
```

这条命令会走 OAuth 登录、把 Nous 设为推理 provider、并开启 Tool Gateway(网页搜索走 Firecrawl、图像生成走 FAL、TTS 走 OpenAI、云浏览器走 Browser Use,全部通过订阅托管,不需要额外单独注册账号)。README 特别强调了这不是"锁定":

> You can still bring your own keys per-tool whenever you want — the gateway is per-backend, not all-or-nothing.

也就是说 Tool Gateway 是**按工具粒度**生效的,你可以只用 Nous Portal 的模型部分,网页搜索仍然用自己的 Firecrawl Key,两者不冲突。随时可以用 `hermes portal info` 查看当前哪些能力走了 Portal、哪些是自己配的 Key。

`plugins/model-providers/nous/__init__.py` 里的 `NousProfile` 也是一个学习 Profile 钩子的好例子——它重写了 `build_extra_body()` 来注入产品标签和"会话粘滞路由 key"(保证同一个会话的多轮请求路由到同一个上游端点,这样 Anthropic/Vertex/Bedrock 这类实例级缓存才不会每次都冷启动),以及重写 `build_api_kwargs_extras()` 来正确处理"显式关闭思考模式"这个只有 Nous Portal 才支持的语义。

## 小结与思考题

Hermes 把"接入一个新模型厂商"这件事,拆成了两层职责:符合 OpenAI 兼容协议的厂商只需要声明一份 `ProviderProfile`(基础字段 + 可选的钩子重写),放进 `plugins/model-providers/<name>/` 就能被自动发现、自动接入到鉴权、模型列表、请求构造的每一层;协议本身不兼容的厂商(Anthropic、Bedrock、Codex)则有独立的 transport 模块承担协议差异。Profile 的发现顺序刻意把可信度最低的 pip 第三方插件放在最先(因此最容易被覆盖),bundled 内置插件次之,用户在 `$HERMES_HOME` 下的私有插件放在最后(因此优先级最高),`register_provider()` 的"后写入覆盖先写入"语义配合这个顺序,构成了一套完整的可扩展、可覆盖、又防止第三方包冒名顶替的注册机制。Nous Portal 则是在这套开放体系之上,给不想自己攒一堆 API Key 的用户提供的托管选项,而且是按工具粒度可选,不是全有或全无。

## 动手练习

1. 执行 `hermes model`,观察选择器里列出的 provider 名单,尝试在其中找到本篇提到的几个真实存在的 Profile(`deepseek`、`nous`、`openrouter`)。
2. 参照 `plugins/model-providers/README.md` 的模板,在 `$HERMES_HOME/plugins/model-providers/` 下新建一个占位的自定义 Profile(哪怕只是指向一个本地无鉴权的 OpenAI 兼容服务),验证它确实出现在 `hermes model` 的列表里,并且优先级高于任何同名的内置 Profile。

## 思考题

1. 为什么 `_discover_entry_point_providers()` 要求 entry point 目标"零参数可调用"才会被当作 Provider 注册钩子处理?这和它与通用插件共享同一个 entry point 组(`hermes_agent.plugins`)有什么关系?
2. 如果你要给某个已有 Provider 增加"根据模型名动态选择是否发送某个请求参数"的逻辑(就像 DeepSeek Profile 区分 V3/V4 那样),你会倾向于写进 `build_api_kwargs_extras`,还是新开一个字段?为什么这条逻辑不适合写在调用方(比如 `chat_completions.py`)里做 if 判断?
