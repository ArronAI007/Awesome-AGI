# Curator:后台复审与技能生命周期治理

> `/learn` 负责"从经验里生出一个新技能",但一个只会新增、不会维护的技能库迟早会变成几百个"某一次会话专属"的窄技能堆在一起,互相重叠、拖慢检索、稀释模型注意力。Curator(`agent/curator.py`,约 2000 行)就是补上"维护"这一半的组件——它不是常驻的 cron 守护进程,而是"inactivity-triggered":每次 CLI 启动、或网关的后台 tick 里,都会检查一次"距上次 curator 运行是否已经超过 `interval_hours`",够了就跑一遍确定性的状态迁移,如果开了"consolidation"开关,还会额外 fork 一个后台 `AIAgent` 去做更激进的技能合并复审。本篇通读这套触发逻辑、复审 agent 的能力边界,以及配套的快照/回滚机制。

## 学习目标

- 理解 curator 的触发方式:不是常驻定时器,而是每次特定入口被调用时检查 `interval_hours` 是否已到,`maybe_run_curator()` 是这个检查的唯一入口。
- 弄清一个和"inactivity-triggered"直觉不完全一致的实现细节:当前两处调用点传给它的"空闲时长"参数分别是什么,这对"是否真的在检测活跃度"意味着什么。
- 读懂一次 curator run 的两阶段结构——确定性的自动状态迁移(永远跑,不花模型调用)与可选的 LLM 复审(consolidation,默认关闭,才是真正会调用 `skill_manage` 做 pin/archive/consolidate/patch 的部分)。
- 掌握几条贯穿全文的不变式:只管 agent-created 技能、永不真删除只能 archive、pinned 技能豁免、复审 fork 用独立的 `AIAgent` 实例因此天然不碰主会话的 prompt cache。
- 理解 `curator_backup.py` 的快照/回滚机制如何兜底"复审 agent 做错了决定"这种风险。
- 能把 `/learn` 与 curator 放在一起,讲清楚"自我改进学习环"这个卖点具体由哪两段代码构成。

## 触发机制:不是 cron,是"到点检查一次"

`agent/curator.py` 模块 docstring 一开始就把这件事说清楚了:

```python
# agent/curator.py:1-20
"""Curator — background skill maintenance orchestrator.

The curator is an auxiliary-model task that periodically reviews agent-created
skills and maintains the collection. It runs inactivity-triggered (no cron
daemon): when the agent is idle and the last curator run was longer than
``interval_hours`` ago, ``maybe_run_curator()`` spawns a forked AIAgent to do
the review.
...
Strict invariants:
  - Only touches agent-created skills (see tools/skill_usage.is_agent_created)
  - Never auto-deletes — only archives. Archive is recoverable.
  - Pinned skills bypass all auto-transitions
  - Uses the auxiliary client; never touches the main session's prompt cache
"""
```

真正的判断逻辑在 `should_run_now()` 里,门槛是三条:`curator.enabled`、没有被 `hermes curator pause` 暂停、以及距离 `last_run_at` 是否已经超过 `interval_hours`(默认 7 天,即 `DEFAULT_INTERVAL_HOURS = 24 * 7`):

```python
# agent/curator.py:233-283(节选)
def should_run_now(now: Optional[datetime] = None) -> bool:
    if not is_enabled():
        return False
    if is_paused():
        return False

    state = load_state()
    last = _parse_iso(state.get("last_run_at"))
    if last is None:
        # First-run: seed last_run_at to now and DEFER the first real pass
        # by one full interval, instead of firing immediately after
        # `hermes update` on a fresh install.
        ...
        return False

    if now is None:
        now = datetime.now(timezone.utc)
    interval = timedelta(hours=get_interval_hours())
    return (now - last) >= interval
```

值得单独一提的是"首次运行不立即触发"这个细节:全新安装或刚从旧版本 `hermes update` 升级后,第一次观察到"从未跑过"时,curator 只是把 `last_run_at` 种成"现在",然后直接返回 `False`——真正的第一次复审要再等一个完整的 `interval_hours`。这给了用户一整个 interval 的窗口去 pin 重要技能,或者干脆关掉 curator,而不会在升级后立刻被一次自动复审"突袭"。

## 一个需要澄清的细节:`min_idle_hours` 目前没有真正接到"空闲检测"

`maybe_run_curator()` 的签名里确实有一个 `idle_for_seconds` 参数,配合 `min_idle_hours`(默认 2 小时)配置项,理论上是"只有 agent 真正闲置够久才触发"这层过滤:

```python
# agent/curator.py:2023-2041
def maybe_run_curator(
    *,
    idle_for_seconds: Optional[float] = None,
    on_summary: Optional[Callable[[str], None]] = None,
) -> Optional[Dict[str, Any]]:
    """Best-effort: run a curator pass if all gates pass. Returns the result
    dict if a pass was started, else None. Never raises."""
    try:
        if not should_run_now():
            return None
        if idle_for_seconds is not None:
            min_idle_s = get_min_idle_hours() * 3600.0
            if idle_for_seconds < min_idle_s:
                return None
        return run_curator_review(on_summary=on_summary)
    except Exception as e:
        logger.debug("maybe_run_curator failed: %s", e, exc_info=True)
        return None
```

但翻遍仓库里全部两处真正调用它的地方——CLI 启动流程和网关的后台 housekeeping tick——传的都是同一个值:

```python
# cli.py:17847-17854(节选)
from agent.curator import maybe_run_curator
maybe_run_curator(
    idle_for_seconds=float("inf"),  # CLI startup = fully idle
    ...
)
```

```python
# gateway/run.py:31275-31281(节选)
from agent.curator import maybe_run_curator
maybe_run_curator(
    idle_for_seconds=float("inf"),
    ...
)
```

也就是说,`idle_for_seconds < min_idle_s` 这个判断目前**永远不会为真**——两处调用都把"空闲时长"硬编码成无穷大,等于直接宣称"永远处于完全空闲状态"。这与官方文档 `website/docs/user-guide/features/curator.md` 里"On CLI session start, and on a recurring tick inside the gateway's cron-ticker thread, Hermes checks whether ... the agent has been idle long enough (`min_idle_hours`)"这句话在字面上有出入:代码里这个检查确实存在、配置项也确实存在,但当前两个调用点都没有接入真实的空闲时长测量,`min_idle_hours` 现阶段实际上是一个待接线的配置项,真正起过滤作用的只有 `interval_hours`(7 天)这一道闸。这是本篇在核对源码时发现的、和最初调研摘要预期不完全一致的地方,值得读者知道。

## 一次 run 的两阶段结构

`run_curator_review()` 把一次 curator run 拆成两段,第一段永远跑、第二段默认关闭:

```python
# agent/curator.py:1518-1551(节选)
def run_curator_review(
    on_summary: Optional[Callable[[str], None]] = None,
    synchronous: bool = False,
    dry_run: bool = False,
    consolidate: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Steps:
      1. Apply automatic state transitions (pure, no LLM).
      2. If consolidation is enabled AND there are agent-created skills, spawn
         a forked AIAgent that runs the LLM review prompt against the current
         candidate list.
      3. Update .curator_state with last_run_at and a one-line summary.
      4. Invoke *on_summary* with a user-visible description.
    ...
    """
```

### 阶段一:确定性状态迁移,不花一次模型调用

`apply_automatic_transitions()` 是一个纯函数,只根据每个技能的 `last_activity_at`/`created_at`/`use_count` 计算它该处于 `active`/`stale`/`archived` 三态里的哪一个:

```python
# agent/curator.py:305-398(节选)
def apply_automatic_transitions(now: Optional[datetime] = None) -> Dict[str, int]:
    """Walk every curator-managed skill and move active/stale/archived based on
    the latest real activity timestamp. Pinned skills are never touched.
    ...
    """
    ...
    for row in _u.curated_report():
        if row.get("pinned"):
            continue
        if name in cron_referenced:
            continue          # 被任何 cron job 引用的技能,视同 pinned

        ...
        never_used = int(row.get("use_count", 0) or 0) == 0
        if never_used and anchor > stale_cutoff:
            continue          # 从未使用过的新技能有一个宽限期,不会一上来就判定过期

        if anchor <= archive_cutoff and current != _u.STATE_ARCHIVED:
            ok, _msg = _u.archive_skill(name)
            ...
        elif anchor <= stale_cutoff and current == _u.STATE_ACTIVE:
            _u.set_state(name, _u.STATE_STALE)
        elif anchor > stale_cutoff and current == _u.STATE_STALE:
            _u.set_state(name, _u.STATE_ACTIVE)   # 用回来了就复活
```

这一步不涉及任何模型调用,`stale_after_days`(默认 30)和 `archive_after_days`(默认 90)两个阈值纯粹是日期比较。它也是"永不真删除"这条不变式在代码层面唯一落地的地方——这里能做的最大破坏性动作就是 `archive_skill()`,把技能目录挪进 `~/.hermes/skills/.archive/`,没有任何删除路径。

### 阶段二:LLM 复审(consolidation),默认关闭

```python
# agent/curator.py:74-78
# Consolidation (the LLM umbrella-building fork) is OFF by default. The
# deterministic inactivity prune (apply_automatic_transitions) still runs
# whenever the curator is enabled; only the opinionated, aux-model-cost
# consolidation pass is opt-in.
DEFAULT_CONSOLIDATE = False
```

这一点和最初的调研摘要有出入,需要在这里明确:并不是"curator 一跑就会 fork 后台 agent 去 pin/archive/consolidate/patch",而是**只有 `curator.consolidate: true`(或显式 `hermes curator run --consolidate`)时,才会走到 fork 后台 agent 这一步**;默认情况下,curator 每 7 天做的事只是前面那段纯日期比较的自动迁移,不花一分钱的模型调用。这是刻意的成本控制——`CURATOR_REVIEW_PROMPT` 要求的是一次"伞形技能"式的整理(把同前缀、同领域的一堆窄技能合并成一个带小节的大技能),这种复审一次要花 50~100 次 API 调用,不应该在用户完全没有要求的情况下自动发生。

真正被 fork 出来的复审 agent,收到的 `CURATOR_REVIEW_PROMPT` 里写死了一批"硬规则"(hard rules),节选如下:

```
# agent/curator.py:448-479(节选,CURATOR_REVIEW_PROMPT)
Hard rules — do not violate:
1. DO NOT touch bundled, hub-installed, or external-dir skills
   (`skills.external_dirs`). The candidate list below is already filtered
   to local curator-managed skills only ...
2. DO NOT delete any skill. Archiving (moving the skill's directory
   into ~/.hermes/skills/.archive/) is the maximum destructive action.
   Archives are recoverable; deletion is not.
3. DO NOT touch skills shown as pinned=yes. Skip them entirely.
3b. DO NOT archive, delete, consolidate, move, or otherwise modify any
    skill named in the protected built-ins list (currently: plan). ...
3c. DO NOT archive or prune any skill marked `cron=yes` in the candidate
    list. ... You MAY still consolidate it into an umbrella — but only
    because the curator rewrites cron job skill references to follow
    consolidations; never simply prune it.
```

它能用的工具被显式限定为 `skills_list`/`skill_view`(只读)和 `skill_manage`(`patch`/`create`/`write_file`/`delete`,这里的 `delete` 语义是"归档",不是物理删除)加上 `terminal`(仅用于把某个技能的内容挪进另一个伞形技能的 `references/`/`templates`/`scripts/` 子目录),完全没有开放访问 bundled/hub-installed/外部目录技能的权限。

### 后台复审 agent 是怎么 fork 出来的

`_run_llm_review()` 直接实例化一个全新的 `AIAgent`,而不是复用当前会话的任何状态:

```python
# agent/curator.py:1939-1970(节选)
review_agent = AIAgent(
    model=_model_name,
    provider=_resolved_provider,
    ...
    enabled_toolsets=["skills", "terminal"],
    max_iterations=9999,
    quiet_mode=True,
    platform="curator",
    skip_context_files=True,
    skip_memory=True,
)
review_agent._memory_nudge_interval = 0
review_agent._skill_nudge_interval = 0
review_agent._memory_write_origin = "background_review"

with open(os.devnull, "w", encoding="utf-8") as _devnull, \
     contextlib.redirect_stdout(_devnull), \
     contextlib.redirect_stderr(_devnull):
    conv_result = review_agent.run_conversation(user_message=prompt)
```

几个细节值得展开:

- `enabled_toolsets=["skills", "terminal"]` 把工具面收窄到只有技能相关操作和终端,复审 agent 拿不到 `delegate_task`/`memory`/`send_message` 这些能力。
- `max_iterations=9999` 是刻意放宽的——一次真正的"伞形化"复审要扫过几百个候选技能、做几十次合并,正常单轮对话的迭代上限完全不够用。
- `_memory_write_origin = "background_review"` 是关键的一处"打标签"——这个值会被 `skill_manage` 的写入守卫读取,只有携带这个标记的调用才会被认定为"自主后台策展",从而触发针对 bundled/hub-installed/外部技能的额外保护,以及在 `.usage.json` 里写下 `created_by: "agent"` 这个 provenance 标记。
- 因为这是一个**全新构造的 `AIAgent` 实例**,它有自己独立的对话历史和请求上下文,不会读取、也不会污染主会话已经积累起来的 prompt cache——"uses the auxiliary client; never touches the main session's prompt cache"这条不变式,本质上就是"复审永远在一个新对象上跑"这件事的自然推论,而不是需要额外加锁或者做缓存隔离的复杂机制。
- 复审用什么模型由 `_resolve_review_runtime()` 解析,优先读 `auxiliary.curator.{provider,model}` 这个专门的辅助任务槽位,没配置就回退到主对话模型——也就是说"用辅助模型"是可配置的默认行为,而不是强制装死的另一个模型。

## 几条不变式,以实际代码为准

- **只处理 agent-created 技能**:`tools/skill_usage.is_agent_created()` 判定的口径是"不在 `.bundled_manifest` 里、不在 hub 的 `lock.json` 里、且 `.usage.json` 里显式标了 `created_by: "agent"`"。这条标记目前只由后台复审 fork(以及用户显式 `hermes curator adopt`)写入——**前台**会话里用户直接要求 `skill_manage(action="create")` 新建的技能,默认反而**不会**被标记为 agent-created,curator 不会碰它们(除非用户手动 `adopt`)。这是一处比"只管 agent 自建技能"更精细的规则:精确说是"只管被认定为可自主策展的技能",而"谁在物理上创建了这个文件"和"这个文件是否归 curator 管辖"是两个不同的问题。
- **永不真删除,只能 archive**:`apply_automatic_transitions()` 和 `CURATOR_REVIEW_PROMPT` 里能触达的最大破坏性动作都是把技能目录挪进 `~/.hermes/skills/.archive/`。物理删除(`hermes curator purge`)是一条完全独立、需要用户显式调用的路径,且默认 TTL 为 `0`(永不过期)。
- **pinned 技能全面豁免**:自动迁移和 LLM 复审都显式跳过 `pinned=true` 的技能;`skill_manage(action="delete")` 对 pinned 技能也会直接拒绝,但 `patch`/`edit`/`write_file`/`remove_file` 仍然放行——目的是让 agent 能持续改进一个被钉住的技能内容,只是不能删掉它。
- **辅助模型、独立实例**:如前一节所述,复审 fork 是一个全新的 `AIAgent`,天然不与主会话共享 prompt cache。

## `curator_backup.py`:运行前快照与可回滚的回滚

任何一次真正的(非 dry-run)curator pass 开始前,`run_curator_review()` 都会先调用 `curator_backup.snapshot_skills()` 打一份快照:

```python
# agent/curator.py:1567-1583(节选)
else:
    try:
        from agent import curator_backup
        snap = curator_backup.snapshot_skills(reason="pre-curator-run")
        ...
    except Exception as e:
        logger.debug("Curator pre-run snapshot failed: %s", e, exc_info=True)
    counts = apply_automatic_transitions(now=start)
```

`curator_backup.py` 模块 docstring 说明了快照覆盖的范围:

```python
# agent/curator_backup.py:1-38(节选)
"""Curator snapshot + rollback.

A pre-run snapshot of ``~/.hermes/skills/`` (excluding ``.curator_backups/``
itself) is taken before any mutating curator pass. Snapshots are tar.gz
files under ``~/.hermes/skills/.curator_backups/<utc-iso>/`` with a
companion ``manifest.json`` ...

It DOES include:
  - all SKILL.md files + their directories (``scripts/``, ``references/``,
    ``templates/``, ``assets/``)
  - ``.usage.json`` (usage telemetry — needed to rehydrate state cleanly)
  - ``.archive/`` (so rollback restores previously-archived skills too)
  - ``.curator_state`` (so rolling back also restores the last-run-at
    pointer — otherwise the curator would immediately re-fire on the next
    tick)
  ...
Alongside the skills tarball, each snapshot also captures a copy of
``~/.hermes/cron/jobs.json`` as ``cron-jobs.json`` when it exists. ...
"""
```

快照失败是"尽力而为"——记一条 debug 日志就继续跑,不会因为一次磁盘故障就把 curator 整个禁用掉。快照数量按 `curator.backup.keep`(默认 5)做轮转清理。`rollback()` 的实现有一个值得记住的细节:回滚本身也会先打一份"回滚前"快照(`pre-rollback to <target-id>`),所以一次误操作的回滚还能再回滚回去——这条"回滚本身也可回滚"的设计,把"复审 agent 做错决定"这个风险兜到了两层保险。除了整棵树粒度的快照,仓库里还有一层更细的机制——按次操作追加写入的审计台账(`~/.hermes/skills/.curator_ledger.jsonl`),记录每一次技能改动的 actor(`curator`/`agent`/`user`)和前后内容哈希,支持单条撤销,但这部分实现细节不在 `curator.py`/`curator_backup.py` 两个核心文件里,本篇不展开。

## 小结与思考题

`/learn` 负责"无中生有"——把一段经验、一份文档蒸馏成新技能;curator 负责"用中变好"——跟踪每个 agent-created 技能的使用痕迹,让长期不用的技能经过 `active → stale → archived` 自动老化(这一步永远在跑、不花模型调用),再由一个可选的、默认关闭的 LLM 复审 pass 把散落的窄技能合并成"类级别"的伞形技能。两段代码合起来,正是 README 里"the only agent with a built-in learning loop"这句宣传的字面实现:**创建(learn)→ 使用中改进(curator)**构成一个完整闭环,而不是"技能只会越攒越多、从不清理"的单向堆积。

需要向你明确指出的、与最初调研摘要有出入的三处:

1. **触发机制**:`maybe_run_curator()` 里确实实现了 `min_idle_hours` 的比较逻辑,但目前仓库里两处真正的调用点(`cli.py` 启动流程、`gateway/run.py` 的后台 tick)都把 `idle_for_seconds` 硬编码成 `float("inf")`,等于永远视为"完全空闲"。真正起作用的门槛只有 `interval_hours`(默认 7 天)——这与"检测 agent 是否真的空闲"这个直觉不完全一致,更准确的描述是"到点检查一次,而非侦测活跃度"。
2. **"能 pin/archive/consolidate/patch"这个能力集**:只有在 `curator.consolidate: true`(默认是 `false`)时,curator 才会 fork 出会调用 `skill_manage` 做这些操作的后台 agent;默认情况下,每次 curator run 只做确定性的日期比较迁移,不涉及任何 LLM 调用,更谈不上"pin"——pin/unpin 完全是用户通过 `hermes curator pin/unpin` 显式触发的手动操作,复审 agent 本身并不会主动去 pin 一个技能。
3. **"只处理 agent 自建技能"的口径**:更精确地说是"只处理被标记为 `created_by: agent` 的技能",而这个标记默认只由后台复审 fork(或用户显式 `adopt`)写入——用户在前台会话里让 agent 用 `skill_manage(action="create")` 建的技能,默认反而不在 curator 的管辖范围内,除非显式 `adopt`。

思考题:

1. 如果要把 `min_idle_hours` 真正接上"检测活跃度"的语义,你会在哪里测量"空闲时长"——CLI 的输入等待时间、gateway 里最后一次收到消息的时间戳,还是别的信号?这个信号需要跨进程重启保持吗?
2. `CURATOR_REVIEW_PROMPT` 里要求复审 agent"如果一轮下来 archive 数量少于 10 个,说明你停得太早",这是一条鼓励"多合并"的指令。结合"pinned 技能全面豁免"和"永不真删除"这两条安全阀,你觉得这种"偏激进"的提示词风格,配合"默认关闭 + 需要显式 `--consolidate`"的开关设计,是不是已经把风险控制在可接受范围?如果让你再加一道保险,你会加在哪一层?
