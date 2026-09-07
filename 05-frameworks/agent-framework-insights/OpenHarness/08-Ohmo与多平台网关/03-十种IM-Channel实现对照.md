# 十种 IM Channel 实现对照

> Telegram 用长轮询,Slack 用 Socket Mode,Discord 直连 Gateway WebSocket,飞书用 lark-oapi 的长连接,DingTalk 用 Stream Mode,Matrix 用 `nio` 的 sync 循环,Mochat 用 Socket.IO,QQ 用官方 `botpy` SDK,WhatsApp 干脆桥接一个 Node.js 进程,Email 则完全没有"连接"这回事,靠 IMAP 轮询收信、SMTP 发信。十种协议形态、十套 SDK,但 `ChannelManager` 只认三个方法:`start`/`stop`/`send`。这篇文章拆开 `BaseChannel` 这个统一接口,对照几个有代表性的实现,看看"接入一个新 IM 平台"到底需要交代清楚哪些事情。

## 学习目标

- 理解 `BaseChannel` 定义的最小契约:三个抽象方法(`start`/`stop`/`send`)加两个共享能力(`is_allowed` 权限检查、`_handle_message` 统一封装 `InboundMessage`),新增一个平台只需要实现这三个方法。
- 通过 Telegram(长轮询 + SDK)、Slack(Socket Mode)、Email(IMAP/SMTP 轮询,没有常驻连接)三种代表性实现,归纳出"connect 型"和"poll 型"两类 channel 在 `start`/`send` 里各自要处理的问题。
- 理解 `channels/bus/events.py`/`queue.py` 如何把十种平台的原始消息统一成 `InboundMessage`/`OutboundMessage` 两个 dataclass,以及为什么这一步是让 `ChannelManager` 和 gateway 上层完全不需要感知平台差异的关键。
- 理解 `ChannelManager._init_channels()` 用 `try/except ImportError` 做的按需导入,以及它和第一课参考范文里 Hermes 的注册表式延迟加载相比,是同一类问题的另一种更朴素的解法。
- 知道 `ohmo`/OpenHarness 目前支持的十种 IM 平台分别是谁,对国内平台(飞书、钉钉、QQ)的覆盖是这套 channel 体系一个值得注意的特点。

## 背景与设计动机

个人助理场景下,用户希望在自己习惯用的聊天工具里直接跟 Agent 对话,而不是被迫切换到一个专门的网页或 CLI。这就要求 gateway 能同时对接尽可能多的 IM 平台——但每个平台的协议形态天差地别:有的提供官方 SDK 和长连接(Telegram、Slack、Discord),有的走应用平台自己的消息网关协议(飞书、DingTalk、企业向 IM 常见的模式),有的完全没有"实时推送"这个概念,只能定期轮询(Email)。如果 gateway 上层的路由、会话管理、命令处理都要为每种协议单独适配,系统会迅速失控。`BaseChannel` 的作用就是把这些差异全部挡在一层抽象之后,让 `ChannelManager` 和更上层的 `OhmoGatewayBridge` 只需要面对两个统一的数据结构和三个统一的方法。

## 核心机制详解

### BaseChannel:三个抽象方法 + 两个共享能力

```python
# src/openharness/channels/impl/base.py:34-95(节选)
class BaseChannel(ABC):
    """
    Abstract base class for chat channel implementations.

    Each channel (Telegram, Discord, etc.) should implement this interface
    to integrate with the nanobot message bus.
    """

    name: str = "base"

    def __init__(self, config: Any, bus: MessageBus):
        self.config = config
        self.bus = bus
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """Connect, listen for messages, forward them to the bus via _handle_message()."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through this channel."""

    def is_allowed(self, sender_id: str) -> bool:
        """Check if *sender_id* is permitted.  Empty list → deny all; ``"*"`` → allow all."""
        allow_list = getattr(self.config, "allow_from", [])
        if not allow_list:
            logger.warning("%s: allow_from is empty — all access denied", self.name)
            return False
        if "*" in allow_list:
            return True
        sender_str = str(sender_id)
        return sender_str in allow_list or any(
            p in allow_list for p in sender_str.split("|") if p
        )
```

`start()`/`stop()`/`send()` 是唯一的强制契约,平台内部怎么维护连接、怎么解析消息格式完全是实现细节。`is_allowed()` 和 `_handle_message()` 是所有子类免费获得的共享能力——`is_allowed()` 的默认策略是**空列表拒绝所有人**,而不是放行所有人,这是一处刻意的默认拒绝设计(下文"常见问题"部分展开)。每个子类的 `start()` 内部,收到一条平台消息后最终都要调用继承来的 `_handle_message()`:

```python
# src/openharness/channels/impl/base.py:96-136(节选)
async def _handle_message(
    self,
    sender_id: str,
    chat_id: str,
    content: str,
    media: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    session_key: str | None = None,
) -> None:
    if not self.is_allowed(sender_id):
        logger.warning(
            "Access denied for sender %s on channel %s. "
            "Add them to allowFrom list in config to grant access.",
            sender_id, self.name,
        )
        return

    msg = InboundMessage(
        channel=self.name,
        sender_id=str(sender_id),
        chat_id=str(chat_id),
        content=content,
        media=media or [],
        metadata=metadata or {},
        session_key_override=session_key,
    )
    await self.bus.publish_inbound(msg)
```

权限检查和封装成统一事件这两件事在基类里做完,子类完全不需要重复实现。

### Connect 型实现:Telegram(长轮询 + 官方 SDK)

`TelegramChannel` 基于 `python-telegram-bot`,`start()` 里构建一个 `Application` 并注册消息处理器,靠库自带的长轮询机制拉取更新——不需要公网 IP 或 webhook,这也是源码注释里特意强调的选型理由("Simple and reliable - no webhook/public IP needed")。`send()` 则要处理平台特有的限制:消息长度上限、Markdown 到平台专属富文本格式的转换、转换失败时的降级:

```python
# src/openharness/channels/impl/telegram.py:273-311(节选)
if msg.content and msg.content != "[empty message]":
    is_progress = msg.metadata.get("_progress", False)
    draft_id = msg.metadata.get("message_id")

    for chunk in split_message(msg.content, TELEGRAM_MAX_MESSAGE_LEN):
        try:
            html = _markdown_to_telegram_html(chunk)
            if is_progress and draft_id:
                await self._app.bot.send_message_draft(
                    chat_id=chat_id, draft_id=draft_id, text=html, parse_mode="HTML"
                )
            else:
                await self._app.bot.send_message(
                    chat_id=chat_id, text=html, parse_mode="HTML", reply_parameters=reply_params
                )
        except Exception as e:
            logger.warning("HTML parse failed, falling back to plain text: %s", e)
            try:
                if is_progress and draft_id:
                    await self._app.bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=chunk)
                else:
                    await self._app.bot.send_message(chat_id=chat_id, text=chunk, reply_parameters=reply_params)
            except Exception as e2:
                logger.error("Error sending Telegram message: %s", e2)
```

`split_message()`(`openharness.utils.helpers`)先按 `TELEGRAM_MAX_MESSAGE_LEN` 切块,每块先尝试把 Markdown 转成 Telegram 的 HTML 子集发送,HTML 解析失败就整体降级成纯文本重试——这是"平台专属渲染能力有限,发送必须容错"的典型处理方式。`_progress` 元数据配合 `draft_id`(对应 Telegram 消息 ID)还支持把中间进度更新成"消息草稿"而不是刷屏式地连续发多条新消息。

### Connect 型实现:Slack(Socket Mode)

`SlackChannel` 走的是 Slack 的 Socket Mode(基于 `slack_sdk`),`start()` 里既要建 `AsyncWebClient` 又要建 `SocketModeClient`,还要额外调一次 `auth_test()` 拿到 bot 自己的 user id 用于识别 @mention:

```python
# src/openharness/channels/impl/slack.py:33-60(节选)
async def start(self) -> None:
    ...
    self._web_client = AsyncWebClient(token=self.config.bot_token)
    self._socket_client = SocketModeClient(
        app_token=self.config.app_token,
        web_client=self._web_client,
    )
    self._socket_client.socket_mode_request_listeners.append(self._on_socket_request)

    try:
        auth = await self._web_client.auth_test()
        self._bot_user_id = auth.get("user_id")
        logger.info("Slack bot connected as %s", self._bot_user_id)
    except Exception as e:
        logger.warning("Slack auth_test failed: %s", e)
```

这里能看出一个规律:所有"connect 型" channel(Telegram、Slack、Discord、飞书、DingTalk、Matrix、Mochat、QQ)在 `start()` 里做的事情形状很像——建立连接、注册事件回调、解析出自身身份信息(用于判断"消息是不是在 @我"或过滤自己发的消息)——具体协议和 SDK 完全不同,但要交代给 `ChannelManager` 的"我已经在跑了"这件事是一样的。

### Poll 型实现:Email(IMAP 轮询 + SMTP,没有常驻连接)

`EmailChannel` 是十种实现里协议形态最不一样的一个——它没有长连接、没有 WebSocket、没有官方推送,`start()` 就是一个简单的轮询循环:

```python
# src/openharness/channels/impl/email.py:63-101(节选)
async def start(self) -> None:
    """Start polling IMAP for inbound emails."""
    if not self.config.consent_granted:
        logger.warning(
            "Email channel disabled: consent_granted is false. "
            "Set channels.email.consentGranted=true after explicit user permission."
        )
        return

    if not self._validate_config():
        return

    self._running = True
    poll_seconds = max(5, int(self.config.poll_interval_seconds))
    while self._running:
        try:
            inbound_items = await asyncio.to_thread(self._fetch_new_messages)
            for item in inbound_items:
                ...
                await self._handle_message(
                    sender_id=item["sender"],
                    chat_id=item["sender"],
                    content=item["content"],
                    metadata=item.get("metadata", {}),
                )
        except Exception as e:
            logger.error("Email polling error: %s", e)
        await asyncio.sleep(poll_seconds)
```

`send()` 则走 SMTP,细节上要处理 `to_addr`、主题、`In-Reply-To` 这些邮件协议特有的字段(此处不展开)。值得单独指出的是 `consent_granted` 这个配置项:邮箱账号涉及的隐私和滥用风险比一般 IM bot 更高(轮询意味着要拿到邮箱的完整读取权限),所以 Email channel 在 `start()` 最开头就做了一次显式同意检查,不满足直接拒绝启动,而不是像其他 channel 那样只检查 token/密钥是否配置。这是同一套 `BaseChannel` 接口下,某个具体实现为自己的风险场景加的额外一道门槛,基类完全不知道这道门槛的存在——接口只保证"实现了 start/stop/send",具体实现可以在 `start()` 内部加任意多的前置校验。

### bus/events.py + bus/queue.py:统一事件格式与解耦队列

无论哪种协议进来的消息,最终都要收敛成同一个 dataclass:

```python
# src/openharness/channels/bus/events.py:8-36
@dataclass
class InboundMessage:
    """Message received from a chat channel."""
    channel: str
    sender_id: str
    chat_id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    session_key_override: str | None = None

    @property
    def session_key(self) -> str:
        return self.session_key_override or f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""
    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

平台专属的信息(Telegram 的 `message_id` 用于回复引用、Slack/飞书的 thread 标识、群聊类型标记)全部塞进 `metadata` 这个开放字典里,不污染核心字段——这就是第二篇 `session_key_for_message()` 能同时处理 Telegram 话题群和 Slack 线程的原因:两个平台把各自的 thread 标识用不同的 key(`message_thread_id` vs `thread_ts`)塞进同一个 `metadata` 字典,路由逻辑按优先级依次尝试读取即可,不需要为每个平台写一个分支。

`MessageBus` 本身极简,就是一对 `asyncio.Queue`:

```python
# src/openharness/channels/bus/queue.py:8-34(节选)
class MessageBus:
    def __init__(self):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    async def publish_inbound(self, msg: InboundMessage) -> None:
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        return await self.outbound.get()
```

十个 channel 的 `start()` 循环各自往 `inbound` 队列里塞消息,`OhmoGatewayBridge`(第二篇)从 `inbound` 队列消费;`ChannelManager` 内部的 `_dispatch_outbound()` 循环从 `outbound` 队列取消息,按 `msg.channel` 找到对应的 channel 实例调用 `send()`。这一对队列就是解耦的全部机制——没有更复杂的中间件,足够用是因为 gateway 是单进程场景,不需要跨进程/跨机器的消息队列。

### ChannelManager:按需 import,失败不致命

```python
# src/openharness/channels/impl/manager.py:38-49(节选)
if self.config.channels.telegram.enabled:
    try:
        from openharness.channels.impl.telegram import TelegramChannel
        self.channels["telegram"] = TelegramChannel(
            self.config.channels.telegram, self.bus,
            groq_api_key=self.config.providers.groq.api_key,
        )
        logger.info("Telegram channel enabled")
    except ImportError as e:
        logger.warning("Telegram channel not available: %s", e)
```

十个平台各自的重量级 SDK(`python-telegram-bot`、`slack_sdk`、`lark-oapi`、`nio`、`botpy`……)不是全部作为核心依赖强制安装的,而是按需 import——只有配置里 `enabled=True` 的平台才会尝试 import 对应模块,导入失败(SDK 没装)只记一条 warning 并跳过,不会让整个 gateway 启动失败。这与本课程参考的 Hermes 网关平台注册表(通过一张显式注册表 + 延迟加载器解决同样的"不能为不需要的平台付出加载成本"问题)是同一类问题的更朴素解法:Hermes 用注册表 + `threading.Event` 做单次加载协调,这里直接用 `try/except ImportError` 加一个固定的 if/elif 序列——因为 `ohmo` 目前只有十个内置平台且不支持第三方插件平台注册,不需要 Hermes 那种支持运行时插件扩展的复杂度,一个平铺的初始化函数已经足够清晰。

### 十种平台一览

`ChannelManager._init_channels()` 里出现的十个平台,以及各自的接入技术:

| 平台 | 技术形态 |
|---|---|
| Telegram | `python-telegram-bot` 长轮询 |
| Slack | `slack_sdk` Socket Mode |
| Discord | Discord Gateway WebSocket(`websockets` 直连) |
| 飞书(Feishu/Lark) | `lark-oapi` SDK WebSocket 长连接 |
| DingTalk | Stream Mode(`httpx`) |
| Matrix | `nio`(matrix-nio)sync 循环 |
| WhatsApp | Node.js 桥接进程 |
| QQ | 官方 `botpy` SDK |
| Email | IMAP 轮询 + SMTP 发送 |
| Mochat | Socket.IO,带 HTTP 轮询兜底 |

这个覆盖面有一个值得点评的特点:相比常见的海外 IM 网关方案通常只覆盖 Telegram/Discord/Slack/WhatsApp 这几个国际主流平台,`ohmo`/OpenHarness 这套 channel 体系额外覆盖了国内使用广泛的飞书、钉钉、QQ——这对希望把个人助理接入国内工作流(飞书群、钉钉群机器人、QQ 私聊)的用户是直接可用的能力,不需要自己再写一层适配。

## 常见问题/易踩坑

- **`allow_from` 留空不是"暂不限制",而是"拒绝所有人"。** `BaseChannel.is_allowed()` 的默认策略是空列表直接拒绝并打一条 warning 日志——这是显式的默认拒绝(default-deny)安全设计,配置一个新 channel 后如果发现消息没有被处理,先检查是不是忘了填 `allow_from`(或者显式填 `["*"]` 表示对所有人开放,这个选择必须是明确的)。
- **不是所有 channel 都是"启动后一直连着"的。** Email 是轮询模型,`poll_interval_seconds` 决定了收到新邮件的延迟上限,不要预期它有 IM 平台那种近实时的响应速度。
- **新增一个 channel 出错时,不会让 gateway 整体崩溃。** `_start_channel()` 包了一层 try/except,单个平台连接失败只会记录在 `last_error` 里(供 `gateway status` 展示),其他平台照常运行。

## 小结

`BaseChannel` 用三个抽象方法(`start`/`stop`/`send`)加两个共享能力(权限检查、事件封装)把十种协议形态迥异的 IM 平台统一到同一套接口下;`InboundMessage`/`OutboundMessage` 这两个 dataclass 是整个 gateway 唯一认识的内部消息格式,平台专属信息全部装进开放的 `metadata` 字典;`MessageBus` 用一对 `asyncio.Queue` 完成了 channel 层和 Agent 运行时层的解耦;`ChannelManager` 用简单的 try/except 按需加载各平台 SDK。十种平台里飞书、钉钉、QQ 的覆盖,让这套体系在国内个人助理场景下有直接可用的接入面。下一篇我们转向 gateway 之外的另一条能力线——cron 调度与主动触发,看看 Agent 是怎么在用户不发消息的情况下,自己按计划或按需发起一次对话的。
