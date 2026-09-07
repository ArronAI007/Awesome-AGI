# Plugins 插件系统

> `plugins/loader.py` 里 `_load_plugin_skills()` 的文档字符串写着"Load plugin skills using Claude Code's directory SKILL.md layout"——这不是孤例。`_find_manifest()` 同时认 `plugin.json` 和 `.claude-plugin/plugin.json` 两个路径,`_load_plugin_hooks_structured()` 会把命令模板里的 `${CLAUDE_PLUGIN_ROOT}` 占位符替换成插件的真实安装路径,agent frontmatter 支持的字段(`disallowedTools`、`argumentHint`、`permissionMode`、`maxTurns`)全是驼峰命名——这正是 Claude Code 插件规范的命名习惯,而不是 OpenHarness 其余代码里更常见的 snake_case。README 说"Tested with 12 official plugins",本篇要做的是把这份兼容性一条条对到代码上,同时也如实指出目前还没做到的地方(比如插件安装目前只支持本地路径,还不支持从 URL 拉取)。

## 学习目标

- 理解 `PluginManifest`/`LoadedPlugin` 两个数据结构如何把一个插件目录的产出统一成技能、命令、agent、工具、hooks、MCP 服务器六类内容。
- 读懂插件发现的两级目录(用户级 `~/.openharness/plugins`、项目级 `.openharness/plugins`,后者默认关闭)和 `.claude-plugin/plugin.json` 兼容路径。
- 搞清楚插件的命令(commands)和技能(skills)在加载逻辑上是怎么共用同一套 Markdown + frontmatter 解析,又是怎么在 `is_skill` 标志上分岔的。
- 找到 `${CLAUDE_PLUGIN_ROOT}` 占位符替换、`hooks.json` 两种格式并存这两处具体的 Claude Code 插件规范兼容证据。
- 了解插件安装(`oh plugin install`)当前的真实实现边界,不夸大也不遗漏。

## 背景与设计动机

技能解决的是"领域知识按需加载"的问题,而插件解决的是更大的一层问题——如何把技能、斜杠命令、子 agent 定义、自定义工具、生命周期 hooks、MCP 服务器配置这些原本分散的扩展点,打包成一个可以整体分发、整体启停的单元。一个插件目录本质上是这些扩展点的容器,`plugins/types.py` 里 `LoadedPlugin` 这个 dataclass 的字段列表就是最直接的证据:

```python
# src/openharness/plugins/types.py(节选)
@dataclass(frozen=True)
class LoadedPlugin:
    """A loaded plugin and its contributed artifacts."""

    manifest: PluginManifest
    path: Path
    enabled: bool
    skills: list[SkillDefinition] = field(default_factory=list)
    commands: list[PluginCommandDefinition] = field(default_factory=list)
    agents: list[AgentDefinition] = field(default_factory=list)
    tools: list[BaseTool] = field(default_factory=list)
    hooks: dict[str, list] = field(default_factory=dict)
    mcp_servers: dict[str, McpServerConfig] = field(default_factory=dict)
```

六个字段对应六种扩展能力,`skills` 会被并入 `SkillRegistry`(上一篇讲过)、`hooks` 会被并入 `HookRegistry`(下一篇讲)、`mcp_servers` 会和 settings 里配置的 MCP 服务器合并(下下篇讲)。OpenHarness 选择让插件系统直接复用 Claude Code 的插件目录规范,而不是发明一套自己的格式——这个选择的价值主张和技能系统一致:README 列出的"12 个官方插件"(`commit-commands`、`security-guidance`、`hookify`、`feature-dev`、`code-review`、`pr-review-toolkit` 等)不需要任何改造就能被 OpenHarness 加载。

## 核心机制详解

### Manifest 发现:两个候选路径

```python
# src/openharness/plugins/loader.py(节选)
def _find_manifest(plugin_dir: Path) -> Path | None:
    """Find plugin.json in standard or .claude-plugin/ locations."""
    for candidate in [
        plugin_dir / "plugin.json",
        plugin_dir / ".claude-plugin" / "plugin.json",
    ]:
        if candidate.exists():
            return candidate
    return None
```

一个插件目录只要满足其中一个路径存在 `plugin.json` 就会被识别为合法插件——`.claude-plugin/plugin.json` 正是 Claude Code 插件仓库里标准的清单文件位置。`PluginManifest`(`plugins/schemas.py`)本身是一个宽松的 Pydantic 模型:

```python
# src/openharness/plugins/schemas.py
class PluginManifest(BaseModel):
    """Plugin manifest stored in plugin.json or .claude-plugin/plugin.json."""

    name: str
    version: str = "0.0.0"
    description: str = ""
    enabled_by_default: bool = True
    skills_dir: str = "skills"
    tools_dir: str = "tools"
    hooks_file: str = "hooks.json"
    mcp_file: str = "mcp.json"
    # Extended fields: optional author, commands, agents, etc.
    author: dict | None = None
    commands: str | list | dict | None = None
    agents: str | list | None = None
    skills: str | list | None = None
    hooks: str | dict | list | None = None
```

`commands`/`agents`/`hooks` 这几个字段的类型是 `str | list | dict`——可以是一个指向目录的相对路径字符串,可以是多个路径的列表,也可以是一份内联的字典(每个命令名映射到一份包含 `source`/`content`/`description` 等键的元数据)。这种"接受多种形状"的设计换来的是对不同插件作者习惯的兼容:有人喜欢把命令都放进 `commands/` 目录让加载器自动扫描,有人喜欢在 `plugin.json` 里直接内联命令内容,两种写法都能被同一个 `_load_plugin_commands()` 处理。

### 插件发现的两级目录与信任边界

```python
# src/openharness/plugins/loader.py(节选)
def discover_plugin_paths_for_settings(settings, cwd, extra_roots=None) -> list[Path]:
    roots = [get_user_plugins_dir()]
    if getattr(settings, "allow_project_plugins", False):
        roots.append(get_project_plugins_dir(cwd))
    ...
```

注意 `allow_project_plugins` 的默认值是 `False`——和上一篇 `allow_project_skills` 默认 `True` 形成对比。插件比技能能做的事情更多(插件可以携带可执行的 `tools/*.py`,技能只是纯文本),所以项目级插件默认不加载,需要用户显式信任某个工作区之后才开启。`load_plugins()` 里还专门有一段逻辑:即便 `allow_project_plugins` 是关闭状态,只要检测到项目目录下确实放了带 `plugin.json` 的插件,也会打印一条警告提醒用户"这些插件存在但被默认禁用了",而不是静默忽略——这是一种"看得见但不生效"的透明化处理,比完全沉默的拒绝更利于用户发现自己是不是漏配置了什么。

### 技能与命令共用同一套 Markdown 加载逻辑

`_load_plugin_skills()` 的实现和上一篇讲的 `load_skills_from_dirs()` 几乎是同一套代码(都调用 `skills.loader._parse_skill_metadata`),差别只是数据来源从独立的技能目录变成了插件目录下的 `manifest.skills_dir` 子目录,`source` 字段固定标记为 `"plugin"`。真正有意思的是命令加载器如何处理"目录里混杂着技能风格的 `SKILL.md` 和普通命令风格的 `.md` 文件"这种情况:

```python
# src/openharness/plugins/loader.py(节选)
def _transform_command_files(files: list[Path]) -> list[Path]:
    files_by_dir: dict[Path, list[Path]] = {}
    for file_path in files:
        files_by_dir.setdefault(file_path.parent, []).append(file_path)
    result: list[Path] = []
    for dir_path, dir_files in files_by_dir.items():
        skill_files = [path for path in dir_files if path.name.lower() == "skill.md"]
        if skill_files:
            result.append(skill_files[0])
        else:
            result.extend(sorted(dir_files))
    return sorted(result)
```

如果同一个目录下存在 `SKILL.md`,就只把这一份当作命令来源(忽略同目录下其他 `.md` 文件),因为 `SKILL.md` 本身已经是一份完整的、自带 frontmatter 的技能定义;`_walk_plugin_markdown()` 在遍历时一旦发现 `SKILL.md` 也会立刻停止继续下钻子目录(`dirnames[:] = []`)。这意味着一个插件的 `commands/` 目录既可以放传统的"一个命令一个 `.md` 文件",也可以放"一个技能子目录 + `SKILL.md`"的结构,加载器会自动识别并统一转换成 `PluginCommandDefinition`(带 `is_skill=True` 标记),两种写法在下游(斜杠命令列表)看起来是等价的。

命令文件本身的 frontmatter 字段同样是对齐 Claude Code 斜杠命令规范的:

```python
# src/openharness/plugins/loader.py(节选,_load_single_command_file)
argument_hint = frontmatter.get("argument-hint")
...
disable_model_invocation = bool(frontmatter.get("disable-model-invocation", False))
user_invocable_raw = frontmatter.get("user-invocable")
```

`argument-hint`(斜杠命令的参数提示,比如 `/deploy <env>` 里的 `<env>`)、`disable-model-invocation`、`user-invocable` 这几个 kebab-case 字段名和技能系统的 frontmatter 字段是同一套命名,命令和技能在概念上本就是"可选带斜杠触发"和"可选禁止模型调用"的同一类可调用单元,只是命令没有强制要求目录布局。

### Agent frontmatter:一份和 Claude Code 子智能体定义高度对齐的字段表

`_load_single_agent_file()` 解析的 frontmatter 字段列表是插件系统里信息量最大的一段代码:

```python
# src/openharness/plugins/loader.py(节选)
disallowed_raw = frontmatter.get("disallowedTools", frontmatter.get("disallowed_tools"))
...
max_turns_raw = frontmatter.get("maxTurns", frontmatter.get("max_turns"))
...
permission_raw = frontmatter.get("permissionMode", frontmatter.get("permission_mode"))
...
initial_prompt_raw = frontmatter.get("initialPrompt", frontmatter.get("initial_prompt"))
...
critical_raw = frontmatter.get("criticalSystemReminder", frontmatter.get("critical_system_reminder"))
...
required_mcp_servers = _parse_str_list(
    frontmatter.get("requiredMcpServers", frontmatter.get("required_mcp_servers"))
)
```

每一个字段都同时兼容驼峰命名(`disallowedTools`、`maxTurns`、`permissionMode`、`initialPrompt`、`criticalSystemReminder`、`requiredMcpServers`)和 snake_case 命名(`disallowed_tools`、`max_turns` 等),`frontmatter.get(camelCase, frontmatter.get(snake_case))` 这种"先试驼峰、再退化到下划线"的写法,直接说明了驼峰命名才是被优先对齐的目标格式——这正是 Claude Code 子 agent 定义文件里使用的字段命名习惯(JSON/YAML 配置在 Claude Code 生态里普遍用驼峰),而 snake_case 分支更像是给 Python 生态用户准备的备选写法。这份字段表覆盖了工具白名单/黑名单、模型覆盖、推理强度(`effort`)、权限模式、最大轮次、技能依赖、颜色标记、记忆作用域、隔离模式、初始提示词、关键系统提醒、所需 MCP 服务器、精细权限列表——几乎是把 Claude Code 子 agent 定义的表达能力完整搬了过来。

### Hooks:两种 JSON 格式与 `${CLAUDE_PLUGIN_ROOT}` 占位符替换

插件的 hooks 配置支持两种文件布局,加载器按顺序尝试:

```python
# src/openharness/plugins/loader.py(节选,load_plugin 内)
hooks = _load_plugin_hooks(path / manifest.hooks_file)
hooks_dir_file = path / "hooks" / "hooks.json"
if not hooks and hooks_dir_file.exists():
    hooks = _load_plugin_hooks_structured(hooks_dir_file, path)
```

第一种是"扁平格式"——`hooks.json` 顶层直接是 `{事件名: [hook 定义, ...]}`,每个 hook 定义直接用 `CommandHookDefinition`/`PromptHookDefinition`/`HttpHookDefinition`/`AgentHookDefinition`(下一篇细讲这四种类型)校验。第二种是"结构化格式"(`hooks/hooks.json`),数据结构多包一层 `matcher` + `hooks` 列表,并且专门处理了路径占位符:

```python
# src/openharness/plugins/loader.py(节选,_load_plugin_hooks_structured)
cmd = hook.get("command", "")
cmd = cmd.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root))
```

`${CLAUDE_PLUGIN_ROOT}` 是 Claude Code 插件 hooks 配置里用来引用"插件自身安装目录"的标准占位符——一个插件的 hook 命令可能需要执行插件自带的一个脚本(比如 `${CLAUDE_PLUGIN_ROOT}/scripts/check.sh`),但插件安装到用户机器上的绝对路径在打包时是未知的,只能在加载时才能确定,所以用占位符延迟到运行时替换。OpenHarness 在这里做的是逐字节兼容 Claude Code 的占位符语法,而不是要求插件作者改用 OpenHarness 自己的变量语法。

### MCP 配置与 `.mcp.json` 兼容

```python
# src/openharness/plugins/loader.py(节选)
mcp = _load_plugin_mcp(path / manifest.mcp_file)
mcp_json = path / ".mcp.json"
if not mcp and mcp_json.exists():
    mcp = _load_plugin_mcp(mcp_json)
```

同样是"标准位置优先,兼容位置兜底"的模式——`manifest.mcp_file` 默认是 `mcp.json`,如果没找到再尝试 `.mcp.json`(带前导点,这是 Claude Code/Claude Desktop 项目级 MCP 配置文件的惯用文件名)。`_load_plugin_mcp()` 内部用 `McpJsonConfig` 这个 Pydantic 模型解析,顶层键是 `mcpServers`——这个键名同样是 Claude 生态里 MCP 配置文件的标准约定,第四篇会细讲 `McpServerConfig` 的三种传输类型。

### 插件也能携带原生 Python 工具:超出规范兼容之外的扩展

```python
# src/openharness/plugins/loader.py(节选)
def _load_plugin_tools(path: Path, manifest: PluginManifest) -> list:
    """Discover and instantiate BaseTool subclasses from a plugin's tools/ directory."""
    tools_dir = path / manifest.tools_dir
    ...
    for py_file in sorted(tools_dir.glob("*.py")):
        ...
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        for attr_name in dir(module):
            attr = getattr(module, attr_name, None)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseTool)
                and attr is not BaseTool
                and hasattr(attr, "name")
                and hasattr(attr, "description")
            ):
                instance = attr()
                tools.append(instance)
    return tools
```

这一段是 OpenHarness 插件系统里明显超出"复刻 Claude Code 插件规范"范围的部分——Claude Code 的插件通常只包含 Markdown(技能、命令、agent)和 JSON(hooks、MCP 配置)这类声明式内容,不携带可执行代码;而 OpenHarness 允许插件在 `tools/` 目录下直接放置 Python 源文件,加载器用 `importlib.util.spec_from_file_location` 动态导入模块,反射遍历模块里所有 `BaseTool` 子类并实例化注册。这是一处"照搬规范之外的原生扩展点"——因为 OpenHarness 本身就是 Python 实现,让插件也能用同样的语言直接扩展工具能力,比强迫所有扩展都通过声明式配置表达更灵活,代价是这类插件工具的信任要求比纯 Markdown/JSON 插件高得多(执行的是任意 Python 代码),这也是为什么项目级插件默认关闭(`allow_project_plugins=False`)在这里显得尤为必要。

### 安装与卸载:目前只是本地目录复制

```python
# src/openharness/plugins/installer.py
def install_plugin_from_path(source: str | Path) -> Path:
    """Install a plugin directory into the user plugin directory."""
    src = Path(source).resolve()
    dest = get_user_plugins_dir() / src.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest
```

`oh plugin install <source>` 的 CLI 帮助文本写的是 "Plugin source (path or URL)",但 `install_plugin_from_path()` 的实现只是 `Path(source).resolve()` 加 `shutil.copytree`——目前只处理本地文件系统路径,并没有实现从 Git URL 克隆或从远程下载归档的逻辑。这是一处如实指出的现状:帮助文本描述的能力(URL 安装)和当前代码实现之间存在差距,使用者如果传入一个 URL,`Path(source)` 会把它当成一个不存在的本地路径处理,最终在 `src.name`/`copytree` 阶段失败。卸载逻辑(`uninstall_plugin`)则额外做了一层路径安全校验(`_resolve_user_plugin_dir`),确保传入的插件名解析后仍然是用户插件目录的直接子目录,防止路径穿越删到目录之外的文件。

## 常见问题/易踩坑

**Q:插件目录下的 `SKILL.md` 会同时出现在技能列表和命令列表里吗?**

会分别出现,但代表的是同一份内容的两种视图。`_load_plugin_skills()` 会把它注册成一个 `SkillDefinition`(供 `skill` 工具和系统提示词的技能小节使用),同时 `_load_plugin_commands()` 在扫描 `commands/` 目录时如果遇到同一份 `SKILL.md`,会把它转换成一个 `PluginCommandDefinition`(`is_skill=True`,供斜杠命令查找使用)。两者读取的是同一个文件,只是服务于两条不同的调用路径(模型主动调用 `skill` 工具 vs. 用户输入 `/skill-name`)。

**Q:如果 `plugin.json` 里同时有 `commands` 字段的内联字典和 `commands/` 目录,两者会冲突吗?**

不会互相覆盖,而是两者的结果都会被加入最终的命令列表——`_load_plugin_commands()` 先无条件扫描 `path / "commands"` 目录,再额外处理 `manifest.commands` 字段(如果是字典就逐项加载,如果是路径列表就作为额外目录/文件加载)。`seen` 集合会防止同一个文件路径被重复加载两次,但目录扫描和 manifest 内联配置本身是两条独立执行的加载路径。

## 小结

OpenHarness 的插件系统把技能、命令、agent、工具、hooks、MCP 服务器六类扩展内容统一打包进一个插件目录,manifest 发现路径(`plugin.json` 或 `.claude-plugin/plugin.json`)、agent frontmatter 的驼峰字段命名、hooks 的 `${CLAUDE_PLUGIN_ROOT}` 占位符替换、MCP 配置的 `mcpServers`/`.mcp.json` 约定,每一处都能在源码里找到与 Claude Code 插件规范逐条对应的证据——这不是"参考了类似的思路",而是刻意的逐字节兼容。与此同时,插件可以携带原生 Python 工具这一点,是 OpenHarness 在规范兼容之外做的原生扩展,也解释了为什么项目级插件默认关闭:声明式的 Markdown/JSON 插件相对安全,可执行代码插件的信任门槛必须更高。插件安装目前只支持本地路径复制,还没有实现 URL/Git 安装,这是一处如实存在的能力缺口而非设计选择。下一篇会转向插件能携带的另一类内容——MCP 服务器配置,看 OpenHarness 作为 MCP Client 是怎么把外部工具接入自己的工具调用循环的。
