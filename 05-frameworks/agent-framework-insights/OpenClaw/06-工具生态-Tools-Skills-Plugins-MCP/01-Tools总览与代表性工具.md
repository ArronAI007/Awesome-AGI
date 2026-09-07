# Tools 总览与代表性工具

> `docs/tools/` 目录下有 60 多篇文档,对应的是一个比 OpenHarness 42 个内置工具、Hermes 一套消息网关工具集大得多的工具面——`src/agents/tools/` 本身接近 300 个文件。这个规模已经大到不可能逐个工具去读源码,OpenClaw 自己的文档也承认了这一点:一次会话里模型能看到多少工具,不是一个可以数出来的常数,而是"全局配置、per-agent 配置、channel 策略、provider 限制、沙箱规则、插件可用性"层层过滤之后的结果。这也是为什么 OpenClaw 在工具面之上又长出了一层"元工具"——`tool_search`、`code_mode`——专门用来管理工具本身多到超出模型上下文预算这件事。本篇不试图罗列 60 多篇文档,而是先建立全景地图,再挑几个功能簇里最能体现设计取舍的代表性工具讲清楚。

## 学习目标

- 理解 `docs/tools/index.md` 给出的"Tools / Skills / Plugins"三层能力划分,以及工具可见性由哪几层策略叠加决定。
- 按执行类、浏览器与网络类、多代理类、元工具类四个功能簇,认识 OpenClaw 工具集里几个代表性工具的核心机制。
- 理解 `tool_search`/`code_mode` 这类"管理工具的工具"要解决的具体问题——把大量工具 schema 从系统提示词里挪走。
- 理解 `loop-detection` 两套互补护栏各自防的是什么场景。
- 知道权限模式(`tools.exec.mode`)和工具本身是两条独立的正交轴,为什么它只在本章简要带过、留给第 10 章深入。

## 背景与设计动机

OpenClaw 的文档把"能力"切成三层:工具(callable actions)、技能(教模型怎么做事的指令包)、插件(给系统本身添加新能力的运行时扩展)。`docs/tools/index.md` 给这三者的定义很直白:

> A tool is a typed function the agent can call, such as `exec`, `browser`, `web_search`, `message`, or `image_generate`. ... The model only sees tools that survive the active profile, allow/deny policy, provider restrictions, sandbox state, channel permissions, and plugin availability.
> —— `docs/tools/index.md`

这句话里"survive"这个动词值得注意——工具不是一份静态清单,而是要经过至少六层过滤才能到达模型面前的幸存者:profile、allow/deny、provider 限制、沙箱状态、channel 权限、插件可用性。这六层里的具体规则是 `gateway/config-tools` 文档的地盘,不属于本章,但理解"工具是被过滤出来的"这个前提,才能理解为什么 OpenClaw 还需要 `tool_search`/`code_mode` 这类元工具——即便过滤掉了大部分不该看到的工具,剩下"幸存"下来的工具集仍然可能大到没法一次性塞进系统提示词。

`index.md` 用一张路由表把 60 多篇文档收束成十几个功能类别(节选):

```text
Runtime       exec, process, terminal, code_execution
Files         read, write, edit, apply_patch
Web           web_search, x_search, web_fetch
Browser       browser
Sessions and agents   sessions_*, agents_wait, subagents, agents_list, get_goal, ...
Large OpenClaw catalogs  exec, wait, tool_search_code, tool_search, tool_describe
```
—— `docs/tools/index.md`「Built-in tool categories」

这张表本身就是全景导航——本篇不逐行展开,而是挑四个簇:执行类、浏览器与网络类、多代理类、元工具类,讲清楚每个簇里代表性工具解决的具体问题。

## 核心机制详解

### 执行类:`exec` 是可写的,`apply_patch` 是它的结构化子工具

`exec` 的文档开门见山地纠正了一个常见误解:

> `exec` is a mutating shell surface: commands can create, edit, or delete files wherever the selected host or sandbox filesystem permits. Disabling OpenClaw filesystem tools such as `write`, `edit`, or `apply_patch` does not make `exec` read-only.
> —— `docs/tools/exec.md`

也就是说,"关掉 `write`/`edit`/`apply_patch` 就等于让 agent 变成只读"是一个常见但错误的安全假设——只要 `exec` 还在,agent 依然能通过 shell 命令写文件。这也解释了为什么 OpenClaw 把 `apply_patch` 定义为 `exec` 的一个子工具而不是独立能力:

> `apply_patch` is a subtool of `exec` for structured multi-file edits. ... `allow: ["write"]` implicitly allows `apply_patch`. `deny: ["write"]` does not deny `apply_patch`; deny `apply_patch` explicitly or use `deny: ["group:fs"]` when patch writes should also be blocked.
> —— `docs/tools/exec.md`

`allow` 和 `deny` 在这里不对称:允许 `write` 会隐式允许 `apply_patch`,但禁止 `write` 不会隐式禁止 `apply_patch`。这不是文档疏漏,而是提醒使用者"文件写入"这件事在 OpenClaw 里至少有三条路径(`write`/`edit`/`apply_patch`/`exec`),策略配置必须显式覆盖所有路径,否则封堵会有遗漏。`apply_patch` 本身采用的是一种结构化 diff 语法(`*** Begin Patch` / `*** Update File:` / `*** End Patch`),支持一次调用里跨多个文件做增删改,`workspaceOnly` 默认 `true`——把补丁写入范围锁定在工作区目录内,除非显式关闭。

`exec` 的执行策略由 `tools.exec.mode` 一个字段驱动出 `security`(允许清单严格程度)和 `ask`(命中失败时是否询问人类)两个派生维度:

| Mode | security / ask | Behavior |
| --- | --- | --- |
| `deny` | `deny` / `off` | 完全阻止 host exec |
| `allowlist` | `allowlist` / `off` | 只跑白名单命令,未命中静默拒绝 |
| `ask` | `allowlist` / `on-miss` | 白名单命中直接跑,未命中问人 |
| `auto` | `allowlist` / `on-miss` | 白名单命中直接跑,未命中先走自动审查,审查不了再问人 |
| `full` | `full` / `off` | 无审批直接跑 |
—— `docs/tools/exec.md`「Modes」

`auto` 模式引入的"自动审查"值得多说一句:它不是把决策权完全交给模型自己,而是由 OpenClaw 内建的一个独立审查角色(可配置成单独的 reviewer 模型)先尝试判断一条未命中白名单的命令是否安全,只有审查不了时才升级到人类审批。这是"既要人少被打扰,又不能让模型自己既是裁判又是选手"这条设计取舍的具体实现。

### 浏览器与网络类:三个工具三种信任边界

`web_fetch`、`web_search`、`browser` 表面上都是"从网上拿信息",但它们的信任边界完全不同。`web_fetch` 是最轻量的一个——纯 HTTP GET 加 Readability 内容抽取,不执行 JavaScript:

> `web_fetch` does a plain HTTP GET and extracts readable content (HTML to markdown or text). It does **not** execute JavaScript. For JS-heavy sites or login-protected pages, use the Web Browser instead.
> —— `docs/tools/web-fetch.md`

它的抓取流水线是"Fetch → Extract(Readability)→ Fallback(可选,比如 Firecrawl 的反爬绕过模式)→ Cache(默认 15 分钟)"四步,并且默认拦截私有/内网主机名——这是应对 SSRF 的第一道闸门,`ssrfPolicy.allowedHostnames`/`blockedHostnames` 允许精细地开小口子或加黑名单。`web_search` 是另一条独立路径,支持 Brave/Exa/Firecrawl/DuckDuckGo 等多个 provider 可插拔切换,`web_search` 走 xAI Responses(当 provider 是 Grok 时)、`web_fetch` 则"always runs locally"——这句话直接点出两者在信任模型上的差异:一个可能把请求路由到第三方 AI 服务,一个永远在本地发起。

`browser` 工具的信任边界设计则更彻底,它不是"给 agent 一个自动化接口去操作你的浏览器",而是专门起了一个隔离的浏览器身份:

> OpenClaw can run a **dedicated Chrome/Brave/Edge/Chromium profile** that the agent controls. ... Think of it as a **separate, agent-only browser**. The `openclaw` profile never touches your personal browser profile.
> —— `docs/tools/browser.md`

这个 `openclaw` profile 和用户真实登录的 Chrome 会话完全隔离,只有显式选择 `user` profile(通过 Chrome DevTools MCP 附着到真实会话)才会接触用户自己的浏览器状态。这种"专开一个身份给 agent 用"而不是"复用用户身份再加权限检查"的思路,把"agent 操作浏览器可能干扰用户正在用的标签页"这类问题从策略层面挪到了架构层面——从源头上不共享,比事后加约束更彻底。

### 多代理类:`subagents` 与 `swarm` 分别管什么

`subagents`(模型可见工具 `sessions_spawn`)和 `swarm` 都是"派生更多 agent 去做事"的机制,但分工不同。`subagents` 文档定义的是最基本的委派单元:

> Sub-agents are background agent runs spawned from an existing agent run. Each one runs in its own session (`agent:<agentId>:subagent:<uuid>`) and, by default, **announces** its result back to the requester for review.
> —— `docs/tools/subagents.md`

"announce"是这里的关键词——子 agent 跑完之后不是简单地把结果塞回父 agent 的上下文,而是走一条独立的完成投递路径:如果父 agent 当前还在跑,OpenClaw 会先尝试唤醒/引导那次运行;如果唤不醒,完成事件会在同一个会话通道里排队等待,而不是另起一次可见回复。子 agent 默认不拿到 session 工具或 message 工具——这条"工具面故意收窄"的设计和它默认隔离的会话上下文(除非显式 `context: "fork"`)一起,构成了子 agent 委派"默认最小权限"的基本姿态。

`swarm` 则是在 `subagents` 提供的委派原语之上,给 Code Mode 脚本加了一层结构化编排能力:

> Swarm is an experimental way to orchestrate many sub-agents from a Code Mode script. ... There is no graph DSL and no separate workflow format. The program is the orchestration. Swarm adds awaitable collector children, structured results, bounded concurrency, and progress reporting to that program.
> —— `docs/tools/swarm.md`

"没有图 DSL,程序本身就是编排"这句话是设计哲学的直接表达——OpenClaw 没有像很多多智能体框架那样另造一套声明式的工作流描述语言,而是让模型直接写 `Promise.all`/`while`/`if` 这类普通 JavaScript 控制流,Swarm 只负责在这些普通控制流之下补上"可等待的子 agent 句柄""结构化结果""有界并发"("`maxConcurrent` 默认 8")这几个原语。这意味着学会用 Swarm 编排多代理任务,本质上就是学会用 JavaScript 写异步并发代码,没有额外的心智负担要学一套新的图语言。

### 元工具类:当工具多到需要工具去管理工具

`tool_search` 和 `code_mode` 解决的是同一个母问题——工具目录一旦大到某个阈值,把每个工具的完整 JSON Schema 都塞进系统提示词会显著推高请求体积、拖慢首 token、还增加模型选错工具的概率。`tool_search` 文档把这个问题讲得很直接:

> Large catalogs are useful but expensive. Sending every tool schema to the model makes the request larger, slows planning, and increases accidental tool selection.
> —— `docs/tools/tool-search.md`「Why this exists」

它给出的解法不是简单地砍工具数量,而是把"发现"和"调用"分离成两步:模型先看到一份紧凑的能力目录(工具名+简短描述),需要精确调用某个工具时再单独 `describe` 拿完整 schema,再 `call` 真正执行。`code_mode` 走的是更激进的一条路——连"结构化搜索/描述/调用"这三个工具都不直接暴露给模型,而是只暴露 `exec`/`wait` 两个工具,模型写一段 JavaScript/TypeScript,在一个隔离的 QuickJS-WASI worker 里运行,程序内部通过全局函数直接调用被隐藏的工具目录:

> The model-visible tool list becomes `exec`, `wait`, plus any direct-only tool such as `computer` or the native-vision `view_image` loader whose image result cannot survive the guest bridge.
> —— `docs/tools/code-mode.md`「What it does」

值得注意的是,文档专门强调 OpenClaw 的 Code Mode 和 Codex 自带的 Code Mode 是两套独立实现,只是共享了 `exec`/`wait` 这两个工具名——前者的 `exec` 接受 `{ code, language }` 的 JSON payload,在 QuickJS-WASI 里跑;后者的 `exec` 是自由文本语法,直接在 Codex 的进程内 V8 里跑。这是一个"同名不同实现"的具体例子,提醒读者不要把两套文档的细节混为一谈——这也呼应了第四篇要讲的 Codex 深度集成里,Codex 原生能力和 OpenClaw 通用能力经常并存但互不替代这条主线。

`loop-detection` 则是元工具簇里方向不同的一个——它不管工具目录大小,管的是模型在工具调用序列里"卡住"这件事,提供两套互补的护栏:

> 1. **Loop detection** (`enabled`) - disabled by default. Watches the rolling tool-call history for repeated patterns and unknown-tool retries.
> 2. **Post-compaction guard** - enabled whenever `enabled` is not explicitly `false`. Arms after every compaction-retry and aborts the run if the agent repeats the same `(tool, args, result)` triple within the window.
> —— `docs/tools/loop-detection.md`

这两套护栏的默认状态刻意不对称:滚动历史检测默认关闭(留给使用较弱模型的场景手动打开),但压缩后护栏默认开启,而且只有显式设成 `false` 才会关掉。文档解释了这个不对称的理由——压缩后护栏专门防的是"上下文溢出 → 压缩 → 压缩后模型又掉回同一个死循环"这条会无限烧 token 的路径,属于哪怕零配置用户也应该默认获得的保护,而滚动历史检测的误报成本相对更高,所以交给使用者按需开启。

### 权限模式与工具执行的关系(简要)

前面讲的 `exec` 的 `tools.exec.mode`,和"哪些工具对模型可见"是两条正交的轴:一条决定模型能不能看到、调用某个工具,另一条决定看到之后调用它是否需要审批。`permission-modes.md` 专门强调了这个边界:

> Permission mode is separate from `tools.exec.host=auto`. `tools.exec.host` chooses where a command runs. `tools.exec.mode` chooses how host exec is approved.
> —— `docs/tools/permission-modes.md`

文档里还有一处值得记住的细节:ACPX(接入外部 ACP harness 的会话)用的是完全独立的一套权限设置(`plugins.entries.acpx.config.permissionMode`),因为这类会话没有交互式 TTY 弹审批框,`approve-reads`/`approve-all`/`deny-all` 三档和 OpenClaw 自身的 `tools.exec.mode` 互不覆盖——"Set ACPX permissions separately from OpenClaw exec approvals"。这条线索会在第四篇讲 ACP/Codex 集成时重新出现,这里先记住结论:工具能不能被模型看到、工具执行要不要审批、以及第四篇要讲的外部 harness 权限模型,是三层各自独立的策略,深挖审批链条本身是第 10 章的任务,本篇只负责标出这层关系存在。

## 常见问题/易踩坑

**Q:关掉 `write`/`edit` 工具是不是就让 agent 变成只读了?**

不是。只要 `exec` 还在策略允许范围内,agent 依然可以用 shell 命令创建、编辑、删除文件——`docs/tools/exec.md` 明确指出禁用文件类工具"does not make `exec` read-only"。真正要做到只读,需要同时管控 `exec` 本身(比如 `tools.exec.mode: "deny"` 或工具策略里显式 `deny`)。

**Q:`deny: ["write"]` 能不能顺带挡住 `apply_patch`?**

不能。`allow`/`deny` 在 `write` 和 `apply_patch` 之间是不对称的:允许 `write` 会隐式允许 `apply_patch`,但禁止 `write` 不会隐式禁止 `apply_patch`,必须显式 `deny: ["apply_patch"]` 或使用 `deny: ["group:fs"]` 这类分组策略。

**Q:OpenClaw Code Mode 和 Codex Code Mode 是同一个东西吗?**

不是,两者只是恰好共享了 `exec`/`wait` 这两个工具名和"用代码代替直接工具调用"这个思路,底层运行时(QuickJS-WASI worker vs Codex 进程内 V8)、`exec` 的输入语法(JSON payload vs 自由文本)完全不同,文档专门用一整段警示这一点,是本章最容易被读者混淆的一处。

## 小结

OpenClaw 的工具面之所以需要 `tool_search`、`code_mode` 这类元工具,根源在于工具目录本身的规模——它不是一份可以完整塞进系统提示词的静态清单,而是要经过 profile、allow/deny、provider、沙箱、channel、插件可用性六层过滤才能确定的动态集合,过滤之后剩下的部分仍然可能大到需要"先搜索再调用"的两段式发现机制。执行类(`exec`/`apply_patch`)、浏览器与网络类(`browser`/`web_fetch`/`web_search`)、多代理类(`subagents`/`swarm`)这几个功能簇分别用不同的信任边界设计解决各自的问题:`exec` 用 `tools.exec.mode` 派生出的审批链条控制写入风险,`browser` 用完全隔离的浏览器身份而不是权限检查来避免干扰用户,`subagents`/`swarm` 用"默认最小工具面 + 显式的完成投递协议"控制委派链条的失控风险。下一篇会转向另一个能力层——Skill,讲清楚"教模型怎么做事"这件事在 OpenClaw 里是怎么被组织成一份可发现、可加载的指令包的。
