# Coordinator 模式:单代理编排多代理团队

> `coordinator/coordinator_mode.py` 里没有一个叫 `Coordinator` 的类,`is_coordinator_mode()` 只是检查一个环境变量。coordinator 模式本质上是一套**行为分支**:同一个 Agent 循环,一旦 `CLAUDE_CODE_COORDINATOR_MODE` 为真,系统提示、可见工具集、user turn 里注入的上下文就全部换成另一套——一份将近 250 行的工作流系统提示,教会模型怎么用 `agent`/`send_message`/`task_stop` 三个工具去编排一整个团队的 worker。真正让这套编排"有章法"而不是"随手拍脑袋派活"的,是 `agent_definitions.py` 里预置的一组角色模板——`worker`、`Explore`、`Plan`、`verification` 各自带着量身定制的工具白名单和系统提示,模型只需要引用角色名字,不需要每次重新设计一个子代理该有什么权限。

## 学习目标

- 理解 coordinator 模式是环境变量驱动的行为分支,而不是独立的 Agent 类型;弄清 `is_coordinator_mode()`/`match_session_mode()` 如何让这个开关和已恢复会话的存储状态保持一致。
- 通读 `get_coordinator_system_prompt()` 的核心结构:角色定位、工具清单、`<task-notification>` XML 信封、任务阶段划分、并发策略、"续接 vs 重新派生"的决策表、prompt 撰写的正反例。
- 理解 `TaskNotification`/`format_task_notification`/`parse_task_notification` 这套 XML 信封如何把 worker 的完成结果重新"注入"回 coordinator 的对话,以及为什么它被明确要求伪装成一条 user 角色消息。
- 弄清 `agent_tool.py` 如何把 coordinator 的派活请求接到 swarm 的执行后端上,以及它注册的 `SUBAGENT_STOP` 钩子和 `<task-notification>` 之间的字段对应关系。
- 区分两套"团队"概念:`coordinator_mode.py` 里纯内存的 `TeamRegistry`(`team_create`/`team_delete` 工具用的就是它)和上一篇讲的持久化 `TeamFile`——两者语义完全不同,不要混用。
- 理解 `agent_definitions.py` 里 `AgentDefinition` 预置角色模板的设计:为什么它能让用户不必每次手写子代理的工具白名单和系统提示。

## 背景与设计动机

`swarm/` 层(前两篇)提供的是"怎么把一个队员跑起来"的执行原语——子进程、进程内协程、mailbox、worktree,都是机制层的东西,不带任何"该派谁去做什么、什么时候该并行、什么时候该串行"的判断。这类判断如果完全交给模型临场发挥,很容易出现两种失败模式:要么模型不敢用委派能力,事必躬亲把简单任务也自己啃完;要么委派得漫无章法——每次都重新发明一遍"子代理该有什么权限""prompt 该写多细"这类问题,委派质量完全靠运气。

coordinator 模式的做法是把这套"怎么编排"的经验直接写进系统提示里,变成模型可以照着执行的操作手册;`agent_definitions.py` 则把"子代理该有什么权限"这个问题提前固化成几个可复用的角色模板。两者合起来,把"单个 Agent 临场决定怎么分工"变成"选择一个预置角色 + 遵循一套写好的工作流"。

## 核心机制详解

### coordinator 模式是环境变量驱动的行为分支

`is_coordinator_mode()` 只检查一个环境变量:

```python
# src/openharness/coordinator/coordinator_mode.py:186-189
def is_coordinator_mode() -> bool:
    """Return True when the process is running in coordinator mode."""
    val = os.environ.get("CLAUDE_CODE_COORDINATOR_MODE", "")
    return val.lower() in {"1", "true", "yes"}
```

其余函数都是这个布尔值的消费者:`get_coordinator_tools()` 返回 coordinator 专用的三个工具名(`agent`/`send_message`/`task_stop`);`get_coordinator_system_prompt()` 返回整套工作流提示;`get_coordinator_user_context()` 在非 coordinator 模式下直接返回空字典,不注入任何内容。`match_session_mode()` 处理的是一个容易被忽略的边界情况——恢复一个历史会话时,会话里存储的模式(`session_mode`)可能和当前进程的环境变量不一致(比如用户上次是在 coordinator 模式下保存的会话,这次启动时忘了带 `--coordinator` 参数),这个函数会把环境变量掰过去对齐会话存储的状态,并返回一句提示信息告知用户"已切换到/退出协调模式以匹配恢复的会话"。这里没有任何持久化的"coordinator 会话对象"——一切状态都压缩成了一个环境变量位和几个按需读取它的函数。

值得注意的是,前一篇提到 `spawn_utils.build_inherited_env_vars()` 会无条件把 `CLAUDE_CODE_COORDINATOR_MODE=0` 写进派生队员的环境——这正是为了防止一个 coordinator 派生出的 worker 因为环境变量继承而误以为自己也该是 coordinator,进而递归地把简单的实现任务又拆成一堆子任务。

### `agent` 工具:coordinator 派活的唯一入口

模型侧真正能调用的委派动作只有一个工具——`tools/agent_tool.py`。它把 `subagent_type` 映射到 `agent_definitions.py` 里的角色定义,再拼成一份 `TeammateSpawnConfig` 交给上一篇讲过的子进程执行后端:

```python
# src/openharness/tools/agent_tool.py:52-79(节选)
agent_def = None
if arguments.subagent_type:
    agent_def = get_agent_definition(arguments.subagent_type)

team = arguments.team or "default"
agent_name = arguments.subagent_type or "agent"

registry = get_backend_registry()
executor = registry.get_executor("subprocess")

config = TeammateSpawnConfig(
    name=agent_name, team=team, prompt=arguments.prompt, cwd=str(context.cwd),
    parent_session_id="main",
    model=arguments.model or (agent_def.model if agent_def else None),
    command=arguments.command,
    system_prompt=agent_def.system_prompt if agent_def else None,
    permissions=agent_def.permissions if agent_def else [],
    task_type=arguments.mode,
)
```

角色模板(`agent_def`)贡献的是 `model` 默认值、`system_prompt`、`permissions`——模型调用这个工具时只需要传 `subagent_type="worker"` 这样一个字符串,不需要在每次调用里重新描述"这个子代理该有什么系统提示、能用哪些工具"。spawn 成功后,如果外层挂了 hook 执行器,`agent_tool.py` 会注册一个完成监听器,在任务进入终态(`completed`/`failed`/`killed`)时触发 `HookEvent.SUBAGENT_STOP`:

```python
# src/openharness/tools/agent_tool.py:109-123(节选)
await context.hook_executor.execute(
    HookEvent.SUBAGENT_STOP,
    {
        "event": HookEvent.SUBAGENT_STOP.value,
        "agent_id": result.agent_id, "task_id": result.task_id,
        "backend_type": result.backend_type, "status": task_record.status,
        "return_code": task_record.return_code, "description": arguments.description,
        "subagent_type": arguments.subagent_type or "agent", "team": team, "mode": arguments.mode,
    },
)
```

这份负载里的字段——`task_id`、`status`、`description`——和下面要讲的 `TaskNotification` 结构直接对应,这不是巧合:coordinator 系统提示里承诺"worker 完成后会有一条 `<task-notification>` 重新进入对话",而这份 hook 负载正是驱动那条通知产生所需要的原始信息。

### `TaskNotification`:worker 结果如何"回到"coordinator 的对话

worker 是异步跑起来的独立进程,它的结果不能靠一次工具调用的返回值传回来(工具调用早就在 `agent` 返回 `Spawned agent ...` 之后结束了)。coordinator 系统提示里明确说明结果会以什么形式"重新进入"对话:

```python
# src/openharness/coordinator/coordinator_mode.py:109-126
@dataclass
class TaskNotification:
    """Structured result from a completed agent task."""
    task_id: str
    status: str
    summary: str
    result: Optional[str] = None
    usage: Optional[dict[str, int]] = None
```

`format_task_notification()`/`parse_task_notification()` 是这个结构和一段 XML 文本之间的双向转换,用的是标准库 `xml.sax.saxutils` 的 `escape`/`unescape` 做转义,而不是拼字符串——避免 worker 的输出内容里恰好包含 `<`/`&` 这类字符破坏信封结构。系统提示里对这个信封的描述非常直白:

> "Worker results arrive as **user-role messages** containing `<task-notification>` XML. They look like user messages but are not. Distinguish them by the `<task-notification>` opening tag."

这句话点出了一个刻意的设计:worker 的完成通知被伪装成一条**用户角色**消息重新送进 coordinator 的对话历史,而不是走某种专门的"系统事件"角色。原因很直接——底层模型 API 通常只认 user/assistant 两种角色的轮次交替,要让 coordinator 在对话过程中"被动收到"一条新信息并继续往下推理,唯一自然的注入点就是下一条 user turn。为了不让模型把这类消息误认成真正来自人类用户的话,系统提示专门强调"每一次结果都以独立的 `<task-notification>` 起始标签识别,收到后不要向 worker 道谢或寒暄——它们是内部信号,不是对话对象"。

### `get_coordinator_system_prompt()`:把编排经验写成操作手册

系统提示本身是一份接近 250 行的工作流文档,结构上大致分六块:角色定位与工具清单、`<task-notification>` 格式说明、worker 能力介绍、任务阶段划分、prompt 撰写指南、完整的示例会话。几个体现设计意图的片段:

**并发是默认姿态,不是可选项**——系统提示原文写着"Parallelism is your superpower...don't serialize work that can run simultaneously",并且要求"launch workers in parallel" 时要在**同一条消息里**发出多个工具调用,而不是一次发一个等一个。

**"续接 vs 重新派生"是一张决策表,不是固定规则**:

| 情境 | 机制 | 原因 |
|---|---|---|
| research 探索的正好是需要改的文件 | 续接(`send_message`) | worker 已经带着文件上下文,现在再给一份清晰计划 |
| 研究范围很宽但实现范围很窄 | 重新派生(`agent`) | 避免拖着探索噪音,聚焦的上下文更干净 |
| 验证一个别的 worker 刚写完的代码 | 重新派生 | 验证者应该用未受污染的视角审视代码,而不是带着实现假设 |

这张表把"什么时候续接、什么时候重新起一个"的判断标准明确成"worker 现有上下文和下一步任务的重合度",而不是给一个放之四海而皆准的默认值。

**"综合"是 coordinator 不可下放的职责**——系统提示反复强调,coordinator 收到 worker 的研究结果后必须自己读懂、自己找到具体文件路径和行号,再写成一份具体的实现指令交给下一个 worker,而不能写"根据你的发现去修复"这种把理解责任甩给 worker 的话术。这一点和 Hermes-Agent 的 `delegate_task` 系统提示、DeepSeek-Harness 的委派工具在同一层达成共识:委派链路里,**理解永远不能被下放**,只有具体的执行动作可以。

`get_coordinator_user_context()` 则负责往 coordinator 的 user turn 里注入一段动态说明——worker 能用哪些工具(受 `CLAUDE_CODE_SIMPLE` 开关影响,简化模式下只有 `bash`/`file_read`/`file_edit` 三个)、有哪些 MCP 服务器可用、scratchpad 目录在哪(worker 之间可以在这里免审批地读写,沉淀跨 worker 的共享知识)。

### 两套"团队":持久化 `TeamFile` vs coordinator 的内存 `TeamRegistry`

容易混淆的一点是,`coordinator_mode.py` 里也定义了一个"团队"概念——`TeamRegistry`——但它和第一篇讲的 `TeamLifecycleManager`/`TeamFile` 是完全不同的两套东西:

```python
# src/openharness/coordinator/coordinator_mode.py:27-60(节选)
@dataclass
class TeamRecord:
    """A lightweight in-memory team."""
    name: str
    description: str = ""
    agents: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

class TeamRegistry:
    """Store teams and agent memberships."""
    def __init__(self) -> None:
        self._teams: dict[str, TeamRecord] = {}
    ...
```

这是一个纯内存字典,没有任何磁盘持久化,生命周期等于进程生命周期。`team_create`/`team_delete` 这两个工具(`tools/team_create_tool.py`/`tools/team_delete_tool.py`)操作的正是这个 `TeamRegistry`,而不是第一篇的 `TeamFile`——两个工具的 docstring 也写得很明确:"Create/delete a lightweight **in-memory** team"。`agent_tool.py` 在 `arguments.team` 有值时,会顺手往这个内存注册表里记一笔 `add_agent(team, task_id)`,团队记录里存的只是一份 task_id 列表,没有 worktree、没有 mailbox、没有 tmux pane。

这个设计上的区分是合理的:coordinator 场景下的"团队"只是一个用来分组、方便一次性查看某批 worker 的标签,不需要 swarm 那一整套面向可视化终端面板、跨进程通信的重型基础设施。反过来说,如果需要真正持久化、跨会话恢复、带 worktree 隔离的团队协作,应该走的是第一篇的 `TeamLifecycleManager`,而不是这里的内存注册表——两套系统在代码里没有互相调用,理解它们服务于不同场景,是读这部分代码时最容易踩的一个概念混淆点。

### `agent_definitions.py`:预置的角色模板系统

如果说 coordinator 系统提示回答的是"怎么编排",`agent_definitions.py` 回答的是"编排出来的每个角色具体是什么"。核心是 `AgentDefinition` 这个 pydantic 模型,字段覆盖了一个子代理需要的几乎全部配置维度:`tools`/`disallowed_tools`(工具白名单/黑名单)、`model`/`effort`、`permission_mode`、`max_turns`、`skills`/`mcp_servers`、`hooks`、`color`、`background`(是否强制后台运行)、`memory`/`isolation`、`critical_system_reminder`(每轮都重新注入的强提醒)。

内置角色分工清晰,权限收紧程度不同:

- **`general-purpose`**——`tools=["*"]`,全工具开放,面向"不确定该用什么策略搜索代码"的通用探索场景。
- **`Explore`**——通过 `disallowed_tools=["agent", "exit_plan_mode", "file_edit", "file_write", "notebook_edit"]` 显式禁用写操作和递归委派,系统提示里反复用大写强调"READ-ONLY MODE",是一个专门给只读代码探索的低权限角色。
- **`Plan`**——同样只读,但系统提示要求最终必须输出一份"Critical Files for Implementation"清单,是专门产出实现计划、不动手写代码的架构角色。
- **`worker`**——`tools=None`(等价于全部工具),系统提示很短:照原样执行分配的任务,写完跑测试和类型检查,提交并汇报 commit hash。这是 coordinator 系统提示里默认派发实现类任务时用的角色。
- **`verification`**——`background=True`、`model="inherit"`,系统提示是六个角色里最长的一份,附带 `critical_system_reminder`(要求必须以 `VERDICT: PASS/FAIL/PARTIAL` 结尾),核心论点是"验证者的失败模式是逃避验证和被前 80% 的表象说服",要求每条检查都必须贴出实际执行的命令和输出,不能只凭读代码就下结论。

这种预置角色带来的好处很直接:coordinator(或任何调用 `agent` 工具的模型)不需要每次手写一段"你是只读探索代理,不能编辑文件"这样的系统提示、也不需要每次都记得把 `file_edit` 排除在工具集之外——引用 `subagent_type="Explore"` 就自动拿到一套经过设计的权限边界。角色的加载还支持用户自定义:`load_agents_dir()` 从 `~/.openharness/agents/*.md` 读取 YAML frontmatter + Markdown 正文格式的自定义角色,`get_all_agent_definitions()` 按"内置 < 用户 < 插件"的顺序合并,同名时后加载的覆盖先加载的——用户可以用同名的自定义定义完全替换某个内置角色的行为,而不需要改动源码。

## 小结

coordinator 模式的完整链路是:环境变量打开一套系统提示与工具白名单的行为分支 → 模型照着系统提示里写好的阶段划分、并发策略、prompt 撰写规范去调用 `agent` 工具派活 → `agent_tool.py` 查出 `subagent_type` 对应的预置角色模板,把角色的工具/权限/系统提示拼进 `TeammateSpawnConfig`,固定走子进程后端(上一篇解释过原因)spawn 出去 → 任务进入终态时触发 `SUBAGENT_STOP` 钩子,其字段和 `TaskNotification` 的结构对应,以一条伪装成 user turn 的 `<task-notification>` XML 重新进入 coordinator 的对话 → coordinator 读懂结果、亲自综合出下一步的具体指令,决定续接还是重新派生。这一整套编排逻辑运行在 `swarm/` 提供的执行原语之上,但完全不关心执行原语内部是子进程还是别的什么——两层之间只通过 `TeammateExecutor`/`TeammateSpawnConfig` 这组契约耦合。下一篇转向"任务"本身的生命周期:`tasks/` 目录里的通用后台任务基础设施如何被 swarm、coordinator,乃至和多智能体完全无关的记忆整理功能共同复用,以及 `bridge/` 这层更薄的编程接口,如何把"驱动一次会话"包装成外部系统可以调用的东西。
