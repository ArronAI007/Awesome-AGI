# MCP 双向集成:作为 Client 与作为 Server

> 大多数 Agent 项目谈到 MCP(Model Context Protocol)时只讲一半:自己是个 MCP client,去接第三方工具服务器。Hermes 把这件事做成了两条独立又对称的路径——`optional-mcps/` 目录收录了 60 多个"Nous 已审核"的第三方 MCP 服务器清单,让 Hermes 作为 client 去挂载 Airtable、Figma、GitLab 这些外部能力;而 `mcp_serve.py` 反过来把 Hermes 自己的消息会话包装成一个 MCP 服务器,让 Claude Code、Cursor 这类外部 MCP host 可以反过来把 Hermes 当工具用。本篇把这两条路径都讲透,重点是它们各自解决了什么具体问题。

## 学习目标

- 理解 `optional-mcps/` 目录下的 `manifest.yaml` 结构,能读懂 `transport`/`auth`/`tools.default_excluded` 这些字段。
- 搞清楚一份第三方 MCP 清单从"仓库里的一个 YAML 文件"到"`config.yaml` 里一条生效的 `mcp_servers.<name>` 配置"要经过哪几步。
- 理解 `mcp_serve.py` 暴露的 10 个工具分别解决什么问题,尤其是它号称"匹配 OpenClaw 的 9-tool MCP 桥接面"这句话背后的含义。
- 理解 `EventBridge` 这个"轮询 SQLite 代替 WebSocket"的设计,以及它为什么要在 `poll_events`/`wait_for_event` 之外还提供一个阻塞版本。
- 能说清楚"既是 MCP client 又是 MCP server"这种双向设计对生态兼容性的意义。

## 作为 MCP Client:`optional-mcps/` 目录

Hermes 仓库里有 66 个 `optional-mcps/<name>/` 子目录,每个目录只放一份 `manifest.yaml`,不放任何可执行代码——这是一份纯声明式的目录清单,而不是一批打包进仓库的 MCP 服务器实现。目录顶部的注释统一说明了"进这个目录 = 已获批准":

```yaml
# optional-mcps/figma/manifest.yaml:1-3
# Nous-approved MCP catalog entry.
# Presence in this directory = approval. Merged via PR review.
manifest_version: 1
```

`hermes_cli/mcp_catalog.py` 的模块文档字符串把这套设计的定位讲得很清楚——它是 `optional-skills/` 那一套模式在 MCP 领域的复刻:

```python
# hermes_cli/mcp_catalog.py:1-20(节选)
"""MCP catalog — curated, Nous-approved MCP servers shipped with the repo.

Mirrors the optional-skills/ pattern: each catalog entry lives under
``optional-mcps/<name>/manifest.yaml`` and ships disabled. Users discover
entries via ``hermes mcp catalog`` or the interactive ``hermes mcp picker``,
and install them with ``hermes mcp install <name>``...

Catalog policy:
- Entries are added only by merging a PR into hermes-agent. Presence in the
  ``optional-mcps/`` directory = Nous approval. No community tier, no trust
  signals beyond "it's in the catalog".
- Manifests pin transport details (commands, args, refs)... MCPs are never
  auto-updated; users explicitly re-run ``hermes mcp install <name>`` to
  pull a new manifest version after a repo update.
- Secrets prompted at install time go to ``~/.hermes/.env``...
"""
```

两个真实清单能看出这套 schema 覆盖的两种典型形态。远程 HTTP + OAuth 型(Figma 官方托管的远程 MCP):

```yaml
# optional-mcps/figma/manifest.yaml(节选)
name: figma
description: >-
  Official Figma remote MCP — design context, Code Connect, and
  write-to-canvas via https://mcp.figma.com/mcp (OAuth).
transport:
  type: http
  url: https://mcp.figma.com/mcp
auth:
  type: oauth
suggest:
  keywords: [figma, mockup, wireframe]
  hosts: [figma.com]
```

Figma 清单里有一段特别值得留意的注释:Figma 的 OAuth 动态客户端注册接口只白名单了 `"Claude Code"`/`"Codex"` 这两个精确的 `client_name` 字符串,`"Hermes Agent"` 会被 403——Hermes 的 MCP OAuth 层因此专门为这个 host 把 `client_name` 默认伪装成 `"Claude Code"`(见 `tools/mcp_oauth.apply_oauth_provider_defaults`),这是一个"为了兼容第三方服务商的白名单策略而做的具体适配"的真实例子,不是纯理论设计。

GitLab 清单展示了另一种常见需求——工具级别的选择性排除:

```yaml
# optional-mcps/gitlab/manifest.yaml(节选)
transport:
  type: http
  url: https://gitlab.com/api/v4/mcp
auth:
  type: oauth
tools:
  default_excluded:
    - get_mcp_server_version
    - list_duo_sessions
```

### 从清单到生效配置:`hermes mcp install` 做了什么

`install_entry()`(`hermes_cli/mcp_catalog.py:887`)的文档字符串把整条安装流水线的六个步骤写得很清楚:如果 `install.type == git` 就先克隆仓库跑 bootstrap 命令;`api_key` 型认证提示用户填env 变量存进 `~/.hermes/.env`;`oauth` 型只写一个 `auth: oauth` 标记,真正的浏览器授权流程留到首次连接时才触发;然后把清单翻译成 `mcp_servers.<name>` 配置块存进 `config.yaml`;探测服务器实际暴露的工具列表,用一个 curses 交互式勾选界面做工具粒度的启停;最后打印 `post_install` 里的使用说明。

翻译这一步由 `_build_server_config()` 完成,它把 `manifest.yaml` 里声明式的 `transport`/`auth` 字段映射成运行时配置期望的形状:

```python
# hermes_cli/mcp_catalog.py:584-605(节选)
def _build_server_config(entry: CatalogEntry, install_dir) -> dict:
    cfg: dict = {}
    t = entry.transport
    if t.type == "stdio":
        cfg["command"] = _expand_install_dir(t.command or "", install_dir)
        if t.args:
            cfg["args"] = [_expand_install_dir(a, install_dir) for a in t.args]
        if t.env:
            cfg["env"] = dict(t.env)
    elif t.type == "http":
        cfg["url"] = t.url
        if entry.auth.type == "oauth":
            cfg["auth"] = "oauth"
        elif entry.auth.type == "api_key":
            cfg["headers"] = _bearer_auth_headers(entry.name)
    return cfg
```

这条链路把"这个 MCP 服务器该怎么连"这件事从"一份人写的、带审批流程的清单"变成了"一段可执行的运行时配置",中间没有任何代码需要 Hermes 团队为每个第三方服务单独维护——每加入一个新的第三方集成,增量成本只是审一份 PR、写一份 YAML,而不是写一段专门的适配代码。

## 作为 MCP Server:`mcp_serve.py`

反过来的路径解决的是完全不同的问题:Hermes 本身管理着大量跨平台(Telegram、Discord、Slack、WhatsApp、Signal、Matrix……)的消息会话和记忆,如果这些数据只能被 Hermes 自己的 Agent 循环访问,外部工具(比如你日常开着的 Claude Code、Cursor)就没法"顺便看一眼 Hermes 那边有没有新消息、要不要回一条"。`mcp_serve.py` 的解法是把 Hermes 会话状态整体包装成一个标准 MCP 服务器,任何 MCP client 都能接上:

```python
# mcp_serve.py:1-27(节选)
"""
Hermes MCP Server — expose messaging conversations as MCP tools.

Starts a stdio MCP server that lets any MCP client (Claude Code, Cursor, Codex,
etc.) list conversations, read message history, send messages, poll for live
events, and manage approval requests across all connected platforms.

Matches OpenClaw's 9-tool MCP channel bridge surface:
  conversations_list, conversation_get, messages_read, attachments_fetch,
  events_poll, events_wait, messages_send, permissions_list_open,
  permissions_respond

Plus: channels_list (Hermes-specific extra)

Usage:
    hermes mcp serve
"""
```

"匹配 OpenClaw 的 9-tool 桥接面"这句话点出了这个设计的定位:OpenClaw 是社区里已经跑出来的一套"消息网关 MCP 桥接"事实标准,Hermes 没有自造一套形状不同的工具集,而是直接对齐这份已有的 9 个工具签名,额外只加了一个 `channels_list`——这样任何已经为 OpenClaw 写过 MCP 客户端集成的下游工具,理论上只需要改一下 server 启动命令就能接上 Hermes。

`create_mcp_server()`(`mcp_serve.py:623`)用 `@mcp.tool()` 装饰器逐个注册这 10 个工具,每个工具的职责划分得很清楚:

- `conversations_list` / `conversation_get`——按平台、关键词过滤会话列表,返回 `session_key`(后续工具的主键)。
- `messages_read` / `attachments_fetch`——读取一段会话的消息历史与非文本附件。
- `messages_send` / `channels_list`——反向能力:往某个 `platform:chat_id` 目标发消息,`channels_list` 返回可用的发送目标。
- `events_poll` / `events_wait`——分别对应"轮询一次"和"长轮询阻塞等待",事件类型覆盖 `message`/`approval_requested`/`approval_resolved`。
- `permissions_list_open` / `permissions_respond`——把 Hermes 内部的危险命令审批请求暴露出去,外部 MCP client 可以代替人工完成 `allow-once`/`allow-always`/`deny` 决策。

### `EventBridge`:轮询 SQLite 而不是维护一条 WebSocket

`events_poll`/`events_wait` 背后的实现是一个后台线程 `EventBridge`,它的类文档字符串直接讲清楚了这个组件在做什么、以及它跟 OpenClaw 对应组件的关系:

```python
# mcp_serve.py:335-341(节选)
class EventBridge:
    """Background poller that watches SessionDB for new messages and
    maintains an in-memory event queue with waiter support.

    This is the Hermes equivalent of OpenClaw's WebSocket gateway bridge.
    Instead of WebSocket events, we poll the SQLite database for changes.
    """
```

`poll_events()` 是无阻塞版本,按 `after_cursor` 游标从内存队列里切一段返回;`wait_for_event()` 则是给 stdio 型 MCP client 准备的长轮询版本。它没有用忙等循环去空耗 CPU,而是每轮检查完队列后,在剩余时间和一个固定 `POLL_INTERVAL` 之间取较小值,挂在一个 `threading.Event` 上等待:

```python
# mcp_serve.py:404-427(节选)
def wait_for_event(self, after_cursor=0, session_key=None, timeout_ms=30000):
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        with self._lock:
            for e in self._queue:
                if e.cursor > after_cursor and (
                    not session_key or e.session_key == session_key
                ):
                    return {"cursor": e.cursor, "type": e.type, ...}
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        self._new_event.clear()
        self._new_event.wait(timeout=min(remaining, POLL_INTERVAL))
```

新事件到达时,后台轮询线程会 `set()` 这个 `Event` 把等待者提前唤醒,而不是让它必须睡满一整个 `POLL_INTERVAL` 才有机会看到新数据——`EventBridge.stop()` 里同样调用了 `self._new_event.set()` 来"唤醒所有等待者"以便干净关闭。这两个工具并存的原因很直接:MCP 的 stdio 传输本身不像 WebSocket 那样天然支持服务端主动推送,`events_wait` 用"客户端发起一次会阻塞的请求"这种方式,在 stdio 上模拟出了接近实时的事件通知效果,而 `events_poll` 留给不想阻塞连接的客户端做纯轮询。`_establish_baseline()` 还专门处理了一个容易被忽略的边界情况——启动时给已有的历史消息拍一次快照,避免把启动前的旧消息当成"新事件"重放一遍。

## 小结与思考题

`optional-mcps/` 和 `mcp_serve.py` 表面上是两套完全独立的代码(前者是一份 YAML 清单 + 一段安装期翻译逻辑,后者是一个常驻的 stdio 服务器进程),但它们共同回答的是同一个问题的两个方向:**Hermes 的能力边界不应该等于它自己的代码边界**。作为 client,它靠一份可审计、可增量扩展的清单目录把外部世界的能力(Figma、GitLab、Airtable……)接进自己的工具面,而不需要为每一个第三方服务单独写维护成本高的适配代码;作为 server,它把自己攒了大量跨平台消息和记忆的会话状态,以业界通用的 MCP 协议重新暴露出去,让 Claude Code、Cursor 这些原本跟 Hermes 毫无关系的工具也能顺手用上这些数据。这种"既消费、又提供"的双向设计,是 Hermes 融入更大的 Agent 生态而不是自建孤岛的关键一步——一个只会当 client 的系统,能力上限被"别人愿意给它接口"框死;一个只会当 server 的系统,则永远只能等别人来找它,自己够不到外部世界已经成熟的工具生态。两者都做,Hermes 才能同时是"生态的消费者"和"生态的一个节点"。

思考题:
1. `optional-mcps/` 的目录审批模型("进仓库 = Nous 已批准,没有社区层级")和第 09 章要讲的插件安全扫描(`tools/plugin_guard.py`)相比,谁的信任假设更强、谁的运营成本更高?如果要新增"社区贡献但未经官方审核"的第三方 MCP 层级,你会怎么在现有目录结构上叠加一层区分?
2. `wait_for_event()` 用一个共享的 `threading.Event` 唤醒所有等待者,而不是给每个等待者一份独立的条件变量。如果同时有多个 MCP client 分别用不同的 `session_key` 过滤条件挂起等待,一次无关会话的新事件到来时,所有等待者都会被唤醒一次、重新扫一遍队列再决定要不要继续等——这在等待者数量很多时会带来什么开销?你会如何改造成"按 `session_key` 分组唤醒"来减少无谓的重复扫描?
