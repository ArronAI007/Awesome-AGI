# 对外协议 SDK、ACP 与生态兼容 Hooks

> 前两篇讲的是"dsh 内部怎么把 Host 和 Client 连起来",本篇要讲的是"外部世界怎么把 dsh 整体当成一个黑盒来用"。dsh 对外暴露了三条完全不同的接入路径:一条是给任意语言用的通用 stdio JSON-RPC 协议(`packages/sdk`),一条是对接业界标准 Agent Client Protocol 的自动化服务器(`packages/acp`),还有一条是让用户直接复用 Claude Code/Codex 现有 hook 脚本、不用重写的生态兼容层(`packages/hooks`)。这三条路径解决的是同一类问题的三个不同侧面——"怎么在不深入了解 dsh 内部包结构的前提下,让外部程序驱动它、或者扩展它"。

## 学习目标

- 理解 `packages/sdk` 这个通用 SDK 和上一篇讲的 Python SDK 的关系——两者驱动的是同一套 wire protocol,但 `packages/sdk` 更底层、面向"仓库邻近的 TypeScript 消费者"。
- 理解 `packages/sdk/protocol` 定义的 newline-delimited JSON-RPC 2.0 消息格式,以及请求/响应/通知三种帧如何靠 `id`/`method` 字段的有无区分。
- 掌握 `packages/acp` 的定位:一个基于业界标准 `@agentclientprotocol/sdk` 包实现的自动化专用 ACP 服务器,面向程序化客户端而非产品 UI。
- 理解 `packages/hooks` 的生态兼容层设计——不是重新发明一套 hook 协议,而是把外部 shell hook 协议翻译到 dsh 内部规范的扩展点上。
- 搞清楚 `PreToolUse`/`PostToolUse`/`Stop` 等 Claude Code/Codex hook 事件,分别映射到 dsh 内部的哪些扩展点(`tools/pre-execute`、`tools/post-execute`、`agent/turn-stopping` 等)。

## 背景与设计动机

一个 Agent 运行时如果只能通过自己的 Web UI 使用,它的价值会被严重限制。dsh 团队显然意识到了这一点,所以在"直接 npm 依赖"和"浏览器 WebSocket 连接"这两条路径之外,又开辟了三条面向外部集成的路径。`packages/sdk/README.md` 用一句话概括了这一整组包的定位：

```text
// packages/sdk/README.md:1-11
# sdk/ — drive Harness runtimes from another process
This group contains the protocol stack for driving a Harness runtime from
another process. Callers supply the runtime executable and its `cordis.yml`;
this group does not create, configure, build, or launch developer projects.

| Package | Role |
|---|---|
| protocol/ | Defines the SDK runtime wire protocol |
| client/   | Drives a Harness runtime through the TypeScript client API |
| server/   | Serves out-of-process SDK clients over stdio JSON-RPC |
```

"不负责创建、配置、构建或启动开发者项目"——这条边界划得很清楚:SDK 只负责协议,不负责替调用方决定"你的 Agent 应该由哪些插件组成"。这和上一篇讲的 Python SDK 是同一种哲学的两个体现:协议是稳定的、可以被任何语言实现的契约,而"这个 Agent 到底装了哪些工具、连了哪个 LLM"完全是调用方通过 `cordis.yml` 自己决定的事。

## 核心机制详解

### `packages/sdk`:通用 stdio JSON-RPC,Python SDK 的"设计双胞胎"

`packages/sdk/client/README.md` 直接点名了这个包和 Python SDK 的关系：

```text
// packages/sdk/client/README.md:1-7
# @deepseek-ai/dsh-sdk-client
The TypeScript client SDK for driving a DeepSeek Harness runtime as a
subprocess over stdio JSON-RPC — the design twin of the Python SDK... A pure
library: it registers nothing on a Cordis context; the runtime process it
spawns is a complete harness whose composition its own `cordis.yml` decides.

Unlike the Python SDK, the launch spec is fully explicit (`command`/`args`):
this package is for repo-adjacent TypeScript consumers... that know which
runtime they are launching.
```

"设计双胞胎"(design twin)——两者驱动的是同一套 wire protocol、同一种"spawn 子进程 + stdio 通信"的思路,区别只在于目标用户:Python SDK 面向完全不了解 Node 生态的用户,所以要把整个运行时打成单文件 exe(上一篇的内容);而这个 TypeScript 版本假设调用方本来就"仓库邻近"(repo-adjacent)、清楚自己要启动哪个运行时,所以启动参数是完全显式的 `command`/`args`,不做任何打包封装。

协议本身定义在 `packages/sdk/protocol`,用的是标准的换行分隔 JSON-RPC 2.0：

```ts
// packages/sdk/protocol/src/transport.ts:1-9
/**
 * Newline-delimited JSON-RPC 2.0 over byte streams. Frames with `id` and
 * `method` are requests, `id` alone is a response, and `method` alone is a
 * notification. Malformed lines are ignored; handler failures become error frames.
 *
 * @module @deepseek-ai/dsh-sdk-protocol/transport
 */
```

三种帧的判定规则——`id`+`method` 是请求,只有 `id` 是响应,只有 `method` 是通知——和上一篇 Python `client.py` 里 `_handle_message()` 的判定逻辑完全对应,再次印证"设计双胞胎"这个说法不是场面话。写帧的实现同样是"一行 JSON + 换行符"：

```ts
// packages/sdk/protocol/src/transport.ts:260-262
private write(message: Record<string, unknown>): void {
  this.output.write(`${JSON.stringify(message)}\n`)
}
```

请求方法命名遵循"`名词/动词`"的规范(客户端→服务端),通知则用"`名词.事件`"(服务端→客户端)——两种命名风格本身就在帮读者一眼分辨消息方向：

```text
// packages/sdk/protocol/README.md(节选)
| Direction | Method | Types |
|---|---|---|
| client→server | initialize | InitializeParams → InitializeResult |
| client→server | session/prompt | SessionPromptParams → SessionPromptResult(durable enqueue receipt) |
| client→server | shutdown | 无参数 → {} |
| server→client | session.event | SessionEventNotification(runtime 内每个 session 的事件,不做过滤) |
| server→client | session.status | SessionStatusNotification(整个 agent 的 running/idle 转换) |
| server→client | subagent.started | SubagentStartedNotification |
| server→client | subagent.finished | SubagentFinishedNotification(仅限进程内运行的子代理) |
```

对应的强类型定义把这份表格变成了编译期可检查的类型约束：

```ts
// packages/sdk/protocol/src/types.ts:92-105
export interface HarnessSdkNotificationMap {
  'session.event': SessionEventNotification
  'session.status': SessionStatusNotification
  'subagent.started': SubagentStartedNotification
  'subagent.finished': SubagentFinishedNotification
}

export interface HarnessSdkRequestMap {
  'initialize': { params: InitializeParams; result: InitializeResult }
  'session/prompt': { params: SessionPromptParams; result: SessionPromptResult }
  'shutdown': { params: undefined; result: Record<string, never> }
}
```

Server 端(`@deepseek-ai/dsh-sdk-jsonrpc-server`)是一个把这三个方法接到真实 Cordis 运行时上的分派器：

```ts
// packages/sdk/server/src/server.ts:190-201
async handleRequest(method: string, params: Record<string, unknown> | undefined): Promise<unknown> {
  switch (method) {
    case 'initialize':
      return this.initialize(params as unknown as InitializeParams)
    case 'session/prompt':
      return this.prompt(params as unknown as SessionPromptParams)
    case 'shutdown':
      return this.shutdown()
    default:
      throw new Error(`unknown DeepSeek Harness SDK runtime method: ${method}`)
  }
}
```

这里同样能看到本课程反复出现的"stdout 只能是协议帧"原则：

```text
// packages/sdk/server/README.md:15-17
## stdout is the protocol
Stdout carries only JSON-RPC frames. The deployment must not compose a
stdout logger; diagnostics belong on stderr.
```

Client 端的 `HarnessClient` 类自己 spawn 子进程,而不是走 dsh 内部统一的 `dsh-subprocess` 服务——文档专门解释了这个例外：

```text
// packages/sdk/client/src/client.ts:1-14(模块注释节选)
Low-level JSON-RPC client for a DeepSeek Harness SDK runtime subprocess.
HarnessClient owns the child process: it spawns the runtime, speaks the
@deepseek-ai/dsh-sdk-protocol wire over the child's stdio, fans server
notifications out to subscriptions, and tears the child down to quiescence
through a private EOF → SIGTERM → SIGKILL ladder. This client runs OUTSIDE
any harness context, so it spawns directly rather than through the
dsh-subprocess service — the seam's documented exception for SDK-managed
transports.
```

"运行在任何 harness context 之外"——这句话点出了这类 SDK 客户端的本质:它们不是 dsh 内部的一个插件,而是完全独立于 dsh 进程空间之外的调用方,理所当然不能依赖只有 Cordis 插件才能访问的内部服务。高层封装 `DeepSeekHarness` 提供了更友好的使用方式：

```ts
// packages/sdk/client/README.md:11-22
import { DeepSeekHarness } from '@deepseek-ai/dsh-sdk-client'

await using harness = new DeepSeekHarness({
  launch: { command: 'node', args: ['lib/bin.js', 'cordis.yml'] },
  provider: 'deepseek-official',
  model: 'deepseek-v4-flash',
  maxTokens: 49_152,
})
const result = await harness.run('say hi')
console.log(result.finalResponse)
```

### ACP:基于业界标准协议的自动化服务器

`packages/acp` 这个名字下真正的实现代码在子目录 `packages/acp/acp` 里,定位说明写得很直接：

```text
// packages/acp/README.md:1-11
# acp/ — Agent Client Protocol automation
The ACP group exposes harness agents to programmatic clients over the Agent
Client Protocol. It is an interoperability transport, not a presentation or
human-interaction layer; the matching out-of-process subagent client lives in
subagent/subagent-acp because it implements the subagent provider interface.
```

```text
// packages/acp/acp/README.md:5-7
Automation-only Agent Client Protocol server over JSON-RPC stdio. Programmatic
clients create fresh harness agents, send text prompts, collect committed
assistant text, resolve one-shot permission requests by policy, and cancel
work. This package is a transport adapter, not a UI integration or a
capability seam. It does not expose editor navigation, transcript replay,
commands, modes, configuration pickers, elicitation, reasoning, plans, titles,
or tool presentation. Interactive rendering and human questions belong to the
Web host and client modules.
```

值得特别指出的一点是,这个包依赖的是业界通用的 `@agentclientprotocol/sdk`(版本 `0.25.1`),这是源自 Zed 发起的 [Agent Client Protocol](https://agentclientprotocol.com) 规范的官方 TypeScript SDK：

```json
// packages/acp/acp/package.json:34-37
"dependencies": {
  "@agentclientprotocol/sdk": "0.25.1",
  "@deepseek-ai/schemastery": "workspace:^"
}
```

也就是说,dsh 这边没有自造一套"看起来像 ACP 但细节不一样"的协议,而是直接调用了这个业界标准包提供的类型和运行时(`AgentSideConnection`、`ndJsonStream`、`PROTOCOL_VERSION`、`RequestError` 等)。建立 stdio 连接的方式,是把 Node 的标准输入输出流适配成 Web Streams API,再交给协议 SDK：

```ts
// packages/acp/acp/src/index.ts:348-353
const stream: Stream = config.stream ?? ndJsonStream(
  Writable.toWeb(process.stdout) as WritableStream<Uint8Array>,
  Readable.toWeb(process.stdin) as ReadableStream<Uint8Array>,
)
conn = new AgentSideConnection(makeAgent, stream)
```

`initialize` 方法的响应故意声明了最保守的能力集——不支持图片、音频、嵌入式上下文,也不声明任何认证方式：

```ts
// packages/acp/acp/src/index.ts:234-245
initialize(_params: InitializeRequest): Promise<InitializeResponse> {
  return Promise.resolve({
    protocolVersion: PROTOCOL_VERSION,
    agentInfo: { name: 'deepseek-harness-acp', version: '0.0.1' },
    agentCapabilities: {
      promptCapabilities: { image: false, audio: false, embeddedContext: false },
    },
    authMethods: [],
  })
},
```

`session/new` 创建一个真实的 dsh Agent 实例,和普通的 Agent 创建流程没有区别,只是包了一层 ACP 的 session 语义：

```ts
// packages/acp/acp/src/index.ts:251-275(节选)
async newSession(params: NewSessionRequest): Promise<NewSessionResponse> {
  assertOpen()
  validateSessionParams(params)
  const sessionId = SessionId(randomUUID())
  const handle = await agents.create({
    sessionId,
    meta: { cwd: params.cwd },
    agentOptions: agentOptions(config),
  })
  sessions.set(sessionId, {
    agent: handle.agent,
    dispose: () => handle.dispose(),
    inflight: undefined,
  })
  return { sessionId }
},
```

完整的方法-行为对照表能看出这个 ACP 服务器"故意做得很窄"的克制设计——每个方法只做协议要求的最小事情,不试图去覆盖 UI 层的职责：

```text
// packages/acp/acp/README.md:20-31(节选)
| Method | Behavior |
|---|---|
| initialize | Negotiates the supported version and advertises baseline-only prompts. |
| session/new | Creates a fresh agent with an absolute primary cwd. |
| session/prompt | Concatenates text blocks... permits one in-flight request per session, and waits for the whole agent to become idle. |
| session/cancel | Cancels only the addressed agent and settles its pending prompt as cancelled. |
| session/update | Emits one agent_message_chunk per non-empty text block in a committed assistant/message. |
| session/request_permission | Offers one-shot allow/reject choices for bridge-owned approval requests carrying a tool call id. |
```

仓库里的 `examples/acp-agent` 示例进一步说明了这个服务器面向谁——不是面向"人在 IDE 里点击交互",而是面向"父 Agent、子 Agent provider 和其他程序化客户端"：

```text
// examples/acp-agent/README.md:1-5
# acp-agent example
Automation-oriented Agent Client Protocol server over JSON-RPC stdio. It is
intended for parent agents, subagent providers, and other programmatic
clients, not as the product UI.
```

这也解释了为什么 `initialize` 响应里所有交互能力(editor navigation、transcript replay、commands、elicitation 等)都是关闭的——这个服务器的假设受众本身就不需要这些人机交互特性,它们属于 Web host/client 模块的职责范围。

### hooks-claude-code / hooks-codex:翻译外部协议,而不是重新发明

`packages/hooks/README.md` 一句话点出了这个子系统存在的动机——让用户能复用已经写好的 hook 脚本,而不必为 dsh 重写一套：

```text
// packages/hooks/README.md:1-13
# hooks/ — hook bridges + shared protocol
The hooks subsystem lets users extend the agent at lifecycle points the way
Claude Code and Codex do — by pointing a bridge plugin at an existing
hooks.json (or settings) so those external shell hooks run faithfully. The
canonical extension surface itself is the harness's typed interception
points; a "native hook" is just an ordinary Cordis plugin on those extension
points. These packages are the bridges that translate the external
shell-hook protocol onto that same surface, plus the shared wire-protocol
library they build on.
```

这段话里有个关键设计洞察:dsh 内部本来就有一套"typed interception points"(类型化的拦截点),写一个原生 hook 其实就是往这些拦截点上挂一个普通的 Cordis 插件。`hooks-claude-code`/`hooks-codex` 不是给 dsh 新增一种能力,而是**把外部 shell hook 的协议格式,翻译成对这些已有拦截点的调用**——用户完全不需要知道 dsh 内部长什么样,只要有一份能被 Claude Code 或 Codex 识别的 `hooks.json`,指给这个桥接插件就能直接生效。

两个桥接包构造给外部 shell 命令的 stdin payload 格式并不相同,分别贴合各自生态的既有约定。Claude Code 桥接用近似驼峰/蛇形混合的字段名：

```ts
// packages/hooks/hooks-claude-code/src/index.ts:322-346(节选)
function base(ctx: Context, agent: Agent | undefined, event: string): Record<string, unknown> {
  return {
    session_id: agent?.session.header.id ?? '',
    transcript_path: agent === undefined ? '' : ctx.get('sessionPersistence')?.locate(agent.session.header)?.path ?? '',
    cwd: agent?.session.header.cwd ?? process.cwd(),
    hook_event_name: event,
  }
}
function preToolPayload(ctx: Context, exec: ToolExecution): Record<string, unknown> {
  return { ...base(ctx, exec.agent, 'PreToolUse'), tool_name: exec.name, tool_input: exec.arguments, tool_use_id: exec.callId }
}
```

Codex 桥接则是纯 snake_case,并且额外携带 `model`/`turn_id`/`permission_mode` 字段,还特别注明"不带结尾换行符"这个和 Claude Code 桥接不一样的细节：

```ts
// packages/hooks/hooks-codex/src/index.ts:1-10(模块注释)
/**
 * Bridge for unmodified Codex command hooks on harness interception points. It
 * supports five points (SessionStart, prompt/tool pre/post, Stop), regex-only
 * matchers, snake_case payloads without a trailing newline, no hook environment
 * or command substitution, and no pre-tool approval or rewrite path; only
 * blocking decisions are honored.
 */
```

```ts
// packages/hooks/hooks-codex/src/index.ts:291-303(节选)
function base(ctx: Context, agent: Agent | undefined, event: string, model: string): Record<string, unknown> {
  return {
    session_id: agent?.session.header.id ?? '',
    transcript_path: agent === undefined ? null : ctx.get('sessionPersistence')?.locate(agent.session.header)?.path ?? null,
    cwd: agent?.session.header.cwd ?? process.cwd(),
    hook_event_name: event,
    model,
    permission_mode: 'default',
  }
}
```

这种"每个桥接自己贴合外部协议的具体字节格式,但都翻译到同一套内部拦截点"的分层,正是这个生态兼容层的核心价值——它把"跟外部生态的字节级兼容"和"跟 dsh 内部的语义对接"清晰地分成了两层,后者两个桥接包完全共用。

### PreToolUse/PostToolUse/Stop 到底映射到哪个内部扩展点

这是这套兼容层里最值得细读的部分。dsh 内部的规范扩展点定义在 Agent Note 里,概括为一句话:每次工具调用都走 `tools/pre-execute` → 守卫 → `tools/execute` → 派发 → `tools/post-execute` → `finalizeContent` → `tools/result` 这条流水线,`tools/pre-execute` 是"允许/拒绝/询问"的瀑布式门,`tools/post-execute` 是"接受/带反馈拦截/替换内容/附加上下文"的检查转换瀑布。

**`PreToolUse` → `tools/pre-execute`**(两个桥接包结构完全一致,以 Claude Code 版为例)：

```ts
// packages/hooks/hooks-claude-code/src/index.ts:237-244
ctx.on('tools/pre-execute', async (exec, next): Promise<PreToolDecision> => {
  const turn = lastTurn(exec.agent)
  const merged = await runPoint('PreToolUse', exec.name, preToolPayload(ctx, exec), { ...exec.agent ? { agent: exec.agent } : {}, turn, signal: exec.signal })
  if (merged.decision === 'deny') return { kind: 'deny', reason: merged.reason ?? 'blocked by PreToolUse hook' }
  if (merged.decision === 'ask') return { kind: 'ask', ...merged.reason !== undefined ? { reason: merged.reason } : {} }
  return next()
})
```

**`PostToolUse` → `tools/post-execute`**：

```ts
// packages/hooks/hooks-claude-code/src/index.ts:246-265(节选)
ctx.on('tools/post-execute', async (exec, result, next): Promise<PostToolDecision> => {
  const turn = lastTurn(exec.agent)
  const merged = await runPoint('PostToolUse', exec.name, postToolPayload(ctx, exec, result), { ...exec.agent ? { agent: exec.agent } : {}, turn, signal: exec.signal })
  const context = contextFrom(merged)
  if (merged.decision === 'deny') {
    return { kind: 'block', feedback: [{ type: 'text', text: merged.reason ?? 'blocked by PostToolUse hook' }], ...context ? { additionalContexts: [context] } : {} }
  }
  const downstream = await next()
  if (!context) return downstream
  return { ...downstream, additionalContexts: prependContext(context, downstream.additionalContexts) }
})
```

**`Stop` → `agent/turn-stopping`**——这一点尤其精妙:dsh 内部本来就有一个"回合即将停止"的通知点,一个返回"继续"的 Stop hook 只需要调用 `agent.steer()` 往对话里注入一条新消息,就能让机器观察到待处理输入、自然地再跑一步,完全不需要一个专门的"阻止停止"API：

```ts
// packages/hooks/hooks-claude-code/src/index.ts:267-277
ctx.on('agent/turn-stopping', async ({ agent, turn, signal }): Promise<void> => {
  const merged = await runPoint('Stop', '', stopPayload(ctx, agent), { agent, turn, signal })
  if (merged.decision === 'deny') {
    const text = merged.reason ?? 'continue: blocked by Stop hook'
    agent.steer(createUserMessage({ content: [{ type: 'text', text }], source: PLUGIN_SOURCE }))
  }
})
```

**`UserPromptSubmit` → `agent/pre-step`**,**`SessionStart` → `agent/session-start`**同样各自对应一个明确的内部拦截点。完整映射表把这七类事件和内部扩展点的关系列得很清楚：

```text
// packages/hooks/hooks-claude-code/README.md:37-45
| CC hook | Harness point | Mapping |
|---|---|---|
| SessionStart | agent/session-start (emit) | additionalContext → agent.inject() into the new session(不能阻塞) |
| UserPromptSubmit | agent/pre-step (waterfall) | deny → PreStepDecision.reject |
| PreToolUse | tools/pre-execute (waterfall) | deny → PreToolDecision.deny; ask → PreToolDecision.ask |
| PostToolUse | tools/post-execute (waterfall) | deny → block with feedback |
| Stop | agent/turn-stopping (serial) | 一个阻塞的 Stop hook 通过 steer() 把理由喂回去,强制再跑一步 |
| SubagentStart | subagent/start (emit) | additionalContext → 注入到存活的进程内子代理 |
| SubagentStop | subagent/end (emit) | 仅观察,不能干预 |
```

Codex 桥接的映射结构完全相同,只是它只支持前五类事件,不支持 `SubagentStart`/`SubagentStop`(Codex 生态本身当前的 hook 事件集合更小)：

```text
// packages/hooks/hooks-codex/README.md:43-49
| Codex hook | Harness point | Mapping |
|---|---|---|
| SessionStart | agent/session-start (emit) | 纯 stdout 输出的 hook → additionalContext → agent.inject() |
| UserPromptSubmit | agent/pre-step (waterfall) | block(exit 2) → PreStepDecision.reject |
| PreToolUse | tools/pre-execute (waterfall) | block → PreToolDecision.deny(没有 allow/ask 两态) |
| PostToolUse | tools/post-execute (waterfall) | block → block with feedback |
| Stop | agent/turn-stopping (serial) | 同 CC:一个阻塞的 Stop hook 通过 steer() 强制再跑一步 |
```

两个桥接包共用同一个 `hook-protocol` 底层库,承载真正跟外部世界打交道的脏活——`matcher.ts` 做规则匹配(CC 支持字面量或正则,Codex 只支持正则)、`runner.ts` 真正执行 shell 命令并处理超时/中止、`codec.ts` 把"exit code + stdout + stderr"解析成中立的 `HookOutput`、`merge.ts` 按 `deny > ask > allow` 的优先级合并多个 hook 的结果、`detached.ts` 追踪那些"发出去不等结果"的 fire-and-forget hook(比如 `SessionStart`)以确保插件卸载时能正确等待或中止它们。

## 常见问题/易踩坑

- **`packages/sdk` 和 `python/sdk` 是不是同一个东西的两份实现？** 不完全是。两者驱动的是设计上高度一致的 wire protocol("design twin"),但 `packages/sdk` 假设调用方清楚自己在启动哪个运行时(显式 `command`/`args`),不做任何单文件打包;Python SDK 则为了让完全不懂 Node 的用户也能用,额外做了"把整个运行时打成单文件 exe"这层分发优化。
- **ACP 是不是给 IDE 插件用的？** 仓库里的文档没有明确提到 IDE 插件这个场景,反而反复强调"面向程序化客户端、父 Agent、子 Agent provider,不是产品 UI"。ACP 协议本身在业界(比如 Zed 编辑器)确实常被用作 IDE 接入 Agent 后端的协议,但 dsh 这边的实现克制地只做了协议服务端本身,没有为任何特定的 IDE 场景做定制。
- **写一个"原生 hook"和用 hooks-claude-code 桥接,效果一样吗？** 语义上是等价的——两者最终都是往 `tools/pre-execute`/`tools/post-execute`/`agent/turn-stopping` 等同一套内部拦截点上挂逻辑。区别只在于:原生 hook 是一个直接写 TypeScript、以 Cordis 插件形式存在的扩展;而 hooks-claude-code/hooks-codex 桥接是"用一份 `hooks.json` 配置外部 shell 命令,由桥接插件负责协议翻译"。
- **Codex 的 `PreToolUse` 为什么没有 `ask` 这一态？** 因为 Codex 生态本身的 hook 协议只有"block/不 block"两种结果(退出码是否为 2),没有第三种"询问用户"的中间态,桥接只能忠实反映这个上游协议的能力边界,不会凭空多造一个 Codex 协议本身不支持的选项。

## 小结

`packages/sdk`、`packages/acp`、`packages/hooks` 这三条对外路径,表面上服务的是完全不同的场景——语言无关的黑盒驱动、业界标准协议对接、生态脚本复用——但背后遵循的是同一条设计原则:**协议是稳定的、可以被独立实现的契约,业务逻辑和内部实现细节永远不应该泄漏到协议层面**。`packages/sdk` 靠一份简单到几行注释就能说清楚的 NDJSON envelope 规则,承载了 Python SDK 和 TypeScript SDK 两份独立实现;`packages/acp` 靠直接采用业界标准包,避免了自造协议带来的兼容性负担;`packages/hooks` 靠把外部协议格式和内部拦截点严格分层,让"跟 Claude Code/Codex 生态字节级兼容"这件麻烦事,完全不影响 dsh 内部"typed interception points"这套核心扩展机制的整洁性。这三条路径共同构成了 dsh"作为黑盒被外部世界驱动"的完整版图。
