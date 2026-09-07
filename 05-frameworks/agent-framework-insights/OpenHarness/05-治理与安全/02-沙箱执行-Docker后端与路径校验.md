# 沙箱执行:Docker 后端与路径校验

> `docker_backend.py` 里有一行注释把这一篇要讲的核心矛盾点破了:"Docker backend currently supports only fully disabled networking... Fail closed instead of silently widening egress to unrefined bridge networking"。这句注释背后是一个更大的事实——`SandboxNetworkSettings` 里的 `allowed_domains`/`denied_domains` 字段虽然存在,但 Docker 后端根本不读它们,只会在检测到用户配置了这些字段时打一条警告日志,然后照样把网络锁死成 `none`。这不是偷懒,而是一种明确的取舍:与其假装实现了一套域名级别的网络管控、结果留了漏洞,不如干脆不做选择性放行,只提供"完全没有网络"这一种确定性的状态。读这一篇的时候,请把这种"宁可少做、也不做半成品安全特性"的态度当作理解 OpenHarness 沙箱设计的一条主线。

## 学习目标

- 理解为什么上一篇讲的进程内权限审批(`PermissionChecker`)不足以构成安全边界,沙箱要解决的是哪一类它管不到的风险。
- 弄清 OpenHarness 里实际存在的两种沙箱后端——默认的 `srt`(基于 bubblewrap/sandbox-exec 的外部沙箱运行时)和可选的 `docker`——以及它们之间的调度是怎么实现的。
- 精读 `docker_backend.py` 如何构造 `docker run`/`docker exec` 参数来隔离文件系统和网络,以及它对网络策略"能做什么、明确不做什么"的取舍。
- 弄清一个容易被忽略的事实:即便 Docker 沙箱正在运行,也不是所有工具调用都会进入容器——`bash`/`grep`/`glob` 会,但 `read_file`/`write_file`/`edit_file` 不会,这直接决定了 `path_validator.py` 存在的必要性。
- 理解 `path_validator.py` 在容器边界之外补的是哪一层校验,以及它目前的实现和配置项之间存在哪些还没打通的地方。

## 背景与设计动机

上一篇讲的 `PermissionChecker` 解决的是"要不要问用户"的问题——它是一段跑在 Agent 进程内部的判断逻辑,靠字符串匹配、glob 规则、工具名黑白名单来决定一次调用是放行、拒绝还是弹窗确认。但这套机制有一个结构性的局限:它本身也是被同一个进程里的代码调用的,一旦某个判断被绕过、或者某个工具的实现根本没有接入这套检查,`PermissionChecker` 挡不住任何东西——它是一层"愿意配合的礼貌门",不是一堵墙。

真正的墙需要操作系统来砌。这就是沙箱要解决的问题:把 Agent 生成的 Bash 命令关进一个文件系统和网络都被显式收窄的执行环境里,让"这条命令能碰到什么"这件事不再取决于 Python 代码里某个 if 判断有没有写对,而是取决于内核 / 容器运行时强制执行的边界。OpenHarness 对这件事的态度同样务实:沙箱默认是关闭的(`SandboxSettings.enabled` 默认 `False`),开启后也不是所有工具都会被同等对待——这一点在文章后半段会详细展开,它直接关系到 `path_validator.py` 存在的原因。

## 核心机制详解

### 沙箱默认关闭,且实际存在两种后端

`SandboxSettings` 的默认值本身就是一条信息:

```python
# src/openharness/config/settings.py:104-113
class SandboxSettings(BaseModel):
    """Sandbox-runtime integration settings."""

    enabled: bool = False
    backend: str = "srt"
    fail_if_unavailable: bool = False
    enabled_platforms: list[str] = Field(default_factory=list)
    network: SandboxNetworkSettings = Field(default_factory=SandboxNetworkSettings)
    filesystem: SandboxFilesystemSettings = Field(default_factory=SandboxFilesystemSettings)
    docker: DockerSandboxSettings = Field(default_factory=DockerSandboxSettings)
```

`enabled=False` 意味着一个全新安装的 OpenHarness,默认情况下 Bash 工具是直接跑在宿主机进程里的,唯一的门是上一篇讲的 `PermissionChecker`。沙箱是一个需要用户显式打开的选项,而不是开箱即用的默认行为——这一点在读这篇文章、评估"OpenHarness 到底有多安全"之前必须先确认清楚。

其次,`backend` 默认值是 `"srt"`,不是 `"docker"`。这里需要纠正一个从文件名容易产生的直觉:`sandbox/adapter.py` 顶部的 docstring 写的是"Adapter around the `srt` sandbox-runtime CLI"——它不是一个笼统的"沙箱后端抽象层",而是专门对接 Anthropic 的 `sandbox-runtime`(`srt`)命令行工具的适配代码。`srt` 在 Linux 上依赖 `bubblewrap`(`bwrap`),在 macOS 上依赖 `sandbox-exec`(Seatbelt),在原生 Windows 上不支持:

```python
# src/openharness/sandbox/adapter.py:86-100(节选)
if platform_name in {"linux", "wsl"} and shutil.which("bwrap") is None:
    return SandboxAvailability(
        enabled=True, available=False,
        reason="bubblewrap (`bwrap`) is required for sandbox runtime on Linux/WSL",
        command=srt,
    )

if platform_name == "macos" and shutil.which("sandbox-exec") is None:
    return SandboxAvailability(
        enabled=True, available=False,
        reason="`sandbox-exec` is required for sandbox runtime on macOS",
        command=srt,
    )
```

也就是说,bubblewrap 并不是 OpenHarness 里"留给未来"的方案,而是默认后端已经在用的机制,只是它被包在外部 `srt` 二进制背后,OpenHarness 自己的代码不直接调用 `bwrap`。`docker` 是与 `srt` 平行的**第二种**、需要用户显式选择的后端(`sandbox.backend: "docker"`)。这篇文章聚焦的正是这第二种——因为它的隔离逻辑完全在 OpenHarness 自己的代码里实现,便于逐行分析;`srt` 后端的具体隔离规则交给了外部工具,OpenHarness 这一侧只负责拼参数、传配置。

两种后端之间没有一个共享的抽象基类(比如某个 `SandboxBackend` 接口),调度是靠字符串比较硬编码在两处调用点上。第一处在 `wrap_command_for_sandbox()` 里,`srt` 路径遇到 `backend == "docker"` 会主动让路:

```python
# src/openharness/sandbox/adapter.py:105-118(节选)
def wrap_command_for_sandbox(
    command: list[str],
    *,
    settings: Settings | None = None,
) -> tuple[list[str], Path | None]:
    """Wrap an argv list with ``srt`` when sandboxing is active."""
    resolved_settings = settings or load_settings()
    if resolved_settings.sandbox.backend == "docker":
        return command, None
    availability = get_sandbox_availability(resolved_settings)
    ...
```

第二处在 `utils/shell.py` 的 `create_shell_subprocess()` 里,它是真正做出选择的地方——先判断是不是 `docker` 后端并且有一个正在运行的容器会话,是的话走 `docker exec`;否则落到"既有的 `srt` 路径"(注释原文就是 "Existing srt path"):

```python
# src/openharness/utils/shell.py:59-88(节选)
# Docker backend: route through docker exec
if resolved_settings.sandbox.enabled and resolved_settings.sandbox.backend == "docker":
    from openharness.sandbox.session import get_docker_sandbox

    session = get_docker_sandbox()
    if session is not None and session.is_running:
        argv = resolve_shell_command(command)
        return await session.exec_command(argv, cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr, env=...)
    if resolved_settings.sandbox.fail_if_unavailable:
        raise SandboxUnavailableError("Docker sandbox session is not running")

# Existing srt path
argv = resolve_shell_command(command, prefer_pty=prefer_pty)
argv, cleanup_path = wrap_command_for_sandbox(argv, settings=resolved_settings)
```

这种"没有正式接口、靠字符串判断分流"的写法虽然不优雅,但它确实标记出了一个明确的扩展点:要接入第三种后端,大概率是往这两处各加一个 `elif backend == "xxx"` 分支,而不是去实现某个抽象方法。代码目前没有更进一步的迹象(比如一个占位的 Protocol 类或者 TODO 注释)能说明这个扩展点背后有更完整的规划,只能如实说这是当前两处调用点各自硬编码的现状。

### Docker 后端:文件系统与网络怎么被收窄

`DockerSandboxSession._build_run_argv()` 是理解 Docker 后端隔离范围的核心函数——它拼出的 `docker run` 参数,就是这个沙箱实际提供的边界:

```python
# src/openharness/sandbox/docker_backend.py:82-128(节选)
def _build_run_argv(self) -> list[str]:
    docker = shutil.which("docker") or "docker"
    sandbox = self.settings.sandbox
    docker_cfg = sandbox.docker
    cwd_str = str(self.cwd.resolve())

    argv = [docker, "run", "-d", "--rm", "--name", self._container_name]

    # Docker backend currently supports only fully disabled networking.
    # Domain-level allow/deny policies exist for the srt backend, but Docker
    # does not enforce them yet. Fail closed instead of silently widening
    # egress to unrestricted bridge networking.
    if sandbox.network.allowed_domains or sandbox.network.denied_domains:
        logger.warning(
            "Docker sandbox does not enforce allowed_domains/denied_domains yet; "
            "keeping network disabled"
        )
    argv.extend(["--network", "none"])

    if docker_cfg.cpu_limit > 0:
        argv.extend(["--cpus", str(docker_cfg.cpu_limit)])
    if docker_cfg.memory_limit:
        argv.extend(["--memory", docker_cfg.memory_limit])

    # Bind-mount project directory at the same path
    argv.extend(["-v", f"{cwd_str}:{cwd_str}"])
    argv.extend(["-w", cwd_str])

    for mount in docker_cfg.extra_mounts:
        argv.extend(["-v", mount])
    for key, value in docker_cfg.extra_env.items():
        argv.extend(["-e", f"{key}={value}"])

    argv.extend([docker_cfg.image, "tail", "-f", "/dev/null"])
    return argv
```

拆开看这几个参数各自在做什么:

- **网络**:`--network none` 是彻底断网,不是"按域名白名单放行"。前面提到的注释说得很直接——`SandboxNetworkSettings.allowed_domains`/`denied_domains` 这两个配置字段目前只被 `srt` 后端(通过 `build_sandbox_runtime_config()` 转换成 `srt` 的 JSON 配置)消费,Docker 后端读到这两个字段非空时只会打一条警告日志,然后继续执行 `--network none`——它选择用"完全没有网络"这一种唯一状态,把"选择性放行网络"这件本身就容易出安全漏洞的功能明确排除在实现范围之外。
- **文件系统**:唯一的挂载是 `-v {cwd}:{cwd}`——把当前工作目录以**相同路径**挂进容器,再用 `-w {cwd}` 把容器内的工作目录设成同一个路径。容器里看不到宿主机上除了这个目录(以及 `docker_cfg.extra_mounts` 显式追加的路径)之外的任何东西。"用相同路径挂载"这个细节值得多说一句:它让容器内外的路径字符串完全一致,不需要做任何路径翻译——这为后面要讲的 `path_validator.py` 提供了一个重要前提:host 侧用 `cwd` 做边界判断的逻辑,和容器侧实际能看到的文件系统边界,说的是同一套坐标系。
- **资源限制**:`--cpus`/`--memory` 只有配置了非零值才会追加(测试 `test_resource_limits_omitted_when_zero` 也确认了这一点),默认不设限。
- **启动方式**:容器用 `tail -f /dev/null` 保活,自身不跑任何业务进程——真正的命令是之后通过 `docker exec` 逐条送进去的,这样一个会话可以复用同一个长驻容器,不必每次执行都重新拉起。

执行阶段对应的是 `exec_command()`,本质是把 argv 包一层 `docker exec -w <cwd> <container> <argv...>`:

```python
# src/openharness/sandbox/docker_backend.py:198-232(节选)
async def exec_command(self, argv, *, cwd, stdin=None, stdout=None, stderr=None, env=None):
    if not self._running:
        raise SandboxUnavailableError("Docker sandbox session is not running")
    docker = shutil.which("docker") or "docker"
    cmd: list[str] = [docker, "exec", "-w", str(Path(cwd).resolve())]
    if env:
        for key, value in env.items():
            cmd.extend(["-e", f"{key}={value}"])
    cmd.append(self._container_name)
    cmd.extend(argv)
    return await asyncio.create_subprocess_exec(*cmd, stdin=stdin, stdout=stdout, stderr=stderr)
```

返回值是一个和 `asyncio.create_subprocess_exec()` 同接口的 `Process` 对象——这是一处刻意做的适配:调用方(`bash` 工具、`grep`/`glob` 工具)不需要关心命令到底是直接起了一个子进程,还是通过 `docker exec` 钻进了容器,读 stdout/stderr、等待退出码的方式完全一样。

### 镜像:一个不区分语言栈的最小基础环境

`docker_image.py` 负责镜像的存在性检查和按需构建,`ensure_image_available()` 是入口:

```python
# src/openharness/sandbox/docker_image.py:93-104
async def ensure_image_available(image: str, auto_build: bool) -> bool:
    """Ensure the sandbox image exists, optionally building it."""
    if await _image_exists(image):
        return True
    if not auto_build:
        logger.warning("Docker image %r not found and auto_build_image is disabled", image)
        return False
    return await build_default_image(image)
```

`_image_exists()` 用 `docker image inspect` 做存在性判断,`DockerSandboxSettings.auto_build_image` 默认是 `True`——意味着首次启用 Docker 沙箱时,不需要用户手动 `docker build`,`DockerSandboxSession.start()` 会自动触发一次构建。构建用的 Dockerfile 内容非常简短:

```dockerfile
# src/openharness/sandbox/Dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    ripgrep bash git && \
    rm -rf /var/lib/apt/lists/*
RUN useradd -m -s /bin/bash ohuser
USER ohuser
```

这个镜像里只有 Python 3.11、`ripgrep`、`bash`、`git`,以及一个非 root 的 `ohuser` 用户(`USER ohuser` 确保容器内命令不以 root 身份执行,这是即便容器本身已经隔离、依然值得保留的一层最小权限原则)。它明显不是为某个具体语言栈(Node、Go、Rust……)定制的开发环境,而是一个通用的最小基座——这意味着如果 Agent 在沙箱里需要跑 `npm install` 之类的命令,默认镜像大概率是缺依赖的,需要用户通过 `DockerSandboxSettings.extra_mounts`/自定义镜像去补全。`get_dockerfile_content()` 还把这份内容硬编码在 Python 源码里作为 fallback(当 `Dockerfile` 文件本身不存在时,通过 stdin 管道传给 `docker build -`),两份内容需要手动保持一致,这是一个容易在后续维护中漏改的地方。

### session.py:进程级单例与容器泄漏的安全网

`session.py` 管理的是"当前 OpenHarness 进程里有没有一个正在运行的 Docker 沙箱会话"这件事,用的是一个模块级全局变量:

```python
# src/openharness/sandbox/session.py:16-56(节选)
_active_session: DockerSandboxSession | None = None

async def start_docker_sandbox(settings: Settings, session_id: str, cwd: Path) -> None:
    global _active_session
    ...
    session = DockerSandboxSession(settings=settings, session_id=session_id, cwd=cwd)
    await session.start()
    _active_session = session

    # Safety net: stop the container if the process exits without close_runtime()
    atexit.register(session.stop_sync)
```

这里有两个值得注意的设计点。第一,全局单例意味着一个 OpenHarness 进程同一时间只维护一个 Docker 沙箱容器,`get_docker_sandbox()`/`is_docker_sandbox_active()` 全局读取的都是同一个会话——这和 `bash`/`grep`/`glob` 工具里各自 `import` 这个模块、独立判断"要不要走容器"的写法是一致的。第二,`atexit.register(session.stop_sync)` 是一条明确的安全网:如果进程异常退出(崩溃、被杀)、没有机会走到正常的 `close_runtime()` 清理路径,`atexit` 钩子会在解释器退出前尝试同步调用 `docker stop` 把容器清理掉,避免残留的沙箱容器在后台一直占着资源。这类"正常关闭路径 + 兜底清理路径"的双保险写法,在管理外部进程/容器生命周期的代码里是一个值得留意的惯用模式。

### 不是所有工具都会进容器

这是整篇文章里最容易被忽略、但对理解沙箱实际防护范围最关键的一点。`bash` 工具的执行路径(前面已经看过)会在 Docker 沙箱运行时把命令交给 `docker exec`;`grep`/`glob` 工具各自也在自己的实现里直接检查 `get_docker_sandbox()`,命中就走 `session.exec_command()`:

```python
# src/openharness/tools/grep_tool.py:195-212(节选,ripgrep 搜索路径)
from openharness.sandbox.session import get_docker_sandbox

session = get_docker_sandbox()
if session is not None and session.is_running:
    process = await session.exec_command(cmd, cwd=root, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
else:
    process = await asyncio.create_subprocess_exec(*cmd, cwd=str(root), ...)
```

`glob_tool.py` 里几乎一模一样的分支结构(同样是判断 `session is not None and session.is_running`,再决定走 `session.exec_command()` 还是本地 `asyncio.create_subprocess_exec()`)。但 `read_file`/`write_file`/`edit_file` 三个工具完全没有这条分支——它们从来不会把操作转交给容器,永远是 Python 自己的 `Path.read_text()`/`Path.write_text()` 直接对宿主机文件系统读写:

```python
# src/openharness/tools/file_write_tool.py:28-42(节选)
async def execute(self, arguments: FileWriteToolInput, context: ToolExecutionContext) -> ToolResult:
    path = _resolve_path(context.cwd, arguments.path)

    from openharness.sandbox.session import is_docker_sandbox_active

    if is_docker_sandbox_active():
        from openharness.sandbox.path_validator import validate_sandbox_path

        allowed, reason = validate_sandbox_path(path, context.cwd)
        if not allowed:
            return ToolResult(output=f"Sandbox: {reason}", is_error=True)
    ...
    path.write_text(arguments.content, encoding="utf-8")
```

`file_read_tool.py`、`file_edit_tool.py` 是同样的结构。这三个工具即便在 Docker 沙箱开启的情况下,依然是在 Agent 主进程里、以运行 OpenHarness 本身的那个操作系统用户身份,直接对宿主机文件系统做 I/O——容器提供的文件系统隔离(只挂载 `cwd`)对这三个工具完全不生效,因为它们压根没有经过 `docker exec`。这不是一个隐藏的漏洞,而是从代码结构上可以直接读出的架构现实:**Docker 沙箱这一层边界,只覆盖会被路由进容器执行的命令(`bash`、以及 `grep`/`glob` 在 ripgrep 可用时的快速路径),不覆盖直接走 Python 文件 I/O 的工具。**

这正是 `path_validator.py` 存在的理由——它是专门为这后一类"永远在宿主机上执行"的工具准备的第二道边界。

### `path_validator.py`:容器边界之外的第二道校验

```python
# src/openharness/sandbox/path_validator.py:8-37
def validate_sandbox_path(
    path: Path,
    cwd: Path,
    extra_allowed: list[str] | None = None,
) -> tuple[bool, str]:
    """Check whether *path* falls within the sandbox boundary.

    Returns ``(True, "")`` when the path is allowed, or ``(False, reason)``
    when it falls outside the permitted directories.
    """
    resolved = path.resolve()
    resolved_cwd = cwd.resolve()

    # Primary check: path must be within the project directory
    try:
        resolved.relative_to(resolved_cwd)
        return True, ""
    except ValueError:
        pass

    # Secondary: check extra allowed paths (from filesystem settings)
    for allowed in extra_allowed or []:
        allowed_path = Path(allowed).expanduser().resolve()
        try:
            resolved.relative_to(allowed_path)
            return True, ""
        except ValueError:
            continue

    return False, f"path {resolved} is outside the sandbox boundary ({resolved_cwd})"
```

实现思路很朴素:先对目标路径和 `cwd` 都调用 `Path.resolve()`,再用 `relative_to()` 判断目标是否落在 `cwd` 之内。`resolve()` 会展开 `..` 这类相对跳转,也会跟随符号链接解析出真实的最终路径,所以 `tests/test_sandbox/test_path_validator.py` 里 `test_dotdot_traversal_blocked`(用 `cwd / ".." / "secret.txt"` 构造路径穿越)和 `test_symlink_escape_blocked`(在 `cwd` 内放一个指向 `cwd` 外文件的符号链接)两个用例都能被正确拦下——`resolve()` 这一步是这两类绕过手法失效的关键,如果只做字符串层面的前缀比较,这两个用例都会被绕过。

它在三个文件工具里的接入方式完全一致:先判断 `is_docker_sandbox_active()`,只有 Docker 沙箱正在运行时才调用 `validate_sandbox_path()`。这意味着这层校验和 Docker 沙箱的启用状态是绑定的——如果沙箱没开启(前面提到,这是默认状态),文件读写工具的路径边界完全不受这个函数约束,只受上一篇讲的 `PermissionChecker` 里 `path_rules`/`SENSITIVE_PATH_PATTERNS` 约束,那是两套不同维度的规则(工具级别的允许/拒绝清单,而不是"是否落在项目目录内"的边界判断)。

函数签名里还留了一个 `extra_allowed` 参数,注释写的是"from filesystem settings"——对应的正是 `SandboxFilesystemSettings.allow_read`/`allow_write` 这些配置项。但通读三个调用点(`file_read_tool.py`、`file_write_tool.py`、`file_edit_tool.py`)会发现,它们调用 `validate_sandbox_path()` 时都只传了 `(path, context.cwd)` 两个位置参数,`extra_allowed` 始终是默认值 `None`。也就是说,`SandboxFilesystemSettings` 里配置的额外允许路径,目前只会被 `build_sandbox_runtime_config()` 转换后传给 `srt` 后端使用,并不会真正影响 Docker 沙箱场景下这三个文件工具的路径判断——`extra_allowed` 这个参数目前更像是为将来打通这条配置路径预留的接口,而不是已经生效的行为。这是读这部分代码时值得留意、也是容易被文档描述掩盖的一处配置项与实际实现之间的落差。

## 常见问题/易踩坑

**Docker 沙箱开着,是不是就意味着 Agent 完全碰不到 `cwd` 之外的宿主机文件?** 不一定。如果 Agent 只用 `bash` 执行命令,或者 `grep`/`glob` 命中了 ripgrep 快速路径,答案是"碰不到"——这些调用会被送进只挂载了 `cwd` 的容器。但如果 Agent 用 `read_file`/`write_file`/`edit_file` 直接操作路径,这三个工具从不经过容器,唯一的边界是 `path_validator.py` 对 `cwd` 的相对路径判断——这层判断本身是可靠的(能挡住 `..` 穿越和符号链接逃逸),但它是纯 Python 层面的应用逻辑校验,不是操作系统强制的边界,和 `bash` 工具那层由容器运行时保证的隔离,严格来说不是同一量级的防御。

**沙箱的网络策略里配置了 `allowed_domains`,为什么 Docker 后端下网络还是完全不通?** 前面已经引用过代码注释:这是有意为之的"宁可什么都不做,也不做半成品域名过滤"。`allowed_domains`/`denied_domains` 只对 `srt` 后端生效,Docker 后端目前的网络策略只有"完全断网"一种状态,配置这两个字段在 Docker 后端下只会触发一条警告日志,不会产生实际的选择性放行效果。

## 小结

沙箱要解决的是权限审批解决不了的问题:`PermissionChecker` 是进程内、靠代码逻辑配合的门,沙箱才是操作系统或容器运行时强制的边界。OpenHarness 实际存在两种沙箱后端——默认的 `srt`(依赖外部命令行工具,底层是 Linux 上的 bubblewrap、macOS 上的 sandbox-exec)和需要显式开启的 `docker`,二者的调度靠两处硬编码的字符串比较分流,没有统一的后端接口。Docker 后端的隔离范围很克制:文件系统只挂载 `cwd`,网络要么完全断开、要么完全断开(不支持选择性放行),这种"不做半成品"的取舍贯穿了整个实现。更值得记住的是,即便沙箱开着,也不是所有工具调用都会被送进容器——`bash` 和走 ripgrep 快速路径的 `grep`/`glob` 会,但 `read_file`/`write_file`/`edit_file` 永远直接操作宿主机文件系统,只受 `path_validator.py` 这一层基于 `cwd` 相对路径判断的应用层校验约束,这也解释了为什么这一层校验必须独立于容器边界之外单独存在。

到这里,治理与安全这一章讲完了 OpenHarness 如何决定"哪些操作需要经过谁的同意"(权限模式与审批流程)、以及"被允许执行的操作最终被限制在多大的边界里"(沙箱与路径校验)。下一章会转向另一个维度——Agent 如何在多轮对话、甚至跨会话之间保持连续性,也就是 CLAUDE.md/MEMORY.md 这类记忆文件的读写机制,以及 session resume 如何让一次中断的任务在下次启动时接着往下走。
