# MCP 集成

> `VISION.md` 在"MCP Support"一节里只用了两句话就把 OpenClaw 对 MCP 的立场交代清楚:"OpenClaw supports MCP as both a server and a runtime integration surface."紧接着是这句话:"The project goal is pragmatic MCP support without duplicating existing agent, tool, ACPX, plugin, or ClawHub paths."——务实的 MCP 支持,但不重复已有的 agent、tool、ACPX、plugin、ClawHub 路径。这不是一句谦虚的免责声明,而是一条实实在在的架构约束:MCP 进入 OpenClaw 之后,不会长成第二套工具系统、第二套插件系统、第二套 agent 编排系统,它必须挤进已有的那几条路径里去用。本篇要做的,就是逐一验证这条约束在真实机制里是怎么落地的。

## 学习目标

- 理解 `VISION.md` 里"pragmatic MCP support without duplicating existing agent, tool, ACPX, plugin, or ClawHub paths"这句话背后的设计取舍,以及它和"What We Will Not Merge"里对应条目之间的呼应。
- 理解 OpenClaw 作为 MCP client 的完整接入路径(Settings、composer、CLI、直写 config)以及连上之后这些远端工具是怎么并入已有工具策略(profile/allow/deny/toolFilter)体系的,而不是另起一套权限模型。
- 理解 OpenClaw 作为 MCP server 的 `openclaw mcp serve` bridge 具体暴露了什么(channel-backed conversations),以及它为什么刻意选择一个窄接口而不是把整个 agent 能力面开放出去。
- 认识 MCP 在 OpenClaw 内部还被当作一种"连接件"本身使用——ACPX harness 要访问插件工具和内建工具时,走的正是内部 MCP server 桥接,而不是给 ACP 协议单独发明一套工具注入机制。
- 认识 MCP 的审批、凭证、沙盒这几层是如何复用第 10 章要讲的审批体系、已有的 auth profile 机制、以及 Gateway 既有的公网暴露路径,而不是各自单独实现。

## 背景与设计动机

MCP(Model Context Protocol)本身要解决的问题很朴素:一个程序想把自己的工具、资源、提示词暴露给另一个程序使用,双方需要一套标准协议,而不是各写各的私有集成。`docs/tools/mcp.md` 开篇给出的定义把这件事说得很直白:"The Model Context Protocol (MCP) is how an agent borrows tools from another program: an MCP server exposes tools, resources, and prompts, and OpenClaw connects to it and makes those tools available to your agents."一句话之后紧跟着的是全篇最关键的一句限定:"Server definitions live under `mcp.servers` in config, and the tools they expose go through the same tool-profile and tool-policy controls as everything else — connecting a server does not bypass your policy."(`docs/tools/mcp.md`)

这句话值得停下来读两遍。它说的不是"MCP 工具也有权限控制",而是"MCP 工具走的是**同一套**权限控制"——第 06 章第 1 篇讲过的 `profile`、`allow`/`deny`、`group:*` 这些机制,不需要为 MCP 场景重新发明一遍,MCP 服务器暴露出来的工具直接汇入那条已有的过滤管线。这是理解本篇全部内容的一把钥匙:凡是遇到"MCP 工具应该怎么被治理"这类问题,先去已有的工具/插件/审批体系里找答案,而不是假设 MCP 会带来一套平行的新规则。

现实的驱动力也很清楚。MCP 生态在过去两年迅速膨胀,官方和社区都在发布各种 MCP server——文件系统访问、记忆存储、文档检索(`context7`)、桌面自动化(CUA)、企业内部服务的私有封装。任何一个 agent 框架都不可能自己重新实现这些能力,能接入 MCP 生态就意味着直接继承了这一整片工具供给。但"能接入"和"接入之后怎么治理"是两个问题——如果每接入一个新协议就要给它配一套独立的权限模型、独立的审批流程、独立的凭证存储,工具生态的复杂度会随协议数量线性增长。`VISION.md` 里"不重复已有路径"的原则,本质上是把这条复杂度曲线压平的工程决策。

与此对应,"What We Will Not Merge (For Now)"清单里专门有一条:"MCP work that duplicates existing MCP, ACPX, plugin, or ClawHub paths without a clear product or security gap"(`VISION.md`)。这不是空话——它给贡献者划了一条具体的审查标准:如果一个 PR 给 MCP 加了能力,但这个能力本来就能用现有的 ACPX 桥接、现有的插件 API、或者 ClawHub 的分发机制解决,除非能说清楚明确的产品或安全缺口,否则不会被合并。下面几节会看到这条原则在真实代码路径里的具体样子。

## 核心机制详解

### `openclaw mcp` 的两个身份

`openclaw mcp` 这个 CLI 命令组本身就体现了"client"和"server"两个方向的划分,`docs/cli/mcp.md` 开篇直接写明:

> `openclaw mcp` has two jobs:
> - run OpenClaw as an MCP server with `openclaw mcp serve`
> - manage OpenClaw-managed outbound MCP server definitions with `list`, `show`, `status`, `doctor`, `probe`, `add`, `set`, `configure`, `tools`, `login`, `logout`, `reload`, and `unset`
> `serve` is OpenClaw acting as an MCP server. The other subcommands are OpenClaw acting as an MCP client-side registry for servers its own runtimes may consume later.

这个划分贯穿全篇:`serve` 是"别人连我",其余一整组子命令是"我连别人"。两者共用一个命令前缀,但背后是完全不同的两条数据流,文档专门用一张表(`docs/cli/mcp.md` "Choose the right MCP path")把常见目标和对应命令列在一起,提醒读者不要把"我想接一个远程 MCP 工具服务器"和"我想让 Claude Code 直接读 OpenClaw 的聊天记录"这两件事搞混——它们分别对应 client 注册表和 server bridge,配置项、命令、乃至信任模型都不相同。这张表(译自原文)值得完整摘出来:

| 想做什么 | 用什么 | 为什么 |
| --- | --- | --- |
| 让外部 MCP client 读写 OpenClaw 的 channel 会话 | `openclaw mcp serve` | OpenClaw 是 MCP server,通过 stdio 暴露 Gateway 会话 |
| 为 OpenClaw 托管的 agent 运行保存第三方 MCP 服务器 | `openclaw mcp add`/`set`/`configure`/`tools`/`login` | OpenClaw 是 client 侧注册表,之后再把这些服务器投射进合适的运行时 |
| 不启动 agent 也想检查一个已保存的服务器 | `openclaw mcp status`/`doctor`/`probe` | `status`/`doctor` 只读配置,`probe` 才建立真实连接列出能力 |
| 从浏览器编辑 MCP 配置 | Control UI `/settings/mcp`(别名 `/mcp`) | 展示清单、启用状态、OAuth/过滤摘要、命令提示,以及一个作用域限定的编辑器 |
| 给 Codex app-server 一个专属的原生 MCP 服务器 | `mcp.servers.<name>.codex` | `codex` 字段只影响 Codex app-server 的线程投射,交接给原生配置前会被剥离 |
| 运行 ACP 托管的 harness 会话 | `openclaw acp` 与 ACP Agents | ACP bridge 模式不接受 per-session 的 MCP 服务器注入,要走 gateway/plugin 桥接 |

（表格内容对应 `docs/cli/mcp.md` "Choose the right MCP path" 一节,文字为中文转述）

### 作为 MCP client:把外部工具接进已有工具面

**四种接入入口。** `docs/tools/mcp.md` 给出了四条并行路径:Control UI 的 **Settings → MCP** 页面表单式添加;chat composer 里 **+ → Connectors → Add MCP server…**,并可以选择 **This session**(仅当前会话)或 **Everywhere**(全局)两种作用域;CLI 的 `openclaw mcp add <name> --command ... / --url ...`;或者直接在 config 里写一段 `mcp.servers.<name>` JSON。四条路径殊途同归,最终都落在同一份 `mcp.servers` 配置结构上——这本身也是"不重复路径"的一个小例子:没有为 UI、composer、CLI 各自发明一套独立的服务器定义格式。

**三种 transport。** 一个启用的 server 定义要么给 `command`(stdio,本地子进程),要么给 `url`(`transport: "sse"` 或 `"streamable-http"`,远程 HTTP)。三种 transport 各自的关键字段:

| Transport | 关键字段 | 说明 |
| --- | --- | --- |
| stdio | `command`(必填)、`args`、`env`、`cwd`/`workingDirectory` | 本地子进程,通过 stdin/stdout 通信 |
| SSE | `url`(必填)、`headers`、`connectionTimeoutMs`、`requestTimeoutMs`、`auth: "oauth"`、`sslVerify`、`clientCert`/`clientKey` | 远程 HTTP Server-Sent Events;省略 `transport` 时的默认值 |
| Streamable HTTP | 同 SSE,另加 `transport: "streamable-http"` | HTTP 流式双向通信,`openclaw mcp set` 会把 CLI-native 的 `type: "http"` 归一化成这个规范拼写 |

（字段表对应 `docs/cli/mcp.md` "Stdio transport" / "SSE / HTTP transport" / "Streamable HTTP transport" 三节）一个最小的 stdio 服务器配置例子(`docs/cli/mcp.md`):

```json5
{
  mcp: {
    servers: {
      context7: {
        command: "uvx",
        args: ["context7-mcp"],
      },
    },
  },
}
```

三种 transport 在配置层是统一的,运行时按字段形状自动分流,不需要为每种 transport 单独维护一套加载逻辑。

**保存不等于连通。** 这是文档反复强调的一点:"Saving a definition proves nothing about reachability — the probe does."(`docs/tools/mcp.md`)`openclaw mcp add` 默认会在保存前先探测一次(除非 `--no-probe` 或需要先走 OAuth),但 `status`、`list`、`show`、不带 `--probe` 的 `doctor`、`set`、`configure`、`tools`、`logout`、`reload`、`unset` 全部只读写配置,不建立真实连接(`docs/cli/mcp.md` "Important behavior")。真正证明"这个服务器活着、暴露了哪些工具"的只有 `openclaw mcp probe` 和 `openclaw mcp doctor --probe` 两条命令。这个区分在实践中很重要:一份写进 config 的服务器定义随时可能因为命令不存在、URL 不可达、OAuth 未授权而实际上什么工具都拿不到,必须靠 probe 来验证,而不是靠"配置文件里有这一段"来自我安慰。

**接入之后,工具长什么样?** 这是回应 VISION 那句话最直接的一处证据。`docs/cli/mcp.md` 写道:"embedded OpenClaw exposes configured MCP tools in normal `coding` and `messaging` tool profiles; `minimal` still hides them, and `tools.deny: ["bundle-mcp"]` disables them explicitly"。也就是说,MCP 服务器暴露出来的远端工具,并没有被塞进一个专属的"MCP 工具"类别独立管理,而是直接进入了第 06 章第 1 篇讲过的那套 `profile`(`coding`/`messaging`/`minimal`)体系——`minimal` profile 下 MCP 工具照样被隐藏,想彻底关掉可以用 `tools.deny: ["bundle-mcp"]` 这个和其他工具组同构的开关。策略层完全没有为 MCP 工具开辟新的分支逻辑。

在这之前还有一道更细的过滤:每个服务器可以配置 `toolFilter.include`/`toolFilter.exclude`,先把服务器自己暴露的工具集合裁剪一遍,再进入 `bundle-mcp` 这一层策略过滤(`docs/cli/mcp.md`)。两层叠加下来,一个 MCP 服务器可能暴露 50 个工具,经过 `toolFilter` 收窄到 5 个,再经过 profile/deny 判断这 5 个能不能被当前 agent 看到——这条链路和"第 1 篇"里讲的"模型只能看到活过所有策略层过滤之后的工具"完全是同一条链路,MCP 只是往这条链路的输入端多插了一路数据源。

**资源和提示词也被"工具化"了。** MCP 协议本身除了 tools 还定义了 resources 和 prompts 两类原语,OpenClaw 没有为它们单独建一套"资源浏览器"或"提示词管理器"概念,而是直接把它们包装成普通工具:"servers that advertise resources or prompts also expose utility tools for listing/reading resources and listing/fetching prompts; those generated utility names (`resources_list`, `resources_read`, `prompts_list`, `prompts_get`) use the same include/exclude filter"(`docs/cli/mcp.md`)。这是"不重复已有路径"原则在协议映射层面的又一次体现:OpenClaw 只有一套"工具"这个统一概念,MCP 的三种能力形态在进入 OpenClaw 之前先被压平成这一种形态,复用同一套调用、过滤、展示逻辑。

**审批复用已有的 Codex 权限体系。** MCP 工具调用要不要人工审批,并没有单独设计一套"MCP 审批模式",而是直接挂在 Codex 会话已有的权限姿态(permission posture)上:"MCP tool approvals follow the effective Codex session permission posture unless you explicitly override the server's approval mode. The default full-permission posture does not prompt... Stricter postures retain approval checks: `workspace` can use automatic review, while `guarded` and `read-only` can prompt the operator"(`docs/cli/mcp.md`)。需要针对单个服务器覆盖时,用 `openclaw mcp configure <server> --approval approve|prompt|auto` 显式设置,这个开关本质上只是写入 `codex.defaultToolsApprovalMode` 这一个已有配置项。

更进一步,**Allow Always** 产生的持久授权(grant)也没有另开一个存储:"For Gateway-hosted Codex runs, **Allow Always** can save a durable grant for one MCP tool on a server configured in `mcp.servers`. The Gateway writes the grant to `agents.<agentId>.mcpTools` in this same approvals document."(`docs/tools/exec-approvals.md`)"in this same approvals document"这几个字是关键——MCP 工具授权和 `exec` 命令的 allowlist 授权共享同一份 approvals 文档,查看和撤销都走同一条 `openclaw approvals get/set --gateway` 命令,这部分完整的审批流程细节留给第 10 章展开,这里只需要确认它没有被单独拆出来。

**OAuth 复用既有的 auth profile 与 Gateway 公网暴露机制。** HTTP 类 MCP 服务器可以配 `auth: "oauth"`,走标准 MCP OAuth 流程,凭证存进共享的 SQLite(`<state-dir>/state/openclaw.sqlite` 的 `mcp_oauth_stores` 表)。如果这个远程服务本来就已经有 OpenClaw 的 auth profile,可以设 `oauth.authProfileId` 直接复用那份已刷新的凭证,而不是让 MCP 单独维护一份刷新逻辑(`docs/cli/mcp.md`)。更有意思的是 `oauth.identity: "per-requester"` 这个模式——每个发消息的人连接自己的账号——它依赖的回调地址是 `<gateway.publicOrigin>/oauth/mcp/callback`,直接复用 Gateway 已有的公网可达域名配置,而不是给 MCP 单独申请一个回调服务。

**注册表是共享的,消费方式各不相同。** `mcp.servers` 这份配置不是只服务于 OpenClaw 内建 agent 一家,`docs/cli/mcp.md` 明确说明:"Runtime adapters may normalize this shared registry into the shape their downstream client expects. For example, embedded OpenClaw consumes OpenClaw `transport` values directly, while Claude Code and Gemini receive CLI-native `type` values such as `http`, `sse`, or `stdio`."这意味着同一份服务器定义,不需要在 Claude Code、Gemini、embedded OpenClaw 各自的运行时里重复配置一遍——注册表只有一份,不同 runtime adapter 各自负责把这份共享定义翻译成自己认识的形状。

### 作为 MCP server:`openclaw mcp serve` bridge

**它暴露的是一个窄接口,不是整个 agent。** `openclaw mcp serve` 让 Codex、Claude Code 或任何其他 MCP client 直接连接 OpenClaw,但它不是把 OpenClaw 的全部工具能力开放出去,而是只做一件具体的事:"OpenClaw is the MCP server and exposes Gateway-backed conversations over stdio."(`docs/cli/mcp.md` "Choose the right MCP path")它的运行方式是:MCP client 启动这个 stdio 子进程并持有它,这个子进程转身再用 WebSocket 连到本地或远程的 OpenClaw Gateway,把 Gateway 里已经路由好的会话(channel conversation)映射成 MCP 语义下的"conversation"和一组读写工具(`docs/cli/mcp.md`,"How it works")。

**bridge 暴露的工具集**——`conversations_list`、`conversation_get`、`messages_read`、`attachments_fetch`、`events_poll`、`events_wait`、`messages_send`、`permissions_list_open`、`permissions_respond`(`docs/cli/mcp.md` "Bridge tools")——这几个名字直接对应"列会话/读记录/等新消息/发回复/看审批/批审批"这几件具体的事,没有更多。这份窄接口本身就是一种安全设计:一个外部 MCP client 通过这条 bridge 能做的事情,严格限制在"操作已有的路由好的会话"范围内,不能凭空发起新的路由、不能绕过 Gateway 直接触达底层 channel 账号。

**信任边界同样复用已有的 channel 配置,而不是单独发明一套白名单。** 文档专门用一节讲这件事:"The bridge does not invent routing. It only exposes conversations that Gateway already knows how to route."紧接着列出的具体含义包括:"sender allowlists, pairing, and channel-level trust still belong to the underlying OpenClaw channel configuration"、"`messages_send` can only reply through an existing stored route"(`docs/cli/mcp.md` "Security and trust boundary")。换句话说,这条 bridge 没有引入一套新的"谁可以给谁发消息"的判断逻辑,它能读到、能回复的会话范围完全由 channel 层已经决定好的路由和信任关系框定——bridge 只是把已经存在的东西以 MCP 协议的形态重新暴露出来。

**事件模型是"实时但不持久"的,历史读取交回已有的 transcript 机制。** bridge 内部维护一个内存事件队列(`message`/`exec_approval_requested`/`exec_approval_resolved`/`plugin_approval_requested`/`plugin_approval_resolved`/`claude_permission_request` 六种类型),`events_poll`/`events_wait` 只能读到 bridge 连接之后产生的实时事件,更早的历史必须用 `messages_read` 去读 Gateway 已有的持久化 transcript(`docs/cli/mcp.md` "Event model")。这个设计再一次避免了重复建设——没有为 MCP client 单独搭一套持久事件存储,持久性这件事完全交给 Gateway 本来就有的会话历史机制。

**Claude 专属通知是可选的适配层,不是协议本体。** `--claude-channel-mode` 三档(`off`/`on`/`auto`,当前 `auto` 行为等同 `on`)控制的是要不要额外发送 `notifications/claude/channel` 这类 Claude 特有的 MCP 通知(`docs/cli/mcp.md`)。文档特意强调这是"intentionally client-specific",通用 MCP client 应该只依赖标准的轮询工具——这也是一种克制:不强迫所有 client 都实现一套 OpenClaw 特有的推送协议,标准路径始终可用,专有能力只作为增量。

**和 ACP 的边界:谁托管 runtime 决定用哪一条。** `docs/cli/mcp.md` 开篇就提醒:"Use [`openclaw acp`](/cli/acp) when OpenClaw should host a coding harness session itself and route that runtime through ACP."`openclaw mcp serve` 与 `openclaw acp` 解决的是两个方向相反的问题——前者是"外部 client 要读写 OpenClaw 的 channel 会话",后者是"OpenClaw 要托管一个外部编码 harness 的运行时"。两条路径都基于既有的 Gateway 会话状态,但服务对象相反,不应该混用。

### MCP 作为内部连接件:ACPX 插件工具桥

如果说前两节讲的是"OpenClaw 对外接 MCP",这一节要讲的是一个更值得玩味的现象:OpenClaw **对内**也在用 MCP 解决问题,而且解决的问题原本大概率会被做成一套 ACP 协议扩展。

第 06 章前几篇讲过,OpenClaw 的插件可以注册自己的工具(比如 memory 插件的 recall/store),内建工具(比如 `cron`)本身也是 OpenClaw 核心能力的一部分。现在的问题是:当一个外部编码 harness(Codex、Claude Code、Gemini CLI)通过 ACP 协议被 OpenClaw 托管运行时,它天然是看不到这些插件工具和内建工具的——ACP 会话默认是一个相对干净的沙盒。`docs/tools/acp-agents-setup.md` 里写得很明确:"By default, ACPX sessions do **not** expose OpenClaw plugin-registered tools to the ACP harness."

这里本可以有两种解法:一种是扩展 ACP 协议本身,给它加一个"OpenClaw 插件工具注入"的私有字段;另一种是复用 MCP——反正 ACP 客户端(Codex、Claude Code 等)本来就认识怎么接一个 MCP server。OpenClaw 选的是第二种。启用方式是一个配置开关:

```bash
openclaw config set plugins.entries.acpx.config.pluginToolsMcpBridge true
```

它做的事情是:"Injects a built-in MCP server named `openclaw-plugin-tools` into ACPX session bootstrap. Exposes plugin tools already registered by installed and enabled OpenClaw plugins."(`docs/tools/acp-agents-setup.md`)也就是说,插件工具被包装成一个内建的、名叫 `openclaw-plugin-tools` 的 MCP server,在 ACPX 会话启动时像挂载任何其他 MCP server 一样挂载给这个 harness。文档还专门澄清了这不是排他机制:"Custom `mcpServers` still work as before. The built-in plugin-tools bridge is an additional opt-in convenience, not a replacement for generic MCP server config."

同样的模式又出现了一次,这次是内建工具:"By default, ACPX sessions also do **not** expose built-in OpenClaw tools through MCP. Enable the separate core-tools bridge when an ACP agent needs selected built-in tools such as `cron`"(`docs/tools/acp-agents-setup.md`),对应开关是 `plugins.entries.acpx.config.openClawToolsMcpBridge`,注入的内建 server 叫 `openclaw-tools`,目前暴露 `cron`。

这两个桥接是理解"不重复已有路径"这条设计原则最具体的证据:面对"ACP harness 需要用到 OpenClaw 自己的工具"这个新需求,OpenClaw 没有在 ACP 协议层新造一条通道,而是把 MCP 本来就承担的"跨程序借用工具"这项能力,反过来用在了自己的两个子系统(插件工具、内建工具)和 ACP 会话之间——MCP 在这里不是"外部集成手段",而是被当成了内部模块解耦的粘合层。与之呼应的是 `docs/cli/acp.md` 里的另一句话:"Per-session MCP servers (`mcpServers`) | Unsupported | Bridge mode rejects per-session MCP server requests. Configure MCP on the OpenClaw Gateway or agent instead."以及"If you want ACPX-backed sessions to see OpenClaw plugin tools or selected built-in tools such as `cron`, enable the gateway-side ACPX MCP bridges instead of trying to pass per-session `mcpServers`."——ACP 会话本身不接受临时的、每会话级别的 MCP server 注入,统一收口到 Gateway 侧这两个显式开关,避免了"每个 ACP 会话各自决定要不要挂载工具"这种难以审计的碎片化配置。

### MCP Apps:渲染面也挂在已有的沙盒和策略边界上

`docs/cli/mcp.md` 里还有一段关于 MCP Apps 扩展的内容,篇幅不小,值得简单一提,因为它同样体现了"复用已有边界"的思路,但不是本篇的重点,这里只做概述。MCP Apps 允许一个 MCP 服务器返回可渲染的 HTML(`ui://` 资源,MIME 类型 `text/html;profile=mcp-app`),OpenClaw 把它渲染在一个独立的、双层 iframe 代理的沙盒 origin 上,和 Control UI 的认证域名严格分开(`mcp.apps.sandboxOrigin`/`sandboxPort`)。值得注意的两处复用:一是 App 只能调用被标记为 `_meta.ui.visibility: ["app"]` 的工具,并且这些调用仍然要"pass the effective OpenClaw tool policy for the run that created the view"——也就是说渲染面再花哨,底层工具调用依然过前面讲的那套 profile/policy;二是渠道内的"Open App"启动链接,依赖的是"Gateway Tailscale exposure has prepared a published HTTPS origin"这个已有的公网穿透机制(`gateway.tailscale.mode`),而不是给 MCP Apps 单独接一套隧道服务。

### 一处容易被忽略的安全细节:stdio 环境变量过滤

在 `mcp.servers` 里给 stdio 服务器传 `env` 时,OpenClaw 会在真正 spawn 子进程之前过滤掉一批危险的环境变量(`NODE_OPTIONS`、`PYTHONSTARTUP`、`DYLD_*`、`LD_*` 等解释器劫持/动态链接劫持类变量),文档说明:"This uses the same host environment security policy as other OpenClaw-spawned processes"(`docs/cli/mcp.md` "Stdio env safety filter")。这条过滤规则不是为 MCP 单独写的,而是 OpenClaw 所有会 spawn 子进程的路径(包括 `exec` 工具)共享的同一份主机环境安全策略——又一处佐证:MCP 只是这套已有安全基础设施的一个新调用方,不是重新实现一遍。

## 常见问题/易踩坑

**Q:一个 MCP 服务器暴露了几十个工具,能不能只让 agent 看到其中几个?**

可以,而且这是官方推荐做法。每个服务器可以配 `toolFilter.include`/`toolFilter.exclude`,用工具名或简单的 `*` 通配符筛选;CLI 上对应 `openclaw mcp tools <name> --include 'search,read_*'`。文档里 Filesystem 服务器的示例就是这么做的:只放行 `read_file,list_directory,search_files`,把写入类工具挡在外面(`docs/cli/mcp.md` "Common server recipes")。这道过滤发生在 `bundle-mcp` 策略判断之前,是先收窄"服务器暴露了什么",再判断"当前 agent 能不能看到"。

**Q:配置文件里写好了 `mcp.servers.<name>`,是不是这个服务器的工具就能用了?**

不是。保存配置只是让 OpenClaw 知道这个服务器的定义,不代表它连得上、也不代表它真的暴露了预期的工具。必须运行 `openclaw mcp doctor <name> --probe` 或 `openclaw mcp probe <name>`,让 OpenClaw 真正建立一次 MCP 连接并列出工具,才能确认这个服务器可用。这一点和第 1 篇里"策略允许 ≠ 工具可达"的教训是同一类问题,只是发生的位置从工具策略层挪到了连通性层。

**Q:某个 profile 里关掉了普通工具,MCP 工具是不是自动跟着一起消失?**

要看具体设置。`minimal` profile 本身就会隐藏 MCP 工具,但在 `coding`/`messaging` 这类正常 profile 下,MCP 工具默认是可见的,想显式关闭需要用 `tools.deny: ["bundle-mcp"]` 整体屏蔽,或者用每个服务器自己的 `toolFilter.exclude` 精细屏蔽。不要假设"我关掉了某个内建工具类别,MCP 工具也会一起被连带关掉"——这是策略粒度上两个独立的开关,这一点和第 1 篇 `write`/`apply_patch` 的教训是同一种模式。

**Q:`openclaw mcp serve` 和 `openclaw acp` 该用哪个?**

看谁托管运行时。想让外部 MCP client(Codex、Claude Code 或其他通用客户端)直接读写 OpenClaw 已有的 channel 会话,用 `openclaw mcp serve`——OpenClaw 是 MCP server。想让 OpenClaw 反过来托管一个外部编码 harness 的运行,并让那个运行走 ACP 协议,用 `openclaw acp`。两者的方向正好相反,不要因为都涉及"MCP"或者"外部 agent"就混着用。

**Q:能不能在一次 ACP 会话里临时传一份 `mcpServers` 给它?**

不能。`docs/cli/acp.md` 明确写了"Bridge mode rejects per-session MCP server requests",per-session 的 MCP server 注入在 ACP bridge 模式下不受支持。想让 ACP 托管的 harness 看到插件工具或内建工具,要走 Gateway 侧显式配置的 `pluginToolsMcpBridge`/`openClawToolsMcpBridge` 这两个开关,而不是指望在建会话的那一刻临时塞一份服务器列表进去。

## 小结

回到开头那句话:"pragmatic MCP support without duplicating existing agent, tool, ACPX, plugin, or ClawHub paths"。走完这一路机制之后,可以看到它不是一句口号——作为 MCP client,远端工具汇入的是第 1 篇讲过的同一套 profile/allow/deny/toolFilter 管线,审批走的是 Codex 权限姿态和同一份 approvals 文档,OAuth 复用已有的 auth profile 与 Gateway 公网域名;作为 MCP server,`openclaw mcp serve` 只暴露一个刻意收窄的 channel-conversation 接口,信任边界完全交给已有的 channel 路由配置决定;更进一步,MCP 甚至被反过来用作 ACPX harness 与插件工具、内建工具之间的内部粘合层,省下了给 ACP 协议单独发明一套工具注入机制的成本。MCP 在 OpenClaw 里从始至终不是一套平行的新扩展体系,而是嵌进已有工具生态、插件体系、审批体系、ACP 体系的一条新入口。

第 06 章到这里就把 Tools、Skills、Plugins、MCP 这四条能力扩展路径讲完了。下一章会转向 Channels——看 OpenClaw 怎么把这一整套已经打通的工具、技能、插件与 MCP 能力,接进用户已经在用的聊天软件里。
