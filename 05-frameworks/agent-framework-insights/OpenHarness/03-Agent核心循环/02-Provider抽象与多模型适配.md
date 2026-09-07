# Provider 抽象与多模型适配

> `oh` 把"接哪家模型"这件事拆成两层完全独立的关注点：一层是**协议差异如何被抹平**——四个具体客户端类各自把厂商协议翻译成 `run_query()` 认识的三种统一流式事件；另一层是**用户该怎么选、选完之后系统该怎么落地**——`ProviderProfile` 把"认证方式 + 协议格式 + 默认模型"打包成一个个可切换的命名档案（README 里称之为"workflow"），`ui/runtime.py` 里一个不到 50 行的工厂函数负责把选定的档案"物化"成一个真正能用的客户端实例。两层各司其职，谁都不需要知道对方的存在。

## 学习目标

- 理解 `SupportsStreamingMessages` 这个 `Protocol` 如何充当"统一 LLM 接口"，以及它比继承式抽象基类更适合这个场景的原因。
- 读懂 `AnthropicApiClient`、`OpenAICompatibleClient`、`CodexApiClient`、`CopilotClient` 四个具体实现各自要解决的协议转换问题，尤其是消息格式、工具调用格式、流式协议三个维度的真实差异。
- 看懂 `CopilotClient` 用组合（而不是继承或重写）复用 `OpenAICompatibleClient` 的设计,这是一处很典型的"能力最小化实现"范例。
- 理解 `api/registry.py` 这张纯数据表如何做"模型名/密钥前缀/base_url 关键词 → 后端协议类型"的自动检测，以及它和 README 里"workflow + profile"概念的关系。
- 看懂 `config/settings.py` 里的 `ProviderProfile` 目录与 `ui/runtime.py::_resolve_api_client_from_settings()` 工厂函数如何把"用户选的档案"落地成"引擎能用的客户端实例"，完成从配置到运行时对象的闭环。

## 背景与设计动机

`oh` 定位为"Python 版 Claude Code 复刻"，但它面对的模型生态远比 Claude Code 复杂：既要支持 Anthropic 原生协议，也要支持标准 OpenAI Chat Completions 协议（覆盖 DeepSeek、Moonshot、DashScope、Gemini 兼容端点等一整批"OpenAI 兼容"网关），还要支持两种完全不基于 API Key 的场景——复用本地 Claude Code / Codex CLI 已登录的订阅凭据、以及 GitHub Copilot 的设备码 OAuth。

如果不做抽象，`run_query()` 里就得写一堆 `if provider == "anthropic": ... elif provider == "openai": ...` 的分支，而且这些分支会随着新增 Provider 不断膨胀。`oh` 的解法和上一篇提到的 `pi-ai` 统一层思路相似——定义一套与厂商无关的请求/事件类型，把所有协议转换的脏活压到具体适配器内部——但落地方式不同：`pi-ai` 用 TypeScript 的可辨识联合与条件类型在编译期做类型收窄；`oh` 是 Python 项目，选择了运行时的**结构化子类型（`Protocol`，即"鸭子类型"的静态版本）**，加上一张纯数据驱动的 Provider 注册表来处理"一大堆 OpenAI 兼容网关该怎么被自动认出来"这个更偏运营的问题。两种语言、两种取舍，但要解决的核心问题是一样的：把差异收敛到一层薄薄的适配器里，让上层编排逻辑保持无knowledge。

## 核心机制详解

### 统一接口：一个 Protocol，三种事件

```python
# src/openharness/api/client.py
@dataclass(frozen=True)
class ApiMessageRequest:
    model: str
    messages: list[ConversationMessage]
    system_prompt: str | None = None
    max_tokens: int = 4096
    tools: list[dict[str, Any]] = field(default_factory=list)
    effort: str | None = None


@dataclass(frozen=True)
class ApiTextDeltaEvent:
    text: str


@dataclass(frozen=True)
class ApiMessageCompleteEvent:
    message: ConversationMessage
    usage: UsageSnapshot
    stop_reason: str | None = None


@dataclass(frozen=True)
class ApiRetryEvent:
    message: str
    attempt: int
    max_attempts: int
    delay_seconds: float


ApiStreamEvent = ApiTextDeltaEvent | ApiMessageCompleteEvent | ApiRetryEvent


class SupportsStreamingMessages(Protocol):
    """Protocol used by the query engine in tests and production."""

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        """Yield streamed events for the request."""
```

这就是整个统一层的全部契约：一个只有单个方法的 `Protocol`，接收统一形状的 `ApiMessageRequest`，产出三种统一形状的事件之一。用 `Protocol` 而不是 `ABC` 抽象基类是有意为之——`Protocol` 是结构化类型，任何实现了同名同签名 `stream_message` 方法的类都自动满足这个接口，不需要显式继承。`api/client.py` 顶部注释直接写明"Protocol used by the query engine in **tests and production**"：在测试里可以随手写一个假的 `stream_message` 方法伪装成一个模型客户端，完全不需要引入真实的 `AnthropicApiClient` 继承链。

这套契约里最关键的是消息表示：`ConversationMessage` 只有 `"user"` / `"assistant"` 两种角色，工具调用与工具结果分别是 `ToolUseBlock` / `ToolResultBlock` 两种内容块类型（详见第三篇）。这是 Anthropic Messages API 的原生形状——四个适配器里，`AnthropicApiClient` 几乎不用做转换，而 `OpenAICompatibleClient`、`CodexApiClient`、`CopilotClient` 都要把这套"两角色 + 类型化内容块"的模型倒腾成各自厂商要的形状，这也是下面几节的重点。

### AnthropicApiClient：原生协议 + 订阅复用的双模式

`AnthropicApiClient`（详见上一篇提到的重试逻辑所在文件）除了标准的 API Key 模式，还内建了 Claude 订阅复用模式（`claude_oauth=True`）：

```python
# src/openharness/api/client.py
def _create_client(self) -> AsyncAnthropic:
    kwargs: dict[str, Any] = {}
    if self._api_key:
        kwargs["api_key"] = self._api_key
    if self._auth_token:
        kwargs["auth_token"] = self._auth_token
        kwargs["default_headers"] = (
            claude_oauth_headers()
            if self._claude_oauth
            else {"anthropic-beta": OAUTH_BETA_HEADER}
        )
    ...
```

`api_key` 与 `auth_token` 是两条完全不同的鉴权路径——这一处细节会在第四篇详细展开（`claude_oauth_headers()` 如何伪装成真正的 Claude Code CLI 请求），这里先记住一点：**同一个客户端类，通过构造参数在"标准 API Key"和"订阅令牌"两种鉴权模式之间切换**，`stream_message()` 本体的流式解析逻辑（消费 `content_block_delta` 事件、`stream.get_final_message()`）完全复用，不需要为订阅模式单独写一个客户端类。

### OpenAICompatibleClient：把两角色模型摊平成 OpenAI 的多角色消息

```python
# src/openharness/api/openai_client.py
def _convert_messages_to_openai(
    messages: list[ConversationMessage],
    system_prompt: str | None,
) -> list[dict[str, Any]]:
    openai_messages: list[dict[str, Any]] = []
    if system_prompt:
        openai_messages.append({"role": "system", "content": system_prompt})
    for msg in messages:
        if msg.role == "assistant":
            openai_messages.append(_convert_assistant_message(msg))
        elif msg.role == "user":
            tool_results = [b for b in msg.content if isinstance(b, ToolResultBlock)]
            user_blocks = [b for b in msg.content if isinstance(b, (TextBlock, ImageBlock))]
            if tool_results:
                for tr in tool_results:
                    openai_messages.append({
                        "role": "tool", "tool_call_id": tr.tool_use_id, "content": tr.content,
                    })
            if user_blocks:
                ...
    return openai_messages
```

这里能直接看到 `oh` 内部消息模型和 OpenAI Chat Completions 协议的核心差异：Anthropic 风格里，工具结果是 `role="user"` 消息内部的一个内容块；OpenAI 风格里，每个工具结果必须拆成一条独立的 `role="tool"` 消息。适配器要做的就是"拆包"：一条 `oh` 内部的 user 消息，可能同时携带工具结果和用户文本，转换后要变成若干条 `role="tool"` 消息加上（如果还有文本/图片）一条 `role="user"` 消息。

工具调用的转换同理：Anthropic 用 `input_schema`，OpenAI 用嵌套一层 `function.parameters`：

```python
# src/openharness/api/openai_client.py
def _convert_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for tool in tools:
        result.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        })
    return result
```

流式层面的差异更细碎——OpenAI 的流式增量按 `delta.tool_calls[i].function.arguments` 累加字符串片段，而不是像 Anthropic 那样有清晰的 `content_block_start/delta/stop` 三段式；`OpenAICompatibleClient._stream_once()` 因此要自己维护一个 `collected_tool_calls: dict[int, dict[str, Any]]` 按索引累积。更值得一提的是它专门处理了两类"厂商方言"：一是部分推理模型（如 Kimi k2.5）用非标准的 `reasoning_content` 字段携带思维链，且不同 Provider 对这个字段是否要求"哪怕为空也要发送"意见不一致，`oh` 用环境变量 `OPENHARNESS_REQUIRE_EMPTY_REASONING_CONTENT` 让用户自己决定；二是有的模型把推理过程内联在正文里用 `<think>...</think>` 包裹，`_strip_think_blocks()` 要在流式的、块与块之间可能截断标签的情况下正确剥离这部分内容，不让它泄漏到用户可见的文本增量里。GPT-5 一类模型还拒绝 `max_tokens` 参数、要求 `max_completion_tokens`，`_token_limit_param_for_model()` 按模型名前缀分派。这些琐碎但真实的兼容性处理，正是"OpenAI 兼容"这个类别之所以需要专门的适配层而不能简单调一个通用 SDK 的原因。

### CodexApiClient：另一套协议，甚至没有复用 OpenAI SDK

```python
# src/openharness/api/codex_client.py
class CodexApiClient:
    """Client for ChatGPT/Codex subscription-backed Codex Responses."""

    async def _stream_once(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        body: dict[str, Any] = {
            "model": request.model,
            "store": False,
            "stream": True,
            "instructions": request.system_prompt or "You are OpenHarness.",
            "input": _convert_messages_to_codex(request.messages),
            "text": {"verbosity": "medium"},
            "include": ["reasoning.encrypted_content"],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        ...
        headers = _build_codex_headers(self._auth_token)
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("POST", self._url, headers=headers, json=body) as response:
                ...
                async for event in self._iter_sse_events(response):
                    event_type = event.get("type")
                    if event_type == "response.output_text.delta":
                        ...
                    elif event_type == "response.output_item.done":
                        ...
```

`CodexApiClient` 走的是 ChatGPT/Codex 订阅背后的 Responses API（`chatgpt.com/backend-api/codex/responses`），和标准 OpenAI Chat Completions 是两套不同的协议——所以它没有复用 `OpenAICompatibleClient`，而是直接用 `httpx` 手写 SSE 解析（`_iter_sse_events()` 自己按空行切分 `data:` 行、拼接、JSON 解析），事件类型也完全不同：`response.output_text.delta` 对应文本增量，`response.output_item.done` 携带的 `item.type` 是 `"message"` 还是 `"function_call"` 决定这段内容最终落进 `TextBlock` 还是 `ToolUseBlock`，`response.completed` 才携带最终的用量和状态。消息转换那侧同样是另一套形状——工具结果不是 `role="tool"` 消息，而是一种独立的 item 类型 `function_call_output`：

```python
# src/openharness/api/codex_client.py
if isinstance(block, ToolResultBlock):
    result.append({
        "type": "function_call_output",
        "call_id": block.tool_use_id,
        "output": block.content,
    })
```

代码注释里特别提到一个排序约束："Responses API requires function_call_output items to appear before any following user input"——这是 Codex 这套协议独有的顺序要求，`_convert_messages_to_codex()` 因此在遍历每条 user 消息时，先把所有 `ToolResultBlock` 转换过的 `function_call_output` 项追加进去，再追加用户文本/图片项，保证顺序正确。这类"协议专属的隐藏约束"正是统一层存在的意义——把这类知识封死在适配器内部，`run_query()` 完全不需要知道 Codex 的 Responses API 对顺序有什么要求。

### CopilotClient：用组合而不是重新实现

```python
# src/openharness/api/copilot_client.py
class CopilotClient:
    """Copilot-aware API client implementing ``SupportsStreamingMessages``."""

    def __init__(self, github_token: str | None = None, *, enterprise_url: str | None = None, model: str | None = None) -> None:
        ...
        base_url = copilot_api_base(ent_url)
        default_headers: dict[str, str] = {
            "User-Agent": f"openharness/{_VERSION}",
            "Openai-Intent": "conversation-edits",
        }
        raw_openai = AsyncOpenAI(api_key=token, base_url=base_url, default_headers=default_headers)
        self._inner = OpenAICompatibleClient(api_key=token, base_url=base_url)
        # Swap the underlying SDK client so Copilot headers are used.
        self._inner._client = raw_openai  # noqa: SLF001

    async def stream_message(self, request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
        effective_model = self._model or request.model
        patched = ApiMessageRequest(model=effective_model, messages=request.messages, ...)
        async for event in self._inner.stream_message(patched):
            yield event
```

GitHub Copilot 的 Chat 接口本身就是 OpenAI 兼容的，所以 `CopilotClient` 没有重新实现一遍消息转换和流式解析——它在构造函数里创建一个内部的 `OpenAICompatibleClient` 实例，然后**直接替换掉它内部持有的 SDK client**（`self._inner._client = raw_openai`，注释里用 `# noqa: SLF001` 标注这是有意访问"私有"属性），换上一个带有 Copilot 专属请求头（`Openai-Intent: conversation-edits`）的 `AsyncOpenAI` 实例。`stream_message()` 自身只做一件事：把 `model` 覆盖成 Copilot 侧确认可用的模型，其余全部转发给 `self._inner`。

这是一处很值得学习的实现范例：当两个 Provider 的协议本质相同、只是鉴权头/base_url 不同时，**不需要重复实现整套流式解析逻辑**，用组合复用现成的适配器、只覆盖差异点即可。它的代价是产生了一处对"私有"属性的直接赋值，稍微牺牲了一点封装性，换来的是消息转换、`<think>` 剥离、工具调用累积这些逻辑只维护一份。

### Provider 注册表：纯数据驱动的自动检测

```python
# src/openharness/api/registry.py
@dataclass(frozen=True)
class ProviderSpec:
    name: str
    keywords: tuple[str, ...]
    env_key: str
    display_name: str = ""
    backend_type: str = "openai_compat"  # "anthropic" | "openai_compat" | "copilot"
    default_base_url: str = ""
    detect_by_key_prefix: str = ""
    detect_by_base_keyword: str = ""
    is_gateway: bool = False
    is_local: bool = False
    is_oauth: bool = False


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(name="openrouter", keywords=("openrouter",), ...,
                 detect_by_key_prefix="sk-or-", detect_by_base_keyword="openrouter", is_gateway=True),
    ...
    ProviderSpec(name="anthropic", keywords=("anthropic", "claude"), backend_type="anthropic", ...),
    ProviderSpec(name="openai", keywords=("openai", "gpt", "o1", "o3", "o4"), ...),
    ProviderSpec(name="deepseek", keywords=("deepseek",), default_base_url="https://api.deepseek.com/v1", ...),
    ...
    ProviderSpec(name="ollama", keywords=("ollama",), is_local=True,
                 default_base_url="http://localhost:11434/v1", detect_by_base_keyword="localhost:11434"),
)
```

这张表本质上是一份"新增一个 OpenAI 兼容 Provider 只需要加一行数据，不需要写代码"的登记表——文件开头的注释直接写着"Adding a new provider: 1. Add a ProviderSpec to PROVIDERS below. Done."。表里超过 20 个条目按检测优先级排列：先是 Copilot（走独立的 OAuth 分支）、再是网关类（OpenRouter/AiHubMix/SiliconFlow/VolcEngine/ModelScope，靠密钥前缀或 base_url 关键词识别，因为它们可以代理任意模型，不能靠模型名判断)、再是标准云厂商（按模型名关键词识别）、再是云平台（Bedrock/Vertex）、最后是本地部署（Ollama/vLLM）。

```python
# src/openharness/api/registry.py
def detect_provider_from_registry(model, api_key=None, base_url=None) -> ProviderSpec | None:
    """Detection priority: 1. api_key prefix 2. base_url keyword 3. model name keyword."""
    if api_key:
        for spec in PROVIDERS:
            if spec.detect_by_key_prefix and api_key.startswith(spec.detect_by_key_prefix):
                return spec
    if base_url:
        base_lower = base_url.lower()
        for spec in PROVIDERS:
            if spec.detect_by_base_keyword and spec.detect_by_base_keyword in base_lower:
                return spec
    if model:
        return _match_by_model(model)
    return None
```

三级检测优先级本身也是设计：密钥前缀最可靠（`sk-or-` 几乎不可能是别家的密钥），其次是 base_url（用户显式配置了指向某个网关的地址，比模型名更能说明"这是谁的服务"），模型名关键词兜底（最不可靠，因为不同厂商可能有同名模型，`_match_by_model()` 因此优先尝试"model 里有没有形如 `provider/model` 的前缀"精确匹配，再退化到关键词模糊匹配）。

`api/provider.py` 里的 `detect_provider()` 是这张注册表之上的薄封装，但它并不是简单调用 `detect_provider_from_registry()` 就完事——三种订阅/OAuth workflow（`anthropic_claude`、`openai_codex`、`copilot`）根本不是靠模型名或密钥能自动识别的，它们是用户在配置里显式选择的档案，所以 `detect_provider()` 一开始就用 `if settings.provider == "openai_codex": ...` 这样的显式分支直接短路掉，只有落到"没有走订阅/OAuth 路径"的普通 API Key 场景，才会去查注册表。这说明注册表只负责"茫茫多的 OpenAI 兼容网关该怎么被自动认出来"这一类问题，而不负责整个 Provider 体系——三种 workflow 层面的档案在下一节的 `ProviderProfile` 里才是权威定义。

### workflow + profile：从配置到运行时客户端的落地

README 把 Provider 描述成"workflow + profile"而不是底层协议名，这套抽象的真实定义在 `config/settings.py`：

```python
# src/openharness/config/settings.py
class ProviderProfile(BaseModel):
    """Named provider workflow configuration."""
    label: str
    provider: str
    api_format: str
    auth_source: str
    default_model: str
    base_url: str | None = None
    ...

def default_provider_profiles() -> dict[str, ProviderProfile]:
    return {
        "claude-api": ProviderProfile(label="Anthropic-Compatible API", provider="anthropic",
                                       api_format="anthropic", auth_source="anthropic_api_key",
                                       default_model="claude-sonnet-4-6"),
        "claude-subscription": ProviderProfile(label="Claude Subscription", provider="anthropic_claude",
                                                api_format="anthropic", auth_source="claude_subscription",
                                                default_model="claude-sonnet-4-6"),
        "openai-compatible": ProviderProfile(label="OpenAI-Compatible API", provider="openai",
                                              api_format="openai", auth_source="openai_api_key",
                                              default_model="gpt-5.4"),
        "codex": ProviderProfile(label="Codex Subscription", provider="openai_codex",
                                  api_format="openai", auth_source="codex_subscription",
                                  default_model="gpt-5.4"),
        "copilot": ProviderProfile(label="GitHub Copilot", provider="copilot",
                                    api_format="copilot", auth_source="copilot_oauth",
                                    default_model="gpt-5.4"),
        "moonshot": ProviderProfile(label="Moonshot (Kimi)", provider="moonshot", ...),
        ...
    }
```

README "Provider 兼容性概览"表格里的五个 workflow 名字（`Anthropic-Compatible API` / `Claude Subscription` / `OpenAI-Compatible API` / `Codex Subscription` / `GitHub Copilot`），逐字对应这里五个内建 `ProviderProfile` 的 `label` 字段——这不是巧合，是同一份数据既驱动了文档，也驱动了运行时行为。除此之外还内建了 Moonshot、Gemini、MiniMax、NVIDIA NIM、Qwen、ModelScope 几个"开箱即用"的便捷档案，它们本质上都是 `api_format="openai"` 加一个预填的 `base_url`，属于"OpenAI 兼容"这个 workflow 的具体实例，只是为了减少用户手填 base_url 的麻烦而预置成独立条目。

真正把"用户选中的 profile"变成"引擎能调用的客户端实例"的，是 `ui/runtime.py` 里的一个工厂函数：

```python
# src/openharness/ui/runtime.py
def _resolve_api_client_from_settings(settings) -> SupportsStreamingMessages:
    """Build the appropriate API client for the resolved settings."""
    settings = settings.materialize_active_profile()

    def _safe_resolve_auth():
        try:
            return settings.resolve_auth()
        except Exception as exc:
            _print_auth_resolution_error(settings, exc)
            raise SystemExit(1)

    if settings.api_format == "copilot":
        ...
        return CopilotClient(model=copilot_model)
    if settings.provider == "openai_codex":
        auth = _safe_resolve_auth()
        return CodexApiClient(auth_token=auth.value, base_url=settings.base_url)
    if settings.provider == "anthropic_claude":
        return AnthropicApiClient(
            auth_token=_safe_resolve_auth().value, base_url=settings.base_url,
            claude_oauth=True, auth_token_resolver=lambda: settings.resolve_auth().value,
        )
    if settings.api_format in ("openai", "openai_compat"):
        auth = _safe_resolve_auth()
        return OpenAICompatibleClient(api_key=auth.value, base_url=settings.base_url, timeout=settings.timeout)
    auth = _safe_resolve_auth()
    return AnthropicApiClient(api_key=auth.value, base_url=settings.base_url)
```

这个函数把本篇讲到的两条线完整地连了起来：`settings.materialize_active_profile()` 先把当前激活的 `ProviderProfile`（`provider`/`api_format`/`base_url`/`model` 等字段）投影回扁平的 `settings` 字段；分支判断走的正是 `provider`/`api_format` 这两个 profile 级字段，而不是重新去猜模型名；每个分支实例化的正是本篇前四节讲过的四个具体客户端类之一，它们都满足 `SupportsStreamingMessages` 这个 Protocol，因此函数的返回类型可以统一标注为这一个接口，调用方（`RuntimeBundle.api_client`，最终被塞进 `QueryEngine`）完全不需要关心具体是哪一个实现。`claude_oauth=True` 分支额外传入了一个 `auth_token_resolver` 回调——这是为了让 `AnthropicApiClient` 在令牌过期时能自行重新拉取最新凭据（第四篇细讲），而不需要重建整个客户端实例。

`_safe_resolve_auth()` 包了一层容错：`settings.resolve_auth()`（第四篇的核心函数）如果因为凭据缺失抛出异常，这里会打印一条对用户友好的诊断信息然后直接 `SystemExit(1)`，而不是让一个裸的 `ValueError` 堆栈甩到用户脸上——这也是"workflow + profile"这套抽象要解决的用户体验问题之一：让 Provider 选择和鉴权失败的报错口径保持一致。

## 常见问题/关键代码解读

- **为什么不用一个大 `if/elif` 直接在 `run_query()` 里分发协议？** 因为那样会让编排逻辑（工具调用循环、压缩触发、错误自愈）和协议转换逻辑（消息格式、流式事件解析）耦合在一个文件里，任何新增一个 Provider 都要去改核心循环。四个客户端类各自独立实现 `SupportsStreamingMessages`，`run_query()` 永远只面对三种统一事件。
- **`api/registry.py` 和 `config/settings.py` 里的 `ProviderProfile` 是不是重复的两套 Provider 列表？** 不是同一层级的东西。`registry.py` 解决的是"用户没有显式选 profile、只给了一个模型名/密钥/base_url，系统该怎么猜出该用哪种协议"（主要服务于自定义 OpenAI 兼容端点场景）；`ProviderProfile` 是用户显式选择、可持久化、可切换的命名档案,三种订阅/OAuth workflow 完全不经过 `registry.py` 的猜测逻辑。
- **`CopilotClient` 直接改 `self._inner._client` 算不算破坏封装？** 严格来说是的，代码里也用 `# noqa: SLF001` 明确承认了这一点。但这是一个务实的权衡：Copilot 和标准 OpenAI 协议的唯一区别就是几个请求头和 base_url，为这点差异重新实现一遍消息转换和 SSE 解析的成本远高于组合复用带来的封装损失。

## 小结

四个具体客户端类各自吸收了自己那家协议的全部脏活——消息格式、工具调用格式、流式事件、认证方式——对外只暴露 `SupportsStreamingMessages` 这一个薄接口；`api/registry.py` 用一张纯数据表解决了"一大堆 OpenAI 兼容网关怎么被自动认出来"的运营问题；`ProviderProfile` 目录把用户真正要做的选择（"我用哪种 workflow"）和底层协议实现解耦，`ui/runtime.py` 里的工厂函数则是这套抽象最终"物化"成运行时对象的落地点。

到这里，`run_query()` 拿到的 `context.api_client` 是从哪来的、它内部怎么把差异悬殊的协议收敛成统一事件，已经讲清楚了。但消息本身——`ConversationMessage`、`ToolUseBlock`、`ToolResultBlock` 这套内部表示——是怎么在多轮工具调用之间维护一致性的？上下文接近上限时又是怎么被压缩、成本又是怎么被累加统计的？下一篇转向消息状态机、上下文管理与成本跟踪这条线。
