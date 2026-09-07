# Channel 插件契约与 Transport-Only 原则

> `src/channels/` 目录下堆着大约 491 个文件,支撑着 WhatsApp、Telegram、Slack、Discord、Signal、iMessage、Google Chat、Matrix、IRC、LINE、飞书、Mattermost、Microsoft Teams、Nextcloud Talk、Nostr 等几十种消息渠道——这个数字本身就足够吓人。但仓库根目录 `AGENTS.md` 里"Architecture"一节只用一句话就把这几十个渠道全部管住了:"Keep channels transport-only. Shared typed actions and presentation contracts belong to their owners; channel adapters encode them. Preserve distinctions between commands, approvals, URLs, and other actions; do not infer commands from raw strings."(`AGENTS.md:55`)。这篇文章要做的,就是把这句"铁律"拆开——它到底在防止什么问题,又是怎么落到 `openclaw/plugin-sdk/*` 这套具体的入站/出站契约里的。

## 学习目标

- 理解 `AGENTS.md` 里"channels transport-only"这条规则要防止的具体错误:渠道适配器不应该自己定义业务语义,而应该只负责把平台原生的消息格式"编码/解码"成核心已经定义好的类型化动作。
- 认识 Channel 插件的所有权边界——一个插件到底该实现什么(`docs/plugins/sdk-channel-plugins.md` 里"What your plugin owns"清单),核心又保留了什么(共享的 `message` 工具、prompt 拼装、会话键结构)。
- 理解入站方向的两层分工:`channel-ingress`(谁有权触发)与 `channel-inbound`(一次触发如何变成一个 agent 回合)是两个独立的契约,插件只提供"平台事实",策略判断留给核心。
- 理解出站方向的能力声明模型:`message` adapter 必须显式声明它真正支持的能力(`durableFinal.capabilities`),声明与实际行为的偏差会被契约测试直接判定失败。
- 通过 model-picker 回调、身份认证分级(`IdentifierAuthentication`)等具体例子,理解"不要从裸字符串推断命令/身份"这条禁令在真实代码里长什么样。
- 认识 `extensions/AGENTS.md` 里的"Extensions Boundary"——transport-only 不只是一句设计建议,而是有导入边界规则在代码组织层面强制执行的。

## 背景与设计动机

一个消息网关要同时接入几十种协议形态迥异的 IM 平台,最大的风险不是"接不进来",而是"接进来之后每个渠道自己发明一套业务逻辑"。如果 Telegram 插件自己判断"这条消息里有没有一个批准操作"、Slack 插件自己解析"这个回调按钮点的是不是审批",核心就完全失去了对"审批""命令""URL""问题"这些动作类型的统一治理能力——同一个审批流程在十个渠道里可能有十种不同的解析方式,任何一处解析错误都可能把一条普通聊天内容误判成一次特权操作,或者反过来让一次真实的审批点击被静默丢弃。

OpenClaw 的解法是把渠道插件死死限制在"transport"这一层:插件只管平台协议的编解码(怎么连接、怎么发消息、怎么解析平台原生事件），核心负责一切跨渠道共享的类型化语义(审批、命令、URL、model-picker 等)。`docs/plugins/sdk-channel-plugins.md` 开篇第一句就是这个边界的直接体现:"Channel plugins do not implement send/edit/react tools; core provides one shared `message` tool."——十几种渠道不需要各自重新发明"发送""编辑""回应"这几个动作,它们只需要告诉核心"我这个平台怎么把一次发送真正落地"。

## 核心机制详解

### 插件的所有权清单:七件事,仅此而已

`docs/plugins/sdk-channel-plugins.md` 用一份清单直接划定了插件该管什么:

> Channel plugins do not implement send/edit/react tools; core provides one shared `message` tool. Your plugin owns:
>
> - **Config** - account resolution and setup wizard
> - **Security** - DM policy and allowlists
> - **Pairing** - DM approval flow
> - **Session grammar** - how provider-specific conversation ids map to base chats, thread ids, and parent fallbacks
> - **Outbound** - sending text, media, and polls to the platform
> - **Threading** - how replies are threaded
> - **Heartbeat typing** - optional typing/busy signals for heartbeat delivery targets
>
> Core owns the shared message tool, prompt wiring, the outer session-key shape, generic `:thread:` bookkeeping, and dispatch.

这七项全部是"平台特有的传输细节":账号怎么解析、DM 允许策略怎么配、平台的会话 ID 语法长什么样、消息怎么真正发出去、回复怎么在这个平台里挂靠到原消息。没有一项涉及"这是不是一条命令""这是不是一次审批"这类跨渠道语义——那些留给核心统一处理。

紧接着这份清单之后,文档专门为 model-picker 这个具体动作类型重申了一遍同样的边界:

> A channel that renders a `ModelPickerAction` declares its `ModelPickerCapabilityProfile`, then encodes the typed action in a transport-private authenticated callback envelope. Keep approval, command, URL, web-app, question, callback, and model-picker actions distinguishable until that encoding boundary; never infer picker intent from a raw callback string. Actor and source-message checks remain channel-owned.

这段话把"transport-only"落到了字节级别:核心先构造出一个类型化的 `ModelPickerAction`,渠道插件把它编码进一个平台原生的回调载荷(比如 Telegram inline keyboard 的 `callback_data`,或 Slack 交互组件的 `action_id`),这个编码动作发生在核心和平台协议的边界上;但渠道插件**不能**反过来在收到一个回调字符串之后自己猜"这看起来像是模型选择器的回调,我按 model-picker 处理"。谁在这一侧编码,谁就负责在另一侧原样解码,而不是靠字符串特征去反推语义。

### Extensions Boundary:transport-only 在目录结构上的强制执行

如果说 `AGENTS.md` 的那句话是设计哲学,`extensions/AGENTS.md`(所有内置渠道插件所在目录的边界说明)就是把这条哲学变成了可以被 lint/CI 检查的规则:

> This directory contains bundled plugins. Treat it as the same boundary that third-party plugins see.
>
> ...
>
> - Extension production code should import from `openclaw/plugin-sdk/*` and its own local barrels such as `./api.ts` and `./runtime-api.ts`.
> - Do not import core internals from `src/**`, `src/channels/**`, `src/plugin-sdk-internal/**`, or another extension's `src/**`.
> - Do not use relative imports that escape the current extension package root.

也就是说,即便是仓库自带的 Telegram/Discord/Slack 这些"内置"插件,在代码层面也**不享有**任何超越第三方插件的特权导入路径——它们同样只能通过 `openclaw/plugin-sdk/*` 这层公开契约和核心交互。这解决了一个常见的架构腐化路径:如果内置插件可以"抄近路"直接 import 核心内部实现,时间一长内置插件和核心之间就会长出大量未声明的隐式依赖,第三方插件永远无法达到同等能力,而"transport-only"这条边界也会在内置插件里第一个被打破。把内置插件和第三方插件放在同一条边界规则下检验,相当于用内置插件自己的构建反过来强制这条契约不会被悄悄绕过。

### 入站契约的两层分工:ingress 管"能不能",inbound 管"怎么变成一次回合"

入站方向被拆成了两个独立的 SDK 子路径,`docs/plugins/sdk-channel-ingress.md` 开篇就说明了这次拆分的分工:

> Channel ingress is the experimental access-control boundary for inbound channel events. Plugins own platform facts and side effects; core owns generic policy: DM/group allowlists, pairing-store DM entries, route gates, command gates, event auth, mention activation, redacted diagnostics, and admission.

插件调用 `resolveChannelMessageIngress(...)` 时只提供"平台事实"——发送者的稳定 ID、会话是私聊还是群聊、这次事件的鉴权模式(`inbound`/`command`/`origin-subject`/`route-only`/`none`)——核心根据这些事实结合配置里的 `allowFrom`/`groupAllowFrom`/`accessGroups` 跑出一个统一的准入决策。文档特别强调插件不能自己做这件事的"预计算":

> Do not precompute effective allowlists, command owners, or command groups. The resolver derives them from raw allowlists, store callbacks, route descriptors, access groups, policy, and conversation kind.

这次准入决策一旦做出,`channel-inbound` 才接手把它变成一次真正的 agent 回合——构建 prompt 上下文、记录会话、分发回复。两者的分界线也解释了为什么核心要求插件"原样透传"resolver 的结果而不是自己重新组装:

> Pass the exact host result; do not rebuild participant evidence from SenderId, From, session keys, routes, rooms, or message metadata.

这句话背后的风险很具体:如果插件在拿到 ingress 结果之后,又想着"方便"地从 `SenderId` 或 `From` 字段里重新拼一份判断依据,就可能在无意中绕开核心刚刚做完的准入检查,或者让一个只是"决策用、未绑定执行范围"的中间结果被误当成可以执行的最终授权。

### 身份认证分级:不能靠消息内容自证身份

`sdk-channel-ingress.md` 里的 `IdentifierAuthentication` 分级是"不要从裸内容推断出强保证"这条原则最具体的落地。它把一个发送者标识符的可信程度分成四档,从强到弱:`verified` > `asserted` > `unverified` > `mutable`。文档对每一档的定义非常克制:

> - `verified`: the owning trusted transport or session boundary bound this exact identifier to this sender.
> - `asserted`: a trusted boundary vouched for the sender without binding this exact identifier.
> - `unverified`: the identifier is exact and stable, but claimed ownership was not proved.
> - `mutable`: the identifier is a changeable or shared alias, such as a display name.

紧接着文档给出了这条分级最关键的边界条件:

> Declare `verified` only from transport or session metadata controlled by the owning boundary. Sender-controlled content, model input, ordinary message context, routing metadata, and the integrity of the host admission carrier do not establish it.

换句话说,一条消息里的文本内容、模型的推理结果、路由过程中携带的元数据,都不能把一个标识符的可信度"拔高"到 `verified`。文档给出的内置渠道声明表把这一点具体化了:

| Channel | Identifier claim | Authoritative transport or session fact |
| --- | --- | --- |
| Discord | Gateway user ID: `verified`;PluralKit member ID: `asserted`;names and tags: `mutable` | Discord 在认证过的 bot-token Gateway 会话上投递事件时自带 `author.id`/`user.id`;PluralKit 的成员 ID 来自其认证过的 API 响应,不是 Discord Gateway 本身担保的 |
| Slack | user 和 workspace-user ID:`asserted`;名字和 slug:`mutable` | 直连 Slack 投递绑定 user ID,中继模式只认证了中继对端,没有端到端的精确发送者证明 |

这张表说明"同一个渠道内部,不同字段的可信等级也可能不同"——Discord 的数字用户 ID 是 `verified`,但用户昵称永远只能是 `mutable`,渠道插件必须按字段分别声明,而不是笼统地给整个渠道打一个可信度标签。

### 出站契约:能力声明必须"诚实",偏差是契约测试的失败

出站方向的核心原则同样是一句话:"Only declare capabilities the native transport actually preserves."(`docs/plugins/sdk-channel-outbound.md`)。一个 `message` adapter 通过 `defineChannelMessageAdapter` 声明它的 `durableFinal.capabilities`(比如 `text`/`replyTo`/`thread`/`messageSendingHooks`),核心据此决定这个渠道能不能承载某些跨渠道功能(比如线程回复、消息编辑)。`docs/plugins/sdk-channel-plugins.md` 讲得更直白:

> Declare live and finalizer capabilities precisely - core uses these to decide what a channel can do, and drift between the declared and actual behavior is a contract test failure.

这条规则把"渠道能力边界"从一份可能过时的文档描述,变成了一份必须被契约测试持续验证的运行时声明——如果某个渠道声明支持 `replyTo` 但实际发送函数根本没有把 `replyToId` 传给平台 API,这不是一个"以后再修"的技术债,而是 CI 里会直接失败的契约违反。

这条边界的另一侧是核心与插件的分工声明:

> Core owns queueing, durability, the durable ingress monitor and drain..., generic retry policy, turn-adoption lifecycle..., hooks, receipts, and the shared `message` tool. The plugin owns native send/edit/delete calls, target normalization, platform threading, selected quotes, notification flags, account state, ingress inspection and payload encoding, lane keys, non-retryable predicates, optional supersede authorization, and platform-specific side effects.

同一句话里能读出的是一条清晰的横切线:凡是"跨渠道都长得一样"的机制(排队、持久化、重试策略、生命周期)归核心;凡是"这个平台特有"的机制(怎么真正调用平台 API、平台线程语义、平台的引用/通知细节)归插件。

### 原生载荷整形:平台专属数据也要走同一条出站路径

有些渠道需要发送平台专属的富媒体载荷——Slack 的 blocks、Discord 的 embeds、企业 IM 的卡片。`sdk-channel-plugins.md` 给出的做法不是让渠道另开一条发送路径,而是把这些平台专属数据塞进统一载荷的一个命名空间字段里:

> If your channel needs provider-specific shaping for `message(action="send")`, prefer `actions.prepareSendPayload(...)`. Put native cards, blocks, embeds, or other durable data under `payload.channelData.<channel>` and let core send through the outbound/message adapter.

`payload.channelData.<channel>` 这个设计延续了 transport-only 的思路:核心的 `message` 工具和整条出站流水线完全不需要认识 Slack blocks 或 Discord embeds 长什么样,它们只是被当作一段"渠道自己认识、核心不解析"的不透明数据原样带过去。

### 提及(mention)判定:平台证据在插件,策略决策在核心

`sdk-channel-plugins.md` 的"Inbound mention policy"一节把这条"证据 vs. 策略"的分层原则又重复了一遍,这次是针对"这条群消息算不算@了机器人":

> Keep inbound mention handling split in two layers:
>
> - plugin-owned evidence gathering
> - shared policy evaluation

插件负责收集平台特有的"证据"——是不是回复了机器人的消息、是不是引用了机器人的消息、平台原生的提及标记——核心的 `resolveInboundMentionDecision(...)` 根据这些证据结合 `requireMention`/隐式提及白名单/命令旁路等策略配置,统一给出"这条消息要不要触发一次 agent 回合"的最终判断。同一套证据收集/策略评估分层模式在 ingress、mention、model-picker 里反复出现,说明这不是某个具体功能的临时设计,而是这套 SDK 一以贯之的架构纪律。

## 常见问题/易踩坑

**Q:渠道插件能不能自己解析一段回调字符串,判断它是不是一次审批操作?**

不能。`AGENTS.md` 明确写着"do not infer commands from raw strings",`sdk-channel-plugins.md` 对 model-picker 的具体要求是"never infer picker intent from a raw callback string"。正确做法是核心在编码时把动作类型固化进回调载荷的结构里(例如带上一个类型标记字段),插件在解码时原样读出这个类型,而不是靠字符串前缀、分隔符特征等启发式规则去猜。Telegram 插件的护栏写得更直接:"Native callbacks stay structured. Approval, native command, plugin, select, and multiselect callbacks must not fall through as raw callback text. Preserve callback values exactly, including delimiters such as `env|prod`."(`extensions/telegram/AGENTS.md`)——下一篇会展开讲这条规则在 Telegram 具体实现里踩过的坑。

**Q:一个渠道插件能不能直接把 `SenderId` 字段当成已验证身份使用?**

不能,除非这个字段的可信等级本身就被声明为 `verified`。`IdentifierAuthentication` 分级明确排除了"消息内容""模型输入""路由元数据"作为身份证据的来源——一个平台的用户昵称即便看起来很像某个已知白名单条目,也只能按 `mutable` 处理,不能因为文本匹配就当作强身份凭证放行。

**Q:内置的 Telegram/Discord 插件是不是可以走"内部快捷通道"直接调用核心实现?**

不可以。`extensions/AGENTS.md` 明确说"Treat it as the same boundary that third-party plugins see"——内置插件和第三方插件必须遵守同一套 `openclaw/plugin-sdk/*` 导入边界,不能 import `src/channels/**` 之类的核心内部实现。这保证了 transport-only 的边界不会因为"反正是自己人"而被内置插件率先打破。

## 小结

`AGENTS.md` 的"channels transport-only"这条规则,把渠道插件的职责死死限制在协议编解码这一层:七件事——配置、DM 安全、配对、会话语法、出站发送、线程、心跳打字——之外的一切跨渠道语义(命令、审批、URL、model-picker、准入策略、提及判定)全部收归核心。这条边界不仅是一句设计建议,还通过 `extensions/AGENTS.md` 的导入规则、`channel-ingress` 与 `channel-inbound` 的职责分离、`IdentifierAuthentication` 的证据分级、出站能力声明的契约测试,层层落到了可以被 CI 验证的具体机制上。下一篇我们把镜头拉近到几个真实的渠道实现——长驻网关连接型的 Discord、依赖 macOS 私有能力的 iMessage、联邦协议的 Matrix、企业 IM 的 Microsoft Teams——看看同一套契约之下,不同协议形态各自要解决哪些"transport"层面的具体问题,以及 Telegram 插件的 `AGENTS.md` 里那些用真实故障教训换来的实现细节。
