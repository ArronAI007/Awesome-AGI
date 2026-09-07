# Pairing、Groups 与访问控制

> "Pairing"这个词在 OpenClaw 里出现在两个完全不同的层面:一处是第 03 章讲过的 Gateway 设备配对——决定一个新的 WebSocket 连接(手机 App、CLI、Control UI)能不能被信任、拿到多大权限的 token;另一处是这一篇要讲的 DM 配对——决定一个陌生的消息发送者发来的第一条消息该不该被处理、该不该被回复。两者都叫"pairing",管的却是完全不同层级的信任问题:前者回答"这个连接是谁",后者回答"这条消息该不该被理睬"。这篇文章把 DM 配对、群组访问控制、以及防止机器人之间互相触发死循环的 bot loop protection 这三块拼在一起讲清楚。

## 学习目标

- 区分 DM 配对(`docs/channels/pairing.md` 第 1 节)与第 03 章 Gateway 设备配对(同一文档第 2 节)分别管的是消息层信任还是连接层信任,理解为什么同一个词在两个场景下的语义完全不同。
- 理解 DM 配对码的具体约束(长度、有效期、并发上限)以及"批准 DM 访问"和"授予群组访问权限"是两个独立的权限维度。
- 理解群组访问控制的两层模型:`groupPolicy`/`groupAllowFrom` 决定"谁能触发",`requireMention`/`contextVisibility` 决定"什么时候触发、模型能看到什么上下文"。
- 理解 `accessGroups` 如何把同一批可信发送者的身份跨渠道复用,以及 Discord 特有的 `discord.channelAudience` 动态访问组类型。
- 理解 bot loop protection 要解决的具体工程问题——两个机器人互相回复对方消息陷入无限循环——以及它的滑动窗口 + 冷却期算法。

## 背景与设计动机

一个消息网关一旦支持"接受其他机器人发来的消息"(`allowBots`)或者"陌生人可以直接私信触发 agent",就同时打开了两类风险:第一类是访问控制风险——谁都可以给机器人发消息,如果没有一道明确的准入闸门,机器人就变成了一个对陌生输入完全开放的执行入口;第二类是稳定性风险——如果两个都配置了自动回复的机器人被凑到了一起,一个机器人的回复会触发另一个机器人的回复,如此往复,足以在几秒钟内产生成百上千条消息,耗尽 API 配额甚至造成实质性的服务风暴。DM 配对和群组访问控制解决的是第一类问题,bot loop protection 解决的是第二类问题。

## 核心机制详解

### DM 配对:陌生发送者的第一道闸门

当一个渠道的 DM 策略是 `pairing` 时,陌生发送者的第一条消息不会被处理,而是收到一个配对码,`docs/channels/pairing.md` 描述了这个码的具体形状:

> Pairing codes:
>
> - 8 characters, uppercase, no ambiguous chars (`0O1I`).
> - **Expire after 1 hour**. The bot only sends the pairing message when a new request is created (roughly once per hour per sender).
> - Pending DM pairing requests are capped at **3 per channel account**; additional requests are ignored until one expires or is approved.

这几个细节都是在权衡"可用性"与"滥用防护"——8 个字符、排除容易混淆的字符(`0`/`O`/`1`/`I`)是为了让人工输入配对码时不容易出错;1 小时过期和"每小时最多提醒一次"是为了避免陌生发送者反复发消息刷屏;每渠道账号最多 3 个待处理请求则是给这道闸门本身加了一个防滥用上限,避免有人对着同一个机器人狂发消息制造大量待批准请求。

批准这一步的语义边界也很明确:"Approval grants direct-message access only. It does not grant group access."——DM 配对批准和群组访问权限是两个完全独立的维度,批准了一个人的私信不代表这个人在任何群里都能触发 agent。文档也特意提醒了一个容易被误解的细节:CLI 批准路径会自动把第一个通过配对的发送者设为命令属主(`commands.ownerAllowFrom`),但后续手动加进允许列表的发送者不会自动获得这个属主身份:

> Manually allowlisted senders are not automatically command owners. If an authorized sender has no owner access, owner-only commands reply with the exact `openclaw config set commands.ownerAllowFrom` command for the operator to run.

这条设计避免了"允许列表越扩越大,属主权限也跟着不知不觉扩大"的隐患——属主身份必须是一次显式决定,不能靠"反正这个人已经在允许列表里了"来隐式获得。

### 两种"pairing",两层信任

`docs/channels/pairing.md` 用两个独立的编号小节把 DM 配对和节点配对分开讲,这个结构安排本身就是对两者语义差异的强调。节点配对面对的问题是"这台设备(iOS App、Android App、headless 节点)能不能连接到 Gateway 并拿到相应的操作权限",批准之后拿到的是一个绑定了角色(`role: node`/`operator`)和权限范围(`scopes`)的设备 token,这个 token 之后可以调用摄像头、屏幕录制、位置等节点专属命令。DM 配对面对的问题则是"这条从某个 IM 平台发来的消息,发送者是不是被允许触发 agent",批准之后进入的是 `channel_pairing_allow_entries` 这张表,和设备 token 完全是两套独立的存储与信任判定路径。

一个直观的区分方法是:节点配对回答的是传输层问题——"这个 WebSocket 连接是谁,能做什么";DM 配对回答的是消息层问题——"这条消息该不该被处理"。一台已经拿到节点 token 的 iOS 设备,如果同时也通过 Telegram 私信机器人,仍然需要单独完成 DM 配对才能让那条 Telegram 消息被处理——两套信任状态互不代替。

### 群组访问控制:两层独立的开关

`docs/channels/groups.md` 把群组安全模型总结成一句"翻译":

> - **DM access** is controlled by `*.allowFrom`.
> - **Group access** is controlled by `*.groupPolicy` + allowlists (`*.groups`, `*.groupAllowFrom`).
> - **Reply triggering** is controlled by mention gating (`requireMention`, `/activation`).

这里能看出群组安全实际上被拆成了两层完全独立的判断:第一层是"这条消息所在的群/发送者有没有资格触发 agent"(`groupPolicy`/`groupAllowFrom`/`groups`),第二层是"即便有资格,这次具体消息要不要真的触发一次回合"(`requireMention` 提及门槛)。文档给出的消息流转示意把这个顺序讲得很直白:

> ```text
> groupPolicy? disabled -> drop
> groupPolicy? allowlist -> group allowed? no -> drop
> requireMention? yes -> mentioned? no -> store for context only
> mention/reply/command/DM -> user request
> always-on group chatter -> user request, or room event when configured
> ```

值得注意的是"未被提及"不等于"被丢弃"——如果群组本身已经通过了准入检查,只是这条具体消息没有提及机器人,它仍然会被存下来作为上下文(`store for context only`),供之后真正触发的那次回合参考。这是"准入"和"触发"分离带来的一个直接好处:机器人可以安静地"listen"整个群聊,只在被明确呼叫时才开口,但开口时仍然带着此前群聊的完整上下文。

第二个值得强调的分离是"谁能触发"和"模型能看到什么补充上下文"是两件不同的事。文档专门用 `contextVisibility` 这个配置项把这两者切开:

> Two different controls are involved in group safety:
>
> - **Trigger authorization**: who can trigger the agent (`groupPolicy`, `groups`, `groupAllowFrom`, channel-specific allowlists).
> - **Context visibility**: what supplemental context is injected into the model (reply/quote text, thread history, forwarded metadata).
>
> By default OpenClaw keeps context as received: allowlists decide who can trigger actions, not what quoted or historical snippets the model sees.

默认情况下,允许列表只决定谁能触发动作,不代表非允许列表成员的发言就不会作为上下文出现在 prompt 里——如果需要更严格的隔离,才需要显式把 `contextVisibility` 设为 `allowlist` 或 `allowlist_quote`。这个默认值的选择本身透露了一个设计取向:群聊场景下,"看到"和"能操纵"被认为是两种不同强度的风险,默认只收紧后者。

### Access Groups:跨渠道复用的可信发送者集合

如果同一批人(运维团队、on-call 值班人员)需要在多个渠道上都拥有访问权限,把他们的 ID 在每个渠道的 `allowFrom` 里各抄一份是重复劳动而且容易漏改。`docs/channels/access-groups.md` 提供的 `accessGroups` 就是为了消掉这种重复:

```json5
{
  accessGroups: {
    operators: {
      type: "message.senders",
      members: {
        "*": ["global-owner-id"],
        discord: ["discord:123456789012345678"],
        telegram: ["987654321"],
        whatsapp: ["+15551234567"],
      },
    },
  },
}
```

引用方式是在渠道原本的 `allowFrom`/`groupAllowFrom` 字段里写 `accessGroup:operators`,而不是把成员 ID 直接铺开。文档特别强调了一个容易被忽视的语义:"A group grants nothing by itself. It only matters where an allowlist field references it."——定义一个组不会自动产生任何权限,权限来自于哪个允许列表字段引用了它。文档也提醒了失败模式:"Missing group names fail closed. If `allowFrom` contains `accessGroup:operators` and `accessGroups.operators` is absent, that entry authorizes nobody."——引用一个不存在的组不会意外放行所有人,而是让这条引用变成一个不授权任何人的死条目,这是典型的"默认拒绝"安全设计。

Discord 还提供了一种动态访问组类型,直接把 Discord 自己的频道成员关系当成信任来源:

```json5
{
  accessGroups: {
    maintainers: {
      type: "discord.channelAudience",
      guildId: "1456350064065904867",
      channelId: "1456744319972282449",
      membership: "canViewChannel",
    },
  },
}
```

`discord.channelAudience` 的语义是"允许当前能看到这个 Discord 频道的人",OpenClaw 在鉴权时实时向 Discord 查询发送者是否满足 `ViewChannel` 权限规则。这种设计适合"团队成员关系的真相已经存在于 Discord 频道权限里"的场景(比如已有的 `#maintainers` 或 `#on-call` 频道),不需要在 OpenClaw 配置里维护一份可能过时的成员名单副本。文档也交代了它的失败模式:"The access group fails closed when Discord returns `Missing Access`, the sender cannot be resolved as a guild member, or the channel belongs to another guild."——同样是默认拒绝而不是默认放行。

### Bot Loop Protection:防止机器人互相触发的死循环

一旦某个渠道打开了 `allowBots`(接受其他机器人发来的消息),就出现了一种纯技术性但很实际的风险:两个都会自动回复的机器人一旦被放进同一个会话,A 回复 B、B 又自动回复 A,如此循环下去,短时间内可以产生大量无意义的消息往来。`docs/channels/bot-loop-protection.md` 的解法是一个滑动窗口 + 冷却期的配对级限流器:

> The guard is enforced by the core inbound reply runner. Each supporting channel maps its inbound event into generic facts: account or scope, conversation id, sender bot id, and receiver bot id. Core tracks the participant pair in both directions (A to B and B to A count as the same pair), applies a sliding-window budget, and suppresses the pair during a cooldown after the budget is exceeded.

默认参数是"60 秒窗口内最多 20 次交换,超出后冷却 60 秒":

> | Key | Default | Meaning |
> | --- | --- | --- |
> | `enabled` | `true` | Guard active for channels that support it. |
> | `maxEventsPerWindow` | `20` | Events a bot pair can exchange within the window. |
> | `windowSeconds` | `60` | Sliding window length. |
> | `cooldownSeconds` | `60` | Suppression time after the pair exceeds the budget. |

这里有两个设计细节值得注意。第一,"A 到 B"和"B 到 A"被算作同一对参与者——这保证了限流是针对"这两个机器人之间的交换关系"而不是单方向计数,否则一个机器人可以通过让另一个机器人先发言来绕开限流。第二,这套机制完全不影响人类发送的消息、单机器人部署,或者本来就没有超出预算的正常机器人回复——"The guard does not affect human-authored messages, single-bot deployments, self-message filtering, or bot replies that stay under the budget."这意味着这是一张只在异常情况下才会拉响的安全网,而不是一道会影响正常协作场景的速率限制。

配置的覆盖优先级也遵循"越具体越优先"的一贯模式,从窄到宽:

> 1. `channels.<channel>.<room-or-space>.botLoopProtection`
> 2. `channels.<channel>.accounts.<account>.botLoopProtection`
> 3. `channels.<channel>.botLoopProtection`
> 4. `channels.defaults.botLoopProtection`
> 5. built-in defaults

一个容易被忽视的前提条件是:这套防护只能在渠道能够"可靠地识别机器人身份"时才生效。文档明确说"Channels that do not expose a reliable inbound bot identity keep using their normal self-message and access-policy filters. They should not opt into this guard until they can identify both participants in the bot pair."——如果一个渠道连"发这条消息的是不是机器人、是哪个机器人"都无法确定,勉强套用这套配对级限流反而可能造成误判,不如继续依赖原有的自消息过滤和访问策略。

### 顺带一提:WhatsApp 的广播组是另一种"群组"

`docs/channels/broadcast-groups.md` 描述的"广播组"和这一篇讲的群组访问控制其实是两件不同的事——它不是访问控制机制,而是一种实验性的多 agent 扇出功能:同一条 WhatsApp 群消息可以同时交给配置里列出的多个 agent 各自独立处理、各自回复。文档强调了它和访问控制的关系:"Broadcast groups are evaluated after channel allowlists and group activation rules... They only change **which agents run**, never whether a message is eligible for processing."换句话说,广播组完全建立在这一篇讲的准入模型之上——先通过 `groupPolicy`/`requireMention` 这些正常的准入检查,广播才决定"通过检查之后由几个 agent 来处理这条消息",而不是绕开或替代访问控制本身。

## 常见问题/易踩坑

**Q:批准了某人的 DM 配对请求,这个人是不是也能在群里控制机器人了?**

不能。`docs/channels/pairing.md` 明确说"Approval grants direct-message access only. It does not grant group access."群组访问是完全独立的一套允许列表(`groupAllowFrom`/`groups`),即便某人已经通过私信配对,群聊里的消息仍然要单独过一遍群组准入检查。

**Q:群里的非白名单成员发的消息,模型是不是完全看不到?**

默认情况下能看到。`contextVisibility` 默认值是 `"all"`,允许列表只决定谁能"触发"agent,不决定哪些内容能作为补充上下文出现在 prompt 里。如果需要更严格的隔离,需要显式设置 `contextVisibility: "allowlist"` 或 `"allowlist_quote"`。

**Q:`accessGroups` 里引用了一个拼错名字的组,会不会误放行?**

不会。这是默认拒绝设计——`accessGroups.<name>` 不存在时,引用它的允许列表条目"authorizes nobody",而不是退化成放行所有人。拼写错误的后果是这条规则完全失效(该被放行的人也进不来),而不是安全漏洞。

**Q:两个机器人一直互相回复,是不是意味着 bot loop protection 配置错了?**

先检查这个渠道是否真的能可靠识别机器人身份。这套防护要求渠道能明确区分"发送者是不是机器人"以及"是哪个机器人",如果渠道本身无法提供这个事实,防护机制根本不会生效,问题需要回到渠道层面的机器人身份识别能力,而不是调整滑动窗口参数。

## 小结

这一篇把消息层面的信任模型理清楚了:DM 配对管的是"陌生私信该不该被处理",和第 03 章讲的 Gateway 设备配对(管连接层信任)是两套完全独立的机制;群组访问控制被拆成"谁能触发"和"提及门槛/上下文可见性"两层独立开关,`accessGroups` 让同一批可信发送者的身份可以跨渠道复用并且默认拒绝失败;bot loop protection 用一个方向无关的滑动窗口加冷却期,专门针对机器人之间可能出现的死循环这一具体工程风险,同时明确排除了对人类消息和正常场景的干扰。下一篇把视角切换到消息网关之外的另一个界面——WebChat 这个原生客户端,以及托管在 Gateway 同一个端口上的 Canvas 和 A2UI 界面系统,看看 agent 是怎么在聊天消息之外,向用户展示一整块可交互的网页组件的。
