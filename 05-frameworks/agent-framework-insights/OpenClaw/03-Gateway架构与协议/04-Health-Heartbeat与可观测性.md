# Health、Heartbeat 与可观测性

> 这一章的前三篇分别讲了 Gateway 的协议骨架、设备信任模型、锁与远程访问——都是"怎么连上 Gateway、连上之后归谁管"的问题。这一篇转向另一个问题:**Gateway 自己怎么知道自己是不是健康的,外部系统又怎么知道**。这里有一个命名上的陷阱值得先说在前面——OpenClaw 协议里的 `heartbeat` 完全不是大多数人从基础设施经验里带来的那个直觉("心跳 = 存活探测")。搞清楚这一点,是理解这一篇后续所有内容的前提。

## 学习目标

- 理解 `health` 快照和 HTTP 探针(`/health`、`/startup`、`/ready`)各自回答什么问题,以及为什么不能只用一个端点应付所有场景。
- 弄清楚 OpenClaw 里 `heartbeat` 真正的含义——它是一个**周期性 agent 轮次的自动化**,不是进程存活探测;真正的连接存活探测另有其名(`tick`)。
- 对比 OpenTelemetry 和 Prometheus 两条可观测性集成路径的定位差异:推送 vs 拉取、需要的认证方式、能不能同时开启。
- 理解 Gateway 崩溃或重启后,进行中的 agent 会话是怎么被自动检测并续接的,以及这套恢复机制的安全阀(重试预算耗尽后的 tombstone、崩溃循环断路器)。
- 了解 launchd/systemd/Scheduled Task 这几种守护进程管理方式各自的关键约束。

## 背景与设计动机

一个常驻进程扛着所有消息渠道和客户端连接,意味着它一旦不健康,影响面是全局性的——不是"某个功能降级",而是"用户可能完全联系不上 Agent"。这就要求 Gateway 在健康与否这件事上必须做到两点:**对内,进程自己要能分辨出"我还活着"和"我活着但做不了事"这两种状态的区别;对外,不同的消费者(容器编排系统、人肉运维、时序数据库)需要不同粒度、不同协议的健康信息**。

同时,进程崩溃或重启在一个长时间运行 agent 工作流的系统里不是小概率的边缘情况,而是必须被设计进正常运行路径的场景——一次 npm 更新触发的重启、一次 OOM、一次宿主机休眠唤醒,都不应该让用户发出的一条消息就此石沉大海。这也是为什么"可观测性"和"重启恢复"要放在同一篇里讲:它们回答的都是同一个更大的问题——**这个常驻进程在不完美的现实世界里,怎么保持"值得信赖"**。

## 核心机制详解

### `health`:分层的健康契约,而不是一个布尔值

`docs/gateway/health.md` 描述的健康检查体系,第一个值得注意的设计是它**从来不是单一的"健康/不健康"二元判断**,而是按消费场景拆成了不同粒度的探针:

| 端点 | 含义 | 用途 |
| --- | --- | --- |
| `/health`、`/healthz` | HTTP 服务本身活着 | 进程存活判断和重启决策 |
| `/startup`、`/startupz` | 启动工作已完成,且 Gateway 不处于 draining 状态(不检查 channel 健康) | 编排系统的启动探针和流量准入 |
| `/ready`、`/readyz` | 启动完成、未在 draining、且配置的 channel 账号都通过深度就绪检查 | 需要感知渠道级故障的运维监控 |

—— `docs/gateway/health.md`

这三个探针故意划出了不同的严格程度:一个 Telegram 账号掉线,不应该让 Kubernetes 判定整个 Pod 不健康并反复重启它——`/startupz` 不检查 channel 健康,所以这种情况下 Control UI 依然可以正常服务;但运维如果想第一时间知道"某个渠道坏了",应该盯 `/readyz`。文档原话把这个区分说得很直接:

> "A broken Telegram or other channel account can make `/readyz` return `503` without taking a healthy Control UI out of service through `/startupz`."
> —— `docs/gateway/health.md`

另一个容易被忽略的设计细节是**"渠道连通"和"能收消息"是两个独立的故障域**:一个 channel 可能持有一条健康的传输层连接、正常发送回复,但它的持久化入站队列打不开,导致一条消息都收不进来。文档专门强调了这一点:

> "Channel connectivity and inbound admission are separate failure domains. A channel can hold a healthy transport connection — sending replies normally — while its durable ingress queue is unavailable, so not a single inbound message is admitted."
> —— `docs/gateway/health.md`

这类账号会被就绪检查判定为**不健康**,即使它的传输层看起来一切正常——这纠正了一个早期版本里"能连上就算健康"的误判。

面向人的调试入口是 `openclaw health` 命令,它默认返回一份缓存快照(Gateway 在后台异步刷新),`--verbose` 才会强制做一次实时探测。这个默认行为本身就是一种设计权衡:健康检查不应该因为自己的探测过程而给系统增加负担。健康快照里还有一个专门给运维盯的字段——`deliveryQueues.ingressPressure`,只有当某条持久化入站队列的积压达到一定阈值(至少 8 次投递尝试且有记录的错误,或者一条已认领的记录 30 分钟没有刷新认领)才会出现,平时是完全省略的,这样报警只在真正值得关注时触发,不会被正常的重试噪声淹没。

文档还专门强调了一个反直觉的实践建议:**不要用 `/v1/chat/completions` 做存活探测**,因为每次调用都会创建一个完整的 agent 会话(带上下文组装和模型调用);外部监控服务应该固定打 `/health`,它不创建会话、不调用模型,只返回 `{"ok":true,"status":"live"}`。

### `heartbeat`:一个容易被名字误导的机制

如果只看名字,大多数人会假设 `heartbeat` 是类似 TCP keepalive 那种"证明连接还活着"的信号。但 `docs/gateway/heartbeat.md` 开篇第一句话就否定了这个直觉:

> "Heartbeat is a system-owned automation that runs **periodic agent turns** in the main session so the model can surface anything that needs attention without spamming you."
> —— `docs/gateway/heartbeat.md`

也就是说,OpenClaw 的 `heartbeat` 是一个**周期性触发的、真实消耗一次模型调用的 agent 轮次**——它存在的目的是让模型有机会主动检查"有没有什么需要我关注的事情",而不是一个基础设施层面的存活信号。默认间隔是 30 分钟(如果解析出的认证模式是 Anthropic OAuth/token,包括复用 Claude CLI,会自动改成 1 小时),默认提示词非常克制:

> "Follow the heartbeat monitor scratch context when provided. Recurring tasks are automations; create or change their schedules with the automations tool, not heartbeat scratch. Do not infer or repeat old tasks from prior chats. If nothing needs attention, reply NO_REPLY."
> —— `docs/gateway/heartbeat.md`

真正对应"连接层面周期性存活信号"这个直觉的,其实是**另一个完全独立的事件** `tick`——`docs/gateway/protocol.md` 的事件族列表把两者分得很清楚:

> - `tick`: periodic keepalive/liveness event.
> - `health`: gateway health snapshot update.
> - `heartbeat`: heartbeat event stream update.
> —— `docs/gateway/protocol.md`

第一篇的连接生命周期时序图里,握手完成后 Gateway 推送的正是 `event:tick`,而不是 `event:heartbeat`——这不是笔误,而是两个概念本来就该分开:`tick` 回答"这条 WS 连接和后端进程是否还活着",`heartbeat` 回答"该不该让模型主动看一眼有没有需要处理的事情"。理解了这一点,再看 `heartbeat.md` 里"heartbeat cadence is owned by the Automations scheduler"这句话就顺理成章——它本质上是**一种被特殊对待的、系统内置的自动化任务**,和用户自己配置的 cron 任务共享同一套调度基础设施,只是多了一层"安静优先"的默认行为:如果没有需要汇报的事情,模型被要求直接回复 `NO_REPLY`,并且默认在渠道侧会被隐藏,不会真的打扰用户。

理解这个区分之后,`docs/gateway/health.md` 里的一句话就有了更准确的读法:

> "The same heartbeat drives the bounded stability recorder: `openclaw gateway stability`."
> —— `docs/gateway/health.md`

这里的"heartbeat"指的是驱动 diagnostics 定期采样的内部调度节拍(和 agent 轮次的 `heartbeat` 共享同一套底层调度器抽象),不是本节讨论的"周期性 agent 轮次"本身在做诊断采样。这也是这套系统里"heartbeat"这个词在不同上下文被复用、需要根据语境分辨具体所指的一个例子。

### OpenTelemetry 与 Prometheus:两条独立但可以并存的路径

Gateway 内部有一套统一的"诊断事件总线"(`diagnostics.enabled`,默认开启),记录模型调用、消息流转、会话状态、队列压力等结构化事件,但不含聊天内容、密钥这类敏感数据。OpenTelemetry 和 Prometheus 这两条可观测性路径,都只是"订阅同一份诊断事件、转换成各自协议格式"的独立插件,彼此不冲突,可以同时开启:

| 维度 | OpenTelemetry(`diagnostics-otel` 插件) | Prometheus(`diagnostics-prometheus` 插件) |
| --- | --- | --- |
| 传输模型 | **推送**:Gateway 主动把数据发给 OTLP collector | **拉取**:Gateway 暴露一个 HTTP 端点,等外部 scraper 来抓 |
| 数据类型 | 指标(metrics)、链路追踪(traces)、日志(logs)三种信号都支持,可独立开关 | 只有指标(Prometheus 文本格式),不含 traces/logs |
| 端点/认证 | 无本地端点概念,直接对外发 OTLP/HTTP(protobuf) | `GET /api/diagnostics/prometheus`,**走 Gateway 认证**(operator scope),不是裸露的公共 `/metrics` |
| 典型消费场景 | 已经有集中式可观测性后端(Grafana Tempo、Datadog、Honeycomb、New Relic)、需要跨服务关联链路 | 已经有 Prometheus/VictoriaMetrics 抓取基础设施,只关心指标 |

Prometheus 文档特别强调了这个端点不是传统意义上"裸奔"的 `/metrics`:

> "The route uses Gateway authentication (operator scope, trusted-operator surface). Do not expose it as a public unauthenticated `/metrics` endpoint."
> —— `docs/gateway/prometheus.md`

这是一个容易在迁移已有监控栈时踩的坑——很多 Prometheus 生态的默认约定是"`/metrics` 端点不需要认证,靠网络隔离保护",但 OpenClaw 反过来把这个端点纳入了和其他 operator API 一样的认证体系里,scrape 配置必须显式带上 token。

两条路径共享同一个前提开关和同一份底层数据源(`diagnostics.enabled`),这解释了为什么它们可以真正独立并存,而不是"二选一"——两个插件各自向同一条诊断事件总线订阅,互不知道对方的存在。一个团队完全可以既往 Grafana Tempo 推链路追踪,又让 Prometheus 抓指标做告警,这不是文档里的一种"可选组合",而是架构上两条彻底解耦的路径的自然结果。

### 崩溃与重启后:进行中的会话怎么被找回来

`docs/gateway/restart-recovery.md` 描述的这套机制,建立在一个基本承诺上:

> "Conversations, transcripts, scheduled jobs, background task records, and queued outbound messages live on disk... eligible work interrupted mid-turn is detected and resumed automatically."
> —— `docs/gateway/restart-recovery.md`

**中断检测靠三种互补的机制叠加**,而不是单一信号:

> "Three complementary mechanisms mark sessions whose turn did not finish: At turn admission ... At shutdown ... At startup: the gateway scans session stores for sessions that still claim to be running but have no live owner in the new process."
> —— `docs/gateway/restart-recovery.md`

也就是说:一次正常的用户消息进来,Gateway 在真正开始处理之前,先在同一个 SQLite 事务里把"这个会话正在跑一个 turn"这件事记下来;如果 Gateway 是被正常请求重启(而不是硬崩溃),关闭前的 drain 阶段还会再补一次标记;如果是 `SIGKILL` 或者宿主机断电这种没有机会走正常关闭流程的场景,新进程启动后会扫一遍所有声称"正在运行"但实际没有存活所有者的会话——这一条兜底机制专门用来应付前两条都来不及执行的硬崩溃。

自动恢复的方式很朴素——**给模型发一条合成的系统消息,告诉它"你上一个 turn 被重启打断了,接着已有的记录继续"**,如果重启前已经生成了回复只是还没发出去,会把这段文本一并带上,让模型选择直接投递而不是重新生成一遍。这个恢复过程有一套**有限重试预算**,防止一个反复失败的会话无限循环重试:

> "Each interrupted main-session cycle has a durable budget of three charged automatic dispatch attempts, retained across gateway restarts... After the durable budget is exhausted, the session is tombstoned instead of looping forever."
> —— `docs/gateway/restart-recovery.md`

三次机会用完之后,这个会话会被打上"墓碑"标记,不再自动重试,需要人工用 `/new` 或 `/reset` 开一个新会话——这是一个刻意的取舍:相比"无限重试一个可能永远无法恢复的会话",宁可尽早放弃并暴露给人工处理。恢复过程还会做一层安全判断:如果中断前的最后一步操作涉及有副作用的外部动作(比如一条消息是否真的发出去了、一次工具调用的结果是否落地),且这个结果是不确定的,恢复时会把这次续接限制在"restart-safe"的工具集合内,不会自动重放那个可能已经产生过副作用的操作。

**正常的计划内重启(比如 `openclaw gateway restart`、配置变更、更新)不会立刻打断进行中的工作**,而是先停止接收新请求,再等待现有的 agent turn 和后台任务完成,给一个默认 5 分钟的 drain 窗口:

> "A requested restart ... does not kill in-flight work immediately. The gateway stops accepting new work, then waits for active agent turns and background tasks to finish, up to a drain budget (5 minutes by default). Most restarts therefore interrupt nothing at all."
> —— `docs/gateway/restart-recovery.md`

在 Linux 上,这个优雅关闭依赖 systemd unit 的一个具体配置——`KillMode=mixed`,只让最初的停止信号送到 Gateway 主进程本身,而不是立刻把所有子进程一起杀掉:

> "On Linux, the systemd unit must use `KillMode=mixed` so the initial stop signal reaches only the Gateway. ... Older `KillMode=control-group` units signal child runtimes immediately, which can interrupt a turn before drain finishes."
> —— `docs/gateway/restart-recovery.md`

这解释了为什么升级之后需要重新 `openclaw gateway install --force`——如果 systemd unit 文件本身没有更新,drain 逻辑再完善也没用,因为子进程(比如某个 exec 工具启动的子命令)可能在 Gateway 主进程还没来得及优雅关闭时就已经被信号杀掉了。

**崩溃循环断路器**是另一道安全阀,专门防止"启动失败 → 自动重启 → 又失败"这种模式把问题放大:

> "3 unclean boots within 5 minutes trip a breaker that suppresses auto-start side services on the next boot ... the control plane still starts, but channel plugins (and other auto-started side services) stay down until an operator manually overrides the suppression."
> —— `docs/gateway/restart-recovery.md`

这里的分寸感值得注意:断路器只抑制"渠道自动启动"这类副作用较大的操作,**控制平面本身依然会启动**——也就是说,即使触发了断路器,运维依然可以连上 Gateway 检查状态、看日志、手动修复配置,而不是被彻底挡在门外。这套恢复行为对外可观测——恢复动作会记录到 Prometheus 指标(`openclaw_session_recovery_total`、`openclaw_session_recovery_age_seconds`)和专门的日志子系统(`main-session-restart-recovery`),运维不需要靠猜测判断"重启之后到底恢复了几个会话"。

### 守护进程管理:launchd / systemd / Scheduled Task

Gateway 本身只是一个前台运行的进程,真正的"崩溃后自动拉起来"依赖操作系统级别的服务管理器,`docs/gateway/index.md` 的 Supervision 一节给出了三大平台各自的关键约束:

- **macOS(launchd)**:`openclaw gateway stop` 默认走 `launchctl bootout`,只是从当前启动会话里移除 LaunchAgent,不持久化禁用——这意味着 `KeepAlive` 自动恢复机制在意外崩溃后依然生效,下次 `gateway start` 也能正常重新启用。如果确实想持久化关闭自动重启,要显式加 `--disable`。
- **Linux(systemd user/system unit)**:除了前面提到的 `KillMode=mixed`,配置里还有一个值得注意的约定——**非法配置导致的启动失败会以退出码 `78` 退出**,配合 unit 文件里的 `RestartPreventExitStatus=78`,让 systemd 不会对着一个"配置本身就是错的"场景无限重启。launchd 和 Windows 任务计划程序没有对等的"按退出码停止重试"机制,所以 Gateway 转而在这两个平台上自己维护一份"最近是否发生过快速的不干净启动"的历史记录,用前面提到的崩溃循环断路器来达到类似的保护效果。
- **Windows(Scheduled Task)**:如果创建计划任务被拒绝,会退化成一个基于用户级启动文件夹的启动器,指向状态目录内的 `gateway.cmd`。

这三种机制虽然平台实现完全不同,但都在服务同一个目标:**让"进程崩溃后自动拉起"这件事不依赖任何人守着屏幕**,而重启之后具体怎么把中断的工作续上,就回到了上一节的会话恢复机制。

## 常见问题/易踩坑

- **不要把 `heartbeat` 当成连接存活探测**——它是一个会真实消耗模型调用的周期性 agent 轮次,真正的连接层面存活信号是 `tick`。如果只是想知道"Gateway 进程是否还在运行",应该看 `health`/`/health` 探针,而不是 `heartbeat` 事件。
- **不要用 `/v1/chat/completions` 做外部监控的存活探测**——每次探测都会创建一个新的完整 agent 会话,长期高频探测会导致会话存储膨胀。
- **不要把 Prometheus 的 `/api/diagnostics/prometheus` 当成传统意义上不需要认证的 `/metrics` 端点**——它复用 Gateway 的 operator 认证体系,scrape 配置必须携带有效的 token。
- **不要在 Linux 上跳过 `openclaw gateway install --force`**——如果 systemd unit 文件还停留在旧的 `KillMode=control-group`,升级到支持优雅 drain 的版本也没有意义,子进程依然会在信号发出的瞬间被一起杀掉。
- **会话恢复不是无限重试**——耗尽三次续接预算之后会被 tombstone,这是刻意设计的止损点,遇到反复恢复失败的会话应该直接用 `/new`/`/reset` 而不是等待它自己好转。

## 小结

这一篇把"Gateway 怎么知道自己健不健康、外部系统怎么观测它、崩溃之后怎么自愈"这三件事串了起来:`health` 用分层的 HTTP 探针回答不同粒度的健康问题,`heartbeat` 这个名字虽然容易引起误解、实际却是一个周期性的 agent 主动检查机制,OpenTelemetry 和 Prometheus 是两条订阅同一份诊断事件总线、彼此独立又可以并存的可观测性路径,而重启恢复机制则用"三层中断检测 + 有限重试预算 + 崩溃循环断路器"把"进程可能随时挂掉"这个现实约束,转化成了用户几乎感知不到的自动续接体验。至此,第三章把 Gateway 作为控制平面的协议、信任模型、多实例治理和运行时可观测性都讲完了。下一章会把视角从"Gateway 这个进程本身怎么运转"转向"Gateway 内部驱动的 Agent 核心循环和会话系统"——也就是当一条 `req:agent` 真正被接受之后,内部到底发生了什么。
