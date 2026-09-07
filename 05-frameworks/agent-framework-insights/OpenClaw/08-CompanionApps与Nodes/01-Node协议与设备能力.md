# Node协议与设备能力

> OpenClaw 的 Gateway 只有一个,但连到它身上的客户端有两种完全不同的身份。一种是"人通过它向 Gateway 下指令"——CLI、Web UI、macOS 菜单栏 App 的聊天窗口,它们都是`role`未声明为`node`的普通操作者客户端(operator client);另一种是"Gateway 反过来向它下指令,借助它去调用一台物理设备的本地能力"——手机的摄像头、笔记本的屏幕录制、腕表的 GPS,这些能力藏在一台台以`role: "node"`连接的伙伴设备(companion device)里。`docs/concepts/architecture.md`把这句话写在一行:"**Nodes** (macOS/iOS/Android/headless) also connect over **WebSocket**, but declare `role: node` with explicit caps/commands."本篇从这条协议边界出发,拆开`node.invoke`的命令契约,再重点展开`computer.act`这个"让 Agent 操作设备屏幕"的能力——它是 Node 体系里工程复杂度最高、也最能说明"能力型协议"设计哲学的一块。

## 学习目标

- 理解 Node 和普通操作者客户端在协议语义上的本质区别:谁向谁发起指令、谁暴露命令面、谁审批谁。
- 弄清`node.invoke`命令契约的两道门:节点声明(`connect.commands`)与网关策略(平台默认允许表 + `commands.allow`/`commands.deny`),以及"危险命令"额外需要的持久化 opt-in。
- 通读相机(`camera.*`)、屏幕录制(`screen.record`)、地理位置(`location.get`)三组具体命令的调用契约、默认权限状态与错误码设计。
- 深入理解`computer.act`：能力发现(capability-based)、坐标系统一(reference frame)、Provider 切换的"不回退"语义,以及它和`screen.snapshot`共享同一份读路径的原因。
- 理解 Node 的"外围设备"定位——它不跑 Gateway 服务,也不承接消息通道流量。

## 背景与设计动机

一个直觉的反问是:既然 Gateway 已经通过 WebSocket 接受各种客户端连接,为什么还要单独定义一种"Node"角色,而不是让操作者客户端顺便暴露一些设备能力?

答案在于指令方向完全相反。操作者客户端(CLI、Web UI、聊天窗口)是"人→Gateway"的入口:用户发一条消息,Gateway 调度 Agent 处理,再把结果回传给这个客户端展示。这条链路里,客户端是被动的展示层,主动权在人手里。Node 反过来:Agent 在处理一个任务时,可能需要"看一眼当前屏幕在显示什么"或者"拍一张照片核实包裹送到了没有",这时候 Gateway 要主动向一台已连接的设备发起`node.invoke`调用,设备执行完再把结果(一张 JPEG、一段 mp4、一组经纬度)回传给 Gateway,继续喂给 Agent。这条链路里,人可能完全不在场——是 Agent 在驱动设备,不是设备在驱动 Agent。

这个方向差异决定了协议必须把"设备能不能被随意调用"当作一等公民设计,而不是像操作者客户端那样只关心"这个人有没有权限看这条消息"。`docs/nodes/index.md`把这句话说得很直白:

> Nodes are **peripherals**, not gateways: they don't run the gateway service, and channel messages (Telegram, WhatsApp, etc.) land on the gateway, not on nodes.

"peripherals"这个词选得精确——Node 就是外围设备,它不跑消息通道的业务逻辑,也不维护会话状态,它唯一的职责是"声明自己能做什么,然后老老实实执行 Gateway 转发过来的调用"。同一份`docs/concepts/architecture.md`用一句话概括了这条能力清单:

> Expose commands like `camera.*`, `screen.record`, and `location.get`; the macOS app also exposes widget-panel commands under `canvas.*`.

值得注意的是 macOS 是一个双重身份的特例——它既可以是"人在这台 Mac 上使用聊天窗口"的操作者客户端,也可以是"这台 Mac 作为 Node 暴露摄像头/屏幕/computer-control"的外围设备,两种身份共享同一条 WebSocket 连接和同一份运行时。这一点在第二篇会展开;本篇先把 Node 协议本身的契约讲清楚。

## 核心机制详解

### 设备身份与配对:先证明"我是谁",再谈"我能做什么"

Node 连接 Gateway 时,和操作者客户端一样要走**设备配对**(device pairing),但审批的对象不同。`docs/nodes/index.md`描述了这套双层模型:

> A node presents a signed device identity during connect; the Gateway creates a device pairing request for `role: node`. Approve via the devices CLI (or UI).

第一层是"这台设备能不能连上 Gateway"——设备携带一个签名过的身份密钥对,Gateway 验证签名后建立配对记录,这一层解决的是身份信任问题。第二层是"这台设备连上之后,能调用哪些具体命令"——这是`node.pair.*`管理的、附着在同一条设备配对记录上的**命令/能力面**(command surface)。文档强调这两层不能混为一谈:

> Approval scope follows the pending request's declared commands:
> - commandless request: `operator.pairing`
> - non-exec node commands: `operator.pairing` + `operator.write`
> - `system.run` / `system.run.prepare` / `system.which`: `operator.pairing` + `operator.admin`

也就是说,一个只想连上 Gateway、不声明任何命令的设备,审批门槛最低;想执行`camera.snap`这类非 exec 命令,需要多一层`operator.write`;想跑`system.run`这种能在设备上执行任意 shell 命令的高危能力,需要`operator.admin`。这是一种按"能造成多大破坏"分级的审批模型,而不是一刀切的"配对完就能为所欲为"。

### 命令契约的两道门:节点声明 + 网关策略

一条`node.invoke`命令要真正被执行,必须同时通过两道独立的门。`docs/nodes/computer-use.md`附带的 index 文档把这条规则写得很清楚:

> Node commands must pass two gates before they can be invoked:
> 1. The node must declare the command in its authenticated connect metadata (`connect.commands`).
> 2. The gateway's platform-and-approval-derived allowlist must include the declared command.

第一道门是**节点自己愿不愿意暴露这个命令**——比如 iOS 的相机开关关闭时,`camera.*`根本不会出现在这台设备连接时声明的命令列表里,Gateway 层面即便配置允许也无从下手。第二道门是**网关策略是否放行这个命令名**——每个平台都有一张默认允许表,例如 macOS 默认允许`camera.list`、`location.get`、`device.info`、`computer.act`等,但不包括真正拍照/拍视频的`camera.snap`/`camera.clip`。这两道门叠加之外,还有第三类"危险命令"需要运维显式做一次性的持久化 opt-in:

```json5
{
  gateway: {
    nodes: {
      commands: { allow: ["camera.snap", "desktop.stream", "screen.record"] },
      deny: ["camera.clip"],
    },
  },
}
```

文档列出的危险命令清单包括`camera.snap`、`camera.clip`、`camera.ptz.control`、`desktop.stream`、`screen.record`、`contacts.add`、`calendar.add`、`reminders.add`、`health.summary`、`sms.send`、`sms.search`——这些命令即便节点声明了、平台默认表也没写进去,运维必须手动把它们加进`gateway.nodes.commands.allow`才能生效,而`commands.deny`永远优先于任何允许项。这种设计的取舍很直白:读取型、低风险的命令(`camera.list`、`device.info`)可以随平台默认放行,但一旦涉及"真的拍下一段影像"或"真的发一条短信",框架拒绝替运维做默认判断。

### 相机、屏幕、地理位置:三组具体命令的调用契约

以相机为例,`docs/nodes/camera.md`定义了`camera.list`/`camera.snap`/`camera.clip`三个命令,每个平台的实现细节都不同但契约形状一致。iOS 的`camera.snap`参数示例:

```
- `camera.snap`
  - Params:
    - `facing`: `front|back` (default: `front`)
    - `maxWidth`: number (optional; default `1600`)
    - `quality`: `0..1` (optional; default `0.9`, clamped to `[0.05, 1.0]`)
    - `delayMs`: number (optional; default `0`, internally capped at `10000`)
  - Response payload: `format: "jpg"`, `base64`, `width`, `height`.
  - Payload guard: photos are recompressed to keep the base64-encoded payload under 5MB.
```

注意这里的"payload guard"——不管前端请求什么分辨率,响应体在协议层面被强制压回 5MB 以内的 base64,这是为了不让一张照片撑爆 WebSocket 帧或者拖慢整条`node.invoke`往返。iOS 和 Android 还共享一条更严格的运行时限制:

> The iOS node only allows `camera.*` commands in the **foreground**. Background invocations return `NODE_BACKGROUND_UNAVAILABLE`.

这条限制不是任意的工程妥协,而是移动操作系统权限模型的直接映射——iOS/Android 都不允许后台进程随意打开摄像头,Node 只能在这个操作系统边界内如实反映限制,不能绕过。相比之下 macOS 的实现走了更远,不仅能拍照,还能对支持 UVC 协议的 USB 摄像头做物理云台控制(`camera.ptz.control`):

> Physical PTZ is implemented by the Mac app for USB cameras that expose standard UVC absolute pan/tilt or zoom controls. It uses the same **Allow Camera** setting as capture. ... Always pass an explicit `deviceId` returned by `camera.list`. OpenClaw never chooses a default camera for physical movement.

"never chooses a default camera for physical movement"这句话值得停下来读——读取型操作(比如`camera.snap`不传`deviceId`)可以让框架挑一个默认摄像头,但会真正移动硬件的操作,框架拒绝做任何隐式选择,必须调用方明确传入摄像头 ID。这是"能力越危险,隐式行为越少"这条设计原则的又一处体现。

地理位置命令`location.get`的设计则围绕"操作系统权限本身就是分级的"这个前提展开。`docs/nodes/location-command.md`解释了为什么不是一个简单的开关:

> OS location permissions are multi-level. Precise location is a separate OS grant too (iOS 14+ "Precise", Android "fine" vs "coarse"). The in-app selector drives the requested mode, but the OS still decides the actual grant.

请求参数里的`desiredAccuracy: "coarse|balanced|precise"`只是"请求"的意愿,真正拿到的精度由操作系统的授权状态决定;如果 OS 拒绝了请求的级别,应用会退回到"当前实际被授予的最高级别"并把状态如实展示给用户,而不是假装拿到了请求的精度。错误码同样体现了"能解释清楚失败原因"这一设计取向——`LOCATION_DISABLED`(选择器本身关着)、`LOCATION_PERMISSION_REQUIRED`(权限没给到位)、`LOCATION_BACKGROUND_UNAVAILABLE`(应用在后台但只有"使用时"权限)、`LOCATION_TIMEOUT`、`LOCATION_UNAVAILABLE`,五种失败各自对应一种可操作的修复路径,而不是笼统的一个"失败"。

屏幕录制(`screen.record`)在 macOS 上依赖 TCC 的 Screen Recording 权限,和相机、位置一样走相同的"节点声明 + 网关策略"两道门,这里不再重复展开;三者共同的模式是:**读取型能力(list/status)默认宽松,采集型能力(snap/clip/record)默认收紧甚至需要额外 opt-in,物理操作型能力(PTZ)彻底拒绝隐式默认值**。

### `computer.act`:让 Agent 操作屏幕的能力型协议设计

如果说相机、位置这些命令是"调用一次、返回一份数据"的简单契约,`computer.act`则是 Node 体系里工程复杂度最高的一块——它要让一个具备视觉能力的模型,通过截图看清屏幕,再用鼠标键盘操作它。`docs/nodes/computer-use.md`开篇就定义了这是一种**能力型**(capability-based)协议,而不是"固定命令集":

> Eligibility is capability-based: the connected node must advertise both `computer.act` and `screen.snapshot`. The node's descriptor identifies the supported v2 action, target, observation, and delivery families, so the built-in `computer` tool exposes only what that provider can faithfully execute.

这句话的关键在"exposes only what that provider can faithfully execute"——不同 Provider(macOS 上的 Peekaboo 或 CUA、Windows/Linux 上的`cua-computer`插件)能做到的动作集合不同,协议不假装它们功能等价,而是让每个 Provider 的描述符(descriptor)如实声明自己支持哪些动作族,工具层再据此裁剪暴露给模型的能力清单。比如支持"窗口/元素族"的 Provider 可以多暴露`list_windows`、`get_accessibility_tree`、`launch_app`,不支持的 Provider 就没有这些动作,而不是让所有 Provider 都假装支持然后在运行时报错。

坐标系统一是这个协议另一处值得细读的设计。模型看到的是一张截图,发出的是"点击某个像素坐标"这样的指令,但不同 Provider 对坐标系的理解不同:

> Window input coordinates follow the observation's `details.coordinateSpace`. CUA reports `image-pixels`: use pixels in the delivered image, including when OpenClaw resized it. Peekaboo reports `global-logical-points`: use desktop logical points.

协议没有强行统一坐标系,而是要求每次截图返回一个`displayFrameId`,后续的坐标动作必须回传这个 ID 来证明"我这次点击引用的就是最近一次看到的这张截图",一旦显示器重连或几何发生变化,`frameId`就会失效,动作直接拒绝而不是"悄悄地对着错误的画面点击"：

> OpenClaw also carries a node-issued display identity from the screenshot into the action, so a display reconnect or geometry change fails closed instead of silently retargeting the same index.

Provider 切换的"不回退"语义同样体现了这个协议对可靠性的偏执:

> Provider selection never falls back per action. Switching providers closes the active execution surface, rotates the provider generation, and re-advertises the node commands. A CUA failure therefore becomes an unavailable result instead of silently running the same action through Peekaboo.

如果不这样设计,一次"看似正常"的降级(CUA 失败,静默换成 Peekaboo 跑同一个动作)可能会因为两个 Provider 对同一坐标系的理解不同而执行出完全不同的物理动作——这在"点击鼠标、输入文字"这类会产生真实副作用的操作上是不可接受的风险,所以协议宁可让失败清晰可见,也不做隐式兜底。

信任模型上,`computer.act`把 Gateway 定义为唯一的授权关卡,驱动进程本身被形容为"哑执行器":

> The Gateway is the authorization chokepoint; the driver is a dumb effector. OpenClaw deliberately leaves the daemon unceilinged and authorizes computer use above it through tool exposure, the dangerous-command allowlist, device and command pairing approval, node-local provider enablement, and OS permissions.

这意味着授权判断完全在协议栈的上层——工具是否暴露给这个 Agent、命令是否在允许表里、设备配对是否批准了这次命令升级、节点本地开关是否打开、操作系统权限是否授予——五层校验全部通过之后,`computer.act`本身不再额外做"这一次点击允不允许"的动态确认。这是一个和相机/位置命令完全一致的设计哲学的延伸:静态的、可审计的层层校验,而不是运行时的临时决策。

### 复用`screen.snapshot`:读路径只有一条

一个容易被忽略但很能说明协议一致性的细节是:`computer.act`并没有单独发明一条"给我看屏幕"的读命令,而是直接复用相机/屏幕录制共享的`screen.snapshot`:

> Reads reuse `screen.snapshot`; there is no second capture path. See [Camera and screen nodes](/nodes/camera) for the shared capture command.

这意味着截图这件事在整个 Node 协议里只有一条实现路径,不管是给模型提供视觉上下文,还是作为`computer.act`坐标动作的前置观测,走的都是同一份采集逻辑、同一套权限校验、同一套 payload 限制。这类"同一个能力只暴露一条路径"的克制,是 Node 命令面能保持可审计的重要原因——审计一次`screen.snapshot`的权限边界,就等于审计了所有依赖它的上层功能。

### 权限自描述:`permissions`映射让 Agent 少猜一步

Node 协议还留了一个很小但很实用的自描述接口——`node.list`/`node.describe`返回结果里可以携带一个`permissions`映射,用权限名到布尔值的键值对,如实报告这台设备当前的操作系统授权状态。`docs/nodes/index.md`定义了它的形状:

> Nodes may include a `permissions` map in `node.list` / `node.describe`, keyed by permission name (e.g. `screenRecording`, `accessibility`, `location`) with boolean values (`true` = granted).

这个字段解决的是一个很具体的体验问题:如果 Agent 每次调用`camera.snap`都要先实际发起一次调用、等失败了才知道"原来这台设备没开相机权限",那么每一次权限缺失都要多付出一次无谓的往返。有了这份自描述,Agent 或者上层工具可以先读一次`node.describe`,在决定要不要发起某个命令之前就了解这台设备的权限现状,把"先探测再决策"变成可能——这也是本篇反复强调的"能力型协议"精神的又一处体现:协议不仅要定义"能调用什么",还要定义"调用之前能查到什么"。

不是所有平台都会填充这份映射——iOS/Android 可能省略它,macOS 节点会稳定上报`location`等字段。这种"可选但一旦提供就要可信"的设计,和`computer.act`里"Provider 描述符是权威来源,不支持的动作就不出现"是同一种克制:宁可留空,也不提供一份不可靠的猜测值。

## 常见问题/易踩坑

- **把"节点声明了命令"等同于"这个命令能被调用"**：两道门任何一道没过都会失败。node 本地开关关闭(比如 macOS 的`Allow Computer Control`未开启)会导致节点根本不声明该命令;网关策略缺失或`commands.deny`命中会导致声明了也调不通。排查顺序应该是先看`openclaw nodes describe`确认节点声明了目标命令,再核对`gateway.nodes.commands.allow/deny`。
- **对危险命令做"能力开了就万事俱备"的假设**：`camera.snap`这类命令即便设备侧权限开启、节点也声明了,网关侧不显式`commands.allow`依然拒绝执行——这是刻意的双重确认,不是 bug。
- **在坐标动作里复用过期的`frameId`**：屏幕内容可能在两次截图之间发生变化,协议不保证`frameId`是"新鲜度"担保,只保证"这个坐标引用的是哪一帧、哪个显示器";每次可能改变画面的操作之后都应该重新截图,而不是复用旧的引用坐标连续操作。

## 小结

Node 协议的核心是一条清晰的方向切分:操作者客户端服务"人向 Gateway 发指令",Node 服务"Gateway 向设备发指令、调用本地能力"。这条切分之上叠加了两道命令门(节点声明 + 网关策略)和一层危险命令的持久化 opt-in,构成了从"读取型能力默认宽松"到"采集/控制型能力默认收紧"的分级授权模型。相机、屏幕、位置这几组具体命令用参数裁剪、payload guard、分级错误码把这个模型落到实处;而`computer.act`把这套哲学推到了极致——能力发现驱动工具暴露、坐标系统一到帧级别、Provider 切换宁可失败也不隐式回退、读路径只留一条可审计的通道。下一篇会转向 Node 的载体本身:macOS/iOS/Android/Linux 四个原生 App 各自在整体架构里扮演什么角色,以及 macOS App 身兼"操作者客户端"与"Node"双重身份时,工程上是如何被约束住的。
