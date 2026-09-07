# Soul 与 Dreaming:人格与长期演化的真相

> 这两个名字都很容易引发过度解读。"Soul"听起来像是某种持久化的人格状态机,"Dreaming"听起来像是模型在后台"做梦生成幻想内容"。读完 `docs/concepts/soul.md` 和 `docs/concepts/dreaming.md` 的真实描述后,答案要朴素得多也严谨得多:`SOUL.md` 是一份 83 行的、需要人手动编辑的"语气风格指南",不涉及记忆写入,也不会自己演化;Dreaming 则是一套三阶段、可审查、有明确安全关卡的后台批处理管线,借用的是"睡眠巩固记忆"这一研究类比,不是字面意义上的生成式联想。这篇把两者的真实机制讲清楚,再看 `USER.md` 用户模型如何和它们配合,构成"同一个助理长期使用会越来越懂你"这件事的实际实现。

## 学习目标

- 准确理解 `SOUL.md` 的定义边界:它是注入到高优先级指令层的"声音"文件(语气、观点、简洁度、边界),不是记忆系统,也不持久化任何"人格演化"状态——它就是一份需要人编辑、被完整读入上下文的静态文件。
- 理解 `SOUL.md` 和 `AGENTS.md` 的分工原则,以及为什么"人格"不应该被塞进操作规则文件。
- 理解 Dreaming 的真实字面动作:三阶段(light/REM/deep)后台整理,只有 deep 阶段能写 `MEMORY.md`,且要经过"确定性阈值门槛"和"tool-free 整理生成"两道关卡。
- 理解 Dreaming 为什么叫这个名字——它对应的是 sleep-time compute 论文的类比,而不是任何"生成幻觉内容"的机制;同时理解它解决的具体工程问题:避免记忆无限堆积、避免把整理这件重活压到回复路径上。
- 理解 `USER.md` 用户模型如何与 Soul、Dreaming 配合,分别承担"语气一致""事实沉淀""偏好沉淀"三种不同职责,共同构成长期"越来越懂你"的效果。

## 背景与设计动机

`soul.md` 的开篇动机说得很直接——对抗"generic assistant sludge"(千篇一律的助理腔调):

> `SOUL.md` is where your agent's voice lives. OpenClaw injects it into normal sessions, so it carries real weight: if your agent sounds bland, hedgy, or corporate, this is usually the file to fix.

它引用的依据是 OpenAI 的 prompt engineering 指南,把"高层行为、语气、目标、示例"归为高优先级指令层,而不是散落在用户轮次里的临时措辞,并且强调这类指令应该被迭代、固定版本、持续评估,而不是写一次就扔在那儿:

> This lines up with OpenAI's prompt guidance: high-level behavior, tone, goals, and examples belong in the high-priority instruction layer, not buried in the user turn, and prompts should be iterated on, pinned, and evaluated rather than written once and forgotten.

Dreaming 的动机则来自完全不同的研究脉络。第二篇提到的核心原则——"写入时机比检索算法更重要"——在这里进一步落地成一个具体判断:与其让模型在每次回复时零散地判断"这句话该不该记住",不如把这件事挪到一个专门的后台阶段,批量、有节制地处理:

> This background pattern follows the motivation behind sleep-time compute (arXiv:2504.13171). Provenance-aware reflection also follows the durable memory lessons of the Generative Agents research.

这条"把整理挪到后台"的思路,恰好呼应了它的命名——"Dreaming"取的是"睡眠期间巩固白天记忆"这个类比,而不是字面上的"生成梦境内容"。下面逐条核对这个类比在实现里到底是怎么落地的。

## 核心机制详解

### `SOUL.md`:一份关于"声音"的文件,不是关于"记忆"的文件

`soul.md` 对该写什么、不该写什么划得很清楚:

> Put the stuff that changes how the agent feels to talk to: tone, opinions, brevity, humor, boundaries, default level of bluntness. Do **not** turn it into a life story, a changelog, a security policy dump, or a wall of vibes with no behavioral effect.

也就是说,`SOUL.md` 的作用域被严格限定在"语气层面的行为差异"上——它不是用来记录用户偏好的地方(那是 `USER.md` 的职责,下文会讲),也不是安全策略文档,更不是变更日志。文档给出的一个具体操作示例("Molty prompt")能帮助理解它的实际使用方式——它是一份**可以整体重写、需要人主动编辑或指示 agent 重写**的静态文件:

```md
Read your `SOUL.md`. Now rewrite it with these changes:
1. You have opinions now. Strong ones. Stop hedging everything with "it depends" - commit to a take.
2. Delete every rule that sounds corporate...
```

这个例子本身就说明了 `SOUL.md` 的本质:它没有自动演化机制,没有"根据历史交互自动调整语气"的后台流程,调整完全依赖显式编辑(哪怕这次编辑是"让 agent 帮我重写一遍")。这一点和 Dreaming 形成了鲜明对比——Dreaming 会自动把 episodic 层的信号提炼进 `MEMORY.md`/`USER.md`,而 `SOUL.md` 没有对应的自动晋升通路,它就是被完整注入到 system context 的一份固定文本。

文档也明确划出了它和 `AGENTS.md` 的分工边界:

> Keep `AGENTS.md` for operating rules; keep `SOUL.md` for voice, stance, and style. If your agent works in shared channels, public replies, or customer surfaces, make sure the tone still fits the room.

这条分工原则说明,OpenClaw 把"操作规则"(能做什么、怎么做)和"表达风格"(怎么说话)拆成了两份完全独立的文件,分别对应"能力边界"和"呈现方式"两类完全不同性质的约束。把这条线画清楚,是为了避免"改语气顺带改了权限""改权限顺带改了语气"这类耦合出的意外行为——这也符合本章第一篇提到的整体设计取向:每个层级都职责单一、可独立编辑。

需要特别指出的是:相比某些基于 OpenClaw 二次开发的衍生 App(比如把 `soul.md` 作为专属人格包装层),`SOUL.md` 是 OpenClaw **核心自带**的通用概念,不属于任何特定衍生产品——但它的实现本身依然朴素:一份被读入高优先级指令层的静态 Markdown 文件,没有独立的存储引擎,没有版本演化状态机,复杂度全部让位给了内容本身怎么写。

### Dreaming:三阶段后台整理,而不是"生成幻觉"

`dreaming.md` 对这套机制的定位是"`memory-core` 里的后台记忆整理系统",默认开启:

> Dreaming is the background memory consolidation system in `memory-core`. It moves strong short-term signals into durable memory while keeping the process explainable and reviewable.

它按固定顺序跑三个阶段,只有最后一个阶段有权写 `MEMORY.md`:

| 阶段 | 目的 | 是否写 `MEMORY.md` |
|---|---|---|
| Light | 整理和暂存最近的短期材料 | 否 |
| REM | 反思主题和反复出现的想法 | 否 |
| Deep | 打分并晋升持久候选项 | 是 |

Light 阶段负责去重、暂存候选行,并为 Deep 阶段的排序记录强化信号;REM 阶段构建主题和反思摘要,记录自己的强化信号。两者都明确"从不写入 `MEMORY.md`"。真正的晋升发生在 Deep 阶段,而且要连续通过两道关卡:

**第一道:确定性打分门槛。** Deep 阶段用六个加权信号给候选项打分:

| 信号 | 权重 | 说明 |
|---|---|---|
| Relevance | 0.30 | 检索质量的平均水平 |
| Frequency | 0.24 | 短期信号的累积次数 |
| Query diversity | 0.15 | 命中它的不同查询/日期上下文数量 |
| Recency | 0.15 | 随时间衰减的新鲜度分数 |
| Consolidation | 0.10 | 跨多日反复出现的强度 |
| Conceptual richness | 0.06 | 片段/路径里的概念标签密度 |

必须同时通过 `minScore`、`minRecallCount`、`minUniqueQueries` 三个阈值,而且——这一点是本篇第二篇讲过的安全边界的延续——来源类别为 `untrusted` 或 `system` 的候选项在打分之前就被结构性剔除,不是打分打低了才被淘汰:

> Before building the consolidation prompt, `memory-core` removes candidates whose indexed provenance is `untrusted` or `system`. This is a structural taint gate, not a score penalty.

**第二道:tool-free 的整理生成步骤。** 通过打分门槛的候选项,连同当前 `MEMORY.md`,一起交给一次不带工具调用的模型补全,由模型决定合并、取代、还是新增,但模型产出的不是"替换文本",而是**操作决策**,由确定性代码去应用:

> The model returns operation decisions, not replacement memory prose. The memory writer applies those decisions to the existing file using each candidate's bounded, sourced entry.

这次重写还要满足结构性校验才会被接受:

```text
# docs/concepts/dreaming.md
- preserve prior entries within phases.deep.maxPriorEntryLossFraction
- include every promoted candidate's Source: path#Lx-Ly reference
- stay within the MEMORY.md bootstrap-safe file budget
- parse as the expected structured response
```

任意一条不满足,这次重写就会被拒绝,退回到"仅追加"的旧行为,而不是让一次不合格的整理污染 `MEMORY.md`。写入本身还用了乐观并发控制:提交前重新校验一次内容哈希,如果文件在整理期间被别的东西改过,这次重写直接放弃,改用追加兜底:

> Write safety. Replacing `MEMORY.md` uses optimistic concurrency: the content hash captured when consolidation input was built is re-checked immediately before an atomic rename... The pre-image of every accepted rewrite is stored, and a human-readable summary of what changed is appended to `DREAMS.md`.

这一整套"打分门槛 + tool-free 决策 + 结构校验 + 乐观并发 + 前像存档"的组合,正是"Dreaming"这个名字在工程上的真实含义——它解决的实际问题是**记忆无限堆积**(短期信号如果照单全收会让 `MEMORY.md` 越滚越大)和**回复路径过载**(如果让每次回复都顺手判断"这句话该记吗",会让主对话变慢、变得不确定)。把这件事挪到一个有明确调度节奏(默认 cron `0 3 * * *`,每天跑一次)、且全过程留痕在 `DREAMS.md` 里的后台批处理,恰好对应"睡眠时巩固白天记忆"这个类比——不是生成新内容,而是筛选、去重、提炼已经发生过的信号。

### 两条独立的复盘通道:live dreaming 与 grounded backfill

`memory.md` 里还提到 dreaming 系统有两条并行但用途不同的复盘通道,容易被混淆:

> Live dreaming works from short-term dreaming state in SQLite plugin storage and is what the normal deep phase uses to decide what graduates into `MEMORY.md`... Grounded backfill reads historical `memory/YYYY-MM-DD.md` notes as standalone day files and writes structured review output into `DREAMS.md`.

Live dreaming 是前面讲的"每日自动跑一次"的正常路径;grounded backfill 则是一个手动触发的回放工具,用来"重新过一遍历史笔记,看看系统认为哪些内容值得沉淀",但它默认只写到 `DREAMS.md` 供人审阅,即便加上 `--stage-short-term` 参数,也只是把候选项塞进和 live dreaming 共用的短期评分池里,并不会绕过 Deep 阶段直接写 `MEMORY.md`:

> `MEMORY.md` is still only written by deep promotion.

这条设计再次印证了同一条原则:无论信号从哪条通道进来,晋升到长期记忆的**唯一**入口始终是 Deep 阶段的那两道关卡。

### `USER.md`:和 Soul、Dreaming 三方配合的用户模型

`user-model.md` 把 `USER.md`定位为"稳定偏好、沟通风格、关系、活跃项目上下文"的指令式条目集合,和 `MEMORY.md` 分开存在的理由是:偏好遵循和事实回忆这两种能力会以不同方式失效——

> `USER.md` is a separate curated file for the user model: stable preferences, communication style, relationships, active projects. It exists apart from `MEMORY.md` because preference adherence and fact recall fail differently.

它引用的 PrefEval 研究发现,模型在对话变长后会逐渐"忘记"仅仅存在于上下文里的偏好,而在查询附近**重新陈述**该偏好比更重的检索或自我批判机制更能恢复遵循度。这直接决定了 `USER.md` 的写法规范——条目必须是祈使句式的指令("Always"/"Never"/"Prefer"),而不是"用户曾经说过"这种叙述式观察:

```md
<!-- observed: 2026-07-27 | status: active -->
- Prefer concise progress updates during implementation work.
```

偏好变化时,规则是**原地取代**而不是追加一条新指令,理由同样来自研究证据——追加式的矛盾历史会导致模型选中"最初陈述的偏好"而不是当前生效的那条:

> HorizonBench reports that systems often select an originally stated preference after the user has changed it... append-only contradictory history recreates that failure mode.

把三份文件放在一起看,分工就非常清楚了:

- **`SOUL.md`**——语气和姿态,静态编辑,不参与记忆写入或晋升流程,保证这个助理"听起来"是同一个人。
- **`USER.md`**——稳定偏好和身份画像,由 dreaming 或用户直接请求写入,原地取代式更新,保证"该怎么对待你"这件事不会因为对话变长而漂移。
- **`MEMORY.md`**——持久化的非画像类事实和决策,由 Deep 阶段的整理管线从每日笔记里提炼晋升,保证"发生过什么、决定过什么"能长期留存而不需要用户重复讲。

"同一个助理长期使用会越来越懂你"这句产品叙事,拆解到工程实现上,其实是这三份文件在各自职责范围内独立演化的结果:Dreaming 负责把 episodic 层的原始信号,持续、有节制地提炼进 `USER.md` 和 `MEMORY.md`;`SOUL.md` 保证这个提炼过程不会连带改变说话的方式。三者没有一个是"自动学习的黑箱模型状态",全部是可以打开文本编辑器直接读、直接改的 Markdown 文件——这也回到了本章第一篇开头那条最基本的原则:无隐藏状态。

## 小结

这一篇纠正了两个容易被名字误导的概念:`SOUL.md` 不是持久化人格系统,而是一份需要人工编辑、被完整注入高优先级指令层的语气风格文件,和记忆系统没有直接的读写关系;Dreaming 也不是生成幻觉内容的机制,而是三阶段(light/REM/deep)的后台批处理,只有 Deep 阶段能晋升记忆,且要连续通过"确定性打分门槛"和"tool-free 整理生成 + 结构校验"两道关卡,目的是解决记忆无限堆积和回复路径过载这两个具体工程问题。`USER.md` 用户模型则和它们分工协作——语气交给 Soul,偏好交给用户模型的原地取代式更新,事实沉淀交给 Dreaming 驱动的 `MEMORY.md` 晋升,三者共同构成了长期使用"越来越懂你"的实际实现,而底层始终是可审查、可编辑的 Markdown 文件,没有隐藏状态。

下一章会转向安全与沙箱——这套系统在把真实设备、账号能力交给 Agent 的同时,是怎样控制风险边界的。
