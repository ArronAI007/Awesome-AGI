# AGENTS.md 治理规范与文档体系

> 根目录的 `AGENTS.md` 只有 149 行、约 1600 词的预算上限,却要管住一个有 56 个工作区、几十个能力 seam 的 monorepo。它做到这一点的方式不是罗列细则,而是把每一次真实踩过的坑压缩成一条一到三行的"站规"(standing order),并把展开的道理链接到别处。本篇选出其中四条最有代表性的规则,逐条讲清楚它们各自解决的真实工程问题,再往上看一层,理解 `docs/` 目录本身的分层治理设计。

## 学习目标

- 理解 `AGENTS.md` 在这个项目里的定位——不是风格指南,而是一份被 `CLAUDE.md` 符号链接、每次会话都会进入模型上下文的"站规",以及"预发布阶段"这一特殊立场对它的影响。
- 理解 **Registrations are effects** 这条规则如何用 Cordis 的副作用系统解决"插件被卸载/热重载后残留注册"的资源泄漏问题。
- 理解 **Model-visible ⟺ logged** 这句规范化表述背后的会话事件溯源设计,以及它和 `SESSION_FORMAT_VERSION`/`ignorable` 标记这套具体机制之间的关系。
- 理解 **Plugins, not loop changes** 如何把 `agent-loop` 保护成一个稀缺、必须经过审慎评审的核心契约,防止它被逐渐蚕食成一个不可测试的巨石。
- 理解 **Trust TypeScript at typed same-process boundaries** 划定的"运行时校验只花在真正的边界上"这条反直觉却合理的原则,以及它列出的具体边界清单意味着什么。
- 理解 `docs/AGENTS.md` 定义的文档分层 taxonomy 与"一个事实只有一个家"(one home per fact)原则,理解为什么一个规范文档体系本身也需要被治理。

## 背景与设计动机

`AGENTS.md` 开篇第一句就给出了整个项目的自我定位:"DeepSeek Harness is a plugin-based agent harness on vendored Cordis: **everything is a plugin**."——包括模型适配器、工具注册表、会话日志,乃至 agent loop 本身,都是可以从配置替换的插件。这种彻底的插件化架构带来一个治理难题:如果任何东西都可以被插件替换、任何贡献都可以来自任意一个包,那么"什么该做、什么不该做"就不能靠代码结构本身来约束,必须靠一份被所有贡献者(人类和 agent)都会读到的规范文档来兜底。

文件还有一节专门声明当前所处的阶段:

> **Remove this section at the first tagged release.** With no external consumers, prefer the correct foundation over compatibility shims: rename or repackage freely and update every reference together. Backends reject old on-disk formats. SQLite uses monotonic `SCHEMA_VERSION`; `dsh-session` keeps `SESSION_FORMAT_VERSION` at `0` with no compatibility promise.
>
> —— `AGENTS.md`

这段"预发布立场"解释了为什么后面很多规则读起来偏向"激进求正确"而不是"保守求兼容"——因为目前没有外部消费者,任何格式、任何包名都可以在下一个 PR 里被重新设计,只要把所有引用一起改掉。这也解释了为什么规则里会出现"Backends reject old on-disk formats"这种在有外部用户的产品里几乎不可想象的表述:拒绝旧格式,而不是费力兼容它。理解这个前提,再看后面几条具体规则,会更容易理解它们为什么这样设计。

`docs/AGENTS.md` 给出的字数预算(root `AGENTS.md` ≤ 1,600 words)进一步说明了这份文件的性质:它不是可以无限增长的知识库,而是一份被严格限定篇幅的"必须留在每次会话上下文里的规则集合"。篇幅越紧,每一条规则背后压缩掉的血泪教训就越多——接下来四条规则,值得逐条把压缩掉的部分还原出来看。

## 核心机制详解

### Registrations are effects:用副作用系统管理注册的生命周期

`AGENTS.md` 的条款本身只有一行:

> **Registrations are effects**: every contribution goes through `ctx.effect()` / `ctx.on()`; a registry's `register()` returns the disposer.
>
> —— `AGENTS.md`

这条规则要解决的问题,是插件化架构里几乎必然会出现的一类 bug:如果一个插件往某个注册表(工具、事件监听器、适配器……)里塞了一份数据,却没有留下"怎么把这份数据撤销"的路径,那么这个插件被卸载或者热重载时,注册表里就会留下一份指向已经不存在的插件的孤儿数据——轻则表现为内存泄漏,重则表现为已卸载插件的行为继续"复活"影响新的会话。Cordis 对这个问题的通用解法就是"注册是可逆的副作用"这条原则,`docs/cordis-primer.zh.md` 把它讲得更具体:

> 注册是可逆的副作用。提示词片段、工具 schema、适配器、提供方和监听器通过 `ctx.effect()` 或 `ctx.on()` 安装,reload 和 teardown 时会按预期撤销。
>
> 每个注册都应有对应的 disposer(资源释放函数):要么从 `ctx.effect()` 返回一个,要么使用 Cordis 提供的辅助方法自动处理。如果 teardown 顺序有要求,请将相关工作放在同一个 effect 中,以确保资源按预期顺序释放。
>
> —— `docs/cordis-primer.zh.md`

这条规则不是抽象洁癖,而是一份可执行的契约:任何一个"贡献"(往工具表里加一个工具、往事件总线上挂一个监听器、往能力 seam 上注册一个 provider)都必须能通过某个 `dispose()` 调用被完全撤销,而不是靠人记住"这个插件被卸载时我需要手动清理什么"。这一契约还落到了测试层面——`docs/testing.md` 里提到"每个注册表都有一个 HMR 安全测试(对向该注册表贡献内容的 fiber 执行 dispose,并断言清理完成)",也就是说这条规则不是停留在文档里的口号,而是被一条机械可检查的测试规则强制执行的:任何注册表如果忘了正确处理卸载,都会在这项测试里暴露出来。

把这条规则放回"everything is a plugin"的整体设计里看,它的价值就更清楚了:一个 agent preset 可以按会话动态组装不同的能力集合、一个插件可以在开发时被反复热重载、一个 subagent 可以被创建又被销毁——如果注册不是可逆的副作用,这些动态组装能力全都会在实践中变得不安全,"卸载一个插件"就会变成一句谎言。

### Model-visible ⟺ logged:会话事件溯源设计的规范化表述

这是四条规则里读起来最抽象、但背后机制最具体的一条:

> **Model-visible ⟺ logged**: anything that reaches a model request must be reconstructable from the session log; a new model-visible input requires a session event.
>
> —— `AGENTS.md`

这条规则的完整版本写在 `docs/architecture.zh.md` 的"会话日志"一节里,措辞上更接近一句可以直接背下来的口号:

> **模型可见即已记录。** 抵达模型请求的一切都必须能从日志重建,并由一项运行时不变量断言这一点。因此,新增一项模型可见输入就需要新增一个会话事件:扩展 `SessionEventMap` 并从日志渲染。
>
> —— `docs/architecture.zh.md`

这条规则解决的问题是:一旦允许"某些影响了模型这次看到的上下文的东西,却没有被写进持久化日志",那么这个会话就再也无法被完整重放、fork、恢复或者用于遥测分析——因为日志里缺了一段模型实际"看见"过的内容,任何依赖"日志是模型上下文的唯一来源"这个前提的功能(fork、resume、transcript、telemetry)都会悄悄地和真实发生的事情不一致。规则用一个双向箭头(`⟺`)而不是单向箭头来表达这件事:不仅"日志里的东西模型能看见",反过来"模型能看见的东西必须在日志里"同样成立——少了任何一侧,这个等价关系就会破裂。

这条规则不是停留在原则层面,而是有一整套具体机制在背后强制执行它。`.agents/notes/implemented/architecture/2026-08-10-session-log-version-mechanism.md` 这份 Agent Note 记录了这套机制的设计决定,其中最直接对应"模型可见即已记录"这条规则的部分是:

> 逐事件的 `ignorable` 标记吸收词汇表增长,普通的新增事件永远不用升版本。事件词汇表由挂载了哪些插件决定,单个版本整数描述不了它。读取器遇到不认识的事件类型时拒绝解读日志,除非该事件的信封带 `ignorable: true`。默认为必需:忘写标记的后果是把一个本可恢复的会话拒绝过头(体验问题),而默认可忽略会让同样的疏忽静默恢复出残缺会话(安全事故)。架构保证了这条规则成立:模型可见内容只经三种带 `surfaceOp` 标记的 surface 事件加 `request/header`、`request/context` 折叠进入重建,危险的未知事件恰好是那些不进 surface 但改变日志其余部分解读方式的事件。
>
> —— `.agents/notes/implemented/architecture/2026-08-10-session-log-version-mechanism.zh.md`

这段话把"模型可见即已记录"从一句规范落实成了一个具体的默认值选择:遇到不认识的事件类型,读取器的默认行为是**拒绝**,而不是静默跳过。之所以默认拒绝而不是默认忽略,是因为这两种错误的代价完全不对称——多拒绝一次是"体验问题"(用户看到一条明确的报错,知道要升级 harness),而多忽略一次是"安全事故"(一个内容残缺的会话被静默地重建出来,用户完全不知道自己看到的历史是不完整的)。这也解释了为什么 `AGENTS.md` 里紧跟着这条规则的还有一句:"A `SessionEventMap` member is required-on-read by default … only structural format changes bump `SESSION_FORMAT_VERSION`"——版本号只在结构性变更时才递增,普通新增事件靠 `ignorable` 标记吸收,版本升级和"模型可见即已记录"这条不变量各自负责不同粒度的兼容性问题,不互相纠缠。

如果你在别处读到过这个项目里会话日志作为"重建模型历史的唯一权威来源"、fork/resume/遥测都是这份日志的投影这一整套事件溯源设计,那么"Model-visible ⟺ logged"这条规则,可以理解成是那套设计在 `AGENTS.md` 里被压缩成的一句可执行站规——它不重复讲机制本身是怎么实现的(这是 `docs/architecture.md` 和 `docs/subsystems/session.md` 的职责),只留下一句"新增模型可见输入,必须同时新增会话事件"的强制要求。

### Plugins, not loop changes:把 agent-loop 钉成一份稀缺契约

第三条规则同样只有一行,却对整个代码库的改动方式做出了一个强硬的默认限制:

> **Plugins, not loop changes**: new behavior goes on documented extension points; changing `agent-loop` requires updating docs/architecture.md.
>
> —— `AGENTS.md`

`agent-loop` 是驱动每一个会话、每一个轮次的核心代码——`docs/architecture.zh.md` 的"轮次流程"一节把它的职责描述为:领取输入、组装提示词、发起模型请求、执行工具调用、判断是否需要下一步。如果每一个新功能需求都被允许直接在这段代码里加分支、加特判,`agent-loop` 很快就会膨胀成一个没有人能完整理解、任何改动都可能引入意外交互的巨石代码。这条规则的解法是把"新增行为"这件事,强制路由到一份已经文档化的扩展点清单上。`docs/architecture.zh.md` 用一张表把这份清单摆得非常具体:

> | 目标 | 机制 |
> |---|---|
> | 添加面向模型的能力 | 在 `ctx.tools` 上注册;其 schema 加入提示词组装 |
> | 拦截请求、工具或轮次 | 使用相应的 `agent/*` 或 `tools/*` 事件;`agent/turn-stopping` 会停止轮次 |
> | 添加模型可见上下文 | 调用 `agent.inject()`;它会落到下一次获准的请求中 |
> | 添加持久会话状态 | 扩展 `SessionEventMap`;从日志渲染和回放 |
>
> —— `docs/architecture.zh.md`

这份表格背后的事件域划分同样值得注意——"轮次流程"一节把 `agent/pre-step`、`agent/request`、`llm/stream` 和三个 `tools/*` 事件标记为**瀑布式(waterfall)事件**,监听器必须调用 `next()` 才能把控制权继续往下传;`agent/turn-stopping` 则是**串行(serial)事件**,没有 `next()` 这个概念。这意味着"新行为"从来不是抽象地"挂在 agent-loop 上",而是要先判断清楚自己要挂在哪一个具体的、已经定义好调用语义的扩展点上——这份判断本身就是把"要不要改 agent-loop"这个危险问题,提前转化成了"我的需求对应文档里哪一行"这个安全问题。

而对于那些确实绕不开、必须改动 `agent-loop` 本身的场景,规则并没有一刀切禁止,而是加了一个强制的连带条件:"changing `agent-loop` requires updating docs/architecture.md"。`docs/architecture.md` 有自己的字数预算上限(≤ 1,800 词),这意味着"改 agent-loop 就要同步改架构文档"这件事本身还带着一重隐性约束——架构文档不能无限膨胀去容纳一次改动的全部细节,这反过来会促使改动者优先考虑"能不能用现有扩展点表达",而不是先改代码后补文档。这条规则和"capability seam 三角色完整性"规则(一个 seam 必须同时具备 Service Definition、Service Provider、Consumer 三个角色,拆分只在角色需要独立演化时才发生)配合,共同表达了同一个态度:新能力的"入口"是稀缺资源,要经过审慎设计,不能靠在核心循环里打补丁来图一时方便。

### Trust TypeScript at typed same-process boundaries:把运行时校验的预算花在真正的边界上

第四条规则读起来最反直觉,因为它是在"少做一件通常被认为是最佳实践的事情":

> **Trust TypeScript at typed same-process boundaries.** Do not add runtime validation, fallback behavior, or hostile-input tests solely for values the static interface requires; validate at parser/config, queued, model/tool JSON, durable/file, worker, process, and wire boundaries.
>
> —— `AGENTS.md`

很多工程师有一种近乎本能的防御性编程习惯:即使一个函数的参数类型已经被 TypeScript 静态接口约束住了,还是会在函数体里再加一层 `if (!value) throw` 之类的运行时校验,理由是"万一"。这条规则明确指出这种习惯在"同进程、类型化"的边界上是浪费——两个在同一次编译里互相类型检查过的 TypeScript 模块之间传值,编译器已经证明了值的形状,再加一层运行时校验不仅是重复劳动,还会带来两个更隐蔽的坏处:一是代码被防御性判断和错误处理淹没,真正的业务逻辑变得难读;二是"fallback 行为"本身可能悄悄掩盖掉一个本该在类型层面就被发现的真实 bug,让程序在错误的状态下继续跑下去,而不是让类型系统在编译期就拦下它。

但这条规则同样明确划出了它*不*适用的范围,而这份清单本身就是一份"什么才算真正的边界"的具体教材:parser/config(配置文件解析,内容来自磁盘,格式可能是错的)、queued(排队消息,可能来自另一个进程或另一次运行留下的旧格式)、model/tool JSON(模型或工具调用返回的 JSON,内容由不受控的一方生成,不受静态类型系统约束)、durable/file(落盘数据,可能是旧版本格式或被手动改过的)、worker(worker 线程之间传递的值,跨越了独立的执行上下文)、process(子进程通信)、wire(线上协议,对端可能是任何版本的客户端)。这份清单的共性是:值从"编译器能证明其形状"的世界跨进了"编译器管不到"的世界——无论是跨越了进程边界、时间边界(旧版本落盘数据)、还是信任边界(模型生成的 JSON、外部协议输入)。规则要求的运行时校验预算,应该精确地花在这些跨越点上,而不是花在两个互相类型检查过的模块之间的普通函数调用上。

理解这条规则,再回头看"Model-visible ⟺ logged"那条规则里提到的"读取器遇到不认识的事件类型时拒绝解读"这一机制,会发现它们其实是同一套判断标准的两个应用:会话日志是"durable/file"边界(落盘数据,可能来自旧版本 harness),所以它理所应当需要运行时校验(未知事件类型守卫、版本方向判断);而两个在同一次编译里被类型检查过的内部函数调用,则不需要重复这层校验。规则清单里列出的七类边界,本质上都是"值从一个 TypeScript 编译单元之外的世界进来"的地方,这也是为什么它会专门把"model/tool JSON"单列出来——模型返回的工具调用参数,尽管在类型层面被声明成了某个 schema,但产生这份 JSON 的一方(模型)并不在这次编译的类型检查范围内,必须在这个具体的跨界点上做真正的运行时校验。

## docs/ 目录的分层 taxonomy:一个事实只有一个家

前面四条规则解决的是代码层面的具体工程问题,而这个项目对"规范文档体系本身"同样有一份治理设计,写在 `docs/AGENTS.md` 里。它开篇就给出了核心原则:

> Each fact has one home: the tier whose job it is; elsewhere, link there.
>
> —— `docs/AGENTS.md`

这句话直译过来就是"一个事实只有一个家"——文档体系被拆成十多个层级(tier),每一层被明确赋予一份职责("Job"),同时也明确列出"不该出现在这一层"的内容("Does NOT belong there")。表格里挑几行最有代表性的看:

> | Tier | Job | Does NOT belong there |
> |---|---|---|
> | Root `AGENTS.md` | Standing orders: rules an agent needs in context in every session, one to three lines each, linking its home | Stories, worked examples, situational procedures, anything restated from a linked home |
> | [architecture.md](architecture.md) | Ordered map: composition, core packages, loop, seams, extension points; read before changing `packages/` | Type definitions (→ subsystems), per-package detail (→ package READMEs), decision rationale (→ Agent Notes), implementation-status annotations |
> | [Agent Notes](../.agents/notes/README.md) | Active decision records: the why, what-was-given-up, and required verification | Migration plans, acceptance-task checklists, fixture walkthroughs, and spec-speak ("should…") once the decision has shipped |
> | [postmortem/](postmortem/README.md) | Incident stories — the only tier where war-story narrative belongs | — |
> | Package README | The per-package contract: config, semantics, limitations, extension points | JSDoc restatement, generated-catalog restatement (event/tool tables), other packages' concerns |
>
> —— `docs/AGENTS.md`

这份分工可以这样理解:根 `AGENTS.md` 只放"每次会话都要带着走的规则",不放故事和案例(那是 postmortem 的职责);`architecture.md` 只放"改动 `packages/` 之前该知道的地图",不放类型定义的具体细节(那是 subsystems 的职责)、也不放某个决定为什么这么做的取舍过程(那是 Agent Notes 的职责);Agent Notes 只记录"活跃的决策依据",一旦决策落地实现,就不该再保留"应该……"这种还没发生的语气;而 postmortem 是**整个文档体系里唯一被允许讲"事故叙事"的层级**——别的层级如果想复述一个 bug 的来龙去脉,规则会把它当作放错了地方。

这套分工存在的直接理由,写在紧接着的"文档写作规则"一节里:

> **Document current state, not change history.** Avoid "previously/now/no longer", PRs, commits, and stack positions in durable prose; name the live mechanism. Put change stories in commits, PRs, Agent Notes, or postmortems …
>
> —— `docs/AGENTS.md`

以及后面"slop checklist"(文档异味检查清单)里排第一位的:

> The same rule stated in more than one home. Grep a distinctive phrase; keep one home and link the rest.
>
> —— `docs/AGENTS.md`

这两条合起来说明了"一个事实只有一个家"要防止的具体腐化过程:如果同一条规则、同一段机制说明可以随手写在两三个不同的文档里,这些副本会在后续迭代中各自被修改、各自遗漏更新,时间一长就会彼此矛盾——读者读到的到底是哪一份是权威的?这个问题在只有几个文档时不明显,但 DeepSeek Harness 的 `docs/` 目录有六十多项内容,还叠加了中英双语(`.md`/`.zh.md`/`.i18n.yaml` 三件套)的翻译负担,如果没有强制的"唯一归属"原则和一份可以直接 grep 关键短语去核查的检查清单,文档体系本身会比代码库更快陷入不可维护的重复与漂移。

这套治理设计还配了一层机械执行:每一份"标准文档"都有一个字数预算上限(`pnpm run verify-doc-budgets` 强制),根 `AGENTS.md` ≤ 1,600 词、`architecture.md` ≤ 1,800 词、大多数子树 `AGENTS.md` ≤ 600 词。字数预算和"一个事实只有一个家"其实是同一枚硬币的两面:如果一份文档的篇幅被硬性限制住,作者就没有空间去重复展开别处已经讲过的内容,唯一的出路就是把细节挪到它真正归属的那一层,自己这一层只留一条链接。当预算不够用时,`docs/AGENTS.md` 给出的优先顺序也很明确——先"迁移"内容到正确的层级,其次才是"压缩"表达,只有当内容确实需要更多篇幅时才"提高"预算上限,而且提高动作必须在 PR 里对预算清单的改动做出说明,不能悄悄改数字。

## 常见问题/易踩坑

- **"AGENTS.md 里的规则这么简短,是不是随便写写、靠约定俗成执行的?"** 不是。四条规则里至少两条(Registrations are effects、Model-visible ⟺ logged)都对应着机械可检查的守卫——注册表的 HMR 安全测试会在插件卸载不干净时直接失败;未知会话事件类型默认被拒绝读取,不需要人工审查就能拦住。简短是因为篇幅预算逼出了压缩表达,不是因为约束本身是软的。
- **"Trust TypeScript at typed same-process boundaries 是不是在鼓励少写校验代码?"** 不完全是。它鼓励的是把校验预算从"到处都加一层以防万一"重新分配到"真正跨越信任边界的七类地方"(parser/config、queued、model/tool JSON、durable/file、worker、process、wire)。同进程、类型化调用之间的校验确实应该省掉,但规则列出的七类边界上的校验一分都不能少——这不是"少校验",而是"把校验用在真正需要的地方"。
- **"改了 agent-loop 里的一行代码,是不是必须大改 docs/architecture.md?"** 取决于这行改动是否改变了 agent-loop 对外承诺的行为契约。规则要求的是"changing agent-loop requires updating docs/architecture.md",如果改动本身只是内部实现细节、没有改变任何一个已文档化的事件语义或扩展点行为,通常意味着这行改动本可以、也应该发生在插件层而不是 loop 本身;真正需要动 loop 契约的改动,才需要同步更新架构文档。
- **"docs/ 目录这么多层级,新写一份文档要怎么决定放哪一层?"** `docs/AGENTS.md` 给出的判断顺序是:先定位这份内容在文档树里该处于哪个位置,再确定这一层被允许的详细程度,再决定是教程还是参考,最后才动笔——如果发现自己在某一层里复述了别的层级已经讲过的细节,应该删掉这部分,换成一条链接。

## 小结

这四条规则和 `docs/AGENTS.md` 的分层设计合起来讲的是同一件事:一个规范条款很少是凭空的道德说教,它往往是对一次具体架构决策或一次具体事故的压缩编码。"Registrations are effects"背后是插件热重载/卸载必须完全可逆的资源生命周期设计;"Model-visible ⟺ logged"背后是整套会话事件溯源、版本升级、`ignorable` 标记的持久化机制;"Plugins, not loop changes"背后是把 `agent-loop` 这个最容易被蚕食的核心组件,用文档化扩展点和架构文档字数预算共同钉成一份稀缺契约;"Trust TypeScript at typed same-process boundaries"背后是一份精确划定的、只在值跨越真正边界时才启用运行时校验的清单。而这些规则本身能保持简短、不互相重复、不随时间腐化,靠的正是 `docs/AGENTS.md` 那套"一个事实只有一个家"的分层治理——规范文档体系,同样需要被当作一个工程产物来设计和维护。
