# 工具自注册管线与 Schema

> `tools/` 目录下有 141 个文件,没有一个中心化的"工具清单"文件列出它们的名字。每个工具文件在被导入
> 时,自己调用一次 `tools.registry.register()` 把名字、schema、handler、可用性探针塞进一个全局注册
> 表——这是彻底的"文件即插件"模式。`model_tools.py` 只做两件事:触发这场大规模的自注册(导入每一个
> 工具模块),然后把注册表里攒下来的结果,转换成 `run_agent.py`、`cli.py`、各家 provider transport 
> 分别需要的形状。本篇沿着真实源码拆开这条从"文件"到"模型看到的 tool schema"的管线。

## 学习目标

- 理解 `model_tools.py` 顶部注释描述的"薄编排层"定位:它不定义任何工具,只触发发现并暴露公共 API。
- 读懂 `tools/registry.py::discover_builtin_tools()` 的发现机制——AST 扫描 + 磁盘缓存,而不是简单的
  `import *`。
- 读懂 `ToolEntry` 的字段含义,以及 `registry.register()` 在注册时做的覆盖保护(`override=True` 
  的显式опт-in、跨 toolset 遮蔽拒绝)。
- 看两个真实工具文件(`tools/file_tools.py` 的 `read_file`/`write_file`,`tools/terminal_tool.py` 的
  `terminal`)的 schema + handler + 注册代码,理解一个工具文件的典型结构。
- 理解工具的 OpenAI 风格 schema 是怎么在 `agent/transports/*.py` 里被转换成 Anthropic/Gemini 等厂商
  期望的具体格式的。
- 理解这套"文件自注册"和 DeepSeek-Harness Seam 三元结构(Service Definition/Provider/Tool)相比,
  轻在哪里。

## `model_tools.py`:一句话说清它的定位

`model_tools.py` 文件顶部的 docstring 把自己的角色讲得非常克制:

```python
# model_tools.py:1-21(节选)
"""
Model Tools Module

Thin orchestration layer over the tool registry. Each tool file in tools/
self-registers its schema, handler, and metadata via tools.registry.register().
This module triggers discovery (by importing all tool modules), then provides
the public API that run_agent.py, cli.py, batch_runner.py, and the RL
environments consume.

Public API (signatures preserved from the original 2,400-line version):
    get_tool_definitions(enabled_toolsets, disabled_toolsets, quiet_mode) -> list
    handle_function_call(function_name, function_args, task_id, user_task) -> str
    ...
"""
```

它触发发现的方式,就是模块级别直接调用一次:

```python
# model_tools.py:226-230
# =============================================================================
# Tool Discovery  (importing each module triggers its registry.register calls)
# =============================================================================

discover_builtin_tools()
```

`discover_builtin_tools()` 一执行,`tools/` 目录下每一个"自己会调用 `registry.register()`"的文件都
被 `import`,而 Python 的 `import` 语句本身会执行模块顶层代码——包括模块末尾那几行
`registry.register(name=..., ...)` 调用。这就是"自注册"的全部机制:没有中心清单,注册这件事发生在
每个工具文件自己的导入副作用里。

## 发现机制:AST 扫描 + 磁盘缓存,而不是暴力 `import *`

`tools/registry.py::discover_builtin_tools()` 并不是无脑地 `import` 目录下所有 `.py` 文件——它先用
一次静态 AST 扫描确认某个文件"真的会调用 `registry.register()`",再决定要不要导入它:

```python
# tools/registry.py:74-108(节选)
def _is_registry_register_call(node: ast.AST) -> bool:
    """Return True when *node* is a ``registry.register(...)`` call expression."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "register"
        and isinstance(func.value, ast.Name)
        and func.value.id == "registry"
    )


def _module_registers_tools(module_path: Path) -> bool:
    """Return True when the module contains a top-level ``registry.register(...)`` call.

    Only inspects module-body statements so that helper modules which happen
    to call ``registry.register()`` inside a function are not picked up.
    """
    ...
    return any(_is_registry_register_call(stmt) for stmt in tree.body)
```

`discover_builtin_tools()` 遍历 `tools/*.py`,对每个文件做这个判断,再把判定结果连同文件的
`(mtime_ns, size)` 写进一份磁盘缓存(`~/.hermes/cache/tool_discovery_cache.json`)。下次启动时,如
果文件的 mtime/size 没变,直接信任缓存结果,跳过 AST 解析:

```python
# tools/registry.py:111-120(节选)
def discover_builtin_tools(tools_dir: Optional[Path] = None) -> List[str]:
    """Import built-in self-registering tool modules and return their module names.

    The per-file AST scan (:func:`_module_registers_tools`) costs ~145 ms over
    ~100 files on a warm cache, so verdicts are memoized on disk keyed by
    ``(mtime_ns, size)``. A file whose mtime_ns+size match the cached entry is
    trusted without re-reading; any mismatch (or a corrupt/missing cache file)
    falls back to a fresh scan for that file.
    """
```

这套"扫描判定 + 磁盘缓存"设计解决的是一个实际的性能问题:141 个工具文件里,并不是每一个都在模块
顶层调用 `register()`(有些是被其他工具文件 `import` 的纯辅助模块,比如 `terminal_hints.py`),如果
不加判定直接全部 `import`,会白白付出这些辅助模块的加载开销;而如果每次启动都用 AST 重新解析全部
文件再决定,又要付出 ~145ms 的解析成本——磁盘缓存把这笔成本摊薄到"文件内容变化时才重新付一次"。

## `ToolEntry` 与 `register()`:注册进去的到底是什么

一次注册会在注册表里落地成一个 `ToolEntry`:

```python
# tools/registry.py:204-233(节选)
class ToolEntry:
    """Metadata for a single registered tool."""

    __slots__ = (
        "name", "toolset", "schema", "handler", "check_fn",
        "requires_env", "is_async", "description", "emoji",
        "max_result_size_chars", "dynamic_schema_overrides",
    )
```

其中 `check_fn` 是"这个工具当前是否可用"的探针(比如"Home Assistant token 有没有配置"),
`dynamic_schema_overrides` 是一个可选的零参回调,在每次 `get_tool_definitions()` 时被重新调用,
把运行时才能确定的字段(比如"当前是否有可信的 OCR 路由")浅合并进基础 schema——下一节会看到具体
例子。

`registry.register()` 的签名和保护逻辑值得单独看一眼:

```python
# tools/registry.py:763-778(节选)
def register(
    self,
    name: str,
    toolset: str,
    schema: dict,
    handler: Callable,
    check_fn: Callable = None,
    requires_env: list = None,
    is_async: bool = False,
    description: str = "",
    emoji: str = "",
    max_result_size_chars: int | float | None = None,
    dynamic_schema_overrides: Callable = None,
    override: bool = False,
    scope: Optional[str] = None,
):
    """Register a tool.  Called at module-import time by each tool file.

    ``override=True`` is an explicit opt-in for plugins that intend to
    replace an existing built-in tool implementation ... Without it,
    registrations that would shadow an existing tool from a different
    toolset are rejected to prevent accidental overwrites.
    """
```

这里的保护逻辑是:如果一个新注册和已存在的同名工具属于**不同的 toolset**,默认直接拒绝并打
`ERROR` 日志,除非显式传 `override=True`——这防止了一个疏忽的插件作者不小心用同名工具覆盖掉内置工
具而不自知。对插件而言,`override=True` 还要通过 `_plugin_override_allowed()` 的操作员级白名单
(`plugins.entries.<id>.allow_tool_override` 配置),双重把关。

## 一个文件的真实结构:`file_tools.py` 里的 `read_file`

`tools/file_tools.py` 有 2900 多行,但真正暴露给模型的只是文件末尾几行注册调用,前面绝大部分代码是
路径解析、沙箱检查、审批流程这些 handler 内部逻辑。schema 长这样(标准 OpenAI function-calling 形
状:`name`/`description`/`parameters` JSON Schema):

```python
# tools/file_tools.py:2649-2669
READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": "Read a text file with line numbers and pagination. Use this "
        "instead of cat/head/tail in terminal. Output format: 'LINE_NUM|CONTENT'. "
        "...",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read ..."},
            "offset": {"type": "integer", "description": "...", "default": 1, "minimum": 1},
            "limit": {"type": "integer", "description": "...", "default": 2000, "maximum": 2000}
        },
        "required": ["path"]
    }
}
```

handler 是一个把模型传入的 `args` 字典解包成内部函数调用参数的薄适配层:

```python
# tools/file_tools.py(节选,handle_read_file 附近)
def _handle_read_file(args, **kw):
    tid = kw.get("task_id") or "default"
    return read_file_tool(path=args["path"], offset=args.get("offset", 1),
                           limit=args.get("limit", 2000), task_id=tid, ...)
```

而 `dynamic_schema_overrides` 展示了 schema 如何在"注册时是静态的"和"暴露给模型时可以是动态的"
之间取得平衡——比如 `read_file` 的描述里"PDF (text layer)"这半句话,只有在检测到可信的托管 OCR 路
由时才升级成"PDF (scanned or text)":

```python
# tools/file_tools.py:2860-2878(节选)
def _read_file_schema_overrides():
    """One-word capability upgrade: "PDF (text layer)" → "PDF (scanned or
    text)" when hosted OCR has a trusted route ... Config/env probe only —
    no network at schema-build time. Compaction's tool refresh (#97073)
    picks up a key added mid-session.
    """
    try:
        from tools.read_extract import hosted_ocr_available
        if hosted_ocr_available():
            return {"description": READ_FILE_SCHEMA["description"].replace(
                "PDF (text layer)", "PDF (scanned or text)")}
    except Exception:
        pass
    return {}

registry.register(
    name="read_file", toolset="file", schema=READ_FILE_SCHEMA,
    handler=_handle_read_file, check_fn=_check_file_reqs, emoji="📖",
    max_result_size_chars=100_000, dynamic_schema_overrides=_read_file_schema_overrides,
)
registry.register(name="write_file", toolset="file", schema=WRITE_FILE_SCHEMA,
    handler=_handle_write_file, check_fn=_check_file_reqs, emoji="✍️",
    max_result_size_chars=100_000)
```

## Shell 类工具:`terminal_tool.py` 的极简注册尾巴

相比 `file_tools.py` 的多工具文件,`tools/terminal_tool.py`(4213 行,是 `tools/` 目录里最大的单文
件之一,承载了完整的终端后端调度、危险命令审批、后台任务追踪)最终只注册了一个工具名:

```python
# tools/terminal_tool.py:4205-4213
registry.register(
    name="terminal",
    toolset="terminal",
    schema=TERMINAL_SCHEMA,
    handler=_handle_terminal,
    check_fn=check_terminal_requirements,
    emoji="💻",
    max_result_size_chars=100_000,
)
```

这印证了一个规律:**注册调用本身永远是薄薄的一行,文件的体量差异完全来自 handler 内部逻辑的复杂
度**,而不是 schema/注册机制本身。无论 `read_file` 这种几十行的工具,还是 `terminal` 这种要处理
本地/Docker/SSH/Modal 多种执行环境的重型工具,它们在注册表里的"形状"是一样的:一个名字、一份
schema、一个 handler、一个可选的 `check_fn`。

## Schema 最终怎么变成不同厂商的格式

`get_tool_definitions()` 把注册表里的 schema 包装成标准 OpenAI 风格的 `{"type": "function",
"function": {...}}` 列表(`model_tools.py` 内多处 `filtered_tools[i] = {"type": "function",
"function": ...}`)。这份 OpenAI 风格的列表是所有 provider 共享的"中间表示"——真正按厂商差异转换
格式的工作,发生在 `agent/transports/*.py` 这一层。以 Anthropic 为例:

```python
# agent/transports/anthropic.py:35-39
def convert_tools(self, tools: List[Dict[str, Any]]) -> Any:
    """Convert OpenAI tool schemas to Anthropic input_schema format."""
    from agent.anthropic_adapter import convert_tools_to_anthropic
    return convert_tools_to_anthropic(tools)
```

```python
# agent/anthropic_adapter.py:1826-1861(节选)
def convert_tools_to_anthropic(tools: List[Dict]) -> List[Dict]:
    """Convert OpenAI tool definitions to Anthropic format."""
    result = []
    for t in tools:
        fn = t.get("function", {})
        anthropic_tool = {
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": _normalize_tool_input_schema(
                fn.get("parameters", {"type": "object", "properties": {}})
            ),
        }
        result.append(anthropic_tool)
    return result
```

`_normalize_tool_input_schema()` 还要做一层清洗——Anthropic 的 schema 校验器不接受
`anyOf: [{"type": "string"}, {"type": "null"}]` 这类 Pydantic/MCP 常见的"可空联合"写法,也不接受
顶层的 `oneOf`/`allOf`/`anyOf`,`convert_tools_to_anthropic()` 在转换时把这些结构拍平成 Anthropic
能接受的形状。`agent/transports/base.py` 里的 `ProviderTransport` 抽象基类把这整条流水线的顺序写
在了模块 docstring 里:

```python
# agent/transports/base.py:1-8
"""Abstract base for provider transports.

A transport owns the data path for one api_mode:
  convert_messages → convert_tools → build_kwargs → normalize_response

It does NOT own: client construction, streaming, credential refresh,
prompt caching, interrupt handling, or retry logic.  Those stay on AIAgent.
"""
```

也就是说,`tools/*.py` 自注册产出的是一份**厂商中立**的 OpenAI 风格 schema,而"这份 schema 最终发
给 Anthropic 时长什么样"是 transport 层的职责,和上一篇讲的 `ProviderProfile`/原生 adapter 是同一
条分工原则的延伸——工具系统本身完全不需要知道自己会被发给哪家厂商。

## 和 DeepSeek-Harness Seam 三元结构的对比

如果你学过 DeepSeek-Harness 的能力扩展范式,会记得那边的工具系统是一套更重的三元结构:
`ToolDefinition`(output 契约 + execute + finalizeContent + presentCall/presentResult)、
`ToolRuntime` 的三段瀑布流水线(`tools/pre-execute` → Guard → `tools/execute` →
`tools/post-execute`)、以及独立的调度器(并行池 + 独占屏障)。hermes-agent 这边明显更轻量:

- **没有独立的输出契约层**。DeepSeek-Harness 要求每个工具声明 `output.schema` + `render()`,把
  "规范化的值"和"喂给模型的文本"分离;hermes-agent 的 handler 直接返回字符串(通常是
  `tool_result()`/`tool_error()` 包装的 JSON 文本),schema 只管输入参数,不管输出契约。
- **没有可插拔的权限/审批瀑布**。hermes-agent 把审批逻辑(比如危险命令确认、受保护路径写入确认)
  写在具体工具的 handler 内部(`file_tools.py` 里的 `_request_protected_instruction_approval` 等函
  数),而不是一套所有工具共享的、外部可插入的 `tools/pre-execute` waterfall。
- **`check_fn` 承担了部分职责,但语义更窄**。它只回答"这个工具现在要不要出现在 schema 里"，不参
  与已经决定调用之后的执行期拦截——这部分逻辑分散在各个工具自己的 handler 里。

这个对比背后是两个项目的定位差异:DeepSeek-Harness 的三元结构是给"许多前后端团队共享同一套工具执
行框架"设计的通用元框架,值得为可插拔性单独付出一层抽象成本;而 hermes-agent 的工具几乎全部是内建
的、跟自己的沙箱/审批体系强耦合的能力,不需要对外提供一个通用的执行流水线协议,所以选择了"文件自
注册 + 极简 `ToolEntry`"这种更轻的方案。

## 小结与思考题

一个工具从"仓库里的一个 `.py` 文件"变成"模型能调用的 tool"要经过三步:`discover_builtin_tools()`
用 AST 扫描 + 磁盘缓存判定哪些文件该被导入,导入触发文件末尾的 `registry.register()` 调用把
`ToolEntry` 塞进全局注册表,`model_tools.py::get_tool_definitions()` 再把注册表内容过滤、包装成
OpenAI 风格的 tool schema。这份中间表示本身是厂商中立的,真正按厂商差异转换成 Anthropic
`input_schema`、Gemini `FunctionDeclaration` 等具体格式,发生在 `agent/transports/*.py` 这一层,和
Provider Profile/原生 Adapter 共享同一条"工具/消息系统不关心厂商是谁"的设计原则。相比
DeepSeek-Harness 的 Seam 三元结构,hermes-agent 的自注册模式没有独立的输出契约层和可插拔执行瀑布,
换来的是极低的新增工具成本——一个工具文件通常只需要一份 schema 字典、一个 handler 函数、一行注册
调用。

思考题:

1. `discover_builtin_tools()` 只在**模块顶层**寻找 `registry.register()` 调用(`_module_registers_tools`
   只检查 `tree.body`,不递归进函数体)。如果一个工具作者把注册调用包在一个 `if` 分支或函数里(比如
   "只在某个条件满足时才注册"),这个工具还能被发现吗?这样设计的取舍是什么?
2. `dynamic_schema_overrides` 在每次 `get_tool_definitions()` 调用时都会被重新执行一次。如果一个工
   具的 override 函数里做了网络请求(而不是像 `_read_file_schema_overrides` 那样只做本地探测),
   会带来什么问题?这也是为什么该函数的 docstring 特意强调"no network at schema-build time"的原因。
3. `registry.register()` 对"跨 toolset 遮蔽"的默认拒绝,和上一篇讲的 Provider Profile
   "last-writer-wins"覆盖规则,在设计哲学上似乎正好相反——一个默认拒绝覆盖,一个默认允许覆盖。结
   合两者各自的使用场景(工具名冲突 vs provider 名冲突),说说这种不一致是合理的还是应该统一?
