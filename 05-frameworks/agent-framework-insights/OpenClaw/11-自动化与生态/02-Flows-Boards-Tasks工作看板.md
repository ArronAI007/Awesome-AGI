# Task Flow、后台任务与 Workboard——三个容易被同名词汇误导的系统

> 如果只看目录名字猜测架构,很容易在 OpenClaw 里踩一个陷阱:`src/flows/` 听起来像"工作流引擎",`src/boards/` 听起来像"看板容器",两者加上 `src/tasks/` 拼在一起,顺理成章地猜成"flows 定义可复用流程、boards 是看板容器、tasks 是具体任务"这样一套整齐的三段式。但读完源码会发现真相并不是这样:`src/flows/` 其实是 `openclaw doctor` 的健康检查和 CLI 引导向导(渠道配置、模型选择这类一次性设置流程),和"任务编排"毫无关系;`src/boards/` 是会话仪表盘(dashboard)里那块承载 widget 的画布引擎,和"看板"这个中文直觉联想的 Kanban 完全是两回事。真正承担"多步骤工作编排"职责的,是 `src/tasks/` 目录下一个专门的子系统——Task Flow(前身叫 ClawFlow)。而用户在 Control UI 里能拖拽卡片、可能第一眼以为就是"任务看板"的 Workboard,又是一个完全独立的插件,自己有一整套 SQLite 表,和 Task Flow 之间只在"引用 ID"这个层面打过照面。本篇按实际代码把这几个系统的边界重新画清楚。

## 学习目标

- 能准确说出 `src/flows/`、`src/boards/`、`src/tasks/`、Workboard 插件这四个"名字容易关联、实现完全独立"的目录/系统各自的真实职责,不被目录名字误导。
- 理解后台任务(`openclaw tasks`)是"活动台账"而不是调度器——它记录已经发生的执行事实,不决定"何时执行"。
- 理解 Task Flow 的两种同步模式(`managed` / `task_mirrored`)分别对应"插件代码显式控制的多步流程"和"一次分离的 ACP/subagent 派生自动生成的单任务镜像"。
- 理解 Workboard 卡片如何通过 `taskId`/`sessionKey`/`runId` 这几个引用字段和后台任务、会话关联起来,同时明确这种关联止步于"引用",Workboard 自己的持久化状态、生命周期和权限模型完全不依赖 Task Flow 或 `src/boards`。
- 知道 Lobster 是什么、它在这套体系里处于哪个位置——它既不是 `src/flows`,也不是 Task Flow 本身,而是一个可选插件,提供"确定性多步骤 + 审批暂停 + 恢复令牌"的执行原语,常被 Task Flow 的 `managed` 模式拿来当执行引擎用。

## 背景与设计动机

上一篇讲的 automations 和 standing intents 解决的是"在什么条件下触发一次执行"。但触发之后呢?一次触发可能只是一句简单提醒(system event),也可能是一整条需要跨越多个子步骤、可能要等待人工审批、可能跨越多次 Gateway 重启才能走完的复杂流水线。如果每种"复杂执行"都各自发明一套状态机,系统会迅速失控;但如果只有一层笼统的"任务"记录,又无法表达"这五个子任务其实属于同一条正在进行的工作"这种结构性关系。

OpenClaw 的解法是把"记录发生了什么"和"编排多步骤应该怎么走"拆成两层:下层是后台任务(tasks)——一张不做任何调度决策、只管记录执行事实的台账;上层是 Task Flow——一层可以引用多个任务、有自己的状态机和版本号、能在 Gateway 重启后继续推进的编排记录。这个拆分本身和"Workboard 长什么样"没有关系——Workboard 是完全独立长出来的一块面向人类操作者的看板 UI,它选择了自己持久化卡片状态,而不是把 Task Flow 或 tasks 当成自己的后端存储。理解这一点,才能理解为什么下面几节读起来像是在讲三个不相关的系统,而不是一套三层架构。

## 核心机制详解

### 先排除一个陷阱:`src/flows/` 不是工作流引擎

`src/flows/` 目录下有 100 多个文件,但抽样看文件名就能确认它的真实职责——`doctor-health.ts`、`doctor-health-contributions.ts`、`doctor-lint-flow.ts`、`doctor-repair-flow.ts`、`channel-setup.ts`、`provider-flow.ts`、`model-picker.ts`、`search-setup.ts`。这些是 `openclaw doctor` 健康检查体系和交互式安装向导(渠道配置、模型选择、搜索提供商配置)的实现代码,"flow"在这里指的是"一次性引导流程"(setup flow),不是可复用的自动化工作流。这不是文档缺失或者笔误,而是这个词在英语工程惯用语里本来就有两种含义——"a flow"既可以指"一段数据/事件流",也可以指"一套多步骤的向导式交互"——OpenClaw 在这个目录里用的是后一种含义。如果按任务描述里的直觉去 `src/flows/` 里找"可复用的自动化流程定义",只会扑空。

### 后台任务(tasks):活动台账,不是调度器

`docs/automation/tasks.md` 在最开头就用一句加粗的提示排除了最常见的误解:

```
Looking for scheduling? See [Automation](/automation) for choosing the right
mechanism. This page is the activity ledger for background work, not the
scheduler.
```
—— `docs/automation/tasks.md`

后台任务记录的是"脱离主对话会话、在后台运行的工作"——ACP 派生、subagent 派生、automation 运行、CLI 发起的操作,以及 agent 自己发起的后台 `exec` 命令。心跳(heartbeat)轮次和普通交互式聊天**不**创建任务记录,这条边界文档专门强调了两遍。任务的生命周期是一个简单的五态机:

```
queued --> running : agent starts
running --> succeeded : completes ok
running --> failed : error
running --> timed_out : timeout exceeded
queued --> cancelled : operator cancels
running --> cancelled : operator cancels
queued --> lost : backing state gone > 5 min
running --> lost : backing state gone > 5 min
```
—— `docs/automation/tasks.md`

`lost` 这个状态值得展开讲,因为它体现了这套系统一个很谨慎的设计原则——"判断一个任务是否还活着"必须依赖对应运行时的权威信号,而不能只看某一行数据库记录是否还存在。文档对四种任务类型分别给出了不同的判活标准:ACP 任务只认 Gateway 进程内一个真实存在的 turn,持久化的会话元数据本身不构成证据;automation 任务要先看 automations 运行时是否还在跟踪这个 job,如果运行时状态已经清空,还要再去查持久化的运行历史里有没有终态结果,才能下"丢失"的结论;离线的 CLI 审计工具因此被特别要求"不能仅凭自己进程内的活跃任务集合为空,就断定 Gateway 拥有的某次运行已经结束"——这条限制是为了防止一个本地一次性运行的 CLI 审计工具,错误地把仍在真实 Gateway 里运行的任务标记为丢失。

任务表和 Task Flow 表都落在同一个共享 SQLite 里:

```
~/.openclaw/state/openclaw.sqlite   (tables: task_runs, task_delivery_state, flow_runs)
```
—— `docs/automation/tasks.md`

一个每 60 秒跑一次的清扫器(sweeper)负责对活跃任务做权威性核对、清理孤儿 ACP 会话、给终态任务打上 `cleanupAfter` 时间戳、按 7 天(`lost` 记录 24 小时)的窗口做最终清理。这一整套机制的核心立场是:任务记录本身从不主动决定"要不要重跑""要不要升级通知",它只负责如实反映"这份工作现在处于什么状态",调度决策永远留给 automations 或者发起方。

### Task Flow:tasks 之上的编排层,两种同步模式

`docs/automation/taskflow.md` 一句话给出了 Task Flow 的定位:"the orchestration layer above background tasks"。它有自己的表(`flow_runs`)、自己的状态机(比 tasks 多了 `waiting` 这个专属状态)、自己的版本号(`revision`),这些都独立于底层被它协调的具体任务:

```ts
// src/tasks/task-flow-registry.types.ts:7-18(节选)
export type TaskFlowSyncMode = "task_mirrored" | "managed";

/** Lifecycle statuses for multi-step task flows. */
export const TASK_FLOW_STATUSES = [
  "queued",
  "running",
  "waiting",
  "blocked",
  "succeeded",
  "failed",
  "cancelled",
  "lost",
] as const;
```

两种同步模式服务的是完全不同的使用场景。`task_mirrored` 是自动生成的——每当一次分离的 ACP 或 subagent 运行启动,OpenClaw 会自动建一条"一对一镜像"的 flow 记录,单纯是为了给这类派生执行提供一个稳定的状态查询句柄,不需要任何人显式驱动;`managed` 则要求有一个"controller"——插件代码显式创建 flow、携带一个 goal 和 controller id,然后自己驱动它在 running/waiting/终态之间推进,每次状态转移(`setWaiting`/`resume`/`finish`/`fail`/`requestCancel`)都必须携带上一次读到的 `revision`,版本冲突时必须重新读取而不是硬闯:

```
Durable state and revision tracking

Flow records persist in the shared SQLite state database ... so progress
survives gateway restarts. Each write bumps the flow's revision; concurrent
writers that pass a stale expected revision get a conflict and must re-read.
```
—— `docs/automation/taskflow.md`

managed 模式的典型执行引擎是 Lobster——一个独立的可选插件(`@openclaw/lobster`),专门做"确定性多步骤 pipeline + 审批暂停 + 恢复令牌"这件事,自己不属于 `src/flows/`,也不是 Task Flow 的一部分,而是被 Task Flow 拿来当"具体怎么一步步执行"的执行引擎用:

```
Lobster runs multi-step tool pipelines as one deterministic tool call, with
explicit approval checkpoints and resume tokens. It sits one layer above
detached background work: for orchestrating flows across many detached
tasks, see Task Flow (openclaw tasks flow); for the task activity ledger,
see Background Tasks (openclaw tasks).
```
—— `docs/tools/lobster.md`

`docs/automation/taskflow.md` 给出的"可靠的定期工作流"模式,把这四层的分工排成了一条清晰的因果链:automations 负责钟点,一个持久化的 automation session 负责让流程在多次运行之间保留上下文,Lobster 负责确定性步骤和审批闸门,Task Flow 负责跨多个子任务、多次等待、多次 Gateway 重启的整体追踪:

```
1. Use Automations for timing.
2. Use a persistent automation session when the workflow should build on prior context.
3. Use Lobster for deterministic steps, approval gates, and resume tokens.
4. Use Task Flow to track the multi-step run across child tasks, waits, retries, and gateway restarts.
```
—— `docs/automation/taskflow.md`

### Workboard:一个自成一体的看板插件,只在引用层面接触前两者

Workboard(`extensions/workboard/`,契约类型定义在 `packages/workboard-contract/src/index.ts`)是完全独立的一个 bundled 插件,不是"boards"目录的产物,和 Task Flow 也没有代码依赖关系。它的卡片状态机是九态 Kanban:

```ts
// packages/workboard-contract/src/index.ts:2-12(节选)
export const WORKBOARD_STATUSES = [
  "triage",
  "backlog",
  "todo",
  "scheduled",
  "ready",
  "running",
  "review",
  "blocked",
  "done",
] as const;
```

Workboard 有自己的 SQLite 表(boards、cards、labels、lifecycle events、run attempts、comments、dependency links、proof、artifact、attachment、diagnostics、notifications、worker logs——文档原话是"Workboard tables (not plugin key-value entries)"),自己的调度批次上限(默认每次调度最多启动 3 个 worker,这个数字直接写在源码常量里而不只是文档里):

```ts
// extensions/workboard/src/dispatcher.ts:34行
const DEFAULT_DISPATCH_MAX_STARTS = 3;
```

它和"后台任务"以及"会话(session)"之间的联系,止步于卡片上几个引用字段——`taskId`、`sessionKey`、`runId`、`execution`(引擎/模式/模型/会话/运行 id/状态)。当你从一张卡片点击"Run Claude"或"Run OpenAI",Workboard 走的是"Gateway 的 task-tracked agent run 路径"去真正启动执行,然后把返回的 task、run id、session key 写回卡片,再靠一个每分钟跑一次的会话生命周期同步(session lifecycle sync)把 Gateway 侧的会话状态映射回卡片状态:

```
| Linked session state                  | Card status |
| -------------------------------------- | ----------- |
| active                                 | `running`   |
| completed                              | `review`    |
| failed, killed, timed out, or aborted  | `blocked`   |
```
—— `docs/plugins/workboard.md`

换句话说,Workboard 卡片"看起来"很像一条被编排的 Task Flow,但它自己并不使用 Task Flow 的 `flow_runs` 表、不使用它的 `revision` 并发控制,而是完全平行地重新实现了一套(更简单的)状态同步机制,只在数据层面通过 id 引用 tasks 系统里已经存在的任务记录。这不是缺陷,而是一个刻意的边界:`docs/plugins/workboard.md` 明确把 Workboard 定位为"intentionally small: it tracks local operating work for one OpenClaw Gateway. It is not a replacement for GitHub Issues, Linear, Jira, or other team project management systems"——它是操作者可视化的一层皮,不试图成为通用编排引擎。

Workboard 自己的诊断机制也印证了这种"独立自愈"的设计——它不依赖 Task Flow 的 `stale_running`/`stale_waiting` 检测,而是自己算一套等价的规则:

| Kind | Condition |
| --- | --- |
| `stranded_ready` | Assigned `todo`/`backlog`/`ready` card not updated in over 1 hour |
| `running_without_heartbeat` | `running` card with no claim heartbeat or execution update in over 20 minutes |
| `blocked_too_long` | `blocked` card not updated in over 24 hours |
| `orphaned_session` | `running` card with a `sessionKey` but no `execution` metadata |
—— `docs/plugins/workboard.md`

### `src/boards/`:另一个完全不相关的"board"——会话仪表盘的画布引擎

最后要单独澄清 `src/boards/`,因为它的英文名字和 Workboard 的"board"用的是同一个词,却指向另一个产品面。`docs/web/dashboards.md` 说得很清楚,每个会话线程都可以拥有一个"dashboard"——一块由 agent 用 `dashboard` 工具动态"钉"上 widget 的画布:

```
Every thread in the Control UI can own a dashboard — a grid of live widgets
your agent builds for you.
```
—— `docs/web/dashboards.md`

`src/boards/board-store.ts` 里管理的 `BoardSnapshot`/`BoardWidgetPutResult`/`BoardWidgetHtmlDocument` 这些类型,对应的正是这块画布上"每个 widget 的 HTML 文档、修订版本、grant 状态"这类底层存储,和 GitHub Actions capability、widget 布局预设(`BOARD_SIZE_PRESETS`)绑在一起——是仪表盘 widget 引擎,不是任务看板。有意思的是,Workboard 插件本身还反过来是这套 dashboard widget 机制的一个消费者:它提供了 `workboard:card`、`workboard:board`、`workboard:mini` 三个原生 widget 类型,可以被"钉"进某个会话的 dashboard 里(`docs/plugins/workboard.md` 的"Session-board widgets"一节),这时候"widget board"(`src/boards/`)和"Kanban board"(Workboard)才第一次在 UI 层面产生交集——但依然是"Workboard 把自己渲染成 dashboard 上的一块 widget",而不是两套存储合并成了一套。

## 常见问题/易踩坑

- **不要以为 `src/flows/` 是工作流引擎**:它是 doctor 健康检查和 CLI 引导向导的实现目录,和"多步骤任务编排"没有关系。真正的编排层是 `src/tasks/` 下的 Task Flow(`task-flow-registry*.ts`)。
- **不要以为 `src/boards/` 就是 Workboard 的后端**:两者共享"board"这个英文词,但 `src/boards/` 管的是会话仪表盘的 widget 画布,Workboard 有自己完全独立的 SQLite 表。
- **不要把 Task Flow 和 Workboard 当成同一套编排系统的两个视图**:Workboard 卡片只是通过 `taskId`/`sessionKey`/`runId` 引用 tasks 系统里的记录,自己的看板状态机、诊断规则、调度批次上限都是独立实现的,并不读写 `flow_runs` 表。
- **不要混淆 Lobster 和 Task Flow**:Lobster 是"怎么把一串确定性步骤跑完并在需要时暂停审批"的执行引擎,Task Flow 是"如何跟踪一条可能横跨多次执行、多次等待、多次重启的工作整体状态"的编排记录——两者常常搭配使用(managed 模式下 Lobster 驱动 Task Flow 的状态转移),但分别解决不同层次的问题。
- **文档已经明确承认关系不总是整齐的**:`docs/automation/tasks.md` 和 `docs/automation/taskflow.md` 都在反复强调"flows coordinate tasks, not replace them"——这是一条组合关系,不是一条继承或包含关系,如果代码或文档没有把某两个系统的边界说清楚,不应该替它们编造一个更整齐的分工故事。

## 小结

这一篇最重要的收获,可能不是记住某个具体的状态机,而是"名字相似不等于职责相关"这条排查习惯本身:`src/flows/` 是引导向导,`src/boards/` 是仪表盘画布,真正的多步骤编排藏在 `src/tasks/` 里的 Task Flow;而用户在 UI 上最直观接触到的 Workboard,又是一个刻意保持独立、只靠 id 引用和其他系统打交道的看板插件。三者合在一起构成的不是一套单一架构,而是"总控保持精简、复杂能力允许各自成一体地生长"的具体案例——这也正是下一篇要展开的主题:OpenClaw 到底是怎么系统性地决定"一个能力应该长在核心里,还是应该长在插件生态里"的,而承接这套治理哲学的落地渠道,就是 ClawHub。
