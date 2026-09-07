# Cron 调度与主动触发

> 定时任务的执行不是 gateway 进程里的一个协程,而是一次完全独立的短生命周期子进程:调度器每 30 秒醒一次,把到期任务通过 shell 拉起一个新的 `ohmo --print` 进程(或者一条裸命令),进程退出后如果配置了通知,直接用 Feishu SDK 把结果主动推给用户——这一步既不经过 `MessageBus`,也不要求 gateway 后台进程正在跑。这就是"主动触发":Agent 不再是"你发消息我才回应"的被动角色,而是可以按计划、或者被自己调用的工具立即触发,主动找上用户。这对提醒、定期汇报这类个人助理场景是刚需能力。

## 学习目标

- 理解 cron 任务的存储结构:一份 JSON 注册表,每条记录包含 `schedule`(cron 表达式)、`command` 或 `payload.message`(agent_turn)、可选的 `notify`,以及调度器维护的 `next_run`/`last_run`/`last_status`。
- 理解调度循环 `run_scheduler_loop()` 的节奏——每 `TICK_INTERVAL_SECONDS`(30 秒)读一次注册表、筛出到期任务、并发执行——以及它为什么允许 30 秒级别的调度粒度而不追求秒级精确。
- 理解一次"任务执行"具体做了什么:`_command_for_job()` 把一条 `agent_turn` 任务翻译成一条 `ohmo --profile ... --cwd ... --print "message"` 命令,拉起子进程运行——这与第一篇讲过的 `ohmo --print` 单次模式是同一个入口。
- 理解任务执行完成后的主动通知路径:`_notify_job_result()` 直接调用 `ohmo.gateway.notify.send_feishu_dm()`,用 Feishu SDK 和存在 `gateway.json` 里的凭证直接发消息,不依赖 gateway 进程是否存活。
- 理解 Agent 自己管理定时任务的完整工具链:`cron_create`/`cron_list`/`cron_toggle`/`cron_delete` 四个工具,以及 `remote_trigger` 工具如何复用调度器同一套命令构造逻辑实现"立即触发一次"。

## 背景与设计动机

个人助理的价值有一部分恰恰在于它不需要用户先开口。"每天早上 9 点汇报一下昨晚的 GitHub 通知"、"每小时检查一次某个网站是否更新"、"三小时后提醒我回复某条消息"——这些场景要求 Agent 能够脱离"用户发消息触发一次会话"这个默认假设,由时间或某个内部条件主动发起一次新的对话。要做到这一点,系统需要三样东西:一个持久化的任务注册表(重启不丢失)、一个独立于 gateway 主进程的调度循环(哪怕 gateway 因为某些原因没在跑,提醒也不该整体失效)、以及一条能把"任务执行完了"这件事主动推送回用户设备的通道。

## 核心机制详解

### 任务存储:一份带文件锁的 JSON 注册表

`src/openharness/services/cron.py` 是最底层的持久化层,所有读写都包一层文件锁,避免调度器和 CLI/工具同时改注册表时互相覆盖:

```python
# src/openharness/services/cron.py:73-90(节选)
def upsert_cron_job(job: dict[str, Any]) -> None:
    """Insert or replace one cron job.

    Automatically sets ``enabled`` to True and computes ``next_run`` when the
    schedule is a valid cron expression.
    """
    job.setdefault("enabled", True)
    job.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    schedule = job.get("schedule", "")
    if validate_cron_expression(schedule):
        job["next_run"] = next_run_time(schedule, tz=job.get("timezone") or job.get("tz")).isoformat()

    with exclusive_file_lock(_cron_lock_path()):
        jobs = [existing for existing in load_cron_jobs() if existing.get("name") != job.get("name")]
        jobs.append(job)
        jobs.sort(key=lambda item: str(item.get("name", "")))
        save_cron_jobs(jobs)
```

`next_run_time()` 基于 `croniter` 计算,支持按 IANA 时区解释 cron 表达式(先把 UTC 基准时间转到目标时区算出下一次触发时间,再转回 UTC 存储),这意味着"每天早上 9 点"可以准确对应用户本地时间的 9 点,而不是服务器所在时区的 9 点。`mark_job_run()` 在每次执行后更新 `last_run`/`last_status` 并重新计算下一次 `next_run`,形成一个自驱动的调度状态机——注册表本身既是配置也是状态。

### 调度循环:30 秒一次 tick,并发执行到期任务

```python
# src/openharness/services/cron_scheduler.py:443-478(节选)
async def run_scheduler_loop(*, once: bool = False) -> None:
    """Main scheduler loop.  Runs until SIGTERM or *once* is True (test mode)."""
    ...
    write_pid()
    try:
        while not shutdown.is_set():
            now = datetime.now(timezone.utc)
            jobs = load_cron_jobs()
            due = _jobs_due(jobs, now)

            if due:
                logger.info("Tick: %d job(s) due", len(due))
                results = await asyncio.gather(
                    *(execute_job(job) for job in due), return_exceptions=True
                )
                for result in results:
                    if isinstance(result, BaseException):
                        logger.error("Unexpected error executing cron job: %s", result)

            if once:
                break
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=TICK_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
    finally:
        restore_signals()
        remove_pid()
```

`_jobs_due()` 只看两个条件:任务 `enabled` 且 `next_run <= now`。调度粒度是 `TICK_INTERVAL_SECONDS = 30` 秒,这意味着一条 cron 表达式声明"每分钟"的任务,实际触发时间可能有最多 30 秒的抖动——对个人助理场景(提醒、定期汇报)这完全够用,不需要为秒级精确调度增加复杂度。到期任务用 `asyncio.gather()` 并发执行,互不阻塞;调度器自己是一个独立的守护进程(通过 `oh cron start` 启动,PID 记在 `cron_scheduler.pid`),与 gateway 进程完全解耦——这一点很关键,下一节会看到它如何体现在任务的实际执行方式上。

### 任务执行 = 拉起一个新的 `ohmo --print` 进程

`_command_for_job()` 是调度器和"立即触发"工具共享的核心翻译逻辑,把一条 `agent_turn` 类型的任务翻译成一条完整的 shell 命令:

```python
# src/openharness/services/cron_scheduler.py:283-309(节选)
def _command_for_job(job: dict[str, Any]) -> str:
    """Return the shell command used to execute a job."""
    command = job.get("command")
    if command:
        return str(command)
    payload = job.get("payload")
    if not isinstance(payload, dict) or payload.get("kind", "agent_turn") != "agent_turn":
        raise ValueError("cron job has no command or agent_turn payload")
    message = str(payload.get("message") or "").strip()
    if not message:
        raise ValueError("agent_turn cron job is missing payload.message")
    cwd = str(job.get("cwd") or ".")
    parts = ["ohmo"]
    profile = payload.get("profile") or job.get("provider_profile")
    if profile is None and load_gateway_config is not None:
        profile = load_gateway_config().provider_profile
    if profile:
        parts.extend(["--profile", str(profile)])
    parts.extend(["--cwd", cwd, "--print", message])
    return " ".join(shlex.quote(part) for part in parts)
```

一条 `agent_turn` 任务最终变成 `ohmo --profile <profile> --cwd <cwd> --print "<message>"` ——这正是第一篇讲过的 `ohmo` 单次运行模式(`run_ohmo_print_mode()`)。也就是说,**cron 触发的 Agent 会话和用户手动在终端敲一次 `ohmo --print "..."` 走的是完全相同的入口**,只是触发者从"人手动敲命令"变成了"调度器在到期时拉起子进程"。这个设计选择解释了为什么 cron 不直接调用 gateway 的 `OhmoSessionRuntimePool`:调度器是一个独立守护进程,不能假设 gateway 进程一定在跑,子进程模式让"定时提醒"这类主动触发能力完全不依赖 gateway 的存活状态——哪怕用户从没启动过 `ohmo gateway run`,只要 cron 调度器在跑,定时任务照样能执行。

`execute_job()` 拉起这条命令后有一个硬性超时(300 秒),超时会 kill 掉子进程并记一条 `status="timeout"` 的历史;正常结束的执行结果(`stdout`/`stderr`/`returncode`)会被截断到最后 2000 字符后写入 `mark_job_run()` 更新的状态和一份 JSON Lines 历史(`cron_history.jsonl`)。

### 执行完成后的主动通知:不经过 gateway,直接用平台 SDK

任务跑完之后,如果配置了 `notify`,调度器会主动把结果推给用户——这一步同样不依赖 gateway 进程:

```python
# src/openharness/services/cron_scheduler.py:249-274(节选)
async def _notify_job_result(job: dict[str, Any], entry: dict[str, Any]) -> None:
    """Deliver an optional post-run notification for a cron job."""
    notify = job.get("notify")
    ...
    notify_type = str(notify.get("type") or "").strip().lower()
    try:
        if notify_type in {"feishu_dm", "feishu"}:
            from ohmo.gateway.notify import send_feishu_dm

            user_open_id = str(
                notify.get("user_open_id") or notify.get("open_id") or notify.get("to") or ""
            ).strip()
            if not user_open_id:
                raise ValueError("missing notify.user_open_id")
            workspace = notify.get("workspace")
            await send_feishu_dm(
                user_open_id=user_open_id,
                content=_format_notification(job, entry),
                workspace=str(workspace) if workspace else None,
            )
        elif notify_type:
            raise ValueError(f"unsupported notify.type: {notify_type}")
    except Exception as exc:
        entry["notification_status"] = "failed"
        entry["notification_error"] = str(exc)
    else:
        entry["notification_status"] = "sent"
```

`send_feishu_dm()`(`ohmo/gateway/notify.py`)读取的是 `~/.ohmo/gateway.json` 里保存的飞书 `app_id`/`app_secret`,用 `lark_oapi` 客户端直接调用飞书开放平台的"发送消息"接口:

```python
# ohmo/gateway/notify.py:38-53(节选)
def _send_feishu_text_sync(*, user_open_id: str, content: str, workspace: str | Path | None = None) -> None:
    """Send a Feishu direct message using ohmo gateway Feishu credentials."""
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

    config = load_gateway_config(workspace)
    feishu_config: dict[str, Any] = config.channel_configs.get("feishu", {})
    app_id = str(feishu_config.get("app_id") or "").strip()
    app_secret = str(feishu_config.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        raise OhmoNotificationError("Feishu app_id/app_secret are not configured in ohmo gateway config.")

    client = lark.Client.builder().app_id(app_id).app_secret(app_secret).log_level(lark.LogLevel.INFO).build()
    ...
```

这里的关键点是:通知走的是**另一条完全独立的路径**,不经过第二篇讲过的 `MessageBus`/`ChannelManager`,而是拿着配置文件里的凭证直接调用飞书 SDK 发消息。这意味着定时任务的"提醒"能力不需要 gateway 后台进程正在运行——凭证是静态配置,飞书开放平台的消息发送接口本身就是无状态的 HTTP 调用。第三篇提到的十种 channel 里,目前只有飞书接了这条主动通知路径(`notify_type` 目前只识别 `feishu_dm`/`feishu`),其余平台要接入类似能力需要在 `_notify_job_result()` 里补一个对应分支。

### Agent 自己管理定时任务:四个 cron 工具

`cron_create`/`cron_list`/`cron_toggle`/`cron_delete` 让 Agent 在对话里就能直接创建、查看、启停、删除自己的定时任务,不需要用户跳出对话去改配置文件。`CronCreateTool` 在真正落盘前做了两层校验,并且负责把用户的自然语言意图组装成 `payload`/`notify` 结构:

```python
# src/openharness/tools/cron_create_tool.py:54-101(节选)
async def execute(self, arguments: CronCreateToolInput, context: ToolExecutionContext) -> ToolResult:
    if not validate_cron_expression(arguments.schedule):
        return ToolResult(
            output=(
                f"Invalid cron expression: {arguments.schedule!r}\n"
                "Use standard 5-field format: minute hour day month weekday\n"
                "Examples: '*/5 * * * *' (every 5 min), '0 9 * * 1-5' (weekdays 9am)"
            ),
            is_error=True,
        )
    if not validate_timezone(arguments.timezone):
        return ToolResult(output=f"Invalid timezone: {arguments.timezone!r}", is_error=True)

    payload = dict(arguments.payload or {})
    if arguments.message:
        payload.setdefault("kind", "agent_turn")
        payload.setdefault("message", arguments.message)
    if arguments.notify is not None:
        payload.setdefault("deliver", True)
        if str(arguments.notify.get("type") or "").strip().lower() == "feishu_dm":
            payload.setdefault("channel", "feishu")
            payload.setdefault("to", arguments.notify.get("user_open_id") or arguments.notify.get("open_id"))
    ...
    job = {
        "name": arguments.name, "schedule": arguments.schedule,
        "cwd": arguments.cwd or str(context.cwd), "enabled": arguments.enabled,
    }
    if payload:
        payload.setdefault("kind", "agent_turn")
        job["payload"] = payload
    if arguments.notify is not None:
        job["notify"] = arguments.notify
    upsert_cron_job(job)
    ...
```

`cron_list` 工具是只读的(`is_read_only()` 返回 `True`),把每条任务的 schedule、上次/下次执行时间、通知目标、payload 摘要格式化成一段人类可读的文本,供 Agent 汇报现有任务清单;`cron_toggle`/`cron_delete` 分别薄封装 `set_job_enabled()`/`delete_cron_job()`。这四个工具合在一起,让"帮我设置一个每天早上的提醒"这类请求可以在一次对话里由 Agent 自己完成配置,不需要用户手写 cron 表达式或编辑 JSON 文件。

### 主动触发:`remote_trigger` 复用同一套命令构造逻辑

除了按计划执行,Agent(或用户)也可能想要"立刻跑一次这个任务,不等下一次调度时间"。`remote_trigger` 工具直接复用了 `cron_scheduler.py` 里的 `_command_for_job()`:

```python
# src/openharness/tools/remote_trigger_tool.py:31-48(节选)
async def execute(self, arguments: RemoteTriggerToolInput, context: ToolExecutionContext) -> ToolResult:
    job = get_cron_job(arguments.name)
    if job is None:
        return ToolResult(output=f"Cron job not found: {arguments.name}", is_error=True)

    cwd = Path(job.get("cwd") or context.cwd).expanduser()
    try:
        command = _command_for_job(job)
        process = await create_shell_subprocess(
            command, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except SandboxUnavailableError as exc:
        return ToolResult(output=str(exc), is_error=True)
    ...
```

它跳过了 `_jobs_due()` 的到期检查,直接拿已注册任务的定义构造命令并执行,执行结果同步返回给调用它的这次对话(而不是走 `notify` 异步推送)。这体现了一处很干净的复用:调度触发和主动触发共享同一份"任务定义 → 可执行命令"的翻译逻辑,唯一的区别是"谁决定现在该跑"——调度器由时间决定,`remote_trigger` 由一次工具调用决定。这也是为什么把 `_command_for_job()` 设计成一个独立、无副作用的纯函数如此重要:它同时被两个完全不同的调用方复用,任何一处修改命令构造逻辑的改动都会同时影响"按计划跑"和"立刻跑一次"两条路径,不需要维护两份逻辑。

## 常见问题/易踩坑

- **cron 触发的会话和一次正常的 gateway 会话是不同的会话。** 因为 `_command_for_job()` 拉起的是全新的 `ohmo --print` 进程,它不会复用 gateway 里某个聊天窗口正在维护的 `RuntimeBundle`(第二篇),也不会自动带上那个会话的历史上下文——`--print` 模式默认是无状态的一次性调用。如果需要定时任务延续某个长期会话的上下文,需要在设计 `payload.message` 时显式把必要信息写进 prompt。
- **执行有 300 秒硬超时,不适合跑长任务。** `execute_job()` 里 `asyncio.wait_for(process.communicate(), timeout=300)` 是写死的,超时会直接 kill 掉子进程并记为失败,设计定时任务时要考虑单次执行是否可能超过 5 分钟。
- **目前只有飞书接了主动通知。** `_notify_job_result()` 只认 `notify.type in {"feishu_dm", "feishu"}`,如果 `notify` 配置了其他类型(比如想通知 Telegram),会直接抛 `ValueError("unsupported notify.type: ...")` 并记录为通知失败——这不是执行失败,任务本身的 `status` 仍然正常,只是 `notification_status` 会标记为 `failed`。

## 小结

Cron 调度把"任务定义"(JSON 注册表 + `croniter` 计算下一次触发时间)、"调度循环"(独立守护进程,30 秒一次 tick)、"任务执行"(拉起与用户手动使用完全相同的 `ohmo --print` 入口)、"结果通知"(绕过 gateway、直接用平台 SDK 主动推送)这四个环节拆成了互相独立、可以分别失效而不拖垮整体的部分——即便 gateway 从未启动,提醒和定期汇报照样能工作。`remote_trigger` 工具复用了调度器同一套命令构造逻辑,让"立刻跑一次"和"按计划跑"共享同一份实现。至此,本章从 `ohmo` 的人格化设计(第一篇),到 gateway 如何路由消息驱动 Agent 会话(第二篇),到十种 IM 平台的统一接入(第三篇),再到主动触发能力(本篇),已经把"一个基于 OpenHarness 构建的个人 Agent App,是如何做到既能被动响应、又能主动触达用户"的完整链路讲清楚了。下一章我们会转向另一个关注可观测性的子系统——Autopilot 的运行快照机制,以及它如何驱动一个 React 仪表盘,把 Agent 的运行状态实时可视化出来。
