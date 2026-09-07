# Ohmo 总览——Soul/Identity/Memory 的人格化设计

> `ohmo` 不是 OpenHarness core 的一个运行模式,而是一个独立的顶层包:它把 `openharness` 当作一个可编程的运行时库来用——复用同一套 `build_runtime`/`run_backend_host`、同一套记忆扫描与命令系统——却在上面叠加了一层完全属于自己的东西:一组存在 `~/.ohmo` 下、用户能直接打开编辑的 Markdown 文件(`soul.md`/`identity.md`/`user.md`/`BOOTSTRAP.md`)。这些文件被组装进最终的 system prompt,构成了 `ohmo` 的"人格"。这篇文章从代码层面拆开这套人格化设计,并厘清 `ohmo` 的记忆系统与 OpenHarness core 记忆系统到底是复用还是另起炉灶。

## 学习目标

- 理解 `ohmo` 与 `openharness` 之间的依赖方向:`ohmo/cli.py`、`ohmo/runtime.py` 只从 `openharness` 里 import 通用能力(鉴权、运行时构建、React 前端启动器),`openharness` 核心代码不反向依赖 `ohmo`——这是"库与产品"分层而不是"核心与插件"分层。
- 理解 `~/.ohmo` 工作区里每个文件各自的职责:`soul.md`(长期人格与行为原则)、`identity.md`(自我认知的极简摘要)、`user.md`(用户画像)、`BOOTSTRAP.md`(一次性首轮引导),以及它们被 `build_ohmo_system_prompt()` 拼装进最终 prompt 的固定顺序。
- 理解 `BOOTSTRAP.md` 的"一次性"语义是如何用 `state.json` 里的一个布尔字段实现的,以及为什么它被设计成"消失了就不该自动恢复"。
- 弄清 `ohmo` 的个人记忆(`ohmo/memory.py`)与 OpenHarness core 记忆系统的关系:是完全独立的实现,还是复用了同一套 markdown + frontmatter 扫描/校验逻辑,只是换了一个存储根目录和默认分类。
- 理解 `ohmo` 的三种运行模式(交互式 React TUI、`--backend-only`、`--print` 单次模式)如何殊途同归地调用同一个 `openharness.ui.runtime.build_runtime`,只是各自传入不同的 `system_prompt`/`session_backend`/`memory_backend`。

## 背景与设计动机

`README.zh-CN.md` 对 `ohmo` 的定位写得很直接:

> `ohmo` 是基于 OpenHarness 的 personal-agent app,不是 core 的一个 mode。

这句话在代码里体现为一个具体的 import 方向。`ohmo/cli.py` 顶部:

```python
# ohmo/cli.py:12-35(节选)
from openharness.auth.manager import AuthManager
from openharness.config import load_settings

from ohmo.gateway.config import load_gateway_config, save_gateway_config
from ohmo.gateway.models import GatewayConfig
from ohmo.gateway.service import (
    OhmoGatewayService,
    gateway_status,
    start_gateway_process,
    stop_gateway_process,
)
from ohmo.memory import add_memory_entry, list_memory_files, remove_memory_entry
from ohmo.runtime import launch_ohmo_react_tui, run_ohmo_backend, run_ohmo_print_mode
from ohmo.session_storage import OhmoSessionBackend
from ohmo.workspace import (
    get_gateway_config_path,
    get_logs_dir,
    get_workspace_root,
    ...
)
```

`ohmo` 只从 `openharness` 顶层模块借用了两样通用能力——鉴权状态(`AuthManager`)和设置加载(`load_settings`)——其余全部是 `ohmo` 自己的子模块。这不是"在 core 里加一个 `mode=ohmo` 分支",而是一个独立的 Typer 应用,自己定义 `ohmo init`/`ohmo config`/`ohmo`/`ohmo gateway *` 命令,自己管理一个完全独立于项目目录的工作区 `~/.ohmo`。这样分层的好处是:OpenHarness core 不需要知道 `ohmo` 的存在,`ohmo` 想怎么定制人格、记忆存储位置、命令集,都不会污染 core 的通用路径。

## 核心机制详解

### 工作区结构:`~/.ohmo` 与模板文件的首次生成

`ohmo/workspace.py` 定义了工作区里每个文件/目录的路径,以及首次初始化时要写入的模板内容。`initialize_workspace()` 是唯一的入口:

```python
# ohmo/workspace.py:252-278(节选)
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
    state_path = get_state_path(root)
    state_data = {"app": "ohmo", "workspace": str(root.resolve())}
    if not state_path.exists():
        state_path.write_text(json.dumps(state_data, indent=2) + "\n", encoding="utf-8")
    else:
        try:
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state_data = {"app": "ohmo", "workspace": str(root.resolve())}
    bootstrap_path = get_bootstrap_path(root)
    if not state_data.get("bootstrap_seeded"):
        state_data["bootstrap_seeded"] = True
        if not bootstrap_path.exists():
            bootstrap_path.write_text(BOOTSTRAP_TEMPLATE.strip() + "\n", encoding="utf-8")
        state_path.write_text(json.dumps(state_data, indent=2) + "\n", encoding="utf-8")
    ...
```

值得注意的是:`initialize_workspace()` 不只是 `ohmo init` 命令的实现,它是 `ohmo` 每一条运行路径(交互模式、`--backend-only`、`--print`、gateway 服务)进入前都会调用的函数——`ensure_workspace()`/模板文件补齐是幂等的,已存在的文件不会被覆盖,`BOOTSTRAP.md` 靠 `state.json` 里的 `bootstrap_seeded` 标记只写一次。这意味着用户可以放心删除或大改任何一个人格文件,重新运行 `ohmo` 时不会被模板覆盖回去,只有真正缺失的文件才会被补上默认值。

### Soul/Identity/User/Bootstrap 如何组装进 system prompt

`ohmo/prompts.py` 里的 `build_ohmo_system_prompt()` 是唯一负责拼装最终 system prompt 的函数:

```python
# ohmo/prompts.py:27-75(节选)
def build_ohmo_system_prompt(
    cwd: str | Path,
    *,
    workspace: str | Path | None = None,
    extra_prompt: str | None = None,
    include_project_memory: bool = False,
) -> str:
    """Build the custom base prompt for ohmo sessions."""
    root = get_workspace_root(workspace)
    sections = [get_base_system_prompt()]

    if extra_prompt:
        sections.extend(["# Additional Instructions", extra_prompt.strip()])

    soul = _read_text(get_soul_path(root))
    if soul:
        sections.extend(["# ohmo Soul", soul])

    identity = _read_text(get_identity_path(root))
    if identity:
        sections.extend(["# ohmo Identity", identity])

    user = _read_text(get_user_path(root))
    if user:
        sections.extend(["# User Profile", user])

    bootstrap = _read_text(get_bootstrap_path(root))
    if bootstrap:
        sections.extend(["# First-Run Bootstrap", bootstrap])

    sections.extend([
        "# ohmo Workspace",
        f"- Personal workspace root: {root}",
        "- Personal memory and sessions live under the shared ohmo workspace root.",
        "- Resume only within ohmo sessions; do not assume interoperability with plain OpenHarness sessions.",
    ])

    if ohmo_memory := load_ohmo_memory_prompt(root):
        sections.append(ohmo_memory)

    if include_project_memory:
        project_memory = load_project_memory_prompt(cwd)
        if project_memory:
            sections.append(project_memory)

    return "\n\n".join(section for section in sections if section and section.strip())
```

这个函数的结构本身就是一份"人格优先级表":先是 OpenHarness 通用的基础 system prompt(`get_base_system_prompt()`,和 core 完全一样,不做任何 `ohmo` 定制),然后依次叠加 soul(行为原则)、identity(自我认知)、user profile(用户画像)、bootstrap(首轮引导,仅在文件还存在时出现),最后才是工作区路径说明和个人记忆。每一段都用 `_read_text()` 读取,文件不存在或内容为空就直接跳过——这意味着一个刚 `ohmo init` 但还没跑过 `ohmo config`/首轮对话的用户,`BOOTSTRAP.md` 会出现在 prompt 里提示 Agent"这是第一次见面,别上来就发问卷";而当 Agent 在某次对话里认为首轮引导已经完成、删除了 `BOOTSTRAP.md` 后,这一段就自然从 prompt 里消失,不需要任何额外的状态位。

`SOUL_TEMPLATE` 里最后一句话点明了这种设计对普通用户的意义:

```python
# ohmo/workspace.py:55-58(节选,SOUL_TEMPLATE 末尾)
Read these files. Update them when something should persist.

If you materially change this file, tell the user. It is your soul.
```

这是"把人格设定拆成独立可编辑 Markdown 文件"相对于把 system prompt 硬编码进 Python 代码的核心价值:一个完全不懂代码的用户,只要能编辑一个 `.md` 文件,就能重新定义"这个助理该怎么说话、该在乎什么、该在什么时候拒绝";而且这个改动是可追溯、可 diff、可以让 Agent 自己在对话里帮忙改的——不需要重新部署代码,甚至不需要重启进程(下一轮对话读到的就是新版 `soul.md`)。

### 个人记忆:复用 core 的扫描/校验逻辑,换一个存储根

`ohmo/memory.py` 表面上是"ohmo 自己的记忆系统",但它的实现几乎完全建立在 OpenHarness core 记忆模块之上:

```python
# ohmo/memory.py:8-25(节选)
from openharness.commands import MemoryCommandBackend
from openharness.memory.scan import scan_memory_files
from openharness.memory.schema import (
    SCHEMA_VERSION,
    coerce_int,
    compute_memory_signature,
    first_content_line,
    format_datetime,
    generate_memory_id,
    memory_metadata_from_path,
    render_memory_file,
    split_memory_file,
    utc_now,
)
from openharness.utils.file_lock import exclusive_file_lock
from openharness.utils.fs import atomic_write_text

from ohmo.workspace import get_memory_dir, get_memory_index_path
```

`add_memory_entry()`、`remove_memory_entry()`、`list_memory_files()` 全部调用的是 `openharness.memory.scan`/`openharness.memory.schema` 里的函数——同一套 frontmatter 元数据格式(`schema_version`/`id`/`type`/`category`/`importance`/`signature`/`ttl_days`/`disabled`/`supersedes`)、同一套去重签名算法(`compute_memory_signature`)、同一套原子写入和文件锁(`atomic_write_text`/`exclusive_file_lock`)。`ohmo` 真正新增的只有三样:

1. 存储根目录:`get_memory_dir(workspace)` 指向 `~/.ohmo/memory`,而不是某个项目目录下的记忆目录;
2. 默认分类:新建条目固定使用 `memory_type="personal"`、`category="preference"`(见 `add_memory_entry` 里的硬编码默认值),对应"这是关于用户本人的稳定偏好",而不是某个项目相关的技术记忆;
3. 一个绑定到这个存储根的 `MemoryCommandBackend` 实例(`create_memory_command_backend()`),供 `/memory` 斜杠命令在 `ohmo` 会话里直接操作个人记忆,而不是项目记忆。

所以第 06 章讲过的记忆扫描/校验/去重机制在这里没有被重新发明,`ohmo` 只是把同一套机制实例化到了一个不同的目录、绑定了不同的默认元数据。`load_memory_prompt()` 把 `MEMORY.md` 索引和最多 5 篇最新记忆文件拼进 prompt 的 `# ohmo Memory` 段落,这也是上一节 `build_ohmo_system_prompt()` 里 `load_ohmo_memory_prompt(root)` 调用的来源。

有一个容易忽视的边界:`build_ohmo_system_prompt()` 的 `include_project_memory` 参数默认是 `False`,而 `ohmo/runtime.py` 里三条运行路径(`run_ohmo_backend`/`run_ohmo_print_mode`/以及后面会讲到的 gateway 会话池)在调用它时都没有传 `True`。也就是说,`ohmo` 默认不会把当前项目目录下的项目级记忆(`include_project_memory=True` 时才会加载的 `load_project_memory_prompt(cwd)`)混进个人助理的 system prompt——这是一个刻意的边界:个人身份和个人偏好不应该被"我恰好在哪个代码仓库里跟你对话"稀释或污染。

### 运行时复用:三种运行模式,同一个 `build_runtime`

`ohmo/runtime.py` 提供三种运行 `ohmo` 的方式,但底层都收敛到 OpenHarness core 暴露的同一组可编程接口:

```python
# ohmo/runtime.py:11-20(节选,import)
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

三种模式各自调用不同的 core 入口,但传入的参数形状是一致的:

- `run_ohmo_backend()` 调用 `run_backend_host()`(交互式 React 前端背后的后端进程),传入 `system_prompt=build_ohmo_system_prompt(...)`、`session_backend=OhmoSessionBackend(...)`、`memory_backend=create_memory_command_backend(...)`、`extra_skill_dirs`/`extra_plugin_roots` 指向 `~/.ohmo/skills`/`~/.ohmo/plugins`、以及一份 `autodream_context`(标注 `app_label="ohmo personal memory"`,供 core 的后台记忆整理任务识别是在为 `ohmo` 工作)。
- `launch_ohmo_react_tui()` 不直接跑对话逻辑,而是拼一条子进程命令 `python -m ohmo --backend-only ...`(见 `build_ohmo_backend_command()`),通过环境变量 `OPENHARNESS_FRONTEND_CONFIG` 把这条命令交给 core 自带的 React 终端前端(`get_frontend_dir()`/`_resolve_tsx()`)去启动——也就是说,`ohmo` 复用的是 OpenHarness 同一套前端 UI 工程,只是后端进程换成了 `ohmo` 自己的 `--backend-only` 入口。
- `run_ohmo_print_mode()` 直接调用 `build_runtime()` 拿到一个 `RuntimeBundle`,`start_runtime()` 启动后用 `handle_line()` 提交一次性 prompt,逐个事件(`AssistantTextDelta`/`AssistantTurnComplete`/`ErrorEvent`/...)打印到 stdout/stderr,是三种模式里最"薄"的一层封装。

这三条路径没有一条重新实现了引擎驱动逻辑,全部依赖 `openharness.ui.runtime.build_runtime`/`start_runtime`/`close_runtime`/`handle_line` 这组函数——这组函数正是 OpenHarness 提供给"任何想在自己的产品里嵌入一个 Agent 会话"的调用方的可编程接口。下一篇要讲的 gateway 会话池,复用的也是同一组函数,这一点会在第二篇里用代码验证清楚。

## 常见问题/易踩坑

- **改了 `soul.md` 会立刻生效吗?** 会,但只对下一次新建的 `RuntimeBundle` 生效。`build_ohmo_system_prompt()` 每次构建 system prompt 都会重新读取磁盘上的文件,不存在缓存;但一个已经在跑的长会话(比如 gateway 里挂了很久的一个 chat session)不会自动重新拼一次完整 prompt,除非该会话下一轮消息触发了 `set_system_prompt()` 调用。
- **`BOOTSTRAP.md` 消失后还会自动恢复吗?** 不会。`state.json` 里的 `bootstrap_seeded` 一旦被置为 `True`,`initialize_workspace()` 就再也不会重新创建 `BOOTSTRAP.md`——这是刻意设计,`BOOTSTRAP_TEMPLATE` 模板文本里也写明"如果它消失了,不要假设应该把它加回来"。如果用户确实想重新走一次首轮引导,需要手动把 `bootstrap_seeded` 改回 `false` 并重新创建文件。
- **个人记忆和项目记忆会不会串?** 默认不会。`include_project_memory` 在 `ohmo` 的所有调用点上都保持默认值 `False`,个人 workspace 下的记忆与用户当前所在项目目录的记忆是两套互不合并的上下文。

## 小结

`ohmo` 用一个干净的分层验证了"库 vs 产品"的设计边界:`openharness` 提供通用、无个性的运行时能力(`build_runtime`/`run_backend_host`/记忆扫描/命令系统/React 前端),`ohmo` 在其上叠加了一层完全独立的人格系统——`soul.md`/`identity.md`/`user.md`/`BOOTSTRAP.md` 这些用户可编辑的 Markdown 文件,通过 `build_ohmo_system_prompt()` 按固定顺序拼进最终 prompt;个人记忆复用了 core 的 markdown+frontmatter 扫描/校验逻辑,只是换了存储根目录和默认分类;三种运行模式殊途同归地调用同一个 `build_runtime()`。下一篇我们把视角转向 `ohmo` 真正让这个人格"活起来"的地方——gateway:一条消息从 Telegram/Slack/飞书等平台进来,是怎么被路由到正确的 workspace/session、驱动一次真正的 Agent 会话、再发回原平台的。
