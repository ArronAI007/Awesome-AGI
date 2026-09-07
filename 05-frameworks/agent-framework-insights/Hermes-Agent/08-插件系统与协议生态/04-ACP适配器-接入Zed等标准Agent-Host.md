# ACP 适配器:接入 Zed 等标准 Agent Host

> MCP 解决的是"Agent 怎么调用外部工具",ACP(Agent Client Protocol)解决的是反方向的问题:一个编辑器/IDE(Agent Host,比如 Zed、VS Code、JetBrains)怎么用同一套协议驱动任意一个遵循该协议的 Agent 后端,而不用为每一个 Agent 单独写一套集成代码。Hermes 的 `acp_adapter/` 用官方 `acp` Python 包实现了这层协议,把 Hermes 包装成一个可以被这些编辑器直接当作聊天/编码 Agent 使用的标准 ACP 服务器。本篇讲清楚这套适配器的文件结构、关键类型,以及权限审批这类"editor-in-the-loop"能力是怎么落地的。

## 学习目标

- 理解 ACP 协议要解决的问题:让不同的 Agent Host 用统一协议驱动任意标准 Agent,而不是每个 Host 各自维护一套厂商专属集成。
- 认识 `acp_adapter/` 的文件分工:`entry.py`/`server.py`/`session.py`/`events.py`/`permissions.py`/`edit_approval.py`/`tools.py`/`auth.py`/`provenance.py`。
- 读懂 `initialize()` 返回的 `AgentCapabilities`/`PromptCapabilities`/`SessionCapabilities` 具体声明了哪些能力,以及这份声明背后的取舍。
- 理解 `permissions.py`(危险命令审批)和 `edit_approval.py`(文件编辑审批)两个模块各自的职责边界和 fail-closed 语义。
- 理解 `_meta.hermes` 这种"标准协议里挂一个私有命名空间"的扩展手法,以及它为什么不会破坏标准 ACP 客户端的兼容性。

## ACP 是什么、解决什么问题

ACP(Agent Client Protocol)是由 Zed 编辑器团队发起的一套标准协议,目标是让任意 Agent Host(编辑器、IDE)能用同一套 JSON-RPC 语义驱动任意实现了这套协议的 Agent 后端。没有 ACP 之前,一个编辑器如果想同时支持 N 个 Agent 后端,理论上要写 N 套专属集成;有了 ACP,编辑器只需要实现一次"ACP client"逻辑,任何声称支持 ACP 的 Agent 都能直接接上。Hermes 官方文档把这个使用场景说得很直接:

```text
# website/docs/integrations/index.md:79
- **[IDE Integration (ACP)](/user-guide/features/acp)** — Use Hermes Agent
  inside ACP-compatible editors such as VS Code, Zed, and JetBrains. Hermes
  runs as an ACP server, rendering chat messages, tool activity, file diffs,
  and terminal commands inside your editor.
```

Hermes 这一侧没有自己发明协议细节,而是直接依赖官方 `acp` Python 包提供的类型和运行时,`acp_adapter/server.py` 顶部就导入了这套包定义的标准 schema:

```python
# acp_adapter/server.py:16-40(节选)
import acp
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AgentThoughtChunk,
    AuthenticateResponse,
    AvailableCommand,
    ...
    McpServerHttp,
    McpServerSse,
    McpServerStdio,
    ...
    PromptResponse,
    ...
    SessionCapabilities,
    ...
)
```

值得一提的是,ACP 的能力声明里还包含 `McpServerHttp`/`McpServerSse`/`McpServerStdio` 这类类型——ACP 协议本身预留了"Agent Host 可以在会话里再声明一批 MCP 服务器给 Agent 用"的能力,这与上一篇讲的 MCP 双向集成形成了第三层协议叠加:编辑器通过 ACP 驱动 Hermes,同时还能通过同一个协议通道告诉 Hermes"这个会话里多挂几个 MCP 服务器"。

## `acp_adapter/` 的文件结构

`website/docs/developer-guide/acp-internals.md` 给出了一份精简的组件地图,和实际目录结构完全对应:

```text
# website/docs/developer-guide/acp-internals.md(节选)
- acp_adapter/entry.py       — CLI 入口,配置 stdout/stderr 分离
- acp_adapter/server.py      — HermesACPAgent,实现 ACP agent 协议
- acp_adapter/session.py     — SessionManager,跟踪存活的 ACP 会话
- acp_adapter/events.py      — 把 AIAgent 回调转换成 ACP session_update 事件
- acp_adapter/permissions.py — 危险命令审批桥接
- acp_adapter/tools.py       — 把 Hermes 工具映射成 ACP 工具类型/内容
- acp_adapter/auth.py        — 复用 Hermes 现有的 provider/凭据解析器
```

再加上仓库里实际存在、文档地图未逐一列出的 `edit_approval.py`(文件编辑审批)和 `provenance.py`(会话世系元数据),`acp_adapter/` 一共由 11 个文件组成(`__init__.py`/`__main__.py` 两个样板文件之外,9 个承载实际逻辑),`server.py` 一家独大——2640 行,是这套适配器的主体实现;其余每个文件都严格对应一个单一职责,彼此边界清晰。

启动流程本身也体现了一条贯穿整个课程的原则——**stdout 只能是协议帧**:

```text
# website/docs/developer-guide/acp-internals.md「Boot flow」节选
hermes acp / hermes-acp / python -m acp_adapter
  -> acp_adapter.entry.main()
  -> load ~/.hermes/.env
  -> configure stderr logging
  -> construct HermesACPAgent
  -> acp.run_agent(agent, use_unstable_protocol=True)

Stdout is reserved for ACP JSON-RPC transport. Human-readable logs go to stderr.
```

## `initialize()`:`AgentCapabilities` 声明了什么

`HermesACPAgent.initialize()`(`acp_adapter/server.py:1295`)是整套协议握手的起点,它的返回值是 Agent 向 Host 声明"我能做什么"的唯一入口:

```python
# acp_adapter/server.py:1313-1327(节选)
return InitializeResponse(
    protocol_version=acp.PROTOCOL_VERSION,
    agent_info=Implementation(name="hermes-agent", version=HERMES_VERSION),
    agent_capabilities=AgentCapabilities(
        load_session=True,
        prompt_capabilities=PromptCapabilities(image=True),
        session_capabilities=SessionCapabilities(
            fork=SessionForkCapabilities(),
            list=SessionListCapabilities(),
            resume=SessionResumeCapabilities(),
        ),
    ),
    auth_methods=auth_methods,
)
```

`load_session=True`、`prompt_capabilities.image=True`、以及 `session_capabilities` 里同时声明 `fork`/`list`/`resume` 三种会话能力——这是一份相当"敢声明"的能力清单:代表编辑器可以要求 Hermes 加载既有会话、发图片型 prompt、把一个会话 fork 出一条独立分支、列出所有历史会话、以及从中断处恢复。`authenticate()` 方法还专门做了一层校验,只接受和 `initialize()` 里广播的方法一致的 `method_id`,注释里写明了这层校验的动机:

```python
# acp_adapter/server.py:1329-1335(节选)
# Only accept authenticate() calls whose method_id matches the
# provider we advertised in initialize(). Without this check,
# authenticate() would acknowledge any method_id as long as the
# server has provider credentials configured — harmless under
# Hermes' threat model (ACP is stdio-only, local-trust), but poor
# API hygiene and confusing if ACP ever grows multi-method auth.
```

`prompt()` 方法(`acp_adapter/server.py:1784`)是每一次用户输入进入 Agent 循环的入口,返回值统一是 `PromptResponse`,`stop_reason` 字段(`end_turn`/`refusal`/`cancelled` 等)是编辑器判断这一轮对话该怎么收尾的唯一依据——这正是这份适配器里被导入、被高频使用的核心类型。

## Session 生命周期:`SessionManager` 与 `EventBridge`

`acp_adapter/session.py` 里的 `SessionManager` 为每个 ACP 会话维护 `session_id`/`agent`/`cwd`/`model`/`history`/`cancel_event` 六项状态,并提供 `create`/`get`/`remove`/`fork`/`list`/`cleanup` 等线程安全操作。会话生命周期的核心流程写在文档里:

```text
# website/docs/developer-guide/acp-internals.md「Session lifecycle」节选
new_session(cwd)
  -> create SessionState
  -> create AIAgent(platform="acp", enabled_toolsets=["hermes-acp"])
  -> bind task_id/session_id to cwd override

prompt(..., session_id)
  -> extract text from ACP content blocks
  -> reset cancel event
  -> install callbacks + approval bridge
  -> run AIAgent in ThreadPoolExecutor
  -> update session history
  -> emit final agent message chunk
```

值得注意的是"`run AIAgent in ThreadPoolExecutor`"这一步——Hermes 的 `AIAgent` 核心是同步实现,而 ACP 的 I/O 是异步事件循环,`acp_adapter/events.py` 里的事件桥接靠 `asyncio.run_coroutine_threadsafe(...)` 把工作线程里同步回调(`tool_progress_callback`/`step_callback`)转发回主事件循环,包成 ACP 的 `session_update` 通知。`fork_session()` 则通过深拷贝消息历史创建一个独立的新会话——这与第 06 章讲的会话压缩机制有交集:`provenance.py` 模块专门从既有的压缩链路(`sessions` 表的 `parent_session_id`/`end_reason`)派生出会话世系信息,让编辑器能看清"当前这个 ACP 会话背后,Hermes 内部因为上下文压缩已经悄悄轮换过几次内部会话头"。

## 权限与编辑审批:`permissions.py` / `edit_approval.py`

这两个模块是 ACP 适配器里最能体现"编辑器在场"这个场景特殊性的部分——普通 CLI/gateway 场景下,危险命令审批和文件编辑没有"编辑器 UI 可以弹窗"这个额外通道,而 ACP 场景下恰恰有。

**`permissions.py`** 把 Hermes 既有的危险终端命令审批请求,转译成 ACP 标准的权限选项:

```python
# acp_adapter/permissions.py:1-27(节选)
"""ACP permission bridging for Hermes dangerous-command approvals."""

# Maps ACP permission option ids to Hermes approval result strings.
_OPTION_ID_TO_HERMES = {
    "allow_once": "once",
    "allow_session": "session",
    "allow_always": "always",
    "deny": "deny",
    "deny_always": "deny",
}
```

`_permission_option_supports_kind()` 甚至做了一次运行时探测,判断当前安装的 ACP SDK 版本是否接受某个 `PermissionOption.kind` 取值——这是协议演进期常见的防御性写法:不同版本的 `acp` 包 schema 可能有细微差异,与其硬编码假设,不如探测一次再决定要不要用这个字段。文档里的映射表和这份代码完全对应,并且强调了失败语义:

```text
# website/docs/developer-guide/acp-internals.md「Permission bridge」节选
- allow_once -> Hermes `once`
- allow_always -> Hermes `always`
- reject options -> Hermes `deny`

Timeouts and bridge failures deny by default.
```

"超时和桥接失败都默认拒绝"——这与第二篇 RFC 精讲里反复出现的"guard 类 hook 必须 fail-closed"原则完全一致:审批请求送到编辑器却没等到回应,不能被解释成"默认放行"。

**`edit_approval.py`** 解决的是另一件事:在 ACP 会话里,自定义的文件编辑工具在真正落盘之前,可以先把改动内容展示给编辑器、等待人工批准。它的模块文档字符串说明了这个能力的作用域边界:

```python
# acp_adapter/edit_approval.py:1-6
"""Pre-execution ACP edit approval helpers.

This module is intentionally isolated from the generic tool registry. ACP
binds an edit approval requester in a ContextVar for the duration of one ACP
agent run; CLI, gateway, and other sessions leave it unset and therefore
bypass this guard.
"""
```

`EditProposal` 是一个不可变 dataclass(`tool_name`/`path`/`old_text`/`new_text`/`arguments`),`EditApprovalRequester = Callable[[EditProposal], bool]` 用一个 `ContextVar` 挂载——这意味着"文件编辑需要先过编辑器审批"这条规则只在 ACP 会话的执行上下文里生效,CLI 或消息网关跑同一个 agent 完全不受影响,不需要在通用工具注册表里侵入式地加一层"是不是 ACP 会话"的判断。文档同样记录了这个"临时安装、用后即恢复"的清理约定:

```text
# website/docs/developer-guide/acp-internals.md「Approval callback restoration」节选
ACP temporarily installs an approval callback on the terminal tool during
prompt execution, then restores the previous callback afterward. This avoids
leaving ACP session-specific approval handlers installed globally forever.
```

## 用 `_meta.hermes` 挂载私有扩展,不破坏标准客户端

`provenance.py` 展示了一种值得记住的协议扩展手法:Hermes 想给 ACP 会话附加一份"内部会话世系"信息(压缩前后是哪个内部 session id、链路根节点是谁),但这不是 ACP 标准协议定义的字段。做法不是去改标准 schema,而是把这份信息塞进标准协议本身预留的 `_meta` 扩展位,用自己的命名空间隔离:

```python
# acp_adapter/provenance.py:1-11(节选)
"""Derive ACP session-provenance metadata from the existing compression chain.

This is an additive Hermes extension surfaced under ACP ``_meta.hermes`` so
existing ACP clients ignore it. It carries no new persisted state: everything
is derived on demand from the ``sessions`` table (``parent_session_id`` /
``end_reason``), which already models compression-continuation chains.
"""
```

任何不认识 `_meta.hermes` 这个字段的标准 ACP 客户端(比如一个只实现了协议基线的通用工具)会照常忽略这段数据,完全不受影响;只有专门为 Hermes 做过适配的客户端才会去读它——这是"协议扩展不能破坏协议基线互操作性"这条原则的一个具体、可复制的实现范式。

## 与 DeepSeek-Harness ACP 实现的简单对比

DeepSeek-Harness 的 `packages/acp` 走的是一条刻意"收窄"的路线:它把自己定位为"automation-only",`initialize()` 声明的能力集是业界最保守的一档——不支持图片、音频、嵌入式上下文,交互式能力(编辑器导航、transcript 回放、commands、elicitation)全部关闭,面向的是父 Agent、子 Agent provider 这类程序化客户端,不面向人在编辑器里点击交互。Hermes 的 `acp_adapter` 走的是相反方向:`prompt_capabilities.image=True`,`session_capabilities` 同时声明 `fork`/`list`/`resume`,加上专门为"编辑器审批 UI 在场"这个场景写的 `permissions.py`/`edit_approval.py` 两个模块——这是一套明确面向真实编辑器人机交互场景(Zed/VS Code/JetBrains)的实现,能力声明尽量"敢用",审批语义则用 fail-closed 兜底,两者组合起来才是"人在回路里"这个场景该有的样子。这组对照也再次印证了 ACP 作为一份协议本身的中立性:同一份协议规范之下,一个实现可以选择做"给自动化程序用的最小服务端",另一个可以选择做"给人类编辑器用户用的全功能服务端"——协议不替具体实现做这个产品决策。

## 小结与思考题

ACP 让 Hermes 不必被绑定在自己的 CLI/TUI/Web 界面里——只要编辑器实现了标准 ACP client,Hermes 就能作为一个标准 Agent 后端被驱动,`acp_adapter/` 里 9 个职责单一的文件分别覆盖了协议握手、会话生命周期、事件桥接、危险命令审批、文件编辑审批、工具内容渲染、认证复用和会话世系元数据这些关注点。`initialize()` 里"敢声明"的能力集、`permissions.py`/`edit_approval.py` 里"超时和失败一律拒绝"的审批语义、以及 `provenance.py` 里"新增能力挂在 `_meta` 私有命名空间、不碰标准字段"的扩展手法,三者共同构成了一套既能被通用 ACP 客户端安全使用、又能给深度适配的客户端(比如未来的 Zed 插件)提供 Hermes 专属增值信息的协议实现。

思考题:
1. 如果一个 ACP Host(比如 Zed)本身不理解 `_meta.hermes.sessionProvenance` 这个私有扩展字段,Hermes 团队要怎么验证"新增一个 `_meta` 扩展字段绝对不会导致标准客户端解析失败"这件事?你会在测试里怎么覆盖这种"未知字段必须被安全忽略"的场景?
2. `edit_approval.py` 用 `ContextVar` 把审批钩子限定在"当前 ACP 会话执行期间"生效,CLI/gateway 场景完全不受影响。对照第 08 章第一篇讲过的 `PluginContext.register_hook()`(全局注册、对所有会话生效),说说"用 ContextVar 做执行期作用域限定"和"用插件注册表做全局能力声明"这两种扩展点设计,分别适合什么场景?
