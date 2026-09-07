# 测试哲学：Verify the World, not the Self-Report

> 传统软件测试里,被测系统不会替自己写测试报告。但一个 agent 测试套件天然多出一个混淆变量——被测对象(模型)自己也会生成一段听起来完全成功的"我已经完成任务"叙述,而这段叙述和任务是否真的完成之间没有必然联系。DeepSeek Harness 的 `docs/testing.md` 把这个问题当作测试策略的第一原则来处理,本篇逐条拆开它,并用一个真实的 e2e 测试文件把"验证外部世界"这句话落到具体代码上。

## 学习目标

- 理解 agent 测试相对传统软件测试多出的那个陷阱:被测系统(LLM)可以自己生成一段以假乱真的"成功报告",单靠这段报告做断言等于让考生自己判卷。
- 理解 DeepSeek Harness 为什么坚持"不要吝惜真实 API 测试"(`We are DeepSeek — do not ration real-API tests`),以及这条策略与"只 mock 昂贵或不确定的边界"这条克制原则之间并不矛盾。
- 搞清楚这个项目的测试分层(单元 / 覆盖率门禁 / 真实 API e2e / 快照 / Web 浏览器快照)各自能证明什么、不能证明什么,理解为什么它们不能互相替代。
- 通过真实测试文件 `examples/headless-agent/tests/coding-task.e2e.ts` 理解"验证外部世界,而非自我报告"这条规则在代码层面具体怎么写。
- 理解"测试真实入口路径"规则如何专门堵住"手工搭建的插件测试全绿、真实产品在生产环境秒崩"这一类回归,并能复述 postmortem 0001 里这个故事的具体细节。
- 理解覆盖率门禁的本质边界:它只能证明代码行被执行过,不能证明功能按交付方式正常工作。

## 背景与设计动机

普通的单元测试作弊很难——一段字符串拼接的实现要么让断言通过要么不通过,写测试的人和被测代码之间没有共谋空间。但如果被测系统是一个大模型驱动的 agent,情况就不同了:agent 的输出本身包含一段自然语言叙述("我已经修好了 bug,测试通过了"),而这段叙述是模型生成的,天然带着"说得像真的"这个特性,却不天然带着"事情真的做对了"这个属性。如果测试断言直接对这段叙述做关键词匹配,那么测试通过的条件退化成了"模型说了正确的话",而不是"模型做了正确的事"——这正是标题里"self-report(自我报告)"这个词想precisely 指向的陷阱。

DeepSeek Harness 用一次真实事故把这个抽象问题变成了具体教训。[docs/postmortem/0001-acp-default-export-drops-inject.md](../../../ai_project/deepseek-harness/docs/postmortem/0001-acp-default-export-drops-inject.md) 记录了 ACP(Agent Client Protocol)服务器在真实编辑器连接的第一秒就崩溃,而崩溃前的仓库状态是 178 个单元测试全绿、行覆盖率 100%。这不是"测试写少了"的问题,而是"测试从没有真正走过产品会走的那条路"的问题。`docs/testing.md` 里几乎每一条规则,都可以在这次事故或类似事故里找到对应的动机。本篇就按这条主线,把测试哲学的几条核心规则和它们各自解决的具体陷阱对应起来讲清楚。

## 核心机制详解

### 测试分层:每一层证明什么,不能证明什么

`docs/testing.md` 开篇先把测试拆成五层,每一层职责单一,互不替代:

> - **Unit** (`pnpm run test`): vitest over package and example specs under their `tests/**` directories … Prefer edge cases, error paths, event ordering, concurrency races, and permanent tests for contract regressions.
> - **Coverage gate** (`pnpm run test:coverage`): the gating run, per-file 100% on `packages/*/*/src`. An uncovered line is often dead code the gate is correctly flagging for deletion, not a missing test to bolt on. Line coverage is necessary, never sufficient — it proves lines ran, not that the feature works as shipped.
> - **Real-API e2e** (`pnpm run test:e2e`): with-key tests against live provider APIs …
> - **Snapshot** (`pnpm run test:snapshot`): keyless expected outputs cover external behavior — transport contracts and presentation, while persisted logs pin assembled backend behavior.
> - **Web browser snapshot** (`pnpm run test:web`; required Linux PR gate): Chromium compares replayed browser output with `apps/web/tests/snapshots/`.
>
> —— `docs/testing.md`

这五层各自守住一个"绝不能被别的层顶替"的证据类型。单元测试守住的是函数/模块内部逻辑的边界情况和事件顺序;覆盖率门禁守住的是"这条代码路径确实被执行过"这一最低门槛,但特别提醒了一句容易被误读的话——**行覆盖率是必要条件,永远不是充分条件**,它只证明代码跑过,不证明代码跑对了。真实 API e2e 守住的是"agent 真的能对接一个活的模型工作";快照守住的是"给定同一份输入,产出的协议消息/呈现内容/持久化日志没有意外漂移";Web 快照专门守住浏览器渲染这一层,因为很多问题(比如样式、DOM 结构)在 Node 环境的单元测试里根本没有对应的失败模式。

这张分层表本身就是一种设计声明:任何一类 bug,都应该能被归类到"哪一层理应捕获它却没有捕获"。这也是为什么每一篇 postmortem 结尾都会明确指出新增了哪一层的哪个具体测试,而不是笼统地说"补了测试"。

### "We are DeepSeek — do not ration real-API tests":为什么 agent 测试离不开真实推理

`docs/testing.md` 用一句近乎宣言式的话给真实 API 测试正名:

> We are DeepSeek — do not ration real-API tests. A no-key test proves plumbing; only a with-key run proves the agent works against a real model. Cover file-writing prompts, multi-turn conversations, tool use, and mid-stream cancellation. Highest-value are **smoke tests** that boot the real example, send one prompt, and check the world — they catch the "green unit tests, broken product" class that mocks cannot. Self-skip keeps secretless CI and keyless contributors unblocked; it is not a cost signal.
>
> —— `docs/testing.md`

这条规则要解决的问题是:很多团队会把"调用真实模型 API"当成一种成本负担,本能地想用 mock 掉推理调用来省钱、省时间。但对 agent harness 这类产品而言,"模型是否真的能在这套 harness 里正常工作"恰恰是产品最核心的承诺,而这个承诺**只有真实推理调用才能验证**——一个手写的 mock 模型,不管写得多逼真,验证的都是"我以为模型会怎么行为",不是"模型真的怎么行为"。`docs/testing.md` 用"自我跳过"(self-skip:没有 `DEEPSEEK_API_KEY` 时套件自动跳过)机制把"保持无密钥 CI 和无密钥贡献者不受阻塞"和"不吝惜真实调用"这两个目标同时满足——跳过不是成本信号,而是访问控制信号。

这条规则并不否定 mock 的价值,它和"优先使用真实实现而非 mock"这条规则是同一枚硬币的两面:

> Mock only the expensive or non-deterministic boundary (LLM adapter, network, clock); keep everything downstream real. A hand-rolled stand-in proves the bridge moves bytes, not that the shipping tool behaves as asserted. Bridge tool-call tests use the scripted mock model with the real tool and executor: `makeBridgeHarness({ withBash: true })` plugs in `dsh-bash-local` and `dsh-tool-bash`, then runs `echo`.
>
> —— `docs/testing.md`

两条规则合起来的意思是:mock 的边界应该尽量收窄到"确实昂贵或确实不确定"的那一层(模型调用、网络、时钟),下游的工具执行器、沙箱、持久化等等都应该用真实实现跑起来。而对"模型调用"这一层本身,策略不是永远 mock,而是分场景——**冒烟测试(smoke test)必须带着真实模型跑**,因为它要证明的正是这一层的真实行为;而"桥接层是否正确搬运字节"这类问题,可以用脚本化的 mock 模型配合真实工具执行器来验证,因为这里要证明的是下游链路而不是模型本身。

### "Verify the world, not the self-report":拒绝关键词探测式断言

这是本篇标题直接引用的那句话,也是整套测试哲学里最反直觉、最需要单独强调的一条:

> An e2e assertion re-runs the command or re-reads the file externally; a keyword probe on the agent's own output lets a cheating agent pass. Assert untouched files are byte-identical. e2e tests own their resources: create the harness in the test, dispose in `afterEach` (even on failure/retry/timeout); shared fixtures live in a plain `tests/harness.ts`, never another `*.e2e.ts` (importing a spec re-registers its `describe` and duplicates real API calls).
>
> —— `docs/testing.md`

"关键词探测(keyword probe)"指的是这样一种写法:agent 跑完一轮对话后,拿到它最后一条回复的文本,搜索里面是否出现"成功""fixed""done"之类的词,把这个搜索结果当作测试断言。这种写法的问题在于,它把"模型说了什么"和"世界发生了什么"这两件事等同起来——而这正是 agent 系统区别于传统程序的地方:模型的输出**本身就是被测的一部分**,不能同时充当"证据"和"结论"。规则给出的解决办法很直接:e2e 断言必须外部地(在测试代码里,独立于 agent 的任何输出)重新运行命令或重新读取文件,拿这个独立观测到的结果做断言;对于"不应该被改动的文件",要断言它们逐字节一致——防止 agent 通过篡改测试本身而不是修复 bug 来"通过"任务。

我们可以在一个真实文件里看到这条规则从"哲学"变成"代码"的过程。`examples/headless-agent/tests/coding-task.e2e.ts` 是一个 SWE-bench 风格的冒烟测试:让真实模型在一个临时目录里,只用 bash 工具修复一个真实的 bug,而修复结果**在 agent 之外**通过重新运行测试脚本来验证。文件开头的注释已经把这条原则写死在意图里:

```typescript
// examples/headless-agent/tests/coding-task.e2e.ts
/**
 * The swebench-style smoke test: a real model fixes a real bug in a temp
 * directory using only the bash tool, and the fix is verified OUTSIDE the
 * agent by re-running the test script. Key-gated.
 */
```

测试的核心断言部分是这样写的:

```typescript
// examples/headless-agent/tests/coding-task.e2e.ts
// The agent claims success…
const summary = finalText([...agent.session.events]).toLowerCase()
expect(summary.length).toBeGreaterThan(0)

// …and the world agrees: the test passes when WE run it, and the test
// file is byte-identical (an agent that neutered the test instead of
// fixing the bug fails here, not just on a keyword probe).
const untouchedTest = await readFile(join(workdir, 'add.test.js'), 'utf8')
expect(untouchedTest).toBe(TEST_FILE)

const after = spawnSync('node', ['add.test.js'], { cwd: workdir, encoding: 'utf8' })
expect(after.stdout).toContain('PASS')
expect(after.status).toBe(0)

const fixed = await readFile(join(workdir, 'add.js'), 'utf8')
expect(fixed).not.toMatch(/a\s*-\s*b/)
```

这几行代码把"验证外部世界"翻译成了四个具体动作,值得逐句拆开看:

- **对模型自己的输出只做最弱的健全性检查**:`expect(summary.length).toBeGreaterThan(0)` 只确认模型确实说了点什么,完全不检查它说了什么内容,更不会去搜索"成功""fixed"这类关键词。真正的判定权被彻底移出了模型的自我叙述。
- **断言不该被改动的文件逐字节一致**:`expect(untouchedTest).toBe(TEST_FILE)`,配合注释里那句"an agent that neutered the test instead of fixing the bug fails here"——如果模型选择了一条"作弊近路"(把测试文件改成永远通过,而不是真的修好 `add.js` 里的 bug),这行断言会立刻抓到它,而且抓住的不是"模型嘴上说了假话",而是"模型在世界里留下了错误的痕迹"。
- **在测试代码里重新运行命令,而不是相信 agent 已经运行过**:`spawnSync('node', ['add.test.js'], …)` 是测试自己发起的一次全新的进程调用,不依赖 agent 在会话里是否运行过、运行结果是什么。这就是"re-runs the command … externally"这句话的字面实现。
- **对修复后的代码本身做结构性断言**:`expect(fixed).not.toMatch(/a\s*-\s*b/)` 检查的是源码里那个具体的 bug 模式(`return a - b` 应该被改成 `return a + b`)是否真的消失了,而不是检查测试是不是"看起来"通过了。

值得注意的是,测试在调用 agent 之前还专门确认了 fixture 本身是坏的(`const before = spawnSync(...); expect(before.status).not.toBe(0)`)——这是"验证外部世界"原则的另一半:既要验证修复后的状态,也要验证修复前的状态确实处于"需要被修复"的起点,防止一个什么都没做的 agent 因为 fixture 本身凑巧能跑通而"通过"。

这条规则还带出一个容易被忽略的资源管理约定:"e2e tests own their resources: create the harness in the test, dispose in `afterEach` … shared fixtures live in a plain `tests/harness.ts`, never another `*.e2e.ts`"。`coding-task.e2e.ts` 里的 `afterEach` 精确对应这条约定:

```typescript
// examples/headless-agent/tests/coding-task.e2e.ts
afterEach(async () => {
  // Dispose the harness even on failure/retry: agent-loop teardown stops the
  // loop and LocalBashExecutor teardown kills anything the model left running.
  await ctx?.fiber.dispose()
  ctx = undefined
  if (workdir !== undefined) await rm(workdir, { recursive: true, force: true })
  workdir = undefined
})
```

这不是普通的测试卫生习惯,而是因为真实 API 测试会启动真实的子进程(bash 工具)和真实的临时目录——如果 dispose 只在测试成功时才执行,一次超时或断言失败就会在磁盘和进程表里留下垃圾,污染后续测试的运行环境。

### "Test the real entry path":为什么手工搭的插件测试不算数

`docs/testing.md` 单独用一节讲清楚了"真实入口路径"这件事,而这一节几乎是 postmortem 0001 事故的直接编纂结果:

> Product-visible plugins require a non-unit REAL-composition test. Hand-built `ctx.plugin(...)` suites are insufficient: boot test-only `cordis.yml` through Loader and app/process, mock only external services or nondeterministic inputs, and assert model-visible request/log, durable state, or user-visible output. Keep opt-ins out of shipped defaults.
>
> A guard only guards if the regression actually fails it. For a plugin without `inject` (bundle/composition plugins), a Loader smoke stays green when a default export replaces the required named exports — add an explicit `expect('default' in mod).toBe(false)` plus an `unwrapExports` round-trip assertion, and prove it: introduce the regression, watch red, revert.
>
> —— `docs/testing.md`

第一段规则针对的问题是:很多测试为了图方便,会在测试代码里手动拼一个插件对象直接塞进 `ctx.plugin({ name, inject, apply })`,绕开了产品实际使用的 Loader 加载流程。这样写出来的测试确实能验证插件内部逻辑,却完全无法验证"这个插件按产品真实的方式被加载时会不会出问题"——而恰恰是"按真实方式加载"这一步,才是 bug 藏身的地方。

postmortem 0001 把这个抽象规则变成了一个具体故事。ACP 插件 `packages/acp/acp/src/index.ts` 本该是一个"命名空间插件":把 `name`、`inject`、`Config`、`apply` 作为独立的具名导出,但代码里多出了一行别的插件都没有的 `export default apply`。Cordis Loader 在真实加载时会对模块做规范化:

> ```ts ignore-check
> unwrapExports(exports: any) {
>   if (isNullable(exports)) return exports
>   exports = exports.default ?? exports        // ← prefers `.default`
>   if (!exports.__esModule) return exports
>   return exports.default ?? exports
> }
> ```
>
> —— postmortem 0001 引用 `vendor/loader/src/index.ts`

存在默认导出时,`exports.default ?? exports` 解析出的是裸 `apply` 函数,而 `inject`/`name`/`Config` 作为*同级*具名导出全部被丢弃——`apply` 于是在一个**没有注入任何服务**的 fiber 里运行,第一行读取 `ctx.agents` 就直接抛出异常。这个 bug 只会在真实 Loader 加载路径上出现,而 178 个单元测试之所以全部绿灯,是因为它们全部通过手动构建的 `ctx.plugin({ name, inject, apply })` 挂载 bridge——**这行代码手动把 `inject` 喂给了 Cordis,而 `unwrapExports` 只在真实 Loader 里被调用**,`ctx.plugin` 从来不会走到这一步。也就是说,不是测试写少了,而是所有测试统一地避开了唯一会暴露 bug 的那条路径。

规则里"A guard only guards if the regression actually fails it"这句话,对应的正是这次事故留下的修复方法论:新增的守卫测试不能停留在"我觉得它能捕获问题",而必须真的把 bug 复现一遍、看着测试变红、再撤回去确认变绿——用实际红绿切换来证明这个守卫有效,而不是靠阅读代码"想象"它有效。postmortem 0001 里也确实记录了这一步:"已验证恢复 `export default apply` 时测试失败"。

### 覆盖率门禁的边界:它证明什么,不证明什么

`docs/testing.md` 在讲覆盖率门禁那一层时,提前埋下了一句提醒:"Line coverage is necessary, never sufficient — it proves lines ran, not that the feature works as shipped."postmortem 0001 用一个具体数字把这句话砸实了:

> 100% 行覆盖率始终满足。覆盖率证明代码行*被执行过*;它不能说明功能是否*按交付方式正常工作*。
>
> —— `docs/postmortem/0001-acp-default-export-drops-inject.zh.md`

这不是一句谦辞,而是这次事故里两个 bug 共同的解释:每一行代码确实都被执行过(所以覆盖率工具无话可说),但执行它们的方式(手工挂载插件、在根上下文里铺平所有服务)和产品真实运行的方式(经过 Loader 的 `unwrapExports`、经过 shadow 代理的祖先遍历)是两条完全不同的路径。覆盖率统计的是"哪些代码行被跑过",而不是"跑过这些代码行所依赖的前提条件是否和生产环境一致"。这也是为什么 `docs/testing.md` 会在覆盖率那一层专门补一句:"An uncovered line is often dead code the gate is correctly flagging for deletion, not a missing test to bolt on"——覆盖率门禁的正确用法是拿它去发现死代码,而不是拿它当作"功能已验证"的证书。

### 快照测试的强制触发条件:把"模型可见即已记录"落到测试义务上

`docs/testing.md` 还有一条容易被忽略、但和会话事件溯源设计直接呼应的规则:

> Every non-trivial model-, protocol-, or human-visible change adds or updates a keyless scenario in the same PR through a runnable example's owning snapshot suite. Package tests, e2e assertions, mock/test-only compositions, and PR rationale do not replace the assembled transcript; extend the harness when needed.
>
> —— `docs/testing.md`

这条规则表面上是一条测试流程要求,骨子里是把"模型可见的东西必须能被完整重建"这条架构不变量,转译成了一条对*测试*同样成立的义务:如果一次改动会影响模型看到的内容、协议消息或者用户可见的呈现,那么光靠包内单元测试、e2e 断言、或者 PR 描述里"我确认过没问题"这类理由都不够,必须在同一个 PR 里让某个可运行示例的快照套件真正跑出一份组装后的 transcript(文本记录)并把它提交进版本库。换句话说,"模型可见"这件事本身自带一条举证责任:任何声称改变了模型可见内容的改动,都要留下一份可以被后续任何人重新比对的具体证据,而不是停留在开发者自己的描述里——这和前一节讲的"验证外部世界,而非自我报告"其实是同一种不信任自我陈述的态度,只是这一次不信任的对象从"agent 的自我报告"换成了"PR 作者的自我陈述"。

## 常见问题/易踩坑

- **"既然要验证外部世界,是不是所有对模型输出的断言都不能要了?"** 不是。规则反对的是把关键词探测当作*唯一*或*核心*判据,不是禁止对模型输出做任何检查。`coding-task.e2e.ts` 里仍然保留了 `expect(summary.length).toBeGreaterThan(0)` 这样的健全性检查,只是它不承担"证明任务完成"的责任——这份责任被转移给了外部可观测的文件状态和进程退出码。
- **"无密钥测试跑通了,是不是说明这块逻辑没问题?"** 不能这么推。无密钥测试(单元测试、快照测试)证明的是"管路本身是通的"——协议编解码正确、fixture 回放确定、组合逻辑没有明显错误。它们和真实 API e2e 验证的是完全不同的东西,postmortem 0001 的教训正是:无密钥的 stdout 纯净性 e2e 测试全绿,却完全没有触达真正会崩溃的 `session/new`/`session/load` 路径,因为触达这条路径的测试恰好是需要 key 的那一个,而 CI 在无 key 时会跳过它。
- **"mock 掉 LLM 调用是不是总是安全的默认选择?"** 不是。mock 应该收窄到"确实昂贵或确实不确定"的边界(模型推理、网络、时钟),而不是被当作默认习惯用在所有测试上。对于产品最核心的承诺——agent 真的能驱动一个真实模型完成任务——只有带真实 API key 的冒烟测试才能验证,这也是"We are DeepSeek — do not ration real-API tests"这句话字面上要纠正的思维定势。
- **"手写一个逼真的 mock 插件对象是不是等价于真实加载?"** 不等价。只要挂载方式绕开了产品实际使用的 Loader/`unwrapExports`/服务解析路径,再逼真的 mock 对象也无法暴露"加载方式本身"引入的 bug。这正是"测试真实入口路径"这条规则存在的理由。

## 小结

DeepSeek Harness 的测试哲学可以归纳为一条主线:**agent 测试比传统软件测试多一个信任问题——被测系统自己也会生成一份看起来可信的成功报告,而这份报告不能被当作证据。**分层测试策略保证每一类证据都有唯一的、不可替代的来源;"不吝惜真实 API 测试"保证产品最核心的承诺被真实验证而不是被 mock 想象出来的行为顶替;"验证外部世界,而非自我报告"把判定权从模型的自我叙述转移到外部可观测的文件、进程、退出码;"测试真实入口路径"保证测试走过的加载方式和生产环境走过的加载方式是同一条路;覆盖率门禁则被明确限定在它真正能证明的范围内——代码跑过,不等于代码跑对。这四条规则不是空对空的教条,而是从一次真实的、100% 覆盖率却在生产环境秒崩的事故里蒸馏出来的具体防线。
