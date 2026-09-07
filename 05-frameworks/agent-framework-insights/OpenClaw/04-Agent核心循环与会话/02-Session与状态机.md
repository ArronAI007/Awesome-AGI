# Session 与状态机

> 上一篇讲了一次 Agent Loop 怎么从接收输入跑到交付回复,但没有回答一个更基础的问题:这次输入到底该落在哪个"会话"里?OpenClaw 把"会话"(session)定义成一个由来源决定归属的独立单位——直接消息、群聊、定时任务、Webhook 各自有默认的路由规则;其中最特殊的一种叫 main session,是个人助理模式下"所有直接消息汇入同一条滚动对话"的默认根会话。本篇从路由规则讲到生命周期,再讲到一套专门解决"多个会话/多个代理协同时状态过期"问题的信号日志机制,最后落到会话裁剪(pruning)——一种不产生摘要、只裁剪工具结果的轻量级上下文控制手段。

## 学习目标

- 理解不同来源的消息(DM/群聊/cron/webhook)默认路由到什么样的 session,以及 `session.dmScope`/`session.groupScope` 两个维度如何独立控制隔离粒度。
- 理解 main session 的特殊性:固定的 `agent:<agentId>:main` 键、Web 端的 Home 页面语义,以及"群活动/后台工作/心跳"三类信息如何汇入它。
- 理解会话生命周期的四种重置策略(none/daily/idle/manual)和 Gateway 重启后的恢复预算机制。
- 理解会话状态感知(session state awareness)的三段式设计:持久信号日志、按目标持有游标的 watcher、通过 `changesSince` 做增量对账,以及它为什么要做成"一个目标只挂一条待处理通知"的反刷屏协议。
- 理解 Session Pruning 和 Compaction 的边界:裁剪只动工具结果,不改写对话正文;两条安全规则——最近三轮 assistant 从不裁剪、首条用户消息之前的内容从不裁剪——分别防住了什么。

## 背景与设计动机

个人助理场景下,"会话"这个概念比一般聊天机器人要复杂得多。同一个人可能在手机上用 Telegram、在电脑上用网页端、偶尔还会通过群聊@到代理;后台还有心跳、cron 任务、子代理完成通知这些不是由人直接触发的"输入"。如果每个来源各自开一条独立的对话线,代理就会变成一个"到哪个渠道说话就换一个人格"的东西,完全违背个人助理"有一个连续心智"的设计初衷。

反过来,如果所有输入不做任何隔离全部塞进一条会话,又会在多用户场景下出现隐私事故——文档给出的警告很直接:

> If multiple people can message your agent, enable DM isolation. Without it, all users share the same conversation context, so Alice's private messages would be visible to Bob.

OpenClaw 的解法是把"会话归属"拆成两个正交的配置维度(`dmScope`/`groupScope`),默认值面向单用户个人助理场景做了优化(所有 DM 共享 main session),但给多用户场景留了清晰的隔离旋钮。同时,为了让"main session 是一个持续存在的心智"这句话成立,系统还需要一整套机制去处理"会话被别的行动者动过之后,原来的假设是不是还成立"——这正是 session state awareness 要解决的问题。

## 核心机制详解

### 消息路由表:来源决定默认归属

文档给出的默认路由表是理解会话模型的起点:

| Source | Behavior |
| --- | --- |
| Direct messages | Shared session by default |
| Group chats | Isolated per group by default |
| Rooms/channels | Isolated per room by default |
| Cron jobs | Fresh session per run |
| Webhooks | Isolated per hook |

DM 和群聊被设计成两种截然相反的默认行为:DM 默认共享(因为个人助理场景下大概率是同一个人在切换设备/渠道),群聊/房间默认隔离(因为群里的对话上下文通常与你和代理的私聊无关)。这两个默认值分别由两个独立的配置项控制:

- `session.dmScope`:`main`(默认,所有 DM 共享 main session)/ `per-peer` / `per-channel-peer`(推荐,按渠道+发送者隔离)/ `per-account-channel-peer`。
- `session.groupScope`:`per-group`(默认,每个群/房间独立会话)/ `main`(把群聊路由进主会话)。

这两个维度可以在 binding 级别单独覆盖——比如全局群聊都隔离,但某个受信任的团队房间单独设成 `groupScope: "main"`,加入主对话。

### main session:个人助理的默认根会话

main session 是一个"看起来普通、地位特殊"的会话。它的键是固定的:

> Under the hood the main session is an ordinary session with the canonical key `agent:<agentId>:main` (for example `agent:main:main`). The suffix is fixed; custom `session.mainKey` values are ignored.

之所以特殊,不是因为它的数据结构有什么不同,而是因为系统把它当作"代理的根"来对待:"heartbeats wake it, background work reports back to it, and activity elsewhere flows up to it"。三类信息汇入 main session 的方式各不相同:

- **群活动**:在默认 `session.groupScope: "per-group"` 下,群/房间会话本身保持隔离,但 main session 会自动"观察"(watch)它们——"Activity queues up as compact notices — coalesced per conversation, never one wake-up per message",代理在下一次运行(用户发消息或定时心跳触发)时才会看到这些通知。
- **后台工作**:子代理和衍生会话的结果,会向发起它们的会话汇报——从 Home 发起的工作,结果也回到 Home。
- **心跳**:定时心跳的目标就是 main session,这也是"没有人发消息时,代理依然能对队列里的通知产生反应"的唯一驱动力。

在 Web 端,main session 就是侧边栏第一项——Home 页面。文档还提到一个细节:分叉出的会话在侧栏归入 **Threads**,群聊归入 **Groups**,编码/CLI 会话归入 **Coding**,而"Talk to your Home agent"(`Cmd/Ctrl+Shift+H`)让你在处理其他页面时用侧边栏对话 Home,并且这个对话面板"uses your real Home conversation, including its history, tools, approvals, and message queue"——不是一个影子会话。

### 会话生命周期:四种重置策略

会话默认没有自动重置("No automatic reset (default `mode: "none"`)"),靠压缩(下一篇主题)维持上下文可控。要开启自动重置需要显式选择策略:

- **Daily reset**:在网关主机的本地时间某个小时触发(`session.reset.atHour`,默认 4 点)。"Daily freshness is based on when the current `sessionId` started, not on later metadata writes"——判断新鲜度用的是会话开始时间,不是随便一次元数据写入的时间。
- **Idle reset**:超过 `idleMinutes` 无活动后触发,但"heartbeat, cron, and exec system events do not keep the session alive"——心跳和系统事件不会让空闲计时器复位,只有真实的用户/渠道交互才算数。
- **Manual reset**:`/new` 或 `/reset`。

两种自动策略可以叠加,"whichever expires first wins"。一个容易忽略的细节:重置发生时,"queued system-event notices for the old session are discarded so stale background updates are not prepended to the first prompt in the new session"——旧会话里排队的系统通知不会带进新会话的第一条 prompt,避免新会话一开始就被过时的后台更新污染。

### Gateway 重启恢复预算

Gateway 重启打断一次活跃运行时,OpenClaw 会尝试自动续接原会话,但这个能力是有预算限制的:

> Three attempts that fail to start a backend turn exhaust the recovery budget. Once a real backend turn starts, the budget refreshes, so a later Gateway restart does not consume the old allowance.

这个设计防的是"反复重启但从未真正跑起来"的死循环——只有真正启动了一次后端轮次,预算才会刷新;仅仅是接受、排队或准备一次续接请求,并不刷新预算。预算耗尽后,事务记录依然完整可用,用户需要显式选择"在新会话里恢复"或 `/new`/`/reset`。

### 会话状态感知:三段式的"过期检测 + 一次通知 + 精确对账"

这是本篇分量最重的机制,解决的是一个在多会话协同场景下必然出现的问题:一个 manager 会话把任务委派给多个 child 会话,或者两个代理通过 `sessions_send` 协作,各方对彼此状态的假设会在对方被别的行动者(人类,或另一个代理)干预的瞬间过期。文档把整套机制拆成三个部件。

**信号日志**:OpenClaw 在共享状态数据库(`session_state_events`)里为"被监视的会话发生实质性变化"记一条类型化事件,"Events carry metadata and a one-line summary — never message content"。八种事件类型里,只有三种会真正推送通知(`human_direct_message`/`upstream_missing`/`goal_changed`),其余五种(`child_spawned`/`run_completed`/`run_failed`/`compacted`/`adopted`)只写日志、不打扰任何人——"Log-only kinds exist for reconciliation history, not notification"。一个会话的**状态版本**(state version)就是它日志里最高的序号。

**Watcher(观察者)**:一个 watcher 在目标会话上持有一个游标,三种来源:

- **隐式(生成边)**:一个会话生出子代理或 ACP 子会话时,父会话的游标自动播种在子会话诞生的那个版本上——"Parents never subscribe manually"。
- **环境组**(Ambient groups):默认 `groupScope: "per-group"` 下,main session 在群/房间会话的第一次人类发言之后自动开始观察它们。
- **显式**:任何协调者可以在 `sessions_send` 上传 `watch: true` 来监视一个非自己生出的目标,注册从"发送成功之后"目标当前的状态版本开始——"prior history never produces notices"。

**通知的反刷屏协议**是这一节设计感最强的部分。核心规则列了五条:

> - **One pending notice per watcher/target pair.** ... twenty rapid changes to the same target still produce a single line in the watcher's prompt.
> - **Frozen watermark.** The cursor freezes its notified position when a notice is queued. Further material events advance only the material watermark; they do not re-notify.
> - **Acknowledge on drain, reopen only for interleaved work.** ...
> - **Self-suppression.** A watcher never gets notified about events it caused itself.
> - **Restart recovery.** Pending notices live in an in-memory queue; a startup sweep re-materializes them from durable cursors after a gateway restart.

这五条规则合起来解决的是同一个问题的不同侧面:**通知本身应该是"有一件事需要关注",而不是"事件流水账"**。二十次连续变更只产生一条通知;通知挂起期间新的变更不会重复触发;通知被消费后游标才前进,但如果在"通知已排队"和"消费者真正处理它"之间又发生了新的实质性变更,会为这部分剩余变更单独开一条新通知,而不是被第一条通知吞掉;自己触发的事件永远不会通知自己;进程重启不会丢失挂起的通知。

拿到通知之后的对账动作也很简单——不重新拉全部历史,而是精确地要"这之后发生了什么":

```json
{
  "stateVersion": 19,
  "stateChanges": {
    "events": [
      { "sequence": 14, "kind": "human_direct_message", "actorType": "human", "summary": "human message via telegram" },
      { "sequence": 19, "kind": "goal_changed", "actorType": "human", "summary": "goal updated" }
    ],
    "historyGap": false
  }
}
```

`historyGap: true` 是一个明确的"我这里不能给你精确增量"信号——"it comes from a per-session pruned watermark, not inferred from sequence arithmetic",遇到这个信号应该整个刷新会话状态,而不是把响应当作一个精确的增量来处理。

这套机制的定位也很克制,文档没有回避它的局限:"Recording is best-effort — a failed append is logged and never fails the originating turn — so `stateVersion` is a signal-log head, not a transactional change-data-capture version"。换句话说,它是一个"尽力而为的感知层",不是一套强一致的分布式事务日志——这个取舍本身也符合个人助理系统"宁可偶尔漏一条通知,也不能因为记账失败拖累正常对话"的优先级。

### Session Pruning:裁剪工具结果,不是压缩对话

Session Pruning 经常被和下一篇要讲的 Compaction 搞混,文档开篇第一句话就划清了边界:

> Session pruning trims **old tool results** from the model's context. It reduces context bloat from accumulated tool outputs (exec results, file reads, search results) without rewriting normal conversation text.

它的落地路径因 provider 而异。对于走 Anthropic API-key 认证的直连请求,OpenClaw 直接委托给 Anthropic 官方的服务端工具结果清理(server-side tool-result clearing),自己不开新的裁剪轮次;其余走 cache-TTL 的路由(Bedrock、Google、Microsoft Foundry、OAuth、代理等)则走客户端裁剪,分两级:

1. **软裁剪(soft-trim)**:超过 4000 字符的工具结果,只保留首尾各 1500 字符,中间用 `...` 连接。
2. **硬清除(hard-clear)**:上下文占用仍然高于约 50% 且可裁剪的工具内容还有至少 50000 字符时,把这些结果整体替换成占位符(默认 `[Old tool result content cleared]`)。

无论走哪条路径,两条安全规则是硬编码、不受阈值影响的:

> Two safety rules apply regardless of thresholds: the last three assistant turns are never pruned, and nothing before the session's first user message is ever pruned (protects bootstrap reads like `SOUL.md`/`USER.md`).

第一条规则防止的是"刚发生的事情被裁没了,模型对自己刚做过什么产生幻觉";第二条规则防止的是"引导阶段读取 `SOUL.md`/`USER.md` 这类身份文件的工具调用结果被裁掉,导致代理在长对话里逐渐'失忆'自己是谁"。这两条规则和 Compaction 里"工具调用与结果必须配对不能被切开"的规则,是同一类设计哲学的两个具体实现——**上下文控制机制的裁剪/压缩边界永远要让位于对话结构完整性**。

### 会话维护:有边界的存储,而不是无限增长

`session.maintenance` 用几个参数框定存储上限:`pruneAfter`(默认 30 天后归档)、`maxEntries`(默认 5000 条未归档会话)、`archiveDashboardAfter`(仪表盘会话 7 天不活跃后自动归档)、`preserveRecent`(可选,保护最近活跃的会话不被立即清理)。压力清理的策略是"归档最旧的、合乎条件的普通会话,而不是删除事务记录"——被钉住(pinned)的根会话、活跃或已接纳的工作、模型锁定的会话、持久的外部对话指针,始终受保护,"the unarchived total can therefore remain above the cap when protected rows alone exceed it"(受保护行本身超过上限时,未归档总数可以合法地高于配置的上限)。

## 常见问题/易踩坑

- **DM 共享不是"默认更安全的选项",而是"默认为单用户场景优化"**:多用户环境下不显式设置 `dmScope`,就是在制造隐私事故——这不是一个边缘情况,文档专门用 `<Warning>` 标出来。
- **`groupScope` 和 `dmScope` 是两个独立开关**:把某个团队房间路由进主会话(`groupScope: "main"`)不需要、也不影响 DM 隔离策略;反过来,DM 隔离之后,群活动依然按 `groupScope` 单独决定要不要汇入 main session。
- **Pruning 不产生摘要,Compaction 才产生摘要**:如果发现"上下文变小了但对话历史看起来完全没变",很可能是触发了裁剪(客户端投影在内存里,原始工具结果没有被改写);如果发现事务记录里多出一条摘要条目,那才是压缩生效了。
- **watcher 收到的通知是"信号",不是"内容"**:通知文本本身不包含消息正文,拿到通知后必须显式调用 `session_status` 的 `changesSince` 才能看到具体发生了什么——这个两段式设计是为了让通知本身保持轻量,不因为携带大量上下文而膨胀模型的输入。

## 小结

这一篇讲了会话作为一个"状态机"的三层结构:路由规则决定归属、生命周期策略决定何时重置、状态感知机制让多个会话之间的协同不因为信息过期而失效,最后是裁剪这个轻量级的上下文控制手段。但裁剪终究只能处理工具结果的膨胀——当整个对话历史本身逼近模型上下文窗口的物理上限时,系统需要一套更彻底的手段:把旧对话摘要化,并且让这套摘要逻辑本身变成一个可插拔的层。下一篇就讲这件事:Compaction 与 Context Engine。
