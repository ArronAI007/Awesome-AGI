# 认证体系：订阅复用与 OAuth

> `oh` 的认证体系里有两类本质不同的模式：一类是教科书式的标准 OAuth（GitHub Copilot 的设备码流程）；另一类是更巧妙也更贴合"Python 版 Claude Code 复刻"这个定位的设计——直接读取本地已经登录过的 Claude Code CLI（`~/.claude/.credentials.json`）或 Codex CLI（`~/.codex/auth.json`）留下的凭据文件，让用户不需要为 `oh` 单独申请一把 API Key、单独付费，只要电脑上装过并登录过官方 CLI，就能直接把已有的订阅额度"借用"过来。

## 学习目标

- 理解 GitHub Copilot 的设备码 OAuth 流程（RFC 8628）在 `oh` 里的完整实现，包括轮询节奏、`slow_down` 退避、令牌落地。
- 理解"复用外部 CLI 凭据"这类认证的核心机制：`oh` 怎么知道去哪个文件/哪个 Keychain 服务读凭据、怎么解析出 access token、以及为什么 Claude 订阅这条路径还需要一套完整的刷新逻辑而 Codex 订阅不需要。
- 看懂 `AnthropicApiClient` 在订阅模式下是如何在请求头和 metadata 里"伪装"成真正的 Claude Code CLI 客户端的，理解这么做背后的必要性。
- 理解 `AuthManager` 如何把"活跃的 provider profile"、"凭据存储"、"外部绑定"这几件事统一到一套状态查询与切换接口之上。
- 理解 profile 级凭据隔离（`credential_slot`）的实现，明白它解决的是"多个同类型 Provider 档案不能共用一把全局 key"这个具体问题。

## 背景与设计动机

一个多 Provider Agent Harness 的认证需求，通常比"存一个 API Key"复杂得多。`oh` 要同时满足：

- **标准 OAuth 场景**：GitHub Copilot 没有直接对外发放长期 API Key，只能走设备码授权流程换一个 GitHub OAuth token。
- **订阅复用场景**：越来越多用户已经为 Claude Code、Codex CLI 这类官方产品付费订阅，如果 `oh` 强制要求用户再单独去申请一把按量计费的 API Key，对这批用户是重复付费；`oh` 选择直接复用这些官方 CLI 本地已经登录好的凭据文件，把订阅额度接过来用。
- **多档案隔离场景**：同一个用户可能同时配置了两个"OpenAI 兼容"档案指向不同的自建网关，如果两者共用同一把全局存储的 `openai` 密钥，切换档案时密钥会互相覆盖。

这些场景的复杂度决定了 `oh` 不能只用一个"读环境变量或读配置文件里的 key"的简单函数了事，而是需要一整套分层的解析逻辑——第二篇提到的 `settings.resolve_auth()` 正是这套逻辑的核心入口，本篇要拆开看它内部到底在做什么。

## 核心机制详解

### 标准 OAuth：GitHub Copilot 的设备码流程

设备码流程（Device Authorization Grant）的入口在 `auth/flows.py` 的 `DeviceCodeFlow`，实际的网络交互封装在 `api/copilot_auth.py`：

```python
# src/openharness/api/copilot_auth.py
COPILOT_CLIENT_ID = "Ov23li8tweQw6odWQebz"

def request_device_code(*, client_id=COPILOT_CLIENT_ID, github_domain="github.com") -> DeviceCodeResponse:
    url = f"https://{github_domain}/login/device/code"
    resp = httpx.post(url, json={"client_id": client_id, "scope": "read:user"}, ...)
    resp.raise_for_status()
    data = resp.json()
    return DeviceCodeResponse(
        device_code=data["device_code"], user_code=data["user_code"],
        verification_uri=data["verification_uri"],
        interval=data.get("interval", 5), expires_in=data.get("expires_in", 900),
    )

def poll_for_access_token(device_code, interval, *, client_id=COPILOT_CLIENT_ID, github_domain="github.com",
                           timeout=900, progress_callback=None) -> str:
    url = f"https://{github_domain}/login/oauth/access_token"
    poll_interval = float(interval)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(poll_interval + _POLL_SAFETY_MARGIN)
        resp = httpx.post(url, json={
            "client_id": client_id, "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }, ...)
        data: dict[str, Any] = resp.json()
        if "access_token" in data:
            return data["access_token"]
        error = data.get("error", "")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            server_interval = data.get("interval")
            if isinstance(server_interval, (int, float)) and server_interval > 0:
                poll_interval = float(server_interval)
            else:
                poll_interval += 5.0
            continue
        raise RuntimeError(f"OAuth device flow failed: {data.get('error_description', error)}")
    raise RuntimeError("OAuth device flow timed out waiting for user authorisation.")
```

这是标准 RFC 8628 流程的忠实实现：先向 `/login/device/code` 换取 `device_code`（后台轮询用）和 `user_code`（展示给用户输入到浏览器），然后按服务端指定的 `interval` 轮询 `/login/oauth/access_token`。轮询逻辑里两个值得注意的细节：`_POLL_SAFETY_MARGIN = 3.0` 秒被加在每次轮询间隔之上，主动比服务端要求的最小间隔慢一点，避免卡在限流边界；`slow_down` 错误码会让轮询间隔按服务端建议动态调大（如果服务端没给具体数字就退而求其次地固定加 5 秒），这是设备码流程规范里明确要求客户端配合的行为，`authorization_pending` 则单纯表示"用户还没操作完，继续等"。

`auth/flows.py::DeviceCodeFlow.run()` 在这层网络交互之上包了一层用户体验：尝试自动打开浏览器（`_try_open_browser()`，按 macOS/Windows/Linux 分平台调用 `open`/`os.startfile`/`xdg-open`），打不开就把 URL 打印出来让用户手动访问。这里有一处专门写在注释里的安全考量——`_try_open_browser()` 一开始就用 `urlparse(url).scheme not in {"http", "https"}` 拦掉非法 scheme，Windows 分支特意选择 `os.startfile()` 而不是 `subprocess.Popen([...], shell=True)`，注释直接点明原因：`shell=True` 会经过 `cmd.exe` 解释，如果设备码流程返回的 `verification_uri` 里恶意/被篡改地包含了 `&`、`|`、`^` 这类 shell 分隔符，就有可能被当成附加命令执行；`os.startfile()` 走 Windows 的 `ShellExecute`，不经过命令行解释器，从根本上避免了这类注入。

拿到 GitHub OAuth token 之后，落地非常简单——`save_copilot_auth()` 直接把 `{"github_token": ..., "enterprise_url": ...}` 写进 `~/.openharness/copilot_auth.json`（权限 0600）。这个 token 后续会被 `CopilotClient`（第二篇讲过）直接当 Bearer token 用在 Copilot API 请求头上，不需要任何额外的 token 交换步骤。

### 订阅复用：从"文件在哪"到"怎么解析"

这是本篇的核心机制,定义在 `auth/external.py`。第一步是知道去哪找凭据：

```python
# src/openharness/auth/external.py
def default_binding_for_provider(provider: str) -> ExternalAuthBinding:
    if provider == CODEX_PROVIDER:
        codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
        return ExternalAuthBinding(
            provider=provider, source_path=str(codex_home / "auth.json"),
            source_kind="codex_auth_json", managed_by="codex-cli", profile_label="Codex CLI",
        )
    if provider == CLAUDE_PROVIDER:
        configured_dir = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
        if configured_dir:
            return ExternalAuthBinding(
                provider=provider, source_path=str(Path(configured_dir).expanduser() / ".credentials.json"),
                source_kind="claude_credentials_json", managed_by="claude-cli", profile_label="Claude CLI",
            )
        if platform.system() == "Darwin":
            return ExternalAuthBinding(
                provider=provider, source_path=f"{_KEYCHAIN_BINDING_PREFIX}{CLAUDE_KEYCHAIN_SERVICE}",
                source_kind="claude_credentials_keychain", managed_by="claude-cli", profile_label="Claude CLI",
            )
        claude_home = Path(os.environ.get("CLAUDE_HOME", "~/.claude")).expanduser()
        return ExternalAuthBinding(
            provider=provider, source_path=str(claude_home / ".credentials.json"),
            source_kind="claude_credentials_json", managed_by="claude-cli", profile_label="Claude CLI",
        )
    raise ValueError(f"Unsupported external auth provider: {provider}")
```

这段代码验证了 README 里"Codex Subscription 复用 `~/.codex/auth.json`"和"Claude Subscription 复用 `~/.claude/.credentials.json`"这两句表述的确切来源——路径可以被 `CODEX_HOME`/`CLAUDE_CONFIG_DIR`/`CLAUDE_HOME` 环境变量覆盖，与官方 CLI 自身的配置约定保持一致（意味着如果用户改过官方 CLI 的配置目录，`oh` 也能跟着找对地方）。有意思的是 macOS 上 Claude 凭据有第二条路径：官方 Claude Code CLI 在 macOS 上默认把凭据存进系统 Keychain（服务名 `Claude Code-credentials`）而不是普通文件，`oh` 因此在没有显式配置 `CLAUDE_CONFIG_DIR` 的 macOS 环境下，默认直接去读 Keychain：

```python
# src/openharness/auth/external.py
def _read_claude_credentials_from_keychain(binding: ExternalAuthBinding) -> tuple[dict[str, Any], Path, str, str | None]:
    service = binding.source_path.removeprefix(_KEYCHAIN_BINDING_PREFIX).strip() or CLAUDE_KEYCHAIN_SERVICE
    raw_payload = subprocess.check_output(["security", "find-generic-password", "-w", "-s", service], text=True)
    metadata = subprocess.check_output(["security", "find-generic-password", "-s", service], text=True)
    payload = json.loads(raw_payload)
    keychain_path = _extract_keychain_path(metadata) or (Path.home() / "Library/Keychains/login.keychain-db")
    account = _extract_keychain_attr(metadata, "acct")
    return payload, keychain_path, service, account
```

直接调用 macOS 自带的 `security` 命令行工具读取 Keychain 条目——一次拿密文本身（`-w` 参数），一次拿元数据（不带 `-w`，用来解析出 Keychain 文件路径和账户名，供后面写回刷新后的 token 时使用）。这说明"复用外部凭据"这件事在不同平台上是不同的具体实现,`oh` 需要跟着官方 CLI 存储凭据的实际位置走，而不是自己发明一套统一格式。

拿到原始 payload 之后，Codex 和 Claude 的解析路径完全不同：

```python
# src/openharness/auth/external.py
def _load_codex_credential(payload, source_path, binding) -> ExternalAuthCredential:
    tokens = payload.get("tokens")
    access_token = str(tokens.get("access_token", "") or "") if isinstance(tokens, dict) else ""
    if not access_token:
        access_token = str(payload.get("OPENAI_API_KEY", "") or "")
    ...
    expires_at_ms = _decode_jwt_expiry(access_token)
    return ExternalAuthCredential(provider=CODEX_PROVIDER, value=access_token, auth_kind="api_key", ...)
```

Codex 这边只是"读出来、解析过期时间，然后直接用"——没有自动刷新逻辑。而 Claude 这边多了一整套刷新机制：

```python
# src/openharness/auth/external.py（节选）
def _load_claude_credential(payload, source_path, binding, *, refresh_if_needed, ...):
    claude_oauth = payload.get("claudeAiOauth")
    access_token = str(claude_oauth.get("accessToken", "") or "")
    refresh_token = str(claude_oauth.get("refreshToken", "") or "")
    expires_at_ms = _coerce_int(claude_oauth.get("expiresAt"))
    credential = ExternalAuthCredential(provider=CLAUDE_PROVIDER, value=access_token, auth_kind="auth_token", ...)
    if refresh_if_needed and is_credential_expired(credential):
        if not refresh_token:
            raise ValueError(f"Claude credentials at {source_path} are expired and cannot be refreshed.")
        refreshed = refresh_claude_oauth_credential(refresh_token)
        if binding.source_kind == "claude_credentials_keychain":
            _write_claude_credentials_to_keychain(..., access_token=str(refreshed["access_token"]), ...)
        else:
            write_claude_credentials(source_path, access_token=str(refreshed["access_token"]), ...)
        credential = ExternalAuthCredential(provider=CLAUDE_PROVIDER, value=str(refreshed["access_token"]), ...)
    return credential
```

这里有一处非常值得留意的设计：`refresh_claude_oauth_credential()` 刷新出新 token 之后，是**直接写回原始的外部凭据文件（或 Keychain 条目）**，而不是写进 `oh` 自己的存储。这意味着这是一条双向同步：`oh` 用官方 Claude Code CLI 登录过的凭据换取新 token 之后，官方 CLI 下次启动时读到的也是这个刷新后的新 token——不是"借用一次就完了"，而是与官方 CLI 共享同一份凭据的生命周期。

```python
# src/openharness/auth/external.py
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_OAUTH_TOKEN_ENDPOINTS = (
    "https://platform.claude.com/v1/oauth/token",
    "https://console.anthropic.com/v1/oauth/token",
)

def refresh_claude_oauth_credential(refresh_token, *, scopes=None) -> dict[str, Any]:
    requested_scopes = list(scopes or CLAUDE_AI_OAUTH_SCOPES)
    payload = json.dumps({
        "grant_type": "refresh_token", "refresh_token": refresh_token,
        "client_id": CLAUDE_OAUTH_CLIENT_ID, "scope": " ".join(requested_scopes),
    }).encode("utf-8")
    ...
    for endpoint in CLAUDE_OAUTH_TOKEN_ENDPOINTS:
        request = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            ...
            if "invalid_grant" in body:
                last_error = ValueError("... Run `claude auth login` to refresh the official Claude CLI credentials, then run `oh auth claude-login` again.")
                continue
            ...
        access_token = str(result.get("access_token", "") or "")
        ...
        return {"access_token": access_token, "refresh_token": next_refresh, "expires_at_ms": ..., "scopes": result.get("scope")}
    ...
```

刷新请求用的 `client_id` 是 `oh` 自己注册的一个 OAuth client（`CLAUDE_OAUTH_CLIENT_ID`），依次尝试两个端点（`platform.claude.com`、`console.anthropic.com` 作为回退）；如果服务端返回 `invalid_grant`（说明连 refresh token 本身都失效了），错误信息里直接给出了修复路径——"先运行 `claude auth login` 刷新官方 CLI 的凭据，再重新运行 `oh auth claude-login`"，把用户导向正确的修复动作，而不是留一个裸的 401 错误。

这套"Codex 不自动刷新、Claude 会自动刷新"的不对称，从代码里看是真实存在的：`_load_codex_credential()` 没有任何刷新分支，只是解析 JWT 里的 `exp` 声明供上层判断是否已过期；只有 `_load_claude_credential()` 接了 `refresh_if_needed` 参数并在过期时真正发起刷新请求。至于这个不对称是否会在未来版本补齐，不影响本篇要传达的核心机制——两条订阅复用路径共享"读外部文件/Keychain → 解析出 access token"这套框架，但"过期后要不要自动续期"是各自独立决定的。

### 伪装成官方客户端：为什么请求头要这么写

拿到订阅令牌之后，用这个令牌发请求也不是简单套一个 Bearer header 就完事。`AnthropicApiClient` 在 `claude_oauth=True` 模式下的行为，在第二篇简单提过一句，这里展开看:

```python
# src/openharness/auth/external.py
CLAUDE_COMMON_BETAS = ("interleaved-thinking-2025-05-14", "fine-grained-tool-streaming-2025-05-14")
CLAUDE_OAUTH_ONLY_BETAS = ("claude-code-20250219", "oauth-2025-04-20")

def claude_oauth_betas() -> list[str]:
    return list(CLAUDE_COMMON_BETAS + CLAUDE_OAUTH_ONLY_BETAS)

def claude_attribution_header() -> str:
    version = get_claude_code_version()
    return f"x-anthropic-billing-header: cc_version={version}; cc_entrypoint=cli;"

def claude_oauth_headers() -> dict[str, str]:
    all_betas = ",".join(claude_oauth_betas())
    return {
        "anthropic-beta": all_betas,
        "user-agent": f"claude-cli/{get_claude_code_version()} (external, cli)",
        "x-app": "cli",
        "X-Claude-Code-Session-Id": get_claude_code_session_id(),
    }

def get_claude_code_version() -> str:
    """Return the locally installed Claude Code version or a fallback."""
    global _claude_code_version_cache
    if _claude_code_version_cache is not None:
        return _claude_code_version_cache
    for command in ("claude", "claude-code"):
        try:
            result = subprocess.run([command, "--version"], capture_output=True, text=True, timeout=5, check=False)
        except Exception:
            continue
        version = (result.stdout or "").strip().split(" ", 1)[0]
        if result.returncode == 0 and version and version[0].isdigit():
            _claude_code_version_cache = version
            return version
    _claude_code_version_cache = CLAUDE_CODE_VERSION_FALLBACK
    return _claude_code_version_cache
```

`user-agent` 直接写成 `claude-cli/<version> (external, cli)`、带上 `claude-code-20250219` 这样明显是 Claude Code 专属的 beta 标志、甚至连版本号都优先去 `subprocess.run(["claude", "--version"])` 问一遍本地真正安装的 Claude Code CLI（问不到才退回硬编码的 `CLAUDE_CODE_VERSION_FALLBACK`）——这一整套请求头拼装的目的，是让这次请求在服务端看起来尽可能"像"是从官方 Claude Code CLI 发出的。这么做是必要的：订阅额度的计费/权限判定绑定在"这是不是来自 Claude Code 客户端"这件事上，而不是绑定在一把通用的 API Key 上，所以复用订阅意味着必须同时复用官方客户端在协议层面暴露的全部特征，而不只是那个 access token 本身。

`AnthropicApiClient._stream_once()` 里能看到这些头信息真正被组装进请求的位置：

```python
# src/openharness/api/client.py
if self._claude_oauth:
    attribution = claude_attribution_header()
    params["system"] = f"{attribution}\n{params['system']}" if params.get("system") else attribution
if self._claude_oauth:
    params["betas"] = claude_oauth_betas()
    params["metadata"] = {
        "user_id": json.dumps({"device_id": "openharness", "session_id": self._session_id, "account_uuid": ""}, separators=(",", ":"))
    }
    params["extra_headers"] = {"x-client-request-id": str(uuid.uuid4())}
stream_api = self._client.beta.messages if self._claude_oauth else self._client.messages
```

订阅模式下走的是 SDK 的 `beta.messages` 端点而不是普通的 `messages`，`metadata.user_id` 里带的 `device_id` 诚实地标成了 `"openharness"`（没有伪装成 Claude Code 本身的 device id），但整体请求形状——beta 标志集合、请求头、attribution 信息——都在尽力对齐官方客户端的协议表现。

### AuthManager：状态查询与切换的统一入口

`auth/manager.py::AuthManager` 是本篇前面几节机制之上的一层薄封装，它不重新实现任何底层逻辑，而是把"当前有哪些 profile、每个 profile 认证状态如何、怎么切换、怎么存取凭据"统一成一套查询/变更接口：

```python
# src/openharness/auth/manager.py
def get_auth_source_statuses(self) -> dict[str, Any]:
    active_profile_name, active_profile = self.settings.resolve_profile()
    result: dict[str, Any] = {}
    for source in _AUTH_SOURCES:
        configured, origin, state, detail = False, "missing", "missing", ""
        storage_provider = auth_source_provider_name(source)
        if source == "anthropic_api_key":
            ...
        elif source in {"codex_subscription", "claude_subscription"}:
            binding = load_external_binding(storage_provider)
            if binding is not None:
                external_state = describe_external_binding(binding)
                configured, origin, state, detail = (
                    external_state.configured, external_state.source,
                    external_state.state, external_state.detail,
                )
        ...
        result[source] = {"configured": configured, "source": origin, "state": state, "detail": detail,
                           "active": source == active_profile.auth_source, "active_profile": active_profile_name}
    return result
```

值得注意的是这里的 `state` 不是简单的布尔"配不配置"——`describe_external_binding()`（`auth/external.py`）会区分 `missing`（文件不存在）、`invalid`（文件存在但解析失败）、`expired`（token 过期且没有 refresh token 可用）、`refreshable`（过期但有 refresh token，下次使用时会自动刷新）、`configured`（正常可用）五种状态，这些细粒度状态直接决定了 CLI/UI 层给用户展示什么样的提示文案与修复建议。

`use_profile()`/`switch_auth_source()`/`upsert_profile()` 这些写操作则统一走 `self.settings.model_copy(update={...}).materialize_active_profile()` 这个模式——先在不可变的 Pydantic 模型上做 `model_copy` 产生新实例，再调用 `materialize_active_profile()` 把新激活的 profile 字段投影回扁平字段（第二篇提到过这个方法），最后持久化。这与仓库整体的不可变编码风格是一致的：从不在原地修改 `Settings` 实例的字段。

### 凭据存储：文件优先，Keyring 可选，OAuth 绑定只存"指针"

底层持久化在 `auth/storage.py`，默认后端是 `~/.openharness/credentials.json`（权限 0600），可选升级到系统 Keyring：

```python
# src/openharness/auth/storage.py
def _keyring_available() -> bool:
    global _keyring_checked, _keyring_usable
    if _keyring_checked:
        return _keyring_usable
    _keyring_checked = True
    try:
        import keyring
        keyring.get_password(_KEYRING_SERVICE, "__probe__")
        _keyring_usable = True
    except ImportError:
        _keyring_usable = False
    except Exception as exc:
        log.info("System keyring unavailable, using file backend: %s", exc)
        _keyring_usable = False
    return _keyring_usable
```

这个探测只做一次并缓存结果——因为 `keyring` 包能被 import 成功不代表真的有可用的后端（容器、CI、无头 Linux/WSL 环境常见 import 成功但探测失败），实际探测一次比每次调用都假设"能 import 就能用"更可靠，缓存则避免每次读写凭据都重新走一遍探测开销与重复告警。文件头部的注释也专门澄清了安全边界："当没有可用的 Keyring 后端时，凭据以**明文 JSON** 形式存储，仅靠 POSIX 文件权限（0600）保护；文件里的 `_obfuscate`/`_deobfuscate` 只是 XOR 编码，**不是加密**，不能用来保护真正的密钥"——这段自我声明式的安全边界说明，比默默留一个容易被误用的"加密"函数名要负责得多。

`ExternalAuthBinding` 的存储只是元数据指针，不涉及真实凭据：

```python
# src/openharness/auth/storage.py
def store_external_binding(binding: ExternalAuthBinding) -> None:
    with exclusive_file_lock(_creds_lock_path()):
        data = _load_creds_file()
        entry = data.setdefault(binding.provider, {})
        entry["external_binding"] = asdict(binding)
        _save_creds_file(data)
```

`oh` 自己的 `credentials.json` 里，对应 `codex_subscription`/`claude_subscription` 这两种订阅认证源，存的从来只是 `ExternalAuthBinding`（`source_path`/`source_kind`/`managed_by` 这类"去哪读"的指针信息），真正的 access token / refresh token 永远留在官方 CLI 自己的凭据文件或 Keychain 里，`oh` 每次使用时才去读一遍最新值。这是"复用"而不是"复制"的关键体现——`oh` 不会把订阅凭据另存一份副本,凭据的唯一权威来源始终是官方 CLI 自己的存储。

### profile 级凭据隔离：不再强制共用一把全局 key

README 提到"Anthropic/OpenAI 兼容接口支持 profile 级凭据，不再强制共用一把全局 key"，落地在 `ProviderProfile.credential_slot` 字段与 `settings.resolve_auth()` 的解析优先级里：

```python
# src/openharness/config/settings.py
def credential_storage_provider_name(profile_name: str, profile: ProviderProfile) -> str:
    """Custom compatible profiles can set ``credential_slot`` to bind their own key."""
    del profile_name
    if auth_source_uses_api_key(profile.auth_source) and profile.credential_slot:
        return f"profile:{profile.credential_slot}"
    return auth_source_provider_name(profile.auth_source)
```

```python
# src/openharness/config/settings.py（resolve_auth 节选）
if profile.credential_slot:
    scoped_storage_provider = f"profile:{profile.credential_slot}"
    scoped = load_credential(scoped_storage_provider, "api_key", use_keyring=False)
    if scoped is None:
        scoped = load_credential(scoped_storage_provider, "api_key")
    if scoped:
        return ResolvedAuth(provider=..., auth_kind="api_key", value=scoped, source=f"file:{scoped_storage_provider}", state="configured")
```

默认情况下，一个 `api_format="openai"` 的 profile 存取密钥用的存储命名空间是 `auth_source_provider_name(profile.auth_source)`（比如统一落在 `"openai"` 这个 key 下）——如果用户建了两个都指向不同自建网关的"OpenAI 兼容"档案,它们会共用同一把存储密钥，切换其中一个必然覆盖另一个。设置了 `credential_slot` 之后，存储命名空间变成 `f"profile:{profile.credential_slot}"`，每个 profile 只要 slot 名不同就彻底隔离，互不干扰。这正是 README 那句承诺的确切实现:不是默认行为的改变（默认仍然是按 provider 类型共享），而是新增了一个可选的逃生舱口，让需要隔离的用户可以显式声明。

`resolve_auth()` 里完整的解析优先级，把本篇讲到的所有路径串成一条链：**订阅类** auth_source（`codex_subscription`/`claude_subscription`）→ 环境变量逃生舱口（仅 `claude_subscription` 支持 `ANTHROPIC_AUTH_TOKEN`）优先于外部绑定 → 外部绑定（读取并按需刷新）；**Copilot** → 直接短路成一个占位 `ResolvedAuth`（真正的 token 由 `CopilotClient` 自己从 `copilot_auth.json` 读取）；**API Key 类** → `credential_slot` 隔离存储 > 环境变量（`OPENHARNESS_*` 前缀优先于裸变量名）> 扁平 `settings.api_key` 兜底。这条优先级链条本身没有被写成一张表或一份文档,它就是 `resolve_auth()` 这一个函数体的控制流——想确认某个具体场景下 `oh` 到底会用哪个凭据,读这一个函数就是唯一可靠的答案来源。

## 常见问题/易踩坑

- **Claude 订阅凭据过期后会自动刷新，Codex 订阅不会**——这是当前代码里真实存在的不对称，`_load_codex_credential()` 没有刷新分支，遇到过期的 Codex 凭据需要用户重新运行 `codex login`（官方 CLI）或 `oh auth codex-login`。
- **`claude_subscription` 只能对接官方 Anthropic/Claude 端点**——`resolve_auth()` 里会用 `is_third_party_anthropic_endpoint(profile.base_url)` 显式检查，一旦发现 base_url 指向非 `anthropic.com`/`claude.com` 的第三方地址就直接抛错，提示用户改用 API-Key 驱动的 Anthropic 兼容档案，而不是静默尝试把订阅令牌发给一个不认识它的第三方端点。
- **XOR 混淆不是加密**——`auth/storage.py` 里的 `_obfuscate`/`_deobfuscate`（别名 `encrypt`/`decrypt`，标记为向后兼容、即将废弃）明确注释为非加密用途，真正的密钥安全性完全依赖文件权限（0600）或系统 Keyring，不要因为看到 `encrypt` 这个别名就误以为凭据文件本身是加密的。

## 小结

`oh` 的认证体系把"怎么拿到一个能用的模型访问凭据"拆成了泾渭分明的两条路：标准 OAuth 走教科书式的设备码流程，凭据落地成一个独立文件；订阅复用则直接读官方 CLI 的凭据存储，Claude 这一侧甚至做到了刷新后双向回写、与官方 CLI 共享凭据生命周期。这一切之所以能对上游模型服务"以假乱真"，靠的是 `AnthropicApiClient` 在订阅模式下精心拼装的请求头与 metadata。`AuthManager` 把这些底层机制统一成一套状态查询/切换接口，`credential_slot` 则解决了多档案共存时的隔离问题。

到这一章为止，四篇文章把"用户发一句话到模型返回、到工具执行、再到下一轮模型调用"这条主循环从头到尾走了一遍：`run_query()` 的循环骨架、Provider 抽象层如何吸收协议差异、消息状态机与上下文压缩如何维持一个可持续的对话，以及这一切依赖的认证凭据是怎么被拿到手的。下一章会转向工具、Skills、Plugins 和 MCP 构成的扩展生态——这条主循环本身并不知道"工具"具体能做什么，它只认识 `ToolRegistry.to_api_schema()` 吐出来的那份 JSON Schema 列表,以及 `context.tool_registry.get(tool_name)` 返回的可执行对象;工具、Skills、插件、MCP server 这些能力究竟是怎么被发现、加载、注册进这份列表里的,正是下一章要展开的内容。
