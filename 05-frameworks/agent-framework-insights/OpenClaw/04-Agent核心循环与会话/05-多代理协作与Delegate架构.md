# 多代理协作与 Delegate 架构

> "多代理"这个词在 OpenClaw 文档里其实对应三个完全不同的层次,读之前不先分清楚,很容易把它们混为一谈:第一层是**多 Agent 路由**——在同一个 Gateway 进程里跑多个互相隔离的"人格"(各自的工作区、鉴权、会话存储),靠 binding 把不同渠道账号路由到不同人格,这解决的是"一个 Gateway 服务多个身份"的问题,不是任务委派;第二层是**Delegate 架构**——在多 Agent 路由基础上叠加的一种组织场景应用(一个"代理人"身份代表人类在组织内行事,分级授权),它同样不是任务委派机制,而是身份和权限模型;第三层才是真正对应 Hermes-Agent 课程讲过的 `delegate_task` 的机制——`sessions_spawn`/`sessions_yield`/`subagents` 这组会话工具,一个 Agent 在**同一个人格内部**把具体任务拆给隔离的子会话去跑。本篇按这三层依次展开,重点落在第三层的子代理生命周期、并行专家赛道的资源设计,以及子代理让渡/交接(yield/handoff)怎么解决"控制权什么时候还给谁"这个问题,最后和 Hermes 的 `delegate_task` 做一次基于事实的对比。

## 学习目标

- 分清"多 Agent 路由"(人格边界)、"Delegate 架构"(组织代理人身份)、"子代理生成"(`sessions_spawn`,任务委派)这三个概念在 OpenClaw 文档体系里各自对应什么,不要把它们当作同一件事的三种叫法。
- 理解 `sessions_spawn` 怎样构造一个隔离的子会话:上下文模式(`isolated` vs `fork`)、工具面收窄(不默认拿到会话/消息工具,只注入 `AGENTS.md`)、深度分级(orchestrator vs leaf,由深度和开关推导而非调用方自称)。
- 理解"并行专家赛道"(Parallel Specialist Lanes)把并行当成稀缺资源问题来设计的三阶段推进路径,以及它到底在优化哪五种争用资源。
- 理解 `sessions_yield` 解决的问题和子代理让渡/交接(yield/handoff)背后的注册表(registry)所有权模型:一次让渡怎样把"完成的所有权"从旧的执行转移到新的后继执行,同时保证只有一个完成所有者。
- 能够说清楚 OpenClaw 的子代理机制和 Hermes-Agent `delegate_task` 的相似与不同,而不是简单套用后者的具体实现细节。

## 背景与设计动机

个人助理型系统迟早会遇到这类任务:一次调研需要读几十个文件、跑几十次工具调用、试错好几轮,如果全部塞进主对话的上下文,会迅速把主对话的上下文窗口填满——而这些中间过程对主对话接下来要做的决策通常没有意义。这正是 Hermes-Agent 课程讲过的核心论点:"父级只看到委派调用和摘要,不需要看到全部中间过程"。OpenClaw 面对的是同一个问题,但它的答案不是一个单独的"delegate 工具",而是一组更细粒度的会话原语(`sessions_spawn`/`sessions_yield`/`subagents`)——这组原语本身又要服务于一个更大的系统:一个 Gateway 进程可能同时要伺候多个人格(多 Agent 路由)、每个人格内部又可能同时有若干条并行工作(专家赛道),这些并行工作还要在正确的时间点把结果交还给正确的对话(yield/handoff)。三层需求叠在一起,才是这一篇要讲的完整图景。

## 核心机制详解

### 第一层:多 Agent 路由——人格边界,不是任务委派

`multi-agent.md` 定义的"Agent"是一个完整的人格作用域:

> An **agent** is the full per-persona scope: workspace files, auth profiles, model registry, and session store.

每个 `agentId` 拥有自己的工作区(`AGENTS.md`/`SOUL.md`/`USER.md`)、状态目录(`agentDir`,存放鉴权 profile 和模型注册表)、会话存储(`<agentDir>/openclaw-agent.sqlite`)。**Binding** 是把一个渠道账号(某个 Slack 工作区、某个 WhatsApp 号码)映射到某个人格的规则,匹配维度包括 `accountId`、`peer`、`guildId`/`teamId`、`roles`,精度从"整个渠道兜底"到"某一个具体的私聊/群/频道"逐级细化,同一优先级内"配置顺序里第一条命中的赢"。

这一层解决的是"一个 Gateway 进程如何服务多个互相隔离的身份",例子包括:同一台服务器托管多个 WhatsApp 号码、不同 Discord 机器人账号映射到不同人格、把某个客服邮箱路由到专门的客服人格。跨 Agent 的会话可见性由 `tools.agentToAgent` 单独控制,默认开启——"cross-agent session access on by default and governed by `tools.agentToAgent`"。这条边界和接下来两层要讲的"子代理"完全是不同维度的隔离:多 Agent 路由隔离的是**持久的、长期存在的人格**,子代理隔离的是**一次性的、任务范围内的临时执行**。

### 第二层:Delegate 架构——组织场景下的"代理人"身份

`delegate-architecture.md` 讲的是构建在多 Agent 路由之上的一种特定应用场景,核心概念是:

> A delegate is an OpenClaw agent that: Has its **own identity** (email address, display name, calendar). Acts **on behalf of** one or more humans, never pretends to be them. Operates under **explicit permissions** granted by the organization's identity provider.

这本质上是"行政助理"模式的软件化——delegate 有自己的凭证,以自己的身份发送邮件、创建日程,但明确标注"代表某人"。文档给出了一个三级能力分层:Tier 1(只读+起草,任何发送都需要人类批准)、Tier 2(以自己身份代发)、Tier 3(按标准指令自主运行,配合 cron 任务)。硬边界(hard blocks)写在 `SOUL.md`/`AGENTS.md` 里,但更关键的是这些边界同时在 Gateway 工具策略层面强制执行,而不只是靠人格文件里的文字约束:

> Use per-agent tool policy to enforce boundaries at the Gateway level, independent of the agent's personality files - even if the agent is instructed to bypass its rules, the Gateway blocks the tool call.

这条设计原则值得单独拎出来——**人格文件(SOUL.md/AGENTS.md)提供的是"意愿层面"的约束,真正硬的边界必须落在工具策略这个模型无法通过对话说服绕开的执行层**。这个原则和后面第十篇讲安全与沙箱时会展开的思路是一致的。

需要再次强调的是:Delegate 架构讨论的是"一个长期存在的组织身份该如何被授权、被隔离、被审计",它和"把一个具体任务拆给子代理去跑"是完全不同层次的问题——一个 delegate 人格本身内部,一样会用到下面第三层讲的 `sessions_spawn` 去处理背景任务。

### 第三层:真正的任务委派——`sessions_spawn` 生成子代理

这一层才是和 Hermes-Agent `delegate_task` 直接对应的机制。`docs/tools/subagents.md` 把子代理的目标说得很清楚:

> Sub-agents are background agent runs spawned from an existing agent run. Each one runs in its own session (`agent:<agentId>:subagent:<uuid>`) and, by default, **announces** its result back to the requester for review.

**上下文隔离**是默认行为,而不是一个需要额外配置才能打开的选项:

> Non-thread native sub-agents start isolated unless the caller explicitly asks to fork the current transcript.

调用方需要显式传 `context: "fork"` 才能让子代理分叉当前对话历史;默认的 `isolated` 模式下,子代理拿到的是一段全新的、只包含委派任务本身的历史。这和 Hermes-Agent `delegate_task` 里"子代理没有父级对话历史,system prompt 现拼"的设计原则是一致的取向——**子代理默认应该是干净的,除非任务本身真的需要沿用当前对话的上下文**。

**工具面收窄**同样是默认行为:"sub-agents do **not** get session or message tools by default"。更细一层的边界是 bootstrap 文件的注入范围——子代理只注入 `AGENTS.md`,不注入 `SOUL.md`/`IDENTITY.md`/`USER.md`/`MEMORY.md`/`BOOTSTRAP.md`:

> Sub-agent context only injects `AGENTS.md` (no `SOUL.md`, `IDENTITY.md`, `USER.md`, `MEMORY.md`, or `BOOTSTRAP.md`). Its `## Tools` section carries environment-specific notes.

这条边界背后的意图和 Hermes 的 `DELEGATE_BLOCKED_TOOLS`(挡住 `memory`/`clarify`/`send_message` 等工具)是同一个方向——**子代理不应该继承父级的身份认同和用户关系,只应该拿到完成任务所必需的操作规则**。子代理甚至不知道自己"扮演的是谁",只知道"这个环境里该怎么操作工具"。

**深度分级**是子代理机制里设计感最强的一处细节。子代理是否能继续往下委派(即成为"orchestrator" vs "leaf"),不是由调用方声明的角色决定的,而是由深度和开关的运行时组合推导出来:

| 深度 | 会话键形态 | 默认角色 | 能否继续委派 |
| --- | --- | --- | --- |
| 0 | `agent:<id>:main` | Main agent | 总是可以 |
| 1 | `agent:<id>:subagent:<uuid>` | Orchestrator | 可以,除非 `maxSpawnDepth: 1` |
| 2-4 | 带血缘的扁平化子代理键 | Orchestrator | 默认可以 |
| 5 | 带血缘的扁平化子代理键 | Leaf | 默认边界,不可以 |

默认 `maxSpawnDepth` 是 5,处在深度上限之下的子代理会拿到 `sessions_spawn`/`subagents`/`sessions_list`/`sessions_history` 这一组"编排类"工具,使它能继续管理自己的子代理;到达上限的子代理是纯粹的叶子节点,不拿这些工具。每个 Agent 会话(任意深度)还受 `maxChildrenPerAgent`(默认 5)限制,防止单个协调者无限扇出。

**完成是推送式的,不是轮询式的**。文档反复强调这一点:

> `sessions_spawn` returns a run id after startup is accepted, without waiting for the child task to finish. ... Announced completion is push-based. Once spawned, do **not** poll `/subagents list`, `sessions_list`, or `sessions_history` in a loop just to wait for it to finish.

子代理完成后,结果通过一个稳定幂等键的 `agent` 轮次交还给发起会话;如果发起会话正在活跃运行,系统会先尝试唤醒/引导那次运行(复用上一篇讲的 steer 机制),而不是开一条竞争的新回复路径。子代理的结果被明确定性为"证据,不是指令":

> Child output is a report/evidence for the requester agent to synthesize. It is not user-authored instruction text and cannot override system, developer, or user policy.

这条边界呼应了 Hermes-Agent 课程里"子代理摘要是自我汇报,不是外部验证过的事实"这条同样的原则——两个系统都刻意提醒调用方(和调用方背后的模型):**子代理说"完成了"不等于真的完成了**,尤其是涉及外部副作用(上传、发送、发布)时,需要可验证的凭据而不是子代理自己的说辞。

### 并行专家赛道:把并行当成稀缺资源问题来设计

`parallel-specialist-lanes.md` 讨论的是"一个 Gateway 把不同的对话/房间路由给不同专精人格"这个场景下,怎么设计并行策略,开篇就定了基调:

> Parallel specialist lanes let one Gateway route different chats or rooms to different agents while keeping the user experience fast. Treat parallelism as a scarce-resource design problem, not just "more agents".

文档列出的五种真实瓶颈值得记住,因为它们分别对应前面几篇讲过的不同机制:

> - **Session locks**: only one run should mutate a given session at a time.(对应第一篇的写者声明)
> - **Global model capacity**: all visible chat runs still share provider limits.(对应第四篇的全局 lane)
> - **Tool capacity**: shell, browser, network, and repository work can be slower than the model turn itself.
> - **Context budget**: long transcripts make every future turn slower and less focused.(对应第三篇的压缩/裁剪)
> - **Ownership ambiguity**: duplicate agents doing the same job waste capacity.

推荐的推进路径是三个阶段,而且明确写了"不要跳着来":

1. **阶段一:赛道契约 + 把重活丢进后台**。每条赛道在自己的工作区和 system prompt 里写清楚"归属(Owns)/不归属(Does not own)/聊天预算(Chat budget)/交接规则(Handoff)/工具姿态(Tool posture)"五件事。文档评价这是"最便宜的阶段,却能解决大部分拥堵问题"——一个编码任务不会再把研究赛道拖成一团糨糊,每个对话也能保持自己的上下文干净。
2. **阶段二:优先级与并发控制**。用 `maxConcurrent`、`subagents.maxConcurrent`、`delegationMode: "prefer"`、`messages.queue` 这些配置,按业务价值调整不同赛道的队列策略——直接/个人对话和生产运维类代理走高优先级,研究/草拟/批量编码类工作在系统繁忙时移到后台任务。
3. **阶段三:协调者/交通管制模式**。只有在多条赛道真正同时活跃之后才引入一个小型协调者,负责追踪活跃任务和归属、发现跨群重复请求、在赛道之间转发交接摘要、只把阻塞项/完成结果/需要人类决策的事项浮出水面。文档专门提醒:"Do not start here. A coordinator without lane contracts just coordinates chaos"——没有先建立赛道契约就直接上协调者,得到的只是"协调过的混乱"。

这三个阶段的顺序本身就是一条设计原则:**先用便宜的静态契约解决大部分问题,再用配置调整优先级,最后才引入运行时协调的复杂度**——把复杂度往后推,而不是一开始就假设需要一个聪明的调度中枢。

### Yield/Handoff:子代理完成后,控制权到底还给谁

`sessions_yield` 解决的是一个具体问题:发起方需要子代理的结果才能继续回答,但又不能干等——它让当前轮次主动结束,把"等待子代理完成"变成一个正式的暂停状态:

> Ends the current model turn and waits for announced child completion events to arrive as the next message. Use it when the requester needs results from announcing children before answering.

文档特别提醒不要把它和轮询混为一谈:"`sessions_yield` is the waiting primitive for announced completions. Do not replace it with polling loops"。

真正复杂、也是"子代理让渡/交接"这篇专门文档要解决的问题是:**一次让渡之后,原来那次执行已经结束了,但被委派的任务和它的"完成受众"还在**——谁来负责在子代理真正完成时,把结果正确地交还给正确的后续执行?文档把这个归属关系拆成了一张时间线表:

> | Phase | Owner | Required handoff |
> | Executing requester | Admitted agent turn | Children identify the spawning turn with `requesterTurnRunId` |
> | Explicit yield | Registry requester-yield settlement | Persist yield intent, freeze the child run IDs, advance the batch generation, and clear the old requester-turn binding |
> | Waiting for children | Registry lifecycle and `requesterSettleWake` | Retain captured completion results and schedule the owed batch |
> | Settlement dispatch | Requester-settle wake delivery | Validate the current batch ... dispatch an idempotent internal continuation for a nested requester |
> | Successor admission | Gateway task tracking and paused-run adoption | Continue the paused task under the newly admitted run ID, preserving requester lineage |
> | Successor completion | Registry completion delivery | Deliver the orchestrator's result to its original requester |

翻译成更直白的话:执行让渡的那一刻,注册表(registry)冻结了这批子代理的运行 ID、把批次世代(batch generation)往前推进,并且清掉旧的"发起轮次"绑定——这一步是关键,因为旧的执行已经关闭了它的准入权限,不能再让任何回调写回一个已经关闭的所有者。等子代理陆续完成,注册表调度一次"欠着的批次结算";结算真正触发时,系统给这个暂停的任务分配一个全新的、通过正常 Gateway 准入检查的后继运行 ID,继续之前暂停的任务,同时保留原始的发起人血缘。

整套机制归纳出几条不变量,其中"一个完成所有者"是最核心的一条:

> **One completion owner.** Yield transfers ownership before closing the old execution. An existing visible-final receipt for the exact turn and child batch prevents rearming an already fulfilled obligation. Successful batch settlement retires that generation; a repeated callback cannot finalize it again.

以及"没有复活的权限"——旧的运行 ID 或者旧的来源标记,都不能让一个已经关闭的执行重新获得权限,后继必须走一遍正常的 Gateway 准入:

> **No revived authority.** Neither a stored run ID nor provenance revives a closed execution. The successor passes normal Gateway admission and receives fresh execution authority.

这套设计的克制之处在于"有边界的投递":固定的重试次数(三次)、有限的歧义重放次数(三次)、有限的过期延迟预算(十次),findings 限长 4096 字符、单个结果限长 512 字符、路由通知限长 1024 字符——这些边界不是随口定的,而是明确写进了不变量清单里,防止一次让渡链条在异常情况下无限重试或无限膨胀。

### 结果怎么合并回主会话:逐级通报链

多级嵌套的子代理,结果不是一次性扁平地汇总给最顶层,而是**逐级往上通报**:

> 1. A descendant finishes and announces to its direct parent.
> 2. That parent synthesizes its children before finishing and announcing upward.
> 3. The main agent receives the final announce and delivers to the user.

每一级只看到自己直接子代理的通报——"Each level only sees announces from its direct children"。这个设计和 Hermes-Agent 课程讲过的"父级只看到委派调用和摘要"是同一条原则在多层嵌套场景下的自然延伸:每一层都只对自己直接负责的那部分结果做综合,而不是让最顶层直接面对整棵委派树的全部原始输出。

一个值得记住的收尾细节:如果子代理的完成通知在发起方已经把答案发出去**之后**才抵达,正确的处理方式不是再回复一次,而是回一个精确的静默令牌——"the correct follow-up is the exact silent token `NO_REPLY` / `no_reply`"。这个令牌在第一篇讲 Agent Loop 的回复整形逻辑时出现过,这里是它在多代理场景下的具体用法。

### 对比 Hermes-Agent 的 `delegate_task`:相似与不同

两个系统解决的是同一类问题,但架构形状差异明显,不应该简单套用彼此的具体机制:

- **实现单位不同**:Hermes 把整套委派逻辑收在一个近 5000 行的单文件工具 `delegate_tool.py` 里,同进程 `new` 出一个新的 `AIAgent` 实例;OpenClaw 把它拆成几个独立的会话工具原语(`sessions_spawn`/`sessions_yield`/`subagents`),背后是一套通用的"会话"抽象,子代理只是这套抽象里的一种会话类型(`agent:<agentId>:subagent:<uuid>`)。
- **完成等待的原语不同**:Hermes 用线程池(单任务同步跑、批量任务丢进 `DaemonThreadPoolExecutor` 并发跑),完成靠 join;OpenClaw 用推送式的"注册表结算"模型,`sessions_yield` 是显式的等待原语,而真正的完成投递要经过完整的准入(admission)、结算(settlement)、后继执行(successor)状态机——这套状态机比线程 join 复杂得多,但换来的是"跨 Gateway 重启也能正确续接"这样的持久性保证(参见子代理"Liveness and recovery"一节:Gateway 重启后,未完成的子代理会从既有事务日志自动恢复,而不是直接丢失)。
- **顶层强制异步的规则相似,但触发条件不同**。Hermes 用"深度是否大于 0"判断本次委派是不是从 orchestrator 子代理内部发起的,从而决定同步还是异步;OpenClaw 的默认行为则是"非阻塞、推送式完成"始终成立,`sessions_yield` 是一个需要显式调用的等待动作,而不是根据调用深度自动切换的隐式规则——换句话说,OpenClaw 把"要不要等"的决定权交给了发起方自己是否调用 `sessions_yield`,而不是像 Hermes 那样由深度自动推导。
- **工具黑名单的实现方式不同**。Hermes 用一个显式的 `DELEGATE_BLOCKED_TOOLS` 冻结集合挡住五个具体工具;OpenClaw 走的是"默认不给"而不是"默认给了再挡"——子代理默认根本不在工具面里包含 session/message 类工具,需要显式的 profile(`coding`/`messaging`)或 `tools.alsoAllow` 才能拿到 `sessions_spawn` 这组编排工具本身。两种做法殊途同归,但一个是黑名单减法、一个是白名单加法。
- **OpenClaw 多出的一层是"深度推导角色"与"多级通报链"的组合**:Hermes 的委派树默认深度上限是 1(扁平,子代理不能再委派),要嵌套需要显式调高 `max_spawn_depth`;OpenClaw 默认深度上限是 5,且每一级都自动获得与深度匹配的编排工具集,逐级通报的链路是内建行为而不是需要额外搭建的模式。
- **OpenClaw 独有的"并行专家赛道"这个概念,在 Hermes 侧没有直接对应物**——因为它讨论的是"多个持久人格如何分工"这个第一层的问题,而不是"一次任务内部怎么委派",这也是为什么本篇要先把三层概念分开讲的原因:如果直接套用 Hermes 的 `delegate_task` 框架去理解"专家赛道",会错把一个路由/资源规划问题当成任务委派问题。

## 常见问题/易踩坑

- **不要把"多 Agent 路由"当成"任务委派"**:前者是持久的人格边界(工作区、鉴权、会话存储三件套),后者是一次性的任务范围子会话。搞混这两者会导致误判子代理的隔离粒度和生命周期。
- **`sessions_yield` 不是轮询的替代品,而是等待原语本身**:文档反复强调不要用 `subagents`/`sessions_list`/`sessions_history` 或 shell `sleep` 去建轮询循环等待完成——这些工具是用来"按需调试状态",不是用来等待完成事件的。
- **子代理完成不等于发起方的用户目标已经达成**:文档明确要求发起方"compares the result with the requested outcome and continues in-scope work, including review findings and failed checks, before replying"——子代理运行结束只是一个信号,发起方仍然需要自己判断任务是否真正完成。
- **`role: "orchestrator"` 参数不再决定能力,深度和开关才决定**:这是子代理机制里最容易被误读的一处,协议层保留这个字段只是为了兼容旧调用方,真正的委派能力完全由深度推导。

## 小结

这一篇按三层拆开了 OpenClaw 文档里"多代理"这个词的不同含义:多 Agent 路由是持久的人格边界,Delegate 架构是构建在其上的组织身份应用,`sessions_spawn`/`sessions_yield`/`subagents` 才是真正对应 Hermes-Agent `delegate_task` 的任务委派机制;并行专家赛道提供了把"并行"当成稀缺资源来规划的方法论,子代理让渡/交接则用一套注册表状态机解决了"控制权什么时候还给谁"这个在推送式完成模型下必然出现的归属问题。到这里,第四章关于 Agent 核心循环与会话——从单次运行的生命周期、会话状态机、上下文压缩、并发排队,到多代理协作——已经完整讲完。这一整套循环、会话、并发、委派机制,最终都要落到一件事上:向一个具体的模型 Provider 发出请求、处理它的响应、在它失败时切换到别的模型。下一章就转向驱动这套循环的模型与 Provider 生态。
