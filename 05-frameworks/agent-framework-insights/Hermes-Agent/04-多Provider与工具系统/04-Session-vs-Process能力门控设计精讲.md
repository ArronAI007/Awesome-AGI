# Session vs Process 能力门控设计精讲

> hermes-agent 的 `AGENTS.md` 里有一条专门起了小标题的规则:"Surface capability is a property of
> the SESSION, never of the process env"——一句听起来像口号的话,背后是一个真实踩过的坑:桌面应用
> 的聊天面板可以驱动本地进程、SSH 远程进程、纯 URL+token 连接、或是 Hermes Cloud 上完全独立的一台
> 机器,只有前两种拓扑会让后端进程带着 `HERMES_DESKTOP=1` 环境变量启动。如果"这个工具能不能用"这个
> 判断挂在进程环境变量上,后三种拓扑里这条判断会**悄无声息地失败**——工具从 schema 里消失了,但同
> 一个后端进程还在通过系统提示词告诉模型"你正在 Hermes 桌面应用里聊天"。本篇完整还原这条规则的问题
> 背景、正确实现,以及它如何贯穿本章前三篇讲过的 Provider 发现、工具注册、Toolset 分发。

## 学习目标

- 理解"进程"和"会话"在 hermes-agent 里是两个完全不同粒度的概念:一个长驻网关进程可以同时服务多个
  来源不同的会话。
- 完整还原"用进程环境变量判断能力可用性"这个反模式的具体故障场景——为什么它是"静默失败"而不是报错。
- 读懂 `AGENTS.md` 里这条规则给出的"正确做法"三要素:toolset 作为唯一入口、`check_fn` 该回答什么
  问题、`HERMES_DESKTOP=1` 真正代表什么身份。
- 读懂 `tui_gateway/server.py` 里 `_gui_surface_toolsets()`/`_session_source()` 这两个函数,理解能力
  判断是怎样真正挂到会话对象而不是 `os.environ` 上的。
- 理解这条规则和 `tools/registry.py` 的 `check_fn` TTL 缓存范围划分之间的关系。
- 能说出这条规则在本章 Provider Profile 发现、工具自注册、Toolset 分发,以及后续插件系统、消息网关
  章节里分别是怎样被呼应的。

## 问题背景:一个进程,多个互不相干的会话来源

`AGENTS.md` 先把物理拓扑讲清楚:

```text
# AGENTS.md:213-227(节选)
### Surface capability is a property of the SESSION, never of the process env

A tool that only works because of *who is on the other end of the connection* —
the desktop app's panes, the in-app browser, message reactions, Projects — must
resolve its availability from the **session's own source**, not from an env var
on the backend process.

The client and the backend are separate machines on separate clocks. The
desktop app can be driving a backend Electron spawned locally, one over SSH,
one behind a plain URL + token, or Hermes Cloud. Only the first two are spawned
by us and carry `HERMES_DESKTOP=1`. Every env-keyed GUI gate is therefore a
silent no-op on the other half of the topologies, and the failure is invisible:
the tool is stripped from the schema before the model ever sees it, on the same
backend whose platform hint is telling the model it's *"chatting inside the
Hermes desktop app."*
```

拆开来看,桌面应用作为一个**客户端**,实际上可以驱动四种完全不同的后端拓扑:

1. **本地 Electron 子进程**——桌面 App 直接 `spawn` 出来,这个进程确实是"被我们自己启动的",带
   `HERMES_DESKTOP=1`。
2. **SSH 远程进程**——桌面 App 通过 SSH 连到一台远程机器上启动同样的后端,这个进程也是"被我们自己
   启动的",同样带 `HERMES_DESKTOP=1`。
3. **纯 URL + token 连接**——后端进程可能是用户自己用别的方式启动的一个长驻服务,桌面 App 只是拿着
   一个 URL 和一个 token 去连它。这个进程从来没有被桌面 App "启动"过,自然不会带
   `HERMES_DESKTOP=1`。
4. **Hermes Cloud**——后端跑在云上完全独立的机器,同样不会带这个环境变量。

四种拓扑里,只有前两种会让后端进程环境里出现 `HERMES_DESKTOP=1`;后两种里,**同一个桌面客户端**、
**同一套 GUI 面板**,连接的却是一个完全没有这个环境变量的后端进程。如果某个工具"是否该出现在
schema 里"这件事是靠后端进程读 `os.environ.get("HERMES_DESKTOP")` 来判断的,那么在后两种拓扑下,这
个判断永远是 `False`——工具被无声地从 schema 里剔除,而这一切发生在模型看到任何东西之前。更糟的
是,同一个后端进程的系统提示词生成逻辑,往往是按"客户端类型"(而不是按这个环境变量)告诉模型"你
正在 Hermes 桌面应用里对话",于是模型被明确告知"这里有一个可以打开的浏览器预览面板",却完全没有
对应的工具可调——这是一个自相矛盾、且没有任何报错信息可循的故障模式,比一次显式抛异常危险得多。

更本质的问题在于:一个长驻的网关进程(比如 `tui_gateway/server.py` 这样的后端服务)本来就设计成**
同时服务多个会话**——同一个进程可能同时挂着一个本地桌面会话、一个 SSH 转发会话、一个通过 URL 连接
的远程会话。进程级的环境变量对这个进程里的所有会话都是同一个值,而"这个会话是不是桌面来源"却是一
个**逐会话**才能回答的问题。用一个进程粒度的信号去回答一个会话粒度的问题,天然就是错的粒度。

## 正确做法的三要素

`AGENTS.md` 给出的修复模式分三条:

```text
# AGENTS.md:229-245(节选)
The pattern that works:

- **The toolset is the surface gate.** Keep the tools off `_HERMES_CORE_TOOLS`
  (nobody else should pay their schema) and put them in a named toolset —
  `desktop_ui`, `project`. The GUI gateway's `_load_enabled_toolsets(platform)`
  folds that toolset in when the session's platform says GUI. One resolver,
  every topology.
- **`check_fn` answers reachability or user opt-in, not surface.** "Is the
  renderer bridge wired?", "did the user enable reactions?" — fine. "Was I
  spawned by Electron?" — not fine. `check_fn` results are also TTL-cached
  process-wide (`tools/registry.py`), so a per-session answer does not belong
  there at all: one process serves many sessions.
- **Ask which identity you actually mean.** `HERMES_DESKTOP=1` legitimately
  marks *"this backend process was spawned by the app"* — it gates the cron
  ticker and web-dist handling correctly. It does NOT mean "a GUI is watching",
  and the embedded terminal pane (`hermes --tui` against that same backend) is
  the standing counterexample.
```

逐条展开:

1. **Toolset 是唯一的能力门**。桌面专属工具(`read_terminal`、`open_preview` 等)从一开始就不放进
   `_HERMES_CORE_TOOLS` 这份所有平台共享的清单——上一篇讲过,这样"没人需要为不属于自己的能力多背
   一份 schema"。它们被单独收纳进一个具名 toolset(`desktop_ui`、`project`),真正决定"这次会话要
   不要折叠进这个 toolset"的,是网关层一个函数(`_load_enabled_toolsets(platform)`),而这个函数
   的输入是**会话的 platform 字段**,不是进程环境。这样无论后端进程处于四种拓扑里的哪一种,只要
   会话本身正确声明了自己的来源,同一套解析逻辑都能得出正确结果。
2. **`check_fn` 该回答"可达性/用户是否开启",不该回答"我是谁的会话"**。`check_fn` 是
   `tools/registry.py` 里"这个工具现在要不要出现"的探针,但它的结果是**进程级别 TTL 缓存**的(下
   一节详细展开)——如果拿它去回答一个逐会话才有意义的问题("这次连接是不是来自桌面客户端"),第
   一个会话探测出的结果会被缓存下来,污染同一进程里后续所有会话的判断。`check_fn` 只适合回答"这
   个能力依赖的外部条件本身是否满足"这种进程级别就能回答清楚的问题——比如"渲染器桥接是否已经建
   立"“用户是否在设置里打开了消息回应功能”。
3. **分清"是谁启动了这个进程"和"现在是谁在看"两种完全不同的身份**。`HERMES_DESKTOP=1` 是一个合
   法且有用的信号,但它回答的是第一种身份——它正确地用来控制 cron 心跳、web 分发这类"进程本身该不
   该做某件事"的逻辑。它**不**回答第二种身份"现在是不是有一个 GUI 在看"。反例就在同一个后端上:
   `hermes --tui` 连到桌面应用启动的同一个后端时,进程确实带着 `HERMES_DESKTOP=1`,但这次连接是一
   个终端会话,不是 GUI——如果按这个环境变量判断,会把桌面专属工具错误地暴露给一个根本没有渲染器
   的终端会话。

## 正确实现:能力判断挂在会话对象上

`toolsets.py` 里 `desktop_ui` toolset 定义处的注释已经预告了这条规则(上一篇引用过),真正落地判
断逻辑的是 `tui_gateway/server.py` 里的两个函数。第一个是"这次会话的 platform 到底是什么":

```python
# tui_gateway/server.py:3768-3773
def _session_source(session: dict | None) -> str:
    if session:
        source = str(session.get("source") or "").strip()
        if source:
            return source
    return _resolve_session_platform()
```

注意判断顺序:**先看会话对象自己携带的 `source` 字段**,只有当会话完全没有声明来源时,才退化成
`_resolve_session_platform()`——一个基于本地环境变量的启发式兜底,只用来覆盖"用户直接在本机敲
`hermes --tui`"这种压根没有显式声明来源的最简单场景:

```python
# tui_gateway/server.py:5106-5129(节选)
def _resolve_session_platform() -> str:
    """Resolve the platform tag for a tui_gateway-routed session.
    ...
    Resolution:
      * ``HERMES_DESKTOP=1`` and ``HERMES_DESKTOP_TERMINAL`` unset → "desktop"
        (the chat-panel backend — a graphical React surface, not a terminal).
      * ``HERMES_DESKTOP_TERMINAL=1`` → "tui"
        (``hermes --tui`` running in the desktop's embedded terminal pane;
        it IS a TUI, just embedded.)
      * neither set → "tui"
        (standalone ``hermes --tui``.)
    """
    if is_truthy_value(os.environ.get("HERMES_DESKTOP")) and not is_truthy_value(
        os.environ.get("HERMES_DESKTOP_TERMINAL")
    ):
        return "desktop"
    return "tui"
```

这里的关键在于:`_resolve_session_platform()` 确实读了 `os.environ`,但它只在**本地直接启动**这
一种场景下被当作真源使用——一旦会话本身携带了显式的 `source`(比如通过 URL/token 连接时,客户端
在建立会话的请求里就声明了自己是"desktop"或别的来源),`_session_source()` 会直接采信会话自带的
值,完全跳过环境变量读取。也就是说,环境变量只是"没有更好信息时的默认猜测",从来不是"能力判断的
唯一依据"——这正是"能力属性挂在会话对象上,而不是进程环境"这句规则的字面落地。

真正执行能力门控的是第二个函数:

```python
# tui_gateway/server.py:5860-5878
def _gui_surface_toolsets(platform: str) -> set[str]:
    """Toolsets that exist because of the CLIENT on the other end, not the host.

    Both entries are deliberately off ``_HERMES_CORE_TOOLS`` — every other
    platform would carry their schema for nothing — so this resolver is the one
    gate that exposes them.

    ``platform`` is the SESSION's source (``session.create``'s ``source``
    field), never a process env var. The desktop app is a client: it can be
    driving a local, SSH, URL, or cloud backend, and only the local/SSH spawn
    paths run with ``HERMES_DESKTOP=1``. Keying GUI capability off that env var
    silently stripped every pane/browser tool from URL and cloud gateways while
    the same backend told the model it was "chatting inside the Hermes desktop
    app". See the surface-capability rule in AGENTS.md.
    """
    surfaces = {"project"}
    if platform == "desktop":
        surfaces.add("desktop_ui")
    return surfaces
```

`_gui_surface_toolsets()` 的入参 `platform` 是一个纯字符串,函数体内**没有任何一处读取
`os.environ`**——它只做字符串比较。这个函数被 `_load_enabled_toolsets(platform)` 调用,而
`_load_enabled_toolsets` 的调用方传入的 `platform` 参数,最终一路溯源到 `_session_source(session)`
的返回值:

```python
# tui_gateway/server.py:8807-8817(节选)
enabled_toolsets=_load_enabled_toolsets(_resolve_agent_platform(platform_override)),
...
platform=_resolve_agent_platform(platform_override),
```

而 `platform_override` 在真正的调用点上是 `_session_source(session)`(`tui_gateway/server.py:6452`
、`8481` 等处),也就是这一整条链路从头到尾都在传递"这个会话自己声明的来源",从未在能力判断这一步
掉回去读进程环境变量。`_load_enabled_toolsets()` 里折叠进 `_gui_surface_toolsets()` 的那一行注释,
把这条设计动机复述了一遍:

```python
# tui_gateway/server.py:6018-6024(节选)
# The client-surface toolsets are off _HERMES_CORE_TOOLS (every other
# platform would carry their schema for nothing), so the platform
# recovery above — which keys off hermes-cli's tool universe — can't
# surface them. This resolver runs ONLY in the desktop/TUI gateway, so
# folding them in here is the gate that exposes them on exactly the
# surface that can answer them.
return sorted(enabled | _gui_surface_toolsets(session_platform))
```

## 一个配套的运行时防线:工具 handler 里的回调判空

即便 toolset 层面已经正确地按会话来源折叠了 `desktop_ui`,单个工具的 handler 仍然保留了一层运行时
兜底判断——`tools/read_preview_tool.py` 是个很直观的例子:

```python
# tools/read_preview_tool.py:1-13, 21-28(节选)
"""Read the in-app browser / preview pane in the Hermes desktop GUI.

The preview's content lives in the desktop renderer (a sandboxed <webview>
for URL tabs), so this tool round-trips through the gateway's blocking-prompt
bridge ... Lives in the ``desktop_ui`` toolset, which the GUI gateway enables
only for desktop-sourced sessions.
"""

def read_preview_tool(start=None, count=None, callback=None) -> str:
    """Return the active preview tab's contents (+ metadata) as a JSON string."""
    if callback is None:
        return tool_error("read_preview is only available in the Hermes desktop app.")
    ...
```

这里的 `callback` 是渲染器桥接注入进来的实际回调函数——如果某个边界情况下工具还是出现在了 schema
里但渲染器桥接没有正确建立(比如 `check_fn` 判断的"渲染器桥接是否已经建立"这类进程级可达性条件恰
好为假),`callback is None` 这一层判空给出一个可读的错误信息,而不是让请求崩溃或悬挂。这正是
`AGENTS.md` 里"`check_fn` 可以回答'渲染器桥接是否已建立'"这条许可的实际体现——它是一层锦上添花的
可达性兜底,不是能力门控本身该依赖的机制。

## 和 `check_fn` TTL 缓存范围的关系

`AGENTS.md` 提到"`check_fn` results are also TTL-cached process-wide",这句话背后的实现在
`tools/registry.py`:

```python
# tools/registry.py:305-345(节选)
def check_fn_cache_scope() -> Optional[str]:
    """Return the active profile key when availability is profile-scoped.

    Browser-controller availability is request-bound and can change on every
    attach/detach. A fully bound browser-control request therefore bypasses both
    this check cache and model_tools' outer definition cache; the same sentinel
    is consumed by both layers. This prevents one Browser session's live tools
    from leaking into any unrelated session.

    Single-profile processes intentionally keep the historical process-wide
    cache. A multiplex gateway installs a Hermes-home override for every
    profile turn, so the canonical profile key is the stable isolation
    boundary across repeated turns for that profile.
    """
```

`_check_fn_cached()` 用 `(fn, scope)` 作为缓存 key,`scope` 默认是 `None`(单 profile 进程沿用历史
的"进程级全局缓存"),只有在多路复用(multiplex)网关模式下才细化到按 profile 隔离,而**从未细化到
按单个会话隔离**。这条缓存策略本身就说明了为什么"是不是桌面来源"这种问题绝不能塞进 `check_fn`:
`check_fn` 的返回值天生就是拿来在多个会话之间共享复用的,如果第一个会话探测出"我是桌面来源"这个结
果,后续所有共享同一个 `(fn, scope)` 缓存 key 的会话都会直接复用这个判断——哪怕它们其实是完全不同
来源的会话。反过来,像"渲染器桥接是否建立"这种确实是进程级/profile 级的可达性问题,用 TTL 缓存换
取重复调用的性能是完全合理的——这也是为什么这条规则反复强调"要先想清楚你问的到底是哪种身份"。

## 这条规则在本章及后续章节里的呼应

把这条规则放回本章的其它内容里看,会发现它其实是同一个原则在四个不同层面的重复应用:

- **Provider Profile 发现**(第 1 篇):`register_provider()` 的 last-writer-wins 覆盖规则和
  entry point 的"先注册、最先被覆盖"顺序,同样是在解决"谁的声明应该在什么粒度上生效"的问题——只
  是这里粒度是"进程内的 provider 名字空间",而不是"会话的能力可见性"。
  两者共享的直觉是:凡是需要跨多个使用者(多个 provider 插件、多个会话)共存的状态,都必须先想清
  楚"隔离边界应该画在哪一层",再决定用什么数据结构去实现它。
- **工具自注册与 Schema**(第 2 篇):`dynamic_schema_overrides` 明确要求"no network at schema-build
  time",本质上也是在划一条"进程级可以安全探测的信息"和"逐次调用才该判断的信息"之间的边界——和
  本篇"`check_fn` 只该回答进程级可达性问题"是同一类约束的不同表现形式。
- **Toolset 组合与分发**(第 3 篇):`desktop_ui`/`project` 两个 toolset 本身就是这条规则的直接产
  物——它们存在的理由,以及为什么故意不在 `_HERMES_CORE_TOOLS` 里,注释原文直接引用了本篇讲的这
  条设计规则。
- **第 8 章插件系统**:插件的能力声明、gating 逻辑一旦涉及到"这个能力是不是该对当前用户/会话可
  见",都要面对同样的"进程 vs 会话"选择——本章建立的判断框架(toolset 是门、`check_fn` 答可达性、
  分清身份)可以直接搬过去用。
- **第 9 章消息网关(多平台 session 隔离)**:消息网关本身就是"一个进程同时服务多个平台、多个用户
  会话"的典型场景,`_session_source()`/`_gui_surface_toolsets()` 这套机制正是网关层"会话隔离"故事
  的一个具体切片——第 9 章会在网关的 session 生命周期管理里更完整地展开这个话题。

## 小结与思考题

"Surface capability is a property of the SESSION, never of the process env"这条规则的价值在于它
指出了一类特别隐蔽的故障:用进程级信号回答会话级问题,不会报错,只会在部分拓扑下**悄悄地**让能力
消失,而系统提示词却仍然宣称这个能力存在。hermes-agent 的修复方式是三层配合:能力门永远是具名
toolset(而不是散落在各处的环境变量判断),`check_fn` 只负责回答进程级/profile 级的可达性和用户
opt-in,真正的"这次连接是谁"这个身份判断,通过 `session["source"]` 字段一路透传到
`_gui_surface_toolsets()` 这样的纯函数里,从源头上避免了对 `os.environ` 的依赖。这条原则不是
hermes-agent 独有的,而是任何"一个长驻进程服务多个隔离上下文"的系统都会面对的通用问题——本章前三
篇讲的 Provider 发现、工具注册、Toolset 分发,乃至第 8、9 章的插件与网关,都是同一个"进程 vs 会
话"边界问题在不同子系统里的具体投影。

思考题:

1. `_resolve_session_platform()` 在会话完全没有显式声明 `source` 时,退化成读 `HERMES_DESKTOP`/
   `HERMES_DESKTOP_TERMINAL` 两个环境变量。这是不是又变回了"用进程环境判断能力"的反模式?结合它
   的实际使用场景(用户直接在本机敲 `hermes --tui`,压根没有一个显式声明来源的"会话创建请求"),
   说说为什么这里的环境变量读取是安全的,而 `AGENTS.md` 要禁止的是另一种用法。
2. 如果要新增一个"仅在 Hermes Cloud 托管环境下才该出现"的工具,你会把判断逻辑放在
   `check_fn`、专属 toolset、还是 `session["source"]` 里?说说你的选择依据,以及这个场景和
   `desktop_ui` 场景在"身份维度"上的异同。
3. `check_fn_cache_scope()` 的注释提到,浏览器控制器(Browser Control)相关的可用性判断会**绕过**
   TTL 缓存(返回 `CHECK_FN_CACHE_BYPASS`),因为它是"request-bound"的。这和本篇的核心论点(能力
   判断不该挂在进程级缓存上)是否矛盾?为什么浏览器控制器选择"绕过缓存"而不是像 `desktop_ui` 那样
   直接改用 toolset 门控?
