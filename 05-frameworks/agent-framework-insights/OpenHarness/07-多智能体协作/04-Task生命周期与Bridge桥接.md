# Task 生命周期与 Bridge 桥接

> `tasks/manager.py` 里的 `BackgroundTaskManager` 不是一个"给多智能体系统用的组件",而是一份更底层、更通用的后台进程生命周期基础设施——它不知道什么是 swarm,也不知道什么是 coordinator。上一篇看到的 `SubprocessBackend` 靠它把队员跑起来,`agent_tool.py` 派生的每一个 worker 也活在它的记录表里,连和多智能体毫无关系的记忆整理后台任务("dream")也复用的是同一套代码。六个 `task_*_tool.py` 工具就是模型操纵这份记录表的统一入口。本篇前半篇讲清楚这套通用基础设施,后半篇转向 `bridge/` 目录——一层职责更窄、体量也小得多的模块,把"外部系统凭一份凭证驱动一次会话"这件事,包装成几个可以直接调用的 Python 函数。

## 学习目标

- 理解 `TaskRecord`/`TaskType`/`TaskStatus` 这套统一的任务数据模型,以及 `BackgroundTaskManager` 如何用一份 argv-direct-exec 的子进程启动逻辑同时服务 shell 命令、本地/远程 Agent、进程内队员、记忆整理这几类完全不同的任务。
- 弄清 `_watch_process()` 用 generation 计数器防止"任务被重启后,旧进程的收尾逻辑覆盖新进程状态"这一类竞态,以及 `_restart_agent_task()` 自动续跑背后"上下文不会被保留"这个诚实的代价声明。
- 理解六个 `task_*_tool.py` 工具如何作为薄封装,统一指向同一个单例 `BackgroundTaskManager`,从而让"后台任务"和"前台对话"通过日志文件、进度元数据、完成监听器解耦。
- 理解 `bridge/` 目录的最小化实现:`work_secret.py` 怎么编解码一份远程凭证并拼出 WebSocket 地址,`session_runner.py`/`manager.py` 怎么另起一套(而不是复用 `BackgroundTaskManager`)子进程管理逻辑。
- 基于代码里能验证的事实,弄清 `bridge/` 和 `swarm/`/`coordinator/`/`tasks/` 之间是否存在直接的函数调用耦合。

## 背景与设计动机

一个多智能体系统里,"跑起来一个后台进程、追踪它的状态、把它的输出喂给别处、决定它什么时候该被判定为完成"这件事会被反复用到——不管这个进程装的是一个 shell 命令、一个 worker Agent,还是别的什么。把这套逻辑单独抽成 `tasks/` 目录,好处是:任何需要"后台跑点什么"的功能都不用重新发明一遍进程管理,只需要往里塞一个新的 `TaskType`。这也是为什么 `TaskType` 里除了和多智能体直接相关的 `local_agent`/`remote_agent`/`in_process_teammate`,还有一个和 swarm 毫无关系的 `local_bash`(纯 shell 命令)和 `dream`(`services/autodream/service.py` 用它跑记忆巩固任务,对应 `/dream` 斜杠命令)——这恰恰说明 `tasks/` 是被设计成一份通用基础设施,而不是 swarm 的私有实现细节。

## 核心机制详解

### `TaskRecord`:任务的统一数据模型

```python
# src/openharness/tasks/types.py:10-32
TaskType = Literal["local_bash", "local_agent", "remote_agent", "in_process_teammate", "dream"]
TaskStatus = Literal["pending", "running", "completed", "failed", "killed"]

@dataclass
class TaskRecord:
    """Runtime representation of a background task."""
    id: str
    type: TaskType
    status: TaskStatus
    description: str
    cwd: str
    output_file: Path
    command: str | None = None
    prompt: str | None = None
    ...
    metadata: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] | None = None
    argv: list[str] | None = None
```

五种 `TaskType` 共用同一份字段:有的任务用 `command`(shell 字符串)启动,有的用 `argv`(直接 exec 列表)启动,`prompt` 只对能接受输入的 Agent 类任务有意义,`metadata` 是一个自由的字符串字典,供 `task_update` 工具写入进度和状态备注。所有任务不论类型,输出都统一落在同一份 `output_file`(每个任务一个独立日志文件)里。

### `BackgroundTaskManager`:进程生命周期与 stdin/stdout 的桥接

启动逻辑延续了上一篇提到的"绕开 shell、直接 argv exec"的原则,`create_shell_task()` 的文档字符串把这个选择的原因写得很清楚——同一个 Windows Git Bash 问题在这里再次出现:

```python
# src/openharness/tasks/manager.py:76-82(节选)
"""...The ``argv`` form bypasses shell invocation entirely — it spawns the
executable directly via ``asyncio.create_subprocess_exec(*argv)`` — which is
the right choice for teammate spawning on Windows: Git Bash cannot reliably
exec Windows-pathed binaries...even though the same shell call works
interactively. Bypassing the shell sidesteps that entire class of
platform-quoting bug."""
```

`create_agent_task()` 在没有显式 `command`/`argv` 时,会自己拼一个默认的 `["python", "-m", "openharness", "--api-key", ...]`,拿到 `TaskRecord` 之后立刻调用 `write_to_task()` 把 `prompt` 当成第一行输入写进子进程的 stdin——启动和"喂第一句话"是两个独立步骤,不是一次调用完成的。

**监视循环用 generation 计数器防止竞态**——`_watch_process()` 在进程退出后要回填任务的最终状态,但如果这段时间任务已经被重启过(比如 leader 在等待过程中又调用了一次 `write_to_task`,触发了自动续跑),旧的监视协程绝不能覆盖新进程产生的状态:

```python
# src/openharness/tasks/manager.py:249-269(节选)
async def _watch_process(self, task_id, process, generation):
    reader = asyncio.create_task(self._copy_output(task_id, process))
    return_code = await process.wait()
    await reader
    await _close_process_stdin(process)

    current_generation = self._generations.get(task_id)
    if current_generation != generation:
        return  # 属于旧一代进程的收尾逻辑,当前已经是新进程了,直接放弃

    task = self._tasks[task_id]
    task.return_code = return_code
    if task.status != "killed":
        task.status = "completed" if return_code == 0 else "failed"
    ...
```

**stdin 写入失败会自动重启,但明确不保证上下文保留**——`write_to_task()` 遇到 `BrokenPipeError`/`ConnectionResetError`(进程已经退出但调用方还在往里写)时,如果任务类型属于可接受输入的三种(`local_agent`/`remote_agent`/`in_process_teammate`),会自动调用 `_restart_agent_task()` 重新拉起一个新进程,并把同一句话重新写进新进程的 stdin。但这不是真正的"续接"——`_restart_agent_task()` 只是用原来的 `command`/`argv` 重新起一个全新进程,并在日志里追加一条明确的告知:

```python
# src/openharness/tasks/manager.py:20
_TASK_RESTART_NOTICE = "[OpenHarness] Agent task restarted; prior interactive context was not preserved.\n"
```

也就是说,调用方(比如 coordinator 的 `send_message`)以为自己在"继续"一个 worker 的对话,但如果那个 worker 进程恰好已经自然退出,这次续接实际上是一个带着相同启动参数、但**丢失了此前所有交互历史**的全新进程——这是一个值得警惕的边界情况:重启保证的是"同一个 task_id 还能继续接收输入",不是"对话记忆被完整保留"。

**完成通知走监听器模式,不是轮询**——`register_completion_listener()` 允许任意代码订阅"某个任务进入终态"这个事件,`_notify_completion_listeners()` 在任务真正结束时统一广播,并且把异常隔离在每个监听器内部(`except Exception: log.exception(...)`,一个监听器出错不影响其他监听器和任务状态本身)。上一篇提到 `agent_tool.py` 注册的 `SUBAGENT_STOP` 钩子,走的正是这条通道。

### 六个 `task_*_tool.py`:任务生命周期在工具层的切面

六个工具全部是薄封装,唯一共同的依赖是同一个单例:

```python
manager = get_task_manager()
```

- **`task_create`**——支持 `local_bash`(需要 `command`)或 `local_agent`(需要 `prompt`)两种类型,是模型自己起后台任务(不通过 swarm/coordinator)的入口。
- **`task_get`**——只读(`is_read_only() -> True`),按 ID 返回单个 `TaskRecord` 的字符串表示。
- **`task_list`**——只读,可选按 `status` 过滤,无任务时返回 `"(no tasks)"` 而不是空字符串或报错。
- **`task_output`**——只读,`max_bytes` 限制在 1~100000 之间,底层调用 `manager.read_task_output()` 只截取日志文件的**尾部**——保证长时间运行任务的输出不会无限增长地塞回模型上下文。
- **`task_update`**——纯元数据更新(`description`/`progress`/`status_note`),不影响任务的实际执行,是留给 UI 展示和跨 worker 协调用的进度旁路信息。
- **`task_stop`**——终止任务,底层 `stop_task()` 先 `terminate()`,3 秒内没退出再 `kill()`,是这个代码库里反复出现的"先温和、超时再强制"模式(和上一篇 `InProcessBackend.shutdown()` 的优雅取消/强制取消如出一辙)。

这六个工具没有各自维护状态,全部指向同一个 `BackgroundTaskManager` 实例——这意味着不管一个任务是通过 `task_create` 直接建的,还是通过 `agent` 工具委派出的 worker,还是 swarm 的子进程队员,模型都可以用这同一套六个工具去查询、更新、终止它。**"后台任务"和"前台对话"的解耦**正是靠这套组合实现的:进程本身异步运行、独立于发起它的那次工具调用;日志文件是持久化的旁路输出通道;`task_output`/`task_get` 让调用方按需拉取状态而不必阻塞等待;`register_completion_listener` 让关心结果的代码(比如 `SUBAGENT_STOP` 钩子)被动接收通知而不必轮询。

## Bridge:把"驱动一次会话"包装成一个可编程接口

`bridge/` 目录明显比 `tasks/`/`swarm/`/`coordinator/` 薄得多,四个文件里没有一个超过 50 行。它解决的是另一类问题:外部系统怎么给这台机器派活、以及怎么在本地拉起并追踪一个"会话"进程。

### `work_secret.py`:一份自描述的远程凭证

`bridge/types.py` 定义了三个极简的数据类:`WorkData(type: session|healthcheck, id)`、`WorkSecret(version, session_ingress_token, api_base_url)`、`BridgeConfig(dir, machine_name, max_sessions, session_timeout_ms)`。真正有实质逻辑的是编解码:

```python
# src/openharness/bridge/work_secret.py:11-32
def encode_work_secret(secret: WorkSecret) -> str:
    data = json.dumps(secret.__dict__, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def decode_work_secret(secret: str) -> WorkSecret:
    padding = "=" * (-len(secret) % 4)
    raw = base64.urlsafe_b64decode((secret + padding).encode("utf-8"))
    data = json.loads(raw.decode("utf-8"))
    if data.get("version") != 1:
        raise ValueError(f"Unsupported work secret version: {data.get('version')}")
    if not data.get("session_ingress_token"):
        raise ValueError("Invalid work secret: missing session_ingress_token")
    ...
```

一份 work secret 就是一段 base64url 编码的 JSON,携带一个 `session_ingress_token`(认证令牌)和 `api_base_url`(要连接的服务端地址),`version` 字段做前向兼容校验——版本不是 1 就直接拒绝,不做静默的向后兼容猜测。`build_sdk_url()` 用这份凭证拼出一个 WebSocket 地址:

```python
# src/openharness/bridge/work_secret.py:35-41
def build_sdk_url(api_base_url: str, session_id: str) -> str:
    is_local = "localhost" in api_base_url or "127.0.0.1" in api_base_url
    protocol = "ws" if is_local else "wss"
    version = "v2" if is_local else "v1"
    host = api_base_url.replace("https://", "").replace("http://", "").rstrip("/")
    return f"{protocol}://{host}/{version}/session_ingress/ws/{session_id}"
```

这套函数暗示的场景是:某个外部的调度系统(在本仓库快照里没有出现具体实现,只能从这几个函数的命名和字段反推)给这台机器分配一份工作(`WorkData`,类型是 `session` 或 `healthcheck`),连同一份 `WorkSecret`——本地解码后,凭 `session_ingress_token` 和拼出的 WebSocket URL 向一个叫 `session_ingress` 的远端端点建立连接,接收/汇报某个 `session_id` 对应的工作进展。这几个函数本身是纯函数、没有网络调用逻辑、也不依赖任何全局状态,可以被任何 Python 代码直接 import 调用——这正符合"把驱动一次会话的凭证与地址计算,封装成一个可编程接口"的定位。

### `session_runner.py` + `manager.py`:真正跑起来的是什么

`spawn_session()` 本身很朴素——就是拿一个任意 shell 命令去起一个子进程:

```python
# src/openharness/bridge/session_runner.py:32-46
async def spawn_session(*, session_id: str, command: str, cwd: str | Path) -> SessionHandle:
    resolved_cwd = Path(cwd).resolve()
    process = await create_shell_subprocess(
        command, cwd=resolved_cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    return SessionHandle(session_id=session_id, process=process, cwd=resolved_cwd)
```

`SessionHandle.kill()` 走的还是那套"先 terminate、超时再 kill"的熟悉模式。`BridgeSessionManager` 在此之上加了一层记录:每个 session 一份独立的输出日志文件(存在 `get_data_dir()/"bridge"/<session_id>.log`)、一个后台协程持续把 stdout 尾随写入日志、`list_sessions()` 根据 `process.returncode` 反推 `running`/`completed`/`failed` 状态。

**这里有一个值得明确指出的观察**:`BridgeSessionManager` 完全没有复用前半篇的 `BackgroundTaskManager`,而是自己重新实现了一套几乎同构的逻辑——子进程启动、输出尾随写日志、按退出码判定状态。两者机制上高度相似,但代码层面完全独立、没有共享任何类或函数。合理的解释是两者服务的语义不同:`tasks/` 里的任务是"当前这次对话过程中,模型或系统临时起的一个后台工具/子代理",生命周期和身份都由本进程分配;而 bridge session 的 `session_id` 是外部调度系统(通过 work secret)指定的,面向的是"整机被远程接管去跑一个完整会话"这种更贴近基础设施调度的场景。是否值得在未来合并成一套代码,是这两处实现留下的一个开放问题,但至少在当前快照里,它们是两套并行、没有互相调用的实现。

### `bridge/` 和 `swarm/`/`coordinator/`/`tasks/` 之间没有直接调用关系

在整个源码树里搜索 `openharness.bridge` 的引用,唯一的消费方是 `commands/registry.py`(`/bridge` 斜杠命令,提供 `show`/`encode`/`decode`/`sdk`/`spawn`/`list`/`output`/`stop` 几个子命令)和 UI 状态面板(`ui/backend_host.py`/`ui/runtime.py`/`ui/protocol.py`,只是把 `bridge_sessions` 的数量和列表展示出来)。反过来搜索 `swarm/`、`coordinator/`、`tasks/` 内部,也没有任何一处 import 了 `bridge` 模块。也就是说,在这份代码快照里,**bridge 和本章前三篇讲的多智能体基础设施之间没有任何直接的函数调用耦合**——它们是并列挂在同一个 CLI 进程上的独立子系统,唯一的公共交汇点是磁盘目录约定(各自在 `~/.openharness/` 下开自己的子目录)和同一个斜杠命令分发器。`bridge/` 目前更像是一层为"外部系统接入"预留的最小化接口骨架:它已经把凭证解码、地址拼接、会话进程管理这几个动作做成了独立可调用的函数,但在这份快照里,唯一实际调用它们的是本地的 `/bridge` 调试命令,还没有看到一个真正意义上的"外部系统"在消费它。

## 小结

`tasks/` 目录提供的是一份与多智能体无关的通用后台进程生命周期基础设施——`BackgroundTaskManager` 用统一的 `TaskRecord` 模型、argv-direct-exec 的启动方式、generation 计数器防竞态的监视循环、自动续跑与完成监听器,同时服务着 swarm 的子进程队员、coordinator 的 worker,以及和多智能体毫无关系的记忆整理任务;六个 `task_*_tool.py` 工具是模型操纵这份共享状态的统一入口,靠日志文件与监听器机制把后台执行和前台对话解耦。`bridge/` 则是体量小得多的另一层——用一份自描述的 work secret 承载远程凭证与连接地址,用一套独立于 `tasks/` 的子进程管理逻辑追踪本地会话进程,把"外部系统驱动一次 OpenHarness 会话"这件事包装成几个可以直接调用的 Python 函数,但在这份代码快照里,它和 `swarm`/`coordinator`/`tasks` 之间还没有产生任何直接的调用耦合。下一章会看到 bridge 这类编程接口的一个具体消费方——ohmo 的 Gateway 系统。
