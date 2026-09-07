# 双前端架构:Ink TUI 与 Textual 备用界面

> OpenHarness 的核心逻辑是纯 Python(`src/openharness/`),但用户实际敲命令后看到的主力交互界面,却是一个用 TypeScript/Ink/React 写的**独立子进程**——Python 后端和这个跨语言前端之间靠一条 stdin/stdout 上的 JSON 行协议对话。仓库里还躺着第二套完整实现:纯 Python、基于 Textual 的 `OpenHarnessTerminalApp`,共享同一套运行时契约(`RuntimeBundle`/`build_runtime`/`handle_line`),却不经过 CLI 的任何路径被调用到。这篇拆开这两套前端各自的定位,以及它们和 Python 后端对话的两种完全不同的方式——一种跨进程走协议,一种同进程共享对象。

## 学习目标

- 理解为什么 OpenHarness 作为 Claude Code 的"Python port",在终端 UI 这件事上选择了复刻 Claude Code 自己"用 Ink 写终端界面"的路径,而不是从零造一个纯 Python TUI。
- 读懂 `ui/react_launcher.py` 如何定位、按需安装、拉起 `frontend/terminal/` 这个 Node 子进程,以及为什么要绕开 `npm exec` 直接调用 `tsx` 二进制。
- 掌握 `ui/protocol.py` 定义的请求/事件模型,以及 `ui/backend_host.py` 里 `OHJSON:` 前缀行协议的具体实现。
- 从前端 `useBackendSession.ts` 的 `spawn` + `readline` 代码里,确认协议在双向两端是如何对称落地的。
- 认识 `ui/textual_app.py` 这个完整但当前未被 CLI 调度到的 Textual 实现,理解它和 React 前端共享的是同一个运行时契约而非同一套协议。

## 背景与设计动机

Claude Code 官方 CLI 的终端界面是用 [Ink](https://github.com/vadimdemedes/ink)——一个把 React 的声明式组件模型搬到终端上的库——写的。Ink 解决的是一个纯 Python TUI 库通常做不好的问题:**终端界面的增量 diff 渲染**。一次流式回复里,每一个 token 到达都可能触发局部重绘;一个工具调用展开、折叠、状态从"运行中"变成"完成",都需要精确地只重绘变化的那一小块区域,同时保证宽字符(中文、emoji)、多行内容、滚动区域在不同终端模拟器下的渲染不错位。React 的虚拟 DOM diff 模型天然适合表达"状态变了,声明新的 UI 树,框架自己算出最小重绘范围"这件事,而 Ink 把这套模型移植到了终端的 ANSI 转义序列层面——这是一条已经被 Claude Code 在生产环境里跑通、验证过的路径。

OpenHarness 的定位是"开源的 Python 版 Claude Code 复刻",它面临一个选择:要么用纯 Python 的 TUI 库(Textual、prompt_toolkit、Rich)重新实现一遍这套增量渲染逻辑,要么直接复刻 Claude Code 自己的技术路径——把 Ink/React 这部分原样搬过来,核心 Agent 逻辑留在 Python 里,两者之间用一条进程边界隔开。仓库选择了后者:`frontend/terminal/` 是一个独立的、用 `ink`/`react` 写成的 TypeScript 项目,`pyproject.toml` 里的依赖列表里没有任何前端库,`src/openharness/ui/` 里也没有重新发明一遍终端渲染引擎——它的角色是**拉起这个 Node 子进程,并通过一条自定义的行协议把 Agent 内部的事件流喂给它**。这不是"为了炫技而跨语言",而是承认了一个事实:终端 UI 的渲染质量这件事,Ink 已经有一套被验证过的解法,没有必要在 Python 生态里重新造轮子去够上同一个水平线。

## 核心机制详解

### 三种运行模式与它们各自的入口

`ui/app.py` 的 `run_repl` 是所有交互式会话的统一入口,它按 `backend_only` 参数分岔成两条完全不同的路径:

```python
# src/openharness/ui/app.py
async def run_repl(
    *,
    prompt: str | None = None,
    cwd: str | None = None,
    ...
    backend_only: bool = False,
    ...
) -> None:
    """Run the default OpenHarness interactive application (React TUI)."""
    if backend_only:
        await run_backend_host(
            cwd=cwd, model=model, max_turns=max_turns, effort=effort,
            base_url=base_url, system_prompt=system_prompt, api_key=api_key,
            api_format=api_format, api_client=api_client,
            restore_messages=restore_messages,
            restore_tool_metadata=restore_tool_metadata,
            enforce_max_turns=max_turns is not None,
            permission_mode=permission_mode,
        )
        return

    exit_code = await launch_react_tui(
        prompt=prompt, cwd=cwd, model=model, max_turns=max_turns,
        ...
    )
```

函数自己的 docstring 直接写明"Run the default OpenHarness interactive application (React TUI)"——**React TUI 是默认路径**,而 `--backend-only` 这个标志切换到的,是同一个 Python 进程以"纯协议后端"的身份运行,不拉起任何 Node 子进程,只在 stdin/stdout 上说 JSON。这两条路径不是互相替代的两种 UI 选择,而是**同一条链路的两端**:普通用户敲 `oh` 时走的是"前端路径"(`launch_react_tui`),它内部又会以 `--backend-only` 重新拉起一个 Python 子进程来跑真正的 Agent 逻辑——也就是说一次完整的交互会话,实际上是**两个 Python/Node 进程协作**的结果,而不是一个进程里既画 UI 又跑 Agent。

### `react_launcher.py`:如何定位并拉起前端子进程

`get_frontend_dir()` 要解决"这个前端项目的源码到底在哪"的问题,因为同一份代码在开发者的源码检出目录和 `pip install` 之后的安装目录里,物理位置完全不同:

```python
# src/openharness/ui/react_launcher.py
def get_frontend_dir() -> Path:
    """Return the React terminal frontend directory.

    Checks in order:
    1. Bundled inside the installed package (pip install)
    2. Development repo layout (source checkout)
    """
    # 1. Bundled inside package: openharness/_frontend/
    pkg_frontend = Path(__file__).resolve().parent.parent / "_frontend"
    if (pkg_frontend / "package.json").exists():
        return pkg_frontend

    # 2. Development repo: <repo>/frontend/terminal/
    repo_root = Path(__file__).resolve().parents[3]
    dev_frontend = repo_root / "frontend" / "terminal"
    if (dev_frontend / "package.json").exists():
        return dev_frontend

    return pkg_frontend
```

这里的关键伏笔在 `pyproject.toml` 的 `force-include` 配置——它把 `frontend/terminal/` 的 TypeScript **源码**(不是构建产物)原样塞进了 Python wheel:

```toml
# pyproject.toml
[tool.hatch.build.targets.wheel.force-include]
"frontend/terminal/package.json" = "openharness/_frontend/package.json"
"frontend/terminal/tsconfig.json" = "openharness/_frontend/tsconfig.json"
"frontend/terminal/src" = "openharness/_frontend/src"
```

也就是说 `pip install openharness-ai` 装下来的不只是 Python 代码,还有一份没有编译过的 TypeScript 源码目录 `openharness/_frontend/`。`launch_react_tui` 第一次运行时会检测 `node_modules` 是否存在,不存在就现场 `npm install`,然后用 `tsx`(一个可以直接运行 TypeScript 而不需要预编译的运行器)执行 `src/index.tsx`:

```python
# src/openharness/ui/react_launcher.py
async def launch_react_tui(...) -> int:
    frontend_dir = get_frontend_dir()
    ...
    if not (frontend_dir / "node_modules").exists():
        install = await asyncio.create_subprocess_exec(
            npm, "install", "--no-fund", "--no-audit", cwd=str(frontend_dir),
        )
        if await install.wait() != 0:
            raise RuntimeError("Failed to install React terminal frontend dependencies")

    env = os.environ.copy()
    env["OPENHARNESS_FRONTEND_CONFIG"] = json.dumps({
        "backend_command": build_backend_command(cwd=cwd or str(Path.cwd()), ...),
        "initial_prompt": prompt,
        "theme": _resolve_theme(),
    })
    tsx_cmd = _resolve_tsx(frontend_dir)
    process = await asyncio.create_subprocess_exec(
        *tsx_cmd, "src/index.tsx",
        cwd=str(frontend_dir), env=env,
        stdin=None, stdout=None, stderr=None,
    )
    return await process.wait()
```

这段代码里有两个值得注意的工程细节:

1. **不发行编译产物,现场用 `tsx` 跑源码**——OpenHarness 没有把前端预编译成 JS 再打包分发,而是把 TypeScript 源码和一个能直接运行它的运行器(`tsx`)一起分发,首次运行时装依赖。这牺牲了一点首次启动速度,换来的是不需要维护一套独立的前端构建/发布流水线——`npx tsc --noEmit` 只是 CI 里的类型检查,不产出任何要发布的构建产物。
2. **`_resolve_tsx` 绕开 `npm exec` 直接找二进制**——注释里解释了原因:在 Windows/WSL 上,`npm exec -- tsx` 这条调用链会派生出中间的 `cmd.exe`/shell 进程,这些中间进程会打断 TTY 的 stdin 继承,导致 Ink 的 `useInput`(依赖 raw-mode stdin 才能工作)失效。所以 `_resolve_tsx` 优先直接调用 `node_modules/.bin/tsx` 这个二进制文件,只有找不到时才退回 `npm exec`。这是一个"表面上等价的两种调用方式,实际在特定平台上会破坏交互性"的典型坑,值得在任何跨进程拉起交互式子进程的场景里留个心眼。

进程本身用 `stdin=None, stdout=None, stderr=None` 拉起——即继承父进程的三个标准流,让 Node 子进程直接接管终端。真正的数据交换发生在**这个子进程内部又拉起的第二个子进程**上,也就是下面的协议层。

### `protocol.py`:双向消息的结构化契约

前端到后端的请求和后端到前端的事件,都被定义成两个 Pydantic 模型,而不是拍脑袋的自由格式 JSON:

```python
# src/openharness/ui/protocol.py
class FrontendRequest(BaseModel):
    """One request sent from the React frontend to the Python backend."""

    type: Literal[
        "submit_line", "permission_response", "question_response",
        "list_sessions", "select_command", "apply_select_command",
        "interrupt", "shutdown",
    ]
    line: str | None = None
    command: str | None = None
    value: str | None = None
    request_id: str | None = None
    allowed: bool | None = None
    permission_reply: str | None = None
    answer: str | None = None
    images: list[FrontendImageAttachment] = Field(default_factory=list)


class BackendEvent(BaseModel):
    """One event sent from the Python backend to the React frontend."""

    type: Literal[
        "ready", "state_snapshot", "tasks_snapshot", "transcript_item",
        "compact_progress", "assistant_delta", "assistant_complete",
        "line_complete", "tool_started", "tool_completed", "clear_transcript",
        "modal_request", "select_request", "todo_update", "plan_mode_change",
        "swarm_status", "error", "shutdown",
    ]
    ...
```

`FrontendRequest` 的 8 种类型基本对应用户在终端里能做的全部动作:提交一行输入、回应权限弹窗、回答一个提问、列出历史会话、选中一个斜杠命令、应用一个选择结果、中断当前请求、关闭会话。`BackendEvent` 的 18 种类型则对应 Agent 内部状态机能对外广播的全部信号——从连接建立时的一次性 `ready` 快照,到流式文本的 `assistant_delta`、工具调用的 `tool_started`/`tool_completed`,再到多智能体协作时的 `swarm_status`。用 `Literal` 类型枚举 + Pydantic 校验把这份契约钉死,意味着任何一端发送了协议之外的字段组合,会在反序列化阶段就报错,而不是在前端渲染时才发现字段对不上。

`FrontendImageAttachment` 上还挂了字段校验器,直接把"图片必须带 `image/` 前缀的 media type"这条业务规则编码进了协议模型本身:

```python
# src/openharness/ui/protocol.py
class FrontendImageAttachment(BaseModel):
    media_type: str
    data: str
    source_path: str | None = None

    @field_validator("media_type")
    @classmethod
    def _validate_media_type(cls, value: str) -> str:
        if not value.startswith("image/"):
            raise ValueError("image attachment media_type must start with image/")
        return value
```

### `backend_host.py`:`OHJSON:` 前缀行协议

`ReactBackendHost` 是真正跑在第二层子进程里的类,它的通信原语只有两个:往 `stdout` 写一行带前缀的 JSON,以及从 `stdin` 逐行读 JSON。写的一端:

```python
# src/openharness/ui/backend_host.py
_PROTOCOL_PREFIX = "OHJSON:"

async def _emit(self, event: BackendEvent) -> None:
    log.debug("emit event: type=%s tool=%s", event.type, getattr(event, "tool_name", None))
    async with self._write_lock:
        payload = _PROTOCOL_PREFIX + event.model_dump_json() + "\n"
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            buffer.write(payload.encode("utf-8"))
            buffer.flush()
            return
        sys.stdout.write(payload)
        sys.stdout.flush()
```

读的一端跑在独立的 asyncio task 里,用 `asyncio.to_thread` 把阻塞的 `sys.stdin.buffer.readline()` 丢到线程池,避免卡住事件循环;权限回应、提问回应会被直接匹配进对应的 `asyncio.Future` 并 resolve 掉,不进入常规请求队列:

```python
# src/openharness/ui/backend_host.py
async def _read_requests(self) -> None:
    while True:
        raw = await asyncio.to_thread(sys.stdin.buffer.readline)
        if not raw:
            await self._request_queue.put(FrontendRequest(type="shutdown"))
            return
        payload = raw.decode("utf-8").strip()
        if not payload:
            continue
        try:
            request = FrontendRequest.model_validate_json(payload)
        except Exception as exc:
            await self._emit(BackendEvent(type="error", message=f"Invalid request: {exc}"))
            continue
        if request.type == "permission_response" and request.request_id in self._edit_approval_requests:
            future = self._edit_approval_requests[request.request_id]
            if not future.done():
                future.set_result(_edit_approval_reply_from_request(request))
            continue
        ...
        await self._request_queue.put(request)
```

这套协议的关键设计是**用一个固定前缀区分"结构化事件"和"其他任何写到 stdout 的东西"**——`OHJSON:` 前缀让前端可以安全地区分"这是后端主动发出的协议事件"还是"某个第三方库不小心往 stdout 打了一行日志"。反方向(stdin)则没有做前缀区分,因为 stdin 完全由前端子进程独占写入,不存在被污染的风险,直接逐行 `model_validate_json` 就够。

### 前端侧的对称实现:`spawn` + `readline`

`useBackendSession.ts` 这个 React Hook 是整条链路在前端的落点。它用 Node 的 `child_process.spawn` 拉起第二层的 `--backend-only` Python 子进程,再用内置的 `readline` 模块逐行监听 `stdout`:

```typescript
// frontend/terminal/src/hooks/useBackendSession.ts
const PROTOCOL_PREFIX = 'OHJSON:';

const child = spawn(command, args, {
    stdio: ['pipe', 'pipe', 'inherit'],
    env: process.env,
    detached: useDetachedGroup,
    windowsHide: true,
});

const reader = readline.createInterface({input: child.stdout});
reader.on('line', (line) => {
    if (!line.startsWith(PROTOCOL_PREFIX)) {
        queueTranscriptItem({role: 'log', text: line});
        return;
    }
    const event = JSON.parse(line.slice(PROTOCOL_PREFIX.length)) as BackendEvent;
    handleEvent(event);
});
```

`stdio: ['pipe', 'pipe', 'inherit']` 精确对应了协议的单向性:`stdin`/`stdout` 是管道(前端向后端发请求、从后端收事件),`stderr` 直接继承到父进程的终端(后端的日志和未捕获异常可以被人直接看到,不参与协议)。这一行本身也印证了前面提到的坑——`backend_command` 数组的第一个元素就是 `react_launcher.py` 里 `build_backend_command` 构造出的 `sys.executable -m openharness --backend-only ...`,前端不需要知道这个命令的任何细节,只需要把它当一个黑盒 `spawn` 起来。发请求的一端同样朴素:

```typescript
// frontend/terminal/src/hooks/useBackendSession.ts
const sendRequest = (payload: Record<string, unknown>): void => {
    const child = childRef.current;
    if (!child || child.stdin.destroyed) {
        return;
    }
    child.stdin.write(JSON.stringify(payload) + '\n');
};
```

至此整条链路闭合:`oh` → `launch_react_tui` 拉起 Node/`tsx` 子进程 → 该子进程读取 `OPENHARNESS_FRONTEND_CONFIG` 环境变量拿到 `backend_command` → `spawn` 出第二层 Python 子进程(`--backend-only`)→ 两个进程之间用 `OHJSON:` 前缀的 JSON 行协议双向通信。三层进程、两条边界、一份用 Pydantic/TypeScript 类型分别在两侧描述的对称协议。

### `ui/textual_app.py`:共享运行时契约,而非共享协议

仓库里还有一份完整的、独立测试覆盖的 Textual 实现——`OpenHarnessTerminalApp`。它的模块 docstring 写的是"Default Textual terminal UI for OpenHarness",但搜索整个仓库会发现 `cli.py` 里没有任何路径调用它,`run_repl` 也从未引用它,只有它自己的测试文件 `tests/test_ui/test_textual_app.py` 直接实例化和驱动它。也就是说,**它当前不在 `oh` 命令的任何调度路径上**——不存在 `--textual` 之类的 CLI 开关把用户导向这里。

真正值得研究的不是它有没有被调用,而是它和 React 前端**共享了什么、又各自独立实现了什么**。两者共享的是同一个运行时契约——`build_runtime`/`start_runtime`/`handle_line`/`close_runtime` 这四个函数和 `RuntimeBundle` 这个数据类:

```python
# src/openharness/ui/textual_app.py
from openharness.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime
```

```python
# src/openharness/ui/backend_host.py
from openharness.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime
```

`RuntimeBundle` 把一次会话需要的全部对象打包在一起——API 客户端、工具注册表、hook 执行器,以及**真正的 Agent 核心循环 `QueryEngine`**:

```python
# src/openharness/ui/runtime.py
@dataclass
class RuntimeBundle:
    """Shared runtime objects for one interactive session."""

    api_client: SupportsStreamingMessages
    cwd: str
    mcp_manager: McpClientManager
    tool_registry: ToolRegistry
    app_state: AppStateStore
    hook_executor: HookExecutor
    engine: QueryEngine
    ...
```

`ReactBackendHost` 消费这个 `RuntimeBundle` 的方式,是把它的流式事件(`StreamEvent` 及其子类型)一个个翻译成 `BackendEvent` 通过协议发出去;`OpenHarnessTerminalApp` 消费同一个 `RuntimeBundle` 的方式,是**直接在同一个 Python 进程里**订阅这些事件,把它们写进 Textual 的 `RichLog` 组件:

```python
# src/openharness/ui/textual_app.py
def _append_line(self, message: str) -> None:
    self.transcript_lines.append(message)
    self.query_one("#transcript", RichLog).write(message)
```

这就是两套前端的本质区别:**React 前端是跨进程消费者,靠一条自定义协议和后端对话**;**Textual 前端是同进程消费者,直接持有 `RuntimeBundle` 的引用,函数调用级别地驱动它**。前者的代价是要维护一份协议契约、一层进程管理、一个 Node 运行时依赖;换来的收益是可以复用 Ink 成熟的终端渲染能力。后者不需要 Node、不需要 `npm install`、不需要维护协议——`textual` 已经是 `pyproject.toml` 里的常规依赖(`textual>=0.80.0`)——但代价是要在 Python 生态里自己维护渲染质量。从代码现状看,`textual_app.py` 更像是这套跨进程架构定稿之前(或者作为未来"零 Node 依赖"路径预留)的一份完整备用实现:功能完整、测试覆盖完整,只是还没有被接入任何用户能触达的入口。这对于任何需要在无 Node.js 环境下运行 OpenHarness 的场景(比如极简的容器镜像、CI 沙箱),都是一条现成但尚未打通"最后一公里"的路径。

## 常见问题/易踩坑

- **不要假设 `oh` 默认走的是同进程渲染**:实际是三层进程(Node 前端 → Python 后端子进程),`ps` 命令下会看到两个独立的 `openharness` 相关进程同时存在,这是设计如此,不是资源泄漏。
- **改协议时要同步改两侧的类型定义**:`ui/protocol.py` 的 Pydantic 模型和 `frontend/terminal/src/types.ts` 里的 TypeScript 类型没有代码生成关联,是手工保持同步的,增删字段容易漏改一侧。
- **`textual_app.py` 目前是孤立代码,不代表它已废弃**:它有独立的测试文件且逻辑完整,只是没有被 CLI 调度到;贸然删除或大改会破坏一条潜在的"无 Node 依赖运行"路径,改动前建议先确认它在项目路线图里的定位。

## 小结

OpenHarness 把"终端 UI 渲染质量"和"Agent 核心循环"拆成了两个进程、两种语言:核心逻辑留在 Python 里,交互界面复刻 Claude Code 自己验证过的 Ink/React 技术路径,靠一条 `OHJSON:` 前缀的 JSON 行协议在 stdin/stdout 上双向通信,协议契约在 Python 侧用 Pydantic、TypeScript 侧用类型定义分别对称描述。`textual_app.py` 则展示了同一套运行时契约(`RuntimeBundle`)可以撑起完全不同的消费方式——同进程直接调用,不需要协议、不需要 Node,只是目前还没有被接入 CLI 的调度路径。下一篇转向另一个维度:OpenHarness 的配置和路径解析体系——`~/.openharness/` 这个目录到底存了什么、`settings.json` 的加载优先级是怎样的、以及 provider profile 这套多供应商切换机制是如何设计的。
