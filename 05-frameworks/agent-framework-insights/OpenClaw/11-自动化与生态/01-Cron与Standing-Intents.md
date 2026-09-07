# Cron 与 Standing Intents——两种"记住要做什么"的机制

> `docs/concepts/standing-intents.md` 开篇一句话划清了两件事的边界:"Standing intents are prospective memory. They remember what to do when a trigger appears; they do not schedule work for a clock time."(常驻意图是前瞻性记忆,它们记住"触发条件出现时该做什么",而不是"在某个钟点该做什么")。这句话反过来读同样成立:OpenClaw 的 automations(也就是 cron)记住的正是"在某个钟点该做什么",却完全不管"某个条件出现时该做什么"。两套机制分别扎根在两张完全不同的存储结构里——automations 落在 Gateway 共享 SQLite 的任务表里,由一个精确到毫秒的定时器驱动;standing intents 落在每个 agent 私有的 SQLite 里,由一张 FTS5 全文索引表在每次用户发言时做确定性前缀匹配。本篇把这两套机制分别拆开,再看清楚它们各自解决的是哪类"记住要做什么"的问题。

## 学习目标

- 理解 OpenClaw automations 支持的五种调度类型(`at`/`every`/`cron`/`on-exit`/`stream`)分别对应什么触发语义,以及为什么日期与星期字段同时非通配时会按"或"逻辑触发而不是"且"逻辑。
- 理解 automations 的调度器是"为每个到期任务精确计算下一次触发时间并直接设置一个定时器"(timer-based),而不是固定周期轮询(poll-based),这与它四个 payload 类型(system-event/agentTurn/command/script)如何共享同一套执行体没有关系,却决定了它的时间精度。
- 完整复述 standing intent 的匹配算法:FTS5 前缀过滤 → 按 `created_at`/`id` 游标分页扫描、每次最多 256 个候选 → 逐条在同一事务里核对 scope/cooldown/fire budget/关键词全匹配 → 命中后立即原地推进 `fire_count`。
- 理解 standing intent 的注入预算(最多 3 条、渲染后不超过 1200 字符)为什么必须在扫描阶段就参与筛选,而不是等扫描完再截断。
- 能区分三种"记住"的层级——cron(钟点)、standing intent(事件)、standing orders(权限与流程,写在 `AGENTS.md` 里的常驻文字指令)——并知道为什么后两者经常被读者混为一谈。

## 背景与设计动机

几乎每个能自主运行的 agent 框架都会遇到同一个需求缺口:用户说"每天早上 8 点提醒我看日历"很好办,写一条 cron 表达式就行;但用户说"下次有人提到发布候选版本,提醒我确认回滚负责人"就完全不是钟点问题——它没有固定的时间点,只有一个可能几小时后、也可能几周后才会出现的"事件"。如果没有专门机制,这类请求只能退化成两种蹩脚的实现:要么让 agent 把它写进某个长期记忆文件,指望未来某次对话恰好把这段文字带回上下文(TriggerBench 的研究结论是,这种"前瞻性回忆"会随着上下文变长而系统性衰减,`docs/concepts/standing-intents.md` 直接引用了这篇论文:"prospective recall decays as context grows and can drift into an always-remind heuristic"[arXiv:2606.23459]);要么每隔几分钟轮询一次去检查条件是否成立,这又变成了一个新的 cron 任务,只是判断逻辑被塞进了脚本里。

OpenClaw 的做法是把这两类需求彻底拆成两套独立的存储和执行路径,而不是让一套机制多任务地兼顾"钟点"和"事件"。automations 是本文重点之一,负责一切能提前算出下一次触发时间的场景;standing intents 是另一个重点,只负责"某个关键词/条件在未来某次对话里出现"这一类无法预先定时的场景。两者共享的只有一件事——它们都在描述"agent 应该在没有人当场催促的情况下,主动做点什么",这也是本章标题"自动化"的含义所在。

## 核心机制详解

### Automations:五种调度类型与一套共享执行体

`docs/automation/cron-jobs.md` 把 automations 定义为"OpenClaw's built-in scheduler",并且明确指出它跑在 Gateway 进程内部而不是模型里:

```
Automations run **inside the Gateway process**, not inside the model. The Gateway
must be running for schedules to fire.
```
—— `docs/automation/cron-jobs.md`

调度类型一共五种,`--cron`/`--every`/`--at`/`--on-exit`/`--stream-command`,对应表格如下(节选自 `docs/automation/cron-jobs.md` 的 Schedule types 一节):

| Kind | Description |
| --- | --- |
| `at` | One-shot timestamp |
| `every` | Fixed interval |
| `cron` | 5/6-field cron expression |
| `on-exit` | Fire once when a watched command exits |
| `stream` | Fire from batched lines produced by a supervised long-lived command |

前三种是纯粹的"钟点"语义,后两种已经带有一点"事件"的味道——`on-exit` 在一个被监视的命令退出时触发一次,`stream` 则从一个长期运行的被监督子进程的 stdout/stderr 里按行或按正则匹配触发。这一点很容易让读者以为 automations 已经能够处理事件,但仔细看文档会发现这两种仍然属于"你必须先显式配置一个具体的外部进程/命令去监视"的范畴,和 standing intent"用户随口一句话就地声明一个关键词条件"完全不是一回事——后面会展开这个对比。

调度器本身是精确定时,而不是固定周期轮询。这与 Hermes-Agent 那种"gateway 反正要一直跑着,顺手每 60 秒检查一次"的设计不同(参见姊妹项目 Hermes-Agent 第九章对 `cron/scheduler.py::tick()` 的分析):OpenClaw 的 `armTimer()` 直接为下一次到期任务设置一个 JS 定时器:

```ts
// src/cron/service/timer-scheduler.ts:53-58(节选)
export function armTimer(state: CronServiceState) {
  if (state.timer) {
    clearTimeout(state.timer);
  }
  state.timer = null;
  if (state.stopped || state.schedulingPaused || state.startupCatchup) {
```

这不是巧合——OpenClaw 的部署模型默认假设 Gateway 进程本身是常驻的(桌面应用、自托管服务器),没有"按使用量计费的托管平台需要 scale to zero"这个前提,所以不需要像 Hermes 的 Chronos 那样把触发权外包给云端账户服务;直接算出下一次 `next_run_at` 并设一个精确定时器,反而比固定轮询更省资源、延迟更低。

四种 payload 类型共享的是"到期之后做什么"这一层,和"什么时候到期"完全解耦:

| Payload | Flag | Runs |
| --- | --- | --- |
| System event | `--system-event <text>` | Enqueued into the main session, no model call by itself |
| Agent message | `--message <text>` | A model-backed agent turn |
| Command | `--command <shell>` | A shell/process on the Gateway host, no model call |
| Script | `--script <file\|->` | A headless code-mode script using the owning agent's tools |
—— `docs/automation/cron-jobs.md`

值得单独记一笔的是文档里那条"day-of-month 和 day-of-week 同时非通配时按或逻辑触发"的陷阱,因为它是几乎所有基于 Vixie cron 语义的系统里最容易被误用的一条:

```
# Intended: "9 AM on the 15th, only if it's a Monday"
# Actual:   "9 AM on every 15th, AND 9 AM on every Monday"
0 9 15 * 1
```
—— `docs/automation/cron-jobs.md`

这条表达式的直觉读法是"每月 15 号且恰好是周一才触发",真实语义却是"每月 15 号触发,以及每周一也触发",一个月里可能触发五六次而不是零到一次。OpenClaw 用的 `croner` 库支持一个非标准的 `+` 修饰符(`0 9 15 * +1`)来强制"且"语义,但默认行为仍然是标准 cron 的"或"逻辑,这是文档专门拿出来提醒读者的一条"易踩坑"。

### Standing Intents:事件条件式的前瞻性记忆

Standing intent 的存储结构本身就说明了它的设计取向。它落在每个 agent 私有的 `agents/<agentId>/agent/openclaw-agent.sqlite` 里(不是共享状态库),表结构里除了常规字段外,专门配了一张 FTS5 虚拟表:

```sql
-- src/state/openclaw-agent-schema.sql:611-630(节选)
CREATE TABLE IF NOT EXISTS standing_intents (
  intent_key INTEGER PRIMARY KEY,
  id TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL,
  trigger_keywords TEXT NOT NULL,
  ...
  status TEXT NOT NULL CHECK (status IN ('pending', 'armed', 'fired', 'done', 'cancelled', 'expired')),
  expires_at INTEGER NOT NULL,
  max_fires INTEGER NOT NULL CHECK (max_fires > 0),
  fire_count INTEGER NOT NULL DEFAULT 0 CHECK (fire_count >= 0),
  cooldown_seconds INTEGER NOT NULL DEFAULT 86400 CHECK (cooldown_seconds >= 0),
  last_fired_at INTEGER,
  ...
) STRICT;

CREATE VIRTUAL TABLE IF NOT EXISTS standing_intents_fts USING fts5(
  trigger_keywords,
  content = 'standing_intents',
  content_rowid = 'intent_key',
  tokenize = 'unicode61 remove_diacritics 2'
);
```

这张表和它的 FTS5 影子表(`standing_intents_fts_config`/`_data`/`_docsize`/`_idx`)不是随 Gateway 启动就创建的,而是"首次用到这个功能才建表"——`ensureOpenClawAgentStandingIntentsSchema()` 每次调用前都先检查表是否存在:

```ts
// src/state/openclaw-agent-standing-intents-schema.ts:42-52(节选)
export function ensureOpenClawAgentStandingIntentsSchema(db: DatabaseSync): void {
  const ensure = () => {
    db.exec(standingIntentsSchemaSql()); // sqlite-allow-raw -- Canonical additive DDL only.
    ensureStandingIntentCreatorColumn(db);
  };
  if (db.isTransaction) {
    ensure();
    return;
  }
  runSqliteImmediateTransactionSync(db, ensure);
}
```

真正的匹配逻辑在 `extensions/memory-core/src/standing-intents.ts` 里,是一整套"先用 FTS5 粗筛、再逐条精确核验"的两阶段设计。第一阶段把用户这一轮发言分词后,拼成一个 `OR` 连接的 FTS5 查询:

```ts
// extensions/memory-core/src/standing-intents.ts:353-363(节选)
function tokenizeIntentText(text: string): string[] {
  return text.toLowerCase().match(/[\p{L}\p{N}_-]+/gu) ?? [];
}

function buildFtsQuery(promptTokens: ReadonlySet<string>): string | null {
  const unique = [...promptTokens];
  if (unique.length === 0) {
    return null;
  }
  return unique.map((token) => `"${token.replaceAll('"', '""')}"`).join(" OR ");
}
```

注意这一步只是粗筛,真正决定"是否命中"的是第二阶段的 `triggerMatchesPrompt`——它要求候选意图的 trigger keywords 里**至少有一组关键词的全部 token** 都出现在这句话里,而不是"任意一个词命中就算数":

```ts
// extensions/memory-core/src/standing-intents.ts:365-372(节选)
function triggerMatchesPrompt(row: StandingIntentRow, promptTokens: ReadonlySet<string>): boolean {
  return parseStoredTriggerKeywords(row.trigger_keywords)
    .map((keyword) => tokenizeIntentText(keyword))
    .some(
      (keywordTokens) =>
        keywordTokens.length > 0 && keywordTokens.every((token) => promptTokens.has(token)),
    );
}
```

匹配主流程 `matchStandingIntents()` 把"至多扫描 256 个候选、至多命中 3 条"这两条硬上限写死成常量,并用游标分页(按 `created_at`、`id` 排序)一批一批地拉候选,避免一次性把某个噪声很大的触发集合全部拉进内存:

```ts
// extensions/memory-core/src/standing-intents.ts:15-18(节选)
const INTENT_MATCH_CANDIDATE_BATCH_SIZE = 32;
const INTENT_MATCH_CANDIDATE_LIMIT = 256;
const INTENT_INJECTION_MAX_COUNT = 3;
export const INTENT_INJECTION_MAX_CHARS = 1_200;
```

每一批候选里,只有同时满足 scope(channel/conversation/anywhere,以及 sender scope)、`canFire`(armed 状态、未过期、`fire_count < max_fires`、冷却期已过)、`triggerMatchesPrompt` 三个条件的候选才会被"点燃"——点燃之后立刻在同一个 SQLite 事务里把 `fire_count`、`last_fired_at`、`status` 写回去,整个匹配-核验-写回过程是一次同步事务,不会有另一个并发请求在核验和写回之间插进来把同一个意图重复点燃:

```ts
// extensions/memory-core/src/standing-intents.ts:521-552(节选)
if (
  !current ||
  !readKnownCreatorSender(current.creator_sender) ||
  !canFire(current, nowMs) ||
  !scopesMatch(current, channelScopes, storedSenderScope) ||
  !triggerMatchesPrompt(current, promptTokens)
) {
  continue;
}
const nextFireCount = current.fire_count + 1;
const firedIntent = rowToIntent({
  ...current,
  fire_count: nextFireCount,
  last_fired_at: nowMs,
  status: nextFireCount >= current.max_fires ? "done" : "fired",
});
if (!standingIntentsFitContext([...fired, firedIntent])) {
  continue;
}
```

`standingIntentsFitContext` 这一行值得单独拎出来讲:注入预算(最多 3 条、渲染后不超过 1200 字符)不是等扫描结束后再对结果列表做截断,而是在**决定是否点燃这一条**的那一刻就参与判断——如果加上这一条会超出字符预算,这条候选就直接被跳过(`continue`),状态也不会被写回 `fired`,它仍然保持 `armed`,下一轮对话还有机会命中。这是一个容易被忽略但很重要的细节:注入预算控制的不是"展示多少条",而是"这一轮到底点燃了几条"——被预算挤掉的候选不会消耗它的 `fire_count`。

匹配命中后,主回复会收到一段有界的隐藏上下文,格式固定为一行摘要:

```
Standing intent (created 2026-07-27): Confirm the rollback owner.
```
—— `docs/concepts/standing-intents.md`

`intent` 工具本身(`extensions/memory-core/src/standing-intents-tool.ts`)只暴露 `create`/`list`/`cancel` 三个动作,创建时要求调用者必须携带认证过的 channel 和 sender 身份,否则直接拒绝:

```ts
// extensions/memory-core/src/standing-intents-tool.ts:187-199(节选)
if (params.action === "create") {
  const provider = options.provider?.trim();
  const senderId = options.senderId?.trim();
  if (!provider || !senderId) {
    const missingIdentity = !provider
      ? senderId
        ? "channel"
        : "channel and sender"
      : "sender";
    throw new Error(
      `authenticated ${missingIdentity} identity is unavailable for this turn; retry from an authenticated channel conversation`,
    );
  }
```

默认值同样保守:冷却期 24 小时、最多触发 3 次、90 天后过期(`DEFAULT_INTENT_COOLDOWN_SECONDS`/`DEFAULT_INTENT_MAX_FIRES`/`DEFAULT_INTENT_EXPIRY_MS`)。取消永远是显式动作——`docs/concepts/standing-intents.md` 特意引用了另一篇论文(ProEvent,[arXiv:2607.17701])来说明为什么不能让模型从对话里"猜测"用户想取消某个常驻意图:"proactive systems frequently overact and struggle with event cancellation",所以取消状态必须是持久化的显式操作,而不是模型的一次判断。

### 三层"记住":cron、standing intent、standing orders 的分工

读到这里容易把 standing intent 和另一个名字很像的概念——`docs/automation/standing-orders.md` 里的 **standing orders** ——搞混。两者的关系文档里说得很清楚:

```
Standing Order: "You own the daily inbox triage"
    ↓
Automation (8 AM daily): "Execute inbox triage per standing orders"
    ↓
Agent: Reads standing orders → executes steps → reports results
```
—— `docs/automation/standing-orders.md`

standing orders 根本不是一种存储在数据库里的、由某个匹配算法命中的机制——它就是写在 `AGENTS.md`(或者被它引用的某个文件)里的一段长期指令文字,靠 workspace bootstrap 在每次会话开始时被注入进上下文,定义的是"agent 被永久授权做什么、什么时候要升级给人类审批",本质上是一份权限与流程文档。它需要靠 automations 提供的"钟点"或者 standing intent 提供的"事件"来触发执行,自己并不具备任何触发能力——`docs/automation/standing-orders.md` 原话:"Forget to enforce with automations - standing orders without triggers become suggestions"(忘记用 automations 强制执行——没有触发器的 standing orders 只是建议)。

所以三者的分工是清晰的三层:standing orders 回答"agent 被允许做什么、边界在哪里";automations 回答"什么钟点该做";standing intent 回答"什么条件出现时该做"。三者互不替代——你不会用 standing intent 去表达一个每天 8 点的提醒(那应该用 `--cron "0 8 * * *"`),也不会用 automations 去表达一个"下次有人提到发布候选版本"这种没有固定时间点的条件(那应该用 `intent` 工具),更不会指望 automations 或 standing intent 单独承载"agent 被授权做什么"这类长期性的权限声明。

## 常见问题/易踩坑

- **day-of-month 与 day-of-week 的或逻辑**:如前所述,`0 9 15 * 1` 不是"15 号且周一",而是"15 号或周一",一个月触发 5-6 次而不是 0-1 次。需要"且"语义时用 croner 的 `+` 修饰符(`0 9 15 * +1`),或者只在一个字段上调度、把另一个条件放进 prompt 里自行判断。
- **把常驻提醒错配成 standing intent**:文档明确说"For a clock time, the agent should use the existing scheduled-task path instead of creating a standing intent."——固定钟点的提醒永远应该走 automations,即使用户的原话听起来像一句"记住提醒我"。
- **误以为注入预算只是显示层的截断**:`standingIntentsFitContext` 参与的是"是否点燃"这个决策本身,而不是事后裁剪展示内容——理解这一点才能解释"为什么某个理应命中的常驻意图在这一轮没有触发,状态却还是 `armed`"这种看起来反常的现象:它不是没匹配上,而是被同一轮里更早点燃的候选挤出了 1200 字符的预算。
- **以为 standing intent 会主动"提醒"用户**:它不会主动推送任何消息,只在下一次符合 scope 的对话轮次里,把描述文本作为隐藏上下文塞给主回复——如果关键词永远不再出现,这条意图会安静地等到 `expires_at` 之后变成 `expired`,不会有任何通知。

## 小结

Automations 和 standing intents 是 OpenClaw 里两套故意分离、互不重叠的"记住要做什么"机制:前者用精确定时器覆盖一切能提前算出触发时刻的场景,四种 payload 类型和五种调度类型共享的是同一层"到期之后做什么"的执行体;后者用 SQLite FTS5 加一层严格的逐条核验,覆盖那些没有固定时间点、只能靠关键词条件触发的场景,注入预算和扫描上限从设计一开始就是为了让这套机制"宁可少触发,也不能无界增长"。第三层 standing orders 则完全不涉及触发机制本身,只负责声明权限和流程,靠前两者驱动执行。三层合在一起,才是 OpenClaw"自动化"能力的完整拼图——但这只是这一章的第一块拼图。下一篇要看的是当自动化产生的不再是一条简单提醒、而是一整个需要跟踪状态、可能跨越多次执行的复杂工作时,OpenClaw 用什么系统去承载它:Task Flow、后台任务(tasks)、以及一个看起来很像但其实是完全独立系统的 Kanban 插件——Workboard。
