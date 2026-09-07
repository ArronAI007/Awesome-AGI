# Toolsets 组合与分发

> 一个工具被注册进 `tools/registry.py` 之后,并不会自动出现在模型看到的 schema 里——它还要先被划进
> 某个具名的 toolset,再由入口层(CLI、消息平台网关、桌面 GUI、批处理研究场景)决定这次对话要启用
> 哪些 toolset。`toolsets.py` 就是这层"工具分组与组合"的定义文件:它维护一份 `_HERMES_CORE_TOOLS`
> 共享清单、一个可以互相 `includes` 的 `TOOLSETS` 字典,以及把 toolset 名字递归展开成具体工具列表
> 的 `resolve_toolset()`。本篇拆开这套组合逻辑,并简单带过 `toolset_distributions.py` 在批处理研究
> 场景里的用法。

## 学习目标

- 理解 `_HERMES_CORE_TOOLS` 作为"CLI + 所有消息平台共享清单"的定位,以及它为什么特意不包含桌面
  GUI 专属工具。
- 读懂 `TOOLSETS` 字典的组合语法——`tools` 直接列出的工具和 `includes` 引用的其他 toolset 如何合并。
- 读懂 `resolve_toolset()` 的递归展开逻辑:环检测、diamond 依赖去重、`"all"`/`"*"` 全集别名、插件
  平台的自动 toolset 生成。
- 能说清 CLI(`hermes-cli`)、消息平台(`hermes-telegram` 等)、桌面 GUI(`desktop_ui`)、编码场景
  (`coding` posture)这几种典型场景分别用什么 toolset 组合。
- 知道 `toolset_distributions.py` 在 `batch_runner.py` 里怎样用概率抽样而不是固定清单选工具集。

## `_HERMES_CORE_TOOLS`:一份共享清单,而不是每个平台各写一份

`toolsets.py` 顶部定义了一份所有"完整功能"场景共享的核心工具清单:

```python
# toolsets.py:29-88(节选)
# Shared tool list for CLI and all messaging platform toolsets.
# Edit this once to update all platforms simultaneously.
_HERMES_CORE_TOOLS = [
    # Web
    "web_search", "web_extract",
    # Terminal + process management
    "terminal", "process",
    # NOTE: the desktop GUI affordances (read_terminal, open_preview, …) are
    # deliberately NOT here, for the same reason as the `project` tools below:
    # they only work where a GUI renderer can answer them. They live in the
    # `desktop_ui` toolset and are enabled solely by the GUI gateway for a
    # session whose SOURCE is the desktop app ... — never keyed on a process
    # env var, which is blind to a desktop client talking to a remote/cloud
    # backend.
    # File manipulation
    "read_file", "write_file", "patch", "search_files",
    # Vision + image generation
    "vision_analyze", "image_generate",
    # Skills
    "skills_list", "skill_view", "skill_manage",
    # Browser automation
    "browser_navigate", "browser_snapshot", "browser_click", ...
    # Text-to-speech
    "text_to_speech",
    # Planning & memory
    "todo", "memory",
    # Session history search
    "session_search",
    # Clarifying questions
    "clarify",
    # Code execution + delegation
    "execute_code", "delegate_task",
    # Cronjob management
    "cronjob",
    # Home Assistant smart home control (gated on HASS_TOKEN via check_fn)
    "ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service",
    # Kanban multi-agent coordination — gated via check_fn in tools/kanban_tools.py
    "kanban_show", "kanban_list", "kanban_complete", "kanban_block", ...
    # Computer use (macOS, gated on cua-driver being installed via check_fn)
    "computer_use",
]
```

这份清单被十几个 `hermes-*` toolset(`hermes-cli`、`hermes-telegram`、`hermes-discord`、
`hermes-whatsapp`、`hermes-slack`……)直接引用:

```python
# toolsets.py:472-514(节选)
"hermes-cli": {
    "description": "Full interactive CLI toolset - all default tools plus cronjob management",
    "tools": _HERMES_CORE_TOOLS,
    "includes": []
},
"hermes-telegram": {
    "description": "Telegram bot toolset - full access for personal use (terminal has safety checks)",
    "tools": _HERMES_CORE_TOOLS,
    "includes": []
},
```

个别平台在 `_HERMES_CORE_TOOLS` 基础上再叠加自己独有的工具,比如 Discord 多了服务器管理工具:

```python
# toolsets.py:495-502
"hermes-discord": {
    "description": "Discord bot toolset - full access (terminal has safety checks via dangerous command approval)",
    "tools": _HERMES_CORE_TOOLS + [
        "discord",
        "discord_admin",
    ],
    "includes": []
},
```

这个设计的价值很直接:核心工具集只需要改一处,十几个平台的 toolset 全部同步生效,不需要在十几份
定义里各改一遍——注释里"Edit this once to update all platforms simultaneously"就是这个意图的直接
表达。

`_HERMES_CORE_TOOLS` 里两处 `NOTE` 注释同样重要:桌面 GUI 专属的 `read_terminal`/`open_preview` 等
工具,以及桌面 Projects 专属的 `project_list`/`project_create`/`project_switch`,都**故意**不放进
这份共享清单——它们只在能力真正可用的场景(桌面会话)才应该出现在 schema 里,这条规则和它背后的
"session vs 进程环境变量"设计原则,是下一篇的核心内容。

## `TOOLSETS`:直接工具 + 组合引用

`TOOLSETS` 字典里的每一项是 `{"description": ..., "tools": [...], "includes": [...]}` 这样的形状,
`tools` 是这个 toolset 自己直接持有的工具,`includes` 是要合并进来的其他 toolset 名字。最基础的几
个原子 toolset:

```python
# toolsets.py:105-115(节选)
"web": {
    "description": "Web research and content extraction tools",
    "tools": ["web_search", "web_extract"],
    "includes": []
},
"search": {
    "description": "Web search only (no content extraction/scraping)",
    "tools": ["web_search"],
    "includes": []
},
```

组合示例——`debugging` toolset 直接列出终端工具,再 `includes` 两个原子 toolset:

```python
# toolsets.py:364-368
"debugging": {
    "description": "Debugging and troubleshooting toolkit",
    "tools": ["terminal", "process"],
    "includes": ["web", "file"]  # For searching error messages and solutions, and file operations
},
```

`desktop_ui` toolset 专门收纳"只因为对面是 GUI 渲染器才存在"的工具——注意它的注释直接引用了下一篇
要讲的会话来源判定规则:

```python
# toolsets.py:243-262
# Affordances that only exist because a GUI renderer is on the other end of
# the connection: read/close the embedded terminal pane, open/read/close the
# in-app browser, focus a pane, tapback a message.
#
# Enabled by the GUI gateway for a session whose SOURCE is the desktop app
# (tui_gateway/server.py::_load_enabled_toolsets), NOT by a process env var.
"desktop_ui": {
    "description": "Desktop GUI affordances — in-app terminal/browser panes, pane focus, reactions (GUI sessions only)",
    "tools": [
        "read_terminal", "close_terminal",
        "desktop_preview", "drive_preview", "annotate_preview",
        "read_window_below",
        "focus_pane", "react_to_message",
        "setup_mcp", "tour", "tip",
    ],
    "includes": []
},
```

而 `coding` 是一个"posture(姿态)"toolset——针对代码工作区场景收窄核心清单,去掉消息平台/TTS/
Spotify/家庭自动化/看板等对编码场景无意义的工具:

```python
# toolsets.py:385-407(节选)
"coding": {
    "description": "Coding-focused toolset: files, terminal, search, web docs, skills, todo, delegate, vision, browser",
    "tools": [
        "web_search", "web_extract", "terminal", "process",
        "read_file", "write_file", "patch", "search_files",
        "vision_analyze", "skills_list", "skill_view", "skill_manage",
        "browser_navigate", "browser_snapshot", ...,
        "todo", "memory", "session_search", "clarify",
        "execute_code", "delegate_task",
    ],
    "includes": [],
    # Posture toolset: selected per-session by agent/coding_context.py,
    # never auto-recovered into per-platform tool config (see the
    # non-configurable-toolset recovery loop in hermes_cli/tools_config.py).
    "posture": True,
},
```

`"posture": True` 这个标记本身也是一处值得注意的设计:它告诉 `hermes_cli/tools_config.py` 里那套
"配置漂移自动纠正"逻辑,`coding` 不是用户在配置文件里手动选的 toolset,而是 `agent/coding_context.py`
每次对话按"当前是不是在代码工作区"动态选出来的——不应该被误当成用户的持久化偏好去"纠正"回配置文件
里。

## `resolve_toolset()`:递归展开、环检测、全集别名

拿到一个 toolset 名字后,真正产出"最终工具名列表"的是 `resolve_toolset()`。它的核心递归逻辑很简
洁:收集自己的 `tools`,再对每个 `includes` 项递归调用自己,把结果并起来:

```python
# toolsets.py:826-834
# Collect direct tools
tools = set(toolset.get("tools", []))

# Recursively resolve included toolsets, sharing the visited set across
# sibling includes so diamond dependencies are only resolved once and
# cycle warnings don't fire multiple times for the same cycle.
for included_name in toolset.get("includes", []):
    included_tools = resolve_toolset(included_name, visited, include_registry=include_registry)
    tools.update(included_tools)
```

几个容易被忽略但很实用的细节:

- **环检测靠一个共享的 `visited` 集合**,而不是显式的图算法:`if name in visited: return []`——
  第二次访问同一个 toolset 名字时直接返回空集合。这既处理了真正的循环引用(A includes B,B 又
  includes A),也顺带处理了"diamond 依赖"(A 和 B 都 includes C,C 只应该被展开一次)——两种情况
  都安全地返回空集合,不会重复添加或抛异常。
- **`"all"`/`"*"` 是两个特殊别名**,代表"遍历所有已知 toolset 名字,取并集":

```python
# toolsets.py:780-788
if name in {"all", "*"}:
    all_tools: Set[str] = set()
    for toolset_name in get_toolset_names():
        resolved = resolve_toolset(toolset_name, visited.copy(), include_registry=include_registry)
        all_tools.update(resolved)
    return sorted(all_tools)
```

- **插件平台的 toolset 是自动生成的**:如果调用方传入 `hermes-<plugin_name>` 这样的名字但
  `TOOLSETS` 里没有对应定义,`resolve_toolset()` 会去检查 `platform_registry` 里是否真的注册了这
  个平台插件,如果是,就返回"核心工具 + 这个平台在注册表里额外注册的工具"——这样第三方消息平台插
  件不需要手写一份完整的 toolset 定义,只要平台名和 toolset 里 `toolset=` 参数对上就自动获得一份
  合理的默认工具集。
- **顶层调用会走一层带 registry 世代号的内存缓存**(`_resolve_toolset_memo`),缓存 key 是
  `(name, include_registry, registry_id, generation)`——只要注册表没有发生任何 `register`/
  `deregister`/别名注册,同一个 toolset 名字的展开结果可以直接复用,避免每次对话轮次都重新递归。

## 典型场景对照

| 场景 | 使用的 toolset(s) | 特点 |
|---|---|---|
| 交互式 CLI(`hermes` 命令) | `hermes-cli`(= `_HERMES_CORE_TOOLS`) | 完整核心工具集 |
| Telegram / Discord / Slack 等消息平台 | `hermes-<platform>`(= `_HERMES_CORE_TOOLS` [+ 平台专属工具]) | 与 CLI 共享同一份核心清单,只叠加平台特有工具 |
| Webhook 入口 | `hermes-webhook`(= `_HERMES_WEBHOOK_SAFE_TOOLS`) | 显式收窄成 `web_search`/`web_extract`/`vision_analyze`/`clarify` 四个只读向工具,防止不可信的第三方内容(比如公开 PR 标题)通过提示注入触发本地文件/系统命令执行 |
| 桌面 GUI 会话 | 常规 toolset(如 `hermes-cli` 或 `coding`) **+** `desktop_ui`(+`project`) | GUI 专属工具由网关按会话来源折叠进来,不在任何平台的静态清单里 |
| 代码工作区(CLI/TUI/桌面/ACP 编辑器集成) | `coding` posture(自动选择) | 去掉消息/TTS/Spotify/家庭自动化等对编码无意义的工具 |
| 批处理研究/数据生成 | `toolset_distributions.py` 里的具名分布(见下一节) | 不是固定清单,而是按概率抽样组合出的工具集 |

`_HERMES_WEBHOOK_SAFE_TOOLS` 的注释把这条安全边界讲得很清楚:

```python
# toolsets.py:90-98
# Webhook events may originate from untrusted third-party content (for example,
# public PR titles/comments). Keep the default webhook toolset intentionally
# constrained to avoid local file/system execution by prompt injection.
_HERMES_WEBHOOK_SAFE_TOOLS = [
    "web_search", "web_extract", "vision_analyze", "clarify",
]
```

## `toolset_distributions.py`:批处理研究场景的概率分发

`batch_runner.py` 跑数据生成/评测任务时,往往不希望每条样本都用同一套固定工具集(那样生成出来的
训练轨迹会缺乏多样性),而是希望"这次任务有 90% 概率带 web 工具、70% 概率带 browser 工具……"这种
概率化的组合。`toolset_distributions.py` 就是为这个场景单独定义的一层:

```python
# toolset_distributions.py:44-63(节选)
DISTRIBUTIONS = {
    "image_gen": {
        "description": "Heavy focus on image generation with vision and web support",
        "toolsets": {
            "image_gen": 90, "vision": 90, "web": 55, "terminal": 45,
        }
    },
    "research": {
        "description": "Web research with vision analysis and reasoning",
        "toolsets": {
            "web": 90, "browser": 70, "vision": 50, "terminal": 10,
        }
    },
    ...
}
```

`sample_toolsets_from_distribution()` 对分布里的每个 toolset **独立投骰子**(而不是从若干套预设组
合里选一套),命中的 toolset 才会被纳入这次任务的工具集,并且兜底"一个都没抽中时至少保留概率最高
的那个":

```python
# toolset_distributions.py:241-282(节选)
def sample_toolsets_from_distribution(distribution_name: str) -> List[str]:
    dist = get_distribution(distribution_name)
    selected_toolsets = []
    for toolset_name, probability in dist["toolsets"].items():
        if not validate_toolset(toolset_name):
            continue
        if random.random() * 100 < probability:
            selected_toolsets.append(toolset_name)
    if not selected_toolsets and dist["toolsets"]:
        highest_prob_toolset = max(dist["toolsets"].items(), key=lambda x: x[1])[0]
        if validate_toolset(highest_prob_toolset):
            selected_toolsets.append(highest_prob_toolset)
    return selected_toolsets
```

`batch_runner.py` 用这份采样结果作为每条样本的 `enabled_toolsets`,再交给 `resolve_toolset()`(或
`resolve_multiple_toolsets()`)展开成具体工具名列表——本质上是在 toolset 这一层组合原语之上,又叠
加了一层"按场景配置抽样概率"的策略层。这部分和第 11 章测试评估/研究工具会再深入,这里只需要记住
`toolset_distributions.py` 消费的是和交互式场景完全一样的 `TOOLSETS`/`resolve_toolset()` 基础设施,
只是选择工具集的方式从"静态指定"换成了"概率抽样"。

## 小结与思考题

`toolsets.py` 用一份共享核心清单(`_HERMES_CORE_TOOLS`)加一个支持组合(`includes`)的字典
(`TOOLSETS`)解决了"十几个消息平台 + CLI + 若干专用场景,如何避免每处都重复维护工具列表"的问题;
`resolve_toolset()` 的递归展开处理了环、diamond 依赖、全集别名、插件平台自动生成这几类边界情况。
不同入口层——CLI、消息平台、Webhook、桌面 GUI、编码 posture、批处理研究——通过选择不同的 toolset
名字(或概率分布)来表达"这次对话应该看到哪些能力",而不需要在各自的代码里重新判断每个工具是否该
出现。`toolset_distributions.py` 是这套组合原语在批处理场景下的一层策略延伸,后面测试评估一章还会
展开。

思考题:

1. `_HERMES_WEBHOOK_SAFE_TOOLS` 没有用 `includes` 引用 `web`/`vision` 两个原子 toolset,而是直接
   平铺写出四个工具名。结合它"故意收紧、防止提示注入"的定位,说说如果改成 `"includes": ["web",
   "vision"]` 会有什么潜在风险(提示:`web`/`vision` toolset 未来会不会被静默加入新工具)?
2. `resolve_toolset()` 的环检测对"真正的循环引用"和"diamond 依赖"给出了完全相同的处理结果(都返
   回空集合)。这种"不区分错误和正常情况"的设计,对调试一个真正写错了的循环 `includes` 配置会带来
   什么不便?你会如何在不破坏 diamond 依赖场景的前提下,给真正的环增加一条告警?
3. `coding` toolset 标了 `"posture": True` 且"never auto-recovered into per-platform tool
   config"。如果没有这个标记,`hermes_cli/tools_config.py` 的配置纠错逻辑可能会把 `coding` 误当
   成什么样的用户配置并做出什么样的"纠正"?
