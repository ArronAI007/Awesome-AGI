# Ohmo 初探：个人 Agent 的另一副面孔

> `README.md` 里有一句容易被跳过的话："`ohmo` 是基于 OpenHarness 的 personal-agent app，不是 core 的一个 mode。"这句话不是一句市场文案，它在包结构上是可以被验证的事实：`ohmo/` 是和 `src/openharness/` 并列的顶层包，有自己独立的 `cli.py`、`runtime.py`、`workspace.py`，通过 `import openharness` 来复用核心运行时,而不是作为 openharness 内部某个 `mode=personal` 的分支存在。

## 学习目标

- 从 `pyproject.toml` 的打包配置和 `ohmo/runtime.py` 的 import 语句里，验证"`ohmo` 是独立应用而非 core 内部模式"这个结构性事实。
- 理解 `ohmo init` 创建的六个工作区文件/目录（`soul.md`、`identity.md`、`user.md`、`BOOTSTRAP.md`、`memory/`、`gateway.json`）各自的职责,以及为什么要拆成这么多份而不是一个大文件。
- 走一遍 `ohmo config`、`ohmo`、`ohmo gateway run/status/restart` 几个命令的真实行为。
- 明确这一篇只是初探，`ohmo` 的 Gateway 架构、多 Channel 路由、Cron 调度是第 08 章的主线内容。

## 背景与设计动机

一个"个人 Agent"和一个"编码助手 CLI"对状态的诉求是不一样的。`oh` 这个核心 Harness 关心的是单次会话内的上下文——当前项目的代码、这次对话的历史、这次任务用到的工具。但一个通过 Telegram/Slack/飞书 长期陪伴用户的个人 Agent，需要跨会话持久化的东西要多得多：它是谁、它应该表现出什么样的性格、它了解用户到什么程度、它第一次上线时该怎么和用户破冰、它积累下来的长期记忆存在哪里、它连接哪些 IM 渠道。

如果把这些状态硬塞进 `oh` 本身的配置体系，`openharness` 这个核心包就会被一个特定应用场景的假设（"你在跟一个长期陪伴你的助手对话"）污染，而 `oh` 原本更纯粹的定位是"给一次性任务/编码会话用的 Harness"。OpenHarness 选择的解法是不在 core 里加这层假设，而是把它做成一个独立的、构建在 core 之上的应用——`ohmo`。这个选择在包结构层面留下了清晰的痕迹。

## 核心机制详解

### 独立顶层包，而非 core 内部分支

`pyproject.toml` 的打包目标直接说明了这一点：

```toml
# pyproject.toml
[tool.hatch.build.targets.wheel]
packages = ["src/openharness", "ohmo"]

[project.scripts]
openharness = "openharness.cli:app"
oh = "openharness.cli:app"
openh = "openharness.cli:app"
ohmo = "ohmo.cli:app"
```

`src/openharness` 和 `ohmo` 是两个并列打包进同一个 wheel 的顶层包,`ohmo` 命令指向的是 `ohmo.cli:app`——一个完全独立的 Typer 应用对象，和 `openharness.cli:app` 没有继承或组合关系。如果 `ohmo` 真的只是 core 内部的一个 mode,期望看到的结构会是类似 `openharness.cli.app` 里多一个 `--personal-agent` 标志，或者 `openharness/modes/personal.py` 这样嵌在 core 包内部的模块——但实际的目录结构不是这样。

真正能验证"复用而非内部分支"的是 `ohmo/runtime.py` 里的 import 语句：

```python
# ohmo/runtime.py
from openharness.api.client import SupportsStreamingMessages
from openharness.engine.stream_events import AssistantTextDelta, AssistantTurnComplete, CompactProgressEvent, ErrorEvent, StatusEvent
from openharness.ui.backend_host import run_backend_host
from openharness.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime
from openharness.ui.react_launcher import _resolve_npm, _resolve_tsx, get_frontend_dir

from ohmo.memory import create_memory_command_backend
from ohmo.prompts import build_ohmo_system_prompt
from ohmo.session_storage import OhmoSessionBackend
from ohmo.workspace import get_memory_dir, get_plugins_dir, get_sessions_dir, get_skills_dir, initialize_workspace
```

`ohmo` 像任何第三方使用者一样，`import openharness.*`——它调用的是 `openharness.ui.backend_host.run_backend_host`、`openharness.ui.runtime.build_runtime` 这些公开的运行时构造函数，而不是靠某种特殊的内部钩子。`run_ohmo_backend` 函数的实现就是这种"组合而非侵入"关系的最好例证：

```python
# ohmo/runtime.py
async def run_ohmo_backend(
    *,
    cwd: str | None = None,
    workspace: str | Path | None = None,
    model: str | None = None,
    max_turns: int | None = None,
    provider_profile: str | None = None,
    ...
) -> int:
    """Run the shared React backend host with ohmo workspace semantics."""
    cwd_path = str(Path(cwd or Path.cwd()).resolve())
    workspace_root = initialize_workspace(workspace)
    extra_skill_dirs, extra_plugin_roots = _ohmo_extra_roots(workspace_root)
    return await run_backend_host(
        cwd=cwd_path,
        model=model,
        max_turns=max_turns,
        system_prompt=build_ohmo_system_prompt(cwd_path, workspace=workspace_root),
        active_profile=provider_profile,
        ...
        session_backend=OhmoSessionBackend(workspace_root),
        extra_skill_dirs=extra_skill_dirs,
        extra_plugin_roots=extra_plugin_roots,
        memory_backend=create_memory_command_backend(workspace_root),
        include_project_memory=False,
        autodream_context={
            "memory_dir": str(get_memory_dir(workspace_root)),
            "session_dir": str(get_sessions_dir(workspace_root)),
            "app_label": "ohmo personal memory",
            "runner_module": "ohmo",
        },
    )
```

`run_backend_host` 是 core 里给交互式后端进程用的通用入口函数，`ohmo` 唯一做的事情是往它的参数里注入自己的一套"扩展点"——自定义的 `system_prompt`（`build_ohmo_system_prompt`）、自定义的 `session_backend`（`OhmoSessionBackend`，把会话存到 `ohmo` 工作区而不是 `openharness` 默认位置）、自定义的技能/插件搜索路径（`extra_skill_dirs`/`extra_plugin_roots`，指向 `~/.ohmo/skills`、`~/.ohmo/plugins`）、以及一个专属的 `memory_backend`。这是一种典型的"核心提供可扩展接口，应用层通过参数注入定制行为"的组合模式，而不是在核心代码里写 `if app == "ohmo"` 这种分支判断。

### `ohmo init` 创建的六份工作区文件

`ohmo/workspace.py` 里的 `initialize_workspace` 函数是 `ohmo init` 背后的真正实现，它会在 `~/.ohmo/`（或 `OHMO_WORKSPACE` 环境变量指定的位置）创建一整套文件：

```python
# ohmo/workspace.py
def initialize_workspace(workspace: str | Path | None = None) -> Path:
    """Create the workspace and seed template files when missing."""
    root = ensure_workspace(workspace)
    templates = {
        get_soul_path(root): SOUL_TEMPLATE,
        get_user_path(root): USER_TEMPLATE,
        get_memory_index_path(root): MEMORY_INDEX_TEMPLATE,
        get_identity_path(root): IDENTITY_TEMPLATE,
    }
    for path, content in templates.items():
        if not path.exists():
            path.write_text(content.strip() + "\n", encoding="utf-8")
    ...
    bootstrap_path = get_bootstrap_path(root)
    if not state_data.get("bootstrap_seeded"):
        state_data["bootstrap_seeded"] = True
        if not bootstrap_path.exists():
            bootstrap_path.write_text(BOOTSTRAP_TEMPLATE.strip() + "\n", encoding="utf-8")
        state_path.write_text(json.dumps(state_data, indent=2) + "\n", encoding="utf-8")
    gateway_path = get_gateway_config_path(root)
    if not gateway_path.exists():
        gateway_path.write_text(json.dumps({"provider_profile": "codex", "enabled_channels": [], ...}, indent=2) + "\n", encoding="utf-8")
    return root
```

六份文件/目录各自的职责,从模板内容本身就能读出设计意图，而不只是文件名的字面意思：

**`soul.md`——长期人格与行为原则**。这是变化频率最低的一份文件，内容更接近"宪法"而不是配置——`SOUL_TEMPLATE` 里写的是"Be genuinely helpful, not performatively helpful"、"Have judgment"这类原则性陈述，模板结尾甚至专门叮嘱："If you materially change this file, tell the user. It is your soul." 把它和其他文件分开，是因为人格设定理应比用户画像、比记忆条目稳定得多——它不应该随便被一次对话悄悄改写。

**`identity.md`——`ohmo` 自己是谁**。`IDENTITY_TEMPLATE` 的内容非常短：名字、类型（"personal agent"）、气质（vibe）、签名。这份文件和 `soul.md` 的区别是粒度——`soul.md` 讲的是行为原则这种抽象层面的东西,`identity.md` 讲的是几个具体的、可以被 BOOTSTRAP 流程直接填空更新的字段。模板注释也印证了这一点："Keep this short and concrete. Update it when the user and the agent have a clearer shared sense of who ohmo is."——这是一份预期会随着首次上线对话被填充、后续变化频率介于 `soul.md` 和 `user.md` 之间的文件。

**`user.md`——用户画像、偏好、关系信息**。`USER_TEMPLATE` 的结构分成 Profile（姓名、称呼、时区、语言）、Defaults（偏好语气、回答长度、决策风格）、Ongoing context（在忙什么项目）、Preferences（喜欢什么、讨厌什么）、Relationship notes（这个 Agent 应该以什么样的关系姿态出现——是"话不多的执行者"还是"体贴的搭档"）。这份文件预期是变化最频繁的一份——用户的项目、偏好、当前处境会持续演进，理应和相对静态的人格设定分开维护。

**`BOOTSTRAP.md`——首轮 landing/onboarding 流程**。这是六份文件里唯一"用完可以扔"的一份。`initialize_workspace` 里有一段专门的一次性播种逻辑：只有当 `state.json` 里的 `bootstrap_seeded` 标志还没被设置过时，才会创建这份文件。`BOOTSTRAP_TEMPLATE` 的结尾明确写道："Once the initial landing is complete, this file can be deleted. If it is gone later, do not assume it should come back."——它的职责就是引导第一次对话（搞清楚用户想让 `ohmo` 怎么称呼自己、什么语气、时区、最近在忙什么），完成使命后就该被清理掉，不需要长期存在。这和 `soul.md`/`user.md` 那种"持续存在、持续更新"的文件形成鲜明对比。

**`memory/`——长期记忆目录**。`MEMORY_INDEX_TEMPLATE` 只有几行提示："Add durable personal facts and preferences as focused markdown files in this directory."——这是一个目录而不是单个文件，因为记忆条目预期会随时间不断增长、且每条记忆的主题、更新时机都彼此独立,适合拆成多个独立的 Markdown 文件而不是塞进一个不断膨胀的单文件。

**`gateway.json`——Gateway 的 profile 和 channel 配置**。这是六份文件里唯一的结构化 JSON（其余都是给模型读的 Markdown），因为它的消费方不是模型本身,而是 `ohmo` 的网关服务代码——它需要以程序可解析的格式知道用哪个 provider profile、启用了哪些 channel（Telegram/Slack/Discord/飞书）、每个 channel 的具体配置（token、allow_from 白名单、group_policy 等）。默认生成的内容里 `provider_profile` 是 `"codex"`：

```python
# ohmo/workspace.py
gateway_path.write_text(
    json.dumps(
        {
            "provider_profile": "codex",
            "enabled_channels": [],
            "session_routing": "chat-thread",
            "send_progress": True,
            "send_tool_hints": True,
            "permission_mode": "default",
            "sandbox_enabled": False,
            "allow_remote_admin_commands": False,
            "allowed_remote_admin_commands": [],
            "log_level": "INFO",
            "channel_configs": {},
        },
        indent=2,
    ) + "\n",
    encoding="utf-8",
)
```

把这六份文件放在一起看，能看出一条清晰的"变化频率"光谱：`soul.md`（近乎不变）→ `identity.md`（低频，随身份共识调整）→ `user.md`（中频，随用户情况演进）→ `memory/`（持续追加）→ `gateway.json`（配置变更时改）→ `BOOTSTRAP.md`（一次性,用后即焚）。把这些职责拆成独立文件而不是一个大配置对象，让每一份文件都可以被单独读、单独改、单独纳入版本历史,而不会因为改一处配置就牵动一份本该稳定的人格设定。

### `ohmo config`、`ohmo`、`ohmo gateway *` 命令

`ohmo config`（`ohmo/cli.py` 的 `config_cmd`）和 `ohmo init` 共用同一套向导函数 `_run_gateway_config_wizard`，区别在于 `init` 只在工作区不存在或用户主动确认时才触发，`config` 则是随时可以重新运行的配置入口：

```python
# ohmo/cli.py
@app.command("config")
def config_cmd(
    cwd: str = typer.Option(str(Path.cwd()), "--cwd", help="Project working directory"),
    workspace: str | None = typer.Option(None, "--workspace", help=_WORKSPACE_HELP),
) -> None:
    """Configure provider profile and gateway channels."""
    cwd_path = str(Path(cwd).resolve())
    workspace_root = initialize_workspace(workspace)
    config = _run_gateway_config_wizard(workspace_root)
    _print_gateway_config_summary(config)
    print(f"Saved gateway config to {get_gateway_config_path(workspace_root)}")
    _maybe_restart_gateway(cwd=cwd_path, workspace=workspace_root)
```

向导本身分两段：先用 `_prompt_provider_profile` 选一个 provider profile（复用的正是上一篇讲过的 `AuthManager().get_profile_statuses()`，选项列表和 `oh setup` 看到的完全是同一批 workflow），再用 `_prompt_channels` 逐个渠道询问是否启用、以及各渠道专属的字段（Telegram 的 bot token、Slack 的 bot/app token 和 group_policy、Discord 的 gateway URL 和 intents、飞书的 app_id/app_secret/加密key/验证token）。配置保存完成后,`_maybe_restart_gateway` 会检测 gateway 当前是否在运行，如果在运行会询问是否立即重启以应用新配置——这是一个照顾"改配置时服务已经在跑"这种真实场景的细节。

没有子命令的裸 `ohmo`，走的是 `main` 回调函数末尾的默认分支——初始化工作区、按 `--print`/`--backend-only` 与否分流到 `run_ohmo_print_mode` 或 `launch_ohmo_react_tui`，本质上和 `oh` 的分流结构是同一套模式，只是把 `system_prompt`、`session_backend` 换成了 `ohmo` 专属的版本。

`ohmo gateway run/status/restart` 三个命令管理的是一个独立于交互式会话的后台服务进程：

```python
# ohmo/cli.py
@gateway_app.command("run")
def gateway_run_cmd(...) -> None:
    """Run the ohmo gateway in the foreground."""
    _configure_gateway_logging(workspace, console=console_log, log_file=log_file)
    service = OhmoGatewayService(cwd, workspace)
    raise SystemExit(asyncio.run(service.run_foreground()))


@gateway_app.command("restart")
def gateway_restart_cmd(...) -> None:
    stop_gateway_process(cwd, workspace)
    pid = start_gateway_process(cwd, workspace)
    print(f"ohmo gateway restarted (pid={pid})")


@gateway_app.command("status")
def gateway_status_cmd(...) -> None:
    state = gateway_status(cwd, workspace)
    print(state.model_dump_json(indent=2))
```

`gateway run` 是前台运行（阻塞当前终端，日志直接打到 console），这是调试阶段常用的方式；日常场景更常用的是配置向导内联触发的重启,或者通过外部进程管理工具接管 `OhmoGatewayService` 的生命周期。`gateway status` 直接把状态对象序列化成 JSON 打印,方便脚本化检查。这个 Gateway 服务具体是怎么把多个 IM channel 的消息路由到同一个 Agent 会话、怎么做 Cron 调度——这些都是第 08 章要深入的内容，这里只需要知道这三个命令分别对应"跑起来"、"重启"、"看状态"三个最基本的运维动作。

## 常见问题/易踩坑

- **以为改 `ohmo/` 下的代码会影响 `oh`**：不会。两者是并列的独立包，`ohmo` 单向依赖 `openharness`，反过来不成立——`src/openharness/` 里不会出现任何 `import ohmo` 的代码。
- **`BOOTSTRAP.md` 消失后再手动加回去**：不建议。模板本身明确说"如果它消失了，不要假设它应该回来"——这个文件的生命周期设计就是一次性的，重新创建它不会重新触发 onboarding 逻辑本身（真正的判断依据是 `state.json` 里的 `bootstrap_seeded` 标志）。
- **`ohmo init` 第二次运行以为会重置工作区**：不会。`initialize_workspace` 对每份模板文件都做了 `if not path.exists()` 判断，已存在的文件不会被覆盖；`ohmo init` 在工作区已存在时会提示"already exists"并询问是否要打开配置向导，而不是重新播种。

## 小结

`ohmo` 和 `oh` 的关系,在包结构、打包配置、import 方向上都是清晰的"应用依赖核心"，而不是"核心内置的一个分支"——这一点在 `pyproject.toml` 的 `packages` 列表和 `ohmo/runtime.py` 的 import 语句里都能直接验证。`ohmo init` 创建的六份工作区文件，按变化频率从近乎不变的 `soul.md` 到一次性的 `BOOTSTRAP.md` 排开，是一套刻意为长期陪伴场景设计的状态分层方案。这一篇只是对 `ohmo` 的初探——它的 Gateway 服务具体怎么统一管理多个 IM Channel、怎么做消息路由和 Cron 调度，是第 08 章《Ohmo 与多平台网关》的主线内容。下一章《仓库全景与工程实践》会从这里跳出去，开始系统地拆开 OpenHarness 的整体包结构和工程实践。
