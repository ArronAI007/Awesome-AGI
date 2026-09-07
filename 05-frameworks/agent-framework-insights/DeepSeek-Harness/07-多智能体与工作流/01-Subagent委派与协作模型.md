# Subagent 委派与协作模型

> 一个 Agent 能不能把手头的活儿"分包"出去,交给另一个 Agent 去干,自己只等结果或者顺手继续别的事?dsh 的答案是:能,而且分包的方式不止一种——同进程内 fork 一个带记忆的孩子、同进程内 spawn 一个白板孩子、通过 ACP 协议驱动远程 Agent、直接拉起 `claude`/`codex` 这样的外部 CLI 当子代理,甚至递归地拉起另一整套 dsh 自己。本篇从 `SubagentProvider` 这个统一契约讲起,拆开六种委派后端各自的机制,再讲清楚父子会话之间"谁能看见谁""谁能管谁"的作用域与通信规则。

## 学习目标

- 理解 `SubagentProvider` 接口如何用一个 `start()` 方法统一六种截然不同的委派机制(同进程 fork/spawn、ACP 远程、外部 CLI、递归 dsh),并弄清 `inheritsParentContext`/`capabilities` 这些声明式字段解决了什么问题。
- 掌握 `SessionHeader` 里 `delegationDepth`/`parentSession`/`origin` 三个字段如何共同支撑"子代理是谁生的、生了几代、还能不能再生"这套会话血缘与深度预算机制。
- 弄清六种 Provider(`fork-in-process`/`spawn-in-process`/`acp`/`claude-code`/`codex`/`dsh-sdk`)分别适合什么场景,以及为什么 fork 和 spawn 的全部差异只是"要不要塞一份历史记录种子"。
- 读懂 `tool-subagent` 委派工具的三条执行路径(前台等待、一次性后台、可续接后台),理解模型为什么只能填 `prompt`/`description`,却填不了"用哪个 Provider"。
- 区分父子之间三条独立的通信信道:`send_message`/`interrupt_agent`(父→子的主动控制)、`report`(子→父的自愿汇报)、结算通知(运行时→父的强制通知),理解它们为什么故意做成三条不同的信道而不是合并成一条。

## 背景与设计动机

多智能体协作最容易踩的坑,是把"谁负责启动子任务""子任务能看到多少上下文""出了问题谁来兜底"这三件事混在一起变成一坨。dsh 的设计里,这三件事被拆成了三层正交的抽象:

1. **传输层**——`SubagentProvider`,只回答一个问题:"怎么把一个 prompt 变成一个正在跑的子代理"。同进程 fork、同进程 spawn、跨进程 ACP、外部 CLI 子进程,对上层来说都是同一张契约。
2. **血缘与预算层**——`SessionHeader` 里的 `parentSession`/`origin`/`delegationDepth`,负责回答"这个会话是不是子代理""它是谁的孩子""它已经递归了几层"。这一层完全独立于传输机制:无论子代理是 fork 出来的还是外部 CLI 拉起来的,只要走完 `SubagentRuntime` 的创建流程,都会留下同一套血缘记录。
3. **通信层**——`report`/`send_message`/`interrupt_agent`/结算通知,负责回答"父子之间谁能对谁说话,说的话算不算数"。

这种分层的好处是:给系统换一种委派后端(比如从"同进程 fork"换成"外部 Claude Code CLI"),血缘记录和通信规则完全不用变——因为它们根本不知道传输层长什么样。

## 核心机制详解

### `SubagentProvider`:委派后端的统一契约

所有委派后端要实现的核心接口定义在 `packages/subagent/subagent/src/types.ts`:

```typescript
// packages/subagent/subagent/src/types.ts:285-303（节选）
export interface SubagentProvider {
	/** Unique registry name (e.g. `spawn`, `fork`, `acp`). */
	readonly name: string
	/** The start-time features this provider supports (see {@link SubagentCapabilities}). */
	readonly capabilities: SubagentCapabilities
	/**
	 * Whether the child sees the parent's completed-turn prefix. This is descriptive, not a
	 * service-validated start capability: the model-facing tool derives truthful wording from it.
	 * It says nothing about tool registration, injected services, or authority inheritance.
	 */
	readonly inheritsParentContext: boolean
	/**
	 * Establish a ONE-SHOT child and return its handle after publication.
	 * ...
	 */
	start(request: ResolvedSubagentStartRequest): Promise<SubagentRun>
	prepareContinuable?(request: ContinuableCreateRequest): Promise<ContinuableCreateSpec>
}
```

这个接口刻意做得很"瘦":**唯一必须实现的方法是 `start()`**——建立一个一次性(one-shot)子代理,返回一个句柄。`prepareContinuable()` 是可选的,它的"存在与否"本身就是能力声明——某个 Provider 是否支持"可续接"(continuable,能被后台挂起、之后再用 `send_message` 唤醒)的后台子代理,不是靠一个布尔字段标注,而是靠这个方法有没有被实现来判断。

`SubagentCapabilities` 则是一组**启动前**就能检查的静态能力标志(同样在 `types.ts` 里):

```typescript
export interface SubagentCapabilities {
	readonly outputSchema: boolean
	readonly depthLimit: boolean
	readonly toolFilter: boolean
	readonly persona: boolean
}
```

这四个字段分别对应"能不能约束子代理必须以某个 JSON Schema 结束""能不能强制一个最大递归深度""能不能限制子代理可用的工具集""能不能覆写子代理的人设(persona)"。这组能力检查在真正调用 `provider.start()` 之前就会做——如果调用方要求 `outputSchema` 而当前 Provider 不支持,请求会直接失败,而不是等子代理跑完了才发现结果格式不对。

子代理跑起来之后,拿到的句柄类型是 `SubagentRun`:

```typescript
// packages/subagent/subagent/src/types.ts:249-261(节选)
export interface SubagentRun {
	readonly id: SessionId
	readonly localAgent: Agent | undefined
	readonly result: Promise<SubagentResult>
	dispose(): Promise<void>
}
```

注意这里没有 `send()`/`interrupt()`/`list()` 这类方法——**一次性子代理的句柄只负责"等结果"和"清理"**。父代理想给已经在跑的后台子代理发消息、打断它、或者列出自己有哪些子代理,走的是另一套服务级 API(`SubagentRuntime` 上的 `followup()`/`interrupt()`/`listChildren()`),这些方法在下文"父子双向通信"一节详细展开。这个设计选择本身就是一个提示:一次性委派(fire-and-wait)和可续接的后台委派(fire-and-control),在 dsh 里被认为是两种不同强度的关系,不该塞进同一个句柄接口里。

### 会话身处何方:`SessionHeader` 与 `delegationDepth`

子代理终究是一个普通会话(Session),只是它的 `SessionHeader` 多带了几个字段来记录血缘:

```typescript
// packages/core/session/src/types.ts:61-69
export interface SessionHeader {
	readonly version: number
	readonly id: SessionId
	readonly createdAt: number
	readonly cwd?: string
	readonly parentSession?: SessionId
	readonly seedLength?: number
	readonly origin?: 'subagent'
	readonly delegationDepth?: number
	readonly agentPreset?: string
}
```

- `parentSession`——这个会话是从哪个会话派生出来的(种子血缘),顶层会话没有这个字段。
- `origin === 'subagent'`——一个粗粒度的产品分类标记,说明"这个会话是作为子代理创建的"。源码注释特别强调:*这只是展示层的元数据,不是"这个子代理可续接"的证明*——判断能不能续接,要看创建它的 Provider 有没有实现 `prepareContinuable()`,而不是看这个字段。
- `delegationDepth`——顶层会话缺省为 0,子代理是父深度 + 1。之所以要把它**持久化**进会话头,而不是只在运行时内存里记一个计数器,是因为"递归预算必须扛得住重启和续接"——如果子代理被挂起后台、进程重启、之后再被唤醒,它得记得自己原来在第几层,不能因为重启就"洗白"成顶层会话。

深度的读取逻辑体现了这一点,在 `packages/subagent/subagent/src/depth.ts` 里:

```typescript
// packages/subagent/subagent/src/depth.ts:28-36
export function delegationDepthOf(agent: Agent): number {
	const runtime = agent.options.subagentDepth
	if (runtime !== undefined && (!Number.isSafeInteger(runtime) || runtime < 0 || Object.is(runtime, -0))) {
		throw new TypeError('agent subagentDepth must be a non-negative safe integer')
	}
	// The header value was validated at the session boundary (creation and
	// persistence load both construct through the store).
	return Math.max(agent.session.header.delegationDepth ?? 0, runtime ?? 0)
}
```

这里的 `Math.max(持久化的 header 值, 运行时选项)` 是一个很值得注意的小设计:深度只能被**运行时选项加深,不能被它调浅**。这防止了一种作弊路径——一个被冷启动恢复的子代理,如果单纯从运行时选项里读深度(而运行时选项在恢复时是全新构造的、默认可能是 0),就会被当成顶层会话,从而绕开递归预算重新无限委派下去。用持久化值做"下限",运行时值只能"追加深度",堵住了这条路。

真正的深度上限检查发生在创建子代理时,`packages/subagent/subagent/src/child-agent.ts`:

```typescript
// packages/subagent/subagent/src/child-agent.ts:48-57
export function resolveChildDepth(parent: Agent, maxDepth: number | undefined): number {
	const childDepth = delegationDepthOf(parent) + 1
	if (!Number.isSafeInteger(childDepth)) {
		throw new RangeError('subagent child depth exceeds the safe-integer range')
	}
	if (maxDepth !== undefined && childDepth > maxDepth) {
		throw new SubagentDepthError(childDepth, maxDepth)
	}
	return childDepth
}
```

值得强调的是:**全局代码里搜不到一个叫 `MAX_DELEGATION_DEPTH` 的常量**——深度上限完全是"每个工具实例自带配置、调用方自己传"的,不是全局硬编码。`tool-subagent` 的默认配置里 `maxDepth` 是 3(见下文);而所有走外部进程的 Provider(ACP/Claude Code/Codex/dsh-sdk)都声明 `depthLimit: false`,这意味着如果用这些 Provider 配置 `subagent` 工具,部署方必须显式把 `maxDepth` 设成字符串常量 `'provider-managed'`——含义是"深度预算由子代理自己那套 harness/产品去管,父层不插手"。

子代理创建时,`origin`/`delegationDepth`/`parentSession` 会一起写进子会话头,`packages/subagent/subagent/src/child-agent.ts` 里的 `childSessionMeta()`:

```typescript
// packages/subagent/subagent/src/child-agent.ts:102-120（节选)
return {
	...(parentHeader.cwd !== undefined ? { cwd: parentHeader.cwd } : {}),
	...(agentPreset === undefined ? {} : { agentPreset }),
	parentSession: parentHeader.id,
	origin: 'subagent',
	delegationDepth: childDepth,
	...(lineageSeedLength > 0 ? { seedLength: lineageSeedLength } : {}),
}
```

后续列举"某会话的所有子代理"就是靠这两个字段过滤,`packages/subagent/subagent/src/list-children.ts`:

```typescript
// packages/subagent/subagent/src/list-children.ts:141-142
.filter(record => record.header.parentSession === parentSessionId
	&& record.header.origin === 'subagent')
```

### 六种委派后端:从同进程 fork 到外部 CLI 子代理

`SubagentProvider` 这一层契约之下,dsh 目前提供六个具体实现,分布在 `packages/subagent/subagent-*` 六个独立包里。它们的差异全部体现在"用什么机制建立子代理进程/会话",而对上层(`tool-subagent`)完全透明。

| Provider 包 | 机制 | 子代理能看到父会话历史? | 典型场景 |
|---|---|---|---|
| `subagent-fork-in-process` | 同进程内创建新 Agent,种子(seed)填父会话已完成的对话轮次 | 是(`inheritsParentContext: true`) | 便宜的同进程委派,子代理需要知道"我们刚讨论到哪儿了" |
| `subagent-spawn-in-process` | 同进程内创建新 Agent,不填任何种子 | 否 | 最便宜的传输,独立子任务,不需要对话上下文 |
| `subagent-in-process-driver` | 不是 Provider,是前两者共享的底层驱动函数 | — | — |
| `subagent-acp` | 拉起任意外部可执行文件,用 Agent Client Protocol 在 stdio 上驱动 | 否 | 驱动任意"会说 ACP"的远程编码 Agent,不锁定具体产品 |
| `subagent-claude-code` | 通过官方 `@anthropic-ai/claude-agent-sdk` 拉起真实 `claude` CLI | 否 | 把任务委派给 Claude Code 本尊 |
| `subagent-codex` | 拉起 `codex app-server --stdio`,手写 JSON-RPC 协议驱动 | 否 | 把任务委派给 Codex 本尊 |
| `subagent-dsh-sdk` | 拉起另一整套完整的 dsh harness(自己的 `cordis.yml`/模型路由/工具集),用 dsh 自己的 SDK 协议驱动 | 否 | 递归跑一个完全独立配置的 dsh 对等实例(自测/dogfood SDK 本身) |

**fork 与 spawn 的全部差异只是"要不要塞种子"。** `subagent-fork-in-process` 的核心逻辑(`packages/subagent/subagent-fork-in-process/src/index.ts`):

```typescript
function completedTurnPrefix(parent: Agent): SessionEvent[] {
	const events = parent.session.events
	const lastEnd = events.findLast(e => e.type === 'turn/end')
	if (lastEnd === undefined) return []
	return events.slice(0, lastEnd.seq + 1)
}

class ForkInProcessProvider implements SubagentProvider {
	readonly capabilities: SubagentCapabilities = { outputSchema: true, depthLimit: true, toolFilter: true, persona: true }
	readonly inheritsParentContext = true
	start(request: ResolvedSubagentStartRequest) {
		const seed = completedTurnPrefix(request.parent)
		return startInProcessRun(request, { ...(seed.length > 0 ? { seed } : {}) })
	}
}
```

`completedTurnPrefix` 只截取父会话**已经完成的对话轮次**(找到最后一个 `turn/end` 事件为止),而不是把当前这个还在进行、工具调用还没配对完的轮次也塞进去——一个未完成的轮次(比如模型刚发起了工具调用但结果还没回来)直接塞给子代理会导致上下文里出现"悬空"的工具调用,子代理看不懂。

`subagent-spawn-in-process` 几乎是同一份代码,唯一区别是不传种子:

```typescript
class SpawnInProcessProvider implements SubagentProvider {
	readonly capabilities: SubagentCapabilities = { outputSchema: true, depthLimit: true, toolFilter: true, persona: true }
	readonly inheritsParentContext = false
	start(request: ResolvedSubagentStartRequest) {
		return startInProcessRun(request, {})
	}
}
```

而 `startInProcessRun` 这个共享函数本身,住在第三个包 `subagent-in-process-driver` 里——**这个包本身不注册任何 `SubagentProvider`**,它只导出一个函数。模块文档写得很直白:"深度解析、子代理创建、可选的子代理定制、结果读取、取消、清理——这些逻辑只在这里实现一次;fork 只是多传了父会话已完成的对话前缀。" 这是一个典型的"两个薄 Provider 共享一个厚驱动"的结构:避免 fork/spawn 在深度校验、结果读取、资源清理这些容易出错的细节上各写一份还可能出现行为漂移。

外部进程类的三个 Provider,机制各不相同但目标一致——把"外部产品的子进程"伪装成一个符合 `SubagentProvider` 契约的子代理:

`subagent-acp` 用官方 ACP SDK 在子进程的 stdio 上跑 ND-JSON:

```typescript
// packages/subagent/subagent-acp/src/index.ts(节选)
const conn = new ClientSideConnection(
	makeClient,
	ndJsonStream(
		NodeWritable.toWeb(child.stdin) as WritableStream<Uint8Array>,
		NodeReadable.toWeb(child.stdout) as ReadableStream<Uint8Array>,
	),
)
await conn.initialize({ protocolVersion: PROTOCOL_VERSION, clientCapabilities: {} })
const session = await conn.newSession({ cwd: spec.cwd, mcpServers: [] })
const promptResult = await conn.prompt({ sessionId: remoteSessionId, prompt: toAcpPrompt(request.prompt) })
```

`subagent-claude-code` 没有自己拼协议,而是复用官方 SDK 的 `query()`,但把 SDK 内部"怎么拉起子进程"这一步接到了 dsh 自己统一的子进程管理服务上:

```typescript
// packages/subagent/subagent-claude-code/src/run.ts(节选)
query = officialQuery({
	prompt,
	options: claudeQueryOptions(spec, controller, (captured) => { child = captured }),
})
// claudeQueryOptions() 里:
spawnClaudeCodeProcess: (options: SpawnOptions) => {
	const child = spec.spawn(claudeSpawnSpec(options, spec.disposeGraceMs))
	capture(child)
	return new ManagedClaudeCodeProcess(child)
},
```

这样一来,真实的 `claude` 进程虽然是 SDK 帮忧拉起来的,但它的生命周期(环境变量清理、进程树级联清理)统一纳入了 dsh 自己的子进程管理体系,不会因为用了外部 SDK 就绕开 dsh 的资源治理。

`subagent-codex` 则完全没有现成 SDK 可用,是手写的一套 JSON-RPC 客户端,拉起 `codex app-server --stdio` 之后走 `initialize → initialized → thread/start → turn/start → 等待 turn/completed`:

```typescript
// packages/subagent/subagent-codex/src/wire.ts(节选,CodexAppServerWire.runTurn())
const response = object(await this.guarded(this.transport.request('turn/start', {
	threadId,
	input: texts.map(text => ({ type: 'text', text, text_elements: [] })),
}, signal), signal), 'turn/start response')
```

`subagent-dsh-sdk` 最特别——它拉起的不是别的产品,而是**另一整套完整的 dsh harness**(自己的 `cordis.yml`、自己的模型路由、自己的工具集、自己的会话持久化),通过 dsh 自己的 SDK 客户端驱动:

```typescript
// packages/subagent/subagent-dsh-sdk/src/run.ts(节选)
const harness = new DeepSeekHarness({
	launch: { command: spec.command, args: spec.args, cwd: spec.cwd, env: {...}, shutdownTimeoutMs, disposeEofGraceMs, disposeGraceMs },
	cwd: spec.cwd, provider: spec.provider, model: spec.model,
})
await harness.start()
const turn = await harness.session(childSessionId).run(request.prompt, { onNotification: observe })
```

这与包装外部 CLI 的三个 Provider 有本质区别:那三个是"驾驶一辆别人造的车",这个是"造一辆完全独立、可能配置迥异的新车,让它自己跑"——子 harness 有自己决定的组合、自己的会话持久化、自己的模型路由,完全是一个对等的独立个体,只是它的启停被父进程当作子代理来管理。这六个外部/递归 Provider 无一例外都声明 `depthLimit: false`——它们的深度预算(如果有)由自己那套系统内部管理,dsh 父进程管不到、也不假装能管到。

### `tool-subagent`:委派工具的完整执行流程

模型真正调用的委派工具是 `packages/subagent/tool-subagent/src/index.ts`。有一个反直觉但很关键的设计:**模型在调用这个工具时,既不能选 Provider,也不能选"要不要 fork 历史"**——这些都是部署方在工具配置(`Config`)里锁定好的:

```typescript
// packages/subagent/tool-subagent/src/index.ts:29-79(节选)
interface Config {
	provider: string
	toolName?: string           // 默认 'subagent'
	enableRunInBackground?: boolean  // 默认 true
	backgroundMode?: 'one-shot' | 'continuable'  // 默认 'one-shot'
	agentOptions?: unknown
	persona?: unknown
	toolFilter?: { allow?: string[]; deny?: string[] }
	maxDepth?: number | 'provider-managed'   // 默认 3
}
```

模型侧看到的参数只有 `description`(3~5 词的一句话描述,用于展示)、`prompt`(完整、自包含的任务描述——因为子代理很可能什么上下文都没有,任务描述必须把话说全),以及在 `enableRunInBackground` 开启时的可选 `run_in_background` 布尔值。一个部署可以同时挂载这个工具的多个实例,分别绑定不同 Provider(比如 `subagent`/`subagent_codex`/`subagent_claude_code`),模型看到的是几个名字不同、职责各异的委派工具,而不是一个带"选择 Provider"参数的万能工具——这样可以避免模型因为参数组合过多而"选错搭配"。

`execute()` 的调度逻辑会依据"续接模式"和"要不要后台"走三条完全不同的路径:

- **可续接 + 后台**(`ctx.subagents.startContinuable(...)`)——立即返回 `{ kind: 'continuable', subagentId }`,**不等子代理跑完这一轮**,后续通过 `send_message`/`interrupt_agent`/`list_agents` 去操控它。
- **一次性 + 后台**——包成一个 `ctx.jobs` 任务,异步跑,父代理可以先干别的,之后再来查任务状态。
- **前台(one-shot 的默认行为)**——直接 `await ctx.subagents.start(...)`,父代理这一步工具调用就会一直挂起,直到子代理跑完。

前台路径的收尾逻辑值得单独看一下,因为它体现了"无论成功失败都要清理资源"的原则:

```typescript
// packages/subagent/tool-subagent/src/index.ts(节选,settleForegroundRun 的逻辑)
async function settleForegroundRun(run: SubagentRun) {
	try {
		const result = await run.result
		if (result.stopReason !== 'completed') {
			throw stopReasonError(result)   // 非 completed 统一转成 Error,保留部分输出文本
		}
		return { content: toolResultFrom(result.output) }
	} finally {
		await run.dispose()   // 无论成功/失败,都必须释放
	}
}
```

不管子代理是正常结束、被中止、还是因为超出 token 上限被截断,`stopReasonError()` 都会把它转成一个统一的错误,而 `run.dispose()` 永远在 `finally` 里执行——这与第一篇讲工具调用机制时"任何异常都要转换成正常的 `ToolResultMessage` 反馈给模型"是同一条设计哲学的延伸。

### 父子双向通信:三条独立信道

父子代理之间的通信被拆成了三条**故意分开**的信道,而不是合并成一条"消息总线"。理解这个拆分,是理解整套委派模型的关键。

**信道一:父 → 子的主动控制,`tool-subagent-control`。** 这个包里其实注册了三个独立的工具(而不是一个带 `action` 参数的调度工具):`send_message`、`interrupt_agent`、`list_agents`。

`send_message`(`packages/subagent/tool-subagent-control/src/index.ts`)把消息投递给指定子代理,作为它的**下一轮**输入,而不会打断它正在跑的这一轮:

```typescript
// packages/subagent/tool-subagent-control/src/index.ts(节选)
async function sendMessage(ctx: Context, parent: Agent, args: { subagent_id: string; message: string }, signal?: AbortSignal) {
	const messageId = await ctx.subagents.followup(
		parent,
		SessionId(args.subagent_id),
		args.message,
		{ source: { kind: 'coordinator', form: 'relay', senderSessionId: parent.id }, signal },
	)
	return { messageId }
}
```

`interrupt_agent` 则是真正的"打断"——目标不仅限于直接子代理,也可以是更深一层的子孙代理:

```typescript
// packages/subagent/tool-subagent-control/src/index.ts(节选)
async function interruptAgent(ctx: Context, caller: Agent, args: { agent_id: string }, signal?: AbortSignal) {
	ctx.subagents.interrupt(SessionId(args.agent_id), { kind: 'ancestor', agent: caller })
	return { accepted: true }
}
```

`list_agents`(独立文件 `packages/subagent/tool-subagent-control/src/list-agents.ts`)支持 `scope: 'children' | 'descendants'` 两档,**只列出可续接的子代理**——一次性子代理跑完就没了,模型压根不会去选它们:

```typescript
// packages/subagent/tool-subagent-control/src/list-agents.ts(节选)
function statusOf(agents: { get(id: SessionId): Agent | undefined }, id: SessionId): 'running' | 'idle' | 'ready' {
	const agent = agents.get(id)
	if (agent === undefined) return 'ready'
	return agent.status === 'running' ? 'running' : 'idle'
}
```

三个工具通过纯字符串 `SessionId` 定位目标,授权检查全部下沉到 `SubagentContinuationManager` 内部的血缘校验逻辑,而不是每个工具各自维护一份"谁能操作谁"的白名单。

**信道二:子 → 父的自愿汇报,`tool-subagent-report`。** 这个工具最有意思的地方不是它的逻辑(`execute()` 只是简单转发 `ctx.subagents.reportFrom(...)`),而是它的**可见性范围**——它只应该出现在子代理的工具列表里,顶层会话、一次性子代理、外部远程子代理统统看不到它。源码的模块文档写得很明确:

> "The child-scoped `report` tool and its usage guidance, installed into every continuable in-process child's unpublished context. **Roots, one-shot children, remote providers, and agentless executions never see the registration.**"

实现这种"仅子级可见"的机制,不是靠在工具内部判断 `if (session.header.origin === 'subagent')`,而是靠一个更彻底的注册时机控制——`ctx.subagents.registerContinuableSetup(...)`:

```typescript
// packages/subagent/tool-subagent-report/src/index.ts(节选)
export function apply(ctx: Context, config: Config = {}): void {
	const { reportDelivery } = Config(config)
	ctx.subagents.registerContinuableSetup(childCtx =>
		installReportTool(childCtx, ctx, reportDelivery))
}
```

`registerContinuableSetup` 注册的回调,只会在 `SubagentContinuationManager` 真正创建一个**可续接的同进程子代理**时,才会被调用一次,拿到的 `childCtx` 是那个子代理专属、全新的 Cordis 作用域。一次性子代理的创建路径根本不经过这个注册表;外部 Provider(ACP/Claude Code/Codex/dsh-sdk)的子代理更是完全在另一套进程里运行,天然碰不到这段代码。所以 `report` 工具的"仅子级可见"不是运行时判断出来的,而是**从作用域层面就没有被注册进去**——这是一种更彻底、更不容易被绕过的隔离方式。

`report` 工具本身很短:一个必填的 `output: string` 参数,`execute()` 里调用 `ctx.subagents.reportFrom(exec.agent, [{type:'text', text: args.output}], { delivery, signal })`。`delivery` 是部署方配置好的 `'quiet' | 'wakeup'`(默认 `wakeup`)——决定这条汇报是悄悄塞进父会话历史,还是主动唤醒正在等待的父代理。特别要注意:**调用 `report` 不会结束子代理当前这一轮**,汇报只是"顺手说一句",子代理接下来还能继续干活。

**信道三:运行时 → 父的强制结算通知。** 这条信道不由子代理的意愿决定——当一个可续接子代理的 Activation(运行实例)结算(settle)时,`SubagentContinuationManager` 会**无条件**通知父代理它是怎么结束的,而这条通知在源码语义里被标记为一种和 `report` **不同的消息来源**(`subagent-settled` 而非 `subagent-report`)。这个区分是故意的:*绝不能让会话记录看起来像是子代理自己说了某句话,而那句话其实是运行时代它说的*。结算通知还有一个时序保证——必须在父代理被判定为"已释放"之前送达,否则会出现父代理提前认为"这个子代理不用管了",而结算通知实际还堆在收件箱里没被读到的竞态。

把三条信道放在一起看:`send_message` 是父方主动、单向、排队式的控制;`report` 是子方自愿、单向、可静默或唤醒的汇报;结算通知是运行时强制、单向、绝不会漏发的兜底。三者共用同一套底层的消息投递机制,却被明确赋予了不同的语义标签,这样父代理在回放会话历史时,永远能分清楚"这句话是子代理自己说的""这句话是运行时替它说的"。

### 权限作用域:委派不能被用来越权

子代理的权限不是"继承父代理当前的权限设置",而是在委派发起的那一刻被**永久固定**下来,之后无法从子代理内部再放宽。这一点通过在每个同进程子代理的系统提示里注入一段固定文案来强制模型知晓边界:

> "You are a delegated subagent: your permission scope was fixed when you were started and cannot be widened from inside this session — operations that require approval are rejected automatically..."

配合"每个子代理只会认识一个全新的、扁平的注册作用域"——子代理不会自动继承父代理注册过的服务或者放宽过的沙箱例外,只会继承(a)对话历史(仅 fork,且仅限已完成轮次)和(b)父代理所在的 Agent Preset 组合出来的工具集。上下文、工具、权限这三个维度各管各的、互不含混,是理解"子代理到底看得到什么、能做什么"时最容易被忽略、却最值得记住的一条设计线。

## 小结与思考题

委派链路可以归纳为:**模型调用 `tool-subagent` → 工具按部署配置选定 Provider → `SubagentProvider.start()` 用六种机制之一建立子代理,写入 `delegationDepth`/`parentSession`/`origin` 血缘记录 → 子代理在被永久固定的权限范围内运行 → 通过三条独立信道(控制/汇报/结算通知)与父代理交互 → 结果或错误统一封装回父代理的工具结果**。深度预算靠"持久化下限 + 运行时只能追加"防止被重启/续接绕开;`report` 工具的可见性靠注册时机而非运行时判断来保证隔离,这两处都是"用结构性约束替代运行时检查"的例子。

思考题:

1. 如果你要新增一个 `subagent-docker` Provider(在隔离容器里跑一个完全独立的编码环境),按照 `SubagentProvider` 契约,你至少要实现哪个方法?`inheritsParentContext` 应该填 `true` 还是 `false`?`capabilities.depthLimit` 呢——容器内部还能不能继续无限委派下去,这件事该由谁来保证?
2. `report` 工具用"注册时机"而不是"运行时判断 `origin` 字段"来实现可见性隔离,这比一个简单的 `if` 判断多绕了一层。这种做法在安全性上比运行时判断多提供了什么保证?你能想到运行时判断可能被绕过的场景吗?
