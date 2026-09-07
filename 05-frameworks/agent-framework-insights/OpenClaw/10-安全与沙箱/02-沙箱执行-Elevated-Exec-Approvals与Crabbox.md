# 沙箱执行:Elevated、Exec Approvals 与 Crabbox

> 排查"为什么这个工具被挡住了"是 OpenClaw 运维里最容易踩坑的场景之一,原因是背后其实有三套互相独立、职责边界分明的控制在同时起作用。`docs/gateway/sandbox-vs-tool-policy-vs-elevated.md` 开门见山地把这三层拆开定义:**沙箱决定工具跑在哪里,工具策略决定哪些工具存在/可用,提权(elevated)是专门给 exec 开的一个从沙箱逃逸到宿主机的例外通道**。这三层控制互不隐含对方,任何一层说"不",结果就是"不"。本篇把这三层控制、以及在此之上落地的 exec approvals 具体审批链路讲透,最后落到 Crabbox 这个独立项目的定位——为什么"云沙箱厂商接入"被明确划进了"我们不会合并"的清单。

## 学习目标

- 精确区分沙箱(where)、工具策略(which)、提权(escape hatch)这三层控制各自的作用域,以及为什么"工具策略拒绝"永远赢过沙箱和提权的任何组合。
- 理解 Docker/Podman/SSH/OpenShell 四种沙箱后端的能力矩阵差异,以及默认配置(`network: "none"`、`readOnlyRoot: true`、`capDrop: ["ALL"]`)具体防住了什么。
- 理解 elevated 模式的逃逸边界:它只影响 exec,不授予额外工具,也无法绕过 creator role 要求的强制沙箱。
- 理解 exec approvals 的批准链路——`security`/`ask`/`askFallback` 三个策略旋钮如何组合,YOLO 模式为什么需要同时打开两层配置,以及批准后的执行为什么要绑定到精确的 cwd/argv/环境哈希甚至文件快照。
- 理解 Crabbox 的定位:它是一个独立的沙箱执行项目,OpenClaw 通过它接入云端隔离能力,而不是把每一家云沙箱厂商都做成一个 OpenClaw 插件。

## 背景与设计动机

上一篇讲到"沙箱默认关闭"这条基线,这里先补一句沙箱本身的定位声明。`docs/gateway/sandboxing.md` 用一句克制的话概括了沙箱能做到什么程度:

> "OpenClaw can run tool execution inside a sandbox backend to reduce blast radius. ... This is not a perfect security boundary, but it materially limits filesystem and process access when the model does something dumb."
> —— `docs/gateway/sandboxing.md`

"reduce blast radius"和"not a perfect security boundary"这两个措辞很值得对照上一篇讲的 Hermes 对比——OpenClaw 没有把沙箱包装成"绝对安全边界",而是老老实实地说它限制的是"模型做了蠢事"之后的波及范围。这种克制延续到了整份文档:沙箱只移动**工具执行**,Gateway 进程本身永远留在宿主机上——

> "Sandboxing is off by default and controlled by `agents.defaults.sandbox` (global), `agents.entries.*.sandbox` (per-agent), or a required creator-role sandbox policy. The Gateway process always stays on the host; only tool execution moves into the sandbox when enabled."
> —— `docs/gateway/sandboxing.md`

理解这三层控制的现实意义,最好先看一眼官方给出的排障命令——`openclaw sandbox explain` 直接把"这个会话到底为什么被挡住了"的答案打印出来:

> "It prints:
> - effective sandbox mode/scope/workspace access
> - whether the session is currently sandboxed (main vs non-main)
> - effective sandbox tool allow/deny (and whether it came from agent/global/default)
> - elevated gates and fix-it key paths"
> —— `docs/gateway/sandbox-vs-tool-policy-vs-elevated.md`

这条命令本身就是"三层控制"这套心智模型的具体产品化——它把 mode/scope/workspace access(沙箱层)、tool allow/deny(工具策略层)、elevated gates(提权层)在同一次输出里列全,逼着排障者一次性看清三层各自的状态,而不是逐个猜测。

## 核心机制详解

### 三层控制的精确定义

`docs/gateway/sandbox-vs-tool-policy-vs-elevated.md` 用编号列表给出了这三层的权威定义:

> "1. **Sandbox** (`agents.defaults.sandbox.*`, `agents.entries.*.sandbox.*`, or a required creator-role policy) decides **where tools run** (sandbox backend vs host).
> 2. **Tool policy** (`tools.*`, `tools.sandbox.tools.*`, `agents.entries.*.tools.*`) decides **which tools are available/allowed**.
> 3. **Elevated** (`tools.elevated.*`, `agents.entries.*.tools.elevated.*`) is an **exec-only escape hatch** from ordinary sandboxing (`gateway` by default, or `node` when the exec target is configured to `node`). It cannot bypass a creator role's required sandbox."
> —— `docs/gateway/sandbox-vs-tool-policy-vs-elevated.md`

这三条定义里,最容易被误解的是它们之间的**优先级关系**。文档明确给出了工具策略的绝对优先地位:

> "Rules of thumb:
> - `deny` always wins.
> - If `allow` is non-empty, everything else is treated as blocked.
> - Tool policy is the hard stop: `/exec` cannot override a denied `exec` tool.
> - Tool policy filters tool availability by name; it does not inspect side effects inside `exec`. If `exec` is allowed, denying `write`, `edit`, or `apply_patch` does not make shell commands read-only."
> —— `docs/gateway/sandbox-vs-tool-policy-vs-elevated.md`

最后一条特别值得停下来想一想:工具策略是按**工具名字**过滤的,不检查 `exec` 内部实际执行了什么副作用。也就是说,如果一个 agent 的工具策略允许 `exec` 但拒绝 `write`/`edit`/`apply_patch`,期待"这样就能让 shell 命令变成只读"是一个常见的误解——`exec` 里跑一条 `rm` 或者用 shell 重定向写文件,工具策略这一层根本看不见,真正能限制这种副作用的是沙箱的文件系统权限,而不是工具名字级别的允许/拒绝表。

Elevated 这一层的定义同样有一句容易被略过的限定——"It cannot bypass a creator role's required sandbox"。这意味着如果一个会话的创建者角色(operator role)把 `sandbox: "required"` 钉死了,elevated 模式在这种会话上完全失效,不管操作者怎么调用 `/elevated full` 都不会生效。这是一处刻意设计的"提权不能突破角色策略"的硬约束,后面会具体展开。

### 沙箱:后端矩阵与默认加固

沙箱由三个相互独立的设置组成——mode(何时生效)、scope(容器粒度)、backend(用什么运行时):

| Setting | Key | Values | Default |
| --- | --- | --- | --- |
| Mode | `agents.defaults.sandbox.mode` | `off`, `non-main`, `all` | `off` |
| Scope | `agents.defaults.sandbox.scope` | `agent`, `session`, `shared` | `agent` |
| Backend | `agents.defaults.sandbox.backend` | `docker`, `podman`, `ssh`, `openshell` | `docker` |

`non-main` 模式有一个经常让人意外的行为——群组/频道会话默认不算"main",因此在 `non-main` 模式下反而是**被沙箱化**的那部分,`docs/gateway/sandbox-vs-tool-policy-vs-elevated.md` 专门把这条列进了常见坑:"I thought this was main, why is it sandboxed?"——因为群组/频道 session key 从定义上就不是 `agent:<agentId>:main`。

Docker 后端的默认配置值得逐条读一遍,因为它体现了"默认加固"的具体尺度:

> "Defaults: `network: "none"` (no egress), `readOnlyRoot: true`, `capDrop: ["ALL"]`, image `openclaw-sandbox:bookworm-slim`."
> —— `docs/gateway/sandboxing.md`

三个默认值分别堵住了三类风险:`network: "none"` 让沙箱内的 `curl`/`wget` 类命令连不到公网,直接呼应上一章 Hermes 课程里讲的"网络出口隔离"要解决的问题,只是 OpenClaw 把它作为沙箱的**默认值**而不是需要额外配置的可选层;`readOnlyRoot: true` 意味着容器根文件系统不可写,配合 `workspaceAccess` 独立控制工作区能不能写;`capDrop: ["ALL"]` 丢掉了容器进程的所有 Linux capability,连带 `no-new-privileges` 一起,把容器内进程能做的特权操作压到最低。文档也坦承了这套默认值的直接后果——沙箱内想装系统包会失败,这是**故意的**:

> "The defaults deliberately combine no network, a read-only root filesystem, and a non-root image user, so an in-turn system package install should fail. Project-local dependencies can be installed in a writable workspace when the operator enables network egress. Prefer a custom image that already contains system packages and private certificate roots."
> —— `docs/gateway/sandboxing.md`

四种后端的能力差异也不是均质的,尤其是网络限制和挂载能力:

| Capability | Docker | SSH | OpenShell |
| --- | --- | --- | --- |
| Network restriction | `docker.network`; defaults to `"none"` | Controlled by the remote host | Controlled by the selected OpenShell policy |
| Additional host folders | `docker.binds` with explicit `:ro` or `:rw` | Not supported as mounts; seed or copy files instead | Not supported as mounts; use workspace sync or remote files |
| Sandboxed browser | Supported in a separate browser container | Not supported | Not supported |

只有 Docker/Podman 后端的网络限制是 OpenClaw 自己控制的默认值,SSH 和 OpenShell 后端的网络边界实际上取决于远程主机或 OpenShell 自身策略——这是一处容易被忽视的差异:切换后端不只是换一种运行时,连"默认无网络"这条安全基线本身是否继续生效都会跟着变。

绑定挂载(bind mount)是"沙箱穿透"最直接的通道,因此 OpenClaw 对它做了双重校验:

> "OpenClaw validates bind sources twice, once on the normalized path and again after resolving through the deepest existing ancestor, so symlink-based bypass attempts fail closed. The deny-list of credential and system paths cannot be disabled — the `dangerouslyAllowExternalBindSources` override relaxes only the allowed-roots check."
> —— `docs/gateway/sandbox-vs-tool-policy-vs-elevated.md`

这里"关键点"是最后一句:即便运维者显式打开了 `dangerouslyAllowExternalBindSources` 这个 opt-in 开关,它放宽的也只是"挂载源必须在工作区之内"这条 allowed-roots 检查,危险系统路径(`/etc`、`/proc`、`/sys`、`/dev`、`/root`、`/boot`)、Docker socket 目录、常见的家目录凭据根(`~/.aws`、`~/.ssh`、`~/.gnupg` 等)这份拒绝列表**不能被任何配置关闭**。这是一处典型的"break-glass 开关只解锁一个具体的检查项,而不是整体关闭安全校验"的设计模式,值得作为读其他 `dangerously*` 前缀配置项时的参照。

### Elevated 模式:从沙箱内逃逸到宿主机的受控通道

Elevated 模式解决的问题很具体:一个被沙箱化的 agent,有时确实需要在宿主机上跑一条命令(比如部署脚本触达沙箱看不到的资源)。`docs/tools/elevated.md` 给出了四个层级的指令:

> "| `/elevated on`   | Run outside the sandbox on the configured host path, keep approvals |
> | `/elevated ask`  | Same as `on` (alias) |
> | `/elevated full` | Run outside the sandbox on the configured host path and skip approvals when the mode/host approval policy is already permissive |
> | `/elevated off`  | Return to sandbox-confined execution |"
> —— `docs/tools/elevated.md`

这里"`full` 跳过审批"是有严格前提的——**只有当宿主的批准策略本身已经是完全放行状态时**,`/elevated full` 才会真的跳过审批;如果宿主批准策略仍然要求审批,`/elevated full` 并不会额外解锁一条绕过通道。下一节讲 exec approvals 时会看到这条前提具体是什么。

Elevated 生效需要同时满足全局开关和发送者白名单——两者缺一不可:

> "**Global gate**: `tools.elevated.enabled` (must be `true`)
> **Sender allowlist**: `tools.elevated.allowFrom` with per-channel lists
> **Per-agent gate**: `agents.entries.*.tools.elevated.enabled` (can only further restrict; both the global and per-agent gate must be `true`)
> **Per-agent allowlist**: `agents.entries.*.tools.elevated.allowFrom` (sender must match both global + per-agent)
> **All gates must pass**; otherwise elevated is treated as unavailable"
> —— `docs/tools/elevated.md`

文档还专门列出了 elevated **不**能做的事,这份清单和上一篇讲的三层边界互相印证:

> "- **Tool policy**: if `exec` is denied by tool policy, elevated cannot override it.
> - **Required role sandboxing**: if the authenticated session creator's operator role required a sandbox, elevated mode cannot run commands on the Gateway or a node.
> - **Host selection policy**: elevated does not turn `auto` into a free cross-host override. It uses the configured/session exec target rules, choosing `node` only when the target is already `node`."
> —— `docs/tools/elevated.md`

三条限制分别对应工具策略、creator role 强制沙箱、host 选择规则——elevated 从头到尾只是"把 exec 挪到宿主机上跑"这一件事,不触碰工具是否存在、会话是否必须沙箱化、跨主机路由这几层独立的判断。

### Exec Approvals:批准链路怎么把"审批"钉在具体的执行上下文上

Exec approvals 是"沙箱化 agent 在真实主机上跑命令"这条路径上的伴生守卫,`docs/tools/exec-approvals.md` 把它的定位说得很直接:

> "Exec approvals are the **companion app / node host guardrail** for letting a sandboxed agent run commands on a real host (`gateway` or `node`). Commands run only when policy + allowlist + (optional) user approval all agree. Approvals stack **on top of** tool policy and elevated gating (elevated `full` skips them)."
> —— `docs/tools/exec-approvals.md`

策略由 `security`(允许列表严格程度)和 `ask`(未命中时是否询问)两个旋钮组成,`tools.exec.mode` 是把两者打包成一个规范化档位:

| Mode | security / ask | Behavior |
| --- | --- | --- |
| `deny` | `deny` / `off` | Block host exec. |
| `allowlist` | `allowlist` / `off` | Run only allowlisted commands without asking. |
| `ask` | `allowlist` / `on-miss` | Use allowlist policy and ask on misses. |
| `auto` | `allowlist` / `on-miss` | Use allowlist policy, run deterministic matches directly, and send approval misses through OpenClaw's native auto reviewer before falling back to a human approval route. |
| `full` | `full` / `off` | Run host exec without approval prompts. |

`auto` 档位正是上一篇提到的"LLM 审核者"在 exec 层面的落地——未命中 allowlist 的命令先交给一个原生的自动审阅者判断,只有它也无法安全裁决时才退回人工。这条路径和会话权限模式(`workspace` 模式的"LLM review, with human fallback")共享同一套"先让模型判断、再退回人工"的设计取向。

值得强调的是**批准策略只能收紧,不能放宽**配置层的效果:

> "Effective policy is the **stricter** of `tools.exec.*` and approvals defaults: approvals can only tighten config-derived security/ask, never loosen them."
> —— `docs/tools/exec-approvals.md`

这意味着即使运维者把 `tools.exec.mode` 配成了 `full`,只要执行主机本地的 approvals 文档里还留着 `ask: "always"`,命令依然会被拦下来询问——本地主机状态永远是"取更严格的一方"这条规则的最终裁决者。这也解释了为什么开启 YOLO(完全免批准)模式需要同时改两层配置,而不是改一个开关就够:

> "| Layer              | YOLO setting               |
> | `tools.exec.mode`  | `full` on `gateway`/`node` |
> | Host `askFallback` | `full`                     |"
> —— `docs/tools/exec-approvals.md`

漏掉任何一层,"更严格的一方胜出"这条规则就会让命令继续卡在批准提示上——这不是 bug,而是这套"双层取严"设计刻意制造的摩擦,目的是防止运维者只改了应用层配置就以为自己已经关闭了所有审批。

批准这件事本身还绑定了具体的执行上下文,而不是只批准"这个命令字符串":

> "Approved node-host runs bind canonical execution context: cwd, exact argv, env binding when present, and pinned executable path when applicable.
> For shell scripts and direct interpreter/runtime file invocations, OpenClaw also tries to bind one concrete local file operand. If that file changes after approval but before execution, the run is denied instead of executing drifted content."
> —— `docs/tools/exec-approvals.md`

"批准之后、执行之前文件发生了变化就拒绝执行"这条规则,防的是一种典型的 TOCTOU(check-then-use)攻击面——如果批准的对象只是命令文本,而实际执行时读取的脚本文件内容已经被替换,那么"人工批准了这条命令"这件事就失去了意义。OpenClaw 选择把批准绑定到文件的具体快照上,漂移就拒绝执行,而不是假装自己完整覆盖了每一种解释器加载路径:

> "File binding is best-effort, not a complete model of every interpreter/runtime loader path. If exactly one concrete local file cannot be identified, OpenClaw refuses to mint an approval-backed run rather than pretend full coverage."
> —— `docs/tools/exec-approvals.md`

这句"pretend full coverage"是整份文档里最诚实的一句话之一——遇到无法唯一确定具体文件的解释器调用形式(比如包脚本、eval 形式、模糊的多文件加载链),OpenClaw 不会假装自己能安全批准,而是直接拒绝铸造一次带批准的执行。

自动化(cron)场景的批准还有一套独立的"standing grant"机制,值得单独一提,因为它和普通的 allowlist 条目性质不同:

> "When an approval originates from an automation's isolated run, resolving it with **Always allow** does not write a JSON allowlist entry. Instead the Gateway mints a scoped standing grant bound to that exact agent, automation, job configuration, and operation (command text, working directory, and requested environment)."
> —— `docs/tools/exec-approvals.md`

这个 grant 的失效条件同样很具体:任务配置被编辑、命令/工作目录/环境有一个字节不同、grant 被撤销或过期,都会让它"fail closed 回到正常提示",而不是继续沿用一个已经过期的授权语境。

### Crabbox:云沙箱厂商不做成插件,而是接到独立项目里

`VISION.md` 的"What We Will Not Merge (For Now)"一节列出了几类明确不会被合并进核心的贡献方向,其中一条直接点名了云沙箱厂商:

> "Cloud-based sandbox providers as OpenClaw plugins; implement provider support in [Crabbox](https://github.com/openclaw/crabbox) instead"
> —— `VISION.md`

这条决策背后的逻辑,和上一篇讲的"沙箱后端矩阵"放在一起看会更清楚。OpenClaw 核心目前维护的沙箱后端是 Docker、Podman、SSH、OpenShell 四种——它们的共同点是要么是通用容器运行时,要么是通过标准 SSH 协议对接任意远程主机。如果每接入一家云沙箱厂商(比如某个专门做 agent 沙箱托管的云服务)就在核心里加一个新插件,核心代码库会随着云沙箱市场的碎片化而持续膨胀,而且每家厂商的鉴权模型、生命周期管理、计费逻辑都不一样,很难收敛成一套干净的抽象。Crabbox 的定位就是承接这部分复杂度——它是一个独立仓库、独立维护节奏的项目,专门做"云端隔离执行环境的provider 接入层",OpenClaw 核心不需要为每一家云沙箱厂商单独写一个插件,而是把这件事交给 Crabbox 去做。

这条边界划分在 `AGENTS.md` 里也留下了具体痕迹——OpenClaw 项目自己的持续集成(CI)流程就是 Crabbox 的一个真实使用者,用来在隔离环境里对不受信任的贡献者代码做安全验证:

> "Untrusted contributor/fork code must not execute locally, including scripts, config, hooks, tests, or checks. Use secretless CI or sanitized direct AWS Crabbox under `$crabbox`. Credentialed execution requires maintainer approval after review; an explicit instruction to land named, reviewed PRs supplies that approval. Never hydrate an untrusted lease."
> —— `AGENTS.md`

以及:

> "Trusted development proof runs locally. Use Crabbox/Testbox when isolation, clean installation, packaging, Docker, live services, desktop, or platform behavior is part of the proof, or when explicitly requested. Reuse task-owned leases and clean them up under the owning skill."
> —— `AGENTS.md`

仓库根目录下的 `.crabbox.yaml` 进一步印证了这一点——它配置的是 OpenClaw 自己开发流程要用到的远程隔离执行环境(AWS、Azure、Blacksmith Testbox 三种 provider,分别用于不同强度的 CI 验证),而不是面向终端用户的 agent 沙箱执行后端。换句话说,Crabbox 首先是 OpenClaw **自己**用来获得"我需要一台干净的、隔离的、可复现的机器来验证某件事"这种能力的基础设施,同一套能力自然也能作为 agent 运行时的云端沙箱 provider 被复用——这解释了为什么 VISION.md 会把"云沙箱厂商接入"整体导向 Crabbox,而不是让每个贡献者各自往核心里加一个厂商插件:这件事本来就有一个专门的项目在做,而且 OpenClaw 项目自己也依赖它。

## 常见问题/易踩坑

- **"工具被沙箱工具策略挡住"的排障顺序**:文档给出的两条 fix-it 路径是——要么整体关掉沙箱(`agents.defaults.sandbox.mode=off`,但这不会覆盖 creator role 要求的强制沙箱),要么把该工具从 `tools.sandbox.tools.deny` 移除或加进 `tools.sandbox.tools.allow`;`openclaw logs` 里的 `agents/tool-policy` 条目会记录到底是哪条规则起了作用。
- **`non-main` 模式下"这明明是主会话为什么被沙箱化了"**——群组/频道的 session key 永远不算 `agent:<agentId>:main`,在 `non-main` 模式下会被当作非主会话直接沙箱化。
- **Elevated 不是万能逃生舱**——它只影响 exec,不授予任何额外工具;如果 `exec` 本身被工具策略拒绝,或者会话的 creator role 强制要求沙箱,elevated 完全无法绕过这两层。
- **YOLO 模式漏配一层等于没配**——`tools.exec.mode: "full"` 和执行主机本地 `askFallback: "full"` 必须同时设置,遗漏任何一层,"取更严格的一方"规则会让命令继续卡在批准提示上。
- **不要把"批准了这个命令"理解成"批准了这个命令字符串"**——OpenClaw 把批准绑定到精确的 cwd/argv/环境哈希,能确定具体文件时还会绑定文件快照;文件在批准后、执行前发生变化会被拒绝而不是继续执行。
- **遇到"接入某某云沙箱厂商"的诉求,先看 Crabbox 而不是提 OpenClaw 核心插件 PR**——这条路线在 `VISION.md` 里是明确写死的方向,核心维护者大概率会引导贡献者去 Crabbox 项目而不是合并一个厂商专属插件。

## 小结

这一篇把"为什么这个工具被挡住了"拆成了三层可以独立排查的控制:沙箱决定工具跑在宿主机还是某个隔离环境里,默认的 Docker 后端用无网络、只读根文件系统、丢弃全部 capability 这三件事把"模型做了蠢事"的波及范围压到最低;工具策略按名字过滤哪些工具存在,`deny` 永远赢,而且不检查 `exec` 内部的具体副作用;elevated 是专门给 exec 开的逃生舱,不授予额外工具,也无法突破 creator role 的强制沙箱。在这三层之上,exec approvals 把"批准"这件事钉在精确的执行上下文上——cwd、argv、环境哈希,能确定的话还有文件快照,批准之后发生任何漂移都直接拒绝执行而不是假装自己完整覆盖了所有场景。而"要不要把每一家云沙箱厂商都做成插件"这个问题,OpenClaw 给出的答案是否定的——这类需求被明确导向了 Crabbox,一个独立维护、OpenClaw 自己的 CI 也在用的云端隔离执行项目。下一篇要转向另一条同样关键但完全不同的防线:凭据怎么在不进入模型上下文的前提下被使用,以及审计日志留下的记录为什么永远不能被当成"这个操作已经被批准过"的证明。
