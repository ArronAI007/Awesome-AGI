# PluginContext 与四种发现源

> Hermes 的插件系统装在一个文件里——`hermes_cli/plugins.py`,7000 多行——但它要解决的问题并不小:插件可能来自仓库自带的目录、用户主目录、项目本地目录,或者一个 pip 包,四条来源要按确定的优先级合并成一份清单;每个插件用一份 `plugin.yaml` 声明身份,用一个 `register(ctx)` 函数把自己接入宿主。`ctx`(`PluginContext`)是这套体系的全部入口——本篇要做的事情,就是把这一个类摊开,看清楚它到底暴露了多少种"扩展面",以及"单一巨型 Context + 目录 manifest"这个架构选择,相比 DeepSeek-Harness 的 Cordis 三元结构,换来了什么、放弃了什么。

## 学习目标

- 记住四种插件发现来源的目录路径、加载顺序和覆盖规则,能独立判断"两个插件同名时谁生效"。
- 会读一份真实的 `plugin.yaml` + `register(ctx)` 组合,知道最小合法插件长什么样。
- 按"扩展面"给 `PluginContext` 的 25 个 `register_*` 方法分类,而不是把它们当成一份无序的方法列表死记。
- 理解 `VALID_HOOKS`、`invoke_hook()`、`hook_callback_timeout` 这三者如何共同构成 Hermes 的 hook 派发机制。
- 能说清楚"文件目录 + manifest + 单一 PluginContext"和"Cordis 的 Context/Service/Plugin 三元结构"这两种能力扩展范式的取舍差异。

## 四种发现来源与覆盖优先级

`hermes_cli/plugins.py` 模块开头的 docstring 就是这套系统的规格说明:

```python
# hermes_cli/plugins.py:1-18
"""
Hermes Plugin System
====================

Discovers, loads, and manages plugins from four sources:

1. **Bundled plugins** – ``<repo>/plugins/<name>/`` (shipped with hermes-agent;
   ``memory/`` and ``context_engine/`` subdirs are excluded — they have their
   own discovery paths)
2. **User plugins**   – ``~/.hermes/plugins/<name>/``
3. **Project plugins** – ``./.hermes/plugins/<name>/`` (opt-in via
   ``HERMES_ENABLE_PROJECT_PLUGINS``)
4. **Pip plugins**     – packages that expose the ``hermes_agent.plugins``
   entry-point group.

Later sources override earlier ones on name collision, so a user or project
plugin with the same name as a bundled plugin replaces it.
"""
```

四条来源对应扫描逻辑里严格按顺序执行的四段代码(`PluginManager._collect_directory_manifests`,`hermes_cli/plugins.py:4540` 附近):

```python
# hermes_cli/plugins.py:4553-4587(节选)
# 1. Bundled plugins (<repo>/plugins/<name>/)...
repo_plugins = get_bundled_plugins_dir()
bundled = self._scan_directory(repo_plugins, source="bundled",
    skip_names={"memory", "context_engine", "platforms", "model-providers"})
manifests.extend(bundled)

# 2. User plugins (~/.hermes/plugins/)
user_dir = get_hermes_home() / "plugins"
manifests.extend(self._scan_directory(user_dir, source="user"))

# 3. Project plugins (./.hermes/plugins/), only when explicitly opted in.
if _env_enabled("HERMES_ENABLE_PROJECT_PLUGINS"):
    project_dir = Path.cwd() / ".hermes" / "plugins"
    manifests.extend(self._scan_directory(project_dir, source="project"))
```

几个细节值得记住:

- **项目插件默认不扫描**。`./.hermes/plugins/` 目录里放了什么都不会自动生效,必须显式设置 `HERMES_ENABLE_PROJECT_PLUGINS=1`——这是一条安全默认值:克隆一个陌生仓库、`cd` 进去启动 Hermes,不会因为仓库自带的 `.hermes/plugins/` 目录而静默执行任意 Python 代码。
- **后来者覆盖先来者**,而这个"先后"顺序是固定写死的代码顺序(bundled → user → project → pip),不是按字母序或加载时间。同名插件(以 manifest 里的 `key` 或 `name` 为准)出现在多条来源里时,列表里靠后的那条赢。
- **pip 包插件走完全不同的通道**——不扫描目录,而是读 Python 的 `importlib.metadata` entry points,分组名是 `hermes_agent.plugins`(`discover_entrypoint_manifests()`,`hermes_cli/plugins.py:470`)。这条路径连插件代码都不需要提前 `import`:它先用 `_classify_entrypoint_value_kind()` 对入口点的目标字符串做"import-free"的源码扫描,判断这是不是一个 memory provider 或 model provider,分流给各自专门的发现系统,只有普通插件才走这里的通用注册流程。

四种来源目录扫描出的都是同一种 `PluginManifest` 对象,后续走同一套加载和 `register(ctx)` 调用逻辑——发现来源的差异只体现在"去哪里找 `plugin.yaml`",不体现在加载之后的行为上。

## 最小合法插件:`plugin.yaml` + `register(ctx)`

一个目录插件必须同时具备 `plugin.yaml` 清单和 `__init__.py` 里的 `register(ctx)` 函数。仓库自带的 `plugins/disk-cleanup/` 是一个体量恰到好处的真实例子。清单:

```yaml
# plugins/disk-cleanup/plugin.yaml
name: disk-cleanup
version: 2.0.0
description: "Auto-track and clean up ephemeral files (test scripts, temp outputs, cron logs) created during Hermes sessions. Runs via plugin hooks — no agent action required."
author: "@LVT382009 (original), NousResearch (plugin port)"
hooks:
  - post_tool_call
  - on_session_end
```

注册函数(`plugins/disk-cleanup/__init__.py:309-315`):

```python
def register(ctx) -> None:
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_command(
        "disk-cleanup",
        handler=_handle_slash,
        description="Track and clean up ephemeral Hermes session files.",
    )
```

三行代码,两个 hook 加一个斜杠命令,就是一个完整可用的插件。清单里的 `hooks:` 字段只是文档性的声明(供 `hermes plugins doctor` 一类工具做人类可读展示),真正生效的注册动作是 `register(ctx)` 里对 `ctx.register_hook()` 的调用——清单和代码是两份独立的真相来源,清单写错了不会导致 hook 失效,但会让 `hermes plugins list` 之类的展示命令显示不准确的信息。

清单还支持一份 v2 schema(`_parse_manifest_v2_fields()`,`hermes_cli/plugins.py:746`),核心字段包括:

- `manifest_version` / `api_version`:前者标记清单自身的 schema 版本,后者是宿主用来做兼容性门禁的插件 API 世代号(下一篇会展开这一点如何对应 RFC 里"host-enforced compat gate"这条结论)。
- `requires_plugins`:`[{id, version_range?}]` 形式声明插件间依赖,`resolve_plugin_load_order()`(`hermes_cli/plugins.py:917`)用 `graphlib.TopologicalSorter` 把它转成一份确定性加载顺序——依赖缺失只警告不阻断,循环依赖会被检测出来并退化为字母序。
- `python_dependencies` / `config_schema` / `tags` / `license` / `homepage`:标准元数据,前者仅做校验展示、从不自动 `pip install`。
- 未知字段永远只警告、不拒绝加载——这是贯穿整个清单解析代码的"前向兼容优先"原则。

## `PluginContext`:按扩展面拆解 25 个 `register_*` 方法

`PluginContext` 的类文档字符串只有一句话:"Facade given to plugins so they can register tools and hooks."(`hermes_cli/plugins.py:1458`)。这份"门面"底下挂了 25 个 `register_*` 方法,一次性读完容易觉得杂乱,但按它们各自服务的"扩展面"分组之后,结构其实很清楚。

**工具与命令类**——把插件的行为接入模型可调用的工具面或人可敲的命令面:

- `register_tool(name, toolset, schema, handler, ...)`——把一个工具挂进全局工具注册表。`override=True` 可以整体替换一个内置工具(比如自定义 `browser_navigate`),但这条路径被一道显式的操作员 opt-in 挡住:
  ```python
  # hermes_cli/plugins.py:1795-1806(节选)
  """
  ``override=True`` against a built-in tool requires the operator to
  opt in via ``plugins.entries.<plugin_id>.allow_tool_override: true``
  in config.yaml — mirrors the trust gate pattern used for
  ``ctx.llm`` provider/model overrides (#23194). Without that gate,
  any enabled plugin could silently replace a privileged built-in
  like ``shell_exec`` or ``write_file`` and exfiltrate everything
  the model invokes through it.
  """
  ```
- `register_command(name, ...)`——注册一个 `/name` 斜杠命令。
- `register_cli_command(name, help, setup_fn, handler_fn)`——注册一个 `hermes <name> ...` 顶层 CLI 子命令(比如 `hermes honcho ...`),`setup_fn` 拿到的是一个 argparse 子解析器。

**Provider 类**——声明"我能提供某种能力的一份实现",覆盖面几乎跟遍了 Hermes 所有的可插拔能力点:`register_context_engine`、`register_context_reference`、`register_memory_provider`、`register_image_gen_provider`、`register_video_gen_provider`、`register_web_search_provider`、`register_browser_provider`、`register_terminal_environment_provider`、`register_secret_source`、`register_tts_provider`、`register_transcription_provider`、`register_dashboard_auth_provider`、`register_approval_transport`。这一组方法数量最多,也最直观地体现了 Hermes"几乎每一种外部依赖(记忆存储、图片生成、网页搜索、浏览器、终端后端、密钥来源、TTS/STT、审批呈现)都是可替换 provider"的产品设计。

**平台与消息类**——`register_platform`(注册一个消息网关平台适配器)、`register_platform_handler`、`register_slack_action_handler`、`register_telegram_handler`,服务于第 09 章要讲的多平台网关。

**Hook / Middleware 类**——`register_hook(hook_name, callback)` 和 `register_middleware(kind, callback)`。两者的语义边界写在 `register_middleware` 的文档字符串里:

```python
# hermes_cli/plugins.py:3567-3573(节选)
"""Register a behavior-changing middleware callback.

Middleware is separate from observer hooks: request middleware may
rewrite the effective payload, and execution middleware may wrap the
real callback. Unknown kinds are stored for forward compatibility but
warned so plugin authors can catch typos.
"""
```

也就是说,hook 是"通知我发生了什么、我可以观察或在少数几个类型化拦截点上给出决定",middleware 是"我要包一层、改写真正的执行行为"——两者共用同一种"未知名字警告但不拒绝"的前向兼容策略。

**UI / 上下文注入类**——`register_system_prompt_section(id, content, position=, max_chars=)` 把一段内容冻结进每个新会话的系统提示词;`register_skill(name, path, ...)` 注册一个只能通过 `'<plugin>:<name>'` 显式加载、不进入 `<available_skills>` 索引的只读技能;`register_auxiliary_task`、`register_redaction_patterns` 分别覆盖后台任务和敏感信息脱敏规则。

25 个方法背后共享同一套生命周期基础设施:每一次成功的 `register_*` 调用都会通过 `PluginContext._track()` 在"所有权账本"里登记一条可撤销记录,插件卸载或热重载时按注册的逆序统一清理——这一点会在第 09 章讲插件生命周期时详细展开。

## Hook 派发:`VALID_HOOKS`、超时与前向兼容

`register_hook()` 本身只做两件事:检查名字是否在 `VALID_HOOKS` 集合里(不在也只是警告,依然照常注册),然后把回调追加进 `PluginManager._hooks[hook_name]` 列表。真正触发回调的是 `invoke_hook(hook_name, **kwargs)`(`hermes_cli/plugins.py:6462`),Agent 核心循环在恰当的时机调用它。

`VALID_HOOKS` 目前登记了三十多个事件名,覆盖工具调用前后(`pre_tool_call`/`post_tool_call`)、流式输出观察(`on_stream_delta` 等,只读、不能改写流)、验证循环闸门(`pre_verify`)、API 错误分类覆盖(`transform_api_error_classification`)、会话生命周期、看板任务生命周期、网关平台事件等等——这份列表本身就是一部"Hermes 内部到底有多少个类型化拦截点"的活文档,每个条目上方都带着一段注释说明触发时机、kwargs 形状、以及是"观察者(返回值被忽略)"还是"可以给出决定"。

超时机制是另一层保护:`_HOOK_CALLBACK_TIMEOUT_SECS`(默认 30 秒,可配置,上限 600 秒)只覆盖"agent 回合热路径"上的一个白名单子集——比如 `on_session_finalize`/`on_session_reset` 这类低频收尾钩子被有意排除在外,因为"fail-open 放弃"可能丢失最后一次落盘的机会。这条设计原文写得很直白:

```python
# hermes_cli/plugins.py:398-403(节选)
# Timeout coverage is an allowlist for the agent-turn hot path, not every
# entry in VALID_HOOKS. The goal is to stop a hung Python plugin callback from
# wedging the conversation loop (#76821) without joining the worker (avoids
# the #6622 ThreadPoolExecutor shutdown hang).
```

下一篇要精读的 RFC 会指出:Pi 和 OpenCode 都没有做 hook 超时,都因此吃过挂起类故障——这里可以看到 Hermes 已经把这条教训落地成了一份带 issue 编号引用的具体实现。

## 架构取舍:单一 PluginContext vs Cordis 三元结构

DeepSeek-Harness 的 Cordis 框架把"能力扩展"建模成一棵服务依赖树:每个能力是 Context 里一个按名字索引的服务,`Service` 基类定义契约,具体 Provider 包实现契约,`inject` 声明依赖,框架自动拓扑排序出加载顺序,热替换一个 Provider 会自动级联卸载/重载所有依赖它的插件。这是一套独立的、领域无关的元框架——Cordis 本身不知道"工具""记忆""LLM"是什么,它只认服务名字。

Hermes 走的是完全不同的一条路:没有独立元框架,`PluginContext` 是一个手写的、领域相关的巨型门面类,每一种可扩展能力(工具、provider、hook、平台适配器……)都是这个类上一个专门写死的 `register_*` 方法,而不是"往一棵通用服务树里挂一个实现"。加载顺序不是拓扑排序算出来的抽象结果,而是"bundled → user → project → pip"四段固定代码顺序,外加 manifest v2 里 `requires_plugins` 声明的一层可选拓扑排序(仅作用于同一批次内的插件间顺序,不是 Cordis 那种服务级的全局依赖图)。

这个选择的取舍很清楚:

- **代价**是可扩展性打了折扣——新增一种可插拔能力,需要有人在 `PluginContext` 里手写一个新的 `register_xxx` 方法(以及配套的 manager 内部存储、生命周期追踪代码),不能像 Cordis 那样"随便一个插件 `provide()` 一个新服务名字,消费方 `inject` 它就能用"。25 个方法背后其实是 25 处手写的样板代码。
- **换来的**是极强的可发现性和类型安全:插件作者打开 `PluginContext` 的源码或文档,能一眼看到"我能做的事情"就是这份有限的方法列表,IDE 补全直接可用,不需要先理解一套服务命名和依赖注入的元协议;宿主也不需要在运行时处理"服务名字冲突""依赖环""服务消失导致依赖方级联卸载"这些 Cordis 要花大量机制去解决的通用问题——因为 Hermes 的"服务"本来就是有限、封闭、提前枚举好的一个集合。
- 这与 Hermes 作为一个面向终端用户的产品(而非一个通用 Agent Harness 框架)的定位是吻合的:它更需要"装个插件就能用、行为可预期"的确定性,而不是"能扩展出全新一类核心能力"的元编程灵活性。

## 小结与思考题

Hermes 的插件发现是四条来源按固定顺序合并、后覆盖前,项目级来源默认关闭需要显式 opt-in;每个目录插件由 `plugin.yaml` 声明身份、`register(ctx)` 接入行为,两者是相互独立的信息来源。`PluginContext` 用 25 个专用的 `register_*` 方法覆盖工具/命令、provider、平台、hook/middleware、UI 注入五大扩展面,而不是一套通用的服务注册协议;这与 DeepSeek-Harness 的 Cordis 三元结构形成了鲜明对照——前者用手写样板换取强可发现性和确定性,后者用一套元框架换取真正开放的可扩展性。VALID_HOOKS 和 hook 超时机制则说明,尽管架构选择不同,"防止一个失控的插件挂起整个 Agent"这条工程要求是共通的。

思考题:
1. 如果 Hermes 想在不引入 Cordis 式服务树的前提下,让第三方插件也能定义"新的可插拔能力类别"(而不是复用现有的 25 种),需要在 `PluginContext` 之外补充哪些机制?
2. `requires_plugins` 的拓扑排序只在"同一批发现结果内部"生效,如果一个用户插件依赖一个尚未安装的 pip 插件,会发生什么?结合 `resolve_plugin_load_order()` 里"缺失依赖只警告、不阻断加载"的设计,思考这条策略的利弊。
