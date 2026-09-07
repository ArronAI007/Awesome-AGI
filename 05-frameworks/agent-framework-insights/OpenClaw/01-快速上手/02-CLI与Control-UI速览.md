# CLI 与 Control UI 速览

> `openclaw` 这一个命令背后挂着接近二十个功能分区、上百个子命令，但它们全都在做同一件事：把用户意图打包成一次 WebSocket RPC，发给那个唯一的 Gateway 进程。Control UI 也不例外——它是一个"直接跟 Gateway WebSocket 对话"的浏览器单页应用，除了渲染层是网页而不是终端字符，跟 CLI 没有本质区别。真正例外的只有一种模式：TUI 的 `--local`，它绕开 Gateway，直接跑内嵌的 agent 运行时。分清"谁是 Gateway 的客户端、谁不是"，是理解 OpenClaw 交互层的第一把钥匙。

## 学习目标

- 建立 `openclaw` CLI 的整体命令版图：设置与引导、消息与 agent、健康与会话、Gateway 与日志、模型与推理、网络与节点、配对与 channel、安全与插件——知道每一类大致管什么，需要时能查到对应命令。
- 理解 Control UI 的技术形态（Vite + Lit 单页应用）、默认监听地址，以及它如何通过 WebSocket 握手完成鉴权，而不是走独立的 HTTP session。
- 读懂 `openclaw dashboard` 的一次性配对链接机制，理解为什么"重新打开仪表盘"不需要每次都带着共享 token。
- 分清 TUI 的两种模式：Gateway 模式（连接一个运行中的 Gateway）与 `--local` 模式（绕开 Gateway，直接跑内嵌 agent runtime），以及为什么后者会缺失部分功能。
- 理解裸调用 `openclaw`（不带子命令）的路由逻辑：它会根据当前配置状态，自动决定进入引导流程、修复流程还是正常的 agent TUI。

## 背景与设计动机

OpenClaw 的架构决定了它必须同时服务好几类完全不同的使用场景：终端重度用户要用 CLI 脚本化操作、日常用户想要一个网页仪表盘随手发消息、需要长期驻留在服务器上做诊断的人想要一个终端界面。如果这三类入口各自实现一套"怎么连接 agent、怎么鉴权、怎么读取会话状态"的逻辑，代码和行为都会很快出现漂移——CLI 能用的功能，网页版却不支持，类似的问题在很多多端产品里都出现过。

OpenClaw 的解法和它的整体架构原则是一致的：**Gateway 是唯一的控制平面和唯一的状态归属方，CLI、Control UI、TUI 都只是连接它的客户端**。README 的"How it fits together"一节把这一点说得很干脆：

> The [Gateway](https://docs.openclaw.ai/gateway) is the local control plane for sessions, tools, events, and channel connections.
> The [Control UI](https://docs.openclaw.ai/web/control-ui), CLI, and [TUI](https://docs.openclaw.ai/web/tui) connect to the Gateway.

这意味着，无论你是敲一行 `openclaw status`，还是在浏览器里点一下发送按钮，最终落地的都是同一套 WebSocket RPC 协议、同一份会话状态、同一层鉴权规则。理解这一点之后，"CLI 命令很多"这件事就不再吓人——它们大多只是同一套 Gateway 能力的不同呈现方式，而不是彼此独立的实现。

## 核心机制详解

### CLI 命令版图：按意图分区，而不是按字母排序

`docs/cli/index.md` 把核心命令按用途归了类，这张表本身就是理解 OpenClaw 能力边界的一份地图：

> | Area | Commands |
> | --- | --- |
> | Setup and onboarding | `openclaw` · `setup` · `onboard` · `configure` · `config` · `completion` · `doctor` · `dashboard` |
> | Reset, backup, and migration | `backup` · `database` · `migrate` · `reset` · `uninstall` · `update` |
> | Messaging and agents | `message` · `agent` · `agents` · `attach` · `acp` · `mcp` |
> | Health and sessions | `status` · `health` · `triage` · `sessions` · `resume` · `audit` |
> | Gateway and logs | `fleet` · `gateway` · `logs` · `system` |
> | Models and inference | `models` · `promos` · `infer` · `memory` · `wiki` |
> | Network and nodes | `connect` · `directory` · `nodes` · `devices` · `node` · `worker` |
> | Runtime and sandbox | `approvals` · `sandbox` · `tui` · `browser` |
> | Automation | `cron` · `tasks` · `hooks` · `webhooks` · `transcripts` |
> | Pairing and channels | `pairing` · `qr` · `channels` |
> | Security and plugins | `security` · `secrets` · `skills` · `plugins` · `proxy` |

同一份文档还给出了"设置类命令"之间的意图划分，值得单独记住，因为它们的名字很容易混淆：

> - `openclaw setup` and `openclaw onboard` verify inference first, then start OpenClaw for Gateway, workspace, channels, skills, and health setup.
> - `openclaw setup --baseline` creates the baseline config and workspace without walking the guided onboarding flow.
> - `openclaw configure` changes targeted parts of an existing setup: model auth, gateway, channels, plugins, or skills.
> - `openclaw channels add` configures channel accounts after the baseline exists.

也就是说，`onboard`/`setup` 是"从零到能跑"的引导式流程，`configure` 是"已经能跑了，改一小块"的日常维护命令，两者不是同一件事的两种叫法。

CLI 还有一套全局约定，几乎所有子命令都遵守：

- `--profile <name>`：把状态隔离到 `~/.openclaw-<name>`，用于同一台机器上跑多个互相独立的 OpenClaw 实例（对应第 1 篇提到的"一台机器一个 Gateway"原则的例外情况，比如救援用的备用 bot）。
- `--dev`：隔离状态到 `~/.openclaw-dev`，默认端口换成 `19001`，方便开发调试不影响正式实例。
- `--json`：命令级别的结构化输出；失败时统一走这个信封格式（`docs/cli/index.md`）：

```json
// CLI JSON 失败信封（docs/cli/index.md 节选）
{
  "ok": false,
  "error": {
    "type": "cli_error",
    "message": "Description of the failure"
  }
}
```

这个统一信封的意义在于：任何脚本只要拿到非零退出码，就可以放心地从 stdout 解析这一份 JSON，而不用针对每个命令写不同的错误处理逻辑——这是 CLI 作为自动化入口的基本前提。

### Control UI：一个直接说 WebSocket 的单页应用

`docs/web/control-ui.md` 对 Control UI 的技术形态描述得很简洁：

> The Control UI is a small **Vite + Lit** single-page app served by the Gateway:
>
> - default: `http://<host>:18789/`
> - optional prefix: set `gateway.controlUi.basePath`
>
> It speaks **directly to the Gateway WebSocket** on the same port.

这句话里有两个值得注意的设计点。第一，Control UI 的静态资源就是 Gateway 自己 serve 出来的，没有单独的前端服务器——这跟很多"前后端分离部署"的产品不同，Gateway 既是控制平面又是这个网页应用的托管方。第二，"直接说 WebSocket"意味着 Control UI 没有走传统的 HTTP session/cookie 鉴权，而是在 WebSocket 握手阶段就带上凭证：

> Auth is supplied during the WebSocket handshake via:
>
> - `connect.params.auth.token`
> - `connect.params.auth.password`
> - Tailscale Serve identity headers when `gateway.auth.allowTailscale: true`
> - trusted-proxy identity headers when `gateway.auth.mode: "trusted-proxy"`
>
> Gateway auth runs before device pairing. A direct loopback connection does not bypass token or password auth.

也就是说，即便是本机 `127.0.0.1` 直连，也逃不过 token/password 校验——"本地连接"和"信任连接"在 OpenClaw 里是两个概念，这一点会在第 5 篇讲安全基线时再展开。

打开仪表盘的标准入口是 CLI 命令：

```bash
openclaw dashboard
```

`docs/cli/dashboard.md` 解释了这背后的一次性配对机制：

> Open the Control UI with a short-lived, one-time owner pairing link. A successful handoff gives that signed browser a durable administrator device credential, so reopening the dashboard does not depend on the shared Gateway token.

这个设计避免了两个麻烦：一是共享 token 不需要每次都手工粘贴到浏览器里；二是即便共享 token 后续被轮换，已经配对过的浏览器仍然可以凭自己的设备凭证正常使用，不会突然被锁在门外。

### TUI：同一个终端外壳，两种运行模式

TUI 提供了 Gateway 模式和本地模式两种用法。Gateway 模式就是标准的"客户端连 Gateway"：

```bash
openclaw gateway   # 先跑起 Gateway
openclaw tui       # 再连上去
```

本地模式则完全绕开 Gateway：

```bash
openclaw chat
# 等价于
openclaw tui --local
```

`docs/web/tui.md` 明确指出了这两种模式的边界：

> - `openclaw chat` and `openclaw terminal` are aliases for `openclaw tui --local`.
> - `--local` cannot be combined with `--url`, `--token`, or `--password`.
> - Local mode uses the embedded agent runtime directly. Most local tools work, but Gateway-only features are unavailable.

"大多数本地工具能用，但仅限 Gateway 的功能不可用"这句话点出了本地模式的定位：它更像是一个"不依赖后台服务、直接在这台机器上验证配置和跑单次任务"的轻量入口，而不是 Gateway 模式的替代品——比如它就没有多设备协同、跨 channel 消息路由这些必须由常驻 Gateway 才能提供的能力。

裸调用 `openclaw`（不带任何子命令）也不是随便打开某个默认界面，而是有一套明确的路由规则（`docs/cli/onboard.md`）：

> - If the active config file is missing or has no authored settings, it starts guided onboarding.
> - If the config file exists but fails validation, it starts the classic onboarding path with `openclaw doctor` guidance.
> - If the config file is valid, it opens the normal agent TUI. A reachable configured Gateway with an agent and model goes directly to that UI without onboarding.

也就是说，`openclaw` 这一个入口本身就承担了"体检 + 分流"的职责：配置缺失就去引导、配置损坏就去修复、配置健康就直接进入正常对话界面。这跟第 1 篇提到的"onboarding 是一条有严格先后依赖的流水线"是同一种设计思路的延续。

### 三个入口，一份状态

把三条线索放在一起看：CLI 的 `gateway call`/`message send` 之类命令、Control UI 的浏览器界面、TUI 的 Gateway 模式，本质上都是在同一条 WebSocket 协议上做 `req(method, params)` → `res(ok/payload|error)` 的请求-响应循环（这套协议的细节留给第 03 章展开）。三者看到的是同一份会话状态、同一套鉴权结果——你在 Control UI 里发的消息，TUI 连到同一个 agent/session 也能看到；你在 CLI 里跑 `openclaw gateway restart`，Control UI 会收到 `shutdown` 事件并提示重连。这也是为什么"Gateway 是唯一控制平面"这条原则不只是运维层面的建议，而是直接决定了这几个交互入口能不能表现一致。

## 常见问题/易踩坑

- **以为 TUI 的 `--deliver`（把回复投递回聊天渠道）能中途开关**：不能，`docs/web/tui.md` 明确写了"Delivery is fixed for the whole TUI session at launch... There is no `/deliver` slash command or Settings toggle to flip it mid-session"，要改就得重启 TUI。
- **给 TUI/CLI 传了显式 `--url` 却期望它自动去读配置里的 token**：不会，官方文档反复强调"When you set `--url`, the CLI does not fall back to config or environment credentials"，必须显式传 `--token`/`--password`。
- **把本地模式（`openclaw chat`）当成 Gateway 模式的轻量替代品长期使用**：本地模式没有常驻服务、没有多设备协同，只适合单机验证配置或跑一次性任务，长期使用应该回到 Gateway 模式。

## 小结

CLI 命令虽多，但都能归到"设置/消息/健康/Gateway/模型/网络/配对/安全"这几个意图分区里；Control UI 和 TUI 的 Gateway 模式在协议层面上和 CLI 并无本质差异，三者都只是 Gateway 这个唯一控制平面的不同呈现形式，真正的例外只有 TUI 的 `--local` 模式。下一篇会把视角切换到"这个助理怎么出现在你已经在用的聊天软件里"——Channels 的整体形态，以及陌生发送者第一次找上门时，OpenClaw 的配对（pairing）机制是怎么工作的。
