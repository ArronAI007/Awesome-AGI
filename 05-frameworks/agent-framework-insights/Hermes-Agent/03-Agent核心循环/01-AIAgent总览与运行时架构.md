# AIAgent 总览与运行时架构

> hermes-agent 的整个运行时收敛在 `run_agent.py` 里一个近 9000 行的 `class AIAgent` 上——它既是持有会话状态的"外壳"，又通过 `__init__` 把真正的初始化工作转发给 `agent/agent_init.py`，通过 `run_conversation` 把真正的对话循环转发给 `agent/conversation_loop.py`。这种"类方法即转发器（forwarder）"的组织方式，是本章后续三篇要深入的所有机制（前奏、错误分类、中断）共同的入口。本篇先建立整体地图：`AIAgent` 管什么状态、`run_agent.py` 与 `agent/conversation_loop.py` 怎么分工、一次完整对话的调用链路长什么样，以及 `codex_app_server` 这个"整条运行时可插拔替换"的分流点。

## 学习目标

- 理解 `class AIAgent`（`run_agent.py:422`）的职责边界：它持有哪些状态，`__init__` 和 `run_conversation` 为什么都只是"转发器"。
- 理解 `run_agent.py`（类方法定义处）与 `agent/conversation_loop.py`（自由函数 `run_conversation`）之间的分工——这不是 PI 那种"引擎/整车"的纯度分层，而是一次为压缩巨型文件体积做的**机械抽取**，理解这个区别很重要。
- 能画出一次"用户输入 → 模型调用 → 工具执行 → 结果反馈 → 再次调用模型"的完整时序，并对照真实代码定位每一步。
- 理解 `agent.api_mode == "codex_app_server"` 分流点：如何把整个轮次委托给外部子进程，构成一个可插拔的运行时后端。
- 建立对 `AIAgent` 暴露的公共方法（`chat`/`run_conversation`/`interrupt`/`steer`/`redirect`/`switch_model`/`close` 等）的整体印象，为后续三篇的细节展开打基础。

## `AIAgent`：持有状态的巨型外壳

`class AIAgent` 的类文档字符串很朴素：

```python
# run_agent.py:422
class AIAgent:
    """
    AI Agent with tool calling capabilities.

    This class manages the conversation flow, tool execution, and response handling
    for AI models that support function calling.
    """
```

但真正有信息量的是它的 `__init__` 签名——超过 70 个关键字参数，涵盖模型/provider/api_mode/base_url、一长串以 `_callback` 结尾的回调（`tool_progress_callback`、`stream_delta_callback`、`step_callback`、`event_callback` 等）、会话标识（`session_id`/`platform`/`user_id`/`chat_id`）、以及运行时开关（`iteration_budget`、`fallback_model`、`credential_pool`、`checkpoints_enabled`）。`__init__` 本身只做一件事：

```python
# run_agent.py:527 附近
"""Forwarder — see ``agent.agent_init.init_agent``."""
from agent.agent_init import init_agent
init_agent(self, base_url=base_url, api_key=api_key, ...)
```

真正的初始化逻辑（近 3000 行）全部在 `agent/agent_init.py` 的 `init_agent()` 函数里完成，它以 `agent` 作为第一个参数直接对 `self` 做属性赋值——工具集解析、system prompt 的初次准备、credential pool、fallback chain 的建立、各种 per-session 锁（`_pending_redirect_lock`、`_pending_steer_lock`、`_session_persist_lock`）都在这里挂到实例上。

`AIAgent` 实例因此持有的状态大致可以分五类：

- **会话身份**：`session_id`、`_session_db`、`_cached_system_prompt`、`_conversation_root_id()`。
- **模型/路由配置**：`model`/`provider`/`api_mode`/`base_url`、`_fallback_chain`/`_fallback_index`/`_primary_runtime`、`_credential_pool`。
- **工具与终端后端句柄**：`tools`/`valid_tool_names`、各类 OpenAI/Anthropic client（`_create_openai_client`、`_create_request_anthropic_client` 等）、MCP 工具快照。
- **本轮/本次运行的瞬时状态**：`iteration_budget`、`_checkpoint_mgr`、大量 `_xxx_retries` 计数器、`_execution_thread_id`。
- **跨线程控制信号**：`_interrupt_requested`/`_pending_redirect`/`_pending_steer` 及其配套锁（第四篇详细展开）。

对外暴露的方法可以粗分为三组（完整方法列表用 `grep -n "^    def " run_agent.py` 就能拿到，数量超过 300 个私有方法，这里只列公共接口）：

- **驱动对话**：`chat()`（`run_agent.py:3944` 附近，单轮简化封装）、`run_conversation()`（本篇下一节详细讲）。
- **跨线程控制**：`interrupt()`/`hard_interrupt()`/`clear_interrupt()`/`steer()`/`redirect()`（第四篇专门展开）。
- **生命周期与可观测性**：`switch_model()`、`close()`/`release_clients()`、`shutdown_memory_provider()`/`commit_memory_session()`、`get_activity_summary()`/`get_credits_state()`/`get_rate_limit_state()`、`is_interrupted()`。

## `run_agent.py` 与 `agent/conversation_loop.py`：机械抽取，不是纯度分层

读到 `AIAgent.run_conversation` 时很容易联想到 PI 的 `Agent` 类（有状态外壳）与 `agent-loop.ts`（无状态纯函数）的分层——但 hermes 这里的真实情况更朴素，也更值得如实说明。

`AIAgent.run_conversation`（`run_agent.py:8597`）本身相当长（近 500 行），但几乎全部内容是**跨进程/跨线程的会话租约与可观测性 bookkeeping**：

```python
# run_agent.py:8597-8630（节选）
def run_conversation(
    self,
    user_message: Any,
    system_message: str = None,
    conversation_history: List[Dict[str, Any]] = None,
    task_id: str = None,
    stream_callback: Optional[callable] = None,
    ...
) -> Dict[str, Any]:
    """Forwarder — see ``agent.conversation_loop.run_conversation``."""
    from agent.background_review import cancel_background_review_for_live_turn
    cancel_background_review_for_live_turn(self)
    from agent.conversation_loop import run_conversation
    ...
```

这段代码的主体在处理一件事：`state.db` 可能被 Desktop、CLI resume、gateway、后台投递等多个进程同时访问，`run_conversation` 在真正进入对话循环之前，会先尝试 `acquire_session_turn_lease()` 获取一把跨进程的会话轮次锁（注释里明确写着"Serialize the full load -> run -> flush region across Hermes processes"），拿到锁之后才调用真正的核心函数：

```python
# run_agent.py:8971-8983
result = run_conversation(
    self,
    user_message,
    system_message,
    conversation_history,
    effective_task_id,
    stream_callback,
    persist_user_message,
    persist_user_timestamp=persist_user_timestamp,
    persist_user_display_kind=persist_user_display_kind,
    persist_user_display_metadata=persist_user_display_metadata,
    moa_config=moa_config,
)
```

这里被调用的 `run_conversation` 是从 `agent.conversation_loop` 导入的**自由函数**，第一个参数是 `agent` 而不是 `self`——它不是某个"引擎类"的方法，就是一个把 `agent` 实例当第一参数传入、直接读写 `agent` 上百个属性的普通函数。`agent/conversation_loop.py` 顶部没有类似 PI `agent-loop.ts` 那种"只认识 `AgentMessage`，只在调用模型时转换成 `Message[]`"的边界声明；相反，它和 `run_agent.py` 共享同一份可变状态，只是物理上被搬到了另一个文件里。

这一点在 `agent/turn_context.py` 的模块文档字符串里说得非常直白（第二篇会细读整份文件）：

```python
# agent/turn_context.py:1-22（节选）
"""Per-turn setup for ``run_conversation`` (the turn prologue).

``run_conversation`` opened with ~470 lines of straight-line setup before the
tool-calling loop ever started: ...

The builder still mutates ``agent`` heavily (counters, thread id, cached
prompt, session DB) exactly as the inline code did — those side effects are
the point. The ``TurnContext`` it returns carries only the *locals* the loop
reads back.

Behavior is identical to the original inline prologue; this is a pure
move-and-name refactor with no semantic change.
"""
```

"pure move-and-name refactor with no semantic change"——这是理解 `run_agent.py` / `agent/conversation_loop.py` / `agent/turn_context.py` 三者关系的关键：`run_conversation` 曾经是 `AIAgent` 类体内一个近 4000 行的方法，出于文件体积和可读性的考虑被整体搬到独立模块，前奏部分又进一步被搬到 `turn_context.py`。这不是为了建立一个可以脱离 `AIAgent` 单独复用、单独测试的"引擎"，而是给一个已经过度膨胀的类"减重"。理解这一点，才能正确解释为什么 `agent/conversation_loop.py` 里到处是 `agent._xxx`（直接读写实例属性），而不是像 PI 那样有一份显式的 `AgentContext`/`AgentLoopConfig` 契约。

## 一次完整对话的时序

```text
User                AIAgent.run_conversation      conversation_loop.run_conversation   build_turn_context      LLM Provider        tool_executor
 |                        |                                  |                              |                     |                    |
 | agent.run_conversation("修复bug")                          |                              |                     |                    |
 |----------------------->|                                  |                              |                     |                    |
 |                        | acquire_session_turn_lease()      |                              |                     |                    |
 |                        | (跨进程/跨线程串行化 load→run→flush) |                             |                     |                    |
 |                        | run_conversation(self, ...) ------------------------------------->|                     |                    |
 |                        |                                  | build_turn_context(agent, ...) ---------------------->|                    |
 |                        |                                  |   stdio 守护 / 重试计数器归零 / 消息清洗                 |                    |
 |                        |                                  |   system prompt 恢复或重建 / 预压缩 / pre_llm_call hook |                    |
 |                        |                                  |   外部记忆预取 / 崩溃可恢复持久化                        |                    |
 |                        |                                  |<-- 返回 TurnContext ----------------|                     |                    |
 |                        |                                  |                              |                     |                    |
 |                        |                                  | if api_mode == "codex_app_server": 整轮委托给 Codex 子进程，跳过下面所有步骤 |
 |                        |                                  |                              |                     |                    |
 |                        |                                  | while (api_call_count < max_iterations              |                     |                    |
 |                        |                                  |        and iteration_budget.remaining > 0):         |                     |                    |
 |                        |                                  |   _drain_pending_redirect()  (轮内改口，见第四篇)     |                     |                    |
 |                        |                                  |   _checkpoint_mgr.new_turn() (每轮一次快照去重)       |                     |                    |
 |                        |                                  |   if _interrupt_requested: break                    |                     |                    |
 |                        |                                  |   while retry_count < max_retries:                  |                     |                    |
 |                        |                                  |     发起模型请求 --------------------------------------->|                    |
 |                        |                                  |<---------------------------- assistant_message --------|                    |
 |                        |                                  |     失败? classify_api_error() 分类 + 重试/降级（见第三篇）|                    |
 |                        |                                  |   if assistant_message.tool_calls:                  |                     |                    |
 |                        |                                  |     agent._execute_tool_calls(...) ---------------------------------------------->|
 |                        |                                  |<---------------------------------------------------------------- 工具结果追加进 messages |
 |                        |                                  |     _apply_pending_steer_to_tool_results(...)（软改口，见第四篇）|                |                    |
 |                        |                                  |     继续 while（api_call_count += 1，回到顶部）          |                     |                    |
 |                        |                                  |   else: final_response = assistant_message.content，退出 while |                |                    |
 |                        |                                  |<-- 返回 {"final_response", "messages", "api_calls", ...} |                    |
 |                        |<---------------------------------|                              |                     |                    |
 |<-----------------------|                                  |                              |                     |                    |
```

这张图对应的正是 `agent/conversation_loop.py:1834` 开始的 `run_conversation()` 函数体。几个值得注意的细节：

- **循环条件比朴素的 `while True` 复杂**：`while (api_call_count < agent.max_iterations and agent.iteration_budget.remaining > 0) or agent._budget_grace_call:`（`agent/conversation_loop.py:2029`）——`iteration_budget` 是一个独立的预算对象（`agent/iteration_budget.py` 的 `IterationBudget`），`_budget_grace_call` 允许"预算已耗尽但要再给一次宽限调用"的场景（例如让模型至少有机会说一句收尾语）。
- **两层嵌套的重试**：外层 `while` 是"要不要再让模型说一句话"的工具调用轮次；内层 `while retry_count < max_retries`（`agent/conversation_loop.py:2921`）是"这一次模型请求本身失败了要不要重试"，二者是完全不同粒度的循环，第三篇会展开内层的错误分类与重试细节。
- **工具执行完之后不是简单地 `continue`**：`_apply_pending_steer_to_tool_results()` 会在工具批次结束、下一次模型调用发起之前，把用户在工具执行期间发来的"软改口"文本追加进最后一条工具结果里（第四篇详细讲）。

## `codex_app_server`：可插拔运行时分流

`agent/conversation_loop.py` 里，`build_turn_context` 跑完前奏、真正进入 `while` 循环之前，有一处非常干脆的分流：

```python
# agent/conversation_loop.py:2015-2027
# Optional opt-in runtime: if api_mode == codex_app_server, hand the
# turn to the codex app-server subprocess (terminal/file ops/patching
# all run inside Codex). Default Hermes path is bypassed entirely.
# See agent/transports/codex_app_server_session.py for the adapter
# and references/codex-app-server-runtime.md for the rationale.
if agent.api_mode == "codex_app_server":
    return agent._run_codex_app_server_turn(
        user_message=user_message,
        original_user_message=original_user_message,
        messages=messages,
        effective_task_id=effective_task_id,
        should_review_memory=_should_review_memory,
    )
```

`_run_codex_app_server_turn` 同样是个转发器：

```python
# run_agent.py:9091-9102
def _run_codex_app_server_turn(
    self, user_message, original_user_message, messages,
    effective_task_id, should_review_memory,
):
    """Forwarder — see ``agent.codex_runtime.run_codex_app_server_turn``."""
    from agent.codex_runtime import run_codex_app_server_turn
    return run_codex_app_server_turn(
        self, user_message=user_message,
        original_user_message=original_user_message,
        messages=messages, effective_task_id=effective_task_id,
        should_review_memory=should_review_memory,
    )
```

这个分流点的设计意义在于：一旦 `agent.api_mode` 被配置为 `"codex_app_server"`，本篇上面画的那张时序图——内层重试循环、`_execute_tool_calls`、终端/文件操作的工具分发——**整条链路都被绕开**。真正驱动模型对话、执行终端命令、打补丁的是一个独立的 Codex app-server 子进程（`agent/transports/codex_app_server_session.py` 是与它对接的适配器），hermes 侧只是把用户消息转交过去、把子进程的事件转译回自己的回调体系。

这是"可插拔运行时"在一个巨型单体项目里少见的具体案例：`AIAgent` 本身作为对外的稳定接口（`run_conversation` 签名不变），内部却可以整体切换成另一套完全不同实现的执行引擎。`interrupt()`/`redirect()` 等跨线程控制方法内部也都各自写了 `if getattr(self, "api_mode", None) == "codex_app_server":` 分支（第四篇会看到具体代码），说明这个分流不是一次性的“开头判断”，而是渗透到了控制流的多个入口点上，调用方需要在多处对齐两套语义。

## 关键代码解读

- `AIAgent.__init__`（`run_agent.py:445`）→ `agent.agent_init.init_agent`：把 70+ 关键字参数落到实例属性上，建立工具集、system prompt、credential pool、fallback chain 等初始状态。
- `AIAgent.run_conversation`（`run_agent.py:8597`）：跨进程会话轮次锁（`acquire_session_turn_lease`）+ relay/task 可观测性 bookkeeping，真正的对话逻辑委托给下面这个自由函数。
- `agent.conversation_loop.run_conversation`（`agent/conversation_loop.py:1834`）：调用 `build_turn_context` 完成前奏，然后跑本篇时序图里的主循环，返回一个包含 `final_response`/`messages`/`api_calls`/`completed`/`interrupted`/`failed` 等键的字典。
- `agent.turn_context.build_turn_context`（`agent/turn_context.py:508`）：第二篇的主角。
- `agent.api_mode == "codex_app_server"` 分流（`agent/conversation_loop.py:2020`）→ `agent._run_codex_app_server_turn`（`run_agent.py:9091`）→ `agent.codex_runtime.run_codex_app_server_turn`：整条运行时的可插拔替换点。

## 小结与思考题

`AIAgent` 是一个持有海量状态的巨型类，`__init__` 和 `run_conversation` 都只是转发器；真正的初始化逻辑在 `agent/agent_init.py`，真正的对话循环在 `agent/conversation_loop.py`，而循环开始前的"前奏"又被进一步抽到了 `agent/turn_context.py`。这三层拆分的动机是**给一个不断膨胀的巨型类减重**，而不是刻意设计出一份"无状态引擎"契约——被抽出的自由函数依然直接读写 `agent` 的上百个属性。`codex_app_server` 分流点则展示了这套体系里少见的一处真正意义上的"可插拔运行时"：整条主循环可以被一个外部子进程完全取代。

思考题：

1. 如果 `agent/conversation_loop.py` 里的 `run_conversation` 是一个纯函数（不直接读写 `agent` 属性，而是接收/返回一份显式的上下文对象），它的调用方需要做出哪些改动？这种改动的收益（可测试性、可复用性）值得付出多大的重构成本？
2. `codex_app_server` 分流点只在 `build_turn_context` 跑完之后才生效——这意味着即便走 Codex 子进程，前奏里的 system prompt 恢复、预压缩等逻辑依然会执行一遍。这是有意为之还是历史遗留？如果是前者，为什么？
3. `interrupt()`/`redirect()` 等方法内部各自都要单独判断 `api_mode == "codex_app_server"` 走不同分支（第四篇会看到），这种"分流点分散在多处入口"的设计相比"在唯一入口处一次性分流"，会带来什么样的维护成本？
