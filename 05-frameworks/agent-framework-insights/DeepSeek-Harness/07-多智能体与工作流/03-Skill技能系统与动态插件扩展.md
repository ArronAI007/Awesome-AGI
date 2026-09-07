# Skill 技能系统与动态插件扩展

> 一套技能库越丰富,越容易在不知不觉间把每个 skill 的完整说明全塞进 system prompt,喂给模型的 token 越滚越大。dsh 的 Skill 系统把这个问题拆成两层:一份轻量的"名字 + 一句话描述"目录随会话常驻,完整的操作说明只在模型明确点名要用某个 skill 时才被加载进来。本篇前半讲这套"按需展开上下文"的技能系统,后半讲一个走得更远的能力——`packages/extensions` 里的 Cordis 动态插件机制,模型可以在运行时自己写一段 JS、定义一个全新的 Cordis 插件挂载到宿主进程里,也就是所谓"自我扩展"。这个能力默认不随标准配置启用,本篇会把源码里能找到的风险边界原样摆出来。

## 学习目标

- 理解 `SkillProvider` 注册表如何把"列出候选(元数据)"和"加载正文(完整指令)"拆成两个方法,以及这个拆分如何天然支撑"目录常驻、正文按需加载"的设计。
- 读懂内置的 `skill-badge`(最小示例)和 `skill-filesystem`(真实的磁盘发现 + 文件监听引擎)两个 Provider 的实现差异。
- 弄清 `tool-skill` 工具如何把"模型可调用的加载动作"和"随会话注入的技能目录消息"分成两条独立路径,以及目录消息为什么要做摘要长度截断和内容摘要去重。
- 把 Skill 系统的"按需加载正文"与第四篇讲过的上下文压缩做类比,理解两者都是"控制喂给模型的上下文体量"的手段,只是压缩针对的是历史,按需加载针对的是待选知识。
- 理解 Cordis 动态插件扩展(`cordis_define`/`cordis_run`)的能力边界:model 写的插件代码到底能碰到什么、guard/sandbox 挡住了什么、又刻意没有挡住什么,以及这套能力为什么被隔离在一个非默认的 Agent Preset 里。

## 背景与设计动机

Skill 系统和 Cordis 动态插件系统表面上离得很远,但放在一起讲是因为它们回答的是同一个更大问题的两端:**一个 Agent 的能力边界,应该在启动时就固定死,还是可以在运行过程中动态调整?**

Skill 系统给出的答案是"温和版"的动态——技能的**内容**在运行时按需加载,但技能能做的事(读文件、生成徽章之类)早就被写成了静态的 Markdown 说明,模型只是"学会怎么用现有工具去完成一件事",并没有获得任何新的执行能力。Cordis 动态插件给出的是"彻底版"的动态——模型可以在运行时定义一段全新的、真正会被求值执行的 JavaScript,挂载成一个能访问宿主服务的插件,相当于给自己造了一件新工具。前者几乎没有额外的信任风险,后者的信任模型等价于给了 shell 访问权限——这也是为什么它被单独隔离在一个不常驻的预设里,而不是随手可用的默认能力。

## Skill 技能系统

### `SkillProvider`:元数据与正文分离的注册表

核心接口定义在 `packages/skill/skill/src/index.ts`:

```typescript
// packages/skill/skill/src/index.ts:247-268(节选)
/** Provider interface for one source of skills, such as local directories or a remote registry. */
export interface SkillProvider {
	/** Unique provider name in the `ctx.skills` registry. */
	readonly name: string
	list: (options: SkillLookupOptions) => Promise<readonly SkillCandidate[] | SkillProviderObservation>
	get: (candidate: SkillCandidate, options: SkillLookupOptions) => Promise<SkillDefinition | undefined>
}
```

`list()` 返回的是轻量候选——`SkillCandidate`/`SkillSummary` 只带 `name`/`description`/`whenToUse?`/`invocation`/`source`/`provider` 这些**元数据**字段,不含正文。`get()` 才会真正加载出带 `content: string`(完整 Markdown 正文)的 `SkillDefinition`。这个"先列候选、再按需取正文"的两段式设计,是整套按需加载机制成立的地基。

`SkillRegistry` 服务(`packages/skill/skill/src/index.ts`)在这之上再叠一层——它是一个"分层注册表",host 级的 Provider 加上每个 Agent Preset 自己的层,同名冲突时按固定优先级(`RUNTIME_RANK=250`、`BUNDLED_SKILL_RANK=600` 等,数值越小越优先)由最近的层胜出。`get()` 方法的实现特别值得注意——它**不缓存正文**,只缓存轻量候选映射:

```typescript
// packages/skill/skill/README.md 的设计原则(转述自源码行为)
// registry.get(name, options) 每次都会重新走 provider.get() 加载正文,
// 只有 list() 产出的候选集合会被缓存(默认上限 128 条)。
```

这个"正文永不缓存"的选择,直接服务于下一节要讲的 `skill-filesystem`——正文文件被人改了之后,下一次加载立刻拿到最新内容,不需要设计任何缓存失效/版本号机制。

### 内置 skill:`skill-badge` 与 `skill-filesystem`

`packages/skill/skill-badge/src/index.ts` 是一个极简示例,把"元数据/正文分离"体现得最清楚:

```typescript
// packages/skill/skill-badge/src/index.ts(节选)
const CANDIDATE: SkillCandidate = { name: 'dsh-badge', description: DESCRIPTION, /* ... */ }
const provider: SkillProvider = {
	name: PROVIDER_NAME,
	list: () => Promise.resolve([CANDIDATE]),   // 零 I/O,同步就能给
	async get(_candidate): Promise<SkillDefinition> {
		return { ...CANDIDATE, content: await readFile(SKILL_BODY_URL, 'utf8') }  // 正文这才去读
	},
}
```

`list()` 完全不碰磁盘,`get()` 才真正去读一次文件。这个 skill 的作用是教模型生成一个 "Built with DeepSeek Harness" 的项目徽章,**默认在标准 CLI 组合里是禁用的**——即便这么轻量的一个内置 skill,dsh 也不假设它应该默认出现在每个会话的目录里,而是要求部署方显式打开。

`packages/skill/skill-filesystem/src/index.ts` 则是真正干活的发现引擎——扫描 `<name>/SKILL.md` 这种技能包目录或者扁平的 `<name>.md` 文件,跨若干个按优先级排序的根目录查找,并且带一套基于 Chokidar(加上对不存在路径的轮询兜底)的文件监听器,能在技能文件被增删改时刷新目录。它的失效判定很有分寸——只有顶层技能包的增删,或者 `SKILL.md`/扁平 `.md` 文件本身的变化才会触发目录刷新,技能包内部 `references/`、`scripts/`、`assets/` 目录下的资源文件变化不会触发失效。这与"正文不缓存,每次现读"配合起来,形成了一条从磁盘到模型的短闭环:**目录变了才刷新目录,内容变了不用管缓存,因为压根没缓存内容**。

`skill-filesystem` 同时按优先级扫描五种根目录,数值越小优先级越高、同名冲突时更靠前的层胜出:

| 根目录种类 | 优先级(rank) |
|---|---|
| 项目级 `.dsh/skills` | 100 |
| 项目级 `.agents/skills`(与 `AGENTS.md` 生态兼容) | 200 |
| 自定义配置根 | 300 |
| 用户级 `~/.dsh/skills` | 400 |
| 用户级 `~/.agents/skills` | 500 |

对照前面提到的 `RUNTIME_RANK=250`(运行时动态注册的技能)和 `BUNDLED_SKILL_RANK=600`(随包自带的内置技能,如 `skill-badge`),可以看出整条优先级链条的设计意图:**项目级配置 > 运行时注册 > 用户级配置 > 内置默认**——一个项目自己放在 `.dsh/skills` 目录下的同名技能,永远能覆盖用户全局配置甚至内置技能,方便团队用项目内配置统一约束技能行为,而不用担心被某个用户的本地全局配置覆盖。

顺带一提两个容易被忽略的边界:技能可以在其元数据里标注 `disable-model-invocation: true`,这样它会从模型可见的目录里消失,但仍然可以被用户用 `/名字` 手势直接触发——也就是"人可以用,模型看不到、也调不了"这档中间状态;另外,整个 Skill 系统里**没有任何"版本号"字段**,同名冲突完全靠层级优先级和注册顺序决定谁生效,不存在语义化版本比对的机制。

### `tool-skill`:按需加载,而不是全部塞进 system prompt

模型真正用来加载技能正文的工具是 `packages/skill/tool-skill/src/index.ts`,它的参数极其简单——只要一个 `name`:

```typescript
// packages/skill/tool-skill/src/index.ts:82-92(节选)
{
	name: 'skill',
	description: 'Load the full instructions for an available skill. Call this with the exact skill name from the session skill catalog before acting on a task that names or clearly matches that skill.',
	parameters: {
		name: { type: 'string', required: true, description: 'The exact skill name from the available skills list.' },
	},
}
```

`execute()` 内部会同时查 `ctx.skills.list()` 和 `ctx.skills.get()`,这一步会透明地合并所有已注册 Provider、所有层级的结果,最终把完整正文作为工具结果的一部分返回给模型。

真正体现"按需加载"这个设计的,不是这个工具的 `description` 字段(那只是一句静态说明),而是一条**独立注入的目录消息**——它不是工具描述的一部分,是一条会话历史里的普通 `UserMessage`,由 `renderCatalogMessage()` 渲染:

```typescript
// packages/skill/tool-skill/src/index.ts:254-277
function renderCatalogMessage(entries: SkillCatalogSource['entries']): UserMessage {
	return createUserMessage({
		content: [{
			type: 'text',
			text: [
				'<system-reminder>',
				'A skill is a reusable set of task-specific instructions. The following skills are available in this session:',
				'',
				'<available_skills>',
				...renderCatalogEntries(entries),
				'</available_skills>',
				'',
				"If the user names a skill, or the task clearly matches a skill's description, call the `skill` tool with the exact skill name before taking task actions. Load all applicable skills, then follow their full instructions. This catalog contains summaries only; do not infer or follow a skill's instructions until it has been loaded.",
				'A user may also invoke a skill directly; its <skill_content> block then appears in this conversation. Follow it, and do not call the `skill` tool again for that skill.',
				'</system-reminder>',
			].join('\n'),
		}],
		source: { kind: 'skill-catalog', form: 'catalog', entries },
	})
}
```

每一条目录项只有"名字 + 一句话描述",而且这句描述本身还要过一次长度截断(默认上限 500 字符,可通过 `Config.catalogDescriptionMaxLength` 配置)——这是刻意压低"常驻"部分的 token 体量:目录本身要足够便宜,才值得让它一直待在上下文里;昂贵的完整正文只有真正要用到的那一个 skill 才会被加载进来,而且往往只加载一次。

这条目录消息也不是每一轮都重新发一遍——有一个 `agent/pre-step` 钩子会对当前候选集合算一次 SHA-256 摘要,只有摘要变化(比如新增/删除了一个 skill 文件)时才会重新发一条"替换版"目录消息,这个开销通常只在会话开始时付一次,不是逐轮重复的常态成本。

除了工具调用这条路径,还有一条更直接的旁路——用户在对话里直接打出 `/skill 名字` 这种手势,会被另一个 `agent/pre-step` 钩子的正则匹配捕获,直接把技能正文注入对话,完全不经过 `skill` 工具本身。

**与第四篇上下文压缩的类比**:上下文压缩解决的是"历史已经发生的对话太长,要不要把老的部分折叠成摘要";Skill 目录/正文的分离解决的是另一个方向的同一类问题——"待选的知识太多,要不要把还没用到的部分折叠成一句话描述"。两者的手法都是"先给一个廉价的摘要,真正需要细节时再展开完整内容",只是压缩作用于过去已发生的内容,按需加载作用于尚未被选中使用的内容。放在一起看,会发现 dsh 在"控制喂给模型的 token 预算"这件事上是有一套一致方法论的,而不是每个子系统各自发明一套。

一个值得记住的边界:**目录本身的 token 预算被压得很紧,但加载进来的 skill 正文长度目前没有任何上限**——这是工具自己文档里明确写出的已知局限,如果某个技能包的 `SKILL.md` 写得非常长,加载它带来的 token 成本目前完全由技能作者的自觉去控制,系统不会替你截断。

## 动态插件自举:Cordis 自我扩展能力

### `tool-cordis`:七件套自省与自举工具

`packages/extensions/tool-cordis/src/index.ts` 里注册了七个工具,名字都是 `cordis_` 前缀:

```typescript
// packages/extensions/tool-cordis/src/index.ts(工具名一览)
// cordis_inspect_list   — 列出当前动态挂载的插件
// cordis_inspect_query  — 查询某个插件/服务的细节
// cordis_inspect_self   — 自省当前会话自己的组合状态
// cordis_define         — 定义一个新插件(或更新已有插件)
// cordis_run            — 让某个已定义的插件在指定作用域挂载运行
// cordis_stop           — 停掉一个正在运行的插件
// cordis_undefine       — 删除一个插件定义
```

`cordis_define` 的输入是一个 `code: { host?: string, client?: string }` 字段——**这是一段纯 JavaScript 源码字符串**(一个隐式的 async 函数体),不是某种预先设计好的插件描述 JSON。这段代码求值后必须返回一个满足 Cordis "插件"形态的值,判定逻辑在 `cordis-host-runner/src/guard.ts`:

```typescript
// packages/extensions/cordis-host-runner/src/guard.ts:790-794
export function isPlugin(value: unknown): value is Plugin {
	if (typeof value === 'function') return true
	return typeof value === 'object' && value !== null
		&& typeof (value as { apply?: unknown }).apply === 'function'
}
```

也就是说,模型写的代码可以返回一个函数,或者一个带 `apply(ctx)` 方法的对象——这正是 Cordis 框架里普通静态插件的形态(`docs/cordis-primer.md` 里解释 Cordis 是"插件 = Service、Context = 服务仓库、`inject` 声明依赖"的元框架)。一段典型的模型写的插件正文大致是:

```javascript
// 摘自内置技能 cordis-plugin-development/SKILL.md 里给模型的示例
return {
	inject: ['requiredService'],
	apply(ctx) {
		ctx.requiredService.someMethod()
	},
}
```

换句话说,`cordis_define` + `cordis_run` 让模型可以在一次对话里,自己写一个 Cordis 插件、自己声明它要依赖哪些服务、自己把它挂到活的运行时上——这正是"动态插件自举"字面意义上的实现:插件不是部署时写死在 `cordis.yml` 里的,而是模型在运行期临时定义出来的。

### 沙箱与守卫:`guard.ts`/`sandbox.ts` 到底挡住了什么

`cordis-host-runner/src/sandbox.ts` 用 `node:vm` 给模型写的代码建了一个执行环境,但源码文档从一开始就明确否认了这是安全边界。真正挡住的是一组会诱导误用的 Node 全局量——不是删除,而是替换成"抛出教学性错误"的陷阱:

```typescript
// packages/extensions/cordis-host-runner/src/sandbox.ts:96-108(节选逻辑)
const NODE_API_REDIRECTS: Record<string, string> = {
	require: 'Node modules are unavailable. Use the cordis services on ctx instead...',
	setTimeout: TIMER_REDIRECT, setInterval: TIMER_REDIRECT, setImmediate: TIMER_REDIRECT,
	clearTimeout: TIMER_REDIRECT, clearInterval: TIMER_REDIRECT,
	fetch: 'Network access goes through the cordis web service...',
}
```

`process`/`Buffer` 这类更底层的对象则干脆留空(`undefined`),不做任何拦截包装。vm 的超时(`Config.vmTimeoutMs`,默认 5000ms)用的是 `node:vm` 自带的 `timeout` 选项——但文档特别提醒:一个异步函数体可以轻易绕开这个超时,这在这套机制的信任前提下是"可接受的",而不是被当作漏洞。

`guard.ts` 是另一层——一个白名单式的 `ctx` 访问代理,同样明确写着"不是安全边界"。它允许的 `ctx` 方法被限制在一个固定集合(`effect`/`on`/`once`/`provide`/`timeout`/`interval`/`setTimeout`/`setInterval`/`throttle`/`debounce`),未声明的服务读取会抛出带教学意味的错误,任何写操作一律被拒绝("sandbox ctx 是只读的")。其中一条反逃逸规则值得单独一提:**任何服务方法如果返回值本身是一个活的 Cordis `Context` 对象,会被直接拒绝**——这是专门防止"模型写的代码通过某个服务方法拿到一个未经代理的、完整权限的 Context 引用,从而绕开整套 guard"的路径。跨越这条边界传递的数据必须是无损的纯 JSON,类实例、函数、`Map`/`Set`、`Date`、嵌套 `undefined` 都会被明确拒绝并给出具体错误信息。

把这些机制放在一起看,`tool-cordis` 相关的四处不同源码位置(工具自身的提示词文案、`sandbox.ts`、浏览器端对应的 `client/guard.ts`、以及一份提案阶段的架构设计笔记)**都独立地写下了同一句话的不同表述**——"这是防误用的门槛,不是能挡住恶意代码的安全边界"。工具自身注入给模型的提示词原文:

> "The restricted execution environment prevents accidental misuse; it is not a security boundary for malicious code. Services obtained by dynamic code connect to the real runtime."

真正能拿到的能力边界,由插件自己声明的 `inject` 列表决定,而不是由沙箱去裁剪——一个插件完全可以声明依赖 `fs`/`bash`/`subprocess`/`pty`/`web` 这类具备真实主机权限的服务,一旦声明了依赖,拿到的就是真实的服务对象,不是阉割版。此外,动态定义的插件只存在于一个进程内内存态的 `Map` 里,没有任何持久化——进程重启,所有动态对象全部消失,这既是一种"爆炸半径受限"的天然保护,也意味着不能指望这套机制去做长期状态管理。

### `cordis-client-runner` 与 `ui-cordis`:浏览器侧的另一半,更弱的隔离

`cordis_define` 的 `code` 参数其实分 `host`/`client` 两份源码——`host` 那份跑在 Node 侧的 `cordis-host-runner` 里(上一节讲的 `vm` + `guard` 组合),`client` 那份则跑在浏览器页面里,由 `cordis-client-runner` 负责。`packages/extensions/cordis-client-runner/src/index.ts` 本身只是一个 9 行的空壳,真正的执行逻辑在浏览器端的 `client/*.ts` 文件里——因为浏览器环境里根本没有 `node:vm` 可用,它退而用 `new Function(...)` 构造函数来跑模型写的代码。这是一种**明显更弱**的隔离:`new Function` 构造出的代码仍然运行在同一个 JS 现实(realm)里,只是形参列表可以拿掉一部分自由变量的直接可见性,并不像 `vm.createContext` 那样有一个真正独立的全局对象。浏览器端的 `client/guard.ts` 对此毫不讳言:"这是 API 层面的自律,不是安全边界——一段动态包的代码,可信程度等同于接受了它定义请求的宿主进程本身。"

`packages/extensions/ui-cordis` 提供的是配套的人机交互外壳——一个"Cordis 面板",展示已定义的插件、提供审批/拒绝/运行/停止/移除的操作按钮,以及给工具调用卡片(`cordis_define`/`cordis_run`)配的可视化展示,还有一个 `@插件id` 的提及(mention)输入源方便在对话里引用某个已定义的插件。需要强调的是:这层 UI 只是"审批和观察动态插件"的外壳,并不是给动态插件本身提供渲染能力的框架——插件内部要不要有界面、界面长什么样,是插件自己 `client` 代码的事,`ui-cordis` 管的是"人怎么看见、怎么批准这件事在发生"。

浏览器端还有一层 Host 侧没有的强制人工关卡:**Client 代码的挂载需要经过人工点击审批,Host-only 的插件则不需要**——这意味着一个只声明 Host 依赖、不带任何 Client 代码的插件,可以在模型发起 `cordis_run` 工具调用的当下就同步跑起来,没有人工审批这一步。设计笔记里也把这一点列成了值得警惕的细节:双击确认审批一次之后,同一个插件后续的所有版本更新会被预授权,不再逐次询问——这是为了不让每次小改动都要求用户重新点一次确认,但也意味着审批粒度是"插件身份",不是"这一次具体改了什么代码"。

### 默认不启用:`cordis` 预设与 `standard` 预设的分野

这套自举能力不是随手可用的默认工具集,而是被隔离在一个专门的、非默认的 Agent Preset 里。`apps/cli/config/agent-presets/cordis/agent.cordis.yml` 的文件头部注释直接把风险模型写在了配置文件里:

```yaml
# The `cordis` agent preset: the standard coding agent, plus the ability to
# read and write the runtime it is running in.
#
# It exists so a person can ask an agent to author another agent. Everything in
# `standard` is here unchanged; what is added is the self-referential Cordis
# toolset, a skill that teaches composition authoring, and a persona that says
# which of the two planes an edit belongs to.
#
# TRUST: `cordis_mount` evaluates model-written JavaScript against the live
# runtime, and a composition this agent writes becomes a preset other sessions
# mount. Treat a session on this preset as shell access — the toolset's own
# documentation makes the same statement.
```

而系统级的默认预设 id 被硬编码为 `standard`(`packages/bundle/web-app/cordis.patch.yml` 里的 `default: standard`),`standard` 预设本身根本不引用 `tool-cordis`/`cordis-host-runner` 这些包——也就是说,一个普通会话从"标准编码 Agent"切换到"能自己写插件改造运行时的 Agent",必须由部署方或使用者显式切换到 `cordis` 这个预设,不存在任何默认路径会不知不觉打开这扇门。这与 Skill 系统里 `skill-badge` 默认关闭是同一种谨慎——但风险等级完全不是一个量级:`skill-badge` 关闭只是少一个生成徽章的技能,而 `cordis` 预设关闭意味着"默认情况下没有任何会话具备重写自己所在运行时的能力"。

文档层面(`docs/subsystems/extensions.md`/`.zh.md`)其实只是自动生成的 API 参考,没有展开讨论风险考量;`docs/cookbook/extension-cookbook.md` 覆盖的是普通的静态插件编写,同样没有涉及动态自举这个特性。真正的风险论述散落在源码注释、工具自身的提示词、以及一份仍处于"proposed"(尚未落地)状态的架构设计笔记里——这份笔记的原话是:"受限的执行环境不是安全沙箱……白名单和审批机制能降低误用,但不能隔离恶意代码。" 这一点值得如实告诉读者:**dsh 的正式文档目录(`docs/`)本身没有专门展开讨论这个特性的安全考量,风险边界需要读者自己去源码注释和提示词文案里拼出全貌**——本篇引用的四处"不是安全边界"的原话,就是这个拼图目前能找到的全部证据。

## 小结

Skill 系统和 Cordis 动态插件系统是同一条设计主线的两种强度:前者让模型"按需知道有哪些现成本领可用",本领本身是静态、无害的操作说明;后者让模型"按需给自己造一件新本领",新本领是真正会被执行的代码,拿到的是宿主服务的真实访问权限。`SkillProvider` 的 `list`/`get` 分离,以及 `tool-skill` 的目录消息与加载工具分离,构成了一套"廉价目录常驻、昂贵正文按需"的上下文预算控制手法,与上下文压缩是同一方法论在不同方向上的应用。Cordis 动态插件系统则老实地在四处不同的代码位置写明"这不是安全边界",把真实的能力边界交给 `inject` 声明去决定,并且用一个非默认的 Agent Preset 把这扇门锁在默认路径之外——文档本身没有展开的风险讨论,读者在真正启用这类自举能力之前需要自己把源码注释和提示词文案里的这几处声明当作唯一可信的风险说明。

思考题:

1. `tool-skill` 的目录消息用摘要(SHA-256 digest)去重来避免逐轮重发,而 skill 正文选择"完全不缓存、每次现读"。如果要新增一个允许远程 HTTP 拉取的 `SkillProvider`,你会给它的 `get()` 加缓存吗?加的话,怎么在"正文可能被远程更新"和"不希望每次加载都发一次网络请求"之间取舍?
2. `guard.ts` 里"任何返回值是活的 Context 对象就拒绝"这条反逃逸规则,和 `workflow-worker-thread` 里"跨线程边界的值必须是纯 JSON"的规则,本质上是同一类防御——不让"活的、有权限的对象"跨越一条本该受限的边界。如果你要给 Cordis 动态插件系统也加一层"遏制而非安全边界"的进程外隔离(类似第二篇提到的 `isolated-vm` 被放弃的方案),你觉得最难处理的是插件对宿主服务的"能力"访问,还是它返回值里可能夹带的"活对象引用"?
