# Channels 接入与 Pairing 速览

> “Treat inbound messages as untrusted input”——README 安全一节的这句话，是理解 OpenClaw Channels 设计的钥匙。一个能执行 shell 命令、读写文件的 AI 助理一旦接进 Telegram、WhatsApp 这类公网可达的聊天软件，任何人都可能给它发消息。OpenClaw 的默认答案不是“相信配置正确的人不会犯错”，而是在协议层面直接加一道闸：陌生发送者的第一条消息**不会被处理**，只会收到一个配对码，等操作者显式批准。这道闸就是 Pairing。

## 学习目标

- 理解 Channels 在 OpenClaw 里的定位：把同一个 Gateway、同一个 agent 接到不同聊天软件的“传输层插件”，而不是每个聊天软件对应一个独立的助理实例。
- 分清三种 Channel 打包方式：随核心一起装的 bundled plugin、装一条命令就能用的 official plugin、维护在仓库之外的 external plugin，知道这个分类会直接影响“要不要额外装一步”。
- 走通 DM Pairing 的完整生命周期：陌生发送者收到配对码 → 操作者在 Control UI 或 CLI 批准 → 该发送者获得私聊权限（但不等于群组权限、也不等于命令 owner 权限）。
- 知道为什么“陌生人发消息默认要审批”而不是“默认放行”，这条默认值背后的信任模型依据是什么。
- 明确本篇只建立第一手直觉：每个 Channel 具体怎么接、Channel 插件契约怎么设计，是第 07 章的内容；这里不展开。

## 背景与设计动机

OpenClaw 想做的事情，是让助理“出现在你已经在用的聊天软件里”，而不是逼着用户再学一个新的聊天客户端。README 的定义很直接：*“OpenClaw is an AI assistant that runs on your devices and meets you in the channels you already use.”* 这意味着 Channels 这一层要解决的核心问题是**协议转换**：把 Telegram Bot API、WhatsApp 的 QR 登录会话、Slack 的 Socket Mode 事件，统一转换成 Gateway 能理解的消息/会话事件，出站的时候再反向转换回去。

但协议转换本身只是“能不能通”的问题，“该不该通”是另一个维度。一旦某个 Channel 接通了公网可达的聊天软件，理论上任何知道这个账号/群组地址的人都可以给这个 agent 发消息。如果 agent 配了 exec、文件读写这类工具，一条精心构造的消息就有可能诱导它执行不该执行的操作。SECURITY.md 把这类风险明确列在“Agent and Model Assumptions”里：

> The model/agent is **not** a trusted principal. Assume prompt/content injection can manipulate behavior. Security boundaries come from host/config trust, auth, tool policy, sandboxing, and exec approvals.

Pairing 正是这些“security boundaries”里最靠前的一道——它发生在消息进入 agent 之前，用一次显式的人工批准，把“谁能跟这个助理说话”这件事从“消息内容判断”里剥离出来，变成一个独立的、由操作者掌控的准入名单。这也是为什么本篇要把 Channels 和 Pairing 放在同一篇讲：接入渠道和为这条渠道设置准入闸门，在 OpenClaw 里是同一个心智动作的两半。

## 核心机制详解

### Channel 的三种打包方式

`docs/channels/index.md` 在介绍每个 channel 之前，先说明了打包方式如何影响接入的复杂度：

> Entries marked "bundled plugin" or "included in core" ship with the core install. Channels marked "official plugin" install with one command (`openclaw plugins install @openclaw/<id>`) or on demand during `openclaw onboard` / `openclaw channels add`, then need a Gateway restart. "External plugin" channels are maintained outside the OpenClaw repo.

这三档打包方式，本质上对应着 VISION.md 里“两层两条门槛”的插件哲学在 Channels 这个具体领域的体现——核心自带的 channel（比如 Telegram、A2A、Reef）经过了最严格的审视，因为每加一个核心能力都会摊到每个操作者的每次模型请求成本上；而绝大多数聊天平台（Discord、Slack、WhatsApp、Signal……）都是“official plugin”，装一条命令、重启一次 Gateway 就能用，不占核心的“每次调用税”。这个分层解释了为什么 OpenClaw 能同时支持二十多个聊天平台而不显得臃肿：核心足够小，扩展面足够大。

文档里给出的建议起点是 Telegram，理由很朴素——它不需要额外装插件，只要一个 bot token：

```bash
openclaw channels add --channel telegram --token <bot-token>
```

> Start with **Telegram**. It needs a bot token and no plugin install, so it is the fastest channel to get working. WhatsApp requires QR pairing and stores more state on disk.

添加 channel 之后需要重启一次 Gateway 新账号才会生效，这也再次印证了“Gateway 是唯一控制平面”这条原则——channel 账号的启动，本质上是 Gateway 进程内部的一次插件装配变化，不是独立进程。

### DM Pairing：陌生发送者的第一道闸

`docs/channels/pairing.md` 把 Pairing 定义为 OpenClaw 里“显式访问审批”这一个动作在两个场景下的应用：

> "Pairing" is OpenClaw's explicit access approval step. It is used in two places:
>
> 1. **DM pairing** (who is allowed to talk to the bot)
> 2. **Node pairing** (which devices/nodes are allowed to join the gateway network)

本篇聚焦第一种。当某个 channel 的 DM 策略设置为 `pairing`（这是大多数聊天平台的默认策略），陌生发送者发来的第一条消息不会进入 agent 处理流程，而是触发一次配对请求：

> When a channel is configured with DM policy `pairing`, unknown senders get a short code and their message is **not processed** until you approve.

配对码本身的设计带有明显的可用性考量——够短、避免容易混淆的字符、有过期时间、也有防刷限制：

> - 8 characters, uppercase, no ambiguous chars (`0O1I`).
> - **Expire after 1 hour**. The bot only sends the pairing message when a new request is created (roughly once per hour per sender).
> - Pending DM pairing requests are capped at **3 per channel account**; additional requests are ignored until one expires or is approved.

批准配对请求有两条路径。图形化的方式是在 Control UI 里打开 **Settings → Channels → DM access requests**，这个队列会把所有配置了 `pairing` 策略的 channel 账号的待批准请求汇总在一起，按 channel/account 过滤、查看发送者信息，然后点 **Approve**。命令行的方式更适合脚本化或者没有图形界面的服务器场景：

```bash
openclaw pairing list telegram
openclaw pairing approve telegram <CODE>
```

批准之后拿到的权限范围是有明确边界的，容易被误解成“这个人现在可以对 bot 为所欲为”，但实际上：

> Approval grants direct-message access only. It does not grant group access.

CLI 批准流程还有一个值得注意的细节：如果当前完全没有配置命令 owner（能执行敏感命令、批准 exec 请求的人），CLI 会自动把这第一个被批准的发送者设为 owner；但这只在“完全没有 owner”的情况下发生一次，之后的配对批准就只授予 DM 访问权限，不会再顺带授予 owner 身份：

> Unlike the Control UI's explicit checkbox, the CLI automatically bootstraps `commands.ownerAllowFrom` when no command owner is configured... After an owner exists, later pairing approvals only grant DM access; they do not add more owners.

这个“首次自动引导、之后必须显式操作”的设计，呼应了 OpenClaw 一贯的思路：关键权限的授予要么发生在明确无人掌控的初始状态（此时自动化是安全的，因为不这么做系统就没有 owner），要么必须由已经存在的信任链条显式确认，不存在“顺手就升级了权限”的中间地带。

### 陌生人为什么默认要审批，而不是默认放行

`dmPolicy: "open"`（无需审批、任何人都能直接对话）在 OpenClaw 里不是不存在，而是被限制得很谨慎：

> `dmPolicy: "open"` is public only when the effective DM allowlist includes `"*"`. Setup and validation require that wildcard for public-open configs.

也就是说，“完全开放”必须显式声明一个通配符白名单，不能靠遗漏配置意外达成——这是一种“默认拒绝、显式选择开放”的设计惯例，跟 SECURITY.md 里反复强调的“strong defaults without killing capability”（VISION.md 原话）是同一种取舍：默认值要保守，但不堵死操作者主动选择更开放配置的路径。

把这条默认值放回信任模型里看会更清楚：一旦某个 agent 配了工具，任何能跟它说上话的人事实上都在共享这个 agent 的工具权限（这是 SECURITY.md “One-User Trust Model” 一节的核心判断：*“If multiple people can message the same tool-enabled agent... they can all steer that agent within its granted permissions.”*）。既然如此，“谁能跟 agent 说话”这道闸就必须默认收紧，而不是默认敞开——Pairing 正是把这道闸做成了显式的、可审计的操作者动作，而不是隐藏在某个不起眼的配置项里。

### 可复用的信任名单：`accessGroups`

如果同一批可信发送者需要同时出现在多个 channel 的白名单里，或者要同时管 DM 和群组两套准入规则，逐个 channel 重复填写发送者 ID 会很快变得难以维护。OpenClaw 为此提供了顶层的 `accessGroups` 配置，把“这批人是谁”和“他们在哪个 channel 里有什么权限”拆成两层：

```json5
// openclaw.json 节选（docs/gateway/pairing.md）
{
  accessGroups: {
    operators: {
      type: "message.senders",
      members: {
        discord: ["discord:123456789012345678"],
        telegram: ["987654321"],
        whatsapp: ["+15551234567"],
      },
    },
  },
  channels: {
    telegram: { dmPolicy: "allowlist", allowFrom: ["accessGroup:operators"] },
    whatsapp: { groupPolicy: "allowlist", groupAllowFrom: ["accessGroup:operators"] },
  },
}
```

`accessGroup:operators` 这个引用可以同时出现在不同 channel 的 `allowFrom`/`groupAllowFrom` 里，维护一份名单就能同步影响所有引用它的地方——这也是“配置即代码”思路的一个小体现：信任关系被声明成一份可复用、可审计的数据，而不是散落在每个 channel 各自的配置块里、容易改了一处忘了另一处。

### 群组场景下的另一重克制：加入群组时的自我介绍

Pairing 管的是“谁能触发 agent”，但即便触发权限已经放开（比如 bot 被拉进了一个群），OpenClaw 在“要不要主动说话”这件事上依然保持了克制。Discord、LINE、Matrix、Slack、Telegram 这几个 channel 在 bot 加入允许的群组时，会自动发一条基于房间上下文生成的自我介绍，而不是默默潜伏。这个功能本身的安全设计很能说明 OpenClaw 一贯的思路——房间的标题、话题、置顶消息、历史消息全部被当成**第三方不可信内容**处理：

> Room titles, topics, pinned text, and message history are third-party content, so they are wrapped as untrusted external content and the introduction turn runs with no tools available at all. Instructions embedded in a room cannot reach a tool.

即便只是生成一句“这个群看起来是做什么用的”的自我介绍，这一次模型调用也被限制在完全没有工具的上下文里，而且不会在私聊场景触发、也不会绕过 channel 本身的访问策略。这是一个很小的功能，但它把“入站内容默认不可信”这条基线，从“要不要处理陌生人的消息”延伸到了“连群组元数据这种看似无害的上下文也要按不可信内容对待”——这条基线会在第 5 篇被更系统地展开。

### 顺带一提：Node Pairing 是另一件事

`docs/channels/pairing.md` 里第二种 Pairing——Node Pairing——管的是 iOS/Android/macOS/headless 节点设备能不能加入 Gateway 网络，走的是设备身份 + 公钥匹配的审批流程，和 DM Pairing 管“聊天软件里的陌生发送者”完全是两套状态、两套审批入口，不要混为一谈。这部分设备与 Companion App 的接入细节留给第 08 章展开。

## 常见问题/易踩坑

- **以为批准了 DM 配对，这个人就能在群里对 bot 发号施令**：不对，DM 配对只管私聊权限；群组的访问控制是独立的一套（`groupPolicy`/`groupAllowFrom` 之类），批准 DM 请求不会自动放开群组权限。
- **把手动加进白名单（`allowFrom`）的发送者当成自动获得了 owner 身份**：不会，手动加白名单只解决“能不能对话”，owner 身份是单独的 `commands.ownerAllowFrom` 配置，如果没有配置，owner-only 命令会直接回复需要操作者手动运行的确切配置命令。
- **把 WhatsApp 的登录二维码和 DM 配对搞混**：WhatsApp 的登录 QR 是把某个 WhatsApp 账号绑定给 OpenClaw 本身，DM 配对审批的是“谁可以给这个已绑定的账号发消息”，两者是完全独立的两个流程。

## 小结

Channels 把 OpenClaw 接进你已经在用的聊天软件，但打包方式（bundled/official/external plugin）决定了接入的额外步骤有多少；Pairing 则是在消息真正进入 agent 之前的一道显式准入闸门，陌生发送者默认被挡在配对码之外，批准之后拿到的也只是私聊权限，而不是群组或 owner 权限。具体到每一个 Channel 的协议细节、以及 Channel 插件契约本身怎么设计，留给第 07 章深入。下一篇会转向“这个助理用哪个大模型回答问题”——Model Provider 抽象的第一手介绍，以及 Onboarding 向导如何在配置任何东西之前，先验证一次真实可用的模型访问。
