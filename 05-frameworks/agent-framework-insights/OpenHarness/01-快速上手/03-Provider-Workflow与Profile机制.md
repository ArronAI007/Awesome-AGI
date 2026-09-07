# Provider Workflow 与 Profile 机制

> `oh setup` 表面上是一个五步向导，但它真正解决的是一个更底层的建模问题：把"用哪个 API 协议"、"怎么认证"、"用哪个具体后端"、"用哪个模型"这四件强相关又经常被绑死在一起的事情拆成正交的维度，用一个叫 Profile 的对象重新组合起来。这也是为什么 Kimi、GLM、MiniMax 这些同样走 Anthropic 协议的后端,现在可以各自持有一把独立的 key,而不必像早期版本那样共用一把全局 `anthropic` key。

## 学习目标

- 走一遍 `oh setup` 真实的五步引导流程,并对照源码理解每一步具体在做什么。
- 理解 OpenHarness 内置的五种 workflow（Anthropic-Compatible API / Claude Subscription / OpenAI-Compatible API / Codex Subscription / GitHub Copilot）分别对应什么认证方式。
- 掌握 `oh provider list/use`、`oh auth status`、`oh provider add` 的日常用法。
- 理解"workflow + profile"这个抽象为什么比裸的 provider 协议名更好用，尤其是它如何解决"多个 Anthropic 兼容后端共享一把 key"的老问题。
- 明确这一篇讲的是引导层的使用方式，Provider 抽象和多模型适配的源码级细节留给第 03 章第 2 篇。

## 背景与设计动机

在只有一个模型供应商的世界里，"配置" 无非是填一个 API key。但 OpenHarness 支持的后端横跨 Anthropic 官方 API、Claude CLI 订阅桥接、OpenAI 官方及一大批 OpenAI 兼容网关（OpenRouter、DashScope、DeepSeek、SiliconFlow、Groq、Ollama……）、Codex CLI 订阅桥接、GitHub Copilot OAuth，这些后端在"用什么协议发请求"和"怎么证明你有权限调用"这两件事上差异很大——有的是简单的 API key，有的是本地 CLI 工具留下的订阅凭据文件，有的是 OAuth device flow。

如果把这些差异直接暴露给用户（"选一个 provider 协议名，再填一个 key"），用户很快会撞上一个具体的老问题：Kimi、GLM、MiniMax 这些后端都实现了 Anthropic 兼容协议，如果配置层只认"provider=anthropic"这一个维度，就意味着这几个后端会被迫共用同一把 `anthropic` key——而它们实际上是完全独立的账号体系。`README.zh-CN.md` 里对这次改动的描述很直接：

> Anthropic/OpenAI 兼容接口支持 profile 级凭据，不再强制共用一把全局 key。

`oh setup` 引入的解法是在"provider 协议"之上再加一层——**Profile**。一个 Profile 把 `label`（展示名）、`provider`（运行时协议标识）、`api_format`（请求格式）、`auth_source`（认证来源类型）、`base_url`、`credential_slot`（凭据存储位置）、`allowed_models` 这些原本散落的字段打包成一个具名对象。`credential_slot` 这个字段是解决"共享 key"问题的关键——它让一个自定义的 Anthropic 兼容 profile 可以把凭据存到自己专属的存储槽位，而不是复用 `provider=anthropic` 这个协议名对应的全局槽位。

## 核心机制详解

### `oh setup` 的真实五步流程

`src/openharness/cli.py` 里的 `setup_cmd` 函数就是 `oh setup` 的完整实现，逐行拆开正好对应五个逻辑步骤：

```python
# src/openharness/cli.py
@app.command("setup")
def setup_cmd(
    profile: str | None = typer.Argument(None, help="Provider profile name to configure"),
) -> None:
    """Unified setup flow: choose workflow, authenticate if needed, then set the model."""
    from openharness.auth.manager import AuthManager
    from openharness.config.settings import display_model_setting

    manager = AuthManager()
    statuses = manager.get_profile_statuses()
    if not statuses:
        print("No provider profiles available.", file=sys.stderr)
        raise typer.Exit(1)

    target = profile
    if target is None:
        target = _select_setup_workflow(
            statuses,
            default_value=manager.get_active_profile(),
        )

    target = _specialize_setup_target(manager, target)
    manager = AuthManager()
    statuses = manager.get_profile_statuses()

    if target not in statuses:
        print(f"Unknown provider profile: {target!r}", file=sys.stderr)
        raise typer.Exit(1)

    info = statuses[target]
    if not info["configured"]:
        source_label = _AUTH_SOURCE_LABELS.get(info["auth_source"], info["auth_source"])
        print(f"{info['label']} requires {source_label}.", flush=True)
        _ensure_profile_auth(manager, target)
        manager = AuthManager()
    else:
        if _maybe_update_profile_auth(manager, target):
            manager = AuthManager()

    profile_obj = manager.list_profiles()[target]
    model_setting = _prompt_model_for_profile(profile_obj)
    if model_setting.lower() == "default":
        manager.update_profile(target, last_model="")
    else:
        manager.update_profile(target, last_model=model_setting)
    manager.use_profile(target)
    ...
```

- **第一步：选择 workflow**——`_select_setup_workflow` 渲染一个选择器,列出所有 profile 状态（内置的 + 用户已保存的），默认高亮当前激活的 profile。
- **第二步：`_specialize_setup_target`**——这一步容易被忽略,但实际上是"选家族、还是选具体后端"这个二级分支的关键：如果用户选的是笼统的 `claude-api`（Anthropic-Compatible API）,会进一步弹出 Claude 官方 / Kimi / GLM / MiniMax 的二级选择,选中非官方选项后立刻在这一步内联收集 Base URL 和 Model,生成一个具体的新 profile 并返回它的名字;`openai-compatible` 走的是类似逻辑（OpenAI 官方 vs OpenRouter）。
- **第三步：认证**——如果目标 profile 还没配置好（`info["configured"]` 为 `False`），调用 `_ensure_profile_auth`,根据 `auth_source_uses_api_key` 判断走 API key 输入流程还是外部 OAuth/订阅绑定流程。
- **第四步：确认模型**——`_prompt_model_for_profile` 根据 profile 的 `allowed_models` 或者是否是 Claude 家族 provider,决定弹出一个模型别名选择器还是一个自由输入框。
- **第五步：保存并激活**——`manager.update_profile(target, last_model=...)` 落盘,`manager.use_profile(target)` 把这个 profile 设为当前激活的 profile。

### 五种内置 workflow 分别对应什么

`src/openharness/config/settings.py` 里的 `default_provider_profiles()` 定义了内置的 Profile 目录，README 里提到的五种主 workflow 分别对应这里的具体条目：

```python
# src/openharness/config/settings.py
def default_provider_profiles() -> dict[str, ProviderProfile]:
    """Return the built-in provider workflow catalog."""
    return {
        "claude-api": ProviderProfile(
            label="Anthropic-Compatible API",
            provider="anthropic",
            api_format="anthropic",
            auth_source="anthropic_api_key",
            default_model="claude-sonnet-4-6",
        ),
        "claude-subscription": ProviderProfile(
            label="Claude Subscription",
            provider="anthropic_claude",
            api_format="anthropic",
            auth_source="claude_subscription",
            default_model="claude-sonnet-4-6",
        ),
        "openai-compatible": ProviderProfile(
            label="OpenAI-Compatible API",
            provider="openai",
            api_format="openai",
            auth_source="openai_api_key",
            default_model="gpt-5.4",
        ),
        "codex": ProviderProfile(
            label="Codex Subscription",
            provider="openai_codex",
            api_format="openai",
            auth_source="codex_subscription",
            default_model="gpt-5.4",
        ),
        "copilot": ProviderProfile(
            label="GitHub Copilot",
            provider="copilot",
            api_format="copilot",
            auth_source="copilot_oauth",
            default_model="gpt-5.4",
        ),
        ...
    }
```

`Claude Subscription` 和 `Codex Subscription` 这两个 workflow 的 `auth_source` 是 `claude_subscription`/`codex_subscription`，它们不需要用户输入任何 API key——`src/openharness/auth/external.py` 里能看到它们分别复用本地 Claude CLI 和 Codex CLI 留下的凭据文件：

```python
# src/openharness/auth/external.py（节选片段位置）
codex_home = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
...
source_path=str(codex_home / "auth.json"),
...
claude_home = Path(os.environ.get("CLAUDE_HOME", "~/.claude")).expanduser()
...
source_path=str(claude_home / ".credentials.json"),
```

这正是英文版 README 表格里"Local `~/.codex/auth.json`"、"Local `~/.claude/.credentials.json`"这两行的来源——如果你的机器上已经登录过 Claude Code 或 Codex CLI，`oh setup` 选择对应的订阅 workflow 时会直接找到这些文件，完全跳过手动输 key 这一步。`GitHub Copilot` workflow 的 `auth_source` 是 `copilot_oauth`，走的是设备码 OAuth flow，同样不需要手动填 key。剩下的 `Anthropic-Compatible API` 和 `OpenAI-Compatible API` 两个 workflow，才是需要用户显式输入 API key 的路径。

### Profile 到底解决了什么：`credential_slot`

`ProviderProfile` 的字段定义（`src/openharness/config/settings.py`）里，`credential_slot` 是理解"不再强制共用一把全局 key"这句话的关键：

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
    last_model: str | None = None
    credential_slot: str | None = None
    allowed_models: list[str] = Field(default_factory=list)
    context_window_tokens: int | None = None
    auto_compact_threshold_tokens: int | None = None
```

凭据实际存到哪个"槽位"，由 `credential_storage_provider_name` 决定：

```python
# src/openharness/config/settings.py
def credential_storage_provider_name(profile_name: str, profile: ProviderProfile) -> str:
    """Return the storage namespace used for this profile's credential.

    Built-in API-key flows continue to use provider-level storage by default.
    Custom compatible profiles can set ``credential_slot`` to bind their own key.
    """
    del profile_name
    if auth_source_uses_api_key(profile.auth_source) and profile.credential_slot:
        return f"profile:{profile.credential_slot}"
    return auth_source_provider_name(profile.auth_source)
```

如果一个 profile 没有设置 `credential_slot`，它的凭据会落在 `auth_source_provider_name(profile.auth_source)` 这个按协议名分类的传统槽位里——比如所有 `auth_source="anthropic_api_key"` 且没有专属 `credential_slot` 的 profile，理论上会共用同一个存储位置。但只要一个自定义 profile 显式带上了 `credential_slot`（比如通过 `oh provider add` 创建的自定义 profile），它的凭据就会存到 `profile:<slot名字>` 这个独立命名空间下,和其他 profile 完全隔离。

`_default_credential_slot_for_profile` 这个辅助函数把这个决策自动化了：只要不是内置 profile、且认证方式是 API key，就默认用 profile 自己的名字当作 `credential_slot`：

```python
# src/openharness/cli.py
def _default_credential_slot_for_profile(name: str, auth_source: str) -> str | None:
    from openharness.config.settings import auth_source_uses_api_key, builtin_provider_profile_names

    if name in builtin_provider_profile_names():
        return None
    if not auth_source_uses_api_key(auth_source):
        return None
    return name
```

这意味着，通过 `_specialize_setup_target` 或者 `oh provider add` 新建的每一个自定义 Anthropic/OpenAI 兼容 profile（比如上文提到的 Kimi、GLM、MiniMax），默认就会拿到一把只属于自己的凭据槽位——这就是"profile 级凭据，不再强制共用一把全局 key"在代码层面的完整实现路径：不是新增了什么复杂的多租户系统，只是给凭据存储加了一层可选的、以 profile 名字为键的命名空间。

### 日常命令：`provider list` / `provider use` / `auth status`

三个最常用的日常命令，源码都很直白：

```python
# src/openharness/cli.py
@provider_app.command("list")
def provider_list() -> None:
    """List configured provider profiles."""
    from openharness.auth.manager import AuthManager

    statuses = AuthManager().get_profile_statuses()
    for name, info in statuses.items():
        marker = "*" if info["active"] else " "
        configured = "ready" if info["configured"] else "missing auth"
        base = info["base_url"] or "(default)"
        print(f"{marker} {name}: {info['label']} [{configured}]")
        print(f"    auth={info['auth_source']} model={info['model']} base_url={base}")


@provider_app.command("use")
def provider_use(
    name: str = typer.Argument(..., help="Provider profile name"),
) -> None:
    """Activate a provider profile."""
    from openharness.auth.manager import AuthManager

    manager = AuthManager()
    try:
        manager.use_profile(name)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    print(f"Activated provider profile: {name}", flush=True)
```

`oh provider list` 输出里那个 `*` 前缀标记的就是当前激活的 profile，`[ready]`/`[missing auth]` 直接告诉你这个 profile 是否已经具备可用凭据——不需要额外一次 `oh auth status` 才能知道。`oh provider use codex` 就是把 `active_profile` 切到 `codex` 这个内置 profile（对应 Codex Subscription workflow），下一次运行 `oh` 就会用这个 profile 解析出的 provider/auth/model。

`oh auth status` 走的是不同的粒度——它同时展示"认证来源"（auth source）和"provider profile"两张表，因为一个 auth source 可能被多个 profile 共用（比如同一把 `openai_api_key` 可以被内置的 `openai-compatible` profile 和某个自定义的 OpenAI 兼容 profile 共同引用），这两个视角不总是一一对应：

```python
# src/openharness/cli.py
@auth_app.command("status")
def auth_status_cmd() -> None:
    """Show authentication source and provider profile status."""
    ...
    print("Auth sources:")
    ...
    print("Provider profiles:")
    ...
```

### `oh provider add`：手动接一个自定义兼容接口

当内置的十来个 preset 都不满足需求（比如接一个私有部署的 Anthropic 兼容网关）时，`oh provider add` 允许直接手写一个完整的 profile 定义：

```bash
oh provider add my-endpoint \
  --label "My Endpoint" \
  --provider anthropic \
  --api-format anthropic \
  --auth-source anthropic_api_key \
  --model my-model \
  --base-url https://example.com/anthropic
```

这条命令对应的实现（`src/openharness/cli.py` 的 `provider_add`）直接构造一个 `ProviderProfile` 并调用 `manager.upsert_profile`，`credential_slot` 参数缺省时会走上面提到的 `_default_credential_slot_for_profile` 自动推导逻辑——这意味着只要不特意传 `--credential-slot None` 之类的覆盖，手动添加的自定义 profile 同样会自动获得独立凭据槽位，行为和 `oh setup` 内联创建的 profile 完全一致。

## 常见问题/易踩坑

- **以为切换 `provider` 就够了，忘了确认 `model`**：`oh provider use` 只切换 `active_profile`，模型仍然是该 profile 上次保存的 `last_model`（或 `default_model`）。想连模型一起改，用 `oh setup <profile名>` 或 `/model` 命令。
- **自定义了 Anthropic 兼容 profile,却发现凭据和另一个 profile"串"了**：检查是不是两个 profile 都没有设置独立的 `credential_slot`——只有非内置、且认证方式是 API key 的 profile,才会默认获得专属槽位；如果手动传了相同的 `--credential-slot`，两者依然会共享凭据，这是预期行为而不是 bug。
- **`Claude Subscription`/`Codex Subscription` workflow 提示认证缺失**：检查本地是否真的登录过对应的 CLI 工具（`~/.claude/.credentials.json` 或 `~/.codex/auth.json` 是否存在），这两个 workflow 不会弹出手动输入 key 的界面。

## 小结

`oh setup` 的五步引导本质上是把"选协议、认证、选后端、定模型、保存激活"这条本来分散在多个命令里的流程，收敛进一个具名对象——Profile——的构造过程。`credential_slot` 这个看似不起眼的字段，是"不再强制共用一把全局 key"的完整答案：它给每个自定义 profile 一个独立的凭据命名空间，而不需要引入额外的多租户机制。这一篇讲的都是引导层的使用体感，Provider 抽象本身（`api/provider.py`、`api/registry.py`）在运行时是怎么把一个 profile 解析成具体的 API 客户端，会在第 03 章第 2 篇详细拆开。下一篇《Dry-run 安全预览》要讲的是一个更少见的能力——在完全不触发真实调用的前提下,提前告诉你"这次运行会不会失败,以及大概会怎么失败"。
