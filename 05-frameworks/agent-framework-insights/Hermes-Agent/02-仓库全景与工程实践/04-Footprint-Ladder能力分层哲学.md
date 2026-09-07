# Footprint Ladder:能力分层哲学

> `AGENTS.md` 开篇第一段就把整份工程手册的价值观说透了:"Hermes 主要通过 plugins 和 skills 扩展,而
> 不是靠做大核心"(It is extended primarily through **plugins and skills**, not by growing the core)。
> 这句话不是口号——它落地成了一套具体的、可操作的决策框架:**Footprint Ladder**(能力足迹阶梯)。当
> 你想给 Hermes 加一项新能力时,这套框架告诉你应该往运行时的哪一层加、以及为什么"加得越少越好"。本篇
> 逐字拆解 `AGENTS.md` 里这一节和紧随其后的"Session capability vs. process env"这条设计铁律,并用
> 仓库里真实存在的代码(`toolsets.py`、`tools/registry.py`)印证它不是纸面上的原则,而是被实际强制
> 执行的约束。

## 学习目标

- 能背出 Footprint Ladder 六个梯级的准确顺序和每一级的适用条件(不是复述大意,是准确到位)。
- 理解"每加一个核心工具,都要在每一次 API 调用里发送一次 schema"这个成本模型,以及它为什么让"新增
  核心工具"必须是最后手段。
- 读懂"Surface capability is a property of the SESSION, never of the process env"这条规则解决的具体
  拓扑问题,并能用 `HERMES_DESKTOP=1` 这个反例把它讲清楚。
- 能对照 `toolsets.py` 里 `desktop_ui`/`project` 两个真实 toolset 的定义,解释这条规则是怎么落地成
  代码的。
- 理解 `check_fn` 应该回答"可达性/用户是否开启"而不是"我是被谁启动的"这条边界,以及为什么它的
  TTL 缓存是进程级而非会话级。
- 知道这套分层哲学和后面 Toolsets、插件系统、MCP 集成几章分别对应梯级里的哪一级。

## 为什么需要一套"决策框架",而不是"看着办"

`AGENTS.md` 的"What Hermes Is"一节把这件事的动机讲得非常直接:

> Two properties shape almost every design decision... **The core is a narrow waist; capability lives
> at the edges.** Every model tool we add is sent on every API call, so the bar for a new *core* tool
> is high. Most new capability should arrive as a CLI command + skill, a service-gated tool, or a
> plugin — not as core surface.

这句话里"Every model tool we add is sent on every API call"是理解整套 Footprint Ladder 的关键成本
模型:模型工具的 schema 不是"按需加载"的,而是**每一次对话轮次都会被完整发送给 LLM**,无论这一轮
用不用得上。工具数量越多,每次请求的固定开销(token 数、模型在一堆无关工具里"迷路"的概率)就越大。
这与另一条"sacred"的性质——**per-conversation 的 prompt caching**——是同一个约束的两面:核心工具集
一旦确定,理想情况下会话全程保持稳定,才能让 LLM provider 侧的前缀缓存持续命中;如果核心工具集频繁
变化,缓存被打破的成本会直接体现在真金白银的账单上。所以"新增一个核心工具"从来不是一个纯粹的功能
决策,而是一个要在"每一次 API 调用的固定开销"和"这项能力被使用的频率与价值"之间做权衡的决策——
Footprint Ladder 存在的意义,就是把这个权衡显式化成一套可以照着走的阶梯,而不是让每个贡献者凭直觉
判断。

## Footprint Ladder 原文与逐级拆解

`AGENTS.md` 第 182 行开始的原文(逐字引用):

> ### The Footprint Ladder (new capability decision)
>
> Each rung adds more permanent surface than the one above. Choose the highest
> (least-footprint) rung that correctly solves the problem:
>
> 1. **Extend existing code** — the capability is a variation of something that
>    already exists. Zero new surface.
> 2. **CLI command + skill** — manages config/state/infra expressible as shell
>    commands. The agent runs `hermes <subcommand>` guided by a skill. Zero
>    model-tool footprint. Default choice for subscriptions, scheduled tasks,
>    service setup. Examples: `hermes webhook`, `hermes cron`, `hermes tools`.
> 3. **Service-gated tool (`check_fn`)** — needs structured params/returns AND
>    only appears when a prerequisite is configured. Zero footprint otherwise.
>    Examples: Home Assistant tools (gated on token), memory-provider tools.
> 4. **Plugin** — third-party/niche/user-specific capability that doesn't ship in
>    core. Lives in `~/.hermes/plugins/` or a pip package, discovered at runtime.
> 5. **MCP server (in the catalog)** — if the capability genuinely needs to be a
>    tool (structured I/O the agent invokes) but isn't core-fundamental, prefer
>    building it as an MCP server and adding it to the MCP catalog over growing
>    the core toolset. The agent connects to it through the built-in MCP client;
>    zero permanent core-schema footprint, and it's reusable by any MCP host.
> 6. **New core tool** — only when the capability is fundamental, broadly useful
>    to nearly every user, and unreachable via terminal + file (or an MCP server).
>    Examples of correct core tools: terminal, read_file, web_search,
>    browser_navigate.

**核对措辞**:这六级的名称和顺序,与本课程写作前给出的"提纲摘要"版本(扩展已有代码 → CLI命令+skill →
`check_fn` 服务门控工具 → 插件 → MCP服务器 → 新核心工具)完全一致,原文的层级顺序和措辞在此确认无误。

逐级拆开来看每一级"零新增表面"体现在哪:

- **第 1 级·扩展已有代码**——"零新增表面"最彻底的一级,因为压根没有新东西被创造出来,只是让既有的
  函数/命令/工具处理一种它本该处理的变体输入。这是任何新增能力请求都应该先问的问题:这真的是"新能力"
  吗,还是既有能力的一个未覆盖分支?
- **第 2 级·CLI 命令 + skill**——"对模型工具 schema 零占用"(Zero model-tool footprint)是这一级最
  核心的卖点:凡是能表达成"跑一条 shell 命令"的事情(管理订阅、配置基础设施、设置定时任务),就不需要
  给模型一个专门的结构化工具——模型本来就有 `terminal` 工具,让它执行 `hermes cron add ...` 这样的
  子命令,再配一份 skill 教它"什么时候、怎么用这条命令",比单独造一个 `manage_cron` 工具便宜得多。
  原文举的例子——`hermes webhook`、`hermes cron`、`hermes tools`——都是"看起来像功能,实际是 CLI +
  skill"的典型形态。这也解释了为什么前面提到 `hermes_cli/` 目录有 224 个文件——CLI 子命令是这套
  分层哲学里被主动选择的"默认落点"之一。
- **第 3 级·`check_fn` 服务门控工具**——当能力"需要结构化的入参/出参"(不能用一条 shell 命令简单
  表达)**并且**只有在某个前提条件被满足时才有意义,就应该做成一个由 `check_fn` 门控的工具:条件不
  满足时,这个工具的 schema 根本不会出现在发给模型的工具列表里——"Zero footprint otherwise"。原文
  举的例子是 Home Assistant 相关工具(依赖一个 token 是否配置)和记忆-provider 工具。这一级是"结构化
  I/O 的必要性"和"按需出现、无条件时零占用"两个条件的交集,任何一个条件不满足就应该退回第 2 级或
  升到第 4 级。
- **第 4 级·插件**——当能力是"第三方的/小众的/因人而异的",不该进核心仓库时,答案是插件,活在
  `~/.hermes/plugins/` 或者一个 pip 包里,运行时被发现。`CONTRIBUTING.md` 里"第三方产品集成走独立
  插件仓库"的规则,以及 `AGENTS.md`"第三方产品集成到核心树中"被列进"我们不想要的东西",都是这一级的
  具体执行(第 8 章插件系统会展开插件的发现机制和两套插件面)。
- **第 5 级·MCP 服务器(编入目录)**——这一级处理的是一个微妙的中间情况:能力确实需要"是一个工具"
  (模型要调用的结构化 I/O),但又不是"核心到几乎每个用户都用得上"的程度。原文的建议是"优先做成一个
  MCP 服务器、加进 MCP 目录,而不是让核心工具集变大"——agent 通过内置的 MCP 客户端连接它,对核心
  schema 的占用是"zero permanent core-schema footprint",而且这个 MCP 服务器可以被**任何** MCP host
  复用,不只是 Hermes。`optional-mcps/` 目录下上百个第三方服务(Notion、Stripe、Figma……)正是这一级
  的产物。
- **第 6 级·新核心工具**——"最后手段"(last resort),只有当能力"fundamental(基础性的)、broadly
  useful to nearly every user(几乎所有用户都用得上)、且 terminal + file 无法触达(或者一个 MCP
  服务器也做不到)"三个条件同时成立时才允许。原文举的正确核心工具例子——`terminal`、`read_file`、
  `web_search`、`browser_navigate`——都是"离开它们,Agent 就几乎丧失基本行动能力"级别的东西,和"某个
  平台/某个第三方服务的专属能力"完全不是一个量级。

原文紧接着还有一条关于"多个 PR 撞车"的处理规则,属于 Footprint Ladder 精神的延伸而非独立的一级:

> When 3+ open PRs try to integrate the same *category* of thing (memory
> backends, providers, notifiers), don't merge them one at a time — design an
> ABC + orchestrator, wrap the existing built-in as the first provider, and turn
> the competing PRs into plugins against that interface.

也就是说,当"同一类"能力(记忆后端、provider、通知渠道)同时有 3 个以上 PR 在竞争进入核心,正确做法
不是按到达顺序逐个合并,而是抽象出一个 ABC(抽象基类)+ 编排器,把已有的内置实现包装成"第一个
provider",再把其余竞争的 PR 全部转化为对着这个接口写的插件。这实际上是把"临时挤进核心的多个相似
实现"这种熵增,主动转化回 Footprint Ladder 第 4 级(插件)——防止核心因为"抢跑效应"被意外撑大。

## 举例演绎:新增功能 X,该走哪一级

**例子一:"我想让 Hermes 能订阅一个第三方天气预警 API,每天早上推送一条消息。"**

先问:这是"变化的推送触发 + 一次 HTTP 调用"的组合,能不能表达成 `hermes cron add` 配一个已有的
`send_message` 工具?如果这个天气 API 只需要一次简单的 `curl`/`requests` 调用,答案是可以——落点是
第 2 级(CLI 命令 + skill:一条 `hermes cron` 定时任务 + 一份教 Agent 怎么调用这个 API、怎么格式化
消息的 skill),根本不需要新的模型工具。只有当这个天气服务需要复杂的、模型必须理解并按结构化参数
调用的交互(比如多轮查询、需要模型自己决定查询哪个城市和时间范围)时,才值得考虑升到第 3 级
`check_fn` 工具(门控条件是"用户是否配置了这个天气服务的 API key")。

**例子二:"我想接入一个类似 Notion 的第三方笔记服务,让 Agent 能创建/查询笔记。"**

这是"确实需要结构化 I/O、但不是核心到几乎每个用户都用"的典型情况——落点是第 5 级,做成一个 MCP
服务器加进 `optional-mcps/` 目录,而不是在核心 `tools/` 里新增 `notion_create_note` 这样的工具。这样
做的额外好处(原文强调的"reusable by any MCP host")是:这个 MCP 服务器不仅服务 Hermes,任何支持 MCP
协议的客户端(Claude Code、Cursor 等)都能直接复用它。

## Session capability vs. process env:一条关于"我到底在问什么"的铁律

紧跟在 Footprint Ladder 之后,`AGENTS.md` 第 213 行开始是另一条同样重要、但关注点完全不同的规则:
它不是"该不该加新能力",而是"一个已经决定要做的能力,该用什么信号判断它现在是否可用"。原文:

> ### Surface capability is a property of the SESSION, never of the process env
>
> A tool that only works because of *who is on the other end of the connection* —
> the desktop app's panes, the in-app browser, message reactions, Projects — must
> resolve its availability from the **session's own source**, not from an env var
> on the backend process.
>
> The client and the backend are separate machines on separate clocks. The
> desktop app can be driving a backend Electron spawned locally, one over SSH,
> one behind a plain URL + token, or Hermes Cloud. Only the first two are spawned
> by us and carry `HERMES_DESKTOP=1`. Every env-keyed GUI gate is therefore a
> silent no-op on the other half of the topologies, and the failure is invisible:
> the tool is stripped from the schema before the model ever sees it, on the same
> backend whose platform hint is telling the model it's *"chatting inside the
> Hermes desktop app."*

这一条规则要解决的具体问题是:哪些工具"只因为对话另一端是谁"才有意义——比如桌面应用里的分栏
(panes)、内嵌浏览器、消息表情回应(reactions)、Projects 功能。这类能力的可用性判断,必须来自
**会话自身的来源信息**,而不能来自后端进程的一个环境变量。

原因是拓扑关系比直觉想象的复杂得多:桌面客户端和它驱动的后端**是两台在不同时钟上运行的独立机器**。
桌面 App 可能驱动的是:本地启动的 Electron 后端、通过 SSH 连接的远程后端、只靠一个 URL + token 连接
的后端,或者 Hermes Cloud。这四种拓扑里,**只有前两种**是 Hermes 自己 spawn 出来的进程,也只有它们
才会带上 `HERMES_DESKTOP=1` 这个环境变量。这意味着:任何"看这个环境变量来决定 GUI 工具要不要出现"的
逻辑,在后两种拓扑下都会**静默失效**——而且失效得让人完全无感:工具在模型看到工具列表之前就已经被
从 schema 里剔除了,而与此同时,这个后端发给模型的 platform 提示还在告诉模型"你正在 Hermes 桌面应用
里聊天"。也就是说,模型被明确告知自己身处一个可以用分栏、内嵌浏览器的环境,但对应的工具却因为一个
错误的可用性判断依据而根本不存在——这是一种"模型被上下文误导,却又无从验证"的失败模式,比"工具压根
不存在"更危险,因为它连错误发生的痕迹都没有留下。

### 正确的模式:toolset 是唯一的表面门

原文给出了三条具体的落地方式,第一条是最核心的:

> - **The toolset is the surface gate.** Keep the tools off `_HERMES_CORE_TOOLS`
>   (nobody else should pay their schema) and put them in a named toolset —
>   `desktop_ui`, `project`. The GUI gateway's `_load_enabled_toolsets(platform)`
>   folds that toolset in when the session's platform says GUI. One resolver,
>   every topology.

这段话在 `toolsets.py` 里有确凿的实证。`_HERMES_CORE_TOOLS` 列表里明确留了注释,解释为什么桌面专属
工具**不在**这个默认核心集合里:

```python
# NOTE: the desktop GUI affordances (read_terminal, open_preview, …) are
# deliberately NOT here, for the same reason as the `project` tools below:
# they only work where a GUI renderer can answer them. They live in the
# `desktop_ui` toolset and are enabled solely by the GUI gateway for a
# session whose SOURCE is the desktop app (tui_gateway/server.py::
# _load_enabled_toolsets) — never keyed on a process env var, ...
```

而 `desktop_ui` 和 `project` 这两个 toolset 本身,是单独定义、单独按会话来源折叠进来的:

```python
"project": {
    "description": "Desktop Projects — create/switch named workspaces (GUI sessions only)",
    "tools": ["desktop_project"],
    "includes": []
},

"desktop_ui": {
    "description": "Desktop GUI affordances — in-app terminal/browser panes, pane focus, reactions (GUI sessions only)",
    "tools": [
        "read_terminal", "close_terminal",
        "desktop_preview", "drive_preview", "annotate_preview",
        "read_window_below",
        "focus_pane", "react_to_message",
        "setup_mcp", "tour", "tip",
    ],
    "includes": []
},
```

也就是说,判断这批工具该不该出现在某个会话里的代码路径是**单一的**——`tui_gateway/server.py` 的
`_load_enabled_toolsets(platform)` 根据"这个会话的 platform 字段是不是 GUI"来决定要不要把
`desktop_ui`/`project` 这两个 toolset 折叠进这次对话的工具集,而这个 platform 字段来自会话本身携带的
来源信息,与"这个 Python 进程启动时环境变量里有没有 `HERMES_DESKTOP=1`"完全无关。不管客户端驱动的
是本地、SSH、纯 URL 还是云端哪一种后端拓扑,判断逻辑都走同一个 resolver——这正是原文"One resolver,
every topology"这句话的字面含义。

### `check_fn` 该回答什么,不该回答什么

> - **`check_fn` answers reachability or user opt-in, not surface.** "Is the
>   renderer bridge wired?", "did the user enable reactions?" — fine. "Was I
>   spawned by Electron?" — not fine. `check_fn` results are also TTL-cached
>   process-wide (`tools/registry.py`), so a per-session answer does not belong
>   there at all: one process serves many sessions.

这一条把"`check_fn` 门控"(Footprint Ladder 第 3 级的核心机制)和"session 来源判断"两件事的边界
划清楚了:`check_fn` 该回答的是"可达性"或者"用户是否主动开启了某个功能"这类**跟具体是哪个会话无关、
只跟这个后端进程/这个用户配置有关**的问题——"渲染器桥接是否已经接好线"、"用户是否启用了消息回应"
都是合适的 `check_fn` 问题。但"我是不是被 Electron 启动的"这个问题**不适合**放进 `check_fn`,原因是
一个更底层的实现细节:`tools/registry.py` 里 `check_fn` 的返回结果是按**进程级别、TTL 缓存**的——

```python
_check_fn_cache: Dict[tuple[Callable, Optional[str]], tuple[float, bool]] = {}
```

同一个网关进程可能同时服务多个会话(比如一个 GUI 会话和一个通过 SSH 连进来的会话)。如果把"这个会话
是不是桌面来源"这种**逐会话变化**的答案塞进一个**逐进程缓存**的 `check_fn`,第一个会话算出的结果会
被缓存下来,直接污染同一进程里后续所有会话的判断——这不是一个"理论上可能"的边界情况,而是"一个进程
服务多个会话"这一事实的直接推论,所以原文才说"a per-session answer does not belong there at all"
(逐会话的答案压根不该放在这里)。

### 区分"两种不同的身份问题"

> - **Ask which identity you actually mean.** `HERMES_DESKTOP=1` legitimately
>   marks *"this backend process was spawned by the app"* — it gates the cron
>   ticker and web-dist handling correctly. It does NOT mean "a GUI is watching",
>   and the embedded terminal pane (`hermes --tui` against that same backend)
>   is the standing counterexample.

`HERMES_DESKTOP=1` 本身不是一个"错误"的信号,它只是回答了一个**不同的问题**:它合法地标记"这个后端
进程是被桌面 App 启动的",可以正确地用来门控 cron ticker(定时任务触发器)和 web-dist 处理逻辑这类
"跟进程本身怎么被启动有关"的行为。它错就错在被拿去回答另一个问题——"现在是不是有一个 GUI 在看着"。
原文给出的"standing counterexample"(长期存在的反例)是:同一个被桌面 App 启动、带着
`HERMES_DESKTOP=1` 的后端,完全可以再被一个 `hermes --tui`(终端 TUI 客户端)连接上——这时进程环境
变量仍然是 `HERMES_DESKTOP=1`,但连接上来的这个具体会话根本不是 GUI,而是一个终端界面。如果拿进程
环境变量当作"GUI 是否在场"的答案,这个 TUI 会话就会被错误地当成 GUI 会话对待。

### 验证方法:换机器测试

> Same test both ways: if the capability would still make sense with the client
> on another machine, it is session-scoped. Cover it with a test that asserts the
> GUI session gets the tool **with the env var absent** — that's the assertion
> the original gate could never have passed.

原文给出了一个简单、可操作的思想实验作为判定标准:**如果这项能力在"客户端跑在另一台机器上"的情况下
依然说得通,它就是会话级别(session-scoped)的,不该用进程环境变量判断**。对应的测试写法也很具体——
断言"在环境变量缺失的情况下,一个 GUI 会话依然能拿到这个工具"——这条断言精确地就是"旧的、按环境变量
判断的门控逻辑永远无法通过"的那一条,把它写成测试用例,能直接暴露出任何退化回"看进程环境变量"的
回归。

## 小结:这条哲学如何呼应后面的章节

Footprint Ladder 和 Session-vs-process-env 这两条规则,分别对应本课程后面会展开的多个章节:

- 第 4 章"多 Provider 与工具系统"会详细讲 `toolsets.py` 的完整结构、`_HERMES_CORE_TOOLS` 的完整
  列表,以及 `tools/registry.py` 里 `check_fn` 的 TTL 缓存机制本身是怎么实现的——本篇只取了它们里
  和这两条规则直接相关的片段。
- 第 8 章"插件系统与协议生态"会展开 Footprint Ladder 第 4 级(插件)的完整发现机制(`PluginManager`、
  `~/.hermes/plugins/`、pip entry points 三条发现路径),以及 MCP 目录(第 5 级)的登记和连接方式。
- 第 7 章"Skills 自我进化学习环"会展开 Footprint Ladder 第 2 级里"skill 引导 CLI 命令"这一模式—
  —skill 本身的 frontmatter、条件激活、写作规范。
- 第 9 章"多智能体网关与调度"会更细致地讲 `tui_gateway/server.py::_load_enabled_toolsets` 这个真正
  执行"会话来源 → toolset 折叠"逻辑的 resolver,以及网关如何区分不同 platform 的会话。

理解这两条规则的共同点,有助于把它们记得更牢:两者都在优化同一个变量——**核心运行时的稳定表面积**。
Footprint Ladder 控制的是"要不要新增表面积",Session-vs-process-env 控制的是"已经存在的表面积,能不
能被正确、可靠地按需显现"——前者防止核心变胖,后者防止核心在特定拓扑下变得对模型撒谎。

## 思考题

1. 如果要给 Hermes 加一个"读取用户 Google Calendar 空闲时段并建议会议时间"的能力,分别用 Footprint
   Ladder 的第 2 级和第 5 级设计一版方案,比较两版方案在"结构化程度"和"复用性"上的差异,再给出你认为
   更合适的选择及理由。
2. 假设有人提出给 Hermes 新增一个 `is_running_in_docker()` 的 `check_fn`,用来门控某个只在容器环境下
   才有意义的工具。这个 `check_fn` 是否违反"回答可达性/opt-in,而非身份"的原则?为什么"是否运行在
   Docker 里"和"是否被 Electron 启动"看起来相似,但可能不算同一类问题?
3. `_check_fn_cache` 是进程级 TTL 缓存。如果 Hermes 未来演进到"一个网关进程同时服务的会话可能分布在
   不同的沙箱/容器里"这种更复杂的拓扑,`check_fn` 的缓存粒度是否还能维持进程级别不变?这对"什么信号
   适合放进 `check_fn`"这条边界会带来什么新的影响?
