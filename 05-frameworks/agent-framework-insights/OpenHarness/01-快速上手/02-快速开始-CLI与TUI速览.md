# 快速开始：CLI 与 TUI 速览

> `oh` 这一个命令背后其实是三种运行形态在共享同一套 Agent 运行时：不传参数是交互式会话，`-p` 是单次查询,`--output-format` 决定这次查询要给人看还是给程序看。理解这三者的分野，比记住具体的命令行参数更重要——它决定了你什么时候该用哪种形态。

## 学习目标

- 分清 `oh`（交互式 TUI）、`oh -p "..."`（非交互单次查询）在源码里各自对应的入口函数。
- 理解 `--output-format text|json|stream-json` 三种输出形态的真实行为差异，而不只是背它们的名字。
- 知道 OpenHarness 事实上有两套 TUI 实现（React/Ink 前端和 Python `textual_app.py`），以及默认交互模式实际走的是哪一条。
- 认识 TUI 里几个关键的斜杠命令（`/model`、`/permissions`、`/resume`、`/provider`）分别做什么。
- 明确这一篇只是速览，双前端架构的细节会留到第 02 章第 2 篇。

## 背景与设计动机

一个 Agent Harness 的 CLI 通常要同时服务两类完全不同的使用场景：人坐在终端前一来一回地对话，和脚本/CI/其他程序把它当一个"黑盒函数"调用。如果只为其中一种场景设计交互协议，另一种场景就会很难受——纯交互式的 CLI 很难被脚本可靠地解析输出，纯批处理式的 CLI 又没法提供流畅的多轮对话体验。

OpenHarness 的解法是让同一个 `main` 回调函数（`src/openharness/cli.py` 里 `@app.callback(invoke_without_command=True)` 装饰的 `main`）根据参数判断走哪条路径，而不是拆成互不相干的多个子命令。这样做的好处是：session、model、permission-mode 这些配置项对三种形态是共享的，用户不需要在"交互模式怎么设置"和"非交互模式怎么设置"之间记两套心智模型。

## 核心机制详解

### 三种运行形态在 `main()` 里的分流

`cli.py` 里 `main()` 函数末尾的分流逻辑，把决策浓缩成几个连续的 `if` 判断（省略了 `--continue`/`--resume` 分支）：

```python
# src/openharness/cli.py
if print_mode is not None:
    prompt = print_mode.strip()
    if not prompt:
        print("Error: -p/--print requires a prompt value, e.g. -p 'your prompt'", file=sys.stderr)
        raise typer.Exit(1)
    asyncio.run(
        run_print_mode(
            prompt=prompt,
            output_format=output_format or "text",
            cwd=cwd,
            model=model,
            ...
        )
    )
    return

if task_worker:
    asyncio.run(run_task_worker(...))
    return

asyncio.run(
    run_repl(
        prompt=None,
        cwd=cwd,
        model=model,
        max_turns=max_turns,
        backend_only=backend_only,
        ...
    )
)
```

`-p`/`--print` 一旦提供了非空的 prompt 值，就直接进入 `run_print_mode`，跑完一次查询就退出——这是脚本、CI、chatbot 后端最常用的形态。`task_worker` 是一个隐藏参数（`hidden=True`），用于给后台子任务提供无 TTY 的 stdin 驱动循环，日常用户不会直接碰到它。什么都不传，走到最后一个分支，进入 `run_repl`——这才是交互式会话的入口。

### `run_repl`：交互式会话默认走的是 React TUI

`src/openharness/ui/app.py` 里的 `run_repl` 函数文档字符串直接写明了它的身份：

```python
# src/openharness/ui/app.py
async def run_repl(
    *,
    prompt: str | None = None,
    cwd: str | None = None,
    ...
    backend_only: bool = False,
    ...
) -> None:
    """Run the default OpenHarness interactive application (React TUI)."""
    if backend_only:
        await run_backend_host(...)
        return

    exit_code = await launch_react_tui(
        prompt=prompt,
        cwd=cwd,
        model=model,
        ...
    )
    if exit_code != 0:
        raise SystemExit(exit_code)
```

也就是说，直接敲 `oh` 进入的交互式会话，默认走的是 `launch_react_tui`——一个基于 Node.js/React 的终端前端，而不是仓库里同样存在的 `src/openharness/ui/textual_app.py`（一个纯 Python、基于 Textual 的实现）。`frontend/terminal/package.json` 里的依赖列表证实了这条前端用的具体技术栈：

```json
// frontend/terminal/package.json
"dependencies": {
  "ink": "^5.1.0",
  "ink-text-input": "^6.0.0",
  "marked": "^18.0.0",
  "react": "^18.3.1",
  "string-width": "^7.2.0"
}
```

`ink` 是社区里用 React 组件模型渲染终端 UI 的库,`frontend/terminal/src/components/` 目录下能看到 `CommandPicker.tsx`、`ConversationView.tsx`、`ToolCallDisplay.tsx`、`StatusBar.tsx` 等一系列真实存在的组件文件。这条前端通过 `oh --backend-only` 拉起的 Python 后端进程做进程间通信（`build_ohmo_backend_command`/`build_ohmo_react_tui` 这类命令拼装逻辑可以在 `ohmo/runtime.py` 里看到同样的模式），Python 侧只负责 Agent 运行时和协议层，渲染完全交给 Node 进程。

这里需要提前说明：为什么会同时存在 Python 版 `textual_app.py` 和 React/Ink 版前端两套实现、它们各自的适用场景和取舍是什么——这是一个足够独立的话题，值得用一整篇去拆，第 02 章第 2 篇会专门展开双前端架构。这一篇只需要记住一个结论：**默认交互路径走的是 React/Ink 前端**。

### `-p` 与三种 `--output-format`

`run_print_mode`（`src/openharness/ui/app.py`）内部按 `output_format` 的值决定同一个事件流该怎么呈现，三种格式对应完全不同的消费方式：

```python
# src/openharness/ui/app.py
async def _render_event(event: StreamEvent) -> None:
    nonlocal collected_text
    if isinstance(event, AssistantTextDelta):
        collected_text += event.text
        if output_format == "text":
            sys.stdout.write(event.text)
            sys.stdout.flush()
        elif output_format == "stream-json":
            obj = {"type": "assistant_delta", "text": event.text}
            print(json.dumps(obj), flush=True)
            events_list.append(obj)
    elif isinstance(event, AssistantTurnComplete):
        ...
    elif isinstance(event, ToolExecutionStarted):
        if output_format == "stream-json":
            obj = {"type": "tool_started", "tool_name": event.tool_name, "tool_input": event.tool_input}
            print(json.dumps(obj), flush=True)
            events_list.append(obj)
    ...
```

三种格式的差异不是"格式不同"这么简单，而是**消费语义完全不同**：

- **`text`**（默认）：把模型生成的文本增量原样写到 `stdout`，其余状态信息（工具调用、compact 进度等）写到 `stderr`。这是给人在终端里直接看的格式，`stdout` 保持干净，方便管道给下一个命令。
- **`stream-json`**：Agent Loop 里每一个内部事件（`assistant_delta`、`assistant_complete`、`tool_started`、`tool_completed`、`error`、`compact_progress`、`status`）都被立刻序列化成一行 JSON 打印出来。这是给需要感知执行过程的程序用的——比如一个聊天机器人网关想要实时把"正在执行某个工具"这个状态转发给用户，就必须消费这个格式,而不是等到最后拿一个完整结果。
- **`json`**：整个查询跑完之后，只打印**一个**汇总对象：

```python
# src/openharness/ui/app.py
if output_format == "json":
    result = {"type": "result", "text": collected_text.strip()}
    print(json.dumps(result))
```

`json` 格式适合那些只关心最终答案、不关心中间过程的脚本调用场景——比如 `oh -p "List all functions in main.py" --output-format json`，取回的就是一个 `{"type": "result", "text": "..."}`，可以直接 `jq '.text'` 取出结果。

三种格式对应三种不同的读者：`text` 给人看，`stream-json` 给需要感知过程的程序看，`json` 给只要结果的程序看。选错格式最常见的后果是：用 `text` 格式写自动化脚本，结果发现 `stdout` 里混进了不该有的提示信息；或者用 `json` 格式想做实时进度展示，结果发现程序卡住不动直到整个查询结束才输出——这不是 bug，是格式语义决定的行为。

### TUI 里的关键交互

`src/openharness/commands/registry.py` 里注册的斜杠命令，本篇只挑几个和"日常起步"强相关的看真实描述：

```python
# src/openharness/commands/registry.py
registry.register(
    SlashCommand(
        "resume",
        "Restore the latest saved session",
        _resume_handler,
        remote_invocable=False,
        remote_admin_opt_in=True,
    )
)
...
registry.register(
    SlashCommand(
        "permissions",
        "Show or update permission mode; Tab in the TUI opens the mode picker",
        _permissions_handler,
        remote_invocable=False,
        remote_admin_opt_in=True,
    )
)
...
registry.register(
    SlashCommand(
        "provider",
        "Show or switch provider profiles",
        _provider_handler,
        remote_invocable=False,
        remote_admin_opt_in=True,
    )
)
registry.register(
    SlashCommand(
        "model",
        "Show, switch, or manage profile models",
        _model_handler,
        remote_invocable=False,
        remote_admin_opt_in=True,
    )
)
```

值得留意的是这四个命令共享同一组标志：`remote_invocable=False` 且 `remote_admin_opt_in=True`。这意味着它们被明确标记为"本地交互专属、远程渠道默认不可调用，管理员需要显式开启才能远程触发"——这类会改变运行时状态（切换 provider、切换模型、切换权限模式）的命令，被有意和"只读查询类"命令区分对待。这个标志组合会在第 05 章讲权限治理时展开，这里先知道它存在即可。

`/permissions` 的描述里还藏着一个 TUI 专属的快捷键提示——"Tab in the TUI opens the mode picker"，也就是说这个功能不仅可以通过 `/permissions` 命令行式地调用，在 React TUI 里按 `Tab` 键也能直接弹出权限模式选择器,这是斜杠命令和快捷键并存的典型例子。

结合 README 里列出的完整清单，交互模式下值得记住的斜杠命令还包括 `/` 命令选择器本身（`CommandPicker.tsx` 组件负责渲染，输入 `/` 后用方向键选择、Enter 确认）、交互式权限确认弹窗（工具执行前的 y/n 确认对话框）。这些具体的交互细节在真实使用中比死记文档更容易掌握,建议直接跑一次 `oh` 感受一下。

## 常见问题/易踩坑

- **以为 `--output-format` 对交互模式（`oh` 不带 `-p`）也生效**：不成立。`--output-format` 只在 `-p`/`--print` 触发的 `run_print_mode` 路径里被读取，交互式的 `run_repl` 完全不关心这个参数。
- **用 `json` 格式做"实时进度条"**：`json` 格式的设计就是"跑完才输出一个对象"，天生不适合展示中间过程,想要中间过程必须用 `stream-json`。
- **不确定进入的是哪个 TUI 前端**：只要没有传 `--backend-only`，交互式 `oh` 命令走的都是 React/Ink 前端；`--backend-only` 是给前端进程反过来调用 Python 后端用的隐藏参数,普通用户不需要手动传它。

## 小结

`oh` 的三种运行形态——交互式会话、`-p` 单次查询、以及查询之下的三种输出格式——共享同一套 Agent 运行时和配置项，区别只在于"事件流最终被谁消费、以什么形式消费"。默认的交互路径实际上启动的是一个独立的 React/Ink Node 进程,通过 `--backend-only` 和 Python 后端通信，这一层双前端架构的细节留给第 02 章第 2 篇专门拆解。下一篇《Provider Workflow 与 Profile 机制》会回到配置层，看看 `oh setup` 是怎么把"认证 → provider → 模型"这条本来很琐碎的配置流程，收敛成一个五步引导的。
