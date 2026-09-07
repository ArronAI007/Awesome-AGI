# delegate_task 轻量子代理委派

> hermes-agent 里最常用的"分身术"不是一个独立协议、也不是一个远程服务,而是一个近 5000 行的单文件工具——`tools/delegate_tool.py`。它在同一个 Python 进程里 new 出一个全新的 `AIAgent` 实例,给它一份从父级裁剪出来的工具集、一段从目标现拼出来的 system prompt、一个独立的终端会话,然后让它自己跑完整个任务循环。父级从头到尾看不到子代理的任何一次工具调用、任何一段推理,只在它跑完之后收到一段摘要文本。本篇拆开这套机制:子代理怎么被造出来、隔离了什么、继承了什么、单任务与批量并发两条路径分别怎么走,以及为什么"父级只看结果"比"父级看到全部过程"更划算。

## 学习目标

- 理解 `delegate_task` 如何在同一进程内构造一个全新的 `AIAgent` 子实例,并说清楚它与父代理之间在对话历史、终端会话（`task_id`）、文件操作缓存三个维度上具体隔离了什么。
- 弄清子代理的工具集是"父级 enabled 工具集 ∩ 请求的工具集,再减去黑名单"这样算出来的,理解 `DELEGATE_BLOCKED_TOOLS` 为什么恰好挡住这五个工具。
- 理解"父级只看到委派调用和摘要结果"这个设计如何具体实现(隔离的 system prompt、摘要预算裁剪、批量结果聚合),并说清楚它相对"父级完整看到子代理全部中间步骤"的价值所在。
- 区分单任务模式与批量并行模式在执行路径上的真实差别:是否走线程池、结果如何按 `task_index` 归位、中途被打断时如何优雅退化。
- 弄清"顶层调用默认强制后台执行、orchestrator 子代理内部委派默认同步等待"这条容易被忽略的规则,以及它如何服务于"父级对话不被阻塞"这个目标。
- 理解 `agent/delegation_context.py` 用 `ContextVar` 而不是直接修改 `os.environ` 来标记"这是一个委派子进程"的原因。

## 背景:一个单文件工具里装了什么

`tools/delegate_tool.py` 顶部的模块文档把整套设计意图写得很直白:

```python
# tools/delegate_tool.py:1-18
"""
Delegate Tool -- Subagent Architecture

Spawns child AIAgent instances with isolated context, inherited toolsets,
and their own terminal sessions. Supports single-task and batch (parallel)
modes. Top-level model calls run in the background; orchestrator children
wait for their own workers so they can synthesize the results.

Each child gets:
  - A fresh conversation (no parent history)
  - Its own task_id (own terminal session, file ops cache)
  - The parent's toolsets, with child-only blocked tools stripped
  - A focused system prompt built from the delegated goal + context

The parent's context only sees the delegation call and the summary result,
never the child's intermediate tool calls or reasoning.
"""
```

这段话本身就是全篇的提纲:子代理隔离了什么(全新对话、自己的终端会话/文件缓存)、继承了什么(父级工具集减去黑名单)、system prompt 怎么来(目标 + 上下文现拼)、以及最核心的价值主张——父级只看得到"调用"和"摘要"这两点,中间过程完全不可见。

## 隔离了什么:对话历史、终端会话、文件缓存

子代理的构造发生在 `_build_child_agent()` 里。它不是"克隆"父代理,而是从零构造一个新的 `AIAgent`:

```python
# tools/delegate_tool.py:1965-2005(节选)
child = AIAgent(
    base_url=effective_base_url,
    api_key=effective_api_key,
    model=effective_model,
    ...
    enabled_toolsets=child_toolsets,
    disabled_toolsets=child_disabled_toolsets,
    quiet_mode=True,
    ephemeral_system_prompt=child_prompt,
    log_prefix=f"[subagent-{task_index}]",
    platform="subagent",
    skip_context_files=True,
    skip_memory=True,
    clarify_callback=None,
    session_db=child_session_db,
    parent_session_id=getattr(parent_agent, "session_id", None),
    ...
    tool_progress_callback=child_progress_cb,
    iteration_budget=None,  # fresh budget per subagent
    **child_optional_kwargs,
)
```

几个隔离点逐一对应模块文档里的承诺:

- **对话历史**:没有任何一步把父代理的消息列表传给 `AIAgent()`。子代理的系统提示是 `ephemeral_system_prompt=child_prompt`——完全由 `goal`/`context` 现拼,而不是父级对话的延续。`skip_context_files=True`、`skip_memory=True` 进一步确保子代理不会自动读取项目的 `AGENTS.md`/`CLAUDE.md`(这些会在 system prompt 里单独按需注入,见下文)或共享的 `MEMORY.md`。
- **终端会话与文件操作缓存**:每个子代理有自己的 `session_id`,而它的终端任务用 `task_id == subagent_id`——`get_subagent_attribution()` 的文档写得很明确:"Children run their terminal sessions under `task_id == subagent_id`"。这意味着子代理起的后台进程、文件读写缓存,都挂在它自己的 `task_id` 命名空间下,不会跟父代理或其他兄弟子代理的终端状态混在一起。
- **SessionDB(会话持久化)**:子代理不复用父代理正在用的 `SessionDB` 连接,而是专门开一个指向同一个数据库文件的独立句柄——代码里的注释解释得很细:父代理的 `SessionDB` 生命周期由父级自己的收尾逻辑管理(cron 任务的 `finally`、gateway 会话结束、`/new`),如果子代理是后台 fire-and-forget 跑着的,父级句柄随时可能被关掉,届时子代理还在写自己的 transcript 就会打到一个已关闭的连接上(#81267)。所以专门为子代理开一个它自己拥有、自己负责关闭的句柄。

```python
# tools/delegate_tool.py:1928-1941(节选,注释)
# Each child gets a DEDICATED SessionDB connection instead of the parent's
# live object. The parent's handle is owned by the parent's lifecycle
# ... and can be closed while a fire-and-forget background child is still
# flushing on a daemon thread — every subsequent flush then hits the closed
# handle and the child's transcript is silently dropped (#81267).
```

## 继承了什么:父级工具集减去黑名单

子代理不是"另起炉灶"配置工具集,而是从父代理当前实际启用的工具集里做交集与裁剪。核心黑名单很短:

```python
# tools/delegate_tool.py:49-58
DELEGATE_BLOCKED_TOOLS = frozenset(
    [
        "delegate_task",  # no recursive delegation
        "clarify",  # no user interaction
        "memory",  # no writes to shared MEMORY.md
        "send_message",  # no cross-platform side effects
        "cronjob",  # no scheduling more work in the parent's name
    ]
)
```

这五个工具分别挡住五类风险:递归无限委派、向用户提问(子代理没有用户可问)、污染共享记忆文件、跨平台发消息的副作用、以及以父级名义排更多定时任务。裁剪逻辑分两层:`_strip_blocked_tools()` 移除"整个工具集里的工具全部在黑名单里"的复合工具集(外加显式列出的 `delegation`、`kanban`);`_blocked_toolsets_for_role()` 则专门处理像 `hermes-cli` 这种混合了有用工具和被黑名单工具的复合工具集——它把要拒绝的具体工具名交给 `AIAgent` 的 `disabled_toolsets`,让底层的 `model_tools` 在复合工具集展开之后再做减法,这样黑名单不会被"打包在一起注册/刷新"的机制悄悄绕过。

子代理工具集的默认继承规则(未显式传 `toolsets` 时)是"父级 enabled_toolsets 原样继承,再减去黑名单";如果父级没有显式的 `enabled_toolsets`(代表全部工具都开着),就从父级实际加载过的工具名反推出对应的工具集合。MCP 工具集有单独的保留逻辑(`_preserve_parent_mcp_toolsets`),避免父级配置的第三方 MCP 服务在子代理里意外消失。

值得注意的是:**模型侧调用 `delegate_task` 时没有 `toolsets` 参数**——批量任务在构造子代理时固定传 `toolsets=None`,子代理拿到的工具集完全由部署配置和父级当前状态决定,模型自己无法挑选或扩大子代理的工具范围。这是"权限收紧只能在委派发起时一次性确定,不能在委派过程中放宽"的具体体现。

## Orchestrator 角色:委派能力由深度推导,不是模型自己声称

一个容易误解的地方是 `role` 参数。工具签名里保留了 `role: leaf | orchestrator`,但真正决定子代理能不能再往下委派的,不是这个字段本身,而是深度和开关的运行时组合:

```python
# tools/delegate_tool.py:1642-1651(节选,_build_child_agent)
# Depth-derived, not caller-declared: a child may delegate iff the
# kill switch is on and depth budget remains below max_spawn_depth.
# The legacy `role` arg no longer participates (it asked the caller
# to guess a fact the config already knows); it is still accepted and
# normalised for wire compat, but capability comes from depth alone.
child_depth = getattr(parent_agent, "_delegate_depth", 0) + 1
max_spawn = _get_max_spawn_depth()
orchestrator_ok = _get_orchestrator_enabled() and child_depth < max_spawn
effective_role = "orchestrator" if orchestrator_ok else "leaf"
```

默认 `MAX_DEPTH = 1`(即"扁平":父级深度 0 → 子代理深度 1,子代理不能再委派),要解锁嵌套委派需要显式把 `delegation.max_spawn_depth` 调到 2 及以上——而且没有上限,每多一层纯粹是运维决策(多一层就多一份 API 成本)。`role` 参数在协议层面被保留只是为了兼容旧的调用方(比如 Kanban 调度器),它本身不再参与能力判定。

当 `effective_role == "orchestrator"` 时,子代理会重新拿回 `delegate_task`(从黑名单里显式排除),并且它的 system prompt 会追加一段"你可以再委派自己的 worker"的说明,同时如实告知它当前的深度和上限——这段文案由代码现算,不是模型编出来的:

```python
# tools/delegate_tool.py:1245-1276(节选,_build_child_system_prompt)
if role == "orchestrator":
    child_note = (
        "Your own children MUST be leaves (cannot delegate further) ..."
        if child_depth + 1 >= max_spawn_depth
        else "Your own children can themselves be orchestrators or leaves, ..."
    )
    parts.append(
        "\n## Subagent Spawning (Orchestrator Role)\n"
        "You have access to the `delegate_task` tool and CAN spawn "
        "your own subagents to parallelize independent work.\n\n"
        ...
        f"NOTE: You are at depth {child_depth}. The delegation tree "
        f"is capped at max_spawn_depth={max_spawn_depth}. {child_note}"
    )
```

## System Prompt 怎么拼:目标 + 上下文 + 按需注入的项目约定

`_build_child_system_prompt()` 现场拼出子代理的整份系统提示,核心结构是"你的任务是……" + 可选的"上下文" + 可选的"工作区路径与项目约定"。项目约定这一块值得单独展开——子代理构造时传了 `skip_context_files=True`,意味着 `AIAgent` 自己不会去读 `AGENTS.md`/`CLAUDE.md` 之类的文件,但如果任务里带了明确的工作区路径,`_build_child_system_prompt` 会用与主 Agent 完全相同的发现/优先级/长度上限逻辑手动把这些文件内容拼进 system prompt——只跳过 `SOUL.md`(身份文件属于父代理,不下放给子代理):

```python
# tools/delegate_tool.py:1214-1230(节选)
try:
    from agent.prompt_builder import build_context_files_prompt
    _ctx_files = build_context_files_prompt(
        cwd=str(workspace_path), skip_soul=True
    )
except Exception:
    _ctx_files = ""
if _ctx_files.strip():
    parts.append(
        "\nThe workspace's project context files are reproduced "
        "below. Their conventions and invariants are binding for "
        "your work in this workspace.\n\n" + _ctx_files.strip()
    )
```

这解决了一个真实的坑:子代理如果完全不知道仓库自己的开发约定,很容易写出不符合项目规范的代码——但这不是靠"继承父级的系统提示"解决的(那样会把父级身份、父级历史话题也带进来),而是靠单独跑一遍同样的项目文件发现逻辑,只取"约定"部分。

## 权限隔离:审批回调不能沿用父级的交互式输入

子代理跑在 `ThreadPoolExecutor` 的工作线程里,而 CLI 的交互式审批回调存在 `tools/terminal_tool.py` 的 `threading.local()` 里——工作线程天然拿不到它。如果什么都不做,子代理遇到危险命令审批时会退化到 `input()`,直接和父级的 `prompt_toolkit` TUI 抢占 stdin 造成死锁。修复方式是显式给每个子代理工作线程装一个非交互回调:

```python
# tools/delegate_tool.py:78-89(节选)
def _subagent_auto_deny(command: str, description: str, **kwargs) -> str:
    """Auto-deny dangerous commands in subagent threads (safe default)."""
    logger.warning(
        "Subagent auto-denied dangerous command: %s (%s). "
        "Set delegation.subagent_auto_approve: true to allow.",
        command, description,
    )
    return "deny"
```

默认策略是"拒绝并留下审计日志",只有显式打开 `delegation.subagent_auto_approve: true` 才会换成自动批准(留给 cron/批量场景的 opt-in YOLO 模式)。这体现了一条通用原则:**降级路径必须是安全默认值,而不是静默放行**。

## 隔离用 ContextVar,而不是 mutate 全局 `os.environ`

`agent/delegation_context.py` 解决的是另一个容易被忽视的问题:父进程如果本身是一个 Kanban worker(环境变量里带着 `HERMES_KANBAN_TASK` 等标识),同进程内 new 出来的 `delegate_task` 子代理不应该被误认成"这个 Kanban 任务的所有者"。如果直接改写 `os.environ` 来标记"现在是子代理上下文",会和同一进程里并发跑着的 Kanban 心跳、gateway watcher 互相踩踏——`os.environ` 是进程级别的全局状态,而委派子任务的生命周期是请求级别的。所以这里用的是 `contextvars.ContextVar`:

```python
# agent/delegation_context.py:20-33
_DELEGATED_CHILD_CONTEXT: ContextVar[bool] = ContextVar(
    "hermes_delegated_child_context",
    default=False,
)
_NON_DISPATCHER_OWNED_CONTEXT: ContextVar[bool] = ContextVar(
    "hermes_non_dispatcher_owned_context",
    default=False,
)
```

```python
# agent/delegation_context.py:48-65(节选)
@contextmanager
def delegated_child_context(session_id: str | None = None) -> Iterator[None]:
    """Mark child execution and isolate its task-local session identity."""
    token = _DELEGATED_CHILD_CONTEXT.set(True)
    try:
        from gateway.session_context import scoped_current_session_id
        with scoped_current_session_id(session_id):
            yield
    finally:
        _DELEGATED_CHILD_CONTEXT.reset(token)
```

`_build_child_agent()` 在真正构造 `AIAgent` 之前,会用 `with delegated_child_context():` 包住整个构造过程。`is_dispatcher_owned_worker_context()` 是全局唯一应该被信任的判定入口——它同时检查"是不是委派子代理"和"是不是一次由 Kanban worker 内联触发的 cron 任务"(`cronjob(action="run")` 会在同一个进程里跑,同样需要不冒充 dispatcher 身份)。`ContextVar` 天然按 asyncio task / 线程上下文传播,不会互相污染,进程退出或上下文块结束时自动复原,不需要手写"用完了记得改回去"的清理代码。跨进程边界(子代理自己又起了个子进程)时,再通过 `scrub_kanban_env()` 显式清掉环境变量里的 Kanban 专属键,并打上 `HERMES_DELEGATED_CHILD_CONTEXT=1` 标记,让子进程也能识别自己的血缘。

这个模块在下一篇讲 Kanban 时还会再次出现——它正是"delegate_task 与 Kanban worker 共存于同一进程时如何互不冒充身份"的关键机制。

## 单任务 vs 批量并行:两条执行路径

`delegate_task` 接受 `goal`(单任务)或 `tasks`(数组,批量)。所有子代理会在主线程上**先全部构造完**(`_build_child_preserving_parent_tools`,构造期间加锁保护父级工具解析状态不被子代理构造过程污染),再统一交给 `_execute_and_aggregate()` 执行:

```python
# tools/delegate_tool.py:3927-3940(节选)
if n_tasks == 1:
    # Single task -- run directly (no thread pool overhead)
    _i, _t, child = children[0]
    result = _run_single_child(_i, _t["goal"], child, parent_agent, ...)
    results.append(result)
else:
    # Batch -- run in parallel with per-task progress lines
    with DaemonThreadPoolExecutor(max_workers=max_children) as executor:
        futures = {executor.submit(...): i for i, t, child in children}
        ...
```

单任务路径直接同步跑,省掉线程池开销;批量路径用 `DaemonThreadPoolExecutor`(守护线程池,父级被打断时不会拖住解释器退出)并发跑,`max_workers` 受 `delegation.max_concurrent_children` 限制(默认 10,可调但没有硬上限,超过 10 会打印一次性成本提示日志)。批量结果按 `task_index` 排序回填,保证返回顺序始终对应输入顺序,而不是"谁先跑完谁排前面"。

父级被打断(interrupt)时的处理很讲究:代码不会无限期 `as_completed()` 死等,而是用 `wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)` 轮询,一旦检测到父级被打断,就把"已完成的"正常收尾、"还没完成的"标记成 `status="interrupted"` 直接放弃等待——子代理本身已经收到了中断信号(通过 `_active_children` 列表级联传播),但父级不会为了等一个可能卡住的子代理而永远挂起。

## 顶层调用强制后台,orchestrator 内部委派强制同步

一个极易被忽略、但对"上下文零成本并行"这个价值主张至关重要的规则是:**模型侧对 `delegate_task` 没有"要不要后台运行"的选择权**。注册到工具表时,`background` 参数是由运行时算出来的,不是模型传的:

```python
# tools/delegate_tool.py:4887-4901(节选)
def _model_background_value(args: dict, parent_agent=None) -> bool:
    """
    Delegations from the top-level agent always run in the background — the
    model does not choose. ... The one exception is a delegation from an
    orchestrator subagent (depth > 0), which needs its workers' results
    within its own turn.
    """
    is_subagent = getattr(parent_agent, "_delegate_depth", 0) > 0
    return not is_subagent
```

也就是说:顶层对话里的模型每次调用 `delegate_task`,不管是单任务还是一个 N 项的批量数组,整批都会被当成**一个**异步单元派发出去——`dispatch` 立即返回一个带 `delegation_id`/`live_transcripts` 的确认,父级对话继续往下走,不阻塞;所有子代理跑完、互相 join 之后,**一条**合并好的结果消息会重新进入对话。而如果这次委派是从一个 orchestrator 子代理内部发起的(它自己就是深度 > 0 的委派产物),则会同步执行——因为 orchestrator 需要在自己这一轮里等到 worker 的结果才能做汇总判断,不能"发完就跑"。

工具的顶层描述文本(`_build_top_level_description()`,会随配置动态重建)把这一点说给模型听:

```python
# tools/delegate_tool.py:4645-4700(节选)
"Runs in the background: dispatch returns immediately with live "
"transcript paths, and the completed result (one consolidated message, "
"results in task order) re-enters the conversation on its own. Do NOT "
"wait or poll; continue other work. While children run, `action` "
"(list/steer/stop) controls them live — steer when a transcript shows "
"a child drifting.\n\n"
```

## 为什么"父级只看结果"比"父级看全部过程"更好

这是本篇的核心论点,可以从三个角度理解:

1. **上下文预算**:子代理动辄跑几十次工具调用、读几万字文件、试错好几轮——如果这些全部原样回灌进父级对话,父级的上下文窗口会被中间过程迅速填满,而这些中间过程对父级要做的下一步决策通常毫无意义。`delegate_task` 只把最终摘要写回父级对话,而且这个摘要本身还有动态预算控制:

```python
# tools/delegate_tool.py:2359-2394(节选,_parent_summary_char_budget)
"""Per-summary character budget sized against the parent's *remaining*
context headroom, split across the batch. ... Returns the per-summary
char budget, or None when the parent's context state is unknown."""
```

`_apply_summary_budget()` 取"父级剩余上下文headroom 的一部分"和"静态字符上限 `delegation.max_summary_chars`(默认 24000)"两者的较小值作为每条摘要的实际预算,超出部分裁剪并把完整文本溢写到磁盘文件、摘要里留一个指针。这是为了堵住 issue #9126 描述的真实事故:一次批量委派返回 N 条完整摘要,直接把父级上下文撑爆,进而触发压缩/429 的死亡螺旋。

2. **并行的"零成本"**:因为父级不需要在每个子代理运行期间持续观察、追问、转发中间结果,N 个子代理可以真正并行跑,父级线程只在最后做一次 join。如果反过来让父级"看着"每个子代理的每一步,协调开销会随子代理数量线性增长,父级自己的推理反而会被大量转发信息打断。

3. **对模型的信任边界更清晚**:工具描述里专门提醒模型——子代理的摘要是"自称完成",不是外部验证过的事实:

```
"Child summaries are SELF-REPORTS, not verified facts: a child claiming
\"uploaded successfully\" or \"file written\" may be wrong. For external
side effects (uploads, remote writes, publishing), require a verifiable
handle (URL, ID, absolute path) and verify it yourself..."
```

这提示了"只看结果"模式的代价:父级失去了对子代理执行细节的直接监督能力。对此,`delegate_task` 提供了一条折中通道——`action="list"/"steer"/"stop"` 三个同步控制动作,让父级在子代理仍在运行时能看一眼状态、插一句纠偏文本,或者提前叫停,而不必等到摘要出来才发现方向跑偏了。`steer` 的实现很克制:文本被追加到子代理"下一次工具结果"里,而不是打断当前正在执行的工具调用——纠偏是柔性的,不是抢占式的。

## 小结与思考题

`delegate_task` 的核心链路是:模型调用工具 → 按 `goal`/`tasks` 归一成任务列表 → 在主线程上逐个构造隔离的子 `AIAgent`(全新对话、独立终端会话与 SessionDB、父级工具集减黑名单、深度推导出的 orchestrator 权限)→ 单任务直接跑、批量丢进守护线程池并发跑 → 顶层调用整体异步派发、orchestrator 内部委派同步等待 → 结果按预算裁剪、按顺序聚合成一条消息回灌父级对话。"父级只看到委派调用和摘要"不是偷懒,而是三重收益的取舍:保住父级的上下文预算、换来真正的并行、逼着模型对子代理的自我汇报保持怀疑,同时用 `list`/`steer`/`stop` 三个轻量控制动作补上"完全看不见"的监督缺口。

思考题:

1. `_model_background_value()` 让顶层调用强制异步、orchestrator 内部调用强制同步——如果一个顶层任务本身就需要"必须先拿到子代理结果才能继续这一轮对话",现有设计要求模型怎么表达这个需求?这是不是意味着某些场景下模型必须先把自己伪装成 orchestrator 才能拿到同步语义?
2. `DELEGATE_BLOCKED_TOOLS` 里的 `memory` 被挡住是为了不让子代理写共享 `MEMORY.md`。如果一个批量任务里的多个子代理确实需要往同一个地方沉淀发现,当前架构下有哪些替代通道(提示:参考父级摘要聚合和下一篇要讲的 Kanban blackboard 模式),分别有什么代价?
