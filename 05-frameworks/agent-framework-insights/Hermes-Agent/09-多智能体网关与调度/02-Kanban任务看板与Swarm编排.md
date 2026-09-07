# Kanban 任务看板与 Swarm 编排

> `delegate_task` 解决的是"父级现在就需要一个子任务的答案"——一次函数调用式的分身,跑完就消失,父级阻塞或异步等待,失败了就是失败了。但如果任务需要跨越好几天、需要人在中间插一句话、需要在父进程重启之后还能继续、或者需要被另一个完全不同的 profile 接手,`delegate_task` 的"进程内、无持久化、单向阻塞"模型就不够用了。hermes-agent 给这类场景准备了另一套完全独立的机制:Kanban——一块落地在 SQLite 里的持久化任务看板,配一个长驻的调度循环,让多个具名 profile 像团队成员一样互相认领任务、留言交接、按依赖关系排队执行。本篇拆开任务分解(`kanban_decompose.py`)、规格生成(`kanban_specify.py`)、Swarm 拓扑(`kanban_swarm.py`)、跨机器迁移(`kanban_transfer.py`)这几块骨架,最后回答一个问题:什么时候该用 `delegate_task`,什么时候该用 Kanban。

## 学习目标

- 说清楚 Kanban 相对 `delegate_task` 到底重在哪:持久化存储、状态机、人类介入点、崩溃可恢复、多 profile 对等协作——并能举出具体不适合用 `delegate_task` 硬撑的场景。
- 理解 Triage 分流的两条路径:`kanban specify`(单任务补全规格)与 `kanban decompose`(拆成一张带依赖关系的子任务图),以及两者如何在同一份代码里自然收敛(`fanout=false` 退化为 specify)。
- 理解 `kanban_swarm.py` 如何在不引入第二套调度器的前提下,用"父任务 + 并行 worker + verifier + synthesizer"这一固定拓扑写进现有的任务图里,以及"结构化评论当共享黑板"这个设计选择。
- 理解调度器 `dispatch_once` 一个 tick 里做的五件事(回收失联任务、提升就绪任务、原子认领、生成 worker、失败计数自动阻塞),建立"谁在什么时候真正把 worker 进程拉起来"的心智模型。
- 理解跨机器导出/导入(`kanban_transfer.py`)要解决的"机器本地状态"问题——为什么不能简单 `tar czf` 一个数据库文件了事。
- 理解 `delegate_task` 与 Kanban 可以共存:一个 Kanban worker 内部完全可以调用 `delegate_task` 做轻量子任务,同时不会被误认成"这个 worker 拥有委派子代理"。

## 什么场景下 delegate_task 不够用

hermes-agent 的用户文档(`website/docs/user-guide/features/kanban.md`)专门用一张表把两套机制的边界画得很清楚,这张对比表本身就是最好的入口:

| | `delegate_task` | Kanban |
|---|---|---|
| 形态 | RPC 调用(fork → join) | 持久化消息队列 + 状态机 |
| 父级行为 | 阻塞等子代理返回 | `create` 之后即可不再管 |
| 子代理身份 | 匿名子代理 | 有名字、有持久记忆的 profile |
| 可恢复性 | 无——失败就是失败 | block → unblock → 重跑;崩溃 → 回收重认领 |
| 人类介入 | 不支持 | 任何时候都能评论/解除阻塞 |
| 每个任务经手的代理数 | 一次调用 = 一个子代理 | 任务一生中可能被 N 个代理经手(重试、评审、后续跟进) |
| 审计轨迹 | 上下文压缩后就丢了 | SQLite 里的行永久留存 |
| 协调关系 | 层级(调用者 → 被调用者) | 对等——任何 profile 都能读写任何任务 |

文档给出的一句话判断标准是:**`delegate_task` 是一次函数调用;Kanban 是一个工作队列,每一次交接都是任何 profile(或人类)都能看到、能编辑的一行数据。** 具体到"什么时候 `delegate_task` 扛不住":

- **需要跨越重启存活**——`delegate_task` 的子代理挂在父进程的线程池里,父进程退出(`/stop`、`/new`、进程被杀)子代理就没了;Kanban 的任务是 SQLite 里的一行,调度器随时可以在任意进程里把它重新捡起来。
- **需要人类在中途插手**——`delegate_task` 没有暂停点,子代理一旦跑起来只能等它自己结束(或用 `action="stop"` 强行打断);Kanban 的任务可以停在 `review`/`blocked` 状态,人类用 `hermes kanban comment`/`unblock` 随时介入。
- **需要被不同身份的代理接手**——`delegate_task` 的子代理是匿名的、一次性的;Kanban 的任务有 `assignee`(具名 profile),同一个任务可以先被研究员认领、失败后被换一个 profile 重新认领。
- **需要长期沉淀记忆**——`delegate_task` 子代理被显式挡掉了 `memory` 工具(见上一篇 `DELEGATE_BLOCKED_TOOLS`);Kanban 的 worker 可以是一个"数字分身"式的常驻 profile,天天跑同一个任务、逐日积累记忆。

文档甚至直接点出两者可以共存:"a kanban worker may call `delegate_task` internally during its run"——Kanban worker 在自己的一次运行里,完全可以用 `delegate_task` 做一次轻量的、不需要持久化的子任务,两套机制不是二选一。

## Triage 分流:specify 补规格,decompose 拆图

用户或自动化把一个粗糙的想法丢进 `triage` 列,这时任务往往只有标题、没有可执行的规格。两个工具专门负责把它捞出来:

**`kanban_specify.py`** 面向"这就是一个任务,只是没写清楚"的情况。它调一次 auxiliary LLM,让模型把标题和正文改写成带 `**Goal**`/`**Approach**`/`**Acceptance criteria**`/`**Out of scope**` 四个小节的规格文本,然后调用 `kb.specify_triage_task()` 把任务从 `triage` 推进到 `todo`:

```python
# hermes_cli/kanban_specify.py:53-82(节选,system prompt)
"""... Output a single JSON object with exactly two keys:
  {
    "title": "<tightened task title, <= 80 chars, imperative voice>",
    "body":  "<multi-line spec, see structure below>"
  }
The body MUST include these sections ...
  **Goal** — one sentence, user-facing outcome.
  **Approach** — 2-5 bullets on how a worker should tackle it.
  **Acceptance criteria** — checklist of concrete, verifiable conditions.
  **Out of scope** — short list of things NOT to touch ...
"""
```

解析很宽容——不强制 JSON mode(照顾不支持结构化输出的 provider),解析失败就把整段回复原样当作正文,标题保持不变,"好歌总比没有强"。

**`kanban_decompose.py`** 面向"这个想法本身就该拆成几个任务"的情况。它同样调一次 auxiliary LLM,但要求的输出形状是一整张任务图——每个子任务带 `title`/`body`/`assignee`/`parents`(父任务在数组里的下标列表),`parents` 表达的是真实的数据依赖:没有 parents 的任务立刻并行跑,有 parents 的任务等父任务全部 `done` 才会被调度器提升。系统提示里专门强调"优先并行":

```python
# hermes_cli/kanban_decompose.py:79-91(节选,system prompt 规则)
"""
  - "parents" is a list of INDICES (0-based) into this same "tasks" list,
    expressing actual data dependencies. Tasks with no parents run in
    PARALLEL. Tasks with parents wait until every parent completes.
  - Prefer parallelism. If two tasks can be done independently, give
    them no parents so the dispatcher fans them out at once.
  - Use 2-6 tasks for normal work. Don't create 20 tiny tasks. ...
"""
```

两个模块的设计文档都明确写了"决不让任务卡死在没有 assignee 的状态"——如果 LLM 选了一个不在当前 profile 名册里的 assignee,会被无声改写成 `default_assignee`(或当前激活 profile):

```python
# hermes_cli/kanban_decompose.py:252-268(节选)
def _normalize_assignee_choice(
    assignee: object, *, default_assignee: str, valid_names: set[str],
) -> str:
    """Return a valid assignee, falling back to ``default_assignee``.
    Fan-out children and the single-task fallback should share the same
    routing guarantee: promoted work must not be left unassigned."""
    if not isinstance(assignee, str) or not assignee.strip():
        return default_assignee
    chosen = assignee.strip()
    if chosen not in valid_names:
        return default_assignee
    return chosen
```

而 `decompose` 有一条很干净的收敛路径:当 LLM 判断"这本来就是一个不可再分的任务"时返回 `fanout=false`,处理逻辑直接复用 `kb.specify_triage_task()`——**decompose 在功能上是 specify 的严格超集**,一份代码,两种入口,行为上不会互相打架。

## Swarm 拓扑:不引入第二套调度器,把拓扑写进现有任务图

`kanban_swarm.py` 的模块文档开门见山地说明了设计约束:

```python
# hermes_cli/kanban_swarm.py:1-15(节选)
"""Kanban Swarm v1: thin swarm topology helpers on top of Kanban.

This module intentionally does not introduce a second scheduler. It writes a
small task graph into the existing Kanban kernel:

    planning root (completed immediately)
        ├─ parallel specialist workers (ready)
        └─ verifier (todo until all workers done)
             └─ synthesizer (todo until verifier done)

The shared blackboard is also deliberately low-tech: structured JSON comments
on the root task. That keeps all state in existing task_comments/task_events
rows, so the dashboard, notifier, slash command, and dispatcher keep working
without a new service.
"""
```

`create_swarm()` 一次性建好四类节点:一个立即标记为 `done` 的"规划根节点"(它的作用不是被执行,而是充当共享黑板和审计锚点)、N 个并行的 specialist worker(以根节点为 parent,立刻可调度)、一个等所有 worker 完成才 `ready` 的 verifier、一个等 verifier 通过才 `ready` 的 synthesizer。整个拓扑就是 Kanban 原有的 `task_links` 父子依赖关系,调度器不需要知道"这是个 swarm"——它只是照常执行"父任务全部 `done` 才提升子任务"的既有规则。

共享黑板同样刻意"低技术含量":不是新建一张表,而是往根任务上发结构化 JSON 评论,靠一个约定前缀识别:

```python
# hermes_cli/kanban_swarm.py:337-378(节选)
BLACKBOARD_PREFIX = "[swarm:blackboard] "

def post_blackboard_update(conn, root_id, *, author, key, value):
    """Append one structured update to the swarm root blackboard."""
    payload = json.dumps({"key": key, "value": value}, ...)
    return kb.add_comment(conn, root_id, author=author, body=BLACKBOARD_PREFIX + payload)

def latest_blackboard(conn, root_id) -> dict:
    """Merge structured blackboard comments on a root card.
    Later comments replace earlier values for the same key."""
    merged = {}
    for comment in kb.list_comments(conn, root_id):
        if not comment.body.startswith(BLACKBOARD_PREFIX):
            continue
        payload = json.loads(comment.body[len(BLACKBOARD_PREFIX):])
        merged[payload["key"]] = payload["value"]
        ...
    return merged
```

后写的同 key 值覆盖先写的,`_authors` 字段记录每个 key 最后是谁写的。因为黑板状态就是普通的 `task_comments` 行,dashboard、通知器、`/kanban` slash 命令、调度器完全不需要为"这是个 swarm"写任何特殊代码路径——这是"能不加新概念就不加新概念"的一个很干净的范例。

根节点的"立即完成"也有讲究——它必须先创建成 `blocked` 状态,在同一个数据库写事务里原子翻转成 `done`,而不是先 `created` 再异步 `complete`,因为完整的 `complete_task()` 助手会开启自己的事务并触发一堆提交后副作用(工作区清理、失败计数器清零、`recompute_ready`),这些副作用如果发生在外层事务尚未提交、还可能回滚的窗口期内,就会产生"事务还没提交但已经清理了工作区"这类不一致状态:

```python
# hermes_cli/kanban_swarm.py:77-91(节选)
def _activate_root_inline(conn, root_id, *, summary, metadata):
    """Inline blocked→done CAS flip + event insert for the swarm root.

    Runs INSIDE create_swarm's outer write_txn, so it must not call
    ``kb.complete_task`` — that helper opens its own transaction and fires
    post-commit side effects ... that would execute while the outer
    transaction can still roll back."""
```

## 调度器一个 tick 做什么

Swarm 拓扑写进任务图之后,真正让任务动起来的是长驻的调度循环——`dispatch_once()`(默认每 60 秒跑一次,内嵌在 gateway 进程里,由 `kanban.dispatch_in_gateway: true` 打开)。它的文档把一个 tick 里发生的事情列得非常清楚:

```python
# hermes_cli/kanban_db.py:9915-9926(节选,_dispatch_once_locked 文档)
"""Run one dispatcher tick.

Steps:
  1. Reclaim stale running tasks (TTL expired).
  2. Reclaim stale running tasks (no recent heartbeat).
  3. Reclaim crashed running tasks (host-local PID no longer alive).
  3. Promote todo -> ready where all parents are done.
  4. For each ready task with an assignee, atomically claim and call
     ``spawn_fn(task, workspace_path, board) -> Optional[int]``.
"""
```

值得留意两个细节:一是 `max_spawn`/`max_in_progress` 是**存量并发上限**而不是"每个 tick 的生成预算"——它们把"已经在跑的任务数"和"这次 tick 打算新起的任务数"加在一起判断,否则 60 秒一个 tick、每次都按预算生成 N 个新任务,并发数会无限往上涨,永远回不去。二是达到 `kanban.failure_limit`(默认 2)次连续失败之后,任务被自动打上 `blocked`,原因就是最后一次的错误信息——这是防止调度器在一个"配置的 profile 不存在""工作区挂不上"之类永远不会成功的任务上反复空转。

## 一个 tick 里"生成 worker"到底是什么

`spawn_fn` 认领到一个就绪任务之后,真正做的事情是拉起一个具名 profile 的 Hermes 进程(附带该任务的 `kanban_*` 工具集),把 `HERMES_KANBAN_BOARD`/`HERMES_KANBAN_TASK`/`HERMES_KANBAN_RUN_ID` 等标识钉进它的环境变量,让它只能看到自己被分配的这一块看板身份。这正是上一篇提到的 `agent/delegation_context.py` 发挥作用的地方——如果这个 worker 内部又调用了 `delegate_task` 启动一个轻量子代理,子代理运行在同一个进程里、天然会"看见"这些 `HERMES_KANBAN_*` 环境变量,但它绝不能被误认成"这个看板任务的拥有者"。`tools/kanban_tools.py` 里对每一个会修改看板状态的动作都套了同一层校验:

```python
# tools/kanban_tools.py:85-99(节选)
def _reject_delegated_child_mutation(tool_name: str) -> Optional[str]:
    """Deny Kanban mutations from delegate_task children.

    A delegate_task child runs in the same process as its parent, so stale or
    inherited HERMES_KANBAN_* env vars are not proof of dispatcher ownership.
    The child may summarize findings to its parent, but it must not complete,
    block, heartbeat, comment, create, link, or unblock board tasks directly.
    """
    if not _is_delegated_child_context():
        return None
    return tool_error(
        f"{tool_name} refused: delegate_task child agents are not Kanban "
        "run owners. Return findings to the parent agent; the dispatcher "
        "worker or an explicitly configured Kanban orchestrator must perform "
        "board mutations."
    )
```

这一段代码把两篇文章串了起来:委派子代理只能把发现汇报给它的父级(也就是 Kanban worker 自己),真正的 `kanban_complete`/`kanban_block` 之类的看板动作必须由 worker 本人(或显式配置的 orchestrator)执行——身份边界靠 `is_delegated_child_context()` 这个 `ContextVar` 判断,而不是靠环境变量里有没有 `HERMES_KANBAN_TASK`。

## 跨机器迁移:为什么不能直接打包数据库文件

`kanban_transfer.py` 支撑 `hermes kanban export|import`,解决"把整块看板搬到另一台机器"的问题。模块文档一开始就点出两个真正的难点:

```python
# hermes_cli/kanban_transfer.py:17-33(节选)
"""
**The database is live.** Kanban runs in WAL mode and a dispatcher may be
mid-write, so copying ``kanban.db`` off the filesystem yields a torn
snapshot that is missing whatever still sits in the ``-wal`` file. Export
goes through SQLite's online-backup API instead ...

**Rows carry machine-local state.** Claims, PIDs, heartbeats, absolute
workspace and attachment paths, gateway chat subscriptions, and session
ids are all meaningful only on the machine that wrote them. Shipping them
verbatim is how an imported board arrives holding claims owned by a
process on somebody else's laptop, or starts pushing task events into a
stranger's Telegram thread. ...
"""
```

第一个问题(WAL 模式下直接拷贝文件会漏掉还在 `-wal` 边车文件里的最新写入)靠 SQLite 的在线备份 API 解决,而不是文件系统层面的拷贝:

```python
# hermes_cli/kanban_transfer.py:76-92(节选)
def _snapshot_db(source: Path, target: Path) -> None:
    """Write a consistent copy of ``source`` to ``target``.
    Uses SQLite's online-backup API rather than a file copy ..."""
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    src.backup(dst)
```

第二个问题(数据库里混着一堆只在原机器上有意义的运行时状态)靠导出侧和导入侧各做一次清洗(`_scrub_local_state`)——认领锁、worker PID、心跳时间戳、gateway 通知订阅这些字段全部清空,状态为 `running` 的任务重置回 `ready`(因为导入的机器上没有真的在跑这个任务的进程),`task_runs` 里的 `running` 行标记为 `released`。导入侧还多做一层"重新落地"(`_relocate_imported_rows`):附件按文件是否真的随包搬过来决定保留还是丢弃并记警告;`dir`/`worktree` 类型的工作区路径在原机器上才有意义,这类任务如果还处于可调度状态就被打回 `triage`,避免调度器认领了一个"工作区路径根本不存在"的任务、直接烧穿失败计数器进自动阻塞。

导入永远落地成一块**新**看板(slug 冲突自动加后缀),这个设计选择让导入操作对已有看板"零风险"——它不可能覆写或合并进任何已经存在的看板。

## 小结与思考题

`delegate_task` 与 Kanban 是两种正交的多智能体协作原语,不是同一个概念的两种实现:`delegate_task` 是一次函数调用式的 fork/join,子代理匿名、无持久化、父级阻塞或整体异步等待;Kanban 是一块持久化在 SQLite 里的工作队列,任务有名字、有依赖图、有状态机(`triage → todo → ready → running → blocked/review → done`),可以在任意进程里被任意 profile 认领、可以被人类随时插手评论、崩溃了能被下一次调度 tick 回收重认领。Kanban 内部的 `decompose`/`specify` 负责把粗糙想法变成可调度的任务(图),`swarm` 在不新增调度器的前提下把"并行 worker + 验证 + 综合"这一常见拓扑写成一张普通的父子任务图,黑板状态复用现有的评论表,`transfer` 解决的是"数据库是活的、行里全是机器本地状态"这两个真实的迁移难题。两者可以嵌套共存:一个 Kanban worker 内部调用 `delegate_task` 完全合法,但 `agent/delegation_context.py` 的 `ContextVar` 隔离机制保证委派出来的子代理不会被误当成看板任务的真正拥有者。

思考题:

1. `kanban_swarm.py` 的黑板用"结构化 JSON 评论 + 前缀识别"实现,后写覆盖先写。如果两个并行 worker 在同一秒各自往黑板写了同一个 key 的不同 value,`latest_blackboard()` 的合并规则(按评论时间顺序覆盖)会如何决定最终结果?这种"最后写入者获胜"的语义在什么场景下是隐患?
2. `_dispatch_once_locked` 把 `max_spawn` 设计成"存量并发上限"而不是"每 tick 生成预算",文档里解释了原因(60 秒一个 tick 的话预算式设计会让并发无界增长)。如果把调度间隔从 60 秒调到 5 秒,这个设计选择的必要性会发生什么变化?
