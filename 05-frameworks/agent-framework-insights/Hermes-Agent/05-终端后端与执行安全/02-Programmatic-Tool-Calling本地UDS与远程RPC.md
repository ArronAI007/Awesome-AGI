# Programmatic Tool Calling:本地 UDS 与远程文件轮询 RPC

> 一次"搜索 5 个结果、逐个抓取网页正文、按条件过滤、汇总输出"的任务,如果按常规工具调用来做,每一步的中间结果都要完整地回流进模型上下文,再由模型决定下一步——5 次工具调用就是 5 轮来回。Hermes 的 Programmatic Tool Calling(PTC,`execute_code` 工具)让模型直接写一段 Python 脚本,把这一整条流水线折叠成一次调用:脚本在子进程里跑,通过 RPC 回调父进程分发真正的工具调用,只有脚本最后 `print()` 的内容才会进入模型上下文。本篇通读 `tools/code_execution_tool.py`,把"本地走 Unix Domain Socket、远程走文件轮询"这套双轨 RPC 机制的真实实现过一遍。

## 学习目标

- 理解 PTC 要解决的问题:把"多步工具调用来回过一遍 LLM 上下文"的成本折叠成一次脚本执行 + 一次 `print()` 输出。
- 理解本地后端下的 UDS(Unix Domain Socket)RPC 通道具体怎么搭建、怎么通信。
- 理解远程后端(Docker/SSH/Modal/Daytona 等)下,因为没有直接的 socket 可达性,PTC 改用什么机制实现同样的"脚本调工具"效果。
- 弄清楚两条路径在哪一个判断点分叉,分叉的依据是什么。
- 理解 PTC 的安全边界:环境变量清洗、工具白名单、资源限额,这些约束是否随传输方式变化。

## 背景与设计动机

`execute_code` 工具本身的定位,`tools/code_execution_tool.py` 顶部的模块 docstring 写得很直接:

```python
# tools/code_execution_tool.py:1-29(节选)
"""
Code Execution Tool -- Programmatic Tool Calling (PTC)

Lets the LLM write a Python script that calls Hermes tools via RPC,
collapsing multi-step tool chains into a single inference turn.
...
In both cases, only the script's stdout is returned to the LLM; intermediate
tool results never enter the context window.

Platform: Linux / macOS only (Unix domain sockets for local). Disabled on Windows.
Remote execution additionally requires Python 3 in the terminal backend.
"""
```

产品文档(`website/docs/user-guide/features/code-execution.md`)给出的场景判据很具体:当一次任务里有"3+ 次工具调用、中间夹杂处理逻辑"、"批量数据过滤或条件分支"、"对结果做循环"这几类特征时,模型会选择用 `execute_code` 而不是一串独立的工具调用。一个典型脚本长这样:

```python
# website/docs/user-guide/features/code-execution.md:19-27
from hermes_tools import web_search, web_extract

results = web_search("Python 3.13 features", limit=5)
for r in results["data"]["web"]:
    content = web_extract([r["url"]])
    # ... filter and process ...
print(summary)
```

脚本里 `from hermes_tools import ...` 导入的并不是真正实现了搜索/抓取逻辑的模块,而是 Hermes 在执行前动态生成的一个 stub 模块——每个函数体都只是把参数打包、通过 RPC 发给父进程、再把父进程回传的结果原样返回。真正的"搜索""抓取"依然是父进程里那套标准工具实现在跑,子进程脚本只是一个编排层。

## 核心机制:两条传输,一份 stub 生成逻辑

`generate_hermes_tools_module()` 是两条路径共用的 stub 生成函数,靠一个 `transport` 参数决定注入哪种传输头:

```python
# tools/code_execution_tool.py:485-517(节选)
def generate_hermes_tools_module(enabled_tools: List[str],
                                 transport: str = "uds") -> str:
    """
    ...
    Args:
        enabled_tools: Tool names enabled in the current session.
        transport: ``"uds"`` for Unix domain socket (local backend) or
                   ``"file"`` for file-based RPC (remote backends).
    """
    ...
    if transport == "file":
        header = _FILE_TRANSPORT_HEADER
    else:
        header = _UDS_TRANSPORT_HEADER

    return header + "\n".join(stub_functions)
```

分叉点在 `execute_code()` 入口处,依据的正是当前生效的终端后端类型:

```python
# tools/code_execution_tool.py:1580-1615(节选)
# Dispatch: remote backends use file-based RPC, local uses UDS
from tools.terminal_tool import _get_env_config, _docker_has_host_access
_env_config = _get_env_config()
env_type = _env_config["env_type"]
...
if env_type != "local":
    return _execute_remote(code, task_id, enabled_tools, reset=bool(reset))

# --- Local execution path (UDS) --- below this line is unchanged ---
```

`env_type` 就是上一篇讲过的 `TERMINAL_ENV`/`terminal.backend`——同一套配置项,既决定 `terminal()` 工具连到哪个执行环境,也决定 PTC 走 UDS 还是文件轮询。只要终端后端不是 `local`,不管是 Docker、SSH 还是 Modal,一律走远程路径。

### 本地路径:Unix Domain Socket(Windows 上退化为回环 TCP)

本地路径下,父进程真正开一个 socket 服务端,子进程脚本连上去发请求:

```python
# tools/code_execution_tool.py:565-600(节选,_UDS_TRANSPORT_HEADER)
def _connect():
    """Connect to the parent's RPC server via the transport it picked.

    HERMES_RPC_SOCKET can be either:
      - a filesystem path (POSIX Unix domain socket — the default on
        Linux and macOS)
      - a string of the form ``tcp://127.0.0.1:<port>`` (Windows, where
        AF_UNIX is unreliable — the parent falls back to loopback TCP)
    """
    global _sock
    if _sock is None:
        endpoint = os.environ["HERMES_RPC_SOCKET"]
        if endpoint.startswith("tcp://"):
            _host_port = endpoint[len("tcp://"):]
            _host, _, _port = _host_port.rpartition(":")
            _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _sock.connect((_host or "127.0.0.1", int(_port)))
        else:
            _sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            _sock.connect(endpoint)
        _sock.settimeout(300)
    return _sock
```

每次调用把 `{"tool": ..., "args": ..., "token": ...}` 序列化成一行 JSON,通过 socket 发给父进程,父进程收到后走标准的 `handle_function_call` 分发,再把结果写回同一个连接:

```python
# tools/code_execution_tool.py:745-749(节选,_rpc_server_loop)
from model_tools import handle_function_call

if dispatch is None:
    def dispatch(tool_name, tool_args):
        return handle_function_call(tool_name, tool_args, task_id=task_id)
```

服务端用 `server_sock.settimeout(0.05)` 配合 `stop_event` 轮询 accept,单个连接内部按换行符切分多条 JSON 消息串行处理——协议里没有请求 ID,所以子进程侧的 `_call()` 用一把 `threading.Lock` 把"发送 + 等待响应"这一整个来回串行化,避免多线程脚本(比如 `ThreadPoolExecutor`)在共享 socket 上抢答彼此的响应。

模块级注释还解释了为什么 Windows 需要单独处理:AF_UNIX 在 Windows Python 上不够可靠,所以父进程在 Windows 上会退化成绑定一个回环地址的 TCP socket,子进程侧的 `_connect()` 通过 `HERMES_RPC_SOCKET` 是否以 `tcp://` 开头来分辨该用哪种 socket 族——这让 `execute_code` 在 Hermes 支持的所有平台上都可用,而不只是 Linux/macOS。

### 远程路径:没有直连 socket,改用"请求文件 + 响应文件"轮询

Docker、SSH、Modal 这类远程/容器后端,子进程脚本运行在一个和父进程网络不直通(或者根本没有暴露 socket 端口)的环境里,无法像本地那样直接连一个 TCP/UDS 地址。Hermes 的解法是把 RPC 降格成一套基于共享文件系统的轮询协议:

```python
# tools/code_execution_tool.py:662-693(节选,_FILE_TRANSPORT_HEADER 内的 _call)
def _call(tool_name, args):
    """Send a tool call request via file-based RPC and wait for response."""
    global _seq
    with _seq_lock:
        _seq += 1
        seq = _seq
    seq_str = f"{seq:06d}"
    req_file = os.path.join(_RPC_DIR, f"req_{seq_str}")
    res_file = os.path.join(_RPC_DIR, f"res_{seq_str}")

    tmp = req_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"tool": tool_name, "args": args, "seq": seq,
                    "token": os.environ.get("HERMES_RPC_TOKEN", "")}, f)
    os.rename(tmp, req_file)

    deadline = time.monotonic() + 300
    poll_interval = 0.05
    while not os.path.exists(res_file):
        if time.monotonic() > deadline:
            raise RuntimeError(f"RPC timeout: no response for {tool_name} after 300s")
        time.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.2, 0.25)
    ...
```

子进程脚本这一侧的逻辑是:把请求 JSON 先写到 `.tmp` 文件,再 `os.rename()` 成正式的 `req_{seq}` 文件(rename 在同一文件系统内是原子的,避免父进程读到半写文件),然后自旋轮询 `res_{seq}` 文件是否出现,轮询间隔从 50ms 指数退避到 250ms 封顶。

父进程这一侧对称地跑一个轮询线程,但它读写"远程文件系统"的手段,正是第一篇讲过的 `env.execute()`——也就是说,父进程是靠反复对同一个终端后端发 `ls`/`cat`/`echo | base64 -d`/`rm` 这些 shell 命令来完成"看远程目录里有没有新请求文件""读请求内容""写响应内容""清理请求文件"这一整套动作:

```python
# tools/code_execution_tool.py:1017-1036(节选,_rpc_poll_loop)
"""Poll the remote filesystem for tool call requests and dispatch them.

Runs in a background thread.  Each ``env.execute()`` spawns an
independent process, so these calls run safely concurrent with the
script-execution thread.
"""
...
ls_result = env.execute(
    f"ls -1 {quoted_rpc_dir}/req_* 2>/dev/null || true",
    cwd="/",
    timeout=10,
)
```

响应内容的回写用 base64 编码后拼进一条 `echo '...' | base64 -d > file.tmp && mv file.tmp file` 命令,注释里说明了原因:直接用 `env.execute()` 的 stdin 参数在 Modal 这类后端上不能可靠地把数据传给链式命令,所以改用"编码进命令行字符串"这种更朴素但兼容性更好的方式。

```python
# tools/code_execution_tool.py:1122-1133(节选)
# Write response atomically (tmp + rename).
# Use echo piping (not stdin_data) because Modal doesn't
# reliably deliver stdin to chained commands.
encoded_result = base64.b64encode(tool_result.encode("utf-8")).decode("ascii")
env.execute(
    f"echo '{encoded_result}' | base64 -d > {quoted_res_file}.tmp"
    f" && mv {quoted_res_file}.tmp {quoted_res_file}",
    cwd="/",
    timeout=60,
)
```

这条远程路径完全建立在"终端后端能执行 shell 命令"这一个能力之上,没有引入任何新的通信原语——它复用的正是第一篇里讲过的 `BaseEnvironment.execute()` 接口:每一次 `ls`/`cat`/写文件都是一次独立的 spawn-per-call 调用,和模型直接发一条 `terminal()` 命令没有本质区别,只是调用方从模型换成了这个轮询线程。这也解释了为什么远程执行"额外要求后端里有 Python 3"(见前面模块 docstring)——脚本本身仍然要在远程环境里用 Python 解释器跑起来,只是它和父进程之间的"打电话"方式从 socket 换成了共享文件系统上的请求/响应文件对。

## 两条路径共享的安全约束

不管走哪条传输,PTC 的安全边界是同一套,不随传输方式变化:

- **环境变量清洗**:子进程只拿到清洗过的最小环境,变量名包含 `KEY`/`TOKEN`/`SECRET`/`PASSWORD`/`CREDENTIAL`/`PASSWD`/`AUTH` 的一律剔除,只放行 `PATH`/`HOME`/`LANG` 等安全的系统变量,以及少数几个精确命名的 `HERMES_HOME`/`HERMES_PROFILE`/`HERMES_CONFIG`/`HERMES_ENV`。
- **工具白名单 + 调用次数上限**:脚本能调用的工具是 `SANDBOX_ALLOWED_TOOLS` 和当前会话 `enabled_tools` 的交集,默认每次执行最多 50 次工具调用,超限直接返回错误;`terminal()` 在脚本内被强制去掉 `background`/`pty` 等参数,只能前台跑。
- **资源限额**:5 分钟超时(SIGTERM 后 5 秒宽限 SIGKILL)、50KB stdout 截断、10KB stderr 保留用于调试。
- **执行前的批准闸门**:`execute_code` 跑的是任意 Python(可以直接 `subprocess`/`os.system`),不经过 `terminal()` 的 `DANGEROUS_PATTERNS` 检测,所以入口处专门接了一道 `tools.approval.check_execute_code_guard` 闸门,在两条分发路径之前统一拦截——下一篇会详细展开这套批准机制。

代码里把这段落地成一句注释:"Switching mode changes where scripts run and which interpreter runs them, not what credentials they can see or which tools they can call"——传输方式和执行模式(`project`/`strict`)只影响脚本"跑在哪、用哪个解释器",不影响它"能看到什么、能调用什么"这两条安全线。

## 小结与思考题

Programmatic Tool Calling 用一段可执行的 Python 脚本替代了"多步工具调用来回过一遍模型上下文"的旧模式:脚本在子进程里编排逻辑,真正的工具执行仍然发生在父进程,只有 `print()` 的最终结果会进入上下文。本地后端下这条 RPC 通道是一个真正的 Unix Domain Socket(Windows 上退化为回环 TCP);远程后端(Docker/SSH/Modal/Daytona 等)下没有直连 socket 的条件,于是改用"请求文件 + 响应文件"轮询协议,父进程侧仍然通过第一篇讲过的 `env.execute()` shell 调用去读写这些文件——两条路径共用同一套 stub 生成逻辑、同一套环境清洗/白名单/资源限额,区别只在"脚本怎么把一次调用送到父进程手里"这一层传输实现。

**验证范围说明**:本篇的双轨机制描述完全来自对 `tools/code_execution_tool.py`(2486 行,含 `_UDS_TRANSPORT_HEADER`/`_FILE_TRANSPORT_HEADER`/`_rpc_server_loop`/`_rpc_poll_loop`/`execute_code` 等函数)以及配套产品文档 `website/docs/user-guide/features/code-execution.md` 的直接阅读,原始调研摘要里"本地 UDS、远程文件轮询 RPC"这个猜测在源码中得到了逐字确认,包括分叉判据(`env_type != "local"`)、传输头选择(`generate_hermes_tools_module(transport=...)`)、以及远程轮询线程复用 `env.execute()` 的具体实现细节。没有找到需要调整框架的地方。

思考题:

1. 远程路径的响应文件轮询间隔从 50ms 指数退避到 250ms 封顶,而本地路径是真正阻塞在 socket 的 `recv()` 上。如果一个远程后端的单次 `env.execute()` 往返延迟本身就有几百毫秒(比如跨区域的云沙箱),这套轮询设计会带来什么样的额外开销?有没有办法进一步压缩?
2. 远程路径的请求/响应文件都落在同一个 `HERMES_RPC_DIR` 目录,靠序列号 `seq` 区分不同调用。如果同一个远程沙箱在同一时刻服务多个并发的 `execute_code` 调用(比如多个会话共享同一个持久化 Modal 沙箱),这套目录/序列号方案够用吗?需要补上什么隔离机制?
