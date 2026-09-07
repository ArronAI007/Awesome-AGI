# Dry-run 安全预览

> 大多数 Agent Harness 的"配置对不对"是在真正跑起来、模型调用失败或工具执行报错之后才知道的。OpenHarness 的 `--dry-run` 把这条反馈链路提前了一整个阶段——它会实际解析 settings、认证状态、system prompt、skills、commands、tools 和 MCP 配置，唯独不触发任何有副作用的调用，然后直接给你一个 `ready`/`warning`/`blocked` 的判断和下一步该做什么。这种"预演但不执行"的能力在同类项目里并不常见，值得单独理解它的实现方式。

## 学习目标

- 理解 `oh --dry-run` 明确的能力边界：不调用模型、不执行工具、不 spawn subagent、不连接 MCP server，但会做哪些真实的静态解析。
- 读懂 `_build_dry_run_preview` 函数的完整执行路径，知道它具体复用了运行时的哪些真实模块（而不是另起一套模拟逻辑）。
- 理解 `ready`/`warning`/`blocked` 三级 readiness 判断背后的具体规则。
- 知道 dry-run 是怎么区分"普通 prompt"和"slash command"两条预览路径的，以及各自会给出什么信息。
- 理解这类"预演式诊断"解决的实际问题：把认证/MCP 配置错误的发现时机从运行时提前到运行前。

## 背景与设计动机

新手第一次跑通一个 Agent Harness，最常卡住的地方往往不是模型能力，而是一堆配置细节：认证有没有配对、MCP server 的命令路径写没写对、这条 slash command 到底存不存在。这些问题的共同特点是——它们在模型真正被调用之前就已经能够判断出来，但传统的做法是"直接跑，跑挂了看报错"，用户需要在真实执行的噪音里（可能混着模型输出、工具执行日志、网络超时）自己剥离出"到底是配置错了还是别的问题"。

`--dry-run` 的设计动机就是把这条诊断链路显式地单独拎出来，变成一个独立的静态分析步骤。它不是"跑一个更安全的假模型"，而是完全不触碰任何会产生外部副作用的调用——不调模型、不执行工具、不连 MCP、不 spawn subagent——但依然去做设置解析、认证状态检查、system prompt 组装、skills/commands/tools 发现、以及 MCP 配置的语法级校验。这条边界在 `README.md` 里表述得很精确：

> Dry-run is intentionally static: it does not call the model, does not execute tools or spawn subagents, does not connect to MCP servers, but does resolve settings, auth status, prompt assembly, skills, commands, tools, and obvious MCP config problems.

"intentionally static"这个措辞值得留意——这不是因为某些能力还没做完，而是刻意把"预览"和"执行"划出一条硬边界，让 dry-run 输出的任何结论都可以放心地在没有副作用的前提下重复运行、甚至接入自动化流水线。

## 核心机制详解

### 三种 readiness：`ready` / `warning` / `blocked`

`_evaluate_dry_run_readiness`（`src/openharness/cli.py`）是整个 dry-run 输出的判断核心，它接收 prompt、入口点分类（entrypoint）和前面各项校验的结果，逐条累加出一个最终结论：

```python
# src/openharness/cli.py
def _evaluate_dry_run_readiness(
    *,
    prompt: str | None,
    entrypoint: dict[str, object],
    validation: dict[str, object],
) -> dict[str, object]:
    level = "ready"
    reasons: list[str] = []
    next_actions: list[str] = []

    if entrypoint.get("kind") == "unknown_slash_command":
        level = "blocked"
        reasons.append("The prompt starts with '/' but does not match any registered slash command.")
        next_actions.append("Check the command name and run `oh --dry-run -p \"/help\"` to inspect available slash commands.")

    api_client = validation.get("api_client")
    if isinstance(api_client, dict) and api_client.get("status") == "error":
        if entrypoint.get("kind") == "model_prompt":
            level = "blocked"
            detail = str(api_client.get("detail") or "").strip()
            reasons.append(detail or "Runtime client resolution failed for a prompt that would require a model call.")
            next_actions.append("Fix authentication or provider profile configuration before running this prompt.")
        elif level != "blocked":
            level = "warning"
            reasons.append("Runtime client resolution failed. Interactive commands may still work, but model execution would fail.")
            next_actions.append("If you expect a model call later, fix authentication or provider profile configuration first.")

    mcp_errors = int(validation.get("mcp_errors") or 0)
    if mcp_errors > 0 and level != "blocked":
        level = "warning"
        reasons.append(f"{mcp_errors} configured MCP server(s) have obvious configuration errors.")
        next_actions.append("Fix or disable the broken MCP server configuration before relying on MCP-backed tools.")

    auth_status = str(validation.get("auth_status") or "")
    if auth_status.startswith("missing") and entrypoint.get("kind") in {"interactive_session", "model_prompt"} and level != "blocked":
        level = "warning"
        reasons.append("Authentication is missing, so live model execution would not start successfully.")
        next_actions.append("Run `oh auth login` or configure the active profile credentials before executing.")
    ...
```

这段逻辑的判断顺序本身就是一种优先级设计：

- **`blocked`**：只有两种情况会触发——输入是一个不存在的 slash command，或者输入需要一次模型调用（`entrypoint.kind == "model_prompt"`）但运行时客户端根本解析不出来（比如认证或 provider 配置本身有语法错误，连"能不能连上"都判断不了）。这两种情况的共性是：即便真的跑起来，也必然会失败,没有任何侥幸空间。
- **`warning`**：MCP 配置有明显错误、或者认证缺失但当前入口点还不一定马上需要模型调用（比如交互式会话刚打开、或者一个只读的 slash command）。这类问题不保证一定会失败——用户可能压根不会走到需要认证的那一步——但值得在运行前被提醒。
- **`ready`**：所有静态检查都过了。如果没有提供 prompt，会提示"这只验证了会话初始化路径本身"；如果提供了 prompt，会直接给出下一步建议命令。

三个级别一旦被设为 `blocked` 就不会再被后续检查降级为 `warning`（`level != "blocked"` 这个条件反复出现），这是一个单调递增的严重程度模型——一旦发现致命问题，后面的检查只会补充原因、不会推翻结论。

### `_build_dry_run_preview`：复用真实运行时模块做静态解析

dry-run 不是另起一套"假运行时"，`_build_dry_run_preview` 直接 import 并调用了和真实运行路径完全相同的模块：

```python
# src/openharness/cli.py
def _build_dry_run_preview(...) -> dict[str, object]:
    from openharness.api.provider import auth_status, detect_provider
    from openharness.commands import create_default_command_registry
    from openharness.config import get_config_file_path, load_settings
    from openharness.mcp.config import load_mcp_server_configs
    from openharness.plugins import load_plugins
    from openharness.prompts.context import build_runtime_system_prompt
    from openharness.skills import load_skill_registry
    from openharness.tools import create_default_tool_registry
    from openharness.ui.runtime import _resolve_api_client_from_settings

    resolved_cwd = str(Path(cwd).expanduser().resolve())
    settings = load_settings().merge_cli_overrides(...)
    provider = detect_provider(settings)
    auth = auth_status(settings)
    profile_name, profile = settings.resolve_profile()

    plugins = load_plugins(settings, resolved_cwd)
    plugin_commands = [command for plugin in plugins if plugin.enabled for command in plugin.commands]
    command_registry = create_default_command_registry(plugin_commands=plugin_commands)
    command_match = command_registry.lookup(prompt) if prompt else None
    skill_registry = load_skill_registry(resolved_cwd, settings=settings)
    skills = skill_registry.list_skills()
    mcp_servers = load_mcp_server_configs(settings, plugins)
    tool_registry = create_default_tool_registry()
    ...
```

这一点是 dry-run 可信度的关键：`load_settings`、`load_plugins`、`create_default_command_registry`、`load_skill_registry`、`load_mcp_server_configs`、`create_default_tool_registry`——全部都是真实运行路径上会用到的同一批函数。这意味着 dry-run 给出的"这次会加载多少个 skill、多少个 plugin、命中哪个 slash command"这些数字，和真的跑一次 `oh` 时实际发生的发现过程是一致的，不存在"预览说没问题、真跑起来才发现少加载了什么"的偏差。

真正被小心避开的只有一处——判断 API 客户端能否被解析出来，但不真的用它发一次请求：

```python
# src/openharness/cli.py
client_validation = {"status": "ok", "detail": ""}
try:
    with redirect_stderr(StringIO()):
        _resolve_api_client_from_settings(settings)
except SystemExit:
    client_validation = {"status": "error", "detail": "runtime client could not be resolved with current auth/config"}
except Exception as exc:  # pragma: no cover - defensive diagnostic path
    client_validation = {"status": "error", "detail": str(exc)}
```

`_resolve_api_client_from_settings` 本身就是真实运行时用来构造 API 客户端对象的函数,dry-run 只是调用它、捕获它可能抛出的 `SystemExit`（比如缺少 key 时的强制退出）或其他异常，但不会真的拿这个客户端去发一次网络请求。这是"复用真实逻辑、但在最后一步截断副作用"的典型写法——最大化了预览结果和真实行为的一致性，同时保住了"不发起任何外部调用"的边界承诺。

### MCP 配置的语法级校验

MCP server 配置错误是最容易在运行时才暴露的一类问题——命令路径写错、URL 格式不对、`cwd` 目录不存在。`_validate_mcp_server` 在完全不启动 MCP server 进程的前提下,针对不同传输方式做静态检查：

```python
# src/openharness/cli.py
def _validate_mcp_server(name: str, config: object) -> dict[str, object]:
    preview = _mcp_transport_preview(config)
    issues: list[str] = []
    status = "ok"
    transport = preview["transport"]

    if transport == "stdio":
        command = getattr(config, "command", None) if not isinstance(config, dict) else config.get("command")
        raw_cwd = getattr(config, "cwd", None) if not isinstance(config, dict) else config.get("cwd")
        command_text = str(command or "").strip()
        if not command_text:
            issues.append("missing command")
        elif shutil.which(command_text) is None:
            issues.append(f"command not found in PATH: {command_text}")
        if raw_cwd:
            resolved_cwd = Path(str(raw_cwd)).expanduser()
            if not resolved_cwd.exists():
                issues.append(f"cwd does not exist: {resolved_cwd}")
    elif transport in {"http", "ws"}:
        raw_url = getattr(config, "url", None) if not isinstance(config, dict) else config.get("url")
        parsed = urlparse(str(raw_url or "").strip())
        expected = {"http", "https"} if transport == "http" else {"ws", "wss"}
        if parsed.scheme not in expected or not parsed.netloc:
            issues.append(f"invalid {transport} url: {raw_url}")

    if issues:
        status = "error"
    return {"name": name, **preview, "status": status, "issues": issues}
```

对 `stdio` 传输的 server，检查点是"命令是否为空"和"用 `shutil.which` 能不能在 `PATH` 里找到这个可执行文件"，以及 `cwd` 目录是否真实存在——这些都是不需要启动进程就能确定的静态事实。对 `http`/`ws` 传输的 server，检查点是 URL 的 scheme 是否匹配预期协议、netloc 是否存在。这些检查抓不住"这个 MCP server 启动后到底能不能正常握手"这类运行时行为，但能抓住"配置本身就写错了"这类最常见、最容易一眼看出的错误——这正是 dry-run 的边界所在：静态可判定的问题它会告诉你，需要真正连接才能判断的问题它不会假装知道。

### 区分普通 prompt 和 slash command：两条不同的预览路径

dry-run 对输入内容的分类逻辑决定了预览会给出什么样的信息。以 `/` 开头的输入会先尝试匹配已注册的 slash command：

```python
# src/openharness/cli.py
if preview_prompt:
    if preview_prompt.startswith("/") and command_match is not None:
        matched_command = command_match[0]
        behavior = _dry_run_command_behavior(matched_command.name)
        entrypoint = {
            "kind": "slash_command",
            "command": matched_command.name,
            ...
            "behavior": behavior["kind"],
            "detail": (
                f"Input resolves to /{matched_command.name}. "
                f"{behavior['detail']} Dry-run does not execute the command handler."
            ),
        }
    elif preview_prompt.startswith("/") and command_match is None:
        entrypoint = {
            "kind": "unknown_slash_command",
            "detail": "Input starts with / but does not match a registered slash command.",
        }
    else:
        entrypoint = {
            "kind": "model_prompt",
            "detail": (
                "The first live step would be a model request. "
                "Exact tool calls and parameters are decided by the model at runtime."
            ),
        }
```

匹配到已知 slash command 时，dry-run 还会调用 `_dry_run_command_behavior` 判断这条命令"偏只读还是会改本地状态"——它维护了两个硬编码的命令名集合：

```python
# src/openharness/cli.py
def _dry_run_command_behavior(name: str) -> dict[str, str]:
    read_only = {
        "help", "version", "status", "context", "cost", "usage", "stats",
        "hooks", "onboarding", "skills", "mcp", "doctor", "diff", "branch",
        "privacy-settings", "rate-limit-options", "release-notes", "upgrade",
        "keybindings", "files",
    }
    mutating = {
        "clear", "compact", "resume", "session", "export", "share", "copy",
        "tag", "rewind", "init", "bridge", "login", "logout", "feedback",
        "config", "plugin", "reload-plugins", "permissions", "plan", "fast",
        "effort", "passes", "turns", "continue", "provider", "model", "theme",
        "output-style", "vim", "voice", "commit", "issue", "pr_comments",
        "agents", "subagents", "tasks", "autopilot", "ship", "memory",
    }
    if name in read_only:
        return {"kind": "read_only", "detail": "..."}
    if name in mutating:
        return {"kind": "stateful", "detail": "..."}
    return {"kind": "unknown", "detail": "..."}
```

这是一份手工维护的分类表，而不是从命令元数据里自动推导出来的——这意味着新增一个会修改本地状态的命令时，需要有人记得把它加进 `mutating` 集合，否则 dry-run 会把它归入默认的 `unknown` 分类。这是一个值得留意的设计取舍：用一份简单、可读的静态表换来实现的简单性,代价是它不会随着命令注册表自动同步，需要维护者手动跟进。

如果输入既不是 `/` 开头、也没有 prompt（也就是 `oh --dry-run` 不带 `-p`），会归入第四种入口点分类 `interactive_session`——表示这只是在验证"如果打开交互式会话，配置本身是否站得住脚"，不涉及任何具体输入的解析。

### 输出里的 `next actions`：直接给下一步命令

`_evaluate_dry_run_readiness` 汇总出的 `next_actions` 不是抽象的建议，而是可以直接复制执行的具体命令。结合 README 里的例子，常见的几条是：

- `oh auth login` —— 认证缺失时的建议
- 修复或禁用坏掉的 MCP 配置 —— MCP server 校验出错时的建议
- `oh -p "..."` 或直接进入 `oh` —— 一切正常时告诉你可以放心运行

`_format_dry_run_preview` 把这些信息渲染成人类可读的文本报告；如果加上 `--output-format json`，`_build_dry_run_preview` 返回的完整字典会被原样序列化输出——这对接入 CI 检查或 IM channel（后续第 08 章会讲到的 `ohmo` 场景）尤其有用：可以把 dry-run 的 `readiness.level` 字段当作一个程序可判断的门禁条件，而不需要解析人类可读的文本。

## 常见问题/易踩坑

- **以为 `--dry-run` 支持 `--continue`/`--resume`**：目前不支持，`cli.py` 里会直接报错退出——`Error: --dry-run does not support --continue/--resume yet.`
- **`ready` 不代表"这个 MCP server 一定能连上"**：dry-run 对 MCP 配置的校验只是语法级的（命令是否存在、URL 格式是否正确），不代表真正连接后一定能握手成功。`README.md` 对此的措辞是"obvious MCP config problems"——只抓明显错误。
- **`blocked` 判断依赖的是入口点分类**：同样是认证缺失，一个 `model_prompt` 会被判为 `blocked`，一个 `interactive_session` 只会被判为 `warning`——因为后者不一定马上就要触发模型调用。理解这一点能避免误以为 dry-run 的判断标准不一致。

## 小结

`--dry-run` 的核心设计不是造一个模拟环境，而是复用运行时的真实解析路径（settings、plugins、skills、commands、tools、MCP 配置），在"是否真的发起有副作用的调用"这一步做精确截断，再用一套单调递增的 `ready`/`warning`/`blocked` 规则把结果收敛成一个可执行的判断。这把认证、MCP 配置这类最常见的新手绊脚石，从"运行时报错"提前到了"运行前诊断"。下一篇《Ohmo 初探：个人 Agent 的另一副面孔》会切换视角,看看基于 OpenHarness 构建的个人 Agent App `ohmo` 是怎么复用这套核心能力、又在哪些地方走出了自己的路。
