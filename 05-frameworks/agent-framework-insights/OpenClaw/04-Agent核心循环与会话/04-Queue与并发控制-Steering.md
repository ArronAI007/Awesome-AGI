# Queue 与并发控制:Steering

> 第一篇提到过"同一个 session key 在同一时刻只能有一个 run 在真正执行"这条铁律,但没展开讲后来的消息该怎么办——是排队等待,还是想办法插进正在跑的这次运行里?OpenClaw 用命令队列(Command Queue)回答"怎么排队、多大并发",用引导队列(Steering Queue)回答"消息该不该、以及怎么插进一次仍在流式输出的运行"。这是本章分量不轻的一篇,也是最适合和姊妹课程 Hermes-Agent 的三级中断机制(`interrupt`/`hard_interrupt`/`steer`/`redirect`)做对比的一篇——两个系统解决的是同一类问题,但设计取向有明显差异。

## 学习目标

- 理解两级 lane(会话级 lane + 全局 lane)如何分别保证"同一会话不并发"和"总体并发有上限"这两条独立的约束。
- 理解 `/queue` 四种模式——`steer`/`followup`/`collect`/`interrupt`——在"活跃运行中的行为"和"稍后行为"两个维度上的完整矩阵。
- 理解 `steer` 模式下引导消息真正插入的时机:模型边界和工具启动边界,以及为什么"已经在跑的工具"永远不会被打断。
- 理解 OpenClaw 内部的引导队列和 Codex 原生 `turn/steer` 在实现颗粒度上的差异,以及这种差异如何反映"谁拥有工具调度权"这条更底层的边界。
- 能够说清楚 OpenClaw 的四模式设计和 Hermes-Agent 三级中断机制的相似与不同,而不是简单套用后者的概念。

## 背景与设计动机

一个常驻的 Gateway 进程,同一时刻可能面对完全不相关的多路输入:某个用户连发了几条消息、另一个群聊也在活跃、心跳定时触发、子代理完成通知需要回灌——如果不做任何排队控制,单是"多个 LLM 调用同时抢占同一个会话的事务日志"就足以造成状态混乱,更不用说上游 provider 的速率限制会被瞬间打爆。文档把这个问题的动机说得很直接:

> Auto-reply runs can be expensive (LLM calls) and can collide when multiple inbound messages arrive close together.
> Serializing avoids competing for shared resources (session state, logs, CLI stdin) and reduces the chance of upstream rate limits.

但纯粹的排队会牺牲交互体验——如果一个用户在代理执行一次需要几分钟的工具调用期间,想临时补一句"改成用中文回复"或者"其实不用查这部分了",让这句话老老实实排在队尾等上几分钟,是很糟糕的体验。这就是为什么排队之上还需要一层"引导"(steering)——**把新消息安全地送进正在跑的运行内部,而不是简单地排队等待**。这两层合起来,才是 OpenClaw 对"并发消息怎么处理"这个问题的完整答案。

## 核心机制详解

### 两级 lane:会话级串行 + 全局并发上限

排队系统是一个"lane 感知的 FIFO 队列",每条 lane 有独立的并发上限:

> A lane-aware FIFO queue drains each lane with a configurable concurrency cap (default 1 for unconfigured lanes; `main` uses `min(16, max(8, available CPU parallelism))`, and `subagent` defaults to 8).

具体的排队路径分两步:CLI、内嵌运行时、Codex 运行时共享同一个**会话级 lane**(`session:<key>`)——不管换成哪种运行时来执行,同一个会话键都在同一条 lane 里排队,"so changing runtimes cannot start a competing turn"。通过这一关之后,每个会话运行还要进入一个**全局 lane**(默认 `main`),由 `agents.defaults.maxConcurrent` 限定总体并发。

这个两级设计解决的是两个独立的约束:第一级保证"同一个会话永远不会被两次并发执行撕裂",第二级保证"哪怕开了再多会话,总的模型调用并发也有一个受控上限"——避免海量并发会话同时命中同一个 provider 而集体触发限流。除了 `main`/`subagent` 之外,还有 `cron`/`cron-nested`/`nested` 等 lane 服务不同性质的后台工作,"so background jobs can run in parallel without blocking inbound replies"。

### /queue 四种模式:一张完整的行为矩阵

`/queue` 控制的是"会话已经有一个活跃运行时,新消息该怎么办"。四种模式在"活跃运行行为"和"之后行为"两个维度上分别是:

| 模式 | 活跃运行时的行为 | 之后的行为 |
| --- | --- | --- |
| `steer` | 引导消息进入当前运行时 | 引导不可用时,等当前运行结束再开始 |
| `followup` | 不引导 | 当前运行结束后作为一次新的轮次单独运行 |
| `collect` | 不引导 | 静默窗口后,合并成一个轮次 |
| `interrupt` | 中止当前运行 | 中止后立即运行最新消息 |

默认模式是 `steer`,配合内置 500ms 的静默去抖(debounce)。这四种模式的语义差异,本质上是在"打断已经发生的事情"和"引导接下来要发生的事情"这两种完全不同的意图之间做选择——`interrupt` 是前者,`steer` 是后者,`followup`/`collect` 干脆放弃介入当前运行,只管理"之后"。

### steer 的具体实现:工具启动边界与模型边界

`steer` 不是简单地把新消息塞进对话历史就完事——它要处理"运行时此刻正好在做什么"这个时序问题。文档描述的边界检查逻辑分两种情况:

**顺序模式(sequential)**:

> 1. The assistant asks for tool calls.
> 2. OpenClaw checks immediately before each call starts, including after asynchronous resolution, validation, and pre-execution hooks.
> 3. A running call finishes. If a steer is waiting afterward, the unstarted sequential tail is skipped.

**并行模式(parallel)**:

> In parallel mode, OpenClaw prepares calls first, then checks once immediately before launching the prepared calls. Calls that have crossed that checkpoint continue together.

这两条规则背后是同一条原则:**已经开始执行的工具调用永远跑完,没开始的可以被跳过**。顺序模式下逐个检查,一旦有引导消息在等,还没开始的后续调用会被整体跳过;并行模式下由于一批调用是"一次性启动检查点",跨过这个检查点之后就没有回头路,只能整批继续跑完。跳过的调用不会留下结构性的空洞:

> Every skipped call receives paired tool start/end events and a synthetic error result (`Skipped due to queued user message.`), in assistant source order.

跳过的调用会收到一个语义明确的合成错误结果(`Skipped due to queued user message.`),这样对话事务日志依然保持结构完整——每一次工具调用请求都有对应的结果,不会出现"请求了但没有结果"的裸调用,这和上一篇 Compaction 里"绝不能切断工具调用/结果配对"的约束是同一条原则在不同机制里的重复应用。所有跳过和引导消息就绪之后,"OpenClaw appends the exact drained steering message before the next LLM call"——引导消息会在下一次模型调用之前被真正追加进去,确保它在模型做下一次决策之前必然可见。

### 已启动 vs 已请求:两个术语的精确区分

Steering Queue 文档专门用一节强调这组区分:

> - A sequential call that is already running completes. Later calls have not started, so OpenClaw returns synthetic skipped results for them and lets the model reconsider with the steer visible.
> - A parallel batch has one atomic launch checkpoint. A steer present before it suppresses all prepared calls; a steer arriving after it does not recall any of them.
> - Validation or policy outcomes finalized before the parallel checkpoint remain truthful. Only executable calls that did not start receive the steering skip result.

第二条尤其值得注意——并行批次的启动检查点是**原子的**:引导消息如果在检查点之前到达,能拦下整批还没启动的调用;如果在检查点之后才到达,哪怕只差一点点,也无法召回任何一个已经跨过检查点的调用。第三条进一步澄清:如果某个调用在检查点之前就已经因为校验失败或策略拒绝而终结,这个结果是真实的,不会被引导逻辑事后"补一个假的跳过结果"去覆盖——只有"本该执行但还没启动"的调用,才会被替换成引导跳过结果。

### OpenClaw 内部引导 vs Codex 的 turn/steer:谁拥有工具调度权

这一节的对比揭示了"运行时边界"这个第一篇提到过的概念,在引导机制上的具体体现。OpenClaw 自己的运行时对引导有细粒度的工具启动边界控制;而 Codex app-server 完全是另一套模型:

> The native Codex app-server harness exposes `turn/steer` instead of OpenClaw runtime's internal steering queue. OpenClaw batches queued prompts for the configured quiet window, then sends a single `turn/steer` request with all collected user input in arrival order. Codex's upstream turn scheduler owns its tool scheduling and consumes accepted steering at the next model boundary; OpenClaw does not add per-tool preemption to that runtime.

也就是说,面对 Codex 这种把工具调度权完整留在自己手里的外部运行时,OpenClaw 放弃了对单个工具调用做细粒度抢占的尝试,退化成"攒够一个静默窗口,打包成一次 `turn/steer` 请求"——**引导的最终生效边界从"每个工具调用"退化成"下一次模型边界"**,因为 OpenClaw 根本不掌握 Codex 内部工具调度的执行细节。这正是第一篇讲运行时归属那张对照表("Model loop owner"/"Native shell and file tools" 谁拥有什么)在引导机制上的一个具体投影——**谁拥有循环,谁就决定引导能做到多细**。

另外两种情况直接放弃同轮引导,只能退化成排队:"Codex review and manual compaction turns reject same-turn steering"——代码审查和手动压缩这两类特殊轮次不接受同轮引导;而"Without streaming, steering falls back to a followup after the active run when the runtime cannot accept same-turn steering"——不支持流式的运行时同样只能退化成 followup。

### interrupt 与 steer:柔性引导 vs 强制中止

`steer` 和 `interrupt` 的边界文档划得很清楚:"`steer` does not abort in-flight tools. ... Use `/queue interrupt` when the newest message should abort the current run."`steer` 从设计意图上就不是用来打断已经在做的事情,而是用来"柔性地重新引导接下来的方向";真正想要"立刻停下、按最新消息重新开始",必须显式切到 `interrupt` 模式,或者用 `/stop` 这个更直接的命令。这条边界防止了一个容易犯的直觉错误——把"改主意"和"叫停"混为一谈。

### 排队中的可取消性

即便消息还在排队(followup/collect 队列里),Gateway 依然维护一个可取消的身份:"Gateway keeps a **Gateway-owned cancel identity** for that client `runId` until the queued content runs or is dropped"。`chat.abort` 带具体 `runId` 可以取消一个仍在排队的轮次;不带 `runId` 时,取消顺序是"先取消已授权的排队轮次,再中止已授权的活跃运行"——这个顺序是刻意设计的:"That order prevents queue drain from promoting work into a half-stopped session"(防止队列排空的动作把新工作提升进一个"半停止"状态的会话)。

### 后台工作:独立于前台回复容量的预算

Skill Workshop 审查、插件后台完成(包括 dreaming)共享一个独立的预算——**三个并发运行**,与前台回复容量完全隔离:

> This keeps maintenance work out of foreground reply capacity while bounding its total concurrency.

一个容易被忽略但设计上很讲究的细节:调度者本身不占用这个预算,只有被派发的工作真正占用一个槽位:"Schedulers that await background work do not occupy this budget themselves. Only the dispatched work holds a slot ... so a scheduler cannot block the child it is waiting for"——如果调度者本身也要占一个槽位,等待自己的孩子完成就可能因为槽位耗尽而死锁,这是一个典型的资源分配设计陷阱,OpenClaw 显式避开了它。

### 诊断:忙、卡滞、卡死的三级分类

诊断系统对长时间处于 `processing` 状态且没有可观测进展的会话做分级,和第一篇结尾提到的分类完全一致,这里从队列诊断的角度再补充一次实际触发的恢复行为:

> `session.stuck` always triggers recovery that can release the affected session lane. A `session.stalled` classification past the abort threshold (blocked tool call, stalled model call, or stalled embedded run) can also trigger active-abort recovery, so both classifications can unstick a queue, not only `session.stuck`.

这条规则纠正了一个容易产生的误解——不是只有最严重的 `session.stuck` 才会触发恢复,`session.stalled` 越过中止阈值之后同样能触发主动中止恢复,两种分类都能解开一个卡住的队列。

### 和 Hermes-Agent 三级中断机制的对比

Hermes-Agent 的中断体系(在姊妹课程第九篇讲过)是 `interrupt`/`hard_interrupt`/`steer`/`redirect` 四个动词构成的三级强度模型,核心思路是显式区分"打断的强度"。OpenClaw 的 `/queue` 四模式表面上词汇相似(同样有 `steer`、`interrupt`),但设计轴线并不完全对应:

- **相似之处**:两个系统都承认"打断正在执行的东西"和"引导接下来的方向"是两类不同强度的意图,都不满足于"要么排队、要么直接杀掉重来"这两个极端。
- **不同之处一:粒度归属不同**。Hermes 的 `steer` 是模型层面的一个显式动作原语,由调用方决定何时触发;OpenClaw 的 `steer` 是**队列模式**,一旦选定,后续所有普通消息都按这个模式处理,真正的插入时机(工具启动边界/模型边界)由运行时自动判定,不需要调用方逐次决定。
- **不同之处二:OpenClaw 把"要不要引导"和"引导不进去怎么办"耦合在同一个模式定义里**——`steer` 模式本身包含了退化路径("引导不可用时,等当前运行结束"),而不是让调用方在引导失败后手动决定下一步该发起哪种动作。
- **不同之处三:OpenClaw 的引导边界会因运行时而变化**。上一节讲到的"OpenClaw 内部引导可以做到工具启动边界级别的抢占,而 Codex 只能做到模型边界级别的批量引导"这件事,在 Hermes 的架构里没有直接对应物——因为 Hermes 的子代理都跑在同一个进程内的同一套循环里,不存在"外部运行时拥有自己的工具调度权"这类边界问题。

这个对比说明,两个系统虽然都在解决"运行时怎么响应中途变化的用户意图"这同一类问题,但 OpenClaw 的设计更多是"把复杂度收敛进几个队列模式,由运行时内部自动判定插入边界",而 Hermes 把"打断强度"做成了模型可以显式调用的动词——这也是两个系统整体架构差异的一个缩影:OpenClaw 是一个常驻 Gateway 服务多渠道消息,天然需要"队列模式"这种可配置、可持久的策略层;Hermes 更接近单次会话内的显式工具调用编排。

## 常见问题/易踩坑

- **`steer` 不会打断正在跑的工具**:这是最容易被误解的一点。想要真正打断,必须用 `/queue interrupt` 或 `/stop`。
- **`collect` 遇到不同渠道/线程目标时会拆开单独 drain**:"If messages target different channels/threads, they drain individually to preserve routing"——不要假设 `collect` 一定把所有排队消息合并成一条。
- **静默窗口不适用于 `steer` 的实际引导动作**:"OpenClaw active steering does not use the debounce timer; at tool-launch and model boundaries it drains FIFO according to the runtime's configured steering drain mode"——去抖窗口只影响 `followup`/`collect` 的排队投递,不影响 `steer` 真正把消息插进运行时的时机。
- **优先级解析顺序容易搞反**:模式选择的优先级是"内联/存储的会话级 `/queue` 覆盖" > "按渠道配置" > "全局配置" > "默认 `steer`";而具体的选项(debounce/cap/drop)优先级是"内联/存储的会话覆盖" > "按渠道 debounce" > "插件默认" > "内置默认"——两条优先级链并不完全一致,混着记容易出错。

## 小结

这一篇讲了两级 lane 怎么保证会话串行和全局并发上限、四种 `/queue` 模式的完整行为矩阵、`steer` 在工具启动边界和模型边界的精确插入时机,以及 OpenClaw 内部引导和 Codex `turn/steer` 之间因"工具调度权归属"不同而产生的粒度差异,最后和 Hermes-Agent 的三级中断机制做了一次基于事实的对比。到这里,第四章关于"单个 Agent 怎么循环、单个会话怎么管理上下文、多路消息怎么排队"的内容已经讲完了三个层次。但个人助理系统很快会遇到下一个问题——一个任务复杂到需要拆给别的代理去做时,系统该怎么组织"多代理协作"。这正是本章最后一篇、也是分量最重的一篇要讲的内容:多代理协作与 Delegate 架构。
