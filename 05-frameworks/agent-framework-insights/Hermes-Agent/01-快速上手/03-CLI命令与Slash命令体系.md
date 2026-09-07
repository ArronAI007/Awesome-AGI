# CLI 命令与 Slash 命令体系

> Hermes 有两层命令:进程启动前的**顶层子命令**(`hermes model`、`hermes gateway ...`,用 argparse 解析)和会话内的**斜杠命令**(`/new`、`/model`、`/compress`,在对话循环里被拦截分发)。本篇拆开这两层各自的注册与分发机制,并说明它们为什么能被 CLI、TUI、Gateway 三种界面共享。

## 学习目标

- 理解顶层子命令是怎么用 argparse 的 `subparsers` 机制组织的,以及为什么这套注册逻辑正在被拆分成独立模块
- 认识"快速路径"(fast-path)这种性能优化手段——为什么裸 `hermes` 启动不需要构建全部子命令解析器
- 掌握 slash 命令的中心化注册表 `CommandDef`/`COMMAND_REGISTRY`,理解 `busy_policy` 等字段解决的实际问题
- 看懂从"用户输入 `/xxx`"到"对应处理逻辑被调用"的真实分发代码
- 知道 CLI、TUI、Gateway 是如何共享同一套 slash 命令逻辑的

## 顶层子命令:分层的 argparse

`hermes` 命令的参数解析入口是 `hermes_cli/_parser.py` 里的 `build_top_level_parser()`。这个文件的模块 docstring 直接说明了它的职责边界:

```python
# hermes_cli/_parser.py
"""
Top-level argparse construction for the hermes CLI.

Lives in its own module so other modules (e.g. ``relaunch.py``) can
introspect the parser to discover which flags exist without running the
``main`` fn.

Only the top-level parser and the ``chat`` subparser live here. Every other
subparser (model, gateway, sessions, …) is built inline in ``main.py``
because its dispatch is tightly coupled to module-level ``cmd_*`` functions.
"""
```

也就是说,只有最基础的顶层 flag(`-m/--model`、`--provider`、`--resume`、`--tui` 等)和 `chat` 子命令的解析在这里定义;真正数量庞大的其他子命令(`model`、`gateway`、`config`、`setup`、`doctor`、`sessions` 等,`main.py` 里维护的 `_BUILTIN_SUBCOMMANDS` 常量列出了近 60 个)分散注册在 `hermes_cli/main.py` 的 `main()` 函数体内,以及一批正在被抽取出去的独立模块——`hermes_cli/subcommands/` 目录下,每个文件对应一个子命令:

```python
# hermes_cli/subcommands/model.py
"""``hermes model`` subcommand parser.

Extracted verbatim from ``hermes_cli/main.py:main()`` (god-file Phase 2).
Handler injected to avoid importing ``main``.
"""

def build_model_parser(subparsers, *, cmd_model: Callable) -> None:
    """Attach the ``model`` subcommand to ``subparsers``."""
    model_parser = subparsers.add_parser(
        "model",
        help="Select default model and provider",
        description="Interactively select your inference provider and default model",
    )
    model_parser.add_argument("--refresh", action="store_true", ...)
    ...
    model_parser.set_defaults(func=cmd_model)
```

`main.py` 里对应只是一行调用:

```python
# hermes_cli/main.py
build_model_parser(subparsers, cmd_model=cmd_model)
```

模块注释里"god-file Phase 2"这个说法很直白——`main.py` 本身已经膨胀到近 1.5 万行("god file",上帝文件,指承担了过多职责的巨型模块),Hermes 团队正在把每个子命令的**解析器构建**逐步搬到 `hermes_cli/subcommands/<name>.py` 里独立成文件,但**处理函数**(`cmd_model`、`cmd_config` 等)暂时还留在 `main.py`,通过参数注入(`cmd_model=cmd_model`)传给构建函数,避免子命令模块反过来 import 整个 `main.py`。这是一种循序渐进的"巨型文件拆分"策略,而不是一次性大重构——第 02 章会更系统地讨论这种工程取舍。

### 性能优化:跳过用不到的解析器

一个值得注意的细节是,Hermes 并不会在每次启动时都无条件构建全部几十个子命令的 argparse 树。`main.py` 里的 `_try_fast_chat_launch()` 解释了原因:

```python
# hermes_cli/main.py
def _try_fast_chat_launch() -> bool:
    """Fast path for unambiguous interactive chat launches (all hosts).

    ``hermes`` / ``hermes -w -s foo --yolo`` / ``hermes chat`` don't need the
    full argparse tree: building all ~40 subcommand parsers costs ~140ms of
    pure-Python argparse setup plus their module imports, none of which the
    chat path uses. Parse the lightweight top-level/chat parser instead and
    dispatch straight to ``cmd_chat``.

    Bails out (returns False) whenever the invocation is not certainly a
    chat launch — a subcommand positional, ``--help``, unknown flags — so
    every other path still goes through the full parser unchanged.
    """
```

当命令行明显就是"裸 `hermes` 进对话"这种最常见的用法时,直接用 `_parser.py` 里那个轻量的顶层+`chat` 解析器解析、分发给 `cmd_chat`,完全跳过构建其余 ~40 个子命令解析器(以及它们各自触发的模块导入)。这是一个很实际的教训:**当你的 CLI 子命令数量膨胀到几十个,"构建全部解析器"本身就会变成一笔不小的启动开销**,值得为最常见路径单独开一条捷径。类似地,`_plugin_cli_discovery_needed()` 也会先看第一个位置参数是否在内置子命令集合里,不在才触发相对昂贵的插件发现流程。

## Slash 命令:中心化注册表 `CommandDef`

会话内的 slash 命令则是完全不同的一套机制,定义在 `hermes_cli/commands.py`(约 2400 行)。核心是一个 `dataclass`:

```python
# hermes_cli/commands.py
class CommandDef:
    """Definition of a single slash command."""

    name: str                          # canonical name without slash: "background"
    description: str                   # human-readable description
    category: str                      # "Session", "Configuration", etc.
    aliases: tuple[str, ...] = ()      # alternative names: ("bg",)
    args_hint: str = ""                # argument placeholder: "<prompt>", "[name]"
    subcommands: tuple[str, ...] = ()  # tab-completable subcommands
    cli_only: bool = False             # only available in CLI
    gateway_only: bool = False         # only available in gateway/messaging
    gateway_config_gate: str | None = None
    busy_policy: str = "reject"
    busy_handler: str | None = None
    execute: str | None = None
    argument_mode: str | None = None
    desktop: str | None = None
```

所有命令实例都集中在一个列表里,构成"单一事实来源":

```python
# hermes_cli/commands.py
COMMAND_REGISTRY: list[CommandDef] = [
    CommandDef("new", "Start a new session (fresh session ID + history)", "Session",
               aliases=("reset",), args_hint="[name]",
               busy_policy="interrupt_then_dispatch", busy_handler="new"),
    ...
    CommandDef("model", "Switch model (session-scoped; --global to persist)", "Configuration",
               args_hint="[model] [--provider name] [--global|--session] [--refresh]",
               busy_policy="reject", busy_handler="model", desktop="hidden"),
    CommandDef("personality", "Set a predefined personality", "Configuration",
               args_hint="[name]", argument_mode="options"),
    CommandDef("compress", "Compress conversation context (add 'here [N]' to keep recent N turns; --preview shows what would happen)", "Session",
               aliases=("compact",), args_hint="[here [N] | focus topic | --preview|--dry-run]"),
    ...
]
```

`busy_policy` 字段值得单独说一下,因为它解决的是一个真实存在的并发问题:**用户在 Agent 正忙(执行工具、等模型返回)的时候又发来一条 slash 命令,应该怎么办?** 三种取值:

- `"reject"`(默认)——拒绝,提示"Agent 正在运行,`/xxx` 不能在轮次中途执行";
- `"dispatch"`——照常执行(比如 `/status`、`/stop` 这类查询/控制类命令,没道理非要等 Agent 空闲);
- `"interrupt_then_dispatch"`——先打断当前正在运行的 Agent,再执行命令(`/new`、`/stop` 这一类)。

这个字段被网关(`gateway/run.py`)和 CLI 共同读取,取代了此前"每个命令各写一段 if 分支判断能不能在忙碌时执行"的手写逻辑——把并发策略变成注册表里的**声明式数据**而不是分散的**命令式代码**,是一种常见的、值得学习的重构方向。

## 从 `/xxx` 到处理逻辑:真实的分发代码

CLI(`cli.py`)里真正拦截并分发 slash 命令的函数是 `process_command()`。它先通过 `resolve_command()` 把用户输入的(可能是别名的)命令词解析成规范名:

```python
# cli.py
def process_command(self, command: str) -> bool:
    cmd_lower = command.lower().strip()
    cmd_original = command.strip()

    # Resolve aliases via central registry so adding an alias is a one-line
    # change in hermes_cli/commands.py instead of touching every dispatch site.
    from hermes_cli.commands import resolve_command as _resolve_cmd
    _base_word = cmd_lower.split()[0].lstrip("/")
    _cmd_def = _resolve_cmd(_base_word)
    canonical = _cmd_def.name if _cmd_def else _base_word

    ...
    if canonical in {"quit", "exit"}:
        ...
        return False
    elif canonical == "help":
        ...
    elif canonical == "palette":
        self._open_command_palette()
    elif canonical == "whoami":
        self._handle_whoami_command()
    elif canonical == "tools":
        self._handle_tools_command(cmd_original)
    elif canonical == "config":
        self.show_config()
    ...
```

注释里那句"adding an alias is a one-line change in hermes_cli/commands.py instead of touching every dispatch site"点出了这套设计的核心收益:别名(比如 `/reset` 是 `/new` 的别名、`/bg` 是 `/background` 的别名)只需要在 `CommandDef` 的 `aliases` 元组里加一项,`resolve_command()` 会统一处理,不需要在每一处判断分支里都补一遍 `or cmd == "reset"`。

分发本身是一个巨大的 `if canonical == ... elif canonical == ...` 链条(`process_command` 函数体本身长达数百行)——这不是最"优雅"的设计,但足够直白,而且中心化的 `resolve_command` 保证了无论 if/elif 链条多长,别名解析和"这个命令是否存在"的判断都只有一份实现。分发之前还会触发一个插件观察者钩子:

```python
# cli.py（process_command 内)
if _cmd_def is not None:
    from hermes_cli.plugins import fire_pre_command_hook
    fire_pre_command_hook(
        surface="cli",
        command=canonical,
        alias_used=_base_word,
        ...
    )
```

`fire_pre_command_hook` 让插件能在任意已注册命令**执行前**得到通知(仅观察,不能拦截或修改结果),这是第 08 章插件系统要展开的内容,这里先知道有这个扩展点存在。

## 三种界面,同一套注册表

`resolve_command`、`COMMAND_REGISTRY`、`CommandDef.busy_policy` 并不是 CLI 专属的——`hermes_cli/commands.py` 同时被 TUI 和 Gateway 导入:

- **TUI**(`tui_gateway/server.py`)直接调用同一个 `resolve_command()` 解析命令名;
- **Gateway**(`gateway/run.py`、`gateway/platforms/base.py`)读取同一批 `CommandDef` 的 `busy_policy`/`busy_handler` 字段,驱动一个专门的"忙碌时中间态分发器"(`_dispatch_busy_slash_command`),决定一条消息到达时 Agent 正忙该拒绝、照常执行还是先打断再执行。

`commands.py` 模块顶部有一段注释专门说明了这种跨界面复用带来的一个工程约束——为了让 Gateway(不一定装了 `prompt_toolkit`)也能安全导入这个模块,`prompt_toolkit` 相关的类做了防御性降级:

```python
# hermes_cli/commands.py
# prompt_toolkit is an optional CLI dependency — only needed for
# SlashCommandCompleter and SlashCommandAutoSuggest.  Gateway and test
# environments that lack it must still be able to import this module
# for resolve_command, gateway_help_lines, and COMMAND_REGISTRY.
try:
    from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
    from prompt_toolkit.completion import Completer, Completion
except ImportError:
    AutoSuggest = object
    Completer = object
    ...
```

这正是"共享内核"设计要付出的代价:一个本来只有 CLI 用得上的可选依赖(终端自动补全库),因为模块被 Gateway 共享导入,也必须写成可选导入。这个模块因此同时扮演着两个角色——CLI 的自动补全数据源(`SlashCommandCompleter`),以及 CLI/TUI/Gateway 三者共同的命令元数据与分发规则中心。第 09、10 章会分别展开 Gateway 的忙碌态分发器和 TUI 的实现细节。

## 小结与思考题

Hermes 的命令系统分成两层:进程级的顶层子命令用 argparse 的 `subparsers` 组织,注册逻辑正在从"上帝文件" `main.py` 逐步拆分到 `hermes_cli/subcommands/` 下的独立模块,并且为最常见的裸 `hermes` 启动路径专门开了一条跳过全部解析器构建的快速通道;会话内的 slash 命令则完全独立于 argparse,由 `hermes_cli/commands.py` 里的 `CommandDef`/`COMMAND_REGISTRY` 中心化注册表描述(名称、别名、分类、忙碌态策略等),`resolve_command()` 统一做别名解析,`process_command()` 里的 if/elif 链条负责实际分发。这套注册表被 CLI、TUI、Gateway 三种界面共同导入复用,是"一体两面"入口设计在代码层面的落地。

思考题:

1. `_try_fast_chat_launch()` 为什么只在"确定无疑"是裸对话启动时才生效,遇到任何不确定情况(未知 flag、`--help`)都直接放弃优化、退回完整解析?这种"保守优化"的设计原则你在其他项目里见过吗?
2. `busy_policy` 把"命令能否在 Agent 忙碌时执行"从分散的 if 判断收敛成声明式字段,你觉得还有哪些同类的"每个命令都要重复判断一次"的逻辑,适合抽成 `CommandDef` 上的新字段?
3. `commands.py` 因为要被 Gateway 复用,不得不把 `prompt_toolkit` 相关的导入做成可选降级。如果让你重新设计,你会把"自动补全"这部分职责继续放在同一个文件里,还是拆成单独模块?两种做法各自的取舍是什么?
