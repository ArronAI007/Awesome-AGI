# 语音与实时能力:Talk / TTS / 会议机器人

> 前两篇分别讲了 Node 协议的命令契约和四个原生 App 各自的角色分工。本篇聚焦一类横跨这两者的能力——语音。语音唤醒(Voice Wake)、连续语音对话(Talk)、文本转语音(TTS)这三块共同构成了 OpenClaw 的"耳朵和嘴巴",而会议机器人(meeting-bot)则是把这套语音栈接入 Zoom、Google Meet、Microsoft Teams 这类第三方视频会议软件的一层适配。源码层面,`src/talk/`(约 80 个文件)、`src/tts/`(约 50 个文件)、`src/meeting-bot/`共同构成了这块能力的实现主体,规模和复杂度在整个仓库里都名列前茅——这也从侧面说明"让 Agent 说话、听懂人说话"远不是一个简单的语音转文字接口能覆盖的问题。

## 学习目标

- 理解 Talk 模式覆盖的多种运行时形态:原生语音识别 + Gateway 聊天 + TTS 播放,和"实时语音"(realtime)两条路径的本质区别。
- 弄清语音唤醒(Voice Wake)为什么是"Gateway 拥有的全局列表",而不是每个设备各自维护一份。
- 理解 TTS 的语音指令(voice directive)机制——回复文本里的一行 JSON 如何控制这一次或此后的播放音色。
- 通读会议机器人的三种参与模式(`agent`/`bidi`/`transcribe`)和它依赖的虚拟音频桥接方案,理解为什么"验证扬声器真的说出话了"比"命令返回成功"更重要。
- 建立对源码目录结构的直观认识:`src/talk/`、`src/tts/`、`src/meeting-bot/`各自的职责边界。

## 背景与设计动机

语音交互看起来像是"录音→转文字→模型处理→转语音→放声音"这样一条简单的流水线,但 OpenClaw 实际支撑的场景要复杂得多:同一个"Talk"入口,在浏览器里可能是客户端自己攒 WebRTC 连接、在 iOS 上可能是原生语音识别、在 Discord 语音频道里可能是走 Gateway 中继的实时语音模型、在会议软件里甚至要先把声音从虚拟麦克风设备里"捞"出来才能进处理链路。`docs/nodes/talk.md`一句话点出了这个复杂度的根源:

> Talk mode covers these runtime shapes: Native macOS/iOS/Android Talk ... iOS Talk (realtime) ... Apple Watch standalone Talk ... Browser Talk ... Android Talk (realtime) ... Transcription-only clients ...

六种运行时形态,分别对应不同的传输方式(WebRTC、Gateway 中继、原生系统语音识别)、不同的音频所有权(客户端自己攒会话,还是 Gateway 代持),背后共同的设计原则是:语音会话的"控制权"和"音频流转"是两个可以独立变化的维度,协议需要能表达"客户端自己开一条 WebRTC 连接、但工具调用的权限决策依然由 Gateway 说了算"这种混合形态,而不是简单地把语音会话归为"纯客户端"或"纯服务端"两个极端。

## 核心机制详解

### Talk 模式:原生循环与实时会话的分野

原生 Talk 是最基础的形态,`docs/nodes/talk.md`把它的循环描述为:

> Native Talk is a continuous loop: listen for speech, send the transcript to the model through the active session, wait for the response, then speak it via the configured Talk provider (`talk.speak`).

这条循环里,语音识别(STT)完全在设备本地完成(苹果的 Speech 框架、Android 安装的语音服务),识别出的文本走的是普通的 Gateway 聊天通路,回复再交给`talk.speak`合成语音——本质上是"语音包了一层壳的普通聊天",延迟和实现复杂度都比较低。

真正的复杂度出现在"实时语音"(realtime)路径上。macOS 只有在配置**同时**满足三个条件时才会切换到这条路径:

| Key | Required value |
| --- | --- |
| `mode` | `realtime` |
| `transport` | `gateway-relay` |
| `brain` | `agent-consult` |

文档特别强调"部分匹配也不生效":

> Any other combination — including a partially set one — keeps the native path.

这种"全有或全无"的判断方式不是随意的——它避免了配置漂移出一种"看起来像实时语音、实际上某个环节还停留在原生路径"的中间态,那种中间态往往是最难调试的:表面上语音识别和回复都在正常工作,但延迟特征、上下文携带方式、工具调用路径可能悄悄从"实时"退化成了"原生",却没有任何显式提示。

即便配置正确,realtime 路径也不是没有退路。macOS 本地还需要一个独立的开关:

> The Mac must also opt in locally with **Settings > Voice & Talk > Use realtime Gateway relay**. This preference defaults off and stays on that Mac; Gateway config alone never activates the streamed path.

这是一处"配置生效需要两个独立主体都同意"的设计——Gateway 侧配置声明了"这个 Agent 支持实时语音",但具体某台设备要不要真的走这条更复杂、更依赖网络质量的路径,由这台设备的本地偏好决定,单方面的服务端配置无法替设备做这个决定。而且这条路径本身设计了失败退化,而不是失败即中断:

> Talk never silently sits idle. If the relay fails to start — no Gateway route, rejected credentials, or an unsupported model — the failure is logged, the overlay shows the reason, and Talk falls back to the native speech path for that session.

这里的退化方向和前两篇反复强调的"高风险操作绝不隐式回退"看似矛盾,但实际上是一致的——`computer.act`的 Provider 切换之所以不能隐式回退,是因为不同 Provider 对同一个动作的物理执行结果可能不同,回退会造成难以预料的副作用;而 Talk 的 realtime→native 回退,两条路径殊途同归都是"听清用户说话、给出回复",回退只影响延迟和交互流畅度,不影响最终语义,所以协议在这里选择了对用户体验更友好的自动降级,而不是让整个语音会话直接失败。

### 语音唤醒:一份由 Gateway 拥有的全局列表

语音唤醒词(比如"嘿 OpenClaw")乍看是一个纯客户端的功能——毕竟真正做语音匹配的是设备本地的语音识别引擎。但`docs/nodes/voicewake.md`明确把这份配置的所有权放在了 Gateway 一侧:

> Wake words are **one global list owned by the Gateway** — there are no per-node custom lists. Any node or app UI can edit the list; the Gateway persists the change and broadcasts it to every connected client.

这个设计决策解决的是一个多设备一致性问题:如果每台设备各自维护一份唤醒词列表,用户在 iPhone 上加了一个自定义唤醒词,却发现 Mac 上完全不生效,这种体验是难以接受的。把这份状态收敛到 Gateway,配合一个`voicewake.changed`广播事件,任何一台设备修改唤醒词列表都会实时同步到所有连接的客户端和节点——这是一种"配置即状态、状态由 Gateway 单点持有、客户端全部是订阅者"的模式,和 Node 命令面"由 Gateway 审批、设备端只是声明和执行"的模式在架构精神上是一致的。

值得一提的是,协议区分了两种不同粒度的归一化:全局触发词列表只做"去空白、去空项"的宽松归一化;而"触发词到目标 session 的路由规则"则做更严格的归一化——转小写、去掉每个单词首尾的标点、合并空白——目的是让`"Hey, Bot!!"`和`"hey bot"`被认定为同一条路由规则,避免用户不小心注册了两条实质相同、只是大小写和标点不同的重复路由。

### TTS:声音由播报内容里的一行 JSON 控制

TTS(文本转语音)侧最有意思的机制是"语音指令"(voice directive)——助手可以在回复文本的第一行嵌入一段 JSON,来控制这一次或者此后所有回复要用的音色:

```json
{ "voice": "<voice-id>", "once": true }
```

`docs/nodes/talk.md`定义了这条指令的解析规则:

> First non-empty line only; the JSON line is stripped before TTS playback. Unknown keys are ignored. `once: true` applies to the current reply only; without it, the voice becomes the new Talk mode default.

这是一种很轻量但表达力足够的机制——不需要专门的 RPC 调用去"切换音色",模型只要在生成回复时,在最前面附上这样一行 JSON,系统就能在朗读之前把这行元数据摘掉、按声明切换发音人。`once`字段的存在把"临时用一次不同的音色"和"从此以后默认换成这个音色"两种意图明确区分开,避免了"这次特意换个声音朗读"之后忘记切回默认音色的尴尬。

`src/tts/`目录下的文件命名也印证了这套设计——`directives.ts`/`directive-facts.ts`/`directive-number.ts`专门处理这类指令解析,和`tts-core.ts`(核心的文本准备、Provider 选择、语音输出协调逻辑)、`tts-runtime-routing.ts`(运行时路由)分工清晰。`src/tts/tts-core.ts`的模块注释直接点明了它的职责边界:

```ts
// TTS core coordinates text preparation, provider selection, and speech output.
```

一个值得记录的工程细节是,`tts-core.ts`里加载"文本摘要"依赖的方式是显式的懒加载:

```ts
function loadDefaultSummarizeTextDeps(): Promise<SummarizeTextDeps> {
  // Speech provider imports should not initialize the LLM stack. Load it only
  // when synthesis actually needs summarization, then reuse the module bindings.
  return (defaultSummarizeTextDepsPromise ??= Promise.all([
    import("../agents/simple-completion-runtime.js"),
    import("../agents/model-auth.js"),
  ]).then(...));
}
```

这条注释解释了一个容易被忽略的架构考量:语音合成模块不应该在被导入的那一刻就顺带拖起整个 LLM 推理栈的初始化——只有当播报文本确实太长、需要先跑一次摘要压缩时,才动态`import`模型相关模块。这样设计的好处是,单纯只想用 TTS 播放一段已经准备好的文本的调用方,不会为了一个用不上的功能而承担模型栈的初始化开销。

### 会议机器人:三种模式与"验证扬声器真的响了"

`src/meeting-bot/`把整套语音栈接进了 Zoom、Google Meet、Microsoft Teams 这类会议软件。三个平台共享同一套参与模式定义,`docs/plugins/meeting-plugins.md`给出的三种模式是:

| Mode | Behavior | Audio requirements |
| --- | --- | --- |
| `agent` | 实时转写喂给配置的 OpenClaw Agent,由常规 OpenClaw TTS 朗读回复 | Chrome talk-back 需要受支持的虚拟音频后端 |
| `bidi` | 一个实时语音模型直接监听并回复 | 同上 |
| `transcribe` | 仅旁听,暴露有限的实时字幕 | 不需要虚拟音频桥接 |

源码里`src/meeting-bot/meeting-modes.ts`把"是否属于会说话的模式"抽成了一个独立的纯函数:

```ts
export function isMeetingTalkBackMode(mode: string): boolean {
  return mode === "agent" || mode === "bidi";
}
```

这个函数被`isMeetingRealtimeRouteReady`复用,后者综合判断"当前是不是会说话的模式"加上"浏览器健康状态里是否已经确认在通话中、麦克风没静音、音频输入输出都已经路由完毕、没有待处理的人工操作"——只有这些条件全部满足,才认为实时语音链路真正就绪。这种把判断条件拆解成小型纯函数再组合的写法,和 Node 协议里"读取型能力宽松、控制型能力层层校验"的克制风格是同一种工程品味的延伸。

会议机器人最值得展开的一处设计,是"如何证明声音真的从虚拟麦克风里传出去了",而不只是"合成命令返回了成功"。`docs/plugins/meeting-plugins.md`对这一点写得很直接:

> For talk-back smoke tests, verified speech requires more than bytes accepted by the playback command. The shared command-pair bridge correlates a bounded waveform fingerprint from the current output generation with audio returning on the selected virtual microphone capture path; Google Meet, Teams, and Zoom do not report `speechOutputVerified: true` when only the output-byte counter advances or unrelated participant audio is present.

这段话解释了一个容易被忽视的失败模式:播放命令本身"接受了多少字节"和"扬声器真的发出了声音、这段声音又真的通过虚拟麦克风被会议软件采集到"是两件完全不同的事——虚拟音频设备配置错误、系统音量被静音、播放路由指向了错误的输出设备,这些故障场景下播放命令依然可以"成功返回",但会议里的其他参会者根本听不到任何声音。协议的解法是采集一份"当前这次输出"的有界波形指纹,再去虚拟麦克风的采集路径上寻找这份指纹是否真的出现——只有指纹在采集端被识别到,才认为这次"说话"被真正验证了。这是一种端到端的验证思路:不信任中间环节报告的"成功",只信任在链路最终出口处观测到的真实效果。

这套验证机制依赖的虚拟音频后端本身也是平台相关的具体基础设施——macOS 用`BlackHole 2ch`加`sox`搭一条虚拟声卡链路,Linux 桌面用 PipeWire-Pulse 创建一个专用的 null sink:

> On a Linux desktop with PipeWire-Pulse ... OpenClaw creates and reuses an `OpenClaw Meeting Audio` null sink and matching source in the desktop user's audio session.

这再次呼应了第二篇讲到的"每个平台如实反映自己的能力边界"这条原则——没有统一的跨平台虚拟音频 API,会议机器人就老老实实针对每个操作系统接入它原生支持得最好的虚拟音频方案,而不是自己发明一套跨平台抽象去掩盖底层差异。

三种模式里,只有`transcribe`不需要这整套虚拟音频桥接,因为它压根不需要"说话"——这也是为什么文档建议"先用`transcribe`模式做冒烟测试":先确认能不能正常加入会议、正常拿到字幕,再逐步引入更复杂的语音桥接和实时对话链路,把故障排查的维度拆解开,而不是一上来就调试一整条"加入会议+听懂+说话"的复杂链路。

会议记录方面,三种模式都会在离开会议时把完整的字幕行和一份摘要写入共享状态数据库,`openclaw transcripts`可以列出、查看或导出这些记录:

> In all three modes, browser joins also persist completed caption rows and a derived summary to the shared state database. ... This durable notes path does not change the live agent-consult transcript or create an audio/video recording.

这条设计边界也值得注意——会议机器人产生的是"文字记录",不是"音视频录制"。这不只是一个功能取舍,更像是一条克制的隐私默认值:默认情况下留存的是可审计的文字摘要,而不是留存原始音视频这种信息量和隐私风险都高得多的数据形态。

### Discord 语音:一条相邻但不属于会议机器人的实时对话面

一个容易和会议机器人混淆的相邻能力是 Discord 语音频道。`docs/plugins/google-meet.md`专门用一段话划清了这条边界:

> [Discord voice channels](/channels/discord#voice-channels) provide native, audio-only realtime conversation without browser meeting automation. OpenClaw can join a voice channel, listen, route turns through an OpenClaw agent or realtime voice model, and speak replies. It does not send or receive camera video or screen sharing ... so Discord voice is a related live-conversation surface rather than a fourth browser meeting plugin.

Discord 语音频道走的是原生协议接入,不需要启动一个浏览器、也不需要虚拟音频设备去"骗过"视频会议软件的麦克风输入检测——它是纯音频的实时对话,机制上更接近 Talk 模式里的"实时语音会话"而不是会议机器人的"浏览器自动化加入会议"。这条边界说明 OpenClaw 并没有把"能不能实时对话"和"是不是在开视频会议"这两件事混为一谈:同样是语音,走原生协议还是走浏览器自动化,取决于目标平台本身有没有开放原生接入能力——有就用原生协议(Discord),没有就只能靠浏览器自动化去参与人类习惯使用的图形化会议客户端(Zoom/Meet/Teams)。

## 常见问题/易踩坑

- **只满足部分 realtime 配置项就期望 Talk 走实时路径**：`mode`/`transport`/`brain`三者必须同时精确匹配,任何一个不对都会静默留在原生路径,而不会报错提示"配置不完整"。
- **以为语音唤醒词是每台设备各自的设置**：它是 Gateway 拥有的全局列表,在一台设备上修改会广播到所有连接的客户端,不存在"只对这台设备生效"的本地唤醒词。
- **用回复文本里出现的语音指令 JSON 当作永久生效的默认值**：没有显式设置`once: true`时,声音选择确实会变成新的默认值并持续到下一次修改,这一点容易在测试时被误以为是"临时生效一次"。
- **把会议机器人播放命令的成功返回当作"对方已经听到"的证据**：只有虚拟麦克风采集路径上观测到匹配的波形指纹,才是真正验证到声音输出的证据,命令层面的成功不能替代这层验证。

## 小结

语音与实时能力这块拼图,靠三层职责清晰的分工组织起来:Talk 定义了从"原生识别+聊天+TTS"到"全链路实时语音"的多种运行时形态,并通过"配置必须精确匹配才切换路径、切换失败则优雅退化到原生"这两条规则控制复杂度;语音唤醒把状态所有权收敛到 Gateway,靠广播机制保证多设备一致性;TTS 用一行嵌入回复文本的 JSON 指令,以最小的协议开销实现了灵活的音色控制,同时对不必要的模型栈初始化保持懒加载的克制。会议机器人则是把这套语音栈接入第三方会议软件的一层适配,它最值得记住的设计是"不信任中间环节报告的成功,只信任链路终点观测到的真实效果"——这条原则不仅适用于语音验证,也是贯穿整个 Node 与语音体系的一条隐藏主线。下一章将从设备与语音这类"外部接口"转向 OpenClaw 内部更深层的状态管理问题:记忆与人格系统,看 Agent 如何跨会话记住用户、如何维持一个稳定但又可配置的"性格"。
