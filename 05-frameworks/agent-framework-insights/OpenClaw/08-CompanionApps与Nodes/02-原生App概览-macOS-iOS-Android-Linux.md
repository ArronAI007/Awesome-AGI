# 原生App概览:macOS / iOS / Android / Linux

> 上一篇讲清楚了 Node 协议本身的契约:谁能调用什么命令、两道门怎么把关、`computer.act`如何用能力发现取代固定命令集。本篇把镜头拉远,看这份协议实际跑在谁身上——四个原生 App 各自在 OpenClaw 整体架构里扮演什么角色。一个容易搞错的直觉是"App 就是 Node 的客户端实现",但至少 macOS App 同时身兼两种角色:它既是`role: node`的外围设备,又是操作者用来跟 Agent 聊天的普通客户端。这种双重身份不是偶然的——它带来了一整套"谁拥有什么状态、谁不能碰什么资源"的工程约束,本篇逐个平台拆开看。

## 学习目标

- 理解 macOS App 的双重身份:同一条 WebSocket 连接上,它既是操作者客户端,又是`role: node`的外围设备,两者共用一个运行时。
- 弄清 iOS、Android 作为"纯 Node"角色(移动端不跑 Gateway)和 macOS/Linux 作为"可选 Node 宿主"之间的差异。
- 读懂`apps/macos/AGENTS.md`、`apps/ios/AGENTS.md`、`apps/android/AGENTS.md`里体现出的工程约束,理解它们分别在防什么问题。
- 理解 macOS 代码签名和 TCC 权限绑定的关系——为什么"稳定、正确签名的 App"是拿到真实设备权限的前提条件,而不只是分发上的讲究。
- 理解 Linux 的定位差异:它是 Gateway 的一等公民运行时,companion App 反而是后起的、能力更受限的一环。

## 背景与设计动机

如果一个团队要给四个不同操作系统各写一个原生 App,最容易掉进的坑是"让每个 App 自己攒一套业务逻辑"——于是 macOS App 里判断"要不要显示这条设置"和 iOS App 里判断同一件事的代码逻辑各写一遍,时间久了就会分叉出四套不一致的行为。`docs/platforms/macos.md`把这条边界画得很清楚:

> Native code owns device-local capabilities and the Connection window; the Dashboard owns all settings UI.

翻译过来就是:原生 Swift/Kotlin 代码只负责"这台设备本地能做什么、需要哪些系统权限",几乎所有的配置项、业务规则统一收敛到 Gateway 提供的 Web Dashboard 里渲染,原生 App 只是把 Dashboard 嵌进一个原生外壳,再通过一层桥接把"设备本地才能做的事"(比如弹出 macOS 权限授权对话框)暴露给它。`apps/macos/AGENTS.md`把这条边界写成了一条明确禁止的规则:

> Dashboard owns all settings UI. Reject new Gateway-data or app-settings UI in Swift.

这不是风格偏好,而是防止逻辑分裂的架构决策——一旦允许"这个设置在 Swift 里再实现一遍",四个平台就会在同一份配置语义上产生行为差异,而且这种差异往往要等到用户报告"为什么 Mac 上这样、手机上那样"才会被发现。

## 核心机制详解

### macOS:唯一同时持有"客户端"和"Node"两种身份的平台

macOS App 是四个原生 App 里唯一一个同时扮演操作者客户端和 Node 的存在。`docs/platforms/macos.md`是这样描述它的:

> The macOS app is the OpenClaw **menu bar companion**: native tray UI, macOS permission prompts, notifications, WebChat, voice input, a hosted-widget panel, and Mac-hosted node tools such as `system.run`.

"WebChat"和"voice input"是操作者客户端的职责——用户在这台 Mac 上跟 Agent 聊天;"Mac-hosted node tools such as `system.run`"则是 Node 的职责——Gateway 可以把这台 Mac 当作一台外围设备,调用它的相机、屏幕、以及本篇会详细展开的`system.run`远程执行能力。这两种职责跑在同一个进程、同一条 WebSocket 连接之上,`docs/nodes/index.md`用一段话讲清楚了这个合并是如何工程化的:

> macOS can also run in **node mode**: the menu bar app connects to the Gateway's WS server as one node (so `openclaw nodes …` works against this Mac). The app adds native widget-panel, camera, screen, notification, and computer-control commands to the same node-host command surface used by `openclaw node run`. Do not start a second CLI node on that Mac; the app runs the matching CLI node-host runtime as an internal worker and remains the sole Gateway connection and node identity.

这里有一条明确的**单一身份约束**:同一台 Mac 不能同时跑"App 内置的 Node 身份"和"独立启动的 CLI `openclaw node run`"——App 内部会启动一个匹配的 CLI node-host 运行时作为内部 worker,始终保持"这台 Mac 只有一个 Node 身份"的不变式。如果放任两条 Node 连接同时存在,Gateway 侧的设备配对记录、命令声明、审批状态都会出现重复或冲突,这是一个典型的"看似能省事、实际上会制造脏状态"的陷阱,所以协议层面直接把它设计成不允许发生。

`docs/platforms/macos.md`还列出了这台 Mac 节点具体合并了哪些能力:

> One Mac node that combines the native widget panel, camera/screen capture, notifications, location, and computer control with the CLI node host's system, browser, plugin, skill, and MCP commands.

也就是说 macOS 的 Node 身份不只是"能拍照、能截屏"这么简单,它还继承了 CLI node host 那一整套系统能力——远程执行 shell 命令(`system.run`)、代理浏览器操作(`browser.proxy`)、暴露插件与 MCP 服务器。这也是为什么 macOS 平台默认命令表里`system.run`/`system.which`不像`camera.list`那样直接出现在静态默认表里,而是要求"通过一次声明了这些命令的配对请求获得批准,之后才在这台设备的已批准命令集里持久存在"——高权限能力走的是配对升级流程,而不是静态默认值。

`apps/macos/AGENTS.md`里还有一条容易被忽略但很重要的约束,直接呼应了"Node 是外围设备,不应该绕过 Gateway 的配置权威"这个原则:

> Bridge mutations use existing native owners; never write `openclaw.json`.

原生代码可以读取、可以调用现有的设备本地设置接口去改变本地状态,但绝不允许直接写这份 Gateway 配置文件——这条线划得很清楚:配置的权威来源永远是 Gateway,原生 App 只是通过桥接层去调用 Gateway 已经定义好的读写路径,不能自己开一条后门去改配置文件。

### iOS 和 Android:纯粹的移动 Node,受操作系统前台/后台模型硬约束

和 macOS 不同,iOS、Android 不跑 Gateway 服务,它们是纯粹的移动端 Node——`docs/platforms/android.md`的"Support snapshot"一节把这一点写得很直白:

> Role: companion node app (Android does not host the Gateway).
> Gateway required: yes (run it on macOS, Linux, or Windows via WSL2).

这两条平台的工程约束主要围绕移动操作系统的电源和权限模型展开,而不是像 macOS 那样操心"如何合并两种身份"。一个具体的例子是"多 Gateway 会话"场景下的设备能力归属问题——一台 iPhone 可以同时连接多个 Gateway 用于聊天,但只能有一个 Gateway 拥有它的设备能力:

> Only the focused gateway receives the iPhone's capability-bearing node session, so camera, screen, location, and other device commands always have one unambiguous owner.

这条设计避免了一个真实的冲突场景:如果两个 Gateway 同时能调用同一台手机的摄像头,那么"谁在什么时候拍了什么"会变得无法追溯,甚至可能出现两个 Agent 同时抢占同一个摄像头资源的竞态。协议选择了最简单的解法——把设备能力绑定到"当前聚焦的那一个 Gateway"上,非聚焦的 Gateway 只能保留普通聊天连接,不拿到 Node 身份。

`apps/ios/AGENTS.md`和`apps/android/AGENTS.md`里的内容和 macOS 那份形成了鲜明对比——它们几乎不谈"设备能力应该如何暴露给 Gateway"这类架构问题,而是大量聚焦在应用商店发布流程的护栏上:

> Agent-driven App Store uploads must use only `pnpm ios:release:upload`. ... If `pnpm ios:release:upload` exits non-zero, stop immediately and report the failing step. ... Do not submit an iOS App Store version for App Review.

> Agent-driven Google Play uploads must use only `pnpm android:release:upload`. ... Do not promote an Android release to production. Production promotion stays manual in Google Play Console.

这类规则的用意很直接:苹果和 Google 的应用商店发布是不可逆或者代价高昂的操作(一旦提交 App Review 或者推production,回滚成本远高于一次构建失败),所以这两份 AGENTS.md 把"发布链路"设计成一条只能往前走、失败就停、绝不允许自动切到"备用发布路径"的单行道——`pnpm ios:release:archive`被明确标注为"仅用于本地归档验证,不是发布失败后的兜底路径"。这和第一篇里`computer.act`"Provider 切换绝不隐式回退"的哲学是同一种工程直觉:高风险、难以撤销的操作,宁可显式失败,也不要自动切换到另一条看起来能凑合用的路径。

移动端还有一处细节值得注意:文档反复强调`camera.*`、`screen.*`在 iOS/Android 上是**前台专属**的——

> `camera.*` and `screen.*` are foreground-only on iOS/Android nodes.

这不是 OpenClaw 自己加的限制,而是移动操作系统本身的电源和隐私管理策略——后台进程被系统限制访问摄像头和屏幕,OpenClaw 的 Node 实现只能如实反映这层操作系统边界,任何试图绕过它的设计都注定行不通。这也解释了为什么 Node 协议要专门定义一个`NODE_BACKGROUND_UNAVAILABLE`错误码,而不是让调用方猜测"是不是权限没给"。

### Apple Watch:一个不走常规 WebSocket 的例外

iOS 平台内部还藏着一个足够特殊、值得单独提一句的例外——独立配对的 Apple Watch 节点。前两篇讲的 Node 协议默认走 Gateway 的操作者端口 WebSocket,但`docs/nodes/index.md`说明了 Watch 为什么走了一条不同的传输:

> Most nodes use the Gateway WebSocket on the operator port. The optional direct Apple Watch node uses signed HTTPS polling on that same port because watchOS blocks generic low-level networking for ordinary apps.

watchOS 出于电池和系统资源管理的考虑,不允许普通 App 使用通用的底层网络套接字,这不是 OpenClaw 能绕过的限制,协议只能顺应它——改用签名过的 HTTPS 轮询来实现和 Gateway 的双向通信。这个例外再次印证了本篇反复强调的原则:每个平台的 Node 实现都要如实反映该操作系统本身划定的边界,不去追求一套所有平台都必须一模一样的传输层实现。配对流程上,Watch 也走了一条更轻量的路径——一个由管理员签发的、短期有效的"仅限 Node、命令面固定且低风险"的设置码,而不是走普通设备配对的完整审批流程;但只要后续需要扩展到更大的命令面,依然要回到正常的审批轨道,不会因为最初走了简化通道就获得额外豁免。

### Linux:Gateway 的一等公民,Companion App 反而是后来者

Linux 平台呈现出和 macOS/iOS/Android 都不同的格局——Gateway 本身在 Linux 上是完全一等公民的运行时,而带 UI 的 companion App 反而是相对晚近、能力覆盖也更有限的补充。`docs/platforms/linux.md`开篇就定了调:

> The Gateway is fully supported on Linux. Node is the primary, default, and recommended runtime.

Linux 的 companion App 是一个基于 Tauri 的桌面应用,定位是"引导新用户完成 Gateway 安装和连接",它本身也可以承担 Node 角色,但走的是一条独立的插件路径——`linux-node`插件,而不是像 macOS App 那样把 Node 能力内建进原生代码:

> The bundled Linux Node plugin gives the CLI `openclaw node` service device capabilities without requiring the desktop app.

这意味着 Linux 上"跑 Node"和"跑桌面 App"是两条可以独立存在的路径:一台无头的 Linux 服务器完全可以只装 CLI、启用`linux-node`插件,拿到相机、地理位置、系统通知这几项能力,根本不需要 Tauri 桌面壳。文档给出的能力表也印证了 Linux Node 的能力集合明显比 macOS/iOS/Android 更克制:

| Capability | Default | Requirement |
| --- | --- | --- |
| Desktop notifications (`system.notify`) | On | `notify-send` + 桌面通知会话 |
| Camera photos and clips (`camera.*`) | Off | FFmpeg、V4L2、PulseAudio/PipeWire |
| Location (`location.get`) | Off | GeoClue2 + `where-am-i` |

值得一提的是 Linux 的相机实现选择了一条务实的路径——不像 macOS/iOS/Android 那样有原生系统 API 可用,而是直接调用 FFmpeg 探测`/dev/video*`设备,用`libx264`编码 MP4,这在第一篇提到的"每个平台如实反映自己的能力边界"这条原则下是完全合理的:与其在没有对应系统框架的平台上硬凑一套自研采集栈,不如复用已经被广泛验证的命令行工具链。

Linux 还有一个和内存管理相关、其他平台没有的独特工程约束,值得单独一提——因为它体现了"Gateway 进程的可用性优先级高于普通子进程"这条服务器场景特有的设计取向:

> The Gateway is a poor victim because it owns long-lived sessions and channel connections, so OpenClaw biases transient child processes to be killed first when possible.

具体做法是给可能被 OOM Killer 选中的子进程(受管进程、PTY shell、MCP stdio 服务器等)包一层 shell,在真正执行目标命令之前先尝试把自己的`oom_score_adj`提到`1000`,这是一个进程对自己的分数做的无需特权的自我调节——本质上是告诉内核"如果内存真的不够了,请优先杀我,而不是杀 Gateway 主进程"。这是一处非常"服务器工程"的细节,在移动端和桌面端语境下都不会出现,因为只有长期驻留、承载多个消息通道连接的 Linux Gateway 才会面临"OOM Killer 该杀谁"这个问题。

### macOS 代码签名:TCC 权限和签名身份深度绑定

第二篇任务里特别提到的一条规则,是`docs/platforms/mac/signing.md`里"Mac 权限证明需要一个稳定、正确签名的 App"这句话背后的机制。这不是一条分发流程上的讲究,而是 macOS 操作系统权限模型本身的硬约束:

> TCC permissions are tied to the bundle ID and code signature; keeping both stable (and the app at a fixed path) across rebuilds keeps macOS from forgetting TCC grants (notifications, accessibility, screen recording, mic, speech).

macOS 的 TCC(Transparency, Consent, and Control)权限系统把"用户曾经批准过这个 App 访问麦克风/摄像头/屏幕录制"这份记录,绑定在这个 App 的 Bundle ID 加代码签名身份上——不是绑定在"这个可执行文件的内容"上。这意味着如果每次重新构建都换一个签名身份(比如用临时的 ad-hoc 签名),即便功能代码完全没变,macOS 也会认为"这是一个新的 App",之前授予的所有权限记录全部作废,用户必须重新走一遍系统权限弹窗。文档对 ad-hoc 签名的后果说得很直接:

> Ad-hoc signing (`SIGN_IDENTITY="-"`) is explicit opt-in and does not persist TCC permissions across rebuilds.

这条规则解释了为什么开发环境和生产环境对签名要求截然不同的严格程度——生产发布必须使用稳定的 Developer ID Application 证书,因为终端用户不可能接受"每次自动更新之后,摄像头和麦克风权限又要重新申请一遍"这种体验;而本地调试可以用 ad-hoc 签名图快,代价就是接受权限记不住这个已知限制。签名脚本还做了一层深入到二进制格式层面的校验:

> Some Apple toolchains return success while signing raw fat64 as generic data, without native entitlements; that result is rejected. The signer does not thin or convert input containers.

这条校验背后的逻辑是:一个"看起来签名成功"的构建产物,如果签名工具实际上只是把整个二进制当作不透明数据块签了一遍壳、没有正确处理里面每个架构切片的原生 entitlements,那么这个 App 在运行时可能拿不到它声明需要的权限——而这种失败往往要等到用户已经安装、点了半天授权弹窗却始终拿不到摄像头权限时才会暴露。签名脚本选择在打包阶段就做严格校验、直接拒绝这类"形式正确但实质有问题"的签名结果,而不是把这个坑留给运行时。

签名脚本还额外做了 Team ID 一致性审计,默认要求应用内每一个原生组件的签名团队 ID 都彼此一致,只有在明确知道原因(比如引入了第三方 Sparkle 更新框架、其 Team ID 天然不同)的开发场景下才允许通过`SKIP_TEAM_ID_CHECK`跳过这一项检查——生产签名流程默认不提供这个逃生舱口的隐式启用路径,必须显式设置环境变量才能放行,这同样是"高风险默认拒绝、显式选择才放行"这条原则的又一次出现。

这条约束和第一篇讲的 Node 权限模型形成了一个完整的闭环:Node 协议本身定义了"哪些命令需要什么权限",但这些权限能不能真正被这台 Mac 上的 OpenClaw App 拿到,最终取决于操作系统层面的 TCC 授权记录是否稳定——而 TCC 记录能不能稳定,又取决于这个 App 的代码签名身份是否在每次升级之间保持一致。签名工程和 Node 能力模型看似是两个不同层面的问题,实际上是同一条权限链路的两端。

## 常见问题/易踩坑

- **在同一台 Mac 上同时启动 App 内置 Node 和独立的`openclaw node run`**：会造成两个 Node 身份互相干扰,文档明确禁止这样做——App 已经在内部跑了匹配的 CLI node-host worker。
- **假设"移动端后台仍能拍照/截屏"**：iOS/Android 的`camera.*`/`screen.*`是前台专属,这是操作系统硬限制,不是 OpenClaw 可以放宽的软限制。
- **用 ad-hoc 签名分发正式版 macOS App**：功能可能完全正常,但每次重新构建都会让终端用户的 TCC 授权失效,导致"升级后摄像头权限突然消失"这类用户报告——根源在签名身份不稳定,不在权限逻辑本身。
- **把 Linux 的桌面 companion App 当作 Node 能力的唯一入口**：Linux 上 Node 能力由独立的`linux-node`插件提供,无头服务器完全可以只跑 CLI + 插件,不需要 Tauri 桌面壳。
- **以为 Apple Watch 节点和 iPhone 节点走的是同一套传输协议**：Watch 因为 watchOS 本身禁止普通 App 使用通用底层网络套接字,走的是签名 HTTPS 轮询,不是常规 WebSocket——这是操作系统限制决定的,不是协议实现上的疏漏。

## 小结

四个原生 App 在 OpenClaw 整体架构里扮演的角色并不对称:macOS 是唯一同时持有"操作者客户端"和"Node"两种身份的平台,靠"原生只管设备本地能力、Dashboard 统一管配置"这条边界把复杂度收敛住;iOS、Android 是纯粹的移动 Node,工程约束主要来自移动操作系统的前台/后台权限模型和应用商店的不可逆发布流程;Linux 则是 Gateway 的一等公民运行时,companion App 和 Node 能力反而是两条独立、可选的补充路径。串起这一切的是 macOS 代码签名和 TCC 权限的绑定关系——这条链路说明"Node 能调用什么命令"这个协议层面的问题,最终要靠操作系统权限系统的信任落地,而信任的锚点就是那份稳定、正确签过名的 App 身份。下一篇转向语音与实时能力——Talk 模式的语音唤醒、实时对话、文本转语音这几块如何组织,以及会议机器人怎样把这套语音栈接进 Zoom、Google Meet 这类第三方会议软件。
