# Skills 机制:Markdown 技能与按需加载

> README 里说 OpenHarness "Compatible with anthropics/skills",这句话不是"我们也支持 Markdown 技能"这种笼统的自我宣称——`skills/loader.py` 里 `_load_plugin_skills()` 的函数文档字符串直接写着"Load plugin skills using Claude Code's directory SKILL.md layout",目录布局、YAML frontmatter 字段名(`name`/`description`)都和 Anthropic 公开的技能规范逐字对应。更值得深挖的是"按需加载"这四个字到底是怎么落地的:是不是真的只把技能名字和一句话描述塞进系统提示词,技能正文要等模型主动调用 `skill` 工具才会被读进来?本篇会把这个假设摆到代码面前逐条验证。

## 学习目标

- 读懂 `SkillDefinition` 这个数据模型的字段构成,理解 `disable_model_invocation`/`user_invocable`/`command_name` 这几个标志各自控制什么。
- 搞清楚一份 `SKILL.md` 从磁盘上的文件到进入系统提示词、再到被模型实际读取正文,要经过哪几层加载与过滤。
- 用代码验证"技能按需加载"这个说法:系统提示词里到底注入了什么,技能正文什么时候才真正进入上下文。
- 理解技能的发现顺序(bundled → user → project → plugin)以及为什么这个顺序本身就是一种"信任优先级"的体现。
- 找到 `_frontmatter.py` 里和 `anthropics/skills` 规范直接对应的证据。

## 背景与设计动机

一个 Agent Harness 如果把所有"领域知识"(怎么写 commit message、怎么调试、怎么做代码评审)都塞进固定的系统提示词,会带来两个问题:提示词会随着知识点增多而线性膨胀,消耗大量上下文预算;而且大部分知识点在大多数会话里根本用不上。Skills 机制要解决的正是这个问题——把"提示词内容"变成"按需检索的外部知识",模型在系统提示词里只看到一份精简的目录(技能名 + 一句话描述),真正需要某项技能时才主动去"读"它的正文。

这套思路本身不是 OpenHarness 发明的——Anthropic 自己在 `anthropics/skills` 仓库和 Claude Code 里推广的正是这一套 `SKILL.md` 目录格式。OpenHarness 选择直接复用这套格式而不是自造一套,换来的好处是双向的:一方面 `anthropics/skills` 仓库里现成的技能(README 提到的 `pdf`、`xlsx` 等)可以不经改动直接放进 OpenHarness 的技能目录使用;另一方面,任何为 OpenHarness 写的技能理论上也能被兼容这套格式的其他工具直接复用。

## 核心机制详解

### `SkillDefinition`:一份技能的完整字段

```python
# src/openharness/skills/types.py
@dataclass(frozen=True)
class SkillDefinition:
    """A loaded skill."""

    name: str
    description: str
    content: str
    source: str
    path: str | None = None
    base_dir: str | None = None
    command_name: str | None = None
    display_name: str | None = None
    aliases: tuple[str, ...] = ()
    user_invocable: bool = True
    disable_model_invocation: bool = False
    model: str | None = None
    argument_hint: str | None = None
```

值得注意的是 `content` 字段——它存的是整份 `SKILL.md` 的**全文**,在加载阶段就已经读进了内存。这意味着"按需加载"不是指"技能正文延迟到磁盘 I/O"(所有技能在启动时就已经被读入了 `SkillDefinition.content`),而是指"技能正文延迟到进入模型的上下文窗口"——这个区别很关键,后面会看到系统提示词组装阶段只用到了 `name`/`description`,`content` 要等 `skill` 工具被调用时才会被取出来发给模型。`disable_model_invocation` 和 `user_invocable` 是一对独立的开关:前者控制"模型能不能主动调用这个技能",后者控制"用户能不能把它当斜杠命令直接跑"(`command_name` 就是这个斜杠命令的名字,例如 `/deploy`)。

### 发现顺序:bundled → user → project → plugin

```python
# src/openharness/skills/loader.py(节选)
def load_skill_registry(
    cwd: str | Path | None = None,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    settings=None,
) -> SkillRegistry:
    """Load bundled, user-defined, project, and plugin skills."""
    registry = SkillRegistry()
    for skill in get_bundled_skills():
        registry.register(skill)
    for skill in load_user_skills():
        registry.register(skill)
    for skill in load_skills_from_dirs(extra_skill_dirs, source="user"):
        registry.register(skill)

    resolved_settings = settings or load_settings()
    if cwd is not None and getattr(resolved_settings, "allow_project_skills", True):
        project_dirs = discover_project_skill_dirs(
            cwd,
            getattr(resolved_settings, "project_skill_dirs", list(_DEFAULT_PROJECT_SKILL_DIRS)),
        )
        for skill in load_skills_from_dirs(project_dirs, source="project", create_missing=False):
            registry.register(skill)

    if cwd is not None:
        from openharness.plugins.loader import load_plugins

        for plugin in load_plugins(resolved_settings, cwd, extra_roots=extra_plugin_roots):
            if not plugin.enabled:
                continue
            for skill in plugin.skills:
                registry.register(skill)
    return registry
```

四批技能按固定顺序依次注册进同一个 `SkillRegistry`,后注册的会覆盖先注册的同名技能(`SkillRegistry.register()` 直接用 `self._skills[key] = skill` 覆写)。这个顺序本身是一种隐含的优先级设计:内置技能(`bundled`,随包分发,最值得信任)最先注册、最容易被覆盖;项目级技能(`project`,可能来自一个刚 clone 下来、还没审查过的仓库)最后注册、能覆盖前面所有同名技能。`allow_project_skills` 这个 settings 开关默认是 `True`,但可以显式关闭——README 里给出的场景是"面对不受信任的仓库时关闭项目级技能加载",因为一份恶意的 `SKILL.md` 本质上就是一段会被喂给模型当作指令的文本,项目级技能天然比用户自己维护的技能更容易被攻击者利用。

`discover_project_skill_dirs()` 的实现值得单独看一眼:

```python
# src/openharness/skills/loader.py(节选)
levels: list[Path] = []
while True:
    levels.append(current)
    if git_root is not None and current == git_root:
        break
    ...
    current = parent

roots: list[Path] = []
for base in reversed(levels):
    for rel in relative_dirs:
        candidate = (base / rel).resolve()
        if candidate in seen or not candidate.is_dir():
            continue
        roots.append(candidate)
return roots
```

它从当前工作目录一路向上收集到 Git 根目录为止的每一层目录,然后**反转顺序**(`reversed(levels)`)——从最不具体(仓库根)到最具体(当前 cwd)依次加入候选列表。配合前面"后注册覆盖先注册"的规则,结果就是:离当前工作目录越近的 `SKILL.md`,优先级越高,可以覆盖仓库根目录或更上层目录里同名的技能。这是一种符合直觉的"就近覆盖"语义,和大多数配置系统(比如 `.gitignore`、`.eslintrc`)的层叠规则是同一套思路。

### frontmatter 解析:与 `anthropics/skills` 的直接对应

```python
# src/openharness/skills/_frontmatter.py(节选)
def parse_skill_metadata(
    default_name: str,
    content: str,
    *,
    fallback_template: str = "Skill: {name}",
) -> dict[str, Any]:
    ...
    if content.startswith("---\n"):
        end_index = content.find("\n---\n", 4)
        if end_index != -1:
            try:
                metadata = yaml.safe_load(content[4:end_index])
                if isinstance(metadata, dict):
                    frontmatter = metadata
                    val = metadata.get("name")
                    if isinstance(val, str) and val.strip():
                        name = val.strip()
                    val = metadata.get("description")
                    if isinstance(val, str) and val.strip():
                        description = val.strip()
            except yaml.YAMLError:
                logger.debug(...)

    if not description:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                if not name or name == default_name:
                    name = stripped[2:].strip() or default_name
                continue
            if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
                description = stripped[:200]
                break
```

解析逻辑分两层:优先解析 `---` 包裹的 YAML frontmatter,读取 `name`/`description` 两个字段——这正是 `anthropics/skills` 规范里 `SKILL.md` 的标准头部格式。仓库里 `skills/bundled/content/skill-creator.md` 就是一个标准示例:

```yaml
# src/openharness/skills/bundled/content/skill-creator.md(节选)
---
name: skill-creator
description: >
  Create, improve, and verify OpenHarness skills. Use this whenever the user
  asks to create a new skill, convert a workflow into a skill, update an
  existing SKILL.md, add skills for oh/ohmo, design skill trigger behavior,
  or test whether a skill loads and works correctly.
---
```

如果一份技能文件根本没有 frontmatter(比如 `debug.md` 就没有 `---` 头),解析器会退化到一套启发式规则:用第一个 `# 标题` 行当作技能名,用第一段非空、非标题、非分隔符的正文当作描述(截断到 200 字符)。这个双层设计意味着 `anthropics/skills` 里那些严格遵循 frontmatter 规范的技能能被完整解析出 `name`/`description`,而项目里随手写的、没有 frontmatter 的 Markdown 文档也能被"降级"识别成一个可用的技能,不会直接加载失败。`parse_bool_frontmatter()` 还专门处理了 YAML 布尔值的多种写法(`"1"`/`"true"`/`"yes"`/`"on"` 都算真),这是应对"人手写 YAML 时格式不统一"的一处细节容错。

### 验证"按需加载":系统提示词里到底注入了什么

这是本篇要验证的核心假设。系统提示词组装发生在 `prompts/context.py` 的 `_build_skills_section()`:

```python
# src/openharness/prompts/context.py(节选)
def _build_skills_section(
    cwd: str | Path,
    *,
    extra_skill_dirs: Iterable[str | Path] | None = None,
    extra_plugin_roots: Iterable[str | Path] | None = None,
    settings: Settings | None = None,
) -> str | None:
    """Build a system prompt section listing available skills."""
    registry = load_skill_registry(cwd, extra_skill_dirs=extra_skill_dirs, extra_plugin_roots=extra_plugin_roots, settings=settings)
    skills = [skill for skill in registry.list_skills() if not skill.disable_model_invocation]
    if not skills:
        return None
    lines = [
        "# Available Skills",
        "",
        "The following skills are available via the `skill` tool. "
        "When a user's request matches a skill, invoke it with `skill(name=\"<skill_name>\")` "
        "to load detailed instructions before proceeding. "
        "User-invocable skills can also be run directly by the user as `/<skill-name>`.",
        "",
    ]
    for skill in skills:
        command_name = skill.command_name or skill.name
        display = f" ({skill.display_name})" if skill.display_name else ""
        lines.append(f"- **{command_name}**{display}: {skill.description}")
    return "\n".join(lines)
```

这段代码把假设坐实了:循环体里对每个技能只拼了一行 `"- **{command_name}**: {description}"`,**没有出现 `skill.content` 的任何引用**。也就是说不管一份 `SKILL.md` 的正文有多长(`skill-creator.md` 有几十行,某些教学向的技能可能上百行),系统提示词里付出的上下文成本永远只是"名字 + 一句话描述"这一行,不随正文长度变化。提示词文本本身还显式指导模型"匹配到某个技能时,调用 `skill(name="<skill_name>")` 加载详细指令再继续"——这是把"要不要展开读正文"的决策权交给模型自己判断。

正文真正被读取的地方是 `skill_tool.py`:

```python
# src/openharness/tools/skill_tool.py(节选)
async def execute(self, arguments: SkillToolInput, context: ToolExecutionContext) -> ToolResult:
    registry = load_skill_registry(
        context.cwd,
        extra_skill_dirs=context.metadata.get("extra_skill_dirs"),
        extra_plugin_roots=context.metadata.get("extra_plugin_roots"),
    )
    skill = registry.get(arguments.name) or registry.get(arguments.name.lower()) or registry.get(arguments.name.title())
    if skill is None:
        return ToolResult(output=f"Skill not found: {arguments.name}", is_error=True)
    if skill.disable_model_invocation:
        command_name = skill.command_name or skill.name
        return ToolResult(
            output=f"Skill {command_name} can only be invoked by the user as /{command_name}.",
            is_error=True,
        )
    return ToolResult(output=skill.content)
```

只有当模型主动发起一次 `skill` 工具调用,`skill.content`(整份 `SKILL.md` 正文)才会作为这次工具调用的结果被塞进消息历史,进而在下一轮请求里进入模型的上下文窗口。至此,"按需加载"这四个字在代码层面的落地路径就完整对上了:**加载阶段(启动时)技能正文已经读进内存,但只有名字和描述这两行文本进入系统提示词;真正的上下文消耗要等模型主动调用 `skill` 工具那一刻才发生。**

这里还能看到一层双重防护:`disable_model_invocation` 为 `True` 的技能,一是在 `_build_skills_section()` 里被 `if not skill.disable_model_invocation` 直接过滤掉,根本不会出现在系统提示词的技能列表里;二是即便模型不知怎么"猜到"了技能名并尝试调用,`skill_tool.py` 也会在 `execute()` 里二次拒绝并提示"只能由用户以 `/command_name` 方式调用"。两道防线确保了"仅限用户手动触发"的技能不会意外被模型自主触发。

### 多来源注册与别名

```python
# src/openharness/skills/registry.py
def register(self, skill: SkillDefinition) -> None:
    """Register one skill."""
    for key in (skill.name, skill.command_name, skill.display_name, *skill.aliases):
        if key:
            self._skills[key] = skill
```

一个技能会同时以 `name`(frontmatter 里的 `name` 字段或推断出的标题)、`command_name`(目录名/文件名,用作斜杠命令)、`display_name`(当 `name` 和目录名不一致时才有值)、以及任意 `aliases` 这几个 key 注册进同一个字典——`skill_tool.py` 里 `registry.get(arguments.name) or registry.get(arguments.name.lower()) or registry.get(arguments.name.title())` 这种"多次尝试不同大小写"的查找逻辑,说明模型在调用 `skill` 工具时传入的名字大小写可能和 frontmatter 里声明的不完全一致,注册表用多 key 索引加多次查找兜住这种不确定性。`list_skills()` 则按 `(source, path or name)` 去重,确保同一份物理文件不会因为注册了多个 key 而在列表里重复出现。

### 目录布局与跨生态兼容

用户级技能会同时从三个目录加载:

```python
# src/openharness/skills/loader.py
_USER_COMPAT_SKILL_DIRS = (
    (".claude", "skills"),
    (".agents", "skills"),
)
```

也就是 `~/.openharness/skills/`(自己的目录)加上 `~/.claude/skills/` 和 `~/.agents/skills/` 这两个"兼容目录"。项目级同理:`_DEFAULT_PROJECT_SKILL_DIRS = (".openharness/skills", ".agents/skills", ".claude/skills")`。这意味着一个已经在用 Claude Code 并在 `~/.claude/skills/` 下积累了若干自定义技能的用户,换到 OpenHarness 之后不需要迁移任何文件——目录结构原地复用。这正是 README 里"Claude-style plugins and skills stay portable because OpenHarness keeps those formats familiar"这句话的具体所指。

## 常见问题/易踩坑

**Q:一份没有 YAML frontmatter、只有 `# 标题` 的 `SKILL.md` 能正常工作吗?**

可以。仓库自带的 `debug.md` 就是这种写法——`_frontmatter.py` 的降级逻辑会用 `# debug` 这一行提取出 `name="debug"`,再用紧随其后的第一段正文(`"Diagnose and fix bugs systematically."`)截断到 200 字符当作 `description`。代价是这种写法拿不到 `user-invocable`/`disable-model-invocation`/`model`/`argument-hint` 这些只能通过 frontmatter 声明的可选字段,它们都会落到各自的默认值。

**Q:项目根目录和更深子目录都有同名 `SKILL.md`,哪个生效?**

更靠近当前工作目录的那个生效。`discover_project_skill_dirs()` 按"从仓库根到当前目录"的顺序收集候选目录并反转,越具体(离 cwd 越近)的目录越晚注册,而 `SkillRegistry.register()` 是后注册覆盖先注册,所以子目录里的技能会覆盖仓库根目录里的同名技能——这是一种"离当前工作上下文越近优先级越高"的就近覆盖语义。

## 小结

Skills 机制把"领域知识"从固定的系统提示词里剥离出来,变成一份份独立的 `SKILL.md` 文件,加载时全部读入内存但只把"名字 + 一句话描述"注入系统提示词,正文要等模型主动调用 `skill` 工具才会真正进入对话上下文——这个假设在 `prompts/context.py._build_skills_section()`(只拼接 `description`,不拼接 `content`)和 `tools/skill_tool.py`(唯一返回 `skill.content` 的地方)两处代码里都得到了验证。技能的发现顺序(bundled → user → project → plugin,越具体的目录优先级越高)和目录布局(`.claude/skills`、`.agents/skills` 等兼容路径)都是刻意向 `anthropics/skills` 规范对齐的结果。技能只是插件能携带的内容类型之一——`LoadedPlugin` 这个数据结构里,技能和命令、agent 定义、hooks、MCP 服务器配置是并列的字段。下一篇会转向插件系统本身,看 OpenHarness 是怎么把 Claude Code 风格的插件目录(`.claude-plugin/plugin.json`、`${CLAUDE_PLUGIN_ROOT}` 占位符替换)完整对齐的。
