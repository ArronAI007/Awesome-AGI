# Cron 调度——本地 Tick 与 Chronos 托管无服务器化

> 定时任务在自托管场景下很好办:反正 gateway 进程本来就要一直跑着接收消息,顺手每 60 秒检查一次有没有到期的任务,成本几乎为零。但如果 gateway 跑在托管云平台上、按使用量计费,"一直跑着"本身就是主要成本——用户可能一天只触发一次定时任务,却要为 24 小时的常驻轮询付费,平台也希望能在空闲时把实例缩到零。hermes-agent 用一层可插拔的调度器抽象(`cron.scheduler_provider.CronScheduler`)把这两种模式统一起来:本地默认走进程内 60 秒轮询(`cron/scheduler.py`),托管场景可以换成 Chronos——把"何时触发"这件事外包给云端账户服务(NAS)按需注册的精确单次定时器,到点由 NAS 回调一个短期 JWT 鉴权的 webhook 把 agent 唤醒。本篇先讲本地 tick 的文件锁并发控制,再完整拆开 Chronos 的信任模型和触发时序,最后说清楚"从进程内轮询到事件驱动 serverless 化"这次架构演进解决的到底是什么问题。

## 学习目标

- 理解 `cron/scheduler.py::tick()` 一次调用做的事情:文件锁防重叠、失联 owner 回收、推进 `next_run_at`、按并发上限并行执行到期任务。
- 理解为什么文件锁的错误处理要精确区分"锁被占用"(正常跳过)和"真正的系统错误如 fd 耗尽"(必须让调用方看到失败),而不能笼统地把任何异常都当成"另一个实例持有锁"。
- 理解 `cron.scheduler_provider.CronScheduler` 这层抽象如何让"本地 60 秒轮询"与"Chronos 托管一次性定时器"共享同一套到期任务执行逻辑(`run_one_job`/`fire_claimed`),差异只在"如何知道任务到期了"。
- 完整复述 Chronos 的三跳信任链(agent→NAS、scheduler→NAS、NAS→agent)以及为什么触发不能让外部调度器直接回调 agent。
- 理解"进程内轮询"与"外部 one-shot + webhook 回调"两种模式在托管场景下的成本本质区别,说清楚为什么常驻 60 秒轮询在"scale to zero"场景下是不可接受的。
- 知道 Chronos 不可用时系统如何优雅退化回内置轮询,理解这条 fallback 规则对"cron 永远不会失去触发能力"这一承诺的意义。

## 本地默认模式:60 秒 Tick 与文件锁

`cron/scheduler.py` 的模块文档一句话说清楚了默认模式:

```python
# cron/scheduler.py:1-8
"""
Cron job scheduler - executes due jobs.

Provides tick() which checks for due jobs and runs them. The gateway
calls this every 60 seconds from a background thread.

Uses a file-based lock (~/.hermes/cron/.tick.lock) so only one tick
runs at a time if multiple processes overlap.
"""
```

真正驱动这套轮询的是 `cron.scheduler_provider.InProcessCronScheduler.start()`——一个跑在守护线程里、直到 `stop_event` 被置位才退出的 `while` 循环:

```python
# cron/scheduler_provider.py:611-651(节选)
consecutive_failures = 0
while not stop_event.is_set():
    ok = False
    try:
        if can_dispatch is not None and not can_dispatch():
            logger.debug("Cron dispatch paused while gateway drains existing work")
        else:
            cron_tick(verbose=False, adapters=adapters, loop=loop, sync=False, can_dispatch=can_dispatch)
        ok = True
    except BaseException as e:
        logger.error("Cron tick error: %s", e, exc_info=True)
        record_ticker_error(f"{type(e).__name__}: {e}")
        consecutive_failures = _note_tick_failure(e, consecutive_failures)
    record_ticker_heartbeat(success=ok)
    if ok:
        clear_ticker_error()
        consecutive_failures = 0
    stop_event.wait(_backoff_wait_seconds(interval, consecutive_failures))
```

几个值得注意的细节:异常捕获用的是 `BaseException` 而不是 `Exception`——连 `SystemExit`/`KeyboardInterrupt` 都要接住,否则某个 provider SDK 内部误触发的 `SystemExit` 会悄悄杀死这个守护线程,而 gateway 的正常关闭另有 `stop_event` 驱动,不应该被这里的异常处理干扰。每次 tick 无论成败都记一次心跳,只有真正 tick 失败才计入"连续失败次数"并触发退避等待(`_backoff_wait_seconds`)——这条退避路径专门为 fd 耗尽(`EMFILE`/`ENFILE`)设计:文件描述符耗尽期间不应该每 60 秒继续锤一次存储层,而应该指数退避,一旦资源恢复(泄漏修复、`_reclaim_fds_best_effort()` 生效)下一次 tick 成功就立刻把退避重置。

**文件锁**是防止多进程重叠的核心机制——网关自带的进程内 ticker、一个独立部署的 daemon、或者一次手动 `hermes cron run`,都可能同时对着同一份 `jobs.json` 起作用。`tick()` 用跨平台的文件锁(Unix `fcntl`,Windows `msvcrt`)在函数入口抢一次非阻塞锁:

```python
# cron/scheduler.py:7693-7750(节选)
lock_fd = open(lock_file, "w", encoding="utf-8")
if fcntl:
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
elif msvcrt:
    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
```

这里最值得学的不是"用了文件锁",而是**错误处理必须精确区分"锁被占用"和"系统调用真的失败了"这两类完全不同的 `OSError`**——如果笼统地把任何异常都当作"另一个实例持有锁"然后安静跳过,fd 耗尽这种真正的故障会被伪装成"一切正常,只是这次跳过了",tick 返回 0、心跳标记成功,但实际上调度器已经彻底瘫痪、再也不会执行任何任务,而这个假象可能持续很久才被发现(源码注释里提到的 #87644 就是这样一次真实事故):

```python
# cron/scheduler.py:1580-1591(节选)
def _is_lock_contention_errno(err: OSError) -> bool:
    """Return True when *err* from the lock syscall means the lock is held.
    - POSIX: flock(LOCK_EX|LOCK_NB) reports EWOULDBLOCK/EAGAIN ...
    - Windows: msvcrt.locking(LK_NBLCK) reports EACCES/EDEADLK.
    """
```

只有精确匹配这几个"锁竞争专属"的 errno 才安静跳过;其余一律 `raise`,让调用方(ticker 循环)据此把这次 tick 记成失败、驱动退避与告警。

拿到锁之后,`tick()` 内部的顺序也值得记住:先做"失联 owner 回收"(一个 `hermes cron run` 一次性进程认领了任务却中途死掉,长期存在的 gateway ticker 要定期把这类"僵尸认领"清理掉,否则那个任务永远卡在 `claimed` 状态)、再取到期任务列表、再对"卡死太久的并发认领"做一次兜底扫描,然后**在任何任务真正开始执行之前**,先在文件锁的保护下把这批到期任务的 `next_run_at` 统一推进一次:

```python
# cron/scheduler.py:7846-7854(节选,注释)
# Advance next_run_at for all recurring jobs FIRST, under the file lock,
# before any execution begins.  This preserves at-most-once semantics.
```

这保证了"最多执行一次"的语义:即使某个任务的执行本身耗时很长、跨越了好几个 tick 周期,它的下一次触发时间早已经在第一次被认领时就确定下来,不会因为执行慢而被重复触发。到期任务本身按 `cron.max_parallel_jobs`(或环境变量覆盖)在线程池里并发跑,默认无上限(`HERMES_CRON_MAX_PARALLEL=1` 可以退回严格串行)。

## 可插拔的调度器抽象:本地轮询与托管触发共用同一套执行体

本地 60 秒轮询不是唯一的触发方式,`cron.scheduler_provider.CronScheduler` 是一个抽象基类,`resolve_cron_scheduler()` 负责根据配置选出具体实现:

```python
# cron/scheduler_provider.py:476-510(节选)
def resolve_cron_scheduler() -> "CronScheduler":
    """... Reads ``cron.provider`` from config. Empty/absent → built-in. A
    named provider that is missing, fails to load, or reports
    ``is_available() == False`` falls back to the built-in with a warning —
    cron must never be left without a trigger."""
    name = (cfg_get(load_config(), "cron", "provider", default="") or "").strip()
    if not name or name in ("builtin", "in-process", "inprocess"):
        return InProcessCronScheduler()
    provider = load_cron_scheduler(name)
    if provider is None or not provider.is_available():
        logger.warning(...)
        return InProcessCronScheduler()
    return provider
```

这条 fallback 链是"cron 永远不会失去触发能力"这个承诺的具体实现——不管是没配置 provider、配置了一个不存在的 provider、provider 加载抛异常,还是 provider 自己判断当前环境不满足条件(比如没有登录、没有配置回调地址),最终都会稳妥地退回内置轮询,而不是让定时任务从此静默失效。

两种实现之间真正共享的是任务执行的核心体——`run_one_job`/`fire_claimed` 这条"认领 → 执行 → 投递结果 → 标记完成"的流水线对触发来源一无所知。本地轮询里 `tick()` 直接调用它;Chronos 里同名的方法链路被复用,只是"知道任务到期了"这件事换了一种方式获知。这正是"传输层与执行层解耦"的具体应用:调度触发的机制可以替换,执行一个到期任务这件事的逻辑只写一次。

## Chronos:让托管 gateway 能够 scale to zero

`docs/chronos-managed-cron-contract.md` 是这套托管方案的权威线协议文档,开篇就点出了动机:

```
Chronos lets a hosted Hermes gateway **scale to zero** while idle and still
fire cron jobs. Instead of an in-process 60-second ticker, the agent asks NAS
to arm exactly **one external one-shot per job at that job's real next-fire
time**. NAS calls the agent back at fire time over an authenticated webhook;
the agent runs the job and re-arms the next one-shot. Between fires the agent
process can be fully stopped — it wakes only on a genuine fire.
```

**为什么常驻轮询在托管场景下不可接受**:自托管时,gateway 进程本来就要为了接收即时消息一直跑着,每 60 秒多做一次"有没有到期任务"的检查几乎不产生边际成本。但托管平台按使用量计费、并且希望空闲实例能缩到零——如果 cron 的实现方式是"进程必须存在才能轮询",那就意味着只要用户配置了任何一个定时任务,这个实例就永远不能真正缩到零,常驻的边际成本变成了主要成本。Chronos 把"什么时候该醒来"这件事从 agent 自己巡查,倒转成外部服务按精确时间点主动通知——两次真正的任务触发之间,agent 进程可以完全停止,不需要有任何东西在后台空转计时。

### 三跳信任链

Chronos 从不直接让外部调度器回调 agent,而是设计了一条三跳链路,时序可以重画成:

```
agent                          NAS (nous-account-service)              scheduler(NAS内部实现细节)
  │  provision(job_id, fire_at, callback_url)                                  │
  │ ── Bearer: agent 自己的 Nous 访问令牌 ────────────────────►  │                              │
  │                                              armed 一个 one-shot,目标是 NAS 自己的 relay 路由
  │                                                                  │                              │
  │                                                                  │  ⏰ fire_at 到达               │
  │                                                                  │ ◄──── relay(签名鉴权) ───────┤
  │                                                        NAS 校验 scheduler 签名
  │                                                        NAS 现铸一个短期 JWT(aud=agent:{id}, purpose=cron_fire)
  │ ◄── POST /api/cron/fire  Bearer: 那个 JWT ──────────────────┤
  │  agent 验签 JWT → 存储层 CAS 认领 → 执行任务 → 重新 provision 下一次
```

之所以要绕一道 NAS 而不是让外部调度器直接敲 agent 的 webhook,原因写在信任模型表里:

```
| Hop | Who calls whom | Auth mechanism | Verified by |
|---|---|---|---|
| 1 | agent → NAS (provision/cancel/list) | agent 的 Nous Portal 访问令牌 | NAS |
| 2 | scheduler → NAS (relay) | scheduler 的请求签名 | NAS |
| 3 | NAS → agent (/api/cron/fire) | 短期 NAS 铸造的 JWT(aud=agent:{instance_id}, purpose=cron_fire) | agent(用 NAS 的 JWKS 验签)|
```

文档给出的核心理由是:"scheduler 用**NAS 自己**的密钥签名,而 agent 既不持有、也不应该持有那把密钥。agent 只能验证一个**NAS 铸造**的令牌——这是它已经具备的信任路径。" 换句话说,把外部调度器的凭据全部关在 NAS 内部,agent 完全不知道、也不需要知道背后具体用的是哪家调度服务——这是本篇提到的第三次"把外部实现细节关在一层抽象后面"的设计,与前两篇的委派 Provider、平台注册表异曲同工。这一路径不需要给 agent 引入任何新的密钥类型:第一跳复用 agent 本来就有的 Portal 令牌,第三跳复用 agent 本来就会做的 NAS-JWT 验签逻辑。

### 三个端点各自做什么

- **`POST /api/agent-cron/provision`(agent → NAS)**——请求(重新)安排一个任务的下一次单次触发,携带 `job_id`/`fire_at`(agent 自己算出来的精确时间,可以是秒级)/`agent_callback_url`/`dedup_key`(`"{job_id}:{fire_at}"`,让重复安排同一次触发是幂等的,NAS 按 `(agent_id, job_id)` upsert)。NAS 只负责把这个一次性定时器安排在自己内部的调度实现上,目标地址是 NAS 自己的 relay 路由,不是 agent。
- **`POST /api/agent-cron/cancel`(agent → NAS)**——取消已安排的一次性定时器,对未知任务幂等返回成功。
- **`POST /api/agent-cron/relay`(scheduler → NAS)**——真正的触发中转站。NAS 校验 scheduler 的签名后,现铸一个作用域极窄的短期 JWT(`aud` 锁定这个具体的 agent 实例、`purpose=cron_fire`、有效期约 60-120 秒),用它去调 agent 的回调地址。scheduler 收到的响应只要是 2xx 就不再重试,agent 那侧收到非 2xx 会被当作可重试失败——因为 agent 侧的存储层 CAS 认领机制保证重复触发不会重复执行。

### Agent 侧的验签与幂等执行

`POST /api/cron/fire`(NAS → agent)在真实代码里由 `plugins/cron_providers/chronos/verify.py` 实现(文档里写的路径是 `plugins/cron/chronos/verify.py`,与实际目录 `plugins/cron_providers/chronos/` 有出入,读者对照代码时留意这一点)。验证逻辑完全匹配文档描述的四项检查——签名、`aud`、`iss`、`purpose`:

```python
# plugins/cron_providers/chronos/verify.py:79-141(节选)
def verify_nas_fire_token(token, *, expected_audience, jwks_url, issuer=None):
    """
      - ``aud`` == ``expected_audience`` (this agent: ``agent:{instance_id}``).
      - ``iss`` == ``issuer`` when an issuer is configured.
      - ``purpose`` == ``"cron_fire"`` — so a general agent JWT can't be
        replayed against this endpoint.
    """
    ...
    if claims.get("purpose") != _FIRE_PURPOSE:
        logger.warning("cron fire: token missing/!=%s purpose claim", _FIRE_PURPOSE)
```

值得一提的是验签用的 `PyJWKClient` 按 JWKS URL 做了进程级缓存,而不是每次触发都新建一个客户端——原始实现每次都新建,导致并发触发时对 NAS 的 JWKS 端点发起大量同步 HTTP 请求,被限流(403),进而验签失败、agent 错误地回 401;甚至在 JWKS 拉取只是"慢"而非被限流的情况下,同步请求会阻塞事件循环,导致 fire webhook 来不及在 relay 的 30 秒超时前返回 202,最终在生产环境表现为集中在"任务数多的实例上"的 504。这是"托管场景下,一个看似无害的每次都重新构造客户端的写法,在真实并发下会变成限流和超时故障"的一个具体案例。

验签通过之后,agent 用存储层的 compare-and-set 操作认领这个任务(`claim_job_for_fire`),在认领成功之前立即返回 `202 {"status": "accepted", ...}`——响应本身不等任务真正跑完,这样一次执行时间较长的任务不会拖累 relay 的 HTTP 超时。真正执行走的还是本地模式共用的那条 `run_one_job` 流水线。

### 至多一次与重新安排

- **周期性任务**(cron 表达式或固定间隔):触发时在存储锁保护下推进 `next_run_at`(与本地模式的"先推进再执行"是同一条原则),执行完毕后重新调用 `provision` 安排下一次单次触发。一次迟到的重复 relay 请求会发现"认领已被拿走或时间已推进",从而安全地被丢弃。
- **一次性任务**(`30m`、`+90s` 这类):触发一次,`mark_job_run` 标记完成,不再重新安排。
- **`repeat.times = N` 到达上限**:任务被直接删除,`get_job` 返回 `None`,agent 因此不会重新安排——定时序列干净地终止,不会留下一个孤儿定时器。
- **多副本部署**:多个 gateway 副本共享同一个 `HERMES_HOME` 存储时,CAS 认领保证同一次触发只有一个副本真正执行。

### 自愈式对账(reconcile),而非周期性唤醒

Chronos 侧的 `ChronosCronScheduler` 实现完整印证了文档描述的约束——`start()` 只做一次性的"把所有启用任务安排好"然后立刻返回,绝不引入任何周期性唤醒:

```python
# plugins/cron_providers/chronos/__init__.py:103-117(节选)
def start(self, stop_event, *, adapters=None, loop=None, interval=60):
    """Arm all enabled jobs via NAS, then RETURN immediately.
    Does NOT block and does NOT spawn a 60s wake (DQ-1) — that is the
    whole point of scale-to-zero. The machine wakes only on a NAS→agent
    fire."""
    self.recover_interrupted()
    try:
        self.reconcile()
    except Exception as e:
        logger.warning("Chronos start() reconcile failed: %s", e)
    # Intentionally return — no loop, no periodic wake.
```

`reconcile()` 只在"进程本来就是热的"这几个时机被调用——启动、任务被用户增删改、以及每次触发之后顺手做一次(见 `fire_claimed` 里触发成功后重新 `_arm_one_shot`)——而不是靠一个定时器周期性唤醒一台本该睡着的机器:

```python
# plugins/cron_providers/chronos/__init__.py:194-224(节选)
def reconcile(self) -> None:
    """Converge the NAS-armed one-shots toward jobs.json (desired state):
    arm missing / re-arm changed-time, cancel orphaned."""
    desired = {j["id"]: j["next_run_at"] for j in load_jobs() if j.get("enabled") ...}
    observed = self._list_armed()
    for job_id, fire_at in desired.items():
        if observed.get(job_id) != fire_at:
            ...
            self._arm_one_shot(job)
    for job_id in list(observed.keys()):
        if job_id not in desired:
            self._cancel(job_id)
```

这是一套标准的"期望状态 vs 观测状态"对账逻辑:本地 `jobs.json` 是期望状态,NAS 那边已安排的一次性定时器集合是观测状态,对账只做差集——缺的补上、多的取消。任何一次瞬时的 NAS 调用失败(比如 `provision` 网络抖动没安排成功)都会在下一次自然发生的对账时机自愈,不需要额外的重试轮询。

### 可用性判定与逃生舱

`is_available()` 只做本地配置检查、绝不发起网络请求——这是为了配合 `resolve_cron_scheduler()` 的 fallback 规则,`is_available` 本身必须便宜且离线可判断:

```python
# plugins/cron_providers/chronos/__init__.py:64-74(节选)
def is_available(self) -> bool:
    """Config presence only — NO network."""
    if not (_cfg("cron", "chronos", "portal_url") and _cfg("cron", "chronos", "callback_url")):
        return False
    return self._have_nous_token()
```

只要缺一样(portal 地址、回调地址、Nous 登录态),Chronos 就判定不可用,`resolve_cron_scheduler()` 随即退回内置轮询——对自托管用户而言,这条判定天然为假,他们完全不需要关心 Chronos 存在。文档里还专门留了一条"逃生舱":如果未来 NAS 中转的调用量真的撑不住,可以把入站验证器换成"直接的 scheduler → agent 模式 + per-job 的 NAS 铸造密钥",而完全不需要改动 webhook 处理器本身——这再次体现了"验证逻辑可插拔"(`get_fire_verifier()`)这条设计线。

## 小结与思考题

本地默认模式用一个 60 秒一轮的进程内 `while` 循环 + 跨平台文件锁,把"检查到期任务"做成一个能容忍多进程短暂重叠、能在 fd 耗尽等真实故障下正确退化成"失败并告警"而不是"假装健康"的轮询器;`next_run_at` 的推进永远发生在执行之前,保证"最多执行一次"。当这套轮询的边际成本在托管计费场景下变得不可接受时,Chronos 把触发方式换成了"外部一次性定时器 + 认证 webhook 回调",本质是把"agent 主动巡查时间"倒转成"外部服务按时间点主动通知 agent",让两次真正的任务触发之间进程可以完全停止。三跳信任链(agent 的 Portal 令牌 → NAS 内部签名 → NAS 铸造的短期 JWT)把外部调度器的密钥完全关在 NAS 内部,agent 只需要维持它本来就有的一条信任路径。两种模式共享同一套"认领 → 执行 → 结果投递"的核心逻辑,只是"如何知道任务到期了"这一层被替换,而 Chronos 不可用时系统会稳妥退回内置轮询,cron 永远不会真正失去触发能力。

思考题:

1. Chronos 的 `dedup_key` 用 `"{job_id}:{fire_at}"` 让重复 `provision` 幂等。如果一个周期性任务的执行时间超过了两次触发之间的间隔(比如每 5 分钟触发一次,但单次执行要跑 8 分钟),"执行完毕后才重新 provision 下一次"这个时序会不会导致某一次触发被跳过?这和本地模式"先推进 `next_run_at` 再执行"的顺序相比,在"迟到执行"的语义上有什么本质区别?
2. `is_available()` 被要求绝对不能发起网络请求,只能检查本地配置和登录态缓存。如果 Nous 登录令牌本地显示"存在"但实际已经在服务端被吊销,`provision` 调用会在什么时候才发现这个问题?这种"乐观判断可用、真正调用时才发现不可用"的设计,与前一篇平台注册表里"被动探测 vs 主动安装"拆分两个字段的思路,是否是同一类工程取舍?
