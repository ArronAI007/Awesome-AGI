# 插件架构对比精讲:Hermes vs Pi vs OpenCode

> 2026 年 7 月,Hermes 团队为了给自己正在设计的插件事件总线、流式 hook、审批机制找参照,做了一次源码级的调研:把 Pi(`earendil-works/pi`,就是姊妹课程"PI"讲的那个 TypeScript coding agent)和 OpenCode(`anomalyco/opencode`)的插件系统整个读了一遍,钉在具体的 commit 和 file:line 上,产出了一份题为《Research spike: plugin-architecture lessons from Pi and OpenCode》的 RFC(`docs/rfcs/2026-07-plugin-architecture-lessons-pi-opencode.md`)。这份 RFC 最后给出了 13 条"Adopt / Adapt / Avoid"结论,每一条都标注了要影响哪个后续 issue、引用了哪一行源码。本篇把这 13 条结论逐条摊开精讲,并且尽可能对照上一篇读过的 `hermes_cli/plugins.py` 现有实现——你会发现相当一部分结论已经不是"计划怎么做",而是已经写进了代码里的既成事实。如果你学过 PI 课程的《扩展 Extension 开发指南》,读到 Pi 那一半时会有强烈的"原来这里是这么权衡的"既视感。

## 学习目标

- 理解这份 RFC 的调研方法论:为什么它坚持"钉在具体 commit 和 file:line"而不是泛泛而谈两个项目的插件设计理念。
- 逐条讲清楚 13 条 Adopt/Adapt/Avoid 结论各自的原文措辞、证据来源,以及 Hermes 现有代码里对应的落地情况。
- 能用 Pi 的 `ExtensionAPI`/`pi.on()` 体系和 Hermes 的 `PluginContext`/`register_hook()` 体系做逐点对照,说清楚"类型化返回值"和"veto-by-throw"两种失败语义的根本区别。
- 理解"guard hook 必须 fail-closed"这条结论在 Hermes 里是如何具体实现的(`resolve_pre_tool_block()` 的 `approve` 分支)。
- 知道 Hermes 的命名空间化事件总线(`ctx.emit`/`ctx.subscribe`)相比 Pi 的 33 行裸事件总线多做了哪三件事。
- 能填出文末的 Pi/OpenCode/Hermes 三方对比表,并且能为表里每一格说出理由,而不是死记结论。

## 调研方法论:为什么要钉 file:line

这份 RFC 开篇就交代了方法:两个系统都是"源码级通读、钉定 commit",不是从文档站看一眼摘要:

```text
# docs/rfcs/2026-07-plugin-architecture-lessons-pi-opencode.md:5
Both systems were read at source level (shallow clones pinned to a commit),
not from docs sites alone: Pi (`badlogic/pi-mono`, now `earendil-works/pi`)
at `eb79351` (v0.80.7, 2026-07-14) and OpenCode (`sst/opencode`, now
`anomalyco/opencode`) at `c69abee` (v1.18.2, 2026-07-16). Claims below carry
file:line references into those commits.
```

这不是一份"调研两个同行怎么做插件"的泛泛报告,而是带着 Hermes 自己已经开了的四个 issue(事件总线 #64164、流式 hook #64161、可插拔审批 #64162、manifest v2 #64165)去找证据支撑或推翻的针对性调研,并且明确声明 Hermes 已有的四条"地基规则"(#64182:additive-only、prompt-cache sacred、observer-first、fail-closed security)是凌驾在一切之上的约束——调研结果要用这四条规则去打分,而不是简单地"抄一个更成熟的实现"。

RFC 开篇给出一张四维对照表,把整篇报告的立场浓缩成一句话:Pi 和 OpenCode 在 Hermes 当时悬而未决的四个设计轴上几乎是"近乎完美的反面",这恰好构成了一次天然的对照实验:

```text
# docs/rfcs/2026-07-plugin-architecture-lessons-pi-opencode.md:9-14(节选)
| Axis | Pi | OpenCode | Hermes proposal on the table |
|---|---|---|---|
| Per-delta streaming hook | Yes — awaited inline, no timeout | Structurally absent (text-end only) | Observer per-delta + never-block contract (#64161) |
| Veto semantics | Typed per-event result vocabulary | Veto-by-throw (bug ≡ policy denial) | TBD in #64162 |
| Guard-hook failure | Fail closed (`tool_call` only) | No runtime containment at all | Ground rule 4: fail closed |
| Plugin event bus | Yes — 33 lines, un-namespaced | None (plugins observe core bus, cannot emit) | Namespaced ctx.emit/subscribe (#64164) |
```

“两个系统都没做 hook 超时、都因此吃过挂起类故障”——这是 RFC 认定的整篇报告里最强的一条跨系统教训,后面第 4 条结论专门展开。

## 先补两条背景:Pi 和 OpenCode 各自的插件模型速写

如果你已经读过 PI 课程的《扩展 Extension 开发指南》,这一节可以快速带过——它对应你已经熟悉的 `ExtensionAPI`/`pi.on()`/`pi.registerTool()` 体系。这里只强调 RFC 额外挖出来的、教学文档里不一定会讲的几个关键事实:

**Pi**:扩展是进程内 TypeScript 模块(用 jiti 加载),没有独立进程、没有 IPC、没有清单权限声明——这与 Hermes"目录 + `plugin.yaml` 清单"的模型形成第一层对比。RFC 特别指出一个有意思的历史反转:Pi 2025 年 11 月立项时的口号是"minimal, no hooks",七个月后(2026 年 7 月)已经演化出 33 种事件类型的扩展系统——"可扩展性的需求赢了,但拒绝 MCP 作为扩展机制的立场没有变"。33 个事件类型定义在 `src/core/extensions/types.ts:507-902`,最核心的设计选择是"每一种会改变行为的事件都有自己专属的类型化 emitter 和结果词汇表",而不是一根通用的中间件管道——这正是你在 PI 课程里读到的 `tool_call` 返回 `{block, reason}`、`session_before_*` 返回 `{cancel}`、`input` 返回 `"handled"`/`"transform"` 这套"每个事件一种返回形状"设计的源头。

**OpenCode**:插件是一个异步工厂返回的单一 `Hooks` 包(`packages/plugin/src/index.ts:74`),大约 16 个"mutate `(input, output)`"型 hook,加上工具/认证/provider 这类声明式注册表,再加一个单一的"firehose"事件观察者。整个派发引擎只有 13 行代码,顺序执行、后 hook 能看到前 hook 的修改。RFC 标注了 OpenCode 一个至今开着的真实缺陷:`permission.ask` 是唯一带真正决策语义的 hook,但一次权限子系统重写之后,它在代码树里**没有任何派发点**——类型还在编译、插件还在被动无操作,这个问题从 2026 年 1 月开到调研时仍未修复(oc#7006)。这是整篇 RFC 里最尖锐的一个失败案例,也是第 3 条结论的直接证据。

## 13 条 Adopt / Adapt / Avoid 逐条精讲

RFC 用"Adopt / Adapt / Avoid"三档给每条结论评级,并且在开篇说明了评分基准:"'Validated' 意味着 Hermes issue 上原本就挂着的提案,被这次调研独立证实了"。以下按 RFC 原文顺序逐条展开(原表格共 13 行,序号与原文一致)。

### 1. 类型化的 per-hook 返回值词汇表,而不是 veto-by-throw —— **Adopt**

Pi 用 `{block, reason}`/`{cancel}`/`"handled"` 这类枚举式返回值表达"这次调用被谁、以什么理由拦下了";OpenCode 的文档化idiom 却是直接 `throw new Error("Do not read .env files")`——策略性拒绝和插件自身的 bug 在下游消费者眼里长得一模一样,再加上前面提到的 `permission.ask` 死路由,这条证据链非常完整。

Hermes 现有实现已经是这条结论的产物:`hermes_cli/plugins.py` 里 `pre_tool_call` 的决议不是让插件 `raise` 一个异常,而是走一个专门的 `_PreToolCallDirective` 类型,`resolve_pre_tool_block()` 明确区分 `action == "block"` 和 `action == "approve"` 两种语义(`hermes_cli/plugins.py:6736` 起),而不是"抛出异常就等于拒绝"。

### 2. Guard hook 必须 fail-closed,observer hook 可以 fail-open —— **Adopt(已验证)**

Pi 对每个 handler 的异常都做了 try/catch 并展示出来,**唯一的例外**是 `tool_call`——它的 crash 不会被吞掉,而是直接把这次工具调用判定为失败("Extension failed, blocking execution"),转成一条模型可见的错误结果,agent loop 本身继续存活。RFC 把这一点称为"对 Hermes 第 4 条地基规则的独立验证",并进一步精炼了这条规则:**一个崩溃的安全类 hook 本身也必须是 fail-closed 的,不能只是"配置默认值是 fail-closed"**。

Hermes 的 `_resolve_block_from_details()` 把这条精炼版规则写进了注释里:

```python
# hermes_cli/plugins.py:6771-6779(节选)
"""
Shared by :func:`resolve_pre_tool_block` and
:func:`_dispatch_pre_tool_call_hooks` so the security-critical
fail-closed approval logic lives in exactly ONE place: ``block``
blocks with its message; an ``approve`` directive whose gate errors,
denies, or times out is fail-closed to a block; anything else
proceeds.
"""
```

`approve` 分支的实现:审批网关本身抛错、拒绝、或超时,统统落到同一个 `return f"BLOCKED: ..."`——"gate 出错"和"gate 明确拒绝"在最终效果上被刻意做成了一回事,这正是 Pi 案例教会 Hermes 的那句话的字面翻译。

### 3. Hook 声明和实际派发点之间的"接线漂移"是最致命的一类 bug,需要 CI 检查 —— **Adopt now**

`permission.ask` 的教训被总结成一条可以立刻低成本落地的规则:任何声明过的 hook 名字,都必须能在代码里找到真正调用它的派发点,否则类型编译通过、插件静默空转,这个问题可能潜伏六个月以上都不会被任何人发现。RFC 特别提到 Hermes 自己已经存在这个风险的土壤:`register_hook()` 对未知 hook 名字"只警告、照常存储",这是为了前向兼容——但同样的宽容策略如果反过来看,就是"一个被拼错或者已经废弃的 hook 名字不会让插件加载失败",而这恰恰是 OpenCode 踩坑的同一种土壤。RFC 建议的做法很朴素:写一个 `VALID_HOOKS` 与所有 `invoke_hook(` 调用点的一次性交叉检查测试,谁新增一个 hook 名字但忘了在核心循环里真正调用它,CI 立刻报警。

### 4. 插件回调的 deadline 预算——做第一个把这件事做对的框架 —— **Adopt(差异化优势)**

这是 RFC 认定的全篇最强跨系统教训:Pi 和 OpenCode **都没有**给运行时 hook 设置超时,**都**因此吃过挂起类故障——Pi 有过后台 handle 泄漏(pi#5687)、关闭排空(pi#5115)两次相关修复;OpenCode 的 v2 `PLAN.md` 里"Transform timeouts"被列进 *Deferred Decisions*,推迟了两轮都没有做。RFC 同时指出 OpenCode 自己的 TUI 卸载路径其实证明了这个机制完全可行——一个硬 5 秒的 dispose 预算,用定时器去竞速每一次清理调用。

Hermes 把这条结论直接落地成了生产代码,而不只是停在 RFC 页面上:

```python
# hermes_cli/plugins.py:398-403(节选)
# Timeout coverage is an allowlist for the agent-turn hot path, not every
# entry in VALID_HOOKS. The goal is to stop a hung Python plugin callback
# from wedging the conversation loop (#76821) without joining the worker
# (avoids the #6622 ThreadPoolExecutor shutdown hang).
```

`_HOOK_CALLBACK_TIMEOUT_SECS`(默认 30 秒、可配置、上限 600 秒)只覆盖"agent 回合热路径"上的一个白名单,`on_session_finalize`/`on_session_reset` 这类低频收尾钩子被有意排除——"fail-open 放弃"在那里可能丢失最后一次落盘的机会,这本身也是对"预算"这件事的又一层精细化:不是所有 hook 都该有超时,只有热路径上的才该有。

### 5. 逐 token 的流式 hook 只有在"非阻塞"是结构性保证而非文档约定时才靠谱 —— **Adapt**

这是全篇最像"受控实验"的一条:Pi 提供逐 delta 事件并且**内联同步等待**——一个慢的 observer 会拖慢可见的输出流,一个挂起的 observer 会直接冻结流;OpenCode 完全不提供逐 delta hook,文本类 hook 只在 `text-end` 触发一次——热路径绝对安全,但代价是 TTS 一类需要"边生成边处理"的场景完全无法实现。RFC 给出的中间路线是:Hermes 计划中的"永不阻塞契约 + 有界队列 helper"是正确方向,但**必须把这个有界队列做成唯一的消费路径**(参考 OpenCode 的 `SubscriberOverflowError` 丢弃队列去处理背压),而不是在一个原始同步回调旁边提供一个"可选的"便利队列。

对照上一篇读到的 `VALID_HOOKS`,`on_stream_delta` 的注释已经写明了这条结论的落地状态:

```python
# hermes_cli/plugins.py:176-179(节选)
# Streaming LLM output observer hooks. Fired asynchronously off the token
# path by agent.plugin_stream_hooks; callbacks observe immutable normalized
# text/lifecycle payloads and cannot transform the stream.
```

"asynchronously off the token path"——这正是"结构性非阻塞"而不是"文档写着不要阻塞",直接对应 RFC 给出的处方。

### 6. 命名空间化事件总线——比两个系统都领先一步,按其两个缺口去修 —— **Adopt own design(已验证)**

Pi 的 33 行事件总线(`src/core/event-bus.ts`)能用,但频道名字是任意字符串、没有命名空间、没有发现机制、没有冲突保护;OpenCode 干脆没有插件发事件的能力,只能被动观察一条重量级的核心事件总线(SQLite 持久化、按聚合序号、幂等重放、还有一个用丢弃队列实现背压的 `allBounded` 保护)。RFC 认为 Hermes 已经规划中的方案(`<plugin_key>:` 强制命名空间、保留 `hermes:` 前缀、建议性声明、递归上限、确定性订阅顺序)在两个系统身上都找不到反例,值得按自己的设计继续推进,同时把两个系统都做对的"per-callback 隔离"以及第 4 条的超时预算一起搬过来。

这条结论在当前代码里已经不是"计划"而是完全实现的机制,`ctx.emit()`/`ctx.subscribe()` 的文档字符串几乎是逐条对上了 RFC 的处方:

```python
# hermes_cli/plugins.py:3491-3510(节选)
"""Publish *event* to all subscribers; return the number invoked.

The event is delivered as ``<plugin_key>:<event>`` where ``plugin_key``
is FORCED to this plugin's own registry key... Passing an already-
namespaced name (anything containing ':', including 'hermes:x' or a
foreign 'other:x') is rejected with a ValueError — fail-closed. The
'hermes:' prefix is reserved for core.

Delivery is fire-and-forget through a host-owned, single-worker queue:
registration order is preserved, while a blocking subscriber cannot
stall the emitter. The queue has a bounded pending budget; a full
budget drops the new event with a warning. Each subscriber receives a
deep-copied payload and is isolated in its own try/except.
"""
```

递归上限也确实存在,而且带着明确的动机注释:

```python
# hermes_cli/plugins.py:592-599
HERMES_EVENT_NAMESPACE = "hermes"
# Max inter-plugin event dispatch recursion depth. A subscriber may itself
# call ``ctx.emit``; this bound stops mutually-emitting plugins from looping
# forever. When exceeded the over-deep emit is dropped (with a warning), not
# raised, so delivery always terminates cleanly.
_EVENT_EMIT_DEPTH_CAP = 8
_EVENT_PENDING_CAP = 64
```

强制命名空间(插件只能发布 `<自己的 key>:xxx`)、保留 `hermes:` 前缀、递归深度上限、有界队列丢弃策略——RFC 里点名的两个系统的缺口(Pi 缺命名空间、OpenCode 缺插件发事件能力)在这份实现里被同时补上了,而且各自都带着 fail-closed/丢弃而非报错的处理方式,呼应第 4、5 条一以贯之的"永不阻塞、永不无限增长"哲学。

### 7. 加载顺序作为唯一的优先级系统,配合每个注册表各自的确定性冲突策略 —— **Adopt**

Pi 的调度是"零配置、确定性",八个月里社区都没有对"优先级"提出过真实需求;冲突处理是按注册表各给一条明确规则:工具先到先得、命令重名自动加数字后缀、快捷键后到覆盖前到但带警告,外加一份 18 项的保留名黑名单——完全不需要真正的依赖解析。RFC 建议 Hermes 把加载顺序当成一份像 OpenCode `PLAN.md` 那样写清楚的规格,每个注册表挑一条 Pi 式的冲突规则,而不是去建一套依赖解析系统。

这里有一个值得留意的细节:Hermes **实际落地的比这条建议本身走得更远**。上一篇讲过,`resolve_plugin_load_order()` 用 `graphlib.TopologicalSorter` 基于清单里的 `requires_plugins` 字段做了一层真正的拓扑排序,而不是纯粹的"发现顺序即优先级"。这不完全是对第 7 条的字面照搬——更像是把"加载顺序为唯一优先级机制"和"允许插件声明可选依赖"这两件事做了融合:拓扑排序只解决"同一批发现结果内谁先谁后",缺失依赖不阻断加载(只警告),循环依赖退化回字母序——依然保留了 Pi 式"零配置、fail-safe 退化"的精神,只是多了一层"作者可以声明依赖"的表达力。

### 8. 宿主强制的兼容性门禁 + 书面弃用窗口,迁移工具优于 semver 仪式 —— **Adapt**

OpenCode 用"整体 lockstep 版本号 + 一道 `engines.opencode` 语义化版本门禁"这个形状是对的,但这道门禁是插件自己 opt-in 声明的,本地文件插件完全绕开它——而 `oc#26557` 那次"一个 patch 版本号直接删掉整个 `api.command.*` 命名空间、事后才补一个弃用 shim"的真实事故,说明"lockstep 版本号"如果没有配套政策,只是社会共识,不是机制强制。Pi 展示了互补的另一半:响亮的 Breaking Changes 变更日志段落 + 自动迁移(目录重命名、会话格式 v2→v3 自动升级)+ 移除前的别名 shim。RFC 的结论是:manifest v2 应该带一个**宿主端强制检查**的 `api_version` 范围,仓库里应该有一段书面的弃用政策。

上一篇讲过的 manifest v2 `api_version` 字段就是这条结论的落点——`_parse_manifest_v2_fields()` 把它解析成一个独立于 `manifest_version` 的插件 API 世代号,为"宿主检查、而非插件自证"这道门禁留出了字段位置。

### 9. 带自动追踪释放的作用域注册 + 用教学性错误"毒化"失效的上下文 —— **Adopt**

OpenCode 用一个 `Proxy` 包装的 keymap API,自动记录每个插件注册过什么,插件被禁用时能干净地批量撤销;Pi 的做法是相反方向:`pi#2860` 曾经因为一次会话管理重构,让"在 `ctx.newSession()` 之后调用捕获的旧 `pi.sendUserMessage()`"静默丢消息——修复方式不是让这个调用继续默默失败,而是让每一个失效的上下文 getter 在被访问时都抛出一段教学式的长篇错误,指向安全的 `withSession` 用法。RFC 认为这两者是同一个健壮生命周期故事的两半:自动追踪的撤销(避免遗漏清理)和显式失败得很吵的错误(避免静默的坏状态)。

Hermes 的 `PluginContext._track()`/所有权账本机制正对应前一半:每一次 `register_*` 成功调用都会在 `PluginManager` 的账本里登记一条可撤销记录,插件卸载时按逆序统一清理(上一篇已详细展开,第 09 章还会再深入讲这套账本的完整生命周期)。

### 10. Prompt-cache 稳定性作为 API 契约——Pi 证明了这是可以落地的 —— **Adopt(已验证)**

Pi 是调研到的**唯一**把"prompt 缓存稳定性"当成扩展 API 一部分正式对待的系统:扩展拿到的是结构化的 `systemPromptOptions` 而不是拼好的最终字符串;每请求的上下文变换操作在一份 `structuredClone` 上进行,原始会话历史永远不会被写坏;缓存友好的动态工具加载(v0.80.6,pi#6474)通过原生 provider 的 deferred loading 机制附加式激活工具,专门避免破坏 prompt 前缀缓存,并且文档里写明了"prompt 元数据变化可能引发二阶失效"这类容易被忽略的坑。RFC 把这条列为"对 Hermes 第 2 条地基规则(prompt-cache sacred)最强的一次验证",而且附带了一份可以直接抄的参考实现思路。

这也是 PI 课程读者最容易产生共鸣的一条:如果你读过《扩展 Extension 开发指南》里"Prompt 组装"相关的内容,会发现 Hermes 的 `register_system_prompt_section(id, content, position=, max_chars=)`——把内容"冻结进每个新会话的系统提示词"而不是运行时任意拼接——正是同一种"缓存稳定性优先于运行时灵活性"的设计立场的另一种实现路径。

### 11. 半吊子沙箱——两个系统出于同一个理由都拒绝了 —— **Adapt with eyes open**

Pi 的文档原话是"一个局部的进程内沙箱很容易被误解成一道安全边界"(`docs/security.md:33-35`),所以干脆不做,只在加载时做一次项目信任判断;OpenCode 同样是全权限运行插件,只做路径包含限制。RFC 的判断是:这在"插件作者约等于用户自己"的阶段是可行的,而 Hermes 更贴近的近期答案不是进程内隔离,而是一套 Skills-Hub 式的信任/扫描流水线。

`tools/plugin_guard.py` 就是这条结论的具体落地,而且模块 docstring 直接点名了灵感来源:

```python
# tools/plugin_guard.py:1-11(节选)
"""
Plugin Guard — Security scanner for externally-installed plugins.

Inspired by Claude Cowork's skill & plugin security scanning (announced
2026-08-06: third-party skills and plugins are automatically checked for
malicious content when someone uploads or edits them, returning pass /
warn / fail). Hermes already scans hub-installed *skills* via
``tools/skills_guard.py``; this module extends the same static-analysis
engine to ``hermes plugins install`` and ``hermes plugins update``, which
previously cloned and executed arbitrary Git repositories unscanned.
"""
```

值得一提的是这个扫描器的分寸感:插件"本来就该"读自己的 API key、调用带 key 的 HTTP 接口、spawn 子进程,这些行为不能直接套用 skill 的威胁模式当误报源;真正要拦的是访问别人的凭据目录(`~/.ssh`、`~/.aws`、`~/.hermes/.env`)、反弹 shell、破坏性命令、持久化机制、混淆执行、已知的外泄服务。这是"拒绝进程内隔离,转而用静态扫描 + 人工 PR 审核兜底"这条路线的一次具体、克制的实现。

### 12. 事件要先于 UI 和持久化到达插件;给插件可用的 client 能力做启动分阶段 —— **Adapt**

Pi 有一条明确的顺序保证:扩展比 UI、比会话持久化更早看到事件(`agent-session.ts:596-601`),这消灭了一整类竞态;OpenCode"插件即 API 客户端"的设计很优雅,但一个插件在自己初始化期间调用 SDK 客户端会直接把启动死锁(`oc#7741`)。RFC 的建议是:如果 Hermes 的 `ctx` 未来长出更像客户端的能力,应该给它们做"未就绪前不可用"式的启动分阶段。

### 13. 两个系统都没有 ADR,都因此付出了代价 —— **Keep + adapt**

Pi 完全没有 ADR 体系,设计理由散落在文档里的"footgun"小节、五千行的变更日志、作者博客和 issue 里;OpenCode 除了 v2 的 `PLAN.md` 之外同样没有 ADR 系统,部分 API 在 patch 版本里被删除,正是因为没有一份决策记录写着"不要这样做"。RFC 认为 Hermes 按 issue 写设计草案(就是 #64182 这种风格)已经领先两者,但应该再学一件事:OpenCode 的 `PLAN.md` 里最好的一部分是一段诚实的 **Deferred Decisions**(待定决策)章节,让"还没想清楚的问题"保持可见,而不是假装已经闭环。

这条结论本身带着一点自反的幽默感:这份 RFC 自己就是"两个系统都没有 ADR"这条教训催生出的产物——Hermes 显然把"调研报告本身写成一份可追溯、可引用 file:line 的决策记录"当成了实践这条结论的第一步。

## 三方对比表

| 维度 | Pi Extension | OpenCode Plugin | Hermes Plugin |
|---|---|---|---|
| Hook 类型 | 33 种事件,各自专属类型化返回值(`{block}`/`{cancel}`/`"handled"`) | 一个 `Hooks` 包,~16 个 `(input, output)` 型变更 hook + 单一 firehose 观察者 | `VALID_HOOKS` 三十余项,`pre_tool_call` 走专属 `_PreToolCallDirective`(`block`/`approve`),观察型 hook(如 `on_stream_delta`)返回值被忽略 |
| 失败/失败语义 | 除 `tool_call` 外全部 try/catch 隔离;`tool_call` 崩溃直接 fail-closed 拦截 | 无内部隔离,veto 靠 `throw`,策略拒绝与 bug 不可区分;`permission.ask` 曾整体失效超过半年 | `resolve_pre_tool_block()` 统一处理:`approve` 网关出错/拒绝/超时一律 fail-closed 到 block |
| 优先级机制 | 纯加载顺序 + 每注册表专属冲突规则(先到先得/加后缀/保留名黑名单),零配置 | 加载顺序(spec 化文档记录),v2 增加显式的插件/变换注册顺序 | 四段固定发现顺序(bundled→user→project→pip)+ 清单 `requires_plugins` 的可选拓扑排序(缺失依赖只警告、循环退化为字母序) |
| Hook/回调超时 | 无,遗留过挂起类故障(pi#5687/#5115) | 无,`PLAN.md` 两次将"Transform timeouts"列为待定 | `hook_callback_timeout`(默认 30s,上限 600s)覆盖 agent 回合热路径的白名单;`on_session_finalize` 等收尾钩子有意保持无界 |
| 插件间通信 | 33 行裸事件总线,任意字符串频道,无命名空间 | 无插件发事件能力,只能被动观察核心事件总线(SQLite 持久化 + 背压丢弃队列) | `ctx.emit`/`ctx.subscribe`:强制 `<plugin_key>:` 命名空间、`hermes:` 保留前缀、递归深度上限(8)、有界待处理队列(64,满则丢弃) |
| 版本兼容策略 | 无版本握手;靠"响亮变更日志 + 自动迁移 + 移除前别名 shim" | 整体 lockstep 版本号 + 插件可选 opt-in 的 `engines` 语义化版本门禁;曾在 patch 版本删 API(oc#26557) | Manifest v2 独立的 `api_version` 字段,预留宿主端强制检查;未知清单字段仅警告、永不拒绝加载 |
| 沙箱/隔离 | 无进程内沙箱(文档明确说明"半吊子沙箱容易被误认成安全边界"),仅项目信任门 | 无沙箱,仅路径包含限制 | 无进程内沙箱;`tools/plugin_guard.py` 做安装/更新时的静态安全扫描,分级 pass/warn/fail |
| 逐 token 流式 hook | 有,内联同步等待,可被慢/挂起的 observer 拖慢或冻结整条流 | 结构性缺失,文本 hook 仅在 `text-end` 触发一次 | `on_stream_delta` 等观察型 hook 由独立线程异步派发,"off the token path",结构上无法阻塞流 |

## 小结与思考题

这份 RFC 最耐人寻味的地方,不是它列出了 13 条"别人怎么做"的清单,而是它自始至终坚持"用 Hermes 自己已经定下的四条地基规则去打分"——同一份 Pi 证据,在"prompt-cache 契约"上被判定为 Adopt,在"半吊子沙箱"上却只能是 Adapt with eyes open,取舍标准从未偏离。更值得记住的是:读完 `hermes_cli/plugins.py` 现有代码,你会发现这 13 条结论里至少 6 条(guard hook fail-closed、hook 超时预算、命名空间化事件总线及其递归上限、manifest v2 的 `api_version`、所有权账本、静态安全扫描)已经不是纸面结论,而是带着具体行号和注释的现存实现——这份 RFC 不是一份束之高阁的研究报告,而是一份真正指导了后续代码的工程文档。

思考题:
1. RFC 第 7 条建议"加载顺序作为唯一优先级机制",但 Hermes 实际的 `resolve_plugin_load_order()` 引入了基于 `requires_plugins` 的拓扑排序。这是不是对 RFC 结论的偏离?结合"缺失依赖只警告、循环退化为字母序"的容错设计,说说这种"表达力更强但仍然 fail-safe"的折中好在哪里、又可能在什么场景下反而增加了心智负担。
2. 如果你要给 Hermes 的 `ctx.emit`/`ctx.subscribe` 写一份类似 Pi `docs/security.md` 那样坦诚的文档,你会把"半吊子沙箱"这条结论的取舍原话怎么翻译给插件作者听,才能既不吓退开发者、又讲清楚信任边界?
3. 对照 PI 课程《扩展 Extension 开发指南》里"扩展工厂可能在根本不会启动会话的调用中也被执行一次,所以不要在工厂函数体里直接启动后台资源"这条提醒,你觉得它对应 RFC 13 条结论里的哪一条(或者哪几条的组合)?Hermes 的 `spawn_task()`/`on_unload()` 机制是否已经覆盖了同样的风险?
