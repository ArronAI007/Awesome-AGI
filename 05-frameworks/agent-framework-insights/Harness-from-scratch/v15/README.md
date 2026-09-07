# v15：多智能体协作（系列终点）

## 本版目标

到 v14 为止，一次运行自始至终只有一个 agent 在跑，遇到需要"分头处理"的子任务也只能塞进同一个上下文、同一个预算里硬跑。这一版加入最小可行的多智能体协作：主 agent 可以把一个子任务委派给一个完全独立的子 agent（自己的消息历史、自己的执行预算、自己的 `MockLLM`），子任务跑完后把结果摘要自然地回填进主循环的上下文——不需要引入任何"多智能体消息类型"或者额外的编排层，一个 `delegate_task` 工具就够了。这是整个 v1~v15 系列的工业级终点形态。

## 新增/修改文件（对照 v14）

- 修改 `tools.py`：`build_default_tool_registry()` 新增可选参数 `sub_task_scripts`（`{子任务名: (子任务目标, 子任务脚本)}`）；新增 `delegate_task(subtask)` 工具，内部按 `subtask` 查表、构建全新的子 `MockLLM`/`Budget`/`tool_registry`，递归调用 `harness.loop.run_agent()`，把子任务最终结果包装成一条说明性文字作为这次工具调用的返回值。
- 修改 `scenarios.py`：新增顶层字典 `SUB_TASK_SCRIPTS`（供 `delegate_task` 查表）和 `delegate_then_finish` 场景。
- 修改 `main.py`：构建 `tool_registry` 时传入 `SUB_TASK_SCRIPTS`；`--scenario` 增加 `delegate_then_finish`。
- 其余文件（`mock_llm.py`、`harness/loop.py` 及其余全部 `harness/` 子模块、`evals.py`）与 v14 完全一致——本版本不修改核心循环，"多智能体"完全是工具层面的能力。

## 核心设计

**为什么用"一个会递归调用 `run_agent()` 的工具"而不是引入一个新的 `Orchestrator` 抽象层**：这个系列从 v1 起的核心哲学就是"一个工具就是一个能力"——`delegate_task` 完美契合这个哲学：从主循环的视角看，委派子任务和调用 `search_web`没有任何区别，都是"发起一次调用、等待结果、把结果塞进消息历史"。引入一个显式的编排层会破坏这种一致性，也会让 v15 看起来像是一个跟前 14 个版本风格不搭的"外挂"。

**为什么子 agent 的 `tool_registry` 不传 `sub_task_scripts` 能阻止无限递归委派**：需要澄清一个容易讲错的细节——`build_default_tool_registry()` 是无条件把 `delegate_task` 注册进返回的 registry 的，所以子 agent 的注册表里**确实还有** `delegate_task` 这个工具键，并不是"工具不存在"。真正起作用的是 `delegate_task` 内部闭包捕获的 `sub_task_scripts`：子 agent 是用 `build_default_tool_registry()`（不传 `sub_task_scripts`）构建的，所以它自己的 `delegate_task` 闭包里 `sub_task_scripts` 默认是空字典 `{}`——不管子 agent 的模型想委派什么子任务名，查表都会立刻失败，返回 `"Error: 未知子任务 ..."`，委派链在这里就被截断了，根本不会真的递归下去。也就是说，阻止无限递归的不是"移除了工具"，而是"每一层子 agent 手里的查表字典都是空的"，这个机制上的差别值得说清楚，避免以后有人真的去检查 `"delegate_task" in sub_registry` 时被"工具应该不存在"这个错误预期搞糊涂。真实系统如果需要支持多层委派，需要额外设计委派深度限制、循环委派检测等机制，这些都留给读者自行扩展。

**为什么 `delegate_task` 要 `try/except ScriptExhausted`**：子 agent 内部也会经历 v1~v14 讲过的全部风险（脚本可能因为各种原因提前耗尽），如果不捕获，这个异常会直接从 `delegate_task` 这个工具函数里往外抛，扎穿 `_execute_call` 的 `except Exception` 兜底（`ScriptExhausted` 确实是 `Exception` 的子类，理论上会被外层 `except Exception` 接住而不是让主循环崩溃——但这样处理会把子任务失败误判成一次普通的工具执行失败，走向重试/熔断逻辑，语义上是错的：子任务没跑完不是因为工具本身不可靠，重试也解决不了"脚本没写够"这个问题）。在 `delegate_task` 内部就近捕获、转换成一条说明性文字，语义更准确，也让主循环能拿到一个有意义的失败摘要继续往下推进，而不是被无谓地重试。

## 如何运行 demo

```bash
python3 main.py --scenario delegate_then_finish
```

## 局限性

`delegate_task` 只支持一层委派（子 agent 不能再往下委派），也没有任何"多个子任务并行委派"的编排能力——如果模型一轮里发出多个 `delegate_task` 调用，它们会像其它工具一样通过 v10 的 `asyncio.gather` 并发执行，但彼此之间没有协调机制（比如子任务之间的依赖关系、结果聚合策略）。子 agent 的运行也不会计入主循环的 `event_log`（如果启用了 v12 的可观测性）、不受主循环的会话持久化配置影响——子 agent 完全独立于这些横切关注点，这是刻意的简化，真实的多智能体框架通常需要让这些能力在委派边界上传播下去。

还有一处 v10（超时取消）和 v15（把整个子 agent 循环当成一次工具调用）叠加后才会出现的细节：主循环给 `delegate_task` 这次调用套的是和其它工具一样的单次 `timeout_seconds`（默认 5 秒），但这一次调用底下其实是一整个最多 `_SUB_AGENT_MAX_STEPS`（10）步、每步都有自己独立超时预算的子 agent 循环——如果子任务恰好需要好几步、加起来接近或超过外层这个 5 秒窗口，子 agent 会被外层超时直接取消掉，拿到一条泛泛的"执行超过 N 秒，已取消"提示，而不是子 agent 本可能给出的更有信息量的成功摘要或 `ScriptExhausted` 说明。演示用的 mock 延迟都在 0.2 秒以内，不会撞到这个边界，但如果把 `delegate_task` 接到真实、有延迟的子任务上，两层超时预算需要一起设计（比如给委派类工具单独放宽 `timeout_seconds`，或者让子 agent 的步数上限和外层超时匹配），这个版本没有解决这个问题，只是把它留在这里说清楚。

## 系列总结

到这里，v1~v15 全部完成：从一个没有任何防护的裸循环开始，逐步加固出执行预算、循环空转检测、上下文治理、输出校验（v1~v7 里程碑整合），再到结构化错误处理、会话持久化、并发执行、权限沙箱（v8~v11），最后是可观测性、自动化评估、动态工具、多智能体协作（v12~v15）——一共十五个版本，每个版本只加一个优化点，最终拼出一个具备工业级水准的 Agent Harness 骨架。
