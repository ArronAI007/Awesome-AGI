# Postmortem 与防御性编程模式

> 在上一篇讲过的文档分层 taxonomy 里,`postmortem/` 被单独标注为"整个文档体系里唯一允许讲事故叙事的层级"。这不是随意的豁免,而是一种明确的分工:别的层级负责陈述"现在是什么样",只有 postmortem 负责回答"我们是怎么把事情搞砸的,而所有安全网为什么都没接住"。本篇读两篇真实的事故复盘(0001 和 0004),提炼出这个项目"从一次事故走到一条新规则"的方法论,再看 `docs/defensive-patterns.md` 这份把历史教训蒸馏成规则清单的文档,理解生命周期/并发/子进程/清理这几类防御模式为什么在一个长期运行的 agent 进程里格外重要。

## 学习目标

- 理解 postmortem 这一文档层级的准入门槛——"subtle(机制不显然)、systemic(暴露的是流程缺口而非笔误)、costly to rediscover(值得写下来防止重复付出调试成本)"——以及它和 Agent Note 的本质区别。
- 通过 postmortem 0001 理解"178 个单元测试全绿、100% 覆盖率"依然能在生产环境第一秒崩溃的具体机制,理解两个独立 bug 为什么都能藏在同一段错误信息背后。
- 通过 postmortem 0004 理解"共享前缀不是协议"这一类多证据归因缺陷:一个语义丰富的信号被压缩成一个子串匹配后,会丢失哪些区分度。
- 提炼出这个项目"事故 → 加一个能让回归真的变红的测试 → 把教训写成规则"这条闭环方法论,理解为什么"链接到这次复盘催生的守卫"是每篇 postmortem 的强制要求。
- 理解 `docs/defensive-patterns.md` 里生命周期、并发、子进程、清理相关的具体规则,以及为什么这些模式在一个持续运行、不断启动子进程、频繁热重载插件的 agent 进程里格外容易被忽视又格外容易出事。

## 背景与设计动机

不是所有 bug 都值得写一篇 postmortem。`docs/postmortem/README.md` 给出了明确的准入标准和写作要求:

> A post-mortem is NOT an [Agent Note] (which records a deliberate design decision and its rejected alternatives, or proposes future work). It is a backward-looking record of a failure: what broke, the mechanism, why every safety net missed it, and the concrete guardrails added so the same class of bug fails loudly next time.
>
> Write one when a bug is **subtle** (the mechanism is non-obvious and a careful engineer would re-derive it the hard way), **systemic** (the reason it escaped is a gap in tests/tooling/conventions, not a one-off typo), and **costly to rediscover** (it cost real debugging time, and would cost it again). Link the guardrails (tests, AGENTS.md rules, ADRs) the post-mortem motivated.
>
> —— `docs/postmortem/README.md`

这段话把 postmortem 和 Agent Note 的分工划得很清楚:Agent Note 记录的是"我们主动做了一个设计决定,放弃了哪些替代方案",是面向未来的;postmortem 记录的是"一件事已经发生并且造成了损失",是面向过去的,而且明确要求写清楚"为什么每一层安全网都没接住它"——这正是 postmortem 区别于一句简单的 changelog("修了一个 bug")的地方:它要解释的不是修复本身,而是修复之前那套本该拦住这个 bug 的机制为什么集体失灵。README 还要求每篇 postmortem 用一段"三十秒内能读完的执行摘要"开篇,这也是为了让这份"事后解剖报告"能被后来的工程师快速复用,而不必每次都重新啃一遍完整时间线。

截至目前,这个项目一共写了四篇 postmortem,分别对应 ACP 服务器加载崩溃、文件系统工具被条件表达式永久禁用、Web agent 验收了错误的服务器、以及 Landlock 部分强制执行通知被误判为子进程失败。本篇挑其中机制最典型的两篇——0001 和 0004——展开讲,再把四篇共同的方法论提炼出来。

## 核心机制详解

### Postmortem 0001:100% 覆盖率崩在生产的第一秒

这篇复盘的标题是"ACP server crashed on connect: `export default` dropped the plugin's `inject`"。摘要部分先给出了让人警觉的对比:

> 两个集成错误在单元测试全覆盖的情况下仍然导致 ACP 崩溃:一个默认导出使 Loader 丢弃了 `inject`,一个经可追踪代理的可选服务查找在 shadow 边界上失败。手动挂载的测试绕过了这两条路径。
>
> —— `docs/postmortem/0001-acp-default-export-drops-inject.zh.md`

根因 #1 是本课程系列前一篇已经详细拆过的那个 bug:`packages/acp/acp/src/index.ts` 作为命名空间插件,本该只用具名导出(`name`/`inject`/`Config`/`apply`),却多写了一行 `export default apply`。Cordis Loader 的 `unwrapExports` 在遇到默认导出时会优先解析出 `.default`,把整个模块命名空间——连带 `inject` 声明——一起丢弃,`apply` 因此在一个没有注入任何服务的 fiber 里运行,第一行读 `ctx.agents` 就直接抛出异常。

根因 #2 是一个更隐蔽的问题,值得单独看一眼。修复了 #1 之后,`session/load` 仍然在读取 `sessionPersistence` 时崩溃。这个服务*故意*没有出现在 `AgentLoop` 的 `static inject` 里(注入它会导致非持久化的演示场景永远挂起,等一个永远不会加载的后端),所以代码里用属性读取的方式机会性地访问它。但 Cordis 的上下文代理在通过*可追踪代理*调用服务方法时,会把 `this` 重新绑定到一个 shadow 对象,而属性访问的 fiber 遍历**只朝祖先方向进行**——`sessionPersistence` 所在的 fiber 是一个兄弟分支,不在这条祖先链上,遍历到根之后只能抛错。这个 bug 之所以在内存测试里从未出现,是因为测试代码直接从"fiber 之外"调用 `ctx.agents.resume(...)`,这时 `ctx.fiber.runtime` 为 `null`,代理会走一条完全不同的绕过路径——基于 isolate symbol 的全局 store 直接查找,根本不会触发那次会失败的祖先遍历。

两个 bug 表面上毫不相关,却被同一段错误信息(`cannot get property "X" without inject`)困在了一起,而复盘专门用一节回答了"为什么所有测试都没有捕获"这个问题:

> 两个 bug 都源于同一个根本流程缺口:**没有任何测试通过插件的真实加载路径或真实调用拓扑来驱动它。**
>
> - 内存 harness 通过手动构建插件对象来挂载 bridge:`ctx.plugin({ name, inject, apply })`。这手动提供了 `inject`,因此永远无法复现 Bug #1。
> - 同一个 harness 将所有内容平铺挂载在一个根上下文上,因此从中触达的 `AgentLoop` 恢复要么运行在顶层(`!runtime` 绕过),要么经由 shadow 运行,而该 shadow 的 origin 仍然解析到 root——掩盖了 Bug #2 的祖先遍历失败。
>
> —— `docs/postmortem/0001-acp-default-export-drops-inject.zh.md`

这段话点出了这次事故最有价值的教训:测试之所以没抓住 bug,不是因为覆盖率不够,而是因为**测试搭建方式本身系统性地绕开了唯一会暴露 bug 的那条路径**——手动挂载既绕开了 `unwrapExports`,又绕开了真实的 fiber 拓扑。这就是为什么复盘的结论不是"补一个测试",而是改写了测试基础设施本身的搭建方式,同时把这条教训编纂进了 `docs/testing.md` 的"测试真实入口路径"规则里,让它约束所有未来插件,而不只是这一个 bridge。

复盘末尾的"经验教训"部分还留下了一句值得记住的方法论提醒:

> 相信跟踪结果,不要迷信理论。优雅的 shadow 解释是真实的,但它是*第二个* bug;*第一个*是一行导出错误,在数小时看似合理但实际错误的推理之后,一个 fiber 遍历的 `console.error` 在几分钟内就找到了它。
>
> —— `docs/postmortem/0001-acp-default-export-drops-inject.zh.md`

### 另外两篇复盘的共性:确定性 ≠ 正确性

0002 和 0003 处理的是两类完全不同的场景,但都指向同一个容易被忽视的判断误区。0002(文件系统快照工具被永久禁用)的根因是:Cordis 只在插件 `config` 字段内对 `!!js` 表达式求值,但示例仓库把 `disabled: !!js ...` 写在了 Loader 配置项元数据上,导致该字段永远读到一个 truthy 的表达式对象,文件系统插件因此在所有模式下都保持禁用。真正暴露问题的不是这个错误本身,而是它逃过检测的方式:

> 快照框架将任何确定性的 transcript(文本记录)视为有效行为。Header pin 验证了组合后的工具 schema,但文件系统场景共享来自默认组合的 pin,因此未独立证明其所需工具已注册。刷新在任何语义断言拒绝缺失工具之前,就已重写了预期的 stdout 和会话日志。
>
> —— `docs/postmortem/0002-js-expression-disabled-filesystem-tools.zh.md`

也就是说,快照测试通过了,是因为工具确实*一直*返回同一个 `UNKNOWN_TOOL` 错误结果——这个结果是确定性的、可回放的,快照机制的字面职责("给定同一份输入,输出没有漂移")被满足了,但"输出没有漂移"和"输出是对的"完全是两件事。复盘把这条教训写得很直接:"快照刷新是 fixture 的生产过程,不是正确性审查。诸如已注册工具缺失这类语义上不可能的结果,需要独立于预期输出的断言。"这和上一篇讲过的"覆盖率证明代码跑过,不证明代码跑对"是同一个逻辑结构在不同测试层级上的重演。

0003(Web agent 验收了替代服务器而非当前 GUI)则展示了另一种"确定性 ≠ 正确性"的变体:agent 依次观察到源码修改成功、构建成功、HTTP 200、注入的启动 manifest,每一个信号单独看都成立,却没有一个指向"用户正在看的那个页面确实更新了"。复盘的结论一针见血:"HTTP 就绪、构建成功和启动 manifest 是不同的事实。验收必须明确指定确切的 origin,并从外部观察所请求的改动是否在该 origin 生效。"——这句话和 `docs/testing.md` 里"验证外部世界,而非自我报告"那条规则几乎是同一件事在产品验收场景里的翻版:agent 手里攥着好几个看似成功的信号,但没有一个信号真正锚定到"那个特定的、用户正在使用的目标"上。

### Postmortem 0004:"共享前缀不是协议"

第四篇复盘处理的是一类完全不同的问题——不是插件加载,而是沙箱子进程的失败归因。摘要是这样写的:

> 在 Landlock ABI 较旧的内核上,launcher 会在执行每个子进程前打印一条无害的部分强制执行通知。harness 把共享的 `landlock-run:` 前缀与任意非零子进程退出组合起来,判定为 launcher 失败,因此 ripgrep 在没有匹配项时以 1 退出等普通结果会呈现为 `SANDBOX_UNAVAILABLE`。
>
> —— `docs/postmortem/0004-landlock-partial-notice-misclassified-child-failures.zh.md`

原生 launcher 的约定本来区分得很清楚:内核只能部分强制执行时,打印一条精确的信息性文本("partial enforcement (older Landlock ABI)")然后继续执行子进程;launcher 真正失败时,打印另一行诊断,并以退出码 125 收场、根本不执行子进程。但消费这个约定的 harness 代码把两种情况都简化成了同一个判断:"stderr 里出现了 `landlock-run: ` 这个子串,同时子进程退出码非零"。问题在于,ripgrep 用退出码 1 表示"搜索完成但没有匹配"——这是一个完全正常的结果,却因为恰好同时满足"非零退出"和"输出里带有那个前缀"这两个条件,被误判成了沙箱基础设施故障。

根因部分把这个问题上升到了一般性的表示能力缺陷:

> 公开的沙箱结果类型只能表达一组子字符串。它无法表示 Landlock 失败必须使用退出码 125、证据必须出现在一行致命诊断内,或同一前缀下有一行精确文本属于信息性通知。消费方的布尔判定逻辑因此把来自不同进程且互不相关的事实组合在一起。
>
> —— `docs/postmortem/0004-landlock-partial-notice-misclassified-child-failures.zh.md`

这段话讲的是一类值得记住的通用陷阱:**一个原本携带多重语义的信号(退出码 + 具体输出行 + 输出顺序),被压缩成一个子串匹配之后,就丢失了原本足以区分"正常"和"故障"的信息。**真正的判定条件需要三项证据同时成立(退出码是 125、致命诊断出现在某一行、这一行不等于那条已知的信息性文本),但代码里只留下了一项弱证据(子串是否出现)。修复方案的思路正是把丢失的区分度找回来:

> [`RunnerFailureRule`] 携带可选的允许退出码、不区分大小写的逐行致命签名,以及按不区分大小写的整行精确匹配排除的信息性行。
>
> —— `docs/postmortem/0004-landlock-partial-notice-misclassified-child-failures.zh.md`

复盘的"教训"部分把这次事故浓缩成了一句可以直接迁移到别处的原则:

> 进程归因需要多项独立证据同时成立;共享前缀不是协议。
>
> 信息性诊断与致命诊断可以共享同一命名空间,因此排除规则必须精确且范围狭窄,同时对未知的致命行保持失败关闭。
>
> —— `docs/postmortem/0004-landlock-partial-notice-misclassified-child-failures.zh.md`

"共享前缀不是协议"这句话值得单独记下来,因为它描述的模式会在很多场景重演:任何时候,判定逻辑图省事只检查了"输出里是否出现某个标志字符串",而没有检查这个字符串出现的位置、伴随的退出码、以及它是否属于一份已知的、有限的信息性文本清单,都可能重复这次事故的错误——一个原本无害的信号会被误判为故障,一个真正的故障也可能因为恰好缺了那个字符串而被漏判。

### 复盘驱动治理的闭环:从故事到规则

把 0001、0004,以及前面提到过的 0002(`!!js` 表达式只在插件 `config` 内求值,导致文件系统工具被永久禁用却被快照刷新悄悄接受)放在一起看,能看出一条重复出现的闭环结构:

1. **一个 bug 逃过了所有现有测试**,而且逃过的原因不是"测试写少了",而是测试搭建方式或判定逻辑本身存在一个系统性的盲区(0001 的手动挂载绕开真实加载路径;0004 的子串匹配丢失了区分度;0002 的快照刷新把语义上不可能的 `UNKNOWN_TOOL` 结果当成了新的预期输出接受了下来)。
2. **新增一个"能让回归真的变红"的守卫**,并且明确要求验证它有效——0001 里"已验证恢复 `export default apply` 时测试失败";0004 里新增了原生边界回归用例和组装后的快照组合,专门覆盖"信息性通知后跟非零子进程退出"这一原来测试矩阵里完全没有覆盖到的组合。
3. **把这次事故蒸馏出的一般性教训写成一条规则**,放进它真正归属的那一层文档——0001 催生了 `docs/testing.md` 的"测试真实入口路径"规则;0002 催生了 `AGENTS.md` 和 `docs/cordis-primer.md` 里关于 `!!js` 只在插件 `config` 内有效的明确说明,以及 `verify-cordis-config` 这个新的静态检查;0004 催生了 `RunnerFailureRule` 这个更精确的沙箱失败表示类型。

这条闭环正是 `docs/postmortem/README.md` 那句"Link the guardrails (tests, AGENTS.md rules, ADRs) the post-mortem motivated"的具体展开——postmortem 本身只负责讲清楚故事和机制,它催生的规则和测试则会被链接出去、安放进各自真正归属的文档层级(`docs/testing.md`、`AGENTS.md`、某个包的 README),这正好呼应了上一篇讲过的"一个事实只有一个家"原则:postmortem 是唯一允许讲事故叙事的地方,但事故教训沉淀下来的*规则*不会留在 postmortem 里重复陈述,而是各自搬去它们该在的位置。

### docs/defensive-patterns.md:蒸馏后的规则清单

如果 postmortem 是"故事",那么 `docs/defensive-patterns.md` 就是这些故事(以及"差点发生的事故")蒸馏出的"规则清单"。文档开篇就说明了它的性质:

> 来之不易的缺陷类别规则:下面每条模式都是本项目实际发布或差点发布的一类缺陷,以防止其复发的规则形式陈述。在编写生命周期、并发、子进程或清理代码之前请先阅读本文。
>
> —— `docs/defensive-patterns.zh.md`

`AGENTS.md` 把这份文档列为改动生命周期、并发、子进程或 teardown 代码之前的强制阅读项。理解这几条模式为什么格外重要,关键在于理解 agent-loop 所在的这个进程的运行特征:它不是一次性跑完就退出的批处理脚本,而是一个长期存活、持续接收新消息、动态挂载/卸载插件、频繁启动又必须清理子进程的常驻服务。下面逐条看:

- **正交结果独立上报**:"一个结果可以同时具有多种性质:进程可能已经超时,却仍以退出码 0 结束,因为它捕获了终止信号。每个独立事实(`timedOut`、`signal`、`exitCode`)都应单独上报;切勿把一个标志的上报嵌套在另一个标志的分支中"(`docs/defensive-patterns.zh.md`)。这条规则和 postmortem 0004 的教训是同一类问题的一体两面——0004 里退出码和输出字符串被错误地绑在一起判断;这里则是提醒开发者不要在设计阶段就制造出这类耦合。对一个会不断启动 bash 工具子进程的 agent 而言,"超时但退出码正常"是一种真实会发生的组合,如果上报逻辑把这些事实嵌套判断而不是独立并列,调用方就可能把一次被提前终止的运行误判为正常成功。
- **公共约定两侧都要遵守**:"当一个实现收到同一结果的多种表示时,应在通过公共 API 返回前将其规范化。`LlmAdapter.stream()` 的实现可以抛出异常或发出 `finish {kind:'error'|'aborted'}`,但 `LlmRuntime.stream()` 只会通过终止型 finish 分片暴露模型请求失败"(`docs/defensive-patterns.zh.md`)。这一条讲的是能力 seam 内部的纪律:一个 Service Definition 可能有多个 Provider 实现,每个实现习惯用不同的方式表达"失败"(抛异常、返回错误字段、发一个特殊事件),如果不在 seam 的公共边界上统一规范化,Consumer 就必须为每一种可能的表示方式各写一遍处理逻辑,而且一旦漏掉一种,失败就会以未处理异常的形式突然冒出来,而不是被消费方优雅地识别为"这次请求失败了"。
- **异步状态不是同步状态**:"`agent.followup()` 没有逐消息的完成状态或结果;后台任务的完成与轮次边界存在竞争……切勿把 `agent/status` 或 `whenIdle()` 当作某次 `followup()` 的结果"(`docs/defensive-patterns.zh.md`)。这条规则直接对应 agent-loop 的运行现实:一个会话的 inbox 里可能同时排着好几条待处理消息、后台任务、steering 注入,它们共享同一个"运行中"区间,而不是一条消息对应一段独占的执行窗口。如果调用方想当然地把"下一次进入 idle"当成"这条消息的结果",在消息被排队、被取消、或者和别的输入合并处理的场景里就会得出错误的因果关系。
- **dispose 必须达到完全停稳,而不仅仅是请求停止**:"如果清理流程只发出终止或中止信号便返回,而不等待工作真正停止,就会留下孤儿进程"(`docs/defensive-patterns.zh.md`)。这一条几乎是为"agent 会通过 bash 工具启动真实子进程"这个事实量身定做的——上一篇提到的 `coding-task.e2e.ts` 里 `afterEach` 那句注释("LocalBashExecutor teardown kills anything the model left running")正是这条规则的具体落地。发送终止信号只是"请求"停止,真正安全的清理必须等到进程确实退出(`done`)才能返回,否则下一个测试或下一个会话开始时,前一个会话遗留的子进程可能仍在争用同一份资源。
- **在分发器中隔离回调异常**:"用户提供的监听器如果抛出异常,不得导致它所在的 promise 被 reject,也不得饿死排在它后面的监听器"(`docs/defensive-patterns.zh.md`)。在一个"everything is a plugin"的架构里,任意数量的插件可能挂了监听器在同一个事件上,如果分发循环没有用 try/catch 隔离每一个监听器的异常,一个写得不好的插件就足以让核心生命周期(比如清理逻辑本身)中途中断——这正是"Registrations are effects"那条规则要求"注册必须可逆"背后隐含的另一半要求:执行监听器本身也不能让一个插件的错误级联影响到其它插件。
- **绝不将环境变量或可预测路径暴露给不可信输出**:要求清理 `*KEY*`/`*SECRET*`/`*TOKEN*`/`*PASSWORD*` 之类的环境变量,临时文件放在 0700 权限的私有目录、用随机文件名、以独占方式打开(`docs/defensive-patterns.zh.md`)。这是几条模式里唯一带有安全属性的一条——因为 agent 会通过 bash 工具执行模型生成的命令,任何一次 `env` 或者命令输出都有可能把 harness 自己的凭证泄漏出去,而这份风险在"agent 能自主决定执行什么命令"这个前提下,比传统程序里的同类风险要现实得多。
- **用 unlink 删除链接形态的路径**:teardown 时如果要删除的路径可能是符号链接或 Windows junction,必须先判断再用 `unlinkSync`(只删链接本身,不跟随进目标),而不是直接对它做递归删除。这条模式看起来琐碎,但恰好是"teardown 代码"这个类别里最容易被跳过测试、又最容易在真实文件系统上出现意外后果的一类 bug——递归删除一旦不小心跟随了链接进入目标目录,清理逻辑就可能删掉本不该删的东西。

这七条模式没有一条是通用编程教材里的新知识,但把它们放在一起、并且明确标注成"编写生命周期/并发/子进程/清理代码之前必须先读"的强制阅读项,本身就是一种治理姿态:与其寄望每个贡献者(包括驱动这个项目开发的 agent 本身)凭经验想起这些坑,不如把踩过的坑直接写成清单钉在正确的位置上。

## 常见问题/易踩坑

- **"复盘里说的都是已经修好的 bug,现在读还有什么用?"** 有用,而且这正是 postmortem 这一文档层级存在的理由。规则本身(比如"测试真实入口路径")读起来只是一句抽象要求,只有配合它所修复的那次具体事故——手动挂载插件为什么系统性绕开真实加载路径——才能理解这条规则划定的边界到底在哪里,以及类似的坑还可能在哪些场景以不同面目重演。
- **"是不是所有 bug 都应该写一篇 postmortem?"** 不是。`docs/postmortem/README.md` 明确要求同时满足"机制不显然""暴露的是流程缺口而非笔误""值得写下来防止重复付出调试成本"三个条件。一次普通的拼写错误或者显而易见的边界条件遗漏,写成 Agent Note 或者干脆只在 PR 描述里说明即可,滥用 postmortem 只会让真正值得反复研读的几篇被稀释。
- **"防御性模式清单是不是越长越好?"** 不是。`docs/defensive-patterns.md` 只收录"本项目实际发布或差点发布过的"缺陷类别,而不是泛泛而谈的通用最佳实践大全——这也是为什么它能保持简短(全文不到 40 行)却每一条都有真实分量。把没有真实教训支撑的"通用建议"混进来,只会让读者失去分辨"这条真的重要"和"这条只是安全起见写上的"的能力。
- **"0004 里退出码、致命行、信息性行都对上了才算故障,这是不是过度设计?"** 不是过度设计,而是把丢失的区分度找回来。子串匹配之所以出问题,恰恰是因为它把一个本该由多个独立事实共同决定的判断,压缩成了一个可以被无关信号意外触发的单一条件;要求多项证据同时成立不是增加复杂度,而是让判断逻辑的复杂度匹配现实世界本身的复杂度。

## 小结

Postmortem 和 `docs/defensive-patterns.md` 是同一套"从事故学习"机制的两个阶段:postmortem 负责讲清楚一次具体事故的完整机制——0001 展示了"手动挂载插件系统性绕开真实加载路径"这一类盲区,0004 展示了"共享前缀不是协议"这一类归因缺陷,两者都伴随着"新增一个能真正变红的守卫测试"这一强制要求;`docs/defensive-patterns.md` 则把这些事故(以及更多没有单独写成 postmortem 的教训)蒸馏成一份不带故事、只留规则的清单,按生命周期、并发、子进程、清理这几个最容易出事的类别组织起来。两者的分工同样遵守"一个事实只有一个家"的原则——故事留在 postmortem 里,可执行的规则搬到 `defensive-patterns.md`、`AGENTS.md` 或具体的测试文件里。对一个长期运行、动态组装插件、持续启动子进程的 agent 进程而言,这套"复盘 → 守卫 → 规则"的闭环治理,正是让工程质量随时间积累而不是随时间腐化的关键机制。
