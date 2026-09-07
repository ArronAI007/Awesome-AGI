# Hooks 机制:事件驱动的行为注入

> 前面四篇讲的都是"给模型增加能做什么"——更多工具、按需加载的知识、可打包分发的插件、外部服务器暴露的能力。Hooks 解决的是另一个方向的问题:在模型调用工具前后、会话生命周期的关键节点上,插入一段不受模型自由意志支配的确定性(或半确定性)校验。`engine/query.py` 里 `_execute_tool_call()` 的证据很直接——`PRE_TOOL_USE` 钩子在权限检查**之前**就有机会直接拒绝一次工具调用,`POST_TOOL_USE` 钩子则在工具执行完毕、结果已经写回消息历史之后才触发。更值得注意的是 hooks 支持四种类型而不只是"执行一条 shell 命令"这一种——`command`/`http`/`prompt`/`agent`,后两种会真的发起一次模型调用来做语义判断,而不是简单的规则匹配。本篇还会讲清楚"热重载"这件事:开发一个 hook 时是否需要重启整个 Agent 进程才能生效。

## 学习目标

- 认清 `HookEvent` 定义的十种生命周期事件,以及它们各自在系统里的触发时机。
- 读懂 `HookExecutor.execute()` 如何按优先级顺序执行同一事件下的多个钩子,以及 `_matches_hook()` 的通配符匹配逻辑。
- 理解四种钩子类型(`command`/`http`/`prompt`/`agent`)各自的执行方式,尤其是后两种如何把"钩子判断"本身也变成一次模型调用。
- 找到 `PRE_TOOL_USE`/`POST_TOOL_USE` 在 `engine/query.py` 里的真实触发位置,理解 hooks 和权限系统是两条独立但顺序衔接的检查链路。
- 搞清楚 hooks 热重载具体发生在哪个粒度(逐行 vs. 逐进程),回答"改一条 hook 配置要不要重启 Agent"这个问题。

## 背景与设计动机

一个允许模型自主调用 Bash、编辑文件、发起网络请求的 Agent Harness,天然需要一套"确定性护栏"——不完全依赖模型自己判断"这个操作安全吗",而是在关键节点插入外部校验。这类校验的形态其实很多样:可能是一条简单的 shell 命令(比如"检查即将写入的文件是不是 `.env`");也可能需要更复杂的语义判断(比如"这条 bash 命令是不是在尝试绕过某个已知的安全限制"),用规则很难穷举,但用另一次模型调用去判断反而更可靠。OpenHarness 的 Hooks 系统同时支持这两种形态——`command` 类型覆盖前者,`prompt`/`agent` 类型覆盖后者——而不是只提供最基础的 shell 命令钩子。同时,hooks 配置往往是在开发调试阶段被频繁修改的东西,如果每改一条配置都要重启整个交互式会话才能生效,会严重拖慢迭代速度,这也是为什么"热重载"值得单独作为一个话题来看。

## 核心机制详解

### 十种生命周期事件

```python
# src/openharness/hooks/events.py
class HookEvent(str, Enum):
    """Events that can trigger hooks."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PRE_COMPACT = "pre_compact"
    POST_COMPACT = "post_compact"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    NOTIFICATION = "notification"
    STOP = "stop"
    SUBAGENT_STOP = "subagent_stop"
```

这十个事件覆盖了会话的完整生命周期:开始/结束(`SESSION_START`/`SESSION_END`)、上下文压缩前后(`PRE_COMPACT`/`POST_COMPACT`,对应第三章讲过的自动压缩机制)、每一次工具调用前后(`PRE_TOOL_USE`/`POST_TOOL_USE`)、用户提交新消息时(`USER_PROMPT_SUBMIT`)、需要向用户展示通知时(`NOTIFICATION`,第一篇提到的"权限确认弹窗"就会触发这个事件)、模型认为一轮任务完成时(`STOP`)、以及子 agent 结束时(`SUBAGENT_STOP`,第一篇 `agent_tool.py` 里能看到这个事件的具体触发点)。这份事件列表本身构成了整个 Agent 生命周期的"骨架视图"——想知道一个 Agent Harness 在运行过程中有哪些关键节点,看它定义了哪些 hook 事件是一条捷径。

### 四种钩子类型:从确定性命令到模型驱动判断

```python
# src/openharness/hooks/schemas.py(节选)
class CommandHookDefinition(BaseModel):
    type: Literal["command"] = "command"
    command: str
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    matcher: str | None = None
    block_on_failure: bool = False
    priority: int = Field(default=0)


class PromptHookDefinition(BaseModel):
    type: Literal["prompt"] = "prompt"
    prompt: str
    model: str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=600)
    matcher: str | None = None
    block_on_failure: bool = True
    priority: int = Field(default=0)


class AgentHookDefinition(BaseModel):
    type: Literal["agent"] = "agent"
    prompt: str
    model: str | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=1200)
    matcher: str | None = None
    block_on_failure: bool = True
    priority: int = Field(default=0)
```

`command` 类型是最基础的一种——执行一条 shell 命令,用退出码判断成功与否,默认 `block_on_failure=False`(命令失败只是记录,不阻断)。`prompt` 和 `agent` 类型结构几乎一样(都是一段 `prompt` 加可选的 `model` 覆盖),区别只在语义上:`prompt` 是一次轻量的判断请求,`agent` 允许更长的超时(60 秒到 1200 秒 vs. 30 秒到 600 秒)并且在执行时会额外强调"更彻底地推理"。两者默认 `block_on_failure=True`——这个默认值差异本身值得注意:一条 shell 命令失败很可能只是环境问题(比如某个检查脚本本身有 bug),默认不阻断更保守;而一次专门设计用来做语义判断的模型调用,如果它判定"不通过",默认就应该真的拦下来,否则这个钩子形同虚设。

`priority` 字段决定同一事件下多个钩子的执行顺序:

```python
# src/openharness/hooks/loader.py(节选)
def get(self, event: HookEvent) -> list[HookDefinition]:
    """Return hooks registered for an event, ordered by priority.

    Hooks with a higher ``priority`` run first. ``sorted`` is stable, so
    hooks sharing the same priority keep their registration order.
    """
    hooks = self._hooks.get(event, [])
    return sorted(hooks, key=lambda hook: -getattr(hook, "priority", 0))
```

数值越大越先执行,同优先级的钩子保持注册顺序(Python `sorted` 是稳定排序,这里用负号取代 `reverse=True` 达到降序效果,同时保留了同值时的原始顺序)——这允许用户表达"这条安全检查必须先于其他钩子跑"这类意图,而不是完全依赖配置文件里的书写顺序。

### `prompt`/`agent` 钩子:让判断本身发起一次模型调用

```python
# src/openharness/hooks/executor.py(节选)
async def _run_prompt_like_hook(self, hook, event, payload, *, agent_mode: bool) -> HookResult:
    prompt = _inject_arguments(hook.prompt, payload)
    prefix = (
        "You are validating whether a hook condition passes in OpenHarness. "
        "Return strict JSON: {\"ok\": true} or {\"ok\": false, \"reason\": \"...\"}."
    )
    if agent_mode:
        prefix += " Be more thorough and reason over the payload before deciding."
    request = ApiMessageRequest(
        model=hook.model or self._context.default_model,
        messages=[ConversationMessage.from_user_text(prompt)],
        system_prompt=prefix,
        max_tokens=512,
    )
    ...
    parsed = _parse_hook_json(text)
    if parsed["ok"]:
        return HookResult(hook_type=hook.type, success=True, output=text)
    return HookResult(hook_type=hook.type, success=False, output=text, blocked=hook.block_on_failure, reason=parsed.get("reason", "hook rejected the event"))
```

这是整个 hooks 系统里最有意思的设计:一次钩子判断本身就是一次完整的模型 API 调用,系统提示词固定要求模型"只返回严格的 JSON:`{"ok": true}` 或 `{"ok": false, "reason": "..."}`",`agent_mode` 为真时额外要求模型"更彻底地推理"。这意味着钩子作者可以用自然语言描述一条很难用规则精确表达的校验条件——比如"检查这条即将执行的命令是否有明显的数据泄露风险",而不需要写一段复杂的正则或规则引擎去匹配。`_parse_hook_json()` 对模型返回结果做了容错:严格 JSON 解析失败时,如果整段文本是 `"ok"`/`"true"`/`"yes"` 这类简单肯定词,也接受为通过,其余一律判定为不通过并把原始文本当作拒绝理由——这是应对模型偶尔不遵守"只返回 JSON"指令的一层保险。

`hook.prompt` 支持 `$ARGUMENTS` 占位符,`_inject_arguments()` 会把当前事件的完整 payload 序列化成 JSON 字符串替换进去(`command` 类型的钩子还会在这一步做 shell 转义):

```python
# src/openharness/hooks/executor.py(节选)
def _inject_arguments(template: str, payload: dict[str, Any], *, shell_escape: bool = False) -> str:
    serialized = json.dumps(payload, ensure_ascii=True)
    if shell_escape:
        serialized = shlex.quote(serialized)
    return template.replace("$ARGUMENTS", serialized)
```

`shell_escape` 只在 `command` 类型钩子里为 `True`——因为 payload 内容最终会作为 shell 命令的一部分执行,如果不转义,payload 里的引号或特殊字符可能破坏命令语法甚至引入命令注入;`prompt`/`agent` 类型钩子的 payload 是作为纯文本发给模型的,不需要 shell 层面的转义。

### `matcher`:用通配符收窄钩子的触发范围

```python
# src/openharness/hooks/executor.py(节选)
def _matches_hook(hook: HookDefinition, payload: dict[str, Any]) -> bool:
    matcher = getattr(hook, "matcher", None)
    if not matcher:
        return True
    subject = str(payload.get("tool_name") or payload.get("prompt") or payload.get("event") or "")
    return fnmatch.fnmatch(subject, matcher)
```

如果一条钩子没有配置 `matcher`,它对所属事件的每一次触发都会执行;配置了 `matcher` 则用 `fnmatch`(shell 风格的通配符,比如 `bash*`、`*write*`)去匹配 `payload` 里的 `tool_name`(工具调用类事件)、`prompt`(提示相关事件)或 `event` 字段之一。这让用户可以写出"只在调用 `bash` 工具时触发的 `PRE_TOOL_USE` 钩子",而不是所有工具调用都触发同一批钩子——这对于"检查即将执行的 shell 命令是否安全"这类只对特定工具有意义的校验尤其重要。

### `PRE_TOOL_USE`/`POST_TOOL_USE` 的真实触发位置

```python
# src/openharness/engine/query.py(节选,_execute_tool_call)
async def _execute_tool_call(context, tool_name, tool_use_id, tool_input) -> ToolResultBlock:
    if context.hook_executor is not None:
        pre_hooks = await context.hook_executor.execute(
            HookEvent.PRE_TOOL_USE,
            {"tool_name": tool_name, "tool_input": tool_input, "event": HookEvent.PRE_TOOL_USE.value},
        )
        if pre_hooks.blocked:
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=pre_hooks.reason or f"pre_tool_use hook blocked {tool_name}",
                is_error=True,
            )

    log.debug("tool_call start: %s id=%s", tool_name, tool_use_id)
    tool = context.tool_registry.get(tool_name)
    ...
    decision = context.permission_checker.evaluate(...)
    if not decision.allowed:
        ...
    result = await tool.execute(...)
    ...
    if context.hook_executor is not None:
        await context.hook_executor.execute(
            HookEvent.POST_TOOL_USE,
            {"tool_name": tool_name, "tool_input": tool_input, "tool_output": tool_result.content, "tool_is_error": tool_result.is_error, "event": HookEvent.POST_TOOL_USE.value},
        )
    return tool_result
```

这段代码把三层检查的先后顺序摆得很清楚:`PRE_TOOL_USE` 钩子最先执行,如果 `pre_hooks.blocked` 为真,函数会**在权限检查(`context.permission_checker.evaluate(...)`)执行之前**就直接返回错误结果——也就是说 hooks 系统的拦截权限比权限系统本身更靠前。这是一个刻意的分层:权限系统(第五章要展开的话题)处理的是"这个工具/路径/命令是否在允许范围内"这类结构化规则,而 `PRE_TOOL_USE` 钩子可以在权限系统介入之前就基于任意自定义逻辑(包括模型判断)拒绝调用,两者是互补而非互斥的两道关卡。`POST_TOOL_USE` 钩子则在工具真正执行完毕、结果已经组装成 `ToolResultBlock` 之后触发,payload 里带上了完整的工具输出和是否出错的标记——这类钩子通常用于审计记录、副作用清理,而不是拦截(虽然 `block_on_failure` 理论上也能让它拦截,但此时工具已经执行完了,拦截只能影响"这次结果要不要被视为失败",不能撤销已经发生的副作用)。

### 热重载:开发一个 hook 不需要重启 Agent 进程

`hooks/hot_reload.py` 提供的是一种基于文件修改时间的缓存重载:

```python
# src/openharness/hooks/hot_reload.py
class HookReloader:
    """Reload hook definitions when the settings file changes."""

    def __init__(self, settings_path: Path) -> None:
        self._settings_path = settings_path
        self._last_mtime_ns = -1
        self._registry = HookRegistry()

    def current_registry(self) -> HookRegistry:
        """Return the latest registry, reloading if needed."""
        try:
            stat = self._settings_path.stat()
        except FileNotFoundError:
            self._registry = HookRegistry()
            self._last_mtime_ns = -1
            return self._registry

        if stat.st_mtime_ns != self._last_mtime_ns:
            self._last_mtime_ns = stat.st_mtime_ns
            self._registry = load_hook_registry(load_settings(self._settings_path))
        return self._registry
```

这不是文件系统监听(没有用 `watchfiles` 之类的库去订阅变更事件),而是"每次被调用时比较一下 mtime,变了才重新解析",典型的惰性缓存失效模式——好处是不需要额外起一个监听协程,坏处是只有在 `current_registry()` 被调用的那一刻才会感知到变化。真正让"改配置不用重启"这件事在交互式会话里生效的,是 `ui/runtime.py` 里 `handle_line()` 的做法:

```python
# src/openharness/ui/runtime.py(节选)
async def handle_line(bundle, line, *, print_system, render_event, clear_output, user_message=None) -> bool:
    """Handle one submitted line for either headless or TUI rendering."""
    if not bundle.external_api_client:
        bundle.hook_executor.update_registry(
            load_hook_registry(bundle.current_settings(), bundle.current_plugins())
        )
    ...
```

每一次用户提交新的一行输入,都会重新调用 `load_hook_registry()` 从当前 settings 和当前已加载插件里完整重建一份 `HookRegistry`,再通过 `HookExecutor.update_registry()` 替换掉执行器里持有的旧注册表——这比 `HookReloader` 的 mtime 缓存更直接,代价是每轮都要重新解析一次配置文件和插件目录,但对于一个"每轮对话之间通常有几秒到几十秒间隔"的交互场景,这点开销可以忽略不计。结论是:**在交互式会话里修改 `settings.json` 里的 hooks 配置(或者往插件目录里新增/修改一份 hooks.json),下一轮提交的用户输入就会用上新配置,完全不需要重启 Agent 进程**——这对于迭代开发一条 hook 规则(改一版、测一轮、看效果、再改)是很实际的效率提升,不用为了验证一处 `matcher` 通配符写得对不对反复重开会话。`HookReloader` 本身则用在另一种场景(`api_client is None` 时,更偏向单次无交互调用的路径),用 mtime 比对避免每次都重新解析文件。

## 常见问题/易踩坑

**Q:`PRE_TOOL_USE` 钩子和权限系统都能拦截工具调用,应该用哪个?**

看校验逻辑的性质。权限系统(第五章详解)处理的是结构化规则——工具白名单/黑名单、路径范围、命令模式匹配,配置成本低、执行确定、审计清晰。`PRE_TOOL_USE` 钩子(尤其是 `prompt`/`agent` 类型)适合规则很难穷举、需要语义理解的场景——比如"判断一条命令是不是在试图绕过某个已知限制",这种意图层面的判断用固定规则容易被绕过,用模型判断反而更稳健,但代价是每次都要多发起一次模型调用,有延迟和额外的 token 成本。两者不冲突,`PRE_TOOL_USE` 钩子先于权限检查执行,可以把"明显有问题、不需要浪费权限系统时间去判断"的调用提前拦下来。

**Q:`command` 类型钩子默认 `block_on_failure=False`,是不是意味着写了也白写?**

不是白写,只是默认语义是"记录但不阻断"。这类钩子常见的用途是审计日志、发送通知、触发外部系统联动,失败(比如日志服务临时不可用)不应该影响 Agent 的正常工作流程,所以默认不阻断更合理。如果确实需要"这条命令检查不通过就必须拦截",在钩子定义里显式设置 `block_on_failure: true` 即可,`CommandHookDefinition` 的这个字段本身是可写的,只是默认值偏保守。

## 小结

Hooks 系统用十个生命周期事件覆盖了会话的关键节点,四种钩子类型(`command`/`http`/`prompt`/`agent`)把"确定性命令校验"和"模型驱动的语义判断"统一到同一套配置格式和执行框架下——`prompt`/`agent` 类型钩子本身会发起一次真实的模型调用并要求严格 JSON 格式的判断结果,这是比单纯的规则引擎更灵活的一种校验手段。`PRE_TOOL_USE` 钩子在权限检查之前就有机会拦截工具调用,`POST_TOOL_USE` 钩子在结果写回消息历史之后触发,两个事件在 `engine/query.py._execute_tool_call()` 里的先后位置清楚地定义了 hooks 和权限系统之间"谁先谁后"的关系。热重载的真实粒度是"交互式会话每轮对话都重新从 settings 和插件目录构建一份新的 `HookRegistry`",这意味着开发调试一条 hook 规则不需要重启整个 Agent 进程,下一轮输入就能验证新配置的效果。

至此,本章把工具、技能、插件、MCP、hooks 这五条扩展路径完整讲完——它们共同回答的是"OpenHarness 给了模型多少能力"这个问题。但能力越大,风险面也越大:一个能执行任意 shell 命令、能编辑任意文件、能连接任意 MCP 服务器、能被任意插件注入 Python 代码的 Agent,如果没有配套的约束机制,后果是灾难性的。下一章会转向权限治理和沙箱执行,也就是 OpenHarness 怎么在给模型这么多能力的同时控制风险。
