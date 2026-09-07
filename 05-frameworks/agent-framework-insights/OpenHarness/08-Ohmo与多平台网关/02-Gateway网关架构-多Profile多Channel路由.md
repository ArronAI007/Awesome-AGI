# Gateway 网关架构——多 Profile、多 Channel 路由

> 一条消息从 Telegram/飞书/Slack 进来,到变成用户手机上收到的那条回复,中间要经过四层:`ChannelManager` 把平台专属的协议收敛成统一事件,`MessageBus` 用一对 `asyncio.Queue` 把"接消息"和"跑 Agent"解耦,`OhmoGatewayBridge` 按会话把消息路由给正确的运行时并处理打断/停止/重启这类控制命令,`OhmoSessionRuntimePool` 则为每个会话维护一个 `RuntimeBundle`——而这个 `RuntimeBundle` 正是复用 `openharness.ui.runtime.build_runtime()` 构建出来的,与上一篇讲的 `ohmo` CLI 走的是同一个函数。这里有一个容易被文件名误导的地方:`ohmo/gateway/bridge.py` 这个名字很容易让人联想到 OpenHarness 另一套叫 `openharness.bridge` 的机制,但读代码可以确认两者没有任何 import 关系——本文会先讲清楚真正的复用点在哪里,再澄清这个命名巧合。

## 学习目标

- 理解从 IM 平台收到一条消息,到该消息被路由到正确 session、驱动一次 Agent 会话、再发回原平台的完整链路,以及链路上每一层各自的职责边界。
- 理解 `session_key_for_message()` 的路由规则:私聊、群聊、带 thread 的群聊分别映射到什么样的 session key,以及为什么共享会话要把 `sender_id` 也编码进 key。
- 理解 `OhmoSessionRuntimePool` 如何为每个 session key 维护一个独立的 `RuntimeBundle`,以及它复用的 `build_runtime()` 与 `ohmo` CLI(第一篇)用的是不是同一个函数——用代码验证,而不是猜测。
- 弄清 `ohmo/gateway/bridge.py` 和 `openharness.bridge` 这两个同名但无关的模块分别是做什么的,避免被命名误导。
- 理解 `OhmoGatewayService` 如何管理 gateway 作为后台服务的生命周期:前台运行、后台进程启动/停止、状态查询、以及"重启"具体是怎么实现的。

## 背景与设计动机

`ohmo gateway` 要解决的问题很直接:用户在 Telegram 或飞书里发一条消息,`ohmo` 应该像日常聊天一样把它当成一次真正的 Agent 会话来处理——理解上下文、调用工具、必要时持续多轮——而不是简单的问答 bot。这意味着 gateway 不能是一个无状态的消息转发器,它需要:

1. 把各个 IM 平台的连接方式(长轮询、WebSocket、Socket Mode、IMAP……)统一成同一种"收消息/发消息"接口;
2. 把同一个聊天窗口的多轮消息路由到同一个会话,不同聊天窗口(私聊 vs 群聊、不同用户)不能共享同一个 Agent 记忆;
3. 复用已经存在的、经过打磨的 Agent 运行时,而不是为 gateway 场景重新写一套引擎驱动逻辑;
4. 作为一个长驻进程,要有干净的启动/停止/重启/状态查询能力。

这四点分别对应下面四个核心机制。

## 核心机制详解

### 第一层:ChannelManager 把平台差异收敛成统一配置

`OhmoGatewayService.__init__` 里,`ChannelManager` 的构造只需要一份 `Config` 和一个共享的 `MessageBus`:

```python
# ohmo/gateway/service.py:54-62(节选)
self._bus = MessageBus()
self._manager = ChannelManager(build_channel_manager_config(self._config), self._bus)
self._runtime_pool = OhmoSessionRuntimePool(
    cwd=self._cwd,
    workspace=self._workspace,
    provider_profile=self._config.provider_profile,
    create_feishu_group=self.create_group_for_user,
    publish_group_welcome=self.publish_group_welcome,
)
```

`build_channel_manager_config()`(`ohmo/gateway/config.py`)把 `ohmo` 自己的 `GatewayConfig`(存在 `~/.ohmo/gateway.json` 里的 provider profile、enabled channels、per-channel 配置)投影成 `openharness.config.schema.Config` 认识的形状:

```python
# ohmo/gateway/config.py:29-41
def build_channel_manager_config(config: GatewayConfig) -> Config:
    """Project gateway settings into the channel compatibility models."""
    root = Config()
    root.channels.send_progress = config.send_progress
    root.channels.send_tool_hints = config.send_tool_hints
    for name in config.enabled_channels:
        if not hasattr(root.channels, name):
            continue
        channel_config = getattr(root.channels, name).model_copy(
            update={"enabled": True, **config.channel_configs.get(name, {})}
        )
        setattr(root.channels, name, channel_config)
    return root
```

第三篇会详细讲 `ChannelManager` 内部怎么按需实例化十种平台的 `BaseChannel` 子类,这里只需要知道它对上层暴露的是"一个进程内所有已启用平台的收发接口",下游完全不需要关心具体是哪个平台。

### 第二层:会话路由——`session_key_for_message`

一个 IM 平台的原始消息(`InboundMessage`)要先被换算成一个 session key,才能决定它该落到哪个 Agent 会话里。这个换算逻辑集中在一个纯函数里:

```python
# ohmo/gateway/router.py:8-31
def session_key_for_message(message: InboundMessage) -> str:
    """Route sessions by chat, isolating shared chats by thread/sender.

    Private chats keep the original ``channel:chat_id`` key so existing long
    ohmo sessions remain resumable. Group/shared chats include sender identity
    to avoid multiple people sharing one agent memory.
    """
    if message.session_key_override:
        return message.session_key_override
    sender_id = str(message.sender_id).strip() or "anonymous"
    chat_type = str(message.metadata.get("chat_type") or "").strip().lower()
    is_shared_chat = chat_type in {"group", "chat", "supergroup", "channel", "room"}
    thread_id = (
        message.metadata.get("thread_id")
        or message.metadata.get("thread_ts")
        or message.metadata.get("message_thread_id")
    )
    if thread_id:
        if is_shared_chat:
            return f"{message.channel}:{message.chat_id}:{thread_id}:{sender_id}"
        return f"{message.channel}:{message.chat_id}:{thread_id}"
    if is_shared_chat:
        return f"{message.channel}:{message.chat_id}:{sender_id}"
    return f"{message.channel}:{message.chat_id}"
```

规则很直白但每一条都有明确动机:私聊(非共享聊天、无 thread)沿用最简单的 `channel:chat_id`,保证老会话可以一直续下去;一旦是群聊/频道这类共享聊天,`sender_id` 必须编码进 key,否则群里所有人会共享同一个 Agent 记忆——A 问的问题、A 的上下文,B 发消息时也能看到,这在个人助理场景里是不可接受的;带 thread 的场景(Slack thread、Telegram 话题群)再把 `thread_id` 也编码进去,让同一个话题内的多轮对话保持连续,不同话题互不干扰。

### 第三层:OhmoGatewayBridge——消费消息、调度任务、处理控制命令

`OhmoGatewayBridge.run()` 是一个从 `MessageBus` 里不断取 `InboundMessage` 的循环,每条消息被路由到 session key 后,用一个独立的 `asyncio.Task` 去处理:

```python
# ohmo/gateway/bridge.py:120-135(节选)
await self._interrupt_session(
    session_key,
    reason="replaced by a newer user message",
    notify=OutboundMessage(
        channel=message.channel,
        chat_id=message.chat_id,
        content="⏹️ 已停止上一条正在处理的任务，继续看你的最新消息。",
        metadata={"_progress": True, "_session_key": session_key},
    ),
)
task = asyncio.create_task(
    self._process_message(message, session_key),
    name=f"ohmo-session:{session_key}",
)
self._session_tasks[session_key] = task
task.add_done_callback(lambda finished, key=session_key: self._cleanup_task(key, finished))
```

这里有一个很实用的设计:同一个 session key 上如果还有一个任务没跑完,新消息到达时会先 `_interrupt_session()` 取消旧任务并发一条"已停止上一条任务"的提示,再启动新任务——这解决的是个人助理场景里一个很常见的体验问题:用户发了一条消息,Agent 还在处理(可能在跑一个耗时工具调用),用户又追加了一条更重要的消息,这时候不应该排队等旧任务跑完,而应该立刻响应最新意图。`/stop`、`/restart` 这两个内置控制命令也是在这一层被拦截处理的,不会被当成普通消息转发给 Agent。

### 第四层:OhmoSessionRuntimePool——真正驱动 Agent 会话

`_process_message` 最终调用 `self._runtime_pool.stream_message(message, session_key)`,这就进入了 `ohmo/gateway/runtime.py` 里的 `OhmoSessionRuntimePool`。它的 `get_bundle()` 按 session key 缓存 `RuntimeBundle`,首次访问时构建一个新的:

```python
# ohmo/gateway/runtime.py:189-213(节选)
bundle = await build_runtime(
    cwd=session_cwd,
    model=self._model,
    max_turns=self._max_turns,
    system_prompt=build_ohmo_system_prompt(session_cwd, workspace=self._workspace, extra_prompt=None),
    active_profile=self._provider_profile,
    session_backend=self._session_backend,
    enforce_max_turns=self._max_turns is not None,
    restore_messages=_sanitize_snapshot_messages(snapshot.get("messages") if snapshot else None),
    restore_tool_metadata=_sanitize_group_command_metadata(snapshot.get("tool_metadata") if snapshot else None),
    extra_skill_dirs=(str(get_skills_dir(self._workspace)),),
    extra_plugin_roots=(str(get_plugins_dir(self._workspace)),),
    memory_backend=create_memory_command_backend(self._workspace),
    include_project_memory=False,
    autodream_context={
        "memory_dir": str(get_memory_dir(self._workspace)),
        "session_dir": str(get_sessions_dir(self._workspace)),
        "app_label": "ohmo personal memory",
        "runner_module": "ohmo",
    },
)
if snapshot and snapshot.get("session_id"):
    bundle.session_id = str(snapshot["session_id"])
self._register_gateway_tools(bundle)
await start_runtime(bundle)
```

对照第一篇里 `ohmo/runtime.py` 的 `run_ohmo_print_mode()`,可以发现两处 `build_runtime()` 调用的参数几乎是同一套模板:`system_prompt` 都来自 `build_ohmo_system_prompt()`,`memory_backend` 都来自 `create_memory_command_backend()`,`extra_skill_dirs`/`extra_plugin_roots` 都指向 `~/.ohmo` 下的 `skills`/`plugins`,`autodream_context` 的 `app_label` 都是 `"ohmo personal memory"`。唯一实质性的区别是:gateway 场景下的 `restore_messages`/`restore_tool_metadata` 来自按 `session_key` 哈希存取的历史快照(`self._session_backend.load_latest_for_session_key(session_key)`),而不是按 cwd 存取——这正好对应上一篇 `router.py` 里那套 session key 规则:每个聊天窗口的会话历史独立存取、独立续接。

`stream_message()` 收到一条消息后,先看它是不是一条已注册的斜杠命令(`bundle.commands.lookup()` / `lookup_skill_slash_command()`),是的话走命令处理分支(`/provider`、`/model` 这类 gateway 专属命令由 `_handle_gateway_scoped_command()` 处理,其余命令复用 core 的命令系统);不是命令的话才真正调用 `bundle.engine.submit_message(user_message)` 驱动一次引擎轮次,把流式事件转换成 `GatewayStreamUpdate` 逐个 `yield` 出去。`bridge.py` 里的 `_process_message()` 消费这些更新,把 `kind="progress"` 的中间态发布成 `OutboundMessage`(带 `_progress` 标记,供 `ChannelManager` 按 `send_progress`/`send_tool_hints` 配置决定要不要真的发到平台),把 `kind="final"` 的最终回复作为这条消息的正式回复发布出去。

### 澄清:gateway/bridge.py 与 openharness.bridge 没有关系

`ohmo/gateway/bridge.py` 这个文件名很容易让人以为它在调用 OpenHarness core 里那套叫 `openharness.bridge` 的机制。实际读一遍两边的 import 就能确认这是两回事:

```python
# ohmo/gateway/bridge.py:10-16(节选,全部 import)
from openharness.channels.bus.events import InboundMessage
from openharness.channels.bus.events import OutboundMessage
from openharness.channels.bus.queue import MessageBus

from ohmo.group_registry import load_managed_group_record
from ohmo.gateway.router import session_key_for_message
from ohmo.gateway.runtime import OhmoSessionRuntimePool
```

`gateway/bridge.py` 只 import 了消息总线(`channels.bus`)和 `ohmo` 自己的路由/运行时模块,完全没有出现 `openharness.bridge` 的踪影。真正的 `openharness.bridge`(`src/openharness/bridge/`)是另一套机制:`BridgeSessionManager`/`spawn_session` 用来在**子进程里拉起一个全新的 CLI 会话**并跟踪它的输出——

```python
# src/openharness/bridge/manager.py:35-45(节选)
async def spawn(self, *, session_id: str, command: str, cwd: str | Path) -> SessionHandle:
    handle = await spawn_session(session_id=session_id, command=command, cwd=cwd)
    self._sessions[session_id] = handle
    self._commands[session_id] = command
    output_dir = get_data_dir() / "bridge"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session_id}.log"
    ...
```

这是"以子进程方式跑一个独立 CLI 命令并采集其输出"的通用能力,与 gateway 的会话路由是完全不同的问题域——gateway 需要的是"在同一个进程内、为每个聊天窗口维护一个长期存活、可以持续对话的 `RuntimeBundle`",而 `openharness.bridge` 服务的是"临时拉起一次性子进程任务"。两者共享 `bridge` 这个词只是命名巧合,gateway 真正复用的可编程接口是上一节讲的 `openharness.ui.runtime.build_runtime()`。第四篇讲 cron 调度时会看到,`openharness.bridge` 的这种"拉起子进程"思路,其实和 cron 任务的执行方式(拉起一个新的 `ohmo --print` 进程)在精神上是相通的,只是走的是完全不同的代码路径。

### 服务生命周期:OhmoGatewayService

`ohmo gateway run/start/stop/restart/status` 这几个 CLI 子命令(第一篇 `ohmo/cli.py` 里的 `gateway_app`)最终都落到 `ohmo/gateway/service.py` 的 `OhmoGatewayService` 上。前台运行的核心是 `run_foreground()`:

```python
# ohmo/gateway/service.py:198-224(节选)
async def run_foreground(self) -> int:
    self.pid_file.write_text(str(os.getpid()), encoding="utf-8")
    self.write_state(running=True)
    bridge_task = asyncio.create_task(self._bridge.run(), name="ohmo-gateway-bridge")
    manager_task = asyncio.create_task(self._manager.start_all(), name="ohmo-gateway-channels")
    restart_notice_task = asyncio.create_task(
        self._publish_pending_restart_notice(),
        name="ohmo-gateway-restart-notice",
    )
    stop_event = asyncio.Event()
    self._stop_event = stop_event
    ...
    async def _state_heartbeat() -> None:
        while not stop_event.is_set():
            self.write_state(running=True)
            await asyncio.sleep(5.0)
```

`bridge_task` 和 `manager_task` 分别驱动上面讲的消息桥接循环和所有 channel 的收发循环;`state_task` 每 5 秒把当前活跃会话数、provider profile、启用的 channel 列表等信息写进 `~/.ohmo/state.json`,供 `ohmo gateway status` 读取——status 命令本身不直接和一个正在跑的 gateway 进程通信,而是读这个文件加上 pid 存活检测。

"重启"的实现值得单独拿出来看,它不是简单地杀掉进程再拉起一个新的:

```python
# ohmo/gateway/service.py:152-166(节选)
def _exec_restart(self) -> None:
    root = str(get_workspace_root(self._workspace))
    argv = [
        sys.executable, "-m", "ohmo", "gateway", "run",
        "--cwd", self._cwd, "--workspace", root,
    ]
    logger.info("ohmo gateway restarting in-place argv=%s", argv)
    os.execv(sys.executable, argv)
```

`request_restart()` 先把一条"我回来了"的提示写进 `~/.ohmo/gateway-restart-notice.json`,等待 0.75 秒让 outbound 分发器把重启前的确认消息发出去,再触发 `stop_event`;`run_foreground()` 的 `finally` 块里做完清理(停 bridge、停所有 channel、写最终状态)之后,如果确实是因为重启请求退出的,就调用 `_exec_restart()`——用 `os.execv` 在**同一个操作系统进程**里原地替换成一个新的 `ohmo gateway run` 进程,而不是 fork 一个子进程再退出。这样 pid 保持不变,`ohmo gateway status` 依赖的 pid 文件不需要处理"旧进程还没退出、新进程已经写了 pid 文件"这类竞态;新进程启动后 `_publish_pending_restart_notice()` 会读到刚才写的 notice 文件,延迟 2 秒后把"gateway 已经重新连上"发回原来的聊天窗口,再删除这个文件。

## 常见问题/易踩坑

- **`gateway/bridge.py` 里的"bridge"不是 `openharness.bridge`。** 这是本文重点澄清的一点,命名巧合但代码路径完全独立,写代码或读代码时不要假设两者有调用关系。
- **群聊里每个人的会话是隔离的,这意味着 Agent 在群里"记不住"整个群的对话脉络。** 这是 `session_key_for_message()` 的直接后果——如果需要群共享上下文的场景(比如第三篇会提到的 `/group` 创建飞书群),需要走专门设计的路径,而不是依赖默认的按发送者隔离规则。
- **gateway 的斜杠命令默认不能被远程触发管理员操作。** `OhmoSessionRuntimePool._remote_admin_allowed()` 要求命令本身声明 `remote_admin_opt_in`,并且 `~/.ohmo/gateway.json` 里显式打开 `allow_remote_admin_commands` 且把命令名加入白名单,否则远程渠道发来的管理员级斜杠命令会被拒绝,只在本地 OpenHarness UI 里可用。

## 小结

一条消息从 IM 平台到 Agent 回复,经过的是 `ChannelManager`(协议收敛)→ `MessageBus`(解耦)→ `OhmoGatewayBridge`(会话路由与打断/控制命令)→ `OhmoSessionRuntimePool`(为每个会话维护一个复用 `build_runtime()` 构建出来的 `RuntimeBundle`)这四层。`gateway/bridge.py` 的名字虽然容易让人联想到 `openharness.bridge`,但两者没有 import 关系——真正把 gateway 与 OpenHarness 引擎连起来的,是与 `ohmo` CLI 共享的同一个可编程运行时接口 `build_runtime()`。`OhmoGatewayService` 用 `os.execv` 原地重启、pid 文件加状态文件实现了一套轻量但完整的服务生命周期管理。下一篇我们深入 `ChannelManager` 背后十种 IM 平台各自的接入实现,看看 `BaseChannel` 这个统一接口是怎么把长轮询、WebSocket、Socket Mode、IMAP 这些完全不同的协议形态收敛到同一套 `start`/`stop`/`send` 方法上的。
