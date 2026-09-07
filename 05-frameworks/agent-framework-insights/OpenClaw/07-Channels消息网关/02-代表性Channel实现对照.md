# 代表性 Channel 实现对照

> 同一套 `ChannelPlugin` 契约之下,Telegram 靠长轮询,Discord 直连一条常驻的 Gateway WebSocket,iMessage 要在一台真实的 Mac 上关掉系统完整性保护(SIP)才能拿到完整能力,Matrix 是一套联邦协议、房间可能加密也可能不加密,Microsoft Teams 则要在"实时但看不到历史"和"能看历史但要走 Graph API 管理员授权"之间做选择。上一篇讲的是这些渠道共享的契约边界,这一篇专门挑几个协议形态差异最大的实现,看看"transport-only"这条纪律具体要吸收哪些协议层面的麻烦事,以及 `extensions/telegram/AGENTS.md` 这份用真实故障教训写成的护栏文档。

## 学习目标

- 理解长驻网关连接型渠道(Discord)与轮询/CLI 桥接型渠道(Telegram、iMessage)在"谁维护连接状态"这件事上的根本差异。
- 通过 iMessage 的私有 API 能力协商(SIP 开关、Library Validation),理解一个依赖操作系统私有能力的渠道要如何把"能力探测"和"降级策略"做成显式契约而不是隐式假设。
- 理解 Matrix 作为联邦协议在加密房间(E2EE)、跨设备信任(cross-signing)上引入的额外状态维度,以及这些状态如何在不引入配置的情况下被自动探测。
- 理解 Microsoft Teams 的 RSC 权限与 Graph API 权限两条完全不同的能力路径——一条实时但看不到历史,一条能查历史但需要租户管理员批准。
- 通过 `extensions/telegram/AGENTS.md` 里的具体条目(durable-before-ack、native 回调结构化、群历史窗口),理解一份渠道专属 `AGENTS.md` 是怎么把真实事故教训固化成"以后不能再犯"的护栏。

## 背景与设计动机

第一篇讲的 `ChannelPlugin` 契约只回答了"渠道插件该实现哪些接口",没有回答"每种协议形态在实现这些接口时各自会撞上什么麻烦"。一个长轮询渠道要处理的是"轮询间隔和实时性的取舍",一个常驻 WebSocket 渠道要处理的是"连接断开重连期间的消息丢失窗口",一个依赖操作系统私有能力的渠道要处理的是"这台机器到底有没有这个能力,没有的时候怎么体面降级"，一个联邦协议渠道要处理的是"这个房间的信任状态是不是这次会话独有的"。这些问题没有一个能在 `ChannelPlugin` 接口层面被抽象掉——它们必须留在每个具体渠道插件的实现细节里,而 `docs/channels/*.md` 恰恰是记录这些协议特有麻烦事的地方。

## 核心机制详解

### 长驻网关连接型:Discord

Discord 走的是一条常驻的 Gateway WebSocket 连接,`docs/channels/discord.md` 的"Runtime model"一节把这类渠道的典型形状总结得很清楚:

> - Gateway owns the Discord connection.
> - Reply routing is deterministic: Discord inbound replies back to Discord.
> - By default (`session.dmScope=main`), direct chats share the agent main session (`agent:main:main`).
> - Guild channels are isolated session keys (`agent:<agentId>:discord:channel:<channelId>`).
> - A send response without a Discord message ID stays unconfirmed. Queued delivery records the missing identity for recovery instead of reporting success or immediately sending a duplicate; inspect delivery warnings with `openclaw health --verbose`.

最后一条很值得注意:一次发送如果拿不到平台返回的消息 ID,系统不会假装"发送成功了",也不会立刻重发一份造成重复——而是把这次不确定的发送记录下来等待恢复检查。这是"常驻连接型"渠道普遍要面对的问题:网络抖动、平台限流、连接短暂中断都可能让"发送请求已提交"和"发送真正落地"这两件事之间出现不确定窗口,渠道实现必须诚实地把这种不确定性暴露出来,而不是靠乐观假设掩盖过去。

Discord 论坛频道(forum channel)只接受帖子而不是普通消息,这也是协议层面的特殊性——OpenClaw 用"发消息到论坛父频道自动建帖"和显式的 `openclaw message thread create` 两条路径来适配这个模型,而不是假装论坛频道和普通频道是同一种东西。

### 依赖操作系统私有能力型:iMessage

iMessage 是这几个代表性实现里协议形态最特殊的一个——它没有官方开放 API,OpenClaw 通过 `steipete/imsg` 这个本地 CLI 工具,用 JSON-RPC over stdio 和跑在 Mac 上的 `imsg rpc` 子进程通信。`docs/channels/imessage-from-bluebubbles.md` 描述得很直接:"There is no HTTP server, webhook URL, background daemon, launch agent, or port to expose."

真正体现"能力协商"这个主题的是它的两种运行模式。基础模式无需改动系统设置就能收发文本和媒体;但 reaction、编辑、撤回、线程回复、发送特效、群管理这些高级动作,需要 `imsg` 把一个辅助 dylib 注入到 `Messages.app` 里调用私有的 `IMCore` API,而这一步的前提是系统关闭 SIP(System Integrity Protection):

> `imsg launch` refuses to inject when SIP is enabled.
>
> **Disabling SIP is a real security tradeoff.** SIP is one of macOS's core protections against running modified system code; turning it off system-wide opens up additional attack surface and side effects. Notably, **disabling SIP on Apple Silicon Macs also disables the ability to install and run iOS apps on your Mac**.

文档没有把这个选择简化成"照着做就行",而是把安全权衡明确摆到操作者面前,并给出了折中方案——用一台专用的 bot Mac 关闭 SIP 承担 iMessage 工作负载,主力设备保持 SIP 开启。这是一种把"平台能力边界"翻译成"运维决策"的做法:渠道插件本身通过探测 `imsg status --json` 返回的 `privateApi.available` 字段知道当前能力集合,而不是假设某个动作永远可用。文档也交代了这个探测的时效性问题:

> If `openclaw channels status --probe` reports the channel as `works` but specific actions throw "iMessage `<action>` requires the imsg private API bridge" at dispatch time, run `imsg launch` again — the helper can fall out (Messages.app restart, OS update, etc.) and the cached `available: true` status will keep advertising actions until the next probe refreshes.

这说明"能力探测"不是一次性的静态配置,而是一个会随系统状态漂移(Messages.app 重启、系统升级)而失效的缓存值,渠道实现必须能应对"探测结果过期"这种情况,而不是把第一次探测的结果当成永久真理。

### 联邦协议型:Matrix

Matrix 房间可能加密(E2EE)也可能不加密,而且加密状态是"运行时属性"而不是配置项——`docs/channels/matrix.md` 说得很干脆:"No configuration is needed - the plugin detects E2EE state automatically."插件必须在每次发送图片时判断当前房间是不是加密房间,分别用 `thumbnail_file`(加密房间,连缩略图也要加密)或 `thumbnail_url`(非加密房间)。这是联邦协议引入的一个"协议本身就带状态机"的例子——普通消息渠道只需要判断"发到哪个会话",Matrix 渠道还要额外判断"这个会话此刻处于什么加密状态"。

Matrix 的跨设备信任模型也比一般 IM 渠道复杂得多。`verify status` 命令报告的是三个相互独立的信任信号,而不是一个简单的"已验证/未验证"布尔值:

> - `Locally trusted`: trusted by this client only
> - `Cross-signing verified`: the SDK reports verification via cross-signing
> - `Signed by owner`: signed by your own self-signing key (diagnostic only)
>
> `Verified by owner` is `yes` only when `Cross-signing verified` is `yes`; local trust or an owner signature alone is not enough.

这三个信号分开报告而不是折叠成一个总分,原因和上一篇讲的 `IdentifierAuthentication` 分级是同一个思路——"本地信任"和"跨签名验证"是两种强度完全不同的证据,把弱证据和强证据混在一起报告,会让运维人员误以为某个设备已经达到了它实际没有达到的信任级别。

### 企业 IM 型:Microsoft Teams 的 RSC 与 Graph 两条路

Microsoft Teams 提供了两条互不重叠的能力路径,`docs/channels/msteams.md` 用一张对比表说清楚了取舍:

> | Capability | RSC permissions | Graph API |
> | --- | --- | --- |
> | **Real-time messages** | Yes (via webhook) | No (polling only) |
> | **Historical messages** | No | Yes (can query history) |
> | **Setup complexity** | App manifest only | Requires admin consent + token flow |
> | **Works offline** | No (must be running) | Yes (query anytime) |
>
> **Bottom line:** RSC is for real-time listening; Graph API is for historical access. To catch up on missed messages while offline, you need Graph API with `ChannelMessage.Read.All` (requires admin consent).

这条边界背后是企业 IM 场景特有的治理复杂度——RSC(Resource-Specific Consent)权限只需要把应用清单(manifest)装进 Teams 就能拿到实时 webhook 推送,但拿不到历史消息,也拿不到 SharePoint/OneDrive 里存储的文件内容;要拿历史或者文件,必须在 Entra ID(原 Azure AD)里申请 Graph 应用权限并让租户管理员显式批准。这不是 OpenClaw 自己的设计选择,而是 Microsoft 平台把"实时监听"和"历史查询"两种能力刻意分离成两套独立的授权体系——渠道插件的职责就是诚实地把这条平台边界呈现给操作者,而不是假装两者可以无缝互通。

文档里还有一个具体的坑:Teams 有时会把消息里的文件标记从发给机器人的 HTML 活动载荷中剥离,导致 Bot Framework 收到的内容和普通无附件消息完全无法区分,只有 Graph 那份消息副本才保留完整的附件引用。这就是为什么 `graphMediaFallback` 默认关闭而不是默认开启——因为一旦打开,每一条看起来没有直接可下载媒体的 HTML 活动都会额外触发一次 Graph 消息查询,这对没有申请相应权限的部署是白白增加的失败请求。

### Telegram:一份用真实事故写成的护栏文档

如果说前面几个渠道展示的是"协议形态差异",`extensions/telegram/AGENTS.md` 展示的是"一个具体渠道实现踩过的坑,以后不能再踩一遍"。这份文档开篇就把自己的性质讲清楚了:

> Read this before any change under `extensions/telegram/`. These are intentional maintainer decisions and review-binding invariants, not incidental implementation details.

几条最值得展开的护栏:

**Durable-before-ack。** 无论是长轮询还是 webhook,Telegram 插件都要求"先落盘、再确认":

> Durable-before-ack on both transports. Polling: ingress worker advances its offset only after the parent's committed spool enqueue (`writeTelegramSpooledUpdate`). Webhook: respond 200 only after the spool write; non-200 on write failure is the redelivery contract.

这条规则背后的风险很具体:如果轮询 worker 先推进 offset 再写入本地队列,一旁刚好在这两步之间进程崩溃,那条消息就会永久丢失——Telegram 不会重新推送一个已经被 offset 认领过的更新。反过来,如果 webhook 在没有成功落盘之前就回了 200,Telegram 同样会认为投递已完成,从而放弃这条消息未来的重投机会。"先持久化、再确认收到"这个顺序不能颠倒,是保证消息不丢的底线。

**Native 回调必须保持结构化。** 这条直接呼应了第一篇讲的"不要从裸字符串推断命令":

> Native callbacks stay structured. Approval, native command, plugin, select, and multiselect callbacks must not fall through as raw callback text. Preserve callback values exactly, including delimiters such as `env|prod`.

值得注意的是后半句——"Preserve callback values exactly, including delimiters such as `env|prod`"——这提示了一类容易被忽略的 bug:如果解析回调数据时用一个过于宽松的分隔符规则(比如简单地按 `|` 切分),而回调值本身恰好包含这个分隔符(比如一个环境名叫 `env|prod`),错误的解析就会把一个合法值截断成两段,进而匹配到错误的处理分支。结构化回调不仅要求"不要靠猜",还要求编解码双方对分隔符、转义规则有完全一致的理解。

**流式预览不能靠 draft 消息实现最终交付。** Telegram 的 `sendMessageDraft` 只是私聊里 30 秒的临时预览,不是真正的消息:

> Do not reintroduce `sendMessageDraft` for answer streaming. Telegram drafts are ephemeral 30-second previews in private chats; final delivery still requires a separate `sendMessage`. OpenClaw uses `sendMessage` plus `editMessageText`, then finalizes in place so the user sees one persistent answer.

这条护栏的价值在于它明确排除了一个"看起来可行、实际上会在生产环境里悄悄失效"的实现路径——如果只用 draft 消息承载流式输出,30 秒之后用户看到的回复会凭空消失,而不是停留在最后一次编辑的内容上。

**群历史窗口不能引入"是否可用"的开关。** 这条护栏是从一次真实的功能回归里提炼出来的:

> The group history window is always on for groups and bounded by `historyLimit`. Do not reintroduce prompt-history gating modes; that regression blinded ambient rooms.

"blinded ambient rooms"这几个字直接点名了后果——一旦给群历史窗口加上一个可以被关闭的开关,常驻监听但不常被提及的群聊(ambient room)就会失去上下文,agent 在这些房间里会变得像刚加入群聊一样对之前发生的事情一无所知。

**Pairing 只在私聊里生效。** "Pairing is DM-only. Group and topic authorization need explicit config allowlists."这条把配对(pairing,下一篇会详细展开)和群组授权的适用范围划得很清楚——不要指望群聊里的陌生发送者能通过配对流程获得访问权限,群组访问只能靠显式的允许列表配置。

**Telegram 的允许列表只认数字 ID。** "Telegram allowlists use numeric sender IDs. Usernames are optional, mutable, and not a reliable arbitrary-user lookup key in the Bot API."这条呼应了上一篇讲的身份认证分级——Telegram 的用户名可以随时修改、也可能压根没有,只有数字用户 ID 才是稳定的身份标识,任何依赖用户名做访问控制的配置都建立在一个可以被随时改写的地基上。

## 常见问题/易踩坑

**Q:iMessage 的私有 API 能力是不是配置一次就永久生效?**

不是。`imsg` 的私有 API 桥接依赖注入到 `Messages.app` 进程里的辅助模块,这个模块可能因为应用重启、系统升级而"掉线"。渠道插件缓存的 `available: true` 状态在下一次探测刷新之前不会自动失效,这意味着实际调用时仍可能遇到"探测说可用,但这个动作抛出私有 API 桥接不可用"的错误——遇到这种情况应该重新运行 `imsg launch` 并触发一次新的探测,而不是假设配置文件里的开关能一劳永逸。

**Q:Microsoft Teams 只装了 RSC 权限,为什么收不到历史消息也下载不了群里的图片?**

这是平台权限模型本身的边界,不是配置遗漏。RSC 权限只覆盖实时 webhook 投递的文本内容,历史查询和 SharePoint/OneDrive 里的文件下载需要单独申请 Graph 应用权限并经过租户管理员同意——这是两条完全独立的授权路径,装了前者不会自动带出后者的能力。

**Q:Telegram 插件为什么不能用更宽松的字符串匹配来解析回调数据?**

因为回调值本身可能包含被当作分隔符的字符(比如 `env|prod` 里的 `|`)。`extensions/telegram/AGENTS.md` 明确要求"Preserve callback values exactly, including delimiters"——回调编解码双方必须对分隔符和转义规则有完全一致的约定,任何试图靠简单字符串切分"猜"出语义的实现都可能在这类边界输入上出错。

## 小结

这一篇挑了四种协议形态差异很大的渠道:常驻 Gateway 连接的 Discord 要面对发送确认的不确定性窗口;依赖操作系统私有能力的 iMessage 要把"能力探测可能过期"作为一等公民对待;联邦协议的 Matrix 要处理加密状态自动探测和多信号跨设备信任;企业 IM 的 Microsoft Teams 要在"实时但无历史"的 RSC 和"有历史但需管理员批准"的 Graph 之间做治理决策。`extensions/telegram/AGENTS.md` 则展示了同一套契约之下,一个具体渠道实现是怎么把真实事故(消息丢失、群聊失忆、流式预览凭空消失)转化成不可再犯的护栏条目。下一篇转向渠道之上的另一层机制——陌生发送者的配对流程(Pairing)、群组与访问控制模型,以及防止两个机器人互相触发陷入死循环的 bot loop protection。
