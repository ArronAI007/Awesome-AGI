# ACP 与 Codex 深度集成

> `AGENTS.md` 里给这个仓库贡献者的强制性规则中,专门有一条只针对 Codex:"Codex-backed behavior: personally inspect the exact sibling `../codex` source contract before implementation or verdict; wrappers, schemas, and another agent's report are insufficient. Cite the checked source."(涉及 Codex 相关行为的改动或判断,必须亲自查看兄弟目录 `../codex` 里的真实源码合约,封装层、schema 描述、别的 agent 的报告都不够,必须引用查过的源码出处)—— `AGENTS.md`。放眼整份 `AGENTS.md`,这种"文档和封装都不算数,必须亲自看上游源码"级别的规则只给了 Codex 集成一条。这不是修辞,而是在告诉每一个要碰这块代码的人:OpenClaw 和 Codex 之间的合约细到需要逐字核对,任何一层转述都可能失真。本篇要讲清楚的,就是这条规则背后到底是什么样的集成面,值得让项目单独立一条规矩。

## 学习目标

- 理解 ACP(Agent Client Protocol)在 OpenClaw 里的定位——它是"接入外部编码 harness"的通用通道,而不是 Codex 专属通道,搞清楚它和"原生 Codex app-server 路径"之间那条容易混淆的边界。
- 读懂 `acp-agents-setup.md` 里从"安装 acpx 插件"到"配置权限模式"的具体步骤,理解为什么 ACP 会话默认跑在 host 运行时而不是 OpenClaw 沙箱里,以及 OpenClaw 自身的工具默认为什么对 ACP harness 不可见。
- 理解 OpenClaw 原生 Codex harness(`codex` 插件)的集成方式——OpenClaw 和 Codex app-server 之间"谁拥有什么"的分工,以及模型引用如何被路由到这条原生路径。
- 准确理解 `codex-supervision.md` 里"supervision"这个词具体指什么机制(不是权限审批,而是跨主机浏览、续接、归档原生 Codex 会话的能力),避免望文生义。
- 理解 `codex-native-plugins.md`(Codex 市场插件)和 `codex-computer-use.md`(桌面控制)各自覆盖的能力边界,以及它们和 OpenClaw 原生工具体系的关系。
- 能说清楚为什么 AGENTS.md 单独给 Codex 集成立规矩——这条集成对项目而言意味着什么工程风险,并能用 `src/acp/` 的真实代码结构印证文档里描述的"两个方向"。

## 背景与设计动机

OpenClaw 自己有一套完整的内置工具、Skill、Plugin 体系,但现实中团队已经在用 Claude Code、Codex、Cursor、Gemini CLI 这些外部编码 harness——每一个都有自己的模型循环、原生工具集、会话恢复机制。与其为每一个都重新发明一遍"怎么执行代码、怎么审批权限、怎么维护会话状态",OpenClaw 选择了两条并行的接入路径:

一条是通用的 **ACP(Agent Client Protocol)**——一个社区协议(见 [agentclientprotocol.com](https://agentclientprotocol.com/)),让 OpenClaw 把 Claude Code、Cursor、Copilot、Droid、Gemini CLI、OpenCode 等一批外部 harness 都通过同一个 `acpx` 后端插件接入,每一次 spawn 都被记录成一个[后台任务](/automation/tasks)——`docs/tools/acp-agents.md`。

另一条是专门为 OpenAI Codex 开的**原生集成**——`codex` 插件,让 OpenClaw 的 embedded agent turn 直接跑在 Codex app-server 上,而不是走 ACP 这条通用路径。这两条路径长期共存、职责分离:

> **ACP is the external-harness path, not the default Codex path.** The native Codex app-server plugin owns `/codex ...` controls and the default `openai/gpt-*` embedded runtime for agent turns; ACP owns `/acp ...` controls and `sessions_spawn({ runtime: "acp" })` sessions.
> —— `docs/tools/acp-agents.md`

之所以 Codex 单独得到一条原生路径,而不是像 Claude Code、Gemini CLI 一样只走 ACP,是因为 OpenAI 生态(模型访问、账号体系、原生插件市场、Computer Use 桌面控制)在 OpenClaw 的产品定位里权重足够高,值得投入一条更深、更贴合的集成——这也正是这条集成面比其他 ACP harness 复杂得多、因而更容易在细节上出错的根本原因。

## 核心机制详解

### ACP:通用外部 harness 通道

ACP 的心智模型很直接:一个外部 harness 进程被 OpenClaw 当作一个可控的会话来管理。`docs/tools/acp-agents.md` 列出的支持目标包括 `claude`、`codex`(仅作为显式回退)、`copilot`、`cursor`、`droid`、`gemini`、`opencode` 等十几个 harness id,每一个通过 `/acp spawn <id>` 或 `sessions_spawn({ runtime: "acp", agentId: "<id>" })` 启动。

ACP 会话有两种存在形态——交互式(绑定到某个聊天会话或子线程,后续消息直接路由进去)和父任务拥有的一次性后台子任务(类似 sub-agent,完成后通过任务通知路径把结果带回父会话)。这套绑定模型专门区分了三层东西:

- **Chat surface**——人在哪聊天(Discord 频道、Telegram 话题)
- **ACP session**——Codex/Claude/Gemini 的持久运行时状态
- **Runtime workspace**——harness 实际执行的文件系统位置(`cwd`)

这三者互相独立,`--bind here` 只是把聊天面和 ACP 会话钉在一起,不影响 workspace 的选择——这个拆分是为了让"你在哪聊"和"agent 在哪个目录跑"能够自由组合,比如你可以在当前 Discord 频道里操作一个跑在 `/workspace/repo` 目录下的 Codex 会话。

安装上,ACP 走的是标准插件路径,没有特殊之处:

```bash
openclaw plugins install @openclaw/acpx
openclaw config set plugins.entries.acpx.enabled true
```

`acpx` 插件把 ACP 运行时直接内嵌进插件本身(不需要单独维护一个 `acpx` 可执行文件或版本),Gateway 启动时注册一次健康探针,`/acp doctor` 可以随时手动重新探测——`docs/tools/acp-agents-setup.md`。真正值得注意的是权限模型:ACP 会话默认跑在**host 运行时**上,不经过 OpenClaw 沙箱:

> **Security boundary:** The external harness can read/write according to its own CLI permissions and the selected `cwd`. OpenClaw's sandbox policy does **not** wrap ACP harness execution.
> —— `docs/tools/acp-agents.md`

这意味着"要不要沙箱化执行"这个问题,ACP 会话把它交给了外部 harness 自己的权限体系,而不是纳入 OpenClaw 统一的沙箱策略——如果请求方会话本身处于沙箱状态,ACP spawn 会被直接拒绝,这是一条明确的失败边界,而不是静默降级。因为 ACP 会话没有交互式 TTY 来弹出权限确认,`acpx` 插件专门提供了 `permissionMode`(`approve-all`/`approve-reads`/`deny-all`)和 `nonInteractivePermissions`(`fail`/`deny`)两个配置项来决定"没有人可以点确认按钮时该怎么办"——默认是 `approve-reads` + `fail`,也就是说一次需要写权限的操作在非交互 ACP 会话里默认会直接报错而不是被静默允许或静默拒绝,这是刻意的保守设计——`docs/tools/acp-agents-setup.md`。

`acp-agents-setup.md` 里另一个容易被忽略、但同样体现"默认收紧"设计哲学的细节是工具暴露面:

> By default, ACPX sessions do **not** expose OpenClaw plugin-registered tools to the ACP harness. ... By default, ACPX sessions also do **not** expose built-in OpenClaw tools through MCP.
> —— `docs/tools/acp-agents-setup.md`

也就是说,即便你把 Claude Code 或 Codex 当作 ACP harness spawn 起来,它默认既看不到 OpenClaw 插件注册的工具(比如 memory recall/store),也看不到 OpenClaw 内置工具(比如 `cron`)——这两类暴露分别由 `pluginToolsMcpBridge` 和 `openClawToolsMcpBridge` 两个显式开关控制,启用后会往 ACPX 会话启动时注入名为 `openclaw-plugin-tools`/`openclaw-tools` 的内建 MCP server。文档专门提醒"把这当成和让这些插件直接在 OpenClaw 里执行同等的信任边界"——这是一条典型的"能力必须显式打开,而不是默认全量暴露"的设计原则,和后面 Codex 原生插件那节的"只安装你信任的插件"是同一种谨慎。

### Codex 原生 harness:谁拥有什么

原生 `codex` 插件的定位一句话能说清:Codex app-server 拥有底层的 agent 会话本身,OpenClaw 拥有围绕它的一切。

> Codex owns the low-level agent session: native thread resume, native tool continuation, native compaction, and app-server execution. OpenClaw still owns chat channels, session files, model selection, OpenClaw dynamic tools, approvals, media delivery, and the visible transcript mirror.
> —— `docs/plugins/codex-harness.md`

这条分工线索贯穿了整个集成——OpenClaw 不重新实现 Codex 的 thread 恢复、工具续接、上下文压缩逻辑,而是让 Codex app-server 原生地做这些事;反过来,Codex 也不需要知道自己正在被哪个消息渠道调用,渠道路由、审批、媒体投递全部留在 OpenClaw 这一侧。这种分工带来一个直接后果:OpenClaw 的动态工具(dynamic tools)通过 app-server 的 `item/tool/call` 桥接机制注入进 Codex 的原生工具循环,而 Codex 原生的 shell、apply-patch 之类工具则继续在 Codex 内部执行——两套工具体系并存在同一个 Codex thread 里,而不是二选一。

值得注意的是,这条"原生路径"并不是靠模型名字符串前缀就能触发的。`openai/gpt-*` 前缀本身从不单独选中 Codex 运行时;只有在运行时策略未设置或为 `auto`、且请求是一条不带任何自定义 provider 参数覆盖的、精确的官方 HTTPS Responses 路由时,OpenClaw 才可能隐式选中 Codex。要把"这个 agent 必须跑在 Codex 上,跑不了就报错"变成一条显式约束,需要在 provider 或 model 层配置 `agentRuntime.id: "codex"`——这是一条 fail-closed 规则:Codex 不可用时直接失败,而不是悄悄退回到 OpenClaw 内建 harness 直接打 OpenAI API。反过来,`agentRuntime.id: "openclaw"` 则是显式选择绕开 Codex、直接走 OpenClaw 自己的 OpenAI 调用路径。这套"前缀只决定模型,运行时策略才决定谁执行"的分离,正是 `docs/plugins/codex-harness.md` 反复强调的一条规则——它防止了"看起来配的是 Codex,实际上悄悄跑在别的执行路径上"这种难以察觉的漂移。

OpenClaw 甚至把"要不要让 Codex 的原生能力全量生效"做成了逐 turn 粒度的决策,而不是一次性的会话级开关:当一个 turn 的工具策略(比如 `tools.allow` 白名单、`tools.deny` 里出现未被审计过的名字)没法安全映射到 Codex 原生工具面时,OpenClaw 会把这一个 turn 标记为"policy-restricted turn"——关掉 Codex 原生 Code Mode、清空环境选择、禁用原生配置的 MCP server 和 hook 中继,同一个会话下一轮可能又恢复回正常的 Codex thread。这和更强的 **ring zero**(host 自己用来做安装/修复的系统级 agent 模式)是两回事:ring zero 只保留一个 `openclaw` 工具,连 `AGENTS.md` 这样的项目级开发者指令都会被替换成 host 自己撰写的安装指令——普通 agent 配置无法把一个聊天切进 ring zero。这种细粒度的分层(policy-restricted turn vs. ring zero vs. 正常 thread)恰恰说明这条集成不是"开/关"两态,而是一套需要精确理解才能不出错的状态机——`docs/plugins/codex-harness.md`。

这也是为什么 `docs/plugins/codex-harness-runtime.md` 专门用一张"V1 support contract"表格划出了当前版本明确支持和明确不支持的能力边界,比如:

- 支持:OpenClaw dynamic tools、prompt/context 插件注入、Codex 原生 `PreToolUse`/`PostToolUse` 钩子中继(可以阻断,但不能改写工具参数)、`Stop` 钩子中继到 `before_agent_finalize`(可以要求 Codex 再过一遍模型再定稿)、app-server 轨迹捕获。
- 明确不支持:改写 Codex 原生工具的调用参数、编辑 Codex 原生的会话历史、拿到丰富的原生压缩元数据(保留/丢弃了哪些内容、token 变化量)、让插件否决或改写原生压缩、逐字节还原 Codex 发给 OpenAI 的最终请求体。

这张表格本身就是"OpenClaw 与 Codex 之间到底谁说了算"这件事最精确的文档化描述——它清楚地写明了哪些地方 OpenClaw 只能观察、不能干预,以及为什么("Codex core builds the final OpenAI API request internally"这类原因反复出现)。

### `codex-supervision`:不是审批,是跨主机会话浏览与续接

"supervision"这个词很容易让人联想到"对 Codex 执行过程的监督审批",但读完 `docs/plugins/codex-supervision.md` 会发现完全不是这么回事——它解决的是一个更具体的问题:**如何让原生 Codex CLI/VS Code/Atlas/ChatGPT 里已经存在的会话,出现在 OpenClaw 自己的会话侧边栏里,并且可以被续接或归档**。

> Codex supervision is an opt-in capability of the official `codex` plugin. It shows non-archived Codex CLI, VS Code, Atlas, and ChatGPT source sessions from the Gateway computer and opted-in paired computers in the normal sessions sidebar and Chat pane.
> —— `docs/plugins/codex-supervision.md`

具体能做什么,取决于会话来自哪台主机、处于什么状态:

- 一个**本地**、处于 stored/idle 状态的会话可以"续接为分支"(Continue as branch)——OpenClaw 从它有限的持久化历史里镜像出一段可见记录,创建一个模型锁定的 Chat,第一条消息发出时才真正启动完整的 Codex harness thread,并且精确复用 Codex App Server 为这个分支选择的那个模型和 provider,而不是 OpenClaw 自己的模型 fallback 链。
- 一个**处于活跃状态**(有正在进行的 turn)的会话不能被分支或归档,只能等它结束。
- **配对节点(paired node)** 上的会话只能通过受限的、分页的 App Server 只读接口读取持久化的 transcript;要在 Chat 里续接,节点必须同时开放并允许 `codex.appServer.threads.list.v1`、`codex.appServer.thread.turns.list.v1`、`codex.cli.session.resume` 三个命令,且操作者需要 `operator.admin` 权限——节点上的归档能力则完全不可用。
- 归档一个本地会话,前提是操作者手动确认"没有其他 Codex 客户端正在用它",这是一条明确写在文档里的竞态安全边界,而不是自动检测:

> The read, descendant enumeration, and archive requests are not one conditional operation, so a turn can still start between them. App Server status is also not shared across independent processes. The confirmation is therefore the safety boundary for unknown clients and that race: quit or otherwise verify every other client before confirming.
> —— `docs/plugins/codex-supervision.md`

这句话本身就说明了 supervision 机制的性质:它面对的是"OpenClaw 之外还有别的进程在用同一个 Codex 会话状态"这个真实的多进程共享问题,靠的是显式的人工确认而不是分布式锁。理解了这一点就能明白,supervision 和"权限审批"是两件不相关的事——它更接近"给 OpenClaw 装一扇能看到、能安全接管 Codex 原生会话的窗口",而 Codex 本身的执行权限审批走的是另一套机制(前面提到的 `PermissionRequest` 原生钩子中继,以及 `approvalPolicy`/`sandbox`/`approvalsReviewer` 这组 app-server 参数)。文档还专门用 `supervision.allowRawTranscripts` 和 `supervision.allowWriteControls` 两个默认为 `false` 的开关,把"能不能读原始 transcript"和"能不能 fork/rename/archive"这两类权限继续拆细——即使 supervision 本身已启用,agent 侧的 `codex_threads` 工具默认仍然拿不到带 transcript 预览的搜索结果,除非显式打开这两个开关中的一个,这再次体现了整份 Codex 集成"默认收紧、逐层显式打开"的一贯风格。

### Codex 原生插件与 Computer Use:两种不同层次的能力扩展

`docs/plugins/codex-native-plugins.md` 讲的是让 Codex-mode 的 OpenClaw agent 使用 **Codex app-server 自己的插件/App 市场**能力——OpenClaw 不会把 Codex 插件转译成自己的 `codex_plugin_*` 动态工具,插件调用完全留在 Codex 原生 transcript 里执行:

> Native Codex plugin support lets a Codex-mode OpenClaw agent use Codex app-server's own app and plugin capabilities inside the same Codex thread that handles the OpenClaw turn. ... OpenClaw does not translate Codex plugins into synthetic `codex_plugin_*` OpenClaw dynamic tools.
> —— `docs/plugins/codex-native-plugins.md`

这套集成分三个状态跟踪:Installed(插件包在目标 app-server 里)、Enabled(Codex 报告启用且 OpenClaw 配置允许)、Accessible(app-server 确认这个插件的 App 条目对当前账号可用)。三者缺一不可,任何一环缺失都会导致该插件的能力对这个 Codex thread 不可见——这是一种刻意"失败即隐藏"而不是"失败即报错但继续暴露"的保守策略,文档里反复出现"缺失或不确定的所有权信息一律 fail closed"这种表述。破坏性操作(destructive actions)也有独立的策略开关 `allow_destructive_actions`,支持 `true`/`false`/`"auto"`/`"ask"` 四档,精细到"哪怕全局允许,不安全的 elicitation schema 依然拒绝"。

`docs/plugins/codex-computer-use.md` 讲的是另一个维度——桌面控制。它明确写道 OpenClaw 本身不打包桌面应用、不亲自执行桌面动作、不绕过 Codex 权限,`codex` 插件做的只是"准备好环境":确认 Codex 支持插件、找到或安装配置好的 Computer Use 插件、确认 `computer-use` 这个 MCP server 可用,然后把原生 MCP 工具调用完全交给 Codex 自己处理——这条能力和 OpenClaw 自己内置的[节点侧 computer-use 工具](/nodes/computer-use)是两套并行、互不替代的东西,文档专门用一节区分了两者的适用场景;更值得注意的是,同一篇文档里还区分了第三条相邻但完全独立的路径——直接把 TryCua 的 `cua-driver mcp` server 注册进 OpenClaw 自己的 MCP 注册表,这条路径保留了上游驱动原始的 MCP 工具面,和 Codex Computer Use 走 marketplace 安装、由 Codex 拥有原生工具调用完全是两回事。三条路径(OpenClaw 内置节点工具、Codex 原生 Computer Use、直连 cua-driver MCP)分别回答"谁拥有执行权""跑在哪台机器上""要不要绕开 Codex"这几个正交的问题,不应该被混为一谈。

值得注意的是,不管是原生插件还是 Computer Use,这两篇文档都反复强调"只安装你信任的插件"——因为一个 Codex 插件可以带来 skill、App、MCP server 和 hook,其中 hook 甚至可以参与权限决策,这不是一次安全审查或隔离边界,而是一次显式的信任委托:

> Only install plugins you trust. A Codex plugin can contribute skills, apps, MCP servers, and hooks. Some hooks can participate in permission decisions, so explicit installation trusts the selected plugin's code; it is not a security review or an isolation boundary.
> —— `docs/plugins/codex-native-plugins.md`

### 代码结构印证:`src/acp/` 里真实存在的"两个方向"

文档里反复出现一个容易被忽略的区分:ACP 不是单向的"OpenClaw 调用外部 harness",而是双向协议——OpenClaw 既可以当 ACP **客户端**(spawn Claude Code/Codex/Gemini CLI 这些外部 harness),也可以通过 `openclaw acp` 把自己反过来暴露成 ACP **服务端**,让编辑器或其他 ACP 客户端连过来(`acp-agents.md` "Which page do I want?" 表格里"Expose an OpenClaw Gateway session as an ACP server"那一行)。这个双向设计在仓库的 `src/acp/` 目录(共约 131 个文件)里能对应到两条清晰分开的代码路径:

- `src/acp/client.ts` 文件头注释直接写明"Interactive stdio ACP client used to connect a terminal session to an OpenClaw ACP server",内部用官方 `@agentclientprotocol/sdk` 的 `ClientSideConnection` 和 `ndJsonStream` 实现——这正是"OpenClaw 暴露为 ACP 服务端、外部客户端连进来"这条桥接方向里、终端一侧扮演客户端角色的实现。
- `src/acp/control-plane/` 目录下的 `AcpSessionManager`(定义在 `manager.core.ts`)才是文档里 `/acp spawn`、`sessions_spawn({ runtime: "acp" })` 背后真正的控制面——它把 spawn、初始化会话、运行 turn、取消、关闭、runtime 配置读写拆成一组独立文件(`manager.initialize-session.ts`、`manager.turn-runner.ts`、`manager.cancel-session.ts`、`manager.close-session.ts`、`manager.runtime-options-commands.ts` 等),`AcpSessionManager` 类本身只是把这些拆分实现组合成一个"Coordinates ACP session metadata, runtime handles, per-session queues, and turn execution"的门面(见类上方注释)。这与文档里描述的会话生命周期——spawn 创建/恢复运行时会话、绑定对话、turn 完成等待投递、`close` 移除绑定但外部 harness 可能仍保留自己的历史——在结构上逐一对应。

这次抽样验证的意义不在于逐行核对实现细节,而在于确认文档描述的架构性断言("ACP 是双向协议""控制面独立于具体 harness 实现")在代码里确实有对应的物理分层,而不是文档一厢情愿的抽象——这也从侧面印证了 AGENTS.md 为什么要求"必须亲自检查源码合约":哪怕只是确认一个目录结构是否和文档吻合,也已经比单纯相信文档描述更接近事实。

### 为什么 AGENTS.md 单独给 Codex 立规矩

把前面几节拼在一起看,能看出这条集成面比其他任何一个 ACP harness 都更深、更纠缠:

- 它不是"调用一个外部进程、转发文本"这种薄封装,而是要精确对齐 Codex app-server 的 thread/turn/tool 事件模型、原生钩子中继、`PermissionRequest` 审批路由、原生压缩、原生插件市场的 install/enable/accessible 三态判定,外加逐 turn 粒度的策略限制(policy-restricted turn)和更强的 ring zero 模式。
- 这条合约本身是**有版本、会演进**的——`docs/plugins/codex-harness-runtime.md` 里的"V1 support contract"表格就是这种演进的产物,今天不支持的能力(比如改写原生工具参数、拿到丰富的压缩元数据)明天可能因为 Codex 一侧新增了 API 而变得可行,反之亦然。
- AGENTS.md 里紧跟着那句规则之后还有一句同样具体的要求:"Harness upgrades also refresh `docs/plugins/codex-harness.md` from `model/list`"——也就是说升级 Codex harness 版本这个动作本身被绑定了一个必须同步执行的文档刷新步骤,以防止文档描述的模型列表和实际支持的模型产生漂移。

这几点合在一起说明,Codex 集成面临的真实风险不是"写错了一个参数名"这种表层错误,而是**文档、封装层描述的行为和 `../codex` 仓库里真实的协议行为之间产生漂移**——尤其是在一个多仓库协作、Codex 自己也在快速迭代的环境里,任何一层转述(哪怕是另一个 agent 认真读过文档后给出的报告)都可能已经过时或者只反映了部分事实。要求"必须亲自检查兄弟目录的源码合约"并"引用查过的源码出处",本质上是把这条集成的正确性验证责任,钉死在离真相最近的那一层——而不是让它在层层转述里被稀释掉。这也是为什么本篇在描述 supervision 机制时反复强调"以文档为准":连"supervision"这个词从字面猜出来的含义,都会和真实机制相差甚远,更何况是没读过源码就下判断的具体行为细节。

## 常见问题/易踩坑

**Q:ACP 里的 `codex` 目标和原生 `codex` 插件是同一回事吗?**

不是。`acp-agents.md` 明确把 `codex` 列为 ACP 支持的目标之一,但标注为"仅在原生 `/codex` 不可用或显式要求 ACP 时才用的显式回退"(Explicit ACP fallback only when native `/codex` is unavailable or ACP is requested)。日常场景应该优先用原生 Codex app-server 路径,ACP 只是一条兜底通道——两条路径甚至用不同的会话 key 前缀(`agent:<agentId>:acp:<uuid>` vs. 原生 Codex 的 thread 绑定),互不共享状态。

**Q:装了原生 Codex 插件,是不是就自动获得了 Codex 的原生插件市场和 Computer Use 能力?**

不是。原生 Codex harness、`codex-native-plugins`、`codex-computer-use` 是三层独立可选的能力,分别对应不同的配置开关(`plugins.entries.codex.enabled`、`codexPlugins.enabled`、`computerUse.autoInstall`)。基础 harness 跑起来之后,原生插件市场和桌面控制都需要单独启用和验证前置条件。

**Q:通过 ACP spawn 一个 Claude Code 或 Codex 会话之后,它能不能调用 OpenClaw 自己的工具(比如 memory、cron)?**

默认不能。`acp-agents-setup.md` 明确写道 ACPX 会话默认既不暴露 OpenClaw 插件工具,也不暴露 OpenClaw 内置工具,必须分别显式打开 `pluginToolsMcpBridge` 和 `openClawToolsMcpBridge` 才会注入对应的内建 MCP server——这是一条需要单独确认的能力开关,不要假设"spawn 了就等于工具打通了"。

## 小结

ACP 给 OpenClaw 提供了一条通用、协议化、双向的外部 harness 接入通道(既能当客户端 spawn 外部 harness,也能反过来被 `openclaw acp` 暴露成服务端),而 Codex 单独拥有一条更深的原生集成路径——两者分工明确,不是竞争关系。深入原生 Codex 集成之后能看到,这条集成面所覆盖的不只是"跑一个模型循环",还包括逐 turn 粒度的策略限制、跨主机的原生会话浏览与续接(supervision)、Codex 自己的插件市场和桌面控制能力——每一层都有清晰但会随版本演进的支持边界,`src/acp/` 里客户端代码与控制面代码的物理分层也印证了文档描述的架构不是纸面抽象。AGENTS.md 里那条只针对 Codex 的"必须亲自检查源码合约"规则,正是对这种深度和易漂移性的工程回应。下一篇会转向另一条同样追求"复用已有协议而不是另起炉灶"的路径——MCP 集成,看 OpenClaw 如何在不重复自己已有的 agent/tool/ACP/plugin 体系的前提下,把 MCP 这套业界通用协议接进同一套底层能力。
