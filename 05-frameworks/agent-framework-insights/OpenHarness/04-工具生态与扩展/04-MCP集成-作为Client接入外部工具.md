# MCP 集成:作为 Client 接入外部工具

> OpenHarness 没有实现 MCP Server 模式——通读 `src/openharness/mcp/` 和 `cli.py` 的 `mcp_app` 子命令,找不到任何"把 OpenHarness 自己包装成一个 MCP 服务器暴露出去"的代码,只有 `mcp add`/`mcp remove`/`mcp list` 这类管理已配置服务器的命令。它选择把全部精力放在 Client 这一侧:`mcp/client.py` 里 `McpClientManager` 负责连接、维护会话、探测工具与资源;`tools/mcp_tool.py` 里 `McpToolAdapter` 把每一个远端 MCP 工具包装成本地 `BaseTool`,命名规则直接对齐 Claude Code 的 `mcp__<server>__<tool>` 约定;`tools/mcp_auth_tool.py`/`list_mcp_resources_tool.py`/`read_mcp_resource_tool.py` 三个工具则分别负责认证配置、资源发现、资源读取。本篇把这条"外部 MCP 服务器 → 内部工具调用循环"的链路完整读一遍。

## 学习目标

- 理解 `McpServerConfig` 的三种传输类型(stdio/http/ws)和当前 `McpClientManager` 实际支持的连接类型之间的差异。
- 读懂 `McpClientManager.connect_all()` 的连接生命周期:成功连接后如何探测工具与资源、连接失败如何被记录而不中断启动。
- 搞清楚 `McpToolAdapter` 如何把一个 MCP 工具的 JSON Schema 动态转换成 Pydantic 输入模型,以及为什么工具命名要做 `mcp__<server>__<tool>` 这样的拼接和字符清洗。
- 理解 `list_mcp_resources`/`read_mcp_resource`/`mcp_auth` 三个工具各自解决的问题,以及配置更新后如何触发重连。
- 弄清楚插件配置和 settings 配置的 MCP 服务器是如何合并成同一份运行时配置的。

## 背景与设计动机

MCP(Model Context Protocol)的价值在于把"给模型接入一个新的外部能力"这件事标准化——不用为每一个第三方服务(GitHub、Figma、自建内部系统)单独写一套工具适配代码,只要对方实现了 MCP 协议,任何 MCP Client 都能按统一的握手流程发现它暴露的工具和资源。OpenHarness 只走了 Client 这一侧的路径,理由从代码结构上能读出来:`tools/__init__.py` 里 `create_default_tool_registry(mcp_manager=None)` 把 MCP 管理器作为一个可选依赖注入,内置工具体系和 MCP 工具体系共享同一个 `ToolRegistry`,模型看到的是一份合并后的、无法区分"哪个是内置的、哪个来自 MCP"的统一工具列表——这正是 MCP Client 集成要达到的效果:外部能力应该和原生能力在调用层面无法区分。

## 核心机制详解

### 三种服务器配置类型与实际支持的传输

```python
# src/openharness/mcp/types.py
class McpStdioServerConfig(BaseModel):
    type: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None


class McpHttpServerConfig(BaseModel):
    type: Literal["http"] = "http"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class McpWebSocketServerConfig(BaseModel):
    type: Literal["ws"] = "ws"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


McpServerConfig = McpStdioServerConfig | McpHttpServerConfig | McpWebSocketServerConfig
```

配置层面声明了三种传输类型,但 `McpClientManager.connect_all()` 目前只实现了 `stdio` 和 `http` 两条连接路径:

```python
# src/openharness/mcp/client.py(节选)
async def connect_all(self) -> None:
    """Connect all configured MCP servers supported by the current build."""
    for name, config in self._server_configs.items():
        if isinstance(config, McpStdioServerConfig):
            await self._connect_stdio(name, config)
        elif isinstance(config, McpHttpServerConfig):
            await self._connect_http(name, config)
        else:
            self._statuses[name] = McpConnectionStatus(
                name=name,
                state="failed",
                transport=config.type,
                auth_configured=bool(getattr(config, "headers", None)),
                detail=f"Unsupported MCP transport in current build: {config.type}",
            )
```

配置了 `McpWebSocketServerConfig` 的服务器会落进 `else` 分支,状态被直接标记为 `failed`,detail 里写明"当前构建不支持这个传输类型"——这是一处诚实的能力边界:类型系统里声明了 WebSocket 传输,但运行时还没有对应的连接实现,不会静默忽略,而是在启动状态里明确报告出来,方便用户在 `mcp list`/`/mcp` 里看到这个服务器为什么连不上。

### 连接生命周期:探测工具与资源,失败不中断启动

`_connect_stdio()` 和 `_connect_http()` 的结构是对称的——建立底层读写流,交给 `_register_connected_session()` 完成后续的会话初始化:

```python
# src/openharness/mcp/client.py(节选)
async def _register_connected_session(self, *, name, config, stack, read_stream, write_stream, auth_configured):
    session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
    await session.initialize()
    tool_result = await session.list_tools()
    resource_result = None
    try:
        resource_result = await session.list_resources()
    except Exception as exc:
        if "Method not found" not in str(exc):
            raise
    ...
    self._sessions[name] = session
    self._stacks[name] = stack
    self._statuses[name] = McpConnectionStatus(
        name=name, state="connected", transport=getattr(config, "type", "unknown"),
        auth_configured=auth_configured, tools=tools, resources=resources,
    )
```

握手成功后立刻调用 `list_tools()` 探测这个服务器暴露了哪些工具,再尝试 `list_resources()` 探测资源——但资源列表是可选的,如果服务器返回"Method not found"(说明这个 MCP 服务器根本没实现资源协议这部分),就把异常吞掉当作"没有资源"处理,而不是让整个连接失败;如果是其他类型的异常则重新抛出,交给外层的失败处理逻辑。这个区分很关键:MCP 协议里工具和资源是两个独立的可选能力,一个只暴露工具、不暴露资源的服务器应该能正常连接,不应该因为可选能力缺失而被判定为连接失败。

连接失败(不管是网络错误、进程启动失败还是握手异常)统一走 `_mark_connection_failed()`,并且外层的 `connect_all()` 是一个 `for` 循环——单个服务器连接失败不会抛出异常中断整个启动流程,只会把这一个服务器的状态记成 `failed`,其余服务器继续正常连接:

```python
# src/openharness/mcp/client.py(节选,_connect_stdio)
except Exception as exc:
    await self._close_failed_stack(stack)
    self._mark_connection_failed(name, config, auth_configured=bool(config.env), exc=exc)
```

这意味着"配置了五个 MCP 服务器,其中一个因为命令找不到而连不上"不会导致整个 Agent 启动失败或另外四个服务器也连不上——每个服务器的连接状态是互相隔离的。

### `call_tool`/`read_resource`:把 MCP 协议的返回值拍平成字符串

`ToolResult.output` 是一个字符串字段,而 MCP 协议的 `CallToolResult.content` 是一个可能包含多种内容块(文本、结构化数据等)的列表,`call_tool()` 负责做这层转换:

```python
# src/openharness/mcp/client.py(节选)
async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
    session = self._sessions.get(server_name)
    if session is None:
        status = self._statuses.get(server_name)
        detail = status.detail if status else "unknown server"
        raise McpServerNotConnectedError(f"MCP server '{server_name}' is not connected: {detail}")
    try:
        result: CallToolResult = await session.call_tool(tool_name, arguments)
    except Exception as exc:
        raise McpServerNotConnectedError(f"MCP server '{server_name}' call failed: {exc}") from exc
    parts: list[str] = []
    for item in result.content:
        if getattr(item, "type", None) == "text":
            parts.append(getattr(item, "text", ""))
        else:
            parts.append(item.model_dump_json())
    if result.structuredContent and not parts:
        parts.append(str(result.structuredContent))
    if not parts:
        parts.append("(no output)")
    return "\n".join(parts).strip()
```

文本类型的内容块直接取 `text` 字段拼接;非文本类型(比如图片、二进制引用)退化成整个内容块的 JSON 序列化字符串——保证不管返回的内容块类型多复杂,最终总能拍平成一段可以放进工具调用结果里的文本。`McpServerNotConnectedError` 是这一层唯一对外暴露的异常类型,不管底层是"会话压根没建立"还是"调用过程中抛出了协议异常",上层(`tools/mcp_tool.py`)只需要捕获这一种异常类型就能统一处理。

### `McpToolAdapter`:把一个远端工具伪装成本地 `BaseTool`

```python
# src/openharness/tools/mcp_tool.py
class McpToolAdapter(BaseTool):
    """Expose one MCP tool as a normal OpenHarness tool."""

    def __init__(self, manager: McpClientManager, tool_info: McpToolInfo) -> None:
        self._manager = manager
        self._tool_info = tool_info
        server_segment = _sanitize_tool_segment(tool_info.server_name)
        tool_segment = _sanitize_tool_segment(tool_info.name)
        self.name = f"mcp__{server_segment}__{tool_segment}"
        self.description = tool_info.description or f"MCP tool {tool_info.name}"
        self.input_model = _input_model_from_schema(self.name, tool_info.input_schema)

    async def execute(self, arguments: BaseModel, context: ToolExecutionContext) -> ToolResult:
        del context
        try:
            output = await self._manager.call_tool(
                self._tool_info.server_name, self._tool_info.name,
                arguments.model_dump(mode="json", exclude_none=True),
            )
        except McpServerNotConnectedError as exc:
            return ToolResult(output=str(exc), is_error=True)
        return ToolResult(output=output)
```

`mcp__{server}__{tool}` 这个双下划线拼接的命名和 Claude Code 暴露 MCP 工具的命名规则完全一致(第一篇已经提过这一点),这里补充命名清洗的细节:

```python
# src/openharness/tools/mcp_tool.py(节选)
def _sanitize_tool_segment(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", value)
    if not sanitized:
        return "tool"
    if not sanitized[0].isalpha():
        return f"mcp_{sanitized}"
    return sanitized
```

MCP 服务器名和工具名是外部输入,不受 OpenHarness 控制,可能包含空格、点号、Unicode 字符等 Anthropic Messages API 工具名规范不允许的字符——`_sanitize_tool_segment()` 把所有非字母数字下划线连字符的字符替换成下划线,并且如果清洗后的结果不是以字母开头(比如原始名字是纯数字或以连字符开头),额外加上 `mcp_` 前缀保证生成的工具名始终是一个合法标识符。

输入 schema 的转换同样值得注意——MCP 工具返回的是标准 JSON Schema,而 OpenHarness 的工具协议要求一个 Pydantic 模型,`_input_model_from_schema()` 用 `pydantic.create_model` 动态构造:

```python
# src/openharness/tools/mcp_tool.py(节选)
def _input_model_from_schema(tool_name: str, schema: dict[str, object]) -> type[BaseModel]:
    properties = schema.get("properties", {})
    ...
    fields = {}
    required = set(schema.get("required", []))
    for key in properties:
        prop = properties[key] if isinstance(properties[key], dict) else {}
        py_type = _JSON_TYPE_MAP.get(str(prop.get("type", "")), object)
        if key in required:
            fields[key] = (py_type, Field(default=...))
        else:
            fields[key] = (py_type | None, Field(default=None))
    return create_model(f"{tool_name.title().replace('-', '_')}Input", **fields)
```

这是一次"逆向"转换:第一篇讲到 `BaseTool.to_api_schema()` 是把 Pydantic 模型正向转换成 JSON Schema 供 Anthropic API 使用;这里则是把 MCP 服务器提供的 JSON Schema 反向转换成一个动态生成的 Pydantic 模型,好让 `McpToolAdapter` 能够复用和内置工具完全相同的 `input_model.model_validate()` 校验路径——这个双向转换是让 MCP 工具和内置工具能在同一套工具执行框架(`engine/query.py._execute_tool_call()`)里被无差别处理的关键。`_JSON_TYPE_MAP` 只覆盖了 JSON Schema 的六种基础类型(`string`/`integer`/`number`/`boolean`/`array`/`object`),未知类型统一退化成 Python 的 `object`,是一种"能转就转、转不了就放宽"的宽容策略,避免因为一个字段类型识别失败就导致整个工具无法注册。

### 资源工具与认证工具

`list_mcp_resources_tool.py` 和 `read_mcp_resource_tool.py` 是围绕 MCP 资源(Resource,与工具 Tool 并列的另一类 MCP 能力,通常代表可被读取的只读内容,比如一份文档或一个数据集)的两个独立工具,而不是把资源也伪装成工具动态注册——这是一个有意思的设计取舍:工具(Tool)因为数量可能很多、每个都有独立的输入 schema,适合各自变成一个独立的 `McpToolAdapter`;资源(Resource)访问模式更统一(总是"给定 server + uri,读出内容"),所以只用两个固定工具(`list_mcp_resources`/`read_mcp_resource`)覆盖所有服务器的所有资源,不需要为每个资源单独生成一个工具。

`mcp_auth_tool.py` 负责在运行时更新某个已配置 MCP 服务器的认证信息并触发重连:

```python
# src/openharness/tools/mcp_auth_tool.py(节选)
settings.mcp_servers[arguments.server_name] = updated
save_settings(settings)

if mcp_manager is not None:
    try:
        mcp_manager.update_server_config(arguments.server_name, updated)
        await mcp_manager.reconnect_all()
    except Exception as exc:
        return ToolResult(output=f"Saved MCP auth for {arguments.server_name}, but reconnect failed: {exc}", is_error=True)
```

注意这里的顺序:先把更新后的配置持久化到 settings(不管重连成不成功,认证信息都会被保存下来),再尝试用新配置重连。`McpClientManager.reconnect_all()` 的实现是"先 `close()` 掉所有现有连接,再重置所有状态为 `pending`,再重新 `connect_all()`"——也就是说更新一个服务器的认证信息会导致**所有**已连接的 MCP 服务器全部断开重连,而不是只重连被改动的那一个。这是一处值得留意的粒度取舍:实现简单(不需要维护"哪个连接对应哪份配置"的增量 diff 逻辑),代价是修改一个服务器的认证会短暂影响其他服务器的可用性。

### 配置合并:settings 与插件的 MCP 服务器汇总到同一份运行时配置

```python
# src/openharness/mcp/config.py
def load_mcp_server_configs(settings, plugins: list[LoadedPlugin]) -> dict[str, object]:
    """Merge settings and plugin MCP server configs."""
    servers = dict(settings.mcp_servers)
    for plugin in plugins:
        if not plugin.enabled:
            continue
        for name, config in plugin.mcp_servers.items():
            servers.setdefault(f"{plugin.manifest.name}:{name}", config)
    return servers
```

用户在 settings 里通过 `oh mcp add` 显式配置的服务器优先——插件携带的同名服务器会被加上 `<插件名>:<服务器名>` 的命名空间前缀(`setdefault` 意味着如果这个带命名空间的 key 已经存在也不会覆盖),这样即便两个不同插件都携带了一个叫 `github` 的 MCP 服务器配置,也不会互相冲突或悄悄覆盖用户自己配置的同名服务器。`ui/runtime.py` 启动时的调用顺序印证了整条链路的组装方式:

```python
# src/openharness/ui/runtime.py(节选)
mcp_manager = McpClientManager(load_mcp_server_configs(settings, plugins))
await mcp_manager.connect_all()
```

先合并配置,再一次性构造 `McpClientManager` 并发起所有连接——这一步完成之后,`create_default_tool_registry(mcp_manager)`(第一篇讲过)才会把已连接服务器暴露的工具逐个包装注册进最终的工具表。

## 常见问题/易踩坑

**Q:一个 MCP 服务器连接失败会不会导致 Agent 启动不起来?**

不会。`connect_all()` 对每个服务器的连接过程都用独立的 `try/except` 包裹,失败的服务器只是状态被记成 `failed` 并附带 detail 说明原因,不会向上抛出异常。可以用 `oh mcp list` 或会话内的 `/mcp` 命令查看每个服务器的连接状态和失败详情。

**Q:修改一个 MCP 服务器的认证信息之后,其他服务器的连接会受影响吗?**

会短暂受影响。`mcp_auth` 工具触发的是 `reconnect_all()`,这个方法会先关闭全部已建立的会话再统一重新连接,不是只重连被改动的那一个服务器——如果同时配置了多个 MCP 服务器,更新其中一个的认证信息会让所有服务器经历一次"断开再重连"。

## 小结

OpenHarness 只实现了 MCP Client 这一侧,把外部服务器暴露的工具和资源接入自己的工具调用循环——`McpClientManager` 负责连接生命周期(stdio/http 两种传输,ws 声明了但未实现;单个服务器失败不影响整体启动),`McpToolAdapter` 负责把远端工具伪装成本地 `BaseTool`(`mcp__server__tool` 命名对齐 Claude Code 约定,JSON Schema 反向转换成 Pydantic 模型),`list_mcp_resources`/`read_mcp_resource`/`mcp_auth` 三个固定工具分别覆盖资源发现、资源读取、运行时认证更新。settings 和插件携带的 MCP 服务器配置会在启动时合并成一份统一的运行时配置,插件配置默认让位给用户显式配置,避免命名冲突。至此,工具、技能、插件、MCP 这四条扩展路径已经全部讲完,它们最终都汇入同一个 `ToolRegistry` 和同一份系统提示词。下一篇要讲的 Hooks 机制是另一个维度的扩展点——不是"增加模型能调用什么",而是"在模型调用工具前后、会话生命周期的关键节点上,注入确定性或模型驱动的行为校验"。
