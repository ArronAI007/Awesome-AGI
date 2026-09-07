# 四种前端与共享 JSON-RPC 网关协议

> Hermes Agent 同时维护着四种界面：`prompt_toolkit` 写的经典 CLI、Ink（React）写的现代 TUI、Web Dashboard 里内嵌的一块终端、以及一个完全独立的 Electron 桌面聊天应用。表面上是"四套 UI"，实际上是"一套核心 + 一份 JSON-RPC 协议 + 两种消费方式"：Dashboard 选择把真正的 `hermes --tui` 进程整个搬进浏览器，Electron 应用则反其道而行之，自己重新实现了一整套聊天界面并直接对话协议本身。本文从 `AGENTS.md`、`tui_gateway/`、`ui-tui/`、`hermes_cli/pty_bridge.py`、`apps/desktop/` 的真实代码出发，讲清楚这四种前端各自的定位和背后的协议设计。

## 学习目标

- 弄清楚 Hermes 四种前端界面（经典 CLI、Ink TUI、Dashboard 内嵌 PTY、Electron 桌面应用）各自的技术形态与产品定位，不再混淆。
- 理解 `ui-tui`（Node/Ink）与 `tui_gateway`（Python）之间"谁画屏幕、谁管会话"的职责划分，以及两者通过 stdio 上换行分隔 JSON-RPC 通信的协议形状。
- 读懂 `tui_gateway/server.py` 里请求/事件两种消息的真实 schema，能照着 `GatewayEvent` 联合类型定位任意一种事件的 payload 结构。
- 理解"Dashboard 为什么选择嵌入真正的 PTY 进程，而不是用 React 重写一遍聊天体验"这个设计决策解决的具体问题。
- 理解 Electron 桌面应用为什么反而是完全独立实现，以及它是如何绕开 Dashboard 前端、只依赖 `tui_gateway` 后端协议的。
- 能够复述 slash 命令在四种前端之间是如何共享同一份 `COMMAND_REGISTRY`、又在桌面端做了怎样的二次裁剪。

## 一、四种前端，四种定位

`AGENTS.md` 里"TUI Architecture"一节开篇就把关系挑明了：

> The TUI is a full replacement for the classic (prompt_toolkit) CLI, activated via `hermes --tui` or `HERMES_TUI=1`.

也就是说，这四种前端并不是并列的四个独立产品，而是有清晰的历史与依赖层次：

| 前端 | 技术形态 | 定位 |
|---|---|---|
| 经典 CLI | Python，`cli.py` 里的 `HermesCLI` 类，用 Rich 画面板/Banner、`prompt_toolkit` 做带自动补全的输入 | `hermes` 默认交互模式，本课程第 1 章已经用过 |
| Ink TUI | TypeScript（`ui-tui/`，Node + React + Ink）+ Python（`tui_gateway/`） | 经典 CLI 的"全量替代品"，`hermes --tui` 启动 |
| Dashboard 内嵌 PTY | `hermes_cli/pty_bridge.py` + `web/src/pages/ChatPage.tsx`（xterm.js） | 浏览器里的聊天标签页，本质是把 Ink TUI 的终端画面通过 WebSocket 转播 |
| Electron 桌面应用 | `apps/desktop/`，Electron + React + `@assistant-ui/react` | 完全独立的第三套聊天 UI，只对接 `tui_gateway` 的 JSON-RPC 协议本身 |

`AGENTS.md`（`## CLI Architecture (cli.py)`）里对经典 CLI 的描述很简洁：Rich 负责静态展示（banner/panels），`prompt_toolkit` 负责带自动补全的输入循环，`KawaiiSpinner`（`agent/display.py`）在等待模型响应时画动画表情。这是这个项目最早的界面形态，也是 TUI 出现之前唯一的交互方式。

## 二、Ink TUI 与 tui_gateway：进程模型与传输协议

`AGENTS.md` 用一张 ASCII 图把 TUI 的进程结构画得很直白：

```
hermes --tui
  └─ Node (Ink)  ──stdio JSON-RPC──  Python (tui_gateway)
       │                                  └─ AIAgent + tools + sessions
       └─ renders transcript, composer, prompts, activity

TypeScript owns the screen. Python owns sessions, tools, model calls, and slash command logic.
```

这是一个很干脆的职责划分：屏幕上"这一帧长什么样"完全交给 TypeScript/Ink，而"发生了什么"（工具调用、模型流式输出、会话生命周期、slash 命令解析）完全留在 Python 一侧——`ui-tui` 从不直接调用模型 API 或触碰工具执行逻辑，它只是协议的消费端。

`ui-tui/README.md` 把子进程的拉起过程写得更具体：客户端入口 `src/entry.tsx` 检测 `stdin` 是不是 TTY，然后启动 `GatewayClient`，后者会 spawn：

```text
python -m tui_gateway.entry
```

Python 解释器的解析顺序是 `HERMES_PYTHON` → `PYTHON` → `$VIRTUAL_ENV/bin/python` → `./.venv/bin/python` → `./venv/bin/python` → `python3`（Windows 上退到 `python`），这段逻辑在 `ui-tui/src/gatewayClient.ts` 的 `resolvePython()` 里实现，本质是"monorepo 里找到正确 Python 解释器"这个通用问题的一次具体实现。

### 传输格式：换行分隔 JSON-RPC

`AGENTS.md` 明确写道：

> Newline-delimited JSON-RPC over stdio. Requests from Ink, events from Python. See `tui_gateway/server.py` for the full method/event catalog.

真实的帧格式在 `tui_gateway/server.py` 里就是三种普通的 JSON-RPC 2.0 消息：

```python
# tui_gateway/server.py
def _ok(rid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}

def _err(rid, code: int, msg: str, data=None) -> dict:
    error = {"code": code, "message": msg}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": error}

def _event_frame(event: str, sid: str, payload: dict | None = None) -> dict:
    params: dict = {"type": event, "session_id": sid}
    if payload is not None:
        params["payload"] = payload
    return {"jsonrpc": "2.0", "method": "event", "params": params}
```

请求-响应走标准的 `id`/`result`/`error` 三段式；服务端主动推送的通知则统一套壳成 `method: "event"`，真正的事件类型和数据放进 `params.type`/`params.payload`。方法处理器用一个极简的注册装饰器收集：

```python
# tui_gateway/server.py
def method(name: str):
    def dec(fn):
        _methods[name] = fn
        return fn
    return dec

# 使用方式
@method("ping")
def _ping(...): ...

@method("wake.start")
def _wake_start(...): ...
```

Ink 一侧的请求发送逻辑对称地简单，`ui-tui/src/gatewayClient.ts` 里 stdio 模式下就是拼一个 JSON 对象、写一行、加换行符：

```typescript
// ui-tui/src/gatewayClient.ts
this.proc!.stdin!.write(JSON.stringify({ id, jsonrpc: '2.0', method, params }) + '\n')
```

值得一提的是 `gatewayClient.ts` 不止支持 spawn 子进程这一种模式，还支持通过 `HERMES_TUI_GATEWAY_URL`/`HERMES_TUI_SIDECAR_URL` 直接以 WebSocket 方式"attach"到一个已经在运行的网关（`requestOverWebSocket()`），这为后面 Dashboard 和 Electron 复用同一套协议埋下了伏笔——JSON-RPC 的方法和事件 payload 是同一套 schema，只是传输载体从 stdio 换成了 WebSocket。

### 事件 schema：`GatewayEvent` 联合类型

`ui-tui/src/gatewayTypes.ts` 里的 `GatewayEvent` 是一个巨大的可辨识联合类型（discriminated union），列出了网关会推送的每一种事件及其 payload 形状，可以直接当成协议文档来读：

```typescript
// ui-tui/src/gatewayTypes.ts
export type GatewayEvent =
  | { payload?: { heartbeat?: boolean; skin?: GatewaySkin }; session_id?: string; type: 'gateway.ready' }
  | { payload?: { text?: string }; session_id?: string; type: 'thinking.delta' }
  | {
      payload: { args_text?: string; context?: string; name?: string; tool_id: string; todos?: unknown[] }
      session_id?: string
      type: 'tool.start'
    }
  | {
      payload: {
        duration_s?: number; error?: string; inline_diff?: string; name?: string;
        result_text?: string; summary?: string; tool_id: string; todos?: unknown[]
      }
      session_id?: string
      type: 'tool.complete'
    }
  | {
      payload: { allow_permanent?: boolean; choices?: string[]; command: string; description: string; smart_denied?: boolean }
      session_id?: string
      type: 'approval.request'
    }
  | { payload: { rendered?: string; text?: string }; session_id?: string; type: 'message.delta' }
  // ... 还有 clarify.request / sudo.request / secret.request / subagent.* /
  //     voice.* / wake.detected / moa.* 等数十种事件类型
```

对照 `AGENTS.md` 给出的"关键界面"表，可以把界面组件和协议方法一一连起来：

| 界面表现 | Ink 组件 | 网关方法/事件 |
|---|---|---|
| 对话流式输出 | `app.tsx` + `messageLine.tsx` | `prompt.submit` → `message.delta`/`complete` |
| 工具执行动态 | `thinking.tsx` | `tool.start`/`progress`/`complete` |
| 审批弹窗 | `prompts.tsx` | `approval.respond` ← `approval.request` |
| 澄清/sudo/密钥 | `prompts.tsx`、`maskedPrompt.tsx` | `clarify`/`sudo`/`secret.respond` |
| 会话选择器 | `sessionPicker.tsx` | `session.list`/`resume` |
| Slash 命令 | 本地处理 + fallthrough | `slash.exec` → `_SlashWorker`、`command.dispatch` |
| 自动补全 | `useCompletion` hook | `complete.slash`、`complete.path` |
| 主题 | `theme.ts` + `branding.tsx` | `gateway.ready` 携带皮肤数据 |

这张表本身就是"协议驱动 UI"的一个范例：Ink 侧几乎不需要理解业务逻辑，只需要知道某个事件类型对应哪个组件该重新渲染。

### Slash 命令的两级路由

`AGENTS.md` 描述的 slash 命令流程是一个典型的"本地快速路径 + 远程兜底"设计：

> 1. Built-in client commands (`/help`, `/quit`, `/clear`, `/resume`, `/copy`, `/paste`, etc.) handled locally in `app.tsx`
> 2. Everything else → `slash.exec` (runs in persistent `_SlashWorker` subprocess) → `command.dispatch` fallback

纯客户端行为（清屏、退出、复制粘贴这类不需要 Python 参与的操作）直接在 Ink 里处理，其余命令通过 `slash.exec` 交给一个常驻的 `_SlashWorker` 子进程执行，执行不了的再落到 `command.dispatch` 统一分发。这条链路和第 3 章讲过的 `hermes_cli/commands.py` 里的 `COMMAND_REGISTRY` 是同一份数据源——同一个 `CommandDef` 列表，同时驱动经典 CLI 的 `process_command()`、网关的 `GATEWAY_KNOWN_COMMANDS`、Telegram/Slack 的命令菜单，以及这里的 TUI slash 分发，"加一个别名只需要改一处"的可维护性收益贯穿了所有前端。

## 三、Dashboard 为什么嵌入真正的 PTY，而不是重写聊天界面

Dashboard（`hermes dashboard` → `/chat` 标签页）本可以像很多 Web 聊天产品一样，用 React 组件重新实现一遍对话气泡、输入框、工具调用展示。但 `AGENTS.md` 明确否决了这条路：

> The dashboard embeds the real `hermes --tui` — **not** a rewrite. See `hermes_cli/pty_bridge.py` + the `@app.websocket("/api/pty")` endpoint in `hermes_cli/web_server.py`.

具体机制是：浏览器端 `web/src/pages/ChatPage.tsx` 挂载 xterm.js 的 `Terminal`（WebGL 渲染 + `@xterm/addon-fit` 自适应容器尺寸 + `@xterm/addon-unicode11` 支持宽字符），`/api/pty?token=...` 升级成 WebSocket 后，服务端通过 `ptyprocess` 拉起一个真正的 `hermes --tui` 子进程，两个方向上传输的都是原始 PTY 字节。`hermes_cli/pty_bridge.py` 里的 `PtyBridge` 类把这套机制包成了一个很小的接口：

```python
# hermes_cli/pty_bridge.py
"""PTY bridge for `hermes dashboard` chat tab.

Wraps a child process behind a pseudo-terminal so its ANSI output can be
streamed to a browser-side terminal emulator (xterm.js) and typed
keystrokes can be fed back in.
"""

@classmethod
def spawn(cls, argv, *, cwd=None, env=None, cols=80, rows=24) -> "PtyBridge":
    ...
    proc = ptyprocess.PtyProcess.spawn(
        list(argv), cwd=cwd, env=spawn_env, dimensions=(rows, cols),
    )
    return cls(proc)

def read(self, timeout: float = 0.2) -> Optional[bytes]:
    """Read up to 64 KiB of raw bytes from the PTY master."""
    ...

def resize(self, cols: int, rows: int) -> None:
    """Forward a terminal resize to the child via TIOCSWINSZ."""
    ...
```

模块顶部的 docstring 直接点出了这个设计换来的收益：

> The browser talks to the same `hermes --tui` binary it would launch from the CLI, so every TUI feature (slash popover, model picker, tool rows, markdown, skin engine, clarify/sudo/approval prompts) ships automatically.

这正是"一套后端实现，避免维护两套渲染逻辑"的直接体现——resize 时甚至专门处理了 WSL2 环境下 xterm.js 可能探测出 `columns=131072` 这种畸形尺寸的边界情况（`_clamp_dimension()` 把宽高限制在 `_MAX_COLS=2000`/`_MAX_ROWS=1000` 内，避免 `struct.pack("HHHH", ...)` 因为超出 unsigned short 范围而抛错）。

`AGENTS.md` 把这条规则说得更重：

> **Do not re-implement the primary chat experience in React.** The main transcript, composer/input flow (including slash-command behavior), and PTY-backed terminal belong to the embedded `hermes --tui` — anything new you add to Ink shows up in the dashboard automatically. If you find yourself rebuilding the transcript or composer for the dashboard, stop and extend Ink instead.

但这不是禁止 Dashboard 有任何 React UI——"structured React UI around the TUI is allowed when it is not a second chat surface"：侧边栏、模型选择弹窗（`ModelPickerDialog`）、工具调用检查器（`ToolCall`）这类辅助面板可以用 React 写，只要它们的状态和 PTY 子进程的会话状态相互独立，出问题时不会拖垮终端本身。

## 四、Electron 桌面应用：为什么反而要独立实现

如果说 Dashboard 的选择是"复用 UI"，那 Electron 桌面应用做的是完全相反的选择。`AGENTS.md`：

> A **separate** chat surface from both the classic CLI and the dashboard's embedded TUI. It is an Electron + React + nanostore renderer (`@assistant-ui/react`) that talks to a `tui_gateway` backend over JSON-RPC (`requestGateway(method, params)`)... It does NOT embed `hermes --tui` — it has its own composer, transcript, and slash-command pipeline.

原因在于两者的产品形态天差地别：Dashboard 是"浏览器里的一个终端窗口"，本质仍然是终端体验，PTY 转播刚好合适；Electron 应用要做的是原生桌面聊天应用的观感（沉浸式的消息气泡、拖拽附件、系统托盘、通知中心集成等），这些交互没有办法通过转播一段 ANSI 字符流实现——PTY 里的文字终究还是文字，做不出真正的原生控件。于是桌面应用选择直接对话协议本身：跳过 TypeScript/Ink 这一层，用自己的 React 组件树消费同一套 `tui_gateway` JSON-RPC 事件。

这也解释了为什么协议要传输结构化事件（`GatewayEvent` 那份联合类型）而不是渲染好的字符串——正是因为协议本身与渲染方式解耦，同一个 `tool.start`/`message.delta` 事件才能同时驱动"Ink 画终端字符画"和"Electron 画一个原生的工具调用卡片"两种截然不同的呈现。

传输层被抽成了一个框架无关的共享包：

> The WebSocket/JSON-RPC transport lives in the framework-agnostic `apps/shared` package (`@hermes/shared` — `JsonRpcGatewayClient` + WS URL helpers), which the web dashboard (`web/`) also consumes; **desktop has no build/runtime dependency on the dashboard frontend**.

`apps/shared/src/json-rpc-gateway.ts` 导出的 `JsonRpcGatewayClient` 和 `JsonRpcGatewayError` 是这份协议在浏览器端/Electron 渲染进程里的通用实现，Dashboard 的 Web 前端和桌面应用各自持有一份连接，互不依赖。桌面应用启动的后端也不是给浏览器用的 `dashboard` 子命令，而是一个更"瘦"的 `hermes serve`——`AGENTS.md` 解释说 `serve` 设置 `headless_backend=True`，跳过 `_build_web_ui` 并导出 `HERMES_SERVE_HEADLESS=1` 让 `mount_spa()` 彻底不挂载 SPA，只留 JSON-RPC/WS/API 这一层可达。为了兼容尚未升级的旧运行时，`electron/backend-command.ts` 里的 `backendSupportsServe()` 会探测目标运行时是否注册了 `serve` 命令，探测不到时才退回旧的 `dashboard --no-open`——这是一条纯粹的向后兼容 fallback，不是常态路径。

桌面应用自己的 slash 命令面板则是"后端全量提供 + 前端按展示需要裁剪"的模式：`tui_gateway/server.py` 的 `commands.catalog`/`complete.slash` 已经把内置命令、用户 `quick_commands`、以及技能派生命令一并暴露出来，桌面端不需要新增 RPC；真正的工作在 `apps/desktop/src/lib/desktop-slash-commands.ts` 里，用 `DESKTOP_COMMAND_SPECS` 和 `NO_DESKTOP_SURFACE` 黑名单把"终端专属/消息平台专属"的命令从桌面弹出面板里剔除，但 `isDesktopSlashExtensionCommand()` 保证任何非内置的扩展命令（技能、快捷命令）始终会流入建议列表——裁剪的对象是噪音，不是用户自己激活的扩展。

## 小结与思考题

- 四种前端不是四份平行实现，而是一条"经典 CLI → Ink TUI 全量替换 → Dashboard 转播 TUI → Electron 直连协议"的演化链：前两者共享 Python 侧的会话/工具/模型调用逻辑，Dashboard 复用的是 Ink 渲染出的终端字节流，只有 Electron 应用真正独立实现了一整套 UI。
- `tui_gateway` 暴露的 JSON-RPC 协议（换行分隔的 stdio 帧，`GatewayEvent` 联合类型描述的事件 payload）是让这条演化链成立的关键：协议与渲染解耦，才能让同一套事件同时驱动终端字符画和原生 React 组件。
- Dashboard 选择"嵌入真 PTY"而非"重写聊天 UI"，本质是用一次工程投入（PTY 转播 + xterm.js）换掉了维护两套渲染逻辑的长期成本；Electron 选择"完全独立实现"，则是因为原生桌面交互的产品诉求本来就无法通过转播字符流达成。
- 和 PI 课程《差分渲染架构与组件模型》一文对比会看得更清楚：PI 只有一个 TUI 实现（`packages/tui`），差分渲染解决的是"同一个进程内如何高效地把一帧画到终端"；Hermes 这里的核心矛盾则是"同一份后端协议，如何让多个完全独立的前端进程各自消费"——前者是单机渲染优化问题，后者是分布式协议设计问题。

思考题：

1. `GatewayEvent` 联合类型里几乎每个事件都携带可选的 `session_id`。如果 Electron 应用要同时维持多个并发会话（多标签页），而 Ink TUI 一次只服务一个会话，这个字段在两种消费者眼里分别扮演什么角色？
2. Dashboard 的 PTY 转播方案是 POSIX-only（依赖 `ptyprocess`/`fcntl`/`termios`），原生 Windows 被 `pty_bridge.py` 显式排除。如果要在原生 Windows 上支持 Dashboard 的 `/chat` 标签页，你会选择接入 ConPTY（`pywinpty`）复用现有转播架构，还是让 Windows 场景走 Electron 那条"直连协议"的路子？两种选择各自的取舍是什么？
3. 桌面应用的 `desktop-slash-commands.ts` 用黑名单（`NO_DESKTOP_SURFACE`）而不是白名单来裁剪命令，文中提到这是为了让技能/快捷命令默认可见。这种"默认放行、显式屏蔽"的策略在什么场景下可能出问题（比如网关新增了一个只该在消息平台可见的内部命令）？
