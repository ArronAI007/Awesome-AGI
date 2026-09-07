# Provider Profile 注册表与原生 Adapter 双轨制

> hermes-agent 要同时接入三十多个推理服务商——从官方 Anthropic/OpenAI 到 Kimi、GMI Cloud、OpenCode
> Zen 这类小众中转站。如果每接一家就写一份完整的协议适配器,这套代码会迅速膨胀到无法维护。真实的架构
> 是一套"双轨制":绝大多数 OpenAI 兼容的服务商只用一份声明式的 `ProviderProfile` 描述"这家的怪癖是什
> 么",而少数协议完全不同的厂商(Anthropic、Bedrock、Gemini 原生、OpenAI Responses)才值得单独写一个
> `agent/*_adapter.py`。本篇拆开这套混合架构,并深入读 `anthropic_adapter.py` 这个体量最大、鉴权模式最
> 丰富的原生 adapter。

## 学习目标

- 理解为什么 hermes-agent 选择"多数 Profile + 少数 Adapter"的混合架构,而不是给每个 provider 都写一层
  完整适配器——这是一笔明确的成本/收益权衡。
- 读懂 `providers/base.py` 里 `ProviderProfile` dataclass 的字段设计,理解它"只描述行为、不拥有客户端
  构造/鉴权轮换/流式传输"的职责边界。
- 理解 Profile 的三种发现来源(内置插件、用户插件、pip entry point)和 `register_provider()` 的
  last-writer-wins 覆盖规则。
- 读懂 `agent/anthropic_adapter.py` 里 API Key / OAuth setup-token / Claude Code 凭据三种鉴权模式分支,
  以及 `_get_anthropic_sdk()` 这个"启动时延优化"的具体实现。
- 知道 Profile 和原生 Adapter 分别在 `agent/transports/*.py` 这条转换管线里扮演什么角色。

## 双轨制:为什么不是每个 provider 都写适配器

`plugins/model-providers/` 目录下有三十多个子目录(`openai-codex`、`kimi-coding`、`gmi`、
`opencode-zen`、`deepinfra`、`fireworks`……),但 `agent/` 目录下只有六个 `*_adapter.py` 文件:
`anthropic_adapter.py`(3284 行)、`bedrock_adapter.py`(1948 行)、`codex_responses_adapter.py`
(1896 行)、`gemini_native_adapter.py`(1274 行)、`vertex_adapter.py`、`azure_identity_adapter.py`
(571 行)。这个数量差距不是疏漏,而是一个明确的架构判断:

- **多数厂商的推理接口本来就是 OpenAI Chat Completions 的方言**——请求体形状、消息角色、`tools`
  数组的位置几乎一模一样,真正的差异只是"要不要发 `temperature`""认证头长什么样""模型列表接口在哪
  "这类局部怪癖。给每一家都写一份完整的消息转换器、流式事件解析器,是把同一份协议转换逻辑复制几十遍。
- **少数厂商的协议是彻底不同的形状**——Anthropic Messages API 用 `system` 字段单独放系统提示词、
  `input_schema` 而不是 `parameters`;Bedrock Converse Stream 走 AWS SDK 自己的事件流和 SigV4/Bearer
  双认证;Gemini 原生协议用 `contents`/`parts`;OpenAI Responses API 用 `input` 数组而不是
  `messages`。这些差异复杂到没法用几个布尔字段描述,只能各自写一份专门的消息/工具/流式转换代码。

`providers/base.py` 的模块 docstring 把这条边界讲得很直白:

```python
# providers/base.py:1-10
"""Provider profile base class.

A ProviderProfile declares everything about an inference provider in one place:
auth, endpoints, client quirks, request-time quirks. The transport reads this
instead of receiving 20+ boolean flags.

Provider profiles are DECLARATIVE — they describe the provider's behavior.
They do NOT own client construction, credential rotation, or streaming.
Those stay on AIAgent.
"""
```

也就是说,Profile 解决的是"20 多个布尔开关"的组合爆炸问题——与其在 transport 代码里堆
`if provider == "kimi": ... elif provider == "opencode": ...`,不如让每个 provider 把自己的怪癖声明
成一个数据对象,transport 只认这个对象的字段,不认 provider 的名字。而协议真正不兼容的少数厂商,则
被换到另一条轨道:写一份独立的 `*_adapter.py`,只在自己的转换函数内部处理协议差异,不污染共享的
transport 代码。

## `ProviderProfile`:声明式的怪癖清单

`providers/base.py` 里的 `ProviderProfile` 是一个 dataclass,字段按用途分组:

```python
# providers/base.py:38-102(节选)
@dataclass
class ProviderProfile:
    name: str
    api_mode: str = "chat_completions"
    aliases: tuple = ()

    display_name: str = ""
    description: str = ""
    signup_url: str = ""

    env_vars: tuple = ()
    base_url: str = ""
    models_url: str = ""
    auth_type: str = "api_key"   # api_key|oauth_device_code|oauth_external|copilot|aws_sdk
    supports_health_check: bool = True

    supports_vision: bool = False
    supports_vision_tool_messages: bool = True
    supports_prompt_cache_key: bool = False

    fallback_models: tuple = ()
    hostname: str = ""

    default_headers: dict[str, str] = field(default_factory=dict)

    fixed_temperature: Any = None
    default_max_tokens: int | None = None
    default_aux_model: str = ""
```

值得注意的两个设计细节:

1. **`OMIT_TEMPERATURE` 哨兵对象**。`fixed_temperature` 的取值有三种语义:`None` 表示"用调用方的默
   认值"、一个具体数字表示"这家厂商必须固定成这个值"、而 `OMIT_TEMPERATURE`(`providers/base.py:21`
   定义的 `object()` 哨兵)表示"完全不要发这个字段"——因为 Kimi 这类服务商由服务端自己管理
   temperature,发了反而可能报错。用哨兵对象而不是 `None` 来表达"不发"这层语义,是因为 `None` 已经
   被"用默认值"占用了,需要第三种可区分的取值。
2. **五个可重写的 hook 方法**而不是纯数据字段:`prepare_messages()`(消息预处理)、
   `build_extra_body()`(附加 `extra_body` 字段)、`build_api_kwargs_extras()`(拆分
   `extra_body`/顶层 kwargs)、`get_max_tokens()`(按模型定制输出上限)、`fetch_models()`(拉取实时
   模型目录)。默认实现都是"什么都不做"或"标准 OpenAI 兼容行为",子类按需覆盖——这让 Profile 既能
   是一份纯数据声明,也能在真正需要逻辑时优雅地长出一点代码,而不必为此另开一个完整的 adapter 文件。

## Profile 的三种来源与 last-writer-wins

`providers/__init__.py` 的模块 docstring 直接列出了 Profile 的三种发现渠道:

```python
# providers/__init__.py:1-18(节选)
"""Provider module registry.

Provider profiles can live in three places:

1. Bundled plugins: ``plugins/model-providers/<name>/`` (shipped with hermes-agent)
2. User plugins: ``$HERMES_HOME/plugins/model-providers/<name>/``
3. Pip-installed plugins: distributions exposing a ``hermes_agent.plugins``
   entry point (``module:func`` callable or a self-registering ``module``)

Discovery is lazy: the first call to ``get_provider_profile()`` or
``list_providers()`` scans both locations and imports every plugin. User
plugins override bundled plugins on name collision (last-writer-wins), so
third parties can monkey-patch or replace any built-in profile without
editing the repo.
"""
```

`_discover_providers()` 按固定顺序导入这三类插件,顺序本身就是覆盖优先级的体现:

```python
# providers/__init__.py:271-302(节选)
def _discover_providers() -> None:
    global _discovered
    if _discovered:
        return
    _discovered = True

    # 0. pip entry points — DISCOVERED FIRST, i.e. LOWEST precedence:
    #    running this before the filesystem steps means a bundled or
    #    $HERMES_HOME profile of the same name always overrides a
    #    pip-installed one.
    _discover_entry_point_providers()

    # 1. Bundled plugins — shipped with hermes-agent.
    if _BUNDLED_PLUGINS_DIR.is_dir():
        for child in sorted(_BUNDLED_PLUGINS_DIR.iterdir()):
            if not child.is_dir() or child.name.startswith(("_", ".")):
                continue
            _import_plugin_dir(child, "bundled")

    # 2. User plugins — under $HERMES_HOME/plugins/model-providers/<name>/.
    user_dir = _user_plugins_dir()
    if user_dir is not None:
        for child in sorted(user_dir.iterdir()):
            if not child.is_dir() or child.name.startswith(("_", ".")):
                continue
            _import_plugin_dir(child, "user")

    # 3. Legacy single-file profiles at providers/<name>.py (back-compat).
    ...
```

每个插件目录的 `__init__.py` 在被导入时,都会调用一次 `register_provider(profile)`;而
`register_provider()` 本身没有任何"是否已存在"的判断,直接覆盖字典槽位:

```python
# providers/__init__.py:56-67
def register_provider(profile: ProviderProfile) -> None:
    """Register a provider profile by name and aliases.

    Later registrations with the same name replace earlier ones — so user
    plugins under ``$HERMES_HOME/plugins/model-providers/`` can override
    bundled profiles without editing repo code.
    """
    global _PROVIDER_LIST_CACHE
    _REGISTRY[profile.name] = profile
    for alias in profile.aliases:
        _ALIASES[alias] = profile.name
    _PROVIDER_LIST_CACHE = None
```

这就是"pip 包最先导入、最先被覆盖"这条注释的由来:如果 pip 包先注册、bundled/user 插件后注册,
`register_provider()` 的覆盖语义天然保证了"第一方 profile 永远赢"——第三方包不可能悄悄劫持一个像
`openrouter` 这样官方已占用的 provider 名字,但仍然可以用一个全新的名字注册出全新的 provider。

一份真实的插件目录长这样(`plugins/model-providers/anthropic/`):

```yaml
# plugins/model-providers/anthropic/plugin.yaml
name: anthropic-provider
kind: model-provider
version: 1.0.0
description: Anthropic (Claude)
author: Nous Research
```

```python
# plugins/model-providers/anthropic/__init__.py(节选)
class AnthropicProfile(ProviderProfile):
    """Native Anthropic — uses x-api-key header, not Bearer."""

    def fetch_models(self, *, api_key=None, base_url=None, timeout=8.0):
        """Anthropic uses x-api-key header and anthropic-version."""
        ...

anthropic = AnthropicProfile(
    name="anthropic",
    aliases=("claude", "claude-oauth", "claude-code"),
    api_mode="anthropic_messages",
    env_vars=("ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"),
    base_url="https://api.anthropic.com",
    auth_type="api_key",
    default_aux_model="claude-haiku-4-5-20251001",
)

register_provider(anthropic)
```

再看一个"非平凡 Profile"的例子——`kimi-coding`,它覆盖了两个 hook 来处理 Kimi 特有的 `thinking`/
`reasoning_effort` 互斥规则:

```python
# plugins/model-providers/kimi-coding/__init__.py(节选)
class KimiProfile(ProviderProfile):
    """Kimi/Moonshot — temperature omitted, thinking xor reasoning_effort."""

    def build_api_kwargs_extras(self, *, reasoning_config=None, **context):
        """Moonshot's wire shape treats extra_body.thinking (a binary toggle)
        and a top-level reasoning_effort as mutually exclusive — sending both
        is at best redundant and risks a 400. ... send effort when one is
        requested, otherwise fall back to extra_body.thinking — never both.
        """
        ...

kimi = KimiProfile(
    name="kimi-coding",
    aliases=("kimi", "moonshot", "kimi-for-coding"),
    env_vars=("KIMI_API_KEY", "KIMI_CODING_API_KEY"),
    base_url="https://api.moonshot.ai/v1",
    fixed_temperature=OMIT_TEMPERATURE,
    default_max_tokens=32000,
    default_aux_model="kimi-k2-turbo-preview",
)
register_provider(kimi)
```

Profile 真正生效的地方是 `agent/transports/chat_completions.py::_build_kwargs_from_profile()`——它
逐字段读取 Profile,而不是接收一堆布尔参数:

```python
# agent/transports/chat_completions.py:737-746(节选)
def _build_kwargs_from_profile(self, profile, model, sanitized, tools, params):
    """Build API kwargs using a ProviderProfile — single path, no legacy flags.

    This method replaces the entire flag-based kwargs assembly when a
    provider_profile is passed. Every quirk comes from the profile object.
    """
    from providers.base import OMIT_TEMPERATURE
    sanitized = profile.prepare_messages(sanitized)
    ...
    if profile.fixed_temperature is OMIT_TEMPERATURE:
        pass  # Don't include temperature at all
    elif profile.fixed_temperature is not None:
        api_kwargs["temperature"] = profile.fixed_temperature
    else:
        temp = params.get("temperature")
        if temp is not None:
            api_kwargs["temperature"] = temp
```

## 少数派：`anthropic_adapter.py` 的三种鉴权模式

`agent/anthropic_adapter.py` 是六个原生 adapter 里体量最大、鉴权分支最丰富的一个。它的模块 docstring
直接列出了三种鉴权模式:

```python
# agent/anthropic_adapter.py:1-11
"""Anthropic Messages API adapter for Hermes Agent.

Translates between Hermes's internal OpenAI-style message format and
Anthropic's Messages API. Follows the same pattern as the codex_responses
adapter — all provider-specific logic is isolated here.

Auth supports:
  - Regular API keys (sk-ant-api*) → x-api-key header
  - OAuth setup-tokens (sk-ant-oat*) → Bearer auth + beta header
  - Claude Code credentials (~/.claude.json or ~/.claude/.credentials.json) → Bearer auth
"""
```

三种模式靠 key 的前缀特征区分,`_is_oauth_token()` 是判定入口:

```python
# agent/anthropic_adapter.py:451-476
def _is_oauth_token(key: str) -> bool:
    if not key:
        return False
    # Regular Anthropic Console API keys — x-api-key auth, never OAuth
    if key.startswith("sk-ant-api"):
        return False
    # Anthropic-issued tokens (setup-tokens sk-ant-oat-*, managed keys)
    if key.startswith("sk-ant-"):
        return True
    # JWTs from Anthropic OAuth flow
    if key.startswith("eyJ"):
        return True
    # Claude Code OAuth access tokens (opaque, from CLAUDE_CODE_OAUTH_TOKEN)
    if key.startswith("cc-"):
        return True
    return False
```

而真正决定用哪种鉴权头的地方是 `build_anthropic_client()`,它是一串按优先级排列的判断分支——Kimi
coding 端点、要求 Bearer 的第三方端点、其他第三方端点、OAuth token、最后才是普通 API Key:

```python
# agent/anthropic_adapter.py:912-960(节选)
if _is_kimi_coding_endpoint(base_url):
    kwargs["api_key"] = api_key
    kwargs["default_headers"] = {"HTTP-Referer": ..., "X-Title": ..., ...}
elif _requires_bearer_auth(normalized_base_url):
    # e.g. MiniMax — expects the key in Authorization: Bearer, not x-api-key.
    kwargs["auth_token"] = api_key
elif _is_third_party_anthropic_endpoint(base_url):
    # Microsoft Foundry, AWS Bedrock, self-hosted — their own x-api-key keys,
    # never Anthropic's sk-ant-* convention, so skip OAuth detection entirely.
    kwargs["api_key"] = api_key
elif _is_oauth_token(api_key):
    # OAuth access token / setup-token → Bearer auth + Claude Code identity.
    # Anthropic routes OAuth requests by user-agent; without Claude Code's
    # fingerprint, requests get intermittent 500s.
    kwargs["auth_token"] = api_key
    kwargs["default_headers"] = {
        "anthropic-beta": ",".join(all_betas),
        "user-agent": f"claude-code/{_get_claude_code_version()} (external, cli)",
        "x-app": "cli",
    }
else:
    # Regular API key → x-api-key header
    kwargs["api_key"] = api_key
```

注意判断顺序本身就是设计文档:MiniMax 这类 Bearer-only 第三方必须排在 OAuth 检测之前,因为它们的
密钥不遵循 `sk-ant-*` 前缀,如果顺序反了会被误判成 Anthropic OAuth token。第三种鉴权模式(Claude
Code 凭据)则完全绕开 key 前缀判断,直接从 `~/.claude.json` 或 `~/.claude/.credentials.json` 读取
JSON 文件(`_read_claude_code_credentials_from_keychain()`/`_read_claude_code_credentials_from_file()`
),这是"借用本机已登录的 Claude Code CLI 会话"的路径。

## 启动时延优化:为什么 `import anthropic` 不在模块顶部

`anthropic_adapter.py` 顶部有一段专门解释导入位置的注释:

```python
# agent/anthropic_adapter.py:47-53
# NOTE: `import anthropic` is deliberately NOT at module top — the SDK pulls
# ~220 ms of imports (anthropic.types, anthropic.lib.tools._beta_runner, etc.)
# and the 3 usage sites (build_anthropic_client, build_anthropic_bedrock_client,
# read_claude_code_credentials_from_keychain) are all on cold user-triggered
# paths. Access via the `_get_anthropic_sdk()` accessor below, which caches
# the module after the first call and returns None on ImportError.
_anthropic_sdk: Any = ...  # sentinel — None means "tried and missing"

def _get_anthropic_sdk():
    """Return the ``anthropic`` SDK module, importing lazily. None if not installed."""
    global _anthropic_sdk
    if _anthropic_sdk is ...:
        try:
            from tools.lazy_deps import ensure as _lazy_ensure
            _lazy_ensure("provider.anthropic", prompt=False)
        except ImportError:
            pass
        except Exception:
            pass
        try:
            import anthropic as _sdk
            _anthropic_sdk = _sdk
        except ImportError:
            _anthropic_sdk = None
    return _anthropic_sdk
```

这里有两个值得记住的实现细节:

- **用 `...`(`Ellipsis`)而不是 `None` 作初始哨兵**。因为“尝试过但没装”这个状态本身要用 `None` 表
  示,如果拿 `None` 当"还没试过"的初始值,第一次导入失败后会和"确认不存在"混淆,导致每次调用都要
  重新尝试导入。用 `...` 区分"未初始化"和"已确认不可用"两种状态,是一个常见但容易被忽略的缓存模式。
- **~220ms 的导入耗时只发生在 3 个冷路径上**(构建客户端、读取 Claude Code 钥匙串凭据),而每个
  agent 进程启动时几乎不会用到 Anthropic(用户可能选了别的模型),把这笔耗时推迟到真正需要时才付
  出,是那种"看起来只是挪了几行代码位置"但实测收益很明显的启动时延优化。

其余几个原生 adapter 出于同样的"协议不兼容"理由存在:`bedrock_adapter.py`(AWS SigV4/Bearer 双认
证 + Converse Stream 事件结构)、`gemini_native_adapter.py`(Google 原生 `contents`/`parts` 协议)、
`codex_responses_adapter.py`(OpenAI Responses API 的 `input` 数组形状)、
`azure_identity_adapter.py`(Entra ID token 铸造)。其中 `azure_identity_adapter.py` 和
`anthropic_adapter.py` 还有一层组合关系:`build_anthropic_client()` 的 `api_key` 参数除了接受静态
字符串,也接受一个可调用对象——当调用方传入 Azure Identity 的 bearer token provider 时,
`_build_anthropic_client_with_bearer_hook()` 会构造一个自定义 `httpx.Client`,在每次请求前用这个
callable 铸造一枚新 JWT 并重写 `Authorization` 头,这样"用 Anthropic Messages 协议但走 Azure Entra
ID 鉴权"这种组合也能被支持,而不需要再单独写一个 adapter。

## 小结与思考题

hermes-agent 的多 provider 架构是一套刻意分层的双轨制:`ProviderProfile` 用声明式字段和少量 hook 方
法覆盖了绝大多数 OpenAI 兼容厂商的差异,靠内置插件、用户插件、pip entry point 三种来源和
last-writer-wins 的覆盖规则实现"随时可插拔";而协议本身不兼容的少数厂商——Anthropic、Bedrock、
Gemini、OpenAI Responses——则各自拥有一份独立的 `agent/*_adapter.py`,把鉴权分支、消息转换、流式解
析这些没法用几个字段描述的逻辑封装在各自文件内部,`anthropic_adapter.py` 的三种鉴权模式判断和惰性
SDK 导入是这条思路里最完整的例子。

这套"元数据 Profile + 少数原生 Adapter"的分层,和你如果学过的 PI 的 `pi-ai` 统一接口层、
DeepSeek-Harness 的多 provider seam 骨架,思路是相通的:三者都把"协议怎么转换"和"这次请求归哪个厂
商处理"拆成两层,只是语言与形式不同——`pi-ai` 用 TypeScript 的条件类型（`Model<TApi>` + 
`ApiOptionsMap`）在编译期强制这层对应关系,hermes-agent 则用 Python 的 dataclass 字段和运行时判断达
到类似的效果,前者拿到的是编译期的类型安全,后者换来的是极低的新增 provider 成本(一个 Profile 通常
只需要十几行)。

思考题:

1. `ProviderProfile.fixed_temperature` 用 `OMIT_TEMPERATURE` 这个哨兵对象而不是字符串常量(比如
   `"omit"`)来表达"不发送"语义,这样设计对调用方(`_build_kwargs_from_profile`)的判断代码
   (`is` 比较而不是 `==`)有什么好处?如果换成字符串常量,可能会踩到什么坑?
2. `_discover_providers()` 把 pip entry point 的扫描放在最前面(最低优先级),而不是放在最后(似乎
   更符合"外部插件最后加载、最后生效"的直觉)。结合 `register_provider()` 的覆盖语义,说说这个顺序
   安排为什么反而是"pip 包永远不能劫持第一方 provider 名字"的正确实现。
3. `build_anthropic_client()` 里,MiniMax 这类"Bearer-only 第三方"的判断分支必须排在 OAuth token
   检测之前。如果颠倒这两个分支的顺序,MiniMax 的 API Key 会被怎样误判?误判之后请求会在哪一步失败?
