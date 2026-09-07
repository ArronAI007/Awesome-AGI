# Swarm 架构总览:Team、Worktree、Mailbox

> `oh` 的 `src/openharness/swarm/` 目录里没有一个叫 `Swarm` 的统一类,也没有一个"多智能体框架"式的顶层入口。它是四块相对独立的基础设施拼出来的:`team_lifecycle.py` 管一份团队元数据(`team.json`)在磁盘上怎么创建、增删成员、清理;`mailbox.py` 管队员之间怎么通过文件系统异步收发消息;`worktree.py` 管"如果多个队员要同时改同一个仓库,怎么给每个人一份独立的 git 工作树";`registry.py` 回答"这个队员到底该用子进程、同进程协程,还是 tmux/iTerm2 面板跑起来"。四者互不知道对方的实现细节,只靠一个共同的目录约定(`~/.openharness/teams/<name>/`)和 `types.py` 里几个数据类型串起来。本篇建立整套 swarm 子系统的心智地图,后面三篇再逐层往深处挖。

## 学习目标

- 理解 `types.py` 里 `TeammateExecutor`/`TeammateSpawnConfig`/`BackendType` 这组 Protocol 式契约,以及为什么 swarm 层不需要一个具体的"Team"基类。
- 弄清持久化的 `TeamFile`/`TeamMember`(`team_lifecycle.py`)和内存态的团队概念是两回事——本篇只讲前者,后者留给第三篇讲 coordinator 时对照。
- 理解 `worktree.py` 里 git worktree 隔离的完整流程:slug 校验、resume 判断、常见大目录的符号链接优化、清理时 `git worktree remove --force` 失败后的兜底路径。
- 理解 `mailbox.py` 的文件级消息队列如何做到"写入原子、并发安全":`.tmp` 文件 + `os.replace` + 跨平台排他锁三件套。
- 理解 `registry.py` 的后端探测优先级(`in_process` 回退 > `tmux` > `subprocess`)以及它和面板后端探测(`detect_pane_backend`)为什么是两条独立的判定逻辑。

## 背景与设计动机

多个 Agent 并行给同一个仓库干活,天然会撞上三类问题:

1. **谁负责跑哪个进程/协程/面板**——不同平台能力不同(Windows 没有 tmux,某些环境没有 iTerm2),不能假设一种执行方式在所有地方都可用。
2. **多个 Agent 同时改代码会不会互相踩踏**——如果大家共享同一份工作目录,一个 Agent 的未提交改动可能被另一个 Agent 的 `git checkout`/编辑冲掉。
3. **Agent 之间(以及 Agent 与 leader 之间)怎么通信**——如果执行方式是子进程或独立的 tmux pane,进程之间没有共享内存,消息只能靠文件系统或 stdin/stdout。

`swarm/` 目录的四个模块分别回答这三类问题,而且刻意做成互不依赖对方内部实现:`registry.py` 只依赖 `types.py` 里的 Protocol,`worktree.py` 完全不知道 mailbox 或 team 的存在,`mailbox.py` 只依赖一个目录路径函数 `get_team_dir()`。这种低耦合的代价是"团队"这个概念在代码里出现了不止一份定义——本篇讲持久化的那一份,第三篇会看到 coordinator 模式下还有一份纯内存的、语义完全不同的团队登记表。

## 核心机制详解

### 数据契约:`TeammateExecutor` 与 `TeammateSpawnConfig`

`types.py` 没有定义"Team"或"Member"类,而是先定义了一组 `Protocol`——具体后端要实现的契约:

```python
# src/openharness/swarm/types.py:357-388
@runtime_checkable
class TeammateExecutor(Protocol):
    """Protocol for teammate execution backends.

    Abstracts spawn/messaging/shutdown across subprocess, in-process, and tmux backends.
    """

    type: BackendType

    def is_available(self) -> bool: ...
    async def spawn(self, config: TeammateSpawnConfig) -> SpawnResult: ...
    async def send_message(self, agent_id: str, message: TeammateMessage) -> None: ...
    async def shutdown(self, agent_id: str, *, force: bool = False) -> bool: ...
```

`BackendType = Literal["subprocess", "in_process", "tmux", "iterm2"]` 一共四种。任何满足这三个方法签名的类都可以被 `registry.py` 注册为一个可用后端——`spawn`/`send_message`/`shutdown` 就是整个 swarm 层对"一个队员"能做的全部操作。配套的 `TeammateSpawnConfig` 是一次性传给 `spawn()` 的完整配置(名字、team、prompt、cwd、model、system_prompt、权限列表、worktree_path、subscriptions 等),`SpawnResult` 是返回值(task_id、agent_id、backend_type、成功与否)。第二篇会具体拆开 `subprocess`/`in_process` 两个后端的实现;`tmux`/`iterm2` 走的是另一条 `PaneBackend` Protocol(同样定义在 `types.py`),负责终端面板的创建、着色、隐藏/显示——这条路径专用于把 swarm 可视化到终端窗口里,和后端执行没有强制绑定关系。

### 持久化的团队:`TeamFile` / `TeamMember`

`team_lifecycle.py` 把团队定义为磁盘上的一份 JSON:

```python
# src/openharness/swarm/team_lifecycle.py:1-9
"""Persistent team lifecycle management for OpenHarness swarms.

Teams are stored as JSON files on disk:
    ~/.openharness/teams/<name>/team.json

This module provides TeamMember, TeamFile, AllowedPath, TeamLifecycleManager
and a full set of CRUD helpers matching the TS teamHelpers.ts API.
"""
```

`TeamMember` 是这份 JSON 里每个成员的完整快照,字段覆盖了一个队员运行期间可能需要追踪的一切:`backend_type`、`session_id`(用于按会话反查)、`color`、`mode`(权限模式)、`tmux_pane_id`、`cwd`、`worktree_path`、`status`。`TeamLifecycleManager` 本身被设计成**无状态**——每个方法都是"读磁盘 → 改内存对象 → 整体写回磁盘",不缓存任何内容,注释里明确写着"这样可以安全地多次实例化"。写入用的是标准的原子替换:

```python
# src/openharness/swarm/team_lifecycle.py:263-268
def save(self, path: Path) -> None:
    """Atomically write this team file to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
    tmp.rename(path)
```

比较值得注意的是会话结束时的清理顺序。`cleanup_session_teams()` 只清理"本次会话新建、且没有被显式删除"的团队(靠 `_session_created_teams` 这个模块级 set 追踪,配合 `register_team_for_session_cleanup`/`unregister_team_for_session_cleanup` 两个登记/取消登记函数),而且清理时**先杀面板再删目录**:

```python
# src/openharness/swarm/team_lifecycle.py:679-687(节选)
teams = list(_session_created_teams)
# Kill panes first — on SIGINT the teammate processes are still running;
# deleting directories alone would orphan them in open tmux/iTerm2 panes.
await asyncio.gather(
    *(_kill_orphaned_teammate_panes(t) for t in teams),
    return_exceptions=True,
)
await asyncio.gather(
    *(cleanup_team_directories(t) for t in teams),
    return_exceptions=True,
)
```

这个顺序不是随意的:如果 leader 进程被 SIGINT 打断,tmux/iTerm2 面板里跑着的队员进程并不会因为 `team.json` 被删除而自动退出——它们是独立的操作系统进程或终端窗口。先把面板杀掉,再删目录,才不会留下一堆孤儿进程占着终端。`cleanup_team_directories()` 还会在删除团队目录之前,先把每个成员记录的 `worktree_path` 逐个销毁(下一节详细展开)——如果反过来先删目录,`team.json` 里记录的 worktree 路径信息就丢了,孤儿工作树就再也找不回来了。

### git worktree 隔离:每个队员一份独立工作树

`worktree.py` 解决的是"多个队员同时改同一个仓库,文件系统层面互不干扰"的问题。核心是 `WorktreeManager.create_worktree()`,对应真实的 `git worktree add`:

```python
# src/openharness/swarm/worktree.py:194-202(节选)
# New worktree: -B resets an orphan branch left by a prior remove
code, _, stderr = await _run_git(
    "worktree", "add", "-B", worktree_branch, str(worktree_path), "HEAD",
    cwd=repo_path,
)
if code != 0:
    raise RuntimeError(f"git worktree add failed: {stderr}")

await _symlink_common_dirs(repo_path, worktree_path)
```

几个设计细节值得展开:

- **`-B` 而不是 `-b`**:`-B` 会强制重置分支到 `HEAD`,即便同名分支已经存在。注释说明这是为了兼容"上一次 worktree 被移除后残留的孤儿分支"——如果用 `-b`,重新创建同名 worktree 时会因为分支已存在而直接失败。
- **resume 而不是每次新建**:`create_worktree()` 先检查 `worktree_path` 是否已存在且是一个合法的 git 目录(`git rev-parse --git-dir` 返回 0),是的话直接复用,不重新跑 `git worktree add`——这让同一个队员多次重启时不会反复创建/销毁工作树。
- **大目录符号链接而非复制**:`_symlink_common_dirs()` 会把 `node_modules`、`.venv`、`__pycache__`、`.tox` 这几个体积可能很大、通常不需要按 worktree 隔离的目录从主仓库软链接过来,避免每个队员的 worktree 都重新装一遍依赖。这是一个纯粹的性能优化,失败(比如文件系统不支持符号链接)不影响功能,只是静默跳过。
- **slug 校验防路径穿越**:`validate_worktree_slug()` 限制 slug 长度(64 字符)、拒绝 `.`/`..` 段、拒绝绝对路径开头——因为 slug 最终会被拼进磁盘路径(`base_dir / slug`),不校验就是一个路径穿越漏洞。

清理路径 `remove_worktree()` 优先走 `git worktree remove --force`,通过 `git rev-parse --git-common-dir` 反查出主仓库路径来执行;`team_lifecycle.py` 里的 `_destroy_worktree()` 则是一条更保守的独立实现——同样先尝试 `git worktree remove --force`,如果 git 命令本身失败(比如主仓库已经被移动或删除),兜底直接 `shutil.rmtree`,并且把 `"not a working tree"` 这个 stderr 内容当作"已经不是 worktree 了,视为成功"而不是报错。两处清理逻辑没有复用同一份代码,是因为 `team_lifecycle.py` 的清理场景更极端(可能发生在 leader 异常退出之后),需要对"主仓库路径推导失败"这种情况更宽容。

### mailbox:基于文件系统的异步消息队列

如果队员是独立子进程或独立 tmux 面板,进程之间没有共享内存,`mailbox.py` 就是它们之间通信的唯一通道——每条消息是收件人 inbox 目录下的一个独立 JSON 文件:

```python
# src/openharness/swarm/mailbox.py:126-151(节选)
async def write(self, msg: MailboxMessage) -> None:
    inbox = self.get_mailbox_dir()
    filename = f"{msg.timestamp:.6f}_{msg.id}.json"
    final_path = inbox / filename
    tmp_path = inbox / f"{filename}.tmp"
    lock_path = inbox / ".write_lock"

    payload = json.dumps(msg.to_dict(), indent=2)

    def _write_atomic() -> None:
        with exclusive_file_lock(lock_path):
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, final_path)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _write_atomic)
```

写入是"先写临时文件,再原子重命名"——读者(`read_all()`)永远不会看到半个 JSON 文件。文件名以时间戳开头,天然按字典序排序就是时间序,`read_all()` 直接 `sorted(inbox.glob("*.json"))` 就能拿到有序的消息列表,不需要额外维护一个索引。锁(`.write_lock`,基于 `exclusive_file_lock`,posix 下是 `fcntl.flock`、Windows 下是 `msvcrt.locking`)保护的是"写入这一小段临界区",而不是整个 inbox 目录的读写——多个写者可以安全地并发写不同的消息文件,锁只防止两次写入互相踩到同一个 `.tmp` 文件名。

消息类型(`MessageType`)覆盖了几类场景:`user_message`(普通文本)、`permission_request`/`permission_response`(权限审批,第二篇细讲)、`sandbox_permission_request`/`sandbox_permission_response`(沙箱网络访问审批)、`shutdown`、`idle_notification`。工厂函数(`create_user_message`、`create_shutdown_request` 等)统一了消息构造,而 `is_permission_request()` 这类类型判断函数额外做了一层兼容:除了检查 `msg.type` 字段,还会尝试把 `payload.get("text")` 当 JSON 解析——这是为了兼容"文本信封"格式的消息(比如子进程队员通过 stdin 收到的是纯文本,统一包装成 mailbox 消息后 `type` 字段可能没有被正确设置,只能从内容里再判断一次)。

### registry:自动探测该用哪个执行后端

`BackendRegistry` 是四个模块里唯一做"决策"的一环——它决定一个队员具体用哪种方式跑起来:

```python
# src/openharness/swarm/registry.py:128-183(节选)
def detect_backend(self) -> BackendType:
    if self._detected is not None:
        return self._detected

    # Priority 1: in-process fallback (activated after a prior failed spawn)
    if self._in_process_fallback_active:
        self._detected = "in_process"
        ...
        return self._detected

    # Priority 2: tmux (inside session + binary available)
    inside_tmux = _detect_tmux()
    if inside_tmux:
        if "tmux" in self._backends:
            self._detected = "tmux"
            ...
            return self._detected

    # Priority 3: subprocess (always available)
    self._detected = "subprocess"
    ...
    return self._detected
```

优先级是:如果之前发生过 spawn 失败并调用了 `mark_in_process_fallback()`,则本次进程生命周期内永远优先选 `in_process`(因为运行环境显然不支持面板后端,没必要每次都重新探测);否则如果当前就跑在一个 tmux 会话里(`$TMUX` 环境变量 + `tmux` 二进制都存在)且 tmux 后端已注册,选 `tmux`;都不满足则退回 `subprocess`——这是唯一保证在任何平台、任何终端环境下都可用的后端。

注意这里有一个诚实的现状:`_register_defaults()` 目前只无条件注册 `subprocess`,并在 `get_platform_capabilities().supports_swarm_mailbox`(仅 macOS/Linux/WSL 为真,Windows 为假)为真时额外注册 `in_process`;`tmux` 后端的注册被显式推迟——注释写的是"if a TmuxBackend is available it can be registered via `register_backend()`",也就是说 `detect_backend()` 的 tmux 分支目前永远走不到"`"tmux" in self._backends`"为真的那一步,除非有外部代码调用 `register_backend()` 注入一个 tmux 实现。

另一条独立的探测逻辑是 `detect_pane_backend()`,专门用于终端可视化(把每个队员的输出显示成一个终端面板),优先级和 `detect_backend()` 完全不同:tmux 会话内永远优先 tmux;iTerm2 里优先原生 `iterm2`(需要 `it2` CLI),`it2` 不可用则退化到 tmux 并标记 `needs_setup=True`;两者都不满足则报错并给出平台相关的安装指引(`_get_tmux_install_instructions()` 针对 macOS/Linux/Windows+WSL 分别给出不同提示)。这条路径与执行后端的选择是正交的——一个队员完全可以用 `subprocess` 后端执行,同时被显示在一个 tmux 面板里。

## 小结

四个模块拼出的图景是:`types.py` 定义"一个队员该有什么样的执行接口"这份契约;`team_lifecycle.py` 把"一个团队有哪些成员、他们的状态是什么"持久化成磁盘上的 JSON,并负责在会话异常退出时按正确顺序清理;`worktree.py` 用标准 git worktree 机制解决多队员并发改代码的文件系统隔离,同时用符号链接优化大依赖目录的存储开销;`mailbox.py` 用"文件即消息"的方式在没有共享内存的进程之间传递结构化消息,靠原子重命名和跨平台文件锁保证并发安全;`registry.py` 则在运行时根据平台能力和当前所处环境,选出一个具体的 `TeammateExecutor` 实现。下一篇会深入 `registry.py` 探测出的两种主流执行后端——`subprocess_backend.py` 和 `in_process.py`——具体对比它们各自的隔离代价与启动开销,以及 `spawn_utils.py` 里启动一个队员到底要准备哪些环境变量和 CLI 参数。
