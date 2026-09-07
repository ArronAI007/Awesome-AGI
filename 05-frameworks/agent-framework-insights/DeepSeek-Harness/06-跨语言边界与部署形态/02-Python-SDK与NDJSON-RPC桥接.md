# Python SDK 与 NDJSON-RPC 桥接

> dsh 的核心是一套 TypeScript/Node 实现的 Agent 运行时,但真实世界里想用它的人未必写 TypeScript——数据科学团队、有 Python 遗留系统的公司、只想在 Jupyter 里跑几行代码验证想法的用户,都需要一条不依赖 Node 生态知识的接入路径。`python/` 目录下的两个包(`deepseek-harness-sdk` 和 `deepseek-harness-runtime-bin`)就是这条路径的答案：一个用标准库 `subprocess` + NDJSON 实现的同步 RPC 客户端,加上一个把整个 Node 运行时打成单文件可执行程序、随 wheel 分发的"运行时载体"。本篇通读 `client.py` 的完整实现,拆解这套双向 RPC 协议的设计,并说明"打包成 exe"这件事到底解决了什么问题。

## 学习目标

- 理解 `python/sdk` 和 `python/sdk-runtime` 两个包的分工：一个是纯 Python 客户端库,一个是不含业务逻辑的可分发运行时载体。
- 搞清楚 NDJSON-RPC 协议的收发实现——独立读线程 + `queue.Queue` 做请求响应关联,而不是简单的"发一句等一句"。
- 理解"服务端可以反向发起请求"这一双向设计,和对应的 `next_request`/`respond`/`respond_error` 接口。
- 理解"按 session 树过滤通知"是客户端自己拼出来的能力,而不是服务端下发了一棵树。
- 理解"把整个 Node 运行时打成单文件 exe"这个打包思路解决的具体问题,以及 exe/node 两种运行时载体的选择逻辑。
- 把这套机制放进"dsh 的第三种消费形态"的坐标系里,和 Web Client、直接 npm 依赖两条路径做对比。

## 背景与设计动机

`python/README.md` 用一句话概括了这个子系统的定位：

```text
// python/README.md:5
Python packages for driving DeepSeek Harness as a subprocess. The client SDK
communicates with the bundled runtime over newline-delimited JSON-RPC on stdio.
```

"驱动一个子进程"——这决定了整个设计的基调:Python 侧不重新实现任何 Agent 逻辑,它只是通过 stdio 上的 NDJSON-RPC 协议,把已经完整实现好的 dsh Agent 运行时当作一个受控的子进程来操作。这和"把 dsh 移植到 Python"是完全不同的思路——移植意味着要在两个语言里维护两份行为一致的业务逻辑,而"驱动子进程"只需要维护一份 wire protocol 的实现。

要让这条路径对 Python 用户友好,还必须解决一个隐藏的门槛:运行时本身是用 TypeScript/Node 写的,而 Python 用户不该被要求"先装好 Node.js 环境"才能 `pip install` 一个包。`python/sdk-runtime` 包的存在就是为了消灭这个门槛——它把整个 Node 运行时打包成一个不依赖任何系统 Node 安装的单文件可执行程序,随 wheel 分发。

两个包的目录结构和职责边界：

```text
python/
├── README.md
├── development.md
├── sdk/                                    # deepseek-harness-sdk,模块名 deepseek_harness
│   ├── pyproject.toml
│   └── src/deepseek_harness/
│       ├── client.py     # HarnessClient:同步 JSON-RPC 客户端
│       ├── api.py        # DeepSeekHarness / Session:更高层的 turn 封装
│       ├── models.py     # 数据模型
│       └── errors.py     # 异常层级
└── sdk-runtime/                            # deepseek-harness-runtime-bin,模块名 deepseek_harness_runtime
    ├── hatch_build.py    # 自定义 hatchling 构建钩子
    ├── platforms.json    # 平台 tag 映射
    ├── package.json       # 纯依赖清单
    └── src/deepseek_harness_runtime/
        ├── __init__.py    # 运行时路径解析
        └── runtime/       # (gitignored,构建期注入)
```

## 核心机制详解

### 两个包的分工:客户端库 vs 运行时载体

`deepseek-harness-sdk`(`python/sdk`)是纯 Python 代码,不含任何编译产物,负责"怎么跟运行时进程说话"。`deepseek-harness-runtime-bin`(`python/sdk-runtime`)恰恰相反——它的 `package.json` 是一份**不含业务逻辑的纯依赖清单**,声明的是要打进最终可执行文件的插件集合：

```json
// python/sdk-runtime/package.json(节选)
{
  "name": "dsh-jsonrpc-agent-pkg",
  "description": "Dependency-only deploy root defining the executable and Python runtime closure; pnpm deploy materializes this manifest and node_modules.",
  "dependencies": {
    "@deepseek-ai/dsh-agent": "workspace:^",
    "@deepseek-ai/dsh-llm-deepseek": "workspace:^",
    "@deepseek-ai/dsh-session-persistence-jsonl": "workspace:^",
    "@deepseek-ai/dsh-session-checkpoint-policy": "workspace:^",
    "@deepseek-ai/dsh-tool-bash": "workspace:^",
    "@deepseek-ai/dsh-tool-bash-persistent": "workspace:^",
    "@deepseek-ai/dsh-terminal-bash": "workspace:^",
    "@deepseek-ai/dsh-fs-local": "workspace:^",
    "@deepseek-ai/dsh-sdk-jsonrpc-server": "workspace:^",
    "@deepseek-ai/dsh-sdk-jsonrpc-demo": "workspace:^"
  }
}
```

这份清单里能直接对应上素材里提到的每一类插件:agent core(`dsh-agent`)、DeepSeek 适配器(`dsh-llm-deepseek`)、JSONL 持久化(`dsh-session-persistence-jsonl`)、checkpoint 策略(`dsh-session-checkpoint-policy`)、本地 bash 工具(`dsh-tool-bash`/`dsh-tool-bash-persistent`/`dsh-terminal-bash`)、本地 fs provider(`dsh-fs-local`)、以及作为 stdio JSON-RPC serving 入口的 `dsh-sdk-jsonrpc-server`。这个 zero-config 组合在 `python/sdk-runtime/README.md` 里有更完整的描述：

```text
// python/sdk-runtime/README.md:27-29
This package checks in `runtime/cordis.yml` with the JSON-RPC serving entry,
agent core, a preloaded DeepSeek adapter, JSONL persistence, the explicitly
composed semantic checkpoint policy, local bash, and a local filesystem
provider for bounded workspace-instruction loading.
```

也就是说,`sdk-runtime` 包的产出不是"一段代码",而是"一整个已经组装好、可以直接跑的 dsh Agent 应用"——只是它的组装方式是通过 Cordis 插件组合(`cordis.yml`),而不是手写胶水代码。

### NDJSON-RPC 收发:独立读线程 + 每请求一个 Queue

`HarnessClient` 的文档字符串直接点明了协议性质：

```python
# python/sdk/src/deepseek_harness/client.py:37-38
class HarnessClient:
    """Synchronous JSON-RPC client for the DeepSeek Harness SDK runtime over stdio."""
```

启动子进程用的是标准库 `subprocess.Popen`,`stdin`/`stdout`/`stderr` 三个管道都单独打开：

```python
# python/sdk/src/deepseek_harness/client.py:63-85(节选)
def start(self) -> None:
    if self._proc is not None:
        return
    args = list(self.config.launch_args_override or self._default_launch_args())
    env = os.environ.copy()
    if self.config.env:
        env.update(self.config.env)
    self._inject_bundled_default_config(env)
    self._proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=None if self.config.cwd is None else str(Path(self.config.cwd).resolve()),
        env=env,
        bufsize=1,
    )
    self._start_reader_thread()
    self._start_stderr_thread()
```

写入侧用一把 `_write_lock` 保护对 `stdin` 的写入,每条消息就是"一行紧凑 JSON + 换行符"——这正是 NDJSON(Newline-Delimited JSON)的定义：

```python
# python/sdk/src/deepseek_harness/client.py:298-308
def _write_message(self, message: JsonObject) -> None:
    proc = self._proc
    if proc is None or proc.stdin is None:
        raise TransportClosedError("DeepSeek Harness runtime is not running")
    try:
        payload = json.dumps(message, separators=(",", ":")) + "\n"
        with self._write_lock:
            proc.stdin.write(payload)
            proc.stdin.flush()
    except Exception as exc:
        raise self._runtime_closed_error("Failed to write to DeepSeek Harness runtime") from exc
```

读取侧是一个独立的守护线程,逐行读取 `stdout`,每行解析成一个 JSON 对象后交给 `_handle_message` 分发：

```python
# python/sdk/src/deepseek_harness/client.py:318-334
def _reader_loop(self) -> None:
    proc = self._proc
    if proc is None or proc.stdout is None:
        return
    try:
        for line in proc.stdout:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._handle_message(message)
    except BaseException as exc:
        self._fail_waiters(exc)
    finally:
        self._fail_waiters(self._runtime_closed_error("DeepSeek Harness runtime stdout closed"))
```

`stderr` 则完全独立于协议之外,单开一个线程收集诊断日志(用 `deque(maxlen=400)` 只保留最近 400 行),供超时或连接关闭时拼进错误信息里：

```python
# python/sdk/src/deepseek_harness/client.py:336-341
def _stderr_loop(self) -> None:
    proc = self._proc
    if proc is None or proc.stderr is None:
        return
    for line in proc.stderr:
        self._stderr_lines.append(line.rstrip())
```

这个"stdout 只承载协议帧,stderr 只承载诊断信息"的分离原则,和本课程后面会讲到的 TypeScript 版通用 SDK(`packages/sdk/server`)是完全一致的约定——两边的 README 都强调过"部署方不能在 stdout 上叠加日志"。

### 请求-响应关联:uuid + 单容量 Queue,不是自增计数器

很多简易 RPC 客户端会用一个自增整数当请求 id,但 `HarnessClient` 选择了 `uuid.uuid4()`,并且给每个请求单独建一个 `maxsize=1` 的 `queue.Queue` 作为"专属信箱"：

```python
# python/sdk/src/deepseek_harness/client.py:228-246(节选)
def _request_raw(self, method, params=None, *, timeout_seconds=None, ...) -> JsonValue:
    request_id = str(uuid.uuid4())
    waiter: queue.Queue[JsonValue | BaseException] = queue.Queue(maxsize=1)
    with self._lock:
        self._responses[request_id] = waiter
    message: JsonObject = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    self._write_message(message)
    ...
    item = waiter.get(timeout=wait_timeout)
    ...
    if isinstance(item, BaseException):
        raise item
    return item
```

响应到达时,读线程按 `id` 从字典里弹出对应的 `waiter`,把结果(或包装成 `JsonRpcError` 的错误)塞进那个专属队列——发起请求的调用方线程原本正阻塞在 `waiter.get()` 上,会立刻被唤醒：

```python
# python/sdk/src/deepseek_harness/client.py:343-362(节选)
if isinstance(msg_id, (str, int)):
    with self._lock:
        waiter = self._responses.pop(str(msg_id), None)
    if waiter is None:
        return
    if isinstance(message.get("error"), dict):
        err = message["error"]
        waiter.put(JsonRpcError(_int_or_none(err.get("code")), str(err.get("message", "JSON-RPC error")), err.get("data")))
    else:
        waiter.put(message.get("result"))
    return
```

这个设计的好处是:多个请求可以真正并发地"挂起等待",互不干扰——每个请求只关心自己那个 `Queue`,不需要在一个共享的响应流里按顺序匹配,读线程的分发逻辑也不需要知道"当前有几个人在等"。

### 服务端主动 Notification:广播 + 订阅 + "session 树过滤"

这套协议不是单纯的"一问一答"。运行时进程会主动推送 notification(没有 `id`、只有 `method` 的消息),客户端支持多个订阅者并行监听。订阅接口非常直白——每次订阅生成一个独立的 `Queue`：

```python
# python/sdk/src/deepseek_harness/client.py:192-200
def subscribe_notifications(self, notification_filter=None) -> "NotificationSubscription":
    subscription_id = str(uuid.uuid4())
    notifications: queue.Queue[Notification | BaseException] = queue.Queue()
    with self._lock:
        self._notification_subscribers[subscription_id] = (notifications, notification_filter)
    return NotificationSubscription(self, subscription_id, notifications)

def subscribe_session_notifications(self, session_id: str) -> "NotificationSubscription":
    """Subscribe to a session and descendants discovered from subagent lifecycle edges."""
    return self.subscribe_notifications(self._notification_belongs_to_session_tree(session_id))
```

分发逻辑在 `_handle_message` 里,对每个订阅者跑一遍过滤器(`predicate`),命中就推进对应队列,一个没命中就落进兜底的全局队列：

```python
# python/sdk/src/deepseek_harness/client.py:363-384(节选)
if isinstance(method, str):
    params = message.get("params")
    notification = Notification(method=method, payload=params if isinstance(params, dict) else {})
    with self._lock:
        self._record_session_relationship_locked(notification)
        subscribers = list(self._notification_subscribers.items())
    delivered = False
    for subscription_id, (subscriber, predicate) in subscribers:
        matches = predicate is None or predicate(notification)
        if matches:
            subscriber.put(notification)
            delivered = True
    if not delivered:
        self._notifications.put(notification)
```

真正有意思的是"按 session 树过滤"这句话背后的实现——**服务端并没有下发一棵 session 树结构**,客户端是靠监听 `subagent.started` 这个通知,自己在本地拼出一张父子映射表：

```python
# python/sdk/src/deepseek_harness/client.py:460-472
def _record_session_relationship_locked(self, notification: Notification) -> None:
    if notification.method != "subagent.started":
        return
    parent_id = notification.payload.get("parentSessionId")
    child_id = notification.payload.get("childSessionId")
    if (isinstance(parent_id, str) and parent_id
        and isinstance(child_id, str) and child_id
        and parent_id != child_id):
        self._session_parents[child_id] = parent_id
```

过滤器本身沿着这张表往上查,判断某条通知是否属于目标 session 的后代：

```python
# python/sdk/src/deepseek_harness/client.py:474-504(节选)
def _notification_belongs_to_session_tree(self, session_id: str) -> NotificationFilter:
    def belongs(notification: Notification) -> bool:
        payload = notification.payload
        if notification.method in {"subagent.started", "subagent.finished"}:
            parent_id = payload.get("parentSessionId")
            if isinstance(parent_id, str) and self._session_is_descendant_of(parent_id, session_id):
                return True
            return payload.get("childSessionId") == session_id
        related_id = payload.get("sessionId")
        return isinstance(related_id, str) and self._session_is_descendant_of(related_id, session_id)
    return belongs

def _session_is_descendant_of(self, session_id: str, root_session_id: str) -> bool:
    current = session_id
    visited: set[str] = set()
    while current not in visited:
        if current == root_session_id:
            return True
        visited.add(current)
        parent = self._session_parents.get(current)
        if parent is None:
            return False
        current = parent
    return False
```

这个设计把"树结构的知情权"完全放在了客户端——服务端只需要老老实实广播每一条 `subagent.started`/`subagent.finished` 事件,携带 `parentSessionId`/`childSessionId` 就够了,不需要维护和同步任何"树快照"给客户端。对于一个可能随时因为子 Agent 创建/销毁而变化的树结构来说,这种"边沿事件驱动重建"比"服务端主动推送快照"要健壮得多。

### 服务端反向请求:`next_request` / `respond` / `respond_error`

普通的 JSON-RPC 客户端只会发请求、收响应,但这套协议里服务端也能主动发起带 `id` 的请求——`_handle_message` 一旦发现某条消息同时有 `id` 又有 `method`(区别于"只有 id"的响应和"只有 method"的通知),就判定这是一条服务端发来的反向请求,塞进专属队列：

```python
# python/sdk/src/deepseek_harness/client.py:343-351
def _handle_message(self, message: object) -> None:
    if not isinstance(message, dict):
        return
    msg_id = message.get("id")
    method = message.get("method")
    if isinstance(msg_id, (str, int)) and isinstance(method, str):
        params = message.get("params")
        self._requests.put(IncomingRequest(id=msg_id, method=method, payload=params if isinstance(params, dict) else {}))
        return
```

调用方用 `next_request()` 阻塞式取出这类请求,处理完之后用 `respond()`/`respond_error()` 把结果写回 stdin,完成一次由服务端发起、客户端应答的反向调用：

```python
# python/sdk/src/deepseek_harness/client.py:206-226
def next_request(self) -> IncomingRequest:
    item = self._requests.get()
    if isinstance(item, BaseException):
        raise item
    return item

def respond(self, request_id: str | int, result: JsonValue) -> None:
    self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result})

def respond_error(self, request_id: str | int, *, code: int, message: str, data: JsonValue | None = None) -> None:
    error: JsonObject = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    self._write_message({"jsonrpc": "2.0", "id": request_id, "error": error})
```

这条通路存在的意义是:运行时进程有时需要向外部世界"问一个问题"再继续往下走(比如某个工具执行前需要用户批准),而不是所有决策都能在服务端内部完成。双向协议让这种"服务端阻塞、等外部世界给答案"的模式成为可能,而不需要单独开一条反向连接。

### `_default_launch_args()`:三级优先级与零配置注入

`HarnessClient` 怎么知道该启动哪个可执行文件、传什么参数？优先级是"显式参数 > 环境变量(经由 `resolve_bundled_launch_args` 间接读取)> 自动只选生产 exe"：

```python
# python/sdk/src/deepseek_harness/client.py:424-436
def _default_launch_args(self) -> tuple[str, ...]:
    if self.config.runtime_bin is not None:
        return (self.config.runtime_bin,)
    if self.config.bridge_bin is not None:
        return (self.config.bridge_bin,)
    try:
        from deepseek_harness_runtime import resolve_bundled_launch_args
    except ImportError as exc:
        raise FileNotFoundError(
            "Unable to locate the bundled DeepSeek Harness SDK runtime. "
            "Install deepseek-harness-runtime-bin or set HarnessConfig.runtime_bin."
        ) from exc
    return resolve_bundled_launch_args()
```

`runtime_bin`/`bridge_bin` 任一显式给出就直接用它,完全跳过对 `deepseek_harness_runtime` 包的依赖——这是留给"想自己控制运行时二进制来源"的高级用户的逃生舱口。只有两者都没给,才会 `import deepseek_harness_runtime` 并调用它的 `resolve_bundled_launch_args()` 来解析打包好的路径。

配套的 `_inject_bundled_default_config` 只在"走打包运行时路径 && 尚未设置 `DSH_CORDIS_CONFIG`"时,才自动注入一份默认配置路径,让"零配置直接跑"成为可能：

```python
# python/sdk/src/deepseek_harness/client.py:438-454
def _inject_bundled_default_config(self, env: dict[str, str]) -> None:
    uses_bundled_runtime = (
        self.config.launch_args_override is None
        and self.config.runtime_bin is None
        and self.config.bridge_bin is None
    )
    if not uses_bundled_runtime or env.get("DSH_CORDIS_CONFIG"):
        return
    from deepseek_harness_runtime import bundled_default_config_path
    env["DSH_CORDIS_CONFIG"] = str(bundled_default_config_path())
}
```

`python/sdk/src/deepseek_harness/api.py` 在这套底层客户端之上封装了一层"turn"语义的高层 API——`DeepSeekHarness`(可复用的 SDK 实例,懒启动子进程)和 `Session`(一次对话会话)。`Session.run()` 内部就是订阅 `subscribe_session_notifications`,发出 `session_prompt`,然后循环读取通知直到看到本 session 的 `session.status == "idle"`：

```python
# python/sdk/src/deepseek_harness/api.py:132-183(节选)
with self.harness.client.subscribe_session_notifications(self.id) as subscription:
    message_id = self.harness.client.session_prompt(self.id, content_blocks, notification_subscription=subscription)
    received = False
    while True:
        notification = subscription.next()
        if not received:
            if not _is_inbox_receipt(notification, self.id, message_id):
                continue
            received = True
        collect(notification)
        if (notification.method == "session.status"
            and notification.payload.get("sessionId") == self.id
            and notification.payload.get("status") == "idle"):
            break
```

最简单的用法(`python/development.md` 给出的官方 smoke test):

```python
from deepseek_harness import DeepSeekHarness

with DeepSeekHarness() as harness:
    print(harness.run("say hi").final_response)
```

底层的 NDJSON-RPC 收发、session 树过滤、双向请求,全部被这一层"turn 封装"隐藏掉了。

### 把整个 Node 运行时打成单文件 exe:解决什么问题

如果 Python SDK 要求用户"先装 Node.js,再 `npm install` 运行时依赖",那这个包对纯 Python 团队就没有意义了。`deepseek_harness_runtime/__init__.py` 的模块 docstring 直接说明了两种运行时载体的存在原因：

```python
# python/sdk-runtime/src/deepseek_harness_runtime/__init__.py:1-20
"""Locate the bundled DeepSeek Harness SDK runtime shipped with this package.

Two runtime carriers coexist under ``runtime/``, both injected by the repo's
``scripts/build-exe-for-python-sdk.ts`` build (neither is checked into git):

- **exe (production)**: single-file Node executables named
  ``dsh-jsonrpc-agent-pkg-<platform>-<arch>`` (platform in {linux, macos}, arch in
  {x64, arm64}); macOS also uses a sibling ``-spawn-helper``. The target machine
  needs no Node installation.
- **node (dev-only)**: the full deploy closure under ``runtime/node/``
  (``package.json`` + ``node_modules/``), executed as ``node
  runtime/node/node_modules/@deepseek-ai/dsh-sdk-jsonrpc-demo/lib/packaged-bin.js`` on a
  system Node >= 22.19. It is the current checkout's source build, never
  selected automatically, and excluded from wheel/sdist distributions.
"""
```

"目标机器不需要装 Node"——这就是打包成单文件 exe 要解决的核心问题。构建脚本 `scripts/build-exe-for-python-sdk.ts` 用 `@yao-pkg/pkg --sea` 完成这件事：

```ts
// scripts/build-exe-for-python-sdk.ts:22-26
/** Default Node major; SEA mode requires at least Node 22. */
const DEFAULT_NODE_RANGE = 'node24'
/** Pinned for reproducible builds. */
const PKG_SPEC = '@yao-pkg/pkg@6.21.0'
const OUT_DIR = 'dist-exe'
```

打包这一步棘手的地方在于:dsh 的插件系统 Cordis 用的是运行时动态 bare-import(根据 `cordis.yml` 里声明的插件名字符串去 `require`),而 `pkg` 是靠静态分析扫描代码里出现的 `require`/`import` 调用来决定哪些文件要打进产物——这种运行时才知道名字的导入,静态分析天然扫不到。解决方式简单粗暴:把 `node_modules` 整棵树的常见文件类型都当资产打进去：

```ts
// scripts/build-exe-for-python-sdk.ts:36-50
/**
 * Whole-tree assets cover Cordis's runtime bare-package imports, which pkg's
 * static analysis cannot see. Package manifests are explicit because bare-name
 * resolution depends on them.
 */
const ASSET_GLOBS = [
  'package.json',
  'node_modules/**/*.js',
  'node_modules/**/*.cjs',
  'node_modules/**/*.mjs',
  'node_modules/**/package.json',
  'node_modules/**/*.json',
  'node_modules/**/*.node',
  'node_modules/**/*.wasm',
]
```

构建产物随后被复制进 Python 包目录,和 `platforms.json` 声明的可执行文件名一一对应：

```ts
// scripts/build-exe-for-python-sdk.ts:459-474(节选)
async syncToPythonRuntime(products: string[]): Promise<void> {
  const destDir = resolve(root, PYTHON_RUNTIME_DIR)
  await mkdir(destDir, { recursive: true })
  for (const path of products) {
    const destination = join(destDir, basename(path))
    await copyFile(path, destination)
    await chmod(destination, statSync(path).mode & 0o777)
  }
}
```

`platforms.json` 定义了三个平台的 wheel tag 与可执行文件名映射：

```json
// python/sdk-runtime/platforms.json
{
  "linux-x64": { "tag": "manylinux_2_28_x86_64", "executable": "dsh-jsonrpc-agent-pkg-linux-x64" },
  "linux-arm64": { "tag": "manylinux_2_28_aarch64", "executable": "dsh-jsonrpc-agent-pkg-linux-arm64" },
  "macos-arm64": { "tag": "macosx_14_0_arm64", "executable": "dsh-jsonrpc-agent-pkg-macos-arm64" }
}
```

`hatch_build.py` 里的自定义构建钩子会校验"这个平台目录下的文件,跟 `platforms.json` 声明的 `expected_files` 严格一致",并把 wheel 的 tag 强制设成平台专属值(而不是纯 Python 包默认的 `py3-none-any`)：

```python
# python/sdk-runtime/hatch_build.py:73-84(节选)
build_data["pure_python"] = False
build_data["infer_tag"] = False
build_data["tag"] = f"py3-none-{platform_tag}"
```

这意味着 `pip install deepseek-harness-runtime-bin` 时,pip 会根据当前机器的平台自动挑选对应的 wheel,里面已经内置了那个平台可用的单文件可执行程序——用户全程不需要知道这背后有一个 Node 运行时。

### exe 与 node 两种载体的选择逻辑

生产环境永远走 exe,但仓库贡献者在开发调试时可能想直接跑未编译的 TS 源码——`resolve_bundled_launch_args` 用一个"显式参数 > 环境变量 > 自动只选 exe"的优先级来处理：

```python
# python/sdk-runtime/src/deepseek_harness_runtime/__init__.py:96-116
def resolve_bundled_launch_args(mode: str | None = None) -> tuple[str, ...]:
    """
    Mode selection: the explicit ``mode`` argument wins, then the
    ``DSH_RUNTIME_MODE`` environment variable (``exe`` | ``node``), then
    automatic resolution. Automatic resolution finds the production exe ONLY —
    the dev-only node carrier must be selected explicitly so a production
    deployment can never silently ride on a source build.
    """
    selected = mode if mode is not None else os.environ.get(RUNTIME_MODE_ENV_VAR)
    if selected is None or selected == "exe":
        return (str(bundled_runtime_path()),)
    if selected == "node":
        return _node_launch_args()
    raise ValueError(f"unsupported DeepSeek Harness runtime mode {selected!r}: expected 'exe' or 'node'")
```

注释里那句"生产部署永远不能悄悄跑在源码构建上"是关键的安全边界——"自动模式只选 exe"这个规则,防止了"开发机上本该显式启用的 node 模式,被误配置带进生产环境"这种事故。`python/development.md` 也给出了贡献者切换到源码模式的两种方式：设置 `DSH_RUNTIME_MODE=node`,或者直接用 `launch_args_override=("./node_modules/.bin/tsx", "packages/examples/jsonrpc-demo/src/bin.ts")` 跑未构建的 TS 源码。

### 第三种消费形态:与 Host/Client、npm 依赖的对比

到这里可以把 dsh 的几种消费路径放进同一张坐标系里看：

- **Web Client**：浏览器通过 WebSocket 连接 Host 进程,消费的是本课程后面会讲的 Typert 生成的 RPC 契约——面向"人在浏览器里交互"的场景。
- **直接 npm 依赖**：TypeScript/Node 项目直接 `import` dsh 的包(`@deepseek-ai/dsh-agent` 等),在同一个进程空间内组装 Cordis 插件——面向"用 TS 写自己的 Agent 应用,并且愿意直接依赖 dsh 的包结构"的场景。
- **Python 子进程(本篇)**：完全不共享进程空间,不要求了解 dsh 的内部包结构,只需要认识 NDJSON-RPC 这一套 wire protocol——面向"用别的语言集成 dsh,又不想承担了解整个 Node 生态的成本"的场景。

三者的抽象层次依次降低耦合度、提高可移植性,但同时也依次降低了可定制的深度(直接 npm 依赖能定制到插件级别,Python 子进程只能通过协议暴露的那几个方法交互)。`packages/sdk`(TypeScript/任意语言都能用的通用 stdio JSON-RPC 协议)是这条"子进程驱动"路径在 Python 之外的等价物——下一篇会讲到,这套通用协议和 Python SDK 走的是同一种"黑盒驱动"思路,只是 Python SDK 多做了一层"把 Node 运行时打成单文件 exe"的分发优化。

## 常见问题/易踩坑

- **为什么用 uuid 而不是自增整数做请求 id？** 自增计数器要求单一的、有序的分配点,在多线程并发发请求的场景下需要额外加锁；`uuid.uuid4()` 天然无冲突,配合"每请求一个 Queue"的设计,完全不需要围绕 id 分配做同步。
- **`subscribe_session_notifications` 订阅的"树"是实时准确的吗？** 它依赖客户端已经收到过对应的 `subagent.started` 事件才能建立父子关系——如果订阅发生在某个子 session 已经存在、但客户端还没见过它的 `subagent.started` 通知之前,那条边暂时不会出现在本地映射表里。这是"事件驱动重建"模型的固有特性,不是 bug。
- **`respond`/`respond_error` 不调用会怎样？** 服务端很可能会一直阻塞等待这次反向请求的答复——具体行为取决于服务端对该请求是否设置了超时,但从协议设计角度看,`next_request()` 取出的每一条请求都应该被及时应答。
- **`DSH_RUNTIME_MODE=node` 能在生产环境用吗？** 设计上不建议——它是仅供仓库贡献者用的开发态载体,不会被自动模式选中,`platforms.json`/`hatch_build.py` 的校验也确保了 wheel 里不会误打包这条路径的产物。

## 小结

Python SDK 这一层解决的其实是两个层次的问题:协议层(怎么跨语言、跨进程地驱动一个 dsh Agent),和分发层(怎么让 Python 用户不需要关心 Node 生态就能装上这套运行时)。NDJSON-RPC 本身并不复杂——换行分隔的 JSON 消息,配合 `id`/`method` 两个字段的有无区分请求/响应/通知——但 `HarnessClient` 在这套简单协议之上叠加的"独立读线程 + 逐请求 Queue""session 树的本地重建""服务端反向请求"这几层设计,共同撑起了一个健壮的双向 RPC 客户端。而"打包成单文件 exe"这个看似只是构建脚本层面的选择,实际上是让整套机制能被 `pip install` 一步到位的关键——协议设计得再优雅,如果用户还要先学会装 Node,这条跨语言边界就没有真正被打通。
