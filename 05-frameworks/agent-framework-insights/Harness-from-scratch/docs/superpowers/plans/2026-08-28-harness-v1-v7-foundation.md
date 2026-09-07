# 渐进式 Harness 教程：v1~v7 基础加固线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `Harness-from-scratch/` 下实现 v1~v7 七个自包含、可运行的最小 Agent Harness 项目，从裸循环逐步加固到"预算+循环检测+上下文治理+输出校验"全部集成的里程碑版本，并配套文档与测试。

**Architecture:** 每个 `v{N}/` 是一个独立的 Python 项目：`mock_llm.py`（脚本化确定性假 LLM）+ `tools.py`（内存态假工具）+ `scenarios.py`（问题场景/防护生效场景）+ `harness/`（本版本累积的核心逻辑，按能力域拆分成文件）+ `main.py`（CLI 入口）+ `tests/`。版本之间不共享代码——未变化的文件用 `cp` 从上一版本复制，变化的文件在本计划中给出完整内容。每个版本一次 commit。

**Tech Stack:** Python 3.11+ 标准库、`pytest`。不依赖网络或真实 API Key。

**依据的设计文档：** `docs/superpowers/specs/2026-08-28-progressive-harness-series-design.md`

---

## 关于本计划的约定

1. **目录已存在 `v1/`（空目录）**，直接在其中创建文件即可，无需 `mkdir v1`。
2. **每个版本的"未变化文件"用 `cp` 从上一版本复制**，命令在任务里给出。这不是占位符——文件内容在上一个版本的任务里已经完整给出，`cp` 是这一步真实要执行的操作。
3. **测试运行方式统一**：在对应 `v{N}/` 目录下运行 `python -m pytest tests/ -v`。每个版本的 `tests/` 顶部都有：
   ```python
   import sys
   from pathlib import Path

   sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
   ```
   这样测试文件可以直接 `import` 同目录下的 `harness`、`mock_llm`、`tools`、`scenarios` 模块，不需要额外的包安装配置。
4. **消息格式**：`{"role": "system"|"user"|"assistant"|"tool", "content": str, "tool_calls"?: [...], "name"?: str}`。工具调用格式：`{"id": str, "name": str, "args": dict}`。
5. **MockLLM 是纯顺序脚本**：`chat()` 每次调用返回 `script[call_count]` 并自增计数器；脚本用尽还被调用就抛 `ScriptExhausted`——这个异常本身就是"证明循环没有在预期步数内停下"的断言手段，测试里会用到。
6. **提交前缀**：全部使用 `feat(v{N}):`。

---

## Task 0: 根目录与 v1 项目骨架

**Files:**
- Create: `Harness-from-scratch/README.md`
- Create: `Harness-from-scratch/v1/mock_llm.py`
- Create: `Harness-from-scratch/v1/tools.py`

- [ ] **Step 1: 写根目录 README**

```markdown
# Harness from Scratch：渐进式 Agent Harness 教程

`agent-framework-insights` 仓库里的 `PI/`、`DeepSeek-Harness/` 两套课程拆解的是**现成的开源 Agent Harness 项目**。这个目录不一样：从一个没有任何防护的裸循环开始，一个版本只加一个优化点，逐步搭出一个工业级水准的 Agent Harness。

每个 `v{N}/` 目录都是一个**完全自包含、可直接运行**的最小 Python 项目——不依赖真实 API Key（内置脚本化的 Mock LLM 和 Mock 工具），也不依赖其他版本目录。想理解某个优化点是怎么落地的，直接对比 `v{N-1}` 和 `v{N}` 的文件差异即可：

```bash
diff -rq v2 v3   # 看 v3 相对 v2 新增/修改了哪些文件
```

## 路线图

| 版本 | 新增能力 | 一句话说明 |
|---|---|---|
| [v1](v1/README.md) | 裸循环骨架 | 无防护的 `while True` 循环，demo 演示一次停不下来的失控场景 |
| [v2](v2/README.md) | 执行预算 | 步数计数器 + 上限熔断 |
| [v3](v3/README.md) | 循环空转检测 | 工具调用参数哈希 + 连续失败率检测，临时禁用问题工具而不是杀死整个任务 |
| [v4](v4/README.md) | 上下文裁剪 | 周期性清理旧的工具输出，支持按工具名豁免 |
| [v5](v5/README.md) | 压缩安全阀 | 高水位线触发全量摘要压缩 + 最大压缩次数熔断，防止"摘要的摘要"死循环 |
| [v6](v6/README.md) | 输出校验与自愈 | 工具调用前校验存在性/必填参数，错误回填上下文让模型自纠 |
| [v7](v7/README.md) | 里程碑：整合版 | 合并 v2~v6 全部防护为一个完整骨架，集成测试证明多层防护协同生效 |
| v8~v15 | 工业级扩展 | 见设计文档，待后续计划补充（重试退避、会话持久化、并发流式、安全沙箱、可观测性、动态工具、多智能体协作） |

## 阅读顺序

按版本号顺序读。每一版本的 `README.md` 固定包含：本版目标、新增/修改文件、核心设计、如何运行 demo、局限性（引出下一版）。建议先读 README 再看代码，最后跑一遍 `pytest`。

设计文档：[`docs/superpowers/specs/2026-08-28-progressive-harness-series-design.md`](docs/superpowers/specs/2026-08-28-progressive-harness-series-design.md)
```

- [ ] **Step 2: 创建 `v1/mock_llm.py`**

```python
"""脚本化的确定性假 LLM：没有真实 API Key 也能稳定复现固定场景。"""


class ScriptExhausted(Exception):
    """脚本用尽后仍被调用——说明循环没有在预期步数内自己停下来。"""


class MockLLM:
    def __init__(self, script):
        # script: [{"content": str | None, "tool_calls": [dict, ...]}, ...]
        # tool_calls 为空列表表示模型认为任务完成，循环应当停止。
        self.script = script
        self.call_count = 0

    def chat(self, messages, tools=None):
        if self.call_count >= len(self.script):
            raise ScriptExhausted(
                f"MockLLM 脚本只有 {len(self.script)} 步，但被调用了第 {self.call_count + 1} 次"
            )
        response = self.script[self.call_count]
        self.call_count += 1
        return response
```

- [ ] **Step 3: 创建 `v1/tools.py`**

```python
"""示例工具集：内存态假文件系统 + 假搜索，配合 MockLLM 复现固定场景。"""


class Tool:
    def __init__(self, name, func, params=None):
        self.name = name
        self.func = func
        self.params = params or {}  # param_name -> {"required": bool}

    def run(self, args):
        return self.func(**args)


def _make_fake_fs():
    return {"config.yaml": "timeout: 30\nretries: 3\n"}


def build_default_tool_registry():
    fake_fs = _make_fake_fs()

    def read_file(path):
        if path not in fake_fs:
            raise FileNotFoundError(f"文件不存在: {path}")
        return fake_fs[path]

    def search_web(query):
        return f"搜索 '{query}' 的结果：暂无相关信息（mock 数据）。"

    def write_file(path, content):
        fake_fs[path] = content
        return f"已写入 {path}（{len(content)} 字符）"

    return {
        "read_file": Tool("read_file", read_file, {"path": {"required": True}}),
        "search_web": Tool("search_web", search_web, {"query": {"required": True}}),
        "write_file": Tool(
            "write_file",
            write_file,
            {"path": {"required": True}, "content": {"required": True}},
        ),
    }
```

Note: `_make_fake_fs()` 在 `build_default_tool_registry()` 内部按次调用创建，保证每次测试拿到的 registry 互不共享状态（避免测试间污染）。

- [ ] **Step 4: Commit**

```bash
cd Harness-from-scratch
git add README.md v1/mock_llm.py v1/tools.py
git commit -m "feat: add project README and v1 mock LLM / tools scaffolding"
```

---

## Task 1: v1 —— 裸循环骨架

**Files:**
- Create: `v1/scenarios.py`
- Create: `v1/harness/__init__.py`
- Create: `v1/harness/loop.py`
- Create: `v1/main.py`
- Test: `v1/tests/test_loop.py`
- Create: `v1/README.md`

- [ ] **Step 1: 创建 `v1/scenarios.py`**

```python
"""场景定义：每个场景是 (goal, script) 二元组。"""


def _repeat(response, times):
    return [response for _ in range(times)]


SCENARIOS = {
    "happy_path": (
        "读取配置文件并总结",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}}
                ],
            },
            {"content": "配置文件内容：timeout=30, retries=3。", "tool_calls": []},
        ],
    ),
    "runaway": (
        "读取 bad.txt 并总结",
        _repeat(
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_x", "name": "read_file", "args": {"path": "bad.txt"}}
                ],
            },
            50,
        ),
    ),
}


def get_scenario(name):
    return SCENARIOS[name]
```

- [ ] **Step 2: 创建 `v1/harness/__init__.py`（空文件）**

```python
```

- [ ] **Step 3: 写失败测试 `v1/tests/test_loop.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.loop import run_agent
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import build_default_tool_registry


def test_happy_path_stops_when_model_returns_no_tool_calls():
    goal, script = get_scenario("happy_path")
    llm = MockLLM(script)
    result = run_agent(goal, build_default_tool_registry(), llm)
    assert "timeout=30" in result
    assert llm.call_count == 2


def test_runaway_scenario_never_stops_on_its_own():
    goal, script = get_scenario("runaway")
    llm = MockLLM(script)
    raised = False
    try:
        run_agent(goal, build_default_tool_registry(), llm)
    except ScriptExhausted:
        raised = True
    assert raised, "v1 没有任何防护机制，理应把 50 步脚本跑穿后仍未停止"
    assert llm.call_count == 50
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd v1 && python -m pytest tests/test_loop.py -v`
Expected: `ModuleNotFoundError: No module named 'harness.loop'`（因为 `harness/loop.py` 还不存在）

- [ ] **Step 5: 实现 `v1/harness/loop.py`**

```python
"""v1：最朴素的 Agent 循环，没有任何防护。"""


def run_agent(goal, tool_registry, llm):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]

    while True:
        response = llm.chat(messages, tools=list(tool_registry.keys()))

        if not response["tool_calls"]:
            return response["content"]

        messages.append(
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            }
        )

        for call in response["tool_calls"]:
            tool = tool_registry[call["name"]]
            try:
                result = tool.run(call["args"])
            except Exception as exc:  # noqa: BLE001 - v1 尚无分类错误处理，见 v6/v8
                result = f"Error: {exc}"
            messages.append({"role": "tool", "name": call["name"], "content": result})
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd v1 && python -m pytest tests/test_loop.py -v`
Expected: `2 passed`

- [ ] **Step 7: 创建 `v1/main.py`**

```python
import argparse

from harness.loop import run_agent
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import build_default_tool_registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, choices=["happy_path", "runaway"])
    args = parser.parse_args()

    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()

    try:
        result = run_agent(goal, tool_registry, llm)
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: 手动跑一遍两个场景，确认输出符合预期**

Run: `cd v1 && python main.py --scenario happy_path`
Expected:
```
[结果] 配置文件内容：timeout=30, retries=3。
[LLM 调用次数] 2
```

Run: `cd v1 && python main.py --scenario runaway`
Expected:
```
[未停止] MockLLM 脚本只有 50 步，但被调用了第 51 次
[LLM 调用次数] 50
```

（真实场景下这里没有 50 步的脚本上限，会真的无限循环下去——这正是 v1 要暴露的问题。）

- [ ] **Step 9: 创建 `v1/README.md`**

```markdown
# v1：裸循环骨架

## 本版目标

搭建能跑通"调用 LLM → 判断是否结束 → 执行工具 → 回填结果"这个最小循环的 Harness，**不加任何防护**。目的是让下一版本的每一层防护都有一个具体、可复现的"如果不加会怎样"的对照。

## 新增文件

- `mock_llm.py` —— 脚本化、确定性的假 LLM，`chat()` 按顺序返回预先写好的响应，脚本用尽还被调用就抛 `ScriptExhausted`。
- `tools.py` —— 内存态的假工具集：`read_file` / `search_web` / `write_file`。
- `harness/loop.py` —— `run_agent()`：核心 while 循环。
- `scenarios.py` —— 两个场景：`happy_path`（正常完成）、`runaway`（路径写错，模型反复重试同一个错误调用）。
- `main.py` —— CLI 入口。

## 核心设计

`run_agent()` 只做三件事：调用 LLM、检查是否有 `tool_calls`（没有就代表完成）、执行工具并把结果写回消息列表。没有步数上限、没有重复调用检测、没有上下文治理、没有输出校验——这就是"裸循环"的含义。

`MockLLM` 用完全确定性的脚本代替真实模型：每次 `chat()` 调用按顺序吐出下一条预设响应。这样"如果模型反复调用同一个错误工具会怎样"可以稳定复现成一个自动化测试，而不用真的接一个会随机应答的模型。

## 如何运行 demo

```bash
python main.py --scenario happy_path   # 一次工具调用后正常完成
python main.py --scenario runaway      # 路径写错，模型反复重试，50 步脚本跑穿后才停（真实场景下会一直停不下来）
```

## 局限性

`runaway` 场景证明了：只要模型认定"应该继续调用工具"，这个循环就会无限跑下去，没有任何机制能把它拉回来。哪怕工具反复报错、哪怕已经浪费了几十次调用，Harness 本身毫无感知。这正是 v2 要解决的问题：加一个步数上限的执行预算。
```

- [ ] **Step 10: Commit**

```bash
cd Harness-from-scratch
git add v1/
git commit -m "feat(v1): bare agent loop with no guardrails"
```

---

## Task 2: v2 —— 执行预算

**Files:**
- Create: `v2/mock_llm.py`, `v2/tools.py`, `v2/scenarios.py`, `v2/harness/__init__.py` (copied from v1)
- Create: `v2/harness/budget.py`
- Modify (relative to v1): `v2/harness/loop.py`, `v2/main.py`
- Test: `v2/tests/test_budget.py`
- Create: `v2/README.md`

- [ ] **Step 1: 复制未变化的文件**

```bash
cd Harness-from-scratch
cp v1/mock_llm.py v2/mock_llm.py
cp v1/tools.py v2/tools.py
cp v1/scenarios.py v2/scenarios.py
cp v1/harness/__init__.py v2/harness/__init__.py
```

- [ ] **Step 2: 写失败测试 `v2/tests/test_budget.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import build_default_tool_registry


def test_budget_stops_runaway_scenario_before_script_exhausted():
    goal, script = get_scenario("runaway")  # 50 步的脚本
    llm = MockLLM(script)
    budget = Budget(max_steps=30)

    result = run_agent(goal, build_default_tool_registry(), llm, budget)

    assert "步骤上限已达" in result
    assert llm.call_count == 30


def test_budget_does_not_cut_off_a_task_that_finishes_within_budget():
    goal, script = get_scenario("happy_path")  # 2 步就结束
    llm = MockLLM(script)
    budget = Budget(max_steps=30)

    result = run_agent(goal, build_default_tool_registry(), llm, budget)

    assert "timeout=30" in result
    assert llm.call_count == 2


def test_budget_boundary_exactly_at_max_steps_is_not_exceeded():
    # 脚本恰好在第 max_steps 步返回空 tool_calls：不应该被判定为超限。
    script = [
        {
            "content": None,
            "tool_calls": [{"id": "c", "name": "search_web", "args": {"query": "x"}}],
        }
    ] * 2 + [{"content": "done", "tool_calls": []}]
    llm = MockLLM(script)
    budget = Budget(max_steps=3)

    result = run_agent("goal", build_default_tool_registry(), llm, budget)

    assert result == "done"
    assert llm.call_count == 3
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd v2 && python -m pytest tests/test_budget.py -v`
Expected: `ModuleNotFoundError: No module named 'harness.budget'`

- [ ] **Step 4: 实现 `v2/harness/budget.py`**

```python
"""v2：执行预算——步数计数器 + 上限熔断。"""


class Budget:
    def __init__(self, max_steps):
        self.max_steps = max_steps
        self.steps_used = 0

    def consume_step(self):
        self.steps_used += 1

    def is_exceeded(self):
        return self.steps_used > self.max_steps
```

- [ ] **Step 5: 修改 `v2/harness/loop.py`**

```python
"""v2：在 v1 的裸循环基础上加入执行预算。"""


def run_agent(goal, tool_registry, llm, budget):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        response = llm.chat(messages, tools=list(tool_registry.keys()))

        if not response["tool_calls"]:
            return response["content"]

        messages.append(
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            }
        )

        for call in response["tool_calls"]:
            tool = tool_registry[call["name"]]
            try:
                result = tool.run(call["args"])
            except Exception as exc:  # noqa: BLE001 - v1 尚无分类错误处理，见 v6/v8
                result = f"Error: {exc}"
            messages.append({"role": "tool", "name": call["name"], "content": result})
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd v2 && python -m pytest tests/test_budget.py -v`
Expected: `3 passed`

- [ ] **Step 7: 修改 `v2/main.py`**

```python
import argparse

from harness.budget import Budget
from harness.loop import run_agent
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import build_default_tool_registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, choices=["happy_path", "runaway"])
    parser.add_argument("--max-steps", type=int, default=30)
    args = parser.parse_args()

    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)

    try:
        result = run_agent(goal, tool_registry, llm, budget)
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: 手动验证**

Run: `cd v2 && python main.py --scenario runaway --max-steps 30`
Expected:
```
[结果] ⚠️ 步骤上限已达（30 步），强制终止
[LLM 调用次数] 30
```

- [ ] **Step 9: 创建 `v2/README.md`**

```markdown
# v2：执行预算

## 本版目标

v1 证明了裸循环在模型反复出错时会无限跑下去。这一版加一道最简单的防线：**步数计数器 + 上限熔断**。

## 新增/修改文件（对照 v1）

- 新增 `harness/budget.py`：`Budget` 类，记录已用步数、判断是否超限。
- 修改 `harness/loop.py`：`run_agent()` 新增 `budget` 参数，每轮循环开始先 `consume_step()`，超限立即返回终止消息。
- 修改 `main.py`：新增 `--max-steps` 参数。
- 其余文件（`mock_llm.py`、`tools.py`、`scenarios.py`）与 v1 完全一致。

## 核心设计

预算检查放在循环最开头，**在调用 LLM 之前**——超限时要立刻停，不能再多花一次 LLM 调用去问它"你还要继续吗"。`Budget` 做成独立的小类而不是裸的整数计数器，是为了后续版本（v7 整合、v8 重试退避）可以复用同一套"资源守卫"设计模式：一个对象只负责"记账 + 判断是否耗尽"，不掺杂决策逻辑。

## 如何运行 demo

```bash
python main.py --scenario runaway --max-steps 30   # 30 步后被强制终止，而不是像 v1 那样一直跑
python main.py --scenario happy_path --max-steps 30 # 正常 2 步内完成，预算完全不影响正常任务
```

## 局限性

`max_steps` 是一个全局硬上限，选值本身就是个两难：设低了会打断正常的多轮任务，设高了遇到空转场景照样浪费大量调用。v2 没有能力区分"模型在正常推进任务"还是"原地打转"——这正是 v3 循环空转检测要解决的问题。
```

- [ ] **Step 10: Commit**

```bash
cd Harness-from-scratch
git add v2/
git commit -m "feat(v2): execution budget with step-count circuit breaker"
```

---

## Task 3: v3 —— 循环空转检测

**Files:**
- Copy from v2 (unchanged): `mock_llm.py`, `tools.py`, `harness/__init__.py`, `harness/budget.py`
- Create: `v3/harness/loop_detector.py`
- Modify (relative to v2): `v3/harness/loop.py`, `v3/scenarios.py`, `v3/main.py`
- Test: `v3/tests/test_loop_detector.py`
- Create: `v3/README.md`

- [ ] **Step 1: 复制未变化的文件**

```bash
cd Harness-from-scratch
cp v2/mock_llm.py v3/mock_llm.py
cp v2/tools.py v3/tools.py
cp v2/harness/__init__.py v3/harness/__init__.py
cp v2/harness/budget.py v3/harness/budget.py
```

- [ ] **Step 2: 扩展 `v3/scenarios.py`（在 v2 场景基础上新增一个）**

```python
"""场景定义：每个场景是 (goal, script) 二元组。"""


def _repeat(response, times):
    return [response for _ in range(times)]


SCENARIOS = {
    "happy_path": (
        "读取配置文件并总结",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}}
                ],
            },
            {"content": "配置文件内容：timeout=30, retries=3。", "tool_calls": []},
        ],
    ),
    "runaway": (
        "读取 bad.txt 并总结",
        _repeat(
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_x", "name": "read_file", "args": {"path": "bad.txt"}}
                ],
            },
            50,
        ),
    ),
    # 模型连续 5 次用相同参数调用 read_file；工具被临时禁用后，
    # 第 6 次调用改用 search_web 成功，第 7 次返回空 tool_calls 结束。
    "spin_then_recover": (
        "读取 bad.txt，如果失败就想别的办法",
        _repeat(
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_x", "name": "read_file", "args": {"path": "bad.txt"}}
                ],
            },
            5,
        )
        + [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_6",
                        "name": "search_web",
                        "args": {"query": "bad.txt 内容 替代方案"},
                    }
                ],
            },
            {"content": "改用搜索后完成任务。", "tool_calls": []},
        ],
    ),
}


def get_scenario(name):
    return SCENARIOS[name]
```

- [ ] **Step 3: 写失败测试 `v3/tests/test_loop_detector.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from harness.loop_detector import detect_loop
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import build_default_tool_registry


def test_detect_loop_flags_five_identical_calls_as_critical():
    call_history = [
        {"tool": "read_file", "args": {"path": "bad.txt"}, "ok": False}
        for _ in range(5)
    ]
    result = detect_loop(call_history)
    assert result["severity"] == "critical"
    assert result["blocked_tool"] == "read_file"


def test_detect_loop_ignores_varied_calls():
    call_history = [
        {"tool": "read_file", "args": {"path": f"file_{i}.txt"}, "ok": True}
        for i in range(5)
    ]
    result = detect_loop(call_history)
    assert result["severity"] == "none"


def test_spin_then_recover_scenario_disables_tool_and_switches_strategy():
    goal, script = get_scenario("spin_then_recover")
    llm = MockLLM(script)
    budget = Budget(max_steps=30)
    tool_registry = build_default_tool_registry()

    result = run_agent(goal, tool_registry, llm, budget)

    assert result == "改用搜索后完成任务。"
    assert "read_file" not in tool_registry  # 被临时禁用
    assert llm.call_count == 7
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd v3 && python -m pytest tests/test_loop_detector.py -v`
Expected: `ModuleNotFoundError: No module named 'harness.loop_detector'`

- [ ] **Step 5: 实现 `v3/harness/loop_detector.py`**

```python
"""v3：循环空转检测——对最近的工具调用做参数哈希，识别原地打转。"""

import hashlib


def hash_args(tool_name, args):
    raw = f"{tool_name}{sorted(args.items())}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def detect_loop(call_history):
    recent = call_history[-10:]

    if len(recent) >= 5:
        hashes = [hash_args(item["tool"], item["args"]) for item in recent[-5:]]
        if len(set(hashes)) == 1:
            return {
                "severity": "critical",
                "reason": "连续 5 次调用参数完全相同，判定为空转",
                "blocked_tool": recent[-1]["tool"],
            }

    fail_count = sum(1 for rec in recent if not rec["ok"])
    if fail_count >= 8:
        return {
            "severity": "warning",
            "reason": f"最近 {len(recent)} 步中有 {fail_count} 步失败",
            "blocked_tool": None,
        }

    return {"severity": "none", "reason": "", "blocked_tool": None}
```

- [ ] **Step 6: 运行测试确认部分通过**

Run: `cd v3 && python -m pytest tests/test_loop_detector.py -v`
Expected: `test_detect_loop_flags_five_identical_calls_as_critical` 和 `test_detect_loop_ignores_varied_calls` 通过；`test_spin_then_recover_scenario_disables_tool_and_switches_strategy` 失败（`run_agent()` 还没有集成循环检测，也不接受/记录 `call_history`）。

- [ ] **Step 7: 修改 `v3/harness/loop.py`**

```python
"""v3：在 v2 的执行预算基础上加入循环空转检测。"""

from harness.loop_detector import detect_loop


def run_agent(goal, tool_registry, llm, budget):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]
    call_history = []

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        loop_check = detect_loop(call_history)
        if loop_check["severity"] == "critical":
            blocked = loop_check["blocked_tool"]
            if blocked in tool_registry:
                del tool_registry[blocked]
            messages.append(
                {
                    "role": "system",
                    "content": f"[循环检测] {loop_check['reason']}。工具 {blocked} 已暂时禁用，请更换策略。",
                }
            )

        response = llm.chat(messages, tools=list(tool_registry.keys()))

        if not response["tool_calls"]:
            return response["content"]

        messages.append(
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            }
        )

        for call in response["tool_calls"]:
            tool = tool_registry[call["name"]]
            ok = True
            try:
                result = tool.run(call["args"])
            except Exception as exc:  # noqa: BLE001 - v1 尚无分类错误处理，见 v6/v8
                result = f"Error: {exc}"
                ok = False
            messages.append({"role": "tool", "name": call["name"], "content": result})
            call_history.append({"tool": call["name"], "args": call["args"], "ok": ok})
```

注意：`del tool_registry[blocked]` 只在下一次循环检测**之后**、执行第 6 次调用**之前**生效——因为 `spin_then_recover` 场景的脚本第 6 步本来就改叫 `search_web`，所以这里不会触发"工具已被删除但模型还在调用它"的情况。这个边界情况留到 v6 的输出校验去处理，本版本的"局限性"里会说明。

- [ ] **Step 8: 运行测试确认全部通过**

Run: `cd v3 && python -m pytest tests/test_loop_detector.py -v`
Expected: `3 passed`

- [ ] **Step 9: 修改 `v3/main.py`（在 v2 基础上新增 scenario 选项）**

```python
import argparse

from harness.budget import Budget
from harness.loop import run_agent
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import build_default_tool_registry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["happy_path", "runaway", "spin_then_recover"],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    args = parser.parse_args()

    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)

    try:
        result = run_agent(goal, tool_registry, llm, budget)
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: 手动验证**

Run: `cd v3 && python main.py --scenario spin_then_recover`
Expected:
```
[结果] 改用搜索后完成任务。
[LLM 调用次数] 7
```

- [ ] **Step 11: 创建 `v3/README.md`**

```markdown
# v3：循环空转检测

## 本版目标

v2 的步数上限治标不治本：阈值设低会打断正常长任务，设高又对空转浪费无能为力。这一版加入**循环空转检测**：识别"模型在原地打转"，只临时禁用那一个出问题的工具，给模型机会换策略，而不是粗暴杀死整个任务。

## 新增/修改文件（对照 v2）

- 新增 `harness/loop_detector.py`：`detect_loop(call_history)`，对最近 5 次工具调用做参数哈希，全部相同就判定为空转；同时统计最近 10 次里的失败率。
- 修改 `harness/loop.py`：`run_agent()` 新增 `call_history` 记录每次工具调用（工具名、参数、是否成功）；每轮循环在调用 LLM 之前先跑 `detect_loop`，命中 `critical` 就从 `tool_registry` 里临时删除该工具，并注入一条系统消息告知模型。
- 修改 `scenarios.py`：新增 `spin_then_recover` 场景（连续 5 次调用同一个坏工具，第 6 步换成 `search_web` 并成功）。
- 修改 `main.py`：`--scenario` 增加 `spin_then_recover` 选项。
- 其余文件（`mock_llm.py`、`tools.py`、`harness/budget.py`）与 v2 完全一致。

## 核心设计

**为什么只禁用一个工具而不是终止整个任务**：模型可能卡在 `read_file` 上，但接下来完全可以换 `search_web` 完成任务——如果一空转就杀掉整个 run，就是在浪费一个本可以被拯救的任务。

**为什么用参数哈希而不是完全比较对象**：`hash_args()` 把工具名和排序后的参数拼成字符串再取 MD5，这样即使参数字典的 key 顺序不同也能识别出"这其实是同一次调用"。

## 如何运行 demo

```bash
python main.py --scenario spin_then_recover
```

预期输出显示：模型连续 5 次调用 `read_file(bad.txt)` 后，Harness 检测到空转并禁用该工具；模型（在这个 mock 场景里是预先写好的脚本）随后改用 `search_web` 并完成任务，总共只花了 7 次 LLM 调用，而不是像 v1/v2 那样毫无察觉地继续重试。

## 局限性

如果模型在工具被临时禁用**之后**仍然尝试调用它（比如脚本没有像 demo 这样"配合"地换策略），`tool = tool_registry[call["name"]]` 会直接抛 `KeyError`，把整个进程崩溃掉——而不是像期望的那样优雅地告诉模型"这个工具现在不可用"。这正是 v6 输出校验要补上的一块：执行工具之前，先检查这个工具是否真的存在。
```

- [ ] **Step 12: Commit**

```bash
cd Harness-from-scratch
git add v3/
git commit -m "feat(v3): loop/spin detection that disables the offending tool"
```

---

## Task 4: v4 —— 上下文裁剪

**Files:**
- Copy from v3 (unchanged): `mock_llm.py`, `tools.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`
- Create: `v4/harness/context_manager.py`
- Modify (relative to v3): `v4/harness/loop.py`, `v4/scenarios.py`, `v4/main.py`
- Test: `v4/tests/test_context_manager.py`
- Create: `v4/README.md`

- [ ] **Step 1: 复制未变化的文件**

```bash
cd Harness-from-scratch
cp v3/mock_llm.py v4/mock_llm.py
cp v3/tools.py v4/tools.py
cp v3/harness/__init__.py v4/harness/__init__.py
cp v3/harness/budget.py v4/harness/budget.py
cp v3/harness/loop_detector.py v4/harness/loop_detector.py
```

- [ ] **Step 2: 扩展 `v4/scenarios.py`（在 v3 场景基础上新增一个）**

在 v3 的 `SCENARIOS` 字典基础上新增 `long_search_session`：

```python
    # 连续 8 次搜索调用，每次返回一段较长的文本，用来触发上下文裁剪。
    "long_search_session": (
        "帮我依次搜索 8 个关键词并总结",
        [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{i}",
                        "name": "search_web",
                        "args": {"query": f"keyword_{i}"},
                    }
                ],
            }
            for i in range(8)
        ]
        + [{"content": "8 个关键词都搜索完了。", "tool_calls": []}],
    ),
```

将其加入 `v3/scenarios.py` 复制过来的 `SCENARIOS` 字典中（即 `v4/scenarios.py` = v3 的完整内容 + 这一个新 key）。

- [ ] **Step 3: 写失败测试 `v4/tests/test_context_manager.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.context_manager import compact_if_needed
from harness.loop import run_agent
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import build_default_tool_registry


def test_compact_if_needed_clears_old_tool_messages_beyond_keep_window():
    messages = [{"role": "tool", "name": "search_web", "content": "x" * 100}] * 5
    config = {"trigger_every": 1, "keep_recent_count": 2, "exempt_tools": set()}

    compact_if_needed(messages, iteration=1, config=config)

    assert messages[0]["content"].startswith("[cleared:")
    assert messages[-1]["content"] == "x" * 100  # 最近 2 条不受影响
    assert messages[-2]["content"] == "x" * 100


def test_compact_if_needed_respects_exempt_tools():
    messages = [{"role": "tool", "name": "read_file", "content": "重要原文内容"}] * 5
    config = {"trigger_every": 1, "keep_recent_count": 1, "exempt_tools": {"read_file"}}

    compact_if_needed(messages, iteration=1, config=config)

    assert all(m["content"] == "重要原文内容" for m in messages)


def test_long_search_session_gets_compacted_but_still_completes():
    goal, script = get_scenario("long_search_session")
    llm = MockLLM(script)
    budget = Budget(max_steps=30)
    tool_registry = build_default_tool_registry()
    compact_config = {"trigger_every": 3, "keep_recent_count": 4, "exempt_tools": set()}

    result = run_agent(goal, tool_registry, llm, budget, compact_config)

    assert result == "8 个关键词都搜索完了。"
    assert llm.call_count == 9
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd v4 && python -m pytest tests/test_context_manager.py -v`
Expected: `ModuleNotFoundError: No module named 'harness.context_manager'`

- [ ] **Step 5: 实现 `v4/harness/context_manager.py`**

```python
"""v4：上下文裁剪——周期性清理旧的工具输出，支持按工具名豁免。"""


def compact_if_needed(messages, iteration, config):
    trigger_every = config["trigger_every"]
    if iteration % trigger_every != 0:
        return

    keep_recent = config["keep_recent_count"]
    exempt_tools = config.get("exempt_tools", set())

    for i in range(len(messages) - keep_recent):
        msg = messages[i]
        if msg["role"] != "tool":
            continue
        if msg.get("name") in exempt_tools:
            continue
        if msg["content"].startswith("[cleared:"):
            continue
        original_len = len(msg["content"])
        msg["content"] = f"[cleared: {original_len} chars]"
```

- [ ] **Step 6: 运行测试确认部分通过**

Run: `cd v4 && python -m pytest tests/test_context_manager.py -v`
Expected: 前两个测试通过；`test_long_search_session_gets_compacted_but_still_completes` 失败（`run_agent` 还不接受 `compact_config` 参数）。

- [ ] **Step 7: 修改 `v4/harness/loop.py`**

```python
"""v4：在 v3 的循环空转检测基础上加入上下文裁剪。"""

from harness.context_manager import compact_if_needed
from harness.loop_detector import detect_loop


def run_agent(goal, tool_registry, llm, budget, compact_config):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]
    call_history = []

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        loop_check = detect_loop(call_history)
        if loop_check["severity"] == "critical":
            blocked = loop_check["blocked_tool"]
            if blocked in tool_registry:
                del tool_registry[blocked]
            messages.append(
                {
                    "role": "system",
                    "content": f"[循环检测] {loop_check['reason']}。工具 {blocked} 已暂时禁用，请更换策略。",
                }
            )

        compact_if_needed(messages, budget.steps_used, compact_config)

        response = llm.chat(messages, tools=list(tool_registry.keys()))

        if not response["tool_calls"]:
            return response["content"]

        messages.append(
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            }
        )

        for call in response["tool_calls"]:
            tool = tool_registry[call["name"]]
            ok = True
            try:
                result = tool.run(call["args"])
            except Exception as exc:  # noqa: BLE001 - v1 尚无分类错误处理，见 v6/v8
                result = f"Error: {exc}"
                ok = False
            messages.append({"role": "tool", "name": call["name"], "content": result})
            call_history.append({"tool": call["name"], "args": call["args"], "ok": ok})
```

- [ ] **Step 8: 运行测试确认全部通过**

Run: `cd v4 && python -m pytest tests/test_context_manager.py -v`
Expected: `3 passed`

- [ ] **Step 9: 修改 `v4/main.py`**

```python
import argparse

from harness.budget import Budget
from harness.loop import run_agent
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import build_default_tool_registry

DEFAULT_COMPACT_CONFIG = {
    "trigger_every": 3,
    "keep_recent_count": 4,
    "exempt_tools": {"read_file"},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["happy_path", "runaway", "spin_then_recover", "long_search_session"],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    args = parser.parse_args()

    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)

    try:
        result = run_agent(goal, tool_registry, llm, budget, DEFAULT_COMPACT_CONFIG)
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: 手动验证**

Run: `cd v4 && python main.py --scenario long_search_session`
Expected:
```
[结果] 8 个关键词都搜索完了。
[LLM 调用次数] 9
```

- [ ] **Step 11: 创建 `v4/README.md`**

```markdown
# v4：上下文裁剪

## 本版目标

工具返回的结果会不断塞进消息列表，上下文窗口是硬性资源。这一版加入**周期性裁剪**：定期清理较旧的工具输出，只保留最近 N 条完整消息，并支持按工具名豁免（比如 `read_file` 的原文不能清，模型编辑代码要依赖它）。

## 新增/修改文件（对照 v3）

- 新增 `harness/context_manager.py`：`compact_if_needed(messages, iteration, config)`，每隔 `trigger_every` 轮触发一次裁剪，把 `keep_recent_count` 之前的旧 `tool` 消息内容替换成 `[cleared: N chars]` 占位标记，`exempt_tools` 里的工具名跳过。
- 修改 `harness/loop.py`：`run_agent()` 新增 `compact_config` 参数，在每轮调用 LLM 之前跑一次 `compact_if_needed`。
- 修改 `scenarios.py`：新增 `long_search_session`（连续 8 次搜索调用）用来触发裁剪。
- 修改 `main.py`：新增默认裁剪配置 `DEFAULT_COMPACT_CONFIG`（豁免 `read_file`）。
- 其余文件（`mock_llm.py`、`tools.py`、`harness/budget.py`、`harness/loop_detector.py`）与 v3 完全一致。

## 核心设计

裁剪策略必须可配置，因为"哪些内容能清"是业务相关的判断：搜索结果、日志这类一次性信息可以安全裁剪，但代码编辑类场景里 `read_file` 的原文清了模型就没法正确 `edit`。`exempt_tools` 就是为了把这个业务判断暴露成配置项，而不是写死在代码里。

裁剪只替换 `content`，不删除消息本身——保留消息结构（`role`、`name`）方便后续排查是"这一步确实调用过某个工具"，只是内容被清空了。

## 如何运行 demo

```bash
python main.py --scenario long_search_session
```

## 局限性

裁剪只是把旧内容换成一个短占位符，**并不会真正大幅压缩已经很长的单条消息**，也没有基于 token 数的整体水位控制——如果每条工具返回本身就很长，裁剪掉的这几条省下来的空间可能远远不够。而且目前完全没有对"整个上下文是不是已经太大了"做出判断和响应。这正是 v5 压缩安全阀要解决的问题：基于总量水位触发的全量摘要压缩，以及防止压缩本身失控的熔断机制。
```

- [ ] **Step 12: Commit**

```bash
cd Harness-from-scratch
git add v4/
git commit -m "feat(v4): periodic context compaction with per-tool exemptions"
```

---

## Task 5: v5 —— 压缩安全阀

**Files:**
- Copy from v4 (unchanged): `mock_llm.py`, `tools.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`
- Modify (relative to v4): `v5/harness/context_manager.py`, `v5/harness/loop.py`, `v5/scenarios.py`, `v5/main.py`
- Test: `v5/tests/test_compression_guard.py`
- Create: `v5/README.md`

- [ ] **Step 1: 复制未变化的文件**

```bash
cd Harness-from-scratch
cp v4/mock_llm.py v5/mock_llm.py
cp v4/tools.py v5/tools.py
cp v4/harness/__init__.py v5/harness/__init__.py
cp v4/harness/budget.py v5/harness/budget.py
cp v4/harness/loop_detector.py v5/harness/loop_detector.py
```

- [ ] **Step 2: 扩展 `v5/scenarios.py`（在 v4 场景基础上新增一个）**

在 v4 复制过来的 `SCENARIOS` 字典中新增：

```python
    # 每次工具返回一段 500 字符的超长文本，用来触发压缩安全阀：
    # 即使压缩后，保留的最近消息本身依然超过阈值，会连续压缩到熔断为止。
    "oversized_tool_output": (
        "反复查询一个返回超长内容的接口",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": f"call_{i}", "name": "search_web", "args": {"query": "big"}}
                ],
            }
            for i in range(10)
        ]
        + [{"content": "查询完成。", "tool_calls": []}],
    ),
```

同时修改 `v5/tools.py`（复制自 v4 后再改）：把 `search_web` 的返回值改成一段可配置长度的超长字符串，方便触发压缩：

```python
    def search_web(query):
        return f"搜索 '{query}' 的结果：" + ("x" * 500)
```

- [ ] **Step 3: 写失败测试 `v5/tests/test_compression_guard.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.context_manager import CompressionGuard, compress_history, needs_compression
from harness.loop import run_agent
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import build_default_tool_registry


def test_needs_compression_true_when_over_threshold():
    messages = [{"role": "tool", "name": "search_web", "content": "x" * 200}]
    assert needs_compression(messages, {"char_threshold": 100}) is True


def test_needs_compression_false_when_under_threshold():
    messages = [{"role": "tool", "name": "search_web", "content": "x" * 10}]
    assert needs_compression(messages, {"char_threshold": 100}) is False


def test_compress_history_keeps_system_and_recent_messages():
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "tool", "name": "search_web", "content": "old-1"},
        {"role": "tool", "name": "search_web", "content": "old-2"},
        {"role": "tool", "name": "search_web", "content": "recent"},
    ]
    compressed = compress_history(messages, keep_recent_count=1)
    assert compressed[0] == {"role": "system", "content": "system prompt"}
    assert "[compressed]" in compressed[1]["content"]
    assert compressed[-1]["content"] == "recent"


def test_compression_guard_trips_after_max_compressions():
    guard = CompressionGuard(max_compressions=3)
    for _ in range(3):
        assert guard.is_exhausted() is False
        guard.record_compression()
    assert guard.is_exhausted() is True


def test_oversized_output_scenario_trips_the_safety_valve():
    goal, script = get_scenario("oversized_tool_output")
    llm = MockLLM(script)
    budget = Budget(max_steps=30)
    tool_registry = build_default_tool_registry()
    compact_config = {"trigger_every": 100, "keep_recent_count": 100, "exempt_tools": set()}
    compression_config = {"char_threshold": 100, "max_compressions": 3, "keep_recent_count": 2}

    result = run_agent(
        goal, tool_registry, llm, budget, compact_config, compression_config
    )

    assert result == "上下文空间已耗尽，结束本轮对话"
```

`trigger_every: 100` / `keep_recent_count: 100` 让 v4 的裁剪机制在这个测试里几乎不触发（10 步远小于 100），这样测试只验证压缩安全阀本身，不和裁剪机制的效果混在一起。

- [ ] **Step 4: 运行测试确认失败**

Run: `cd v5 && python -m pytest tests/test_compression_guard.py -v`
Expected: `ImportError: cannot import name 'CompressionGuard' from 'harness.context_manager'`

- [ ] **Step 5: 修改 `v5/harness/context_manager.py`（在 v4 内容基础上追加）**

```python
"""v5：在 v4 的上下文裁剪基础上加入压缩安全阀。"""


def compact_if_needed(messages, iteration, config):
    trigger_every = config["trigger_every"]
    if iteration % trigger_every != 0:
        return

    keep_recent = config["keep_recent_count"]
    exempt_tools = config.get("exempt_tools", set())

    for i in range(len(messages) - keep_recent):
        msg = messages[i]
        if msg["role"] != "tool":
            continue
        if msg.get("name") in exempt_tools:
            continue
        if msg["content"].startswith("[cleared:"):
            continue
        original_len = len(msg["content"])
        msg["content"] = f"[cleared: {original_len} chars]"


def needs_compression(messages, config):
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    return total_chars > config["char_threshold"]


def compress_history(messages, keep_recent_count):
    system_msgs = [m for m in messages if m["role"] == "system"]
    non_system = [m for m in messages if m["role"] != "system"]
    kept = non_system[-keep_recent_count:] if keep_recent_count else []
    compressed_count = len(non_system) - len(kept)

    summary = {
        "role": "system",
        "content": f"[compressed] 已将 {compressed_count} 条历史消息压缩为摘要。",
    }
    return system_msgs + [summary] + kept


class CompressionGuard:
    """连续压缩次数熔断，防止「摘要的摘要」死循环。"""

    def __init__(self, max_compressions):
        self.max_compressions = max_compressions
        self.compression_count = 0

    def record_compression(self):
        self.compression_count += 1

    def is_exhausted(self):
        return self.compression_count >= self.max_compressions
```

- [ ] **Step 6: 运行测试确认部分通过**

Run: `cd v5 && python -m pytest tests/test_compression_guard.py -v`
Expected: 前 4 个测试通过；`test_oversized_output_scenario_trips_the_safety_valve` 失败（`run_agent` 还不接受 `compression_config`）。

- [ ] **Step 7: 修改 `v5/harness/loop.py`**

```python
"""v5：在 v4 的上下文裁剪基础上加入压缩安全阀。"""

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.loop_detector import detect_loop


def run_agent(goal, tool_registry, llm, budget, compact_config, compression_config):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]
    call_history = []
    compression_guard = CompressionGuard(compression_config["max_compressions"])

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        loop_check = detect_loop(call_history)
        if loop_check["severity"] == "critical":
            blocked = loop_check["blocked_tool"]
            if blocked in tool_registry:
                del tool_registry[blocked]
            messages.append(
                {
                    "role": "system",
                    "content": f"[循环检测] {loop_check['reason']}。工具 {blocked} 已暂时禁用，请更换策略。",
                }
            )

        compact_if_needed(messages, budget.steps_used, compact_config)

        if needs_compression(messages, compression_config):
            if compression_guard.is_exhausted():
                return "上下文空间已耗尽，结束本轮对话"
            messages = compress_history(
                messages, compression_config["keep_recent_count"]
            )
            compression_guard.record_compression()

        response = llm.chat(messages, tools=list(tool_registry.keys()))

        if not response["tool_calls"]:
            return response["content"]

        messages.append(
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            }
        )

        for call in response["tool_calls"]:
            tool = tool_registry[call["name"]]
            ok = True
            try:
                result = tool.run(call["args"])
            except Exception as exc:  # noqa: BLE001 - v1 尚无分类错误处理，见 v6/v8
                result = f"Error: {exc}"
                ok = False
            messages.append({"role": "tool", "name": call["name"], "content": result})
            call_history.append({"tool": call["name"], "args": call["args"], "ok": ok})
```

关键点：`compression_guard.is_exhausted()` 的判断放在**尝试压缩之前**——用完 `max_compressions` 次配额后，第 `max_compressions + 1` 次本该触发压缩的时候直接硬停，而不是先压缩再检查。

- [ ] **Step 8: 运行测试确认全部通过**

Run: `cd v5 && python -m pytest tests/test_compression_guard.py -v`
Expected: `5 passed`

- [ ] **Step 9: 修改 `v5/main.py`**

```python
import argparse

from harness.budget import Budget
from harness.loop import run_agent
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import build_default_tool_registry

DEFAULT_COMPACT_CONFIG = {
    "trigger_every": 3,
    "keep_recent_count": 4,
    "exempt_tools": {"read_file"},
}
DEFAULT_COMPRESSION_CONFIG = {
    "char_threshold": 4000,
    "max_compressions": 3,
    "keep_recent_count": 6,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        required=True,
        choices=[
            "happy_path",
            "runaway",
            "spin_then_recover",
            "long_search_session",
            "oversized_tool_output",
        ],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    args = parser.parse_args()

    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)

    try:
        result = run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: 手动验证**

Run: `cd v5 && python main.py --scenario oversized_tool_output --max-steps 30`
Expected（用默认的 `char_threshold=4000` 可能不会立刻触发压缩，属正常——CLI 默认配置偏保守，测试里用的是更容易触发的小阈值；这一步的重点是确认命令能跑通并给出结果，不强制要求命中安全阀）：
```
[结果] 查询完成。
[LLM 调用次数] 11
```

- [ ] **Step 11: 创建 `v5/README.md`**

```markdown
# v5：压缩安全阀

## 本版目标

v4 的周期性裁剪只是把旧消息换成占位符，省下来的空间有限。这一版加入基于总量水位的**全量摘要压缩**，以及压缩本身的**熔断机制**——防止摘要之后空间还是不够、于是又摘要、变成"摘要的摘要的摘要"最后把原始信息全部丢光的死循环。

## 新增/修改文件（对照 v4）

- 修改 `harness/context_manager.py`：新增 `needs_compression(messages, config)`（按总字符数估算是否超过高水位线）、`compress_history(messages, keep_recent_count)`（保留 system 消息 + 最近 N 条，其余压成一条摘要消息）、`CompressionGuard` 类（记录连续压缩次数，达到上限就报告耗尽）。
- 修改 `harness/loop.py`：`run_agent()` 新增 `compression_config` 参数；在裁剪之后、调用 LLM 之前检查是否需要压缩，命中且 `CompressionGuard` 未耗尽就压缩并计数，耗尽则直接终止。
- 修改 `scenarios.py` / `tools.py`：新增 `oversized_tool_output` 场景，工具返回一段超长字符串，用来在测试里稳定触发安全阀。
- 其余文件（`mock_llm.py`、`harness/budget.py`、`harness/loop_detector.py`）与 v4 完全一致。

## 核心设计

`needs_compression` 用字符数估算 token 占用，足够教学演示用；生产系统通常换成真实的 tokenizer 计数，接口形状不变。

`CompressionGuard` 独立成一个类而不是一个裸计数器，是延续 v2 `Budget` 的设计模式：一个对象只负责"记账 + 判断是否耗尽"。**熔断检查必须在压缩动作之前**——不能先压缩再判断，否则第 `max_compressions + 1` 次会白白再做一次无意义的压缩。

`compress_history` 不调用真实 LLM 做摘要（本项目全程不依赖网络），而是用一个确定性的占位摘要（"已将 N 条历史消息压缩为摘要"）代表"这里本该有一次真实的 LLM 摘要调用"。生产实现里这一步会换成对 LLM 的一次调用，压缩本身逻辑（保留 system + 最近 N 条、其余替换）保持不变。

## 如何运行 demo

```bash
python main.py --scenario oversized_tool_output --max-steps 30
```

## 局限性

现在系统一共有四层独立的防护（预算、循环检测、裁剪、压缩安全阀），但它们的顺序、交互、以及"发生冲突时听谁的"还没有专门验证过——目前只是简单地依次执行。如果模型输出的工具调用本身格式就有问题（比如调用了一个不存在的工具、或者漏填了必填参数），当前所有版本都没有防护，会在 `tool = tool_registry[call["name"]]` 这一步直接抛异常崩溃。这正是 v6 要解决的问题：执行工具之前先校验，校验失败把错误回填给模型而不是让进程崩溃。
```

- [ ] **Step 12: Commit**

```bash
cd Harness-from-scratch
git add v5/
git commit -m "feat(v5): compression safety valve against summarize-of-summary loops"
```

---

## Task 6: v6 —— 输出校验与自愈

**Files:**
- Copy from v5 (unchanged): `mock_llm.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`
- Create: `v6/harness/validator.py`
- Modify (relative to v5): `v6/harness/loop.py`, `v6/tools.py`, `v6/scenarios.py`, `v6/main.py`
- Test: `v6/tests/test_validator.py`
- Create: `v6/README.md`

- [ ] **Step 1: 复制未变化的文件**

```bash
cd Harness-from-scratch
cp v5/mock_llm.py v6/mock_llm.py
cp v5/harness/__init__.py v6/harness/__init__.py
cp v5/harness/budget.py v6/harness/budget.py
cp v5/harness/loop_detector.py v6/harness/loop_detector.py
cp v5/harness/context_manager.py v6/harness/context_manager.py
```

- [ ] **Step 2: 恢复 `v6/tools.py` 为 v3 版本的短返回值（v5 为了触发压缩把 `search_web` 改成了超长输出，这里改回正常长度，避免和本版本的测试断言打架）**

```python
"""示例工具集：内存态假文件系统 + 假搜索，配合 MockLLM 复现固定场景。"""


class Tool:
    def __init__(self, name, func, params=None):
        self.name = name
        self.func = func
        self.params = params or {}  # param_name -> {"required": bool}

    def run(self, args):
        return self.func(**args)


def _make_fake_fs():
    return {"config.yaml": "timeout: 30\nretries: 3\n"}


def build_default_tool_registry():
    fake_fs = _make_fake_fs()

    def read_file(path):
        if path not in fake_fs:
            raise FileNotFoundError(f"文件不存在: {path}")
        return fake_fs[path]

    def search_web(query):
        return f"搜索 '{query}' 的结果：暂无相关信息（mock 数据）。"

    def write_file(path, content):
        fake_fs[path] = content
        return f"已写入 {path}（{len(content)} 字符）"

    return {
        "read_file": Tool("read_file", read_file, {"path": {"required": True}}),
        "search_web": Tool("search_web", search_web, {"query": {"required": True}}),
        "write_file": Tool(
            "write_file",
            write_file,
            {"path": {"required": True}, "content": {"required": True}},
        ),
    }
```

- [ ] **Step 3: 扩展 `v6/scenarios.py`（沿用 v3 的四个场景 + 新增两个校验场景，去掉 v5 特有的 `oversized_tool_output`——本版本不需要它）**

`v6/scenarios.py` = v3 的 `SCENARIOS` 字典完整内容（`happy_path` / `runaway` / `spin_then_recover`）+ v4 的 `long_search_session`，再新增：

```python
    # 第 1 步漏填必填参数 path；第 2 步模型自纠，补上正确参数并成功。
    "missing_required_arg_then_fix": (
        "读取配置文件",
        [
            {
                "content": None,
                "tool_calls": [{"id": "call_1", "name": "read_file", "args": {}}],
            },
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_2", "name": "read_file", "args": {"path": "config.yaml"}}
                ],
            },
            {"content": "读取成功：timeout=30。", "tool_calls": []},
        ],
    ),
    # 连续 3 次调用一个不存在的工具，触发连续校验失败熔断。
    "unknown_tool_repeated": (
        "帮我删除所有临时文件",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": f"call_{i}", "name": "delete_everything", "args": {}}
                ],
            }
            for i in range(3)
        ],
    ),
```

- [ ] **Step 4: 写失败测试 `v6/tests/test_validator.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from harness.validator import validate_tool_call
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import build_default_tool_registry


def test_validate_tool_call_rejects_unknown_tool():
    registry = build_default_tool_registry()
    call = {"name": "delete_everything", "args": {}}
    result = validate_tool_call(call, registry)
    assert result["ok"] is False
    assert "未知工具" in result["error"]


def test_validate_tool_call_rejects_missing_required_arg():
    registry = build_default_tool_registry()
    call = {"name": "read_file", "args": {}}
    result = validate_tool_call(call, registry)
    assert result["ok"] is False
    assert "缺少必填参数" in result["error"]


def test_validate_tool_call_accepts_valid_call():
    registry = build_default_tool_registry()
    call = {"name": "read_file", "args": {"path": "config.yaml"}}
    result = validate_tool_call(call, registry)
    assert result["ok"] is True


def _run(scenario_name, max_steps=30):
    goal, script = get_scenario(scenario_name)
    llm = MockLLM(script)
    budget = Budget(max_steps=max_steps)
    registry = build_default_tool_registry()
    compact_config = {"trigger_every": 100, "keep_recent_count": 100, "exempt_tools": set()}
    compression_config = {
        "char_threshold": 100000,
        "max_compressions": 3,
        "keep_recent_count": 6,
    }
    result = run_agent(
        goal, registry, llm, budget, compact_config, compression_config
    )
    return result, llm.call_count


def test_missing_arg_scenario_self_corrects_after_validation_error():
    result, call_count = _run("missing_required_arg_then_fix")
    assert result == "读取成功：timeout=30。"
    assert call_count == 3


def test_unknown_tool_repeated_trips_consecutive_error_circuit_breaker():
    result, call_count = _run("unknown_tool_repeated")
    assert result == "连续校验失败，任务终止"
    assert call_count == 3
```

- [ ] **Step 5: 运行测试确认失败**

Run: `cd v6 && python -m pytest tests/test_validator.py -v`
Expected: `ModuleNotFoundError: No module named 'harness.validator'`

- [ ] **Step 6: 实现 `v6/harness/validator.py`**

```python
"""v6：工具调用输出校验——存在性 + 必填参数，供 run_agent 在执行前调用。"""


def validate_tool_call(call, tool_registry):
    tool_name = call["name"]
    if tool_name not in tool_registry:
        available = ", ".join(tool_registry.keys())
        return {"ok": False, "error": f"未知工具: {tool_name}。可用工具: {available}"}

    tool = tool_registry[tool_name]
    args = call.get("args", {})
    for param_name, spec in tool.params.items():
        if spec.get("required", True) and param_name not in args:
            return {"ok": False, "error": f"工具 {tool_name} 缺少必填参数: {param_name}"}

    return {"ok": True, "error": ""}
```

- [ ] **Step 7: 运行测试确认部分通过**

Run: `cd v6 && python -m pytest tests/test_validator.py -v`
Expected: 前 3 个纯函数测试通过；后 2 个集成测试失败（`run_agent` 还没有集成校验逻辑）。

- [ ] **Step 8: 修改 `v6/harness/loop.py`**

```python
"""v6：在 v5 的压缩安全阀基础上加入输出校验与自愈。"""

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.loop_detector import detect_loop
from harness.validator import validate_tool_call

MAX_CONSECUTIVE_ERRORS = 3


def run_agent(goal, tool_registry, llm, budget, compact_config, compression_config):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]
    call_history = []
    compression_guard = CompressionGuard(compression_config["max_compressions"])
    consecutive_errors = 0

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        loop_check = detect_loop(call_history)
        if loop_check["severity"] == "critical":
            blocked = loop_check["blocked_tool"]
            if blocked in tool_registry:
                del tool_registry[blocked]
            messages.append(
                {
                    "role": "system",
                    "content": f"[循环检测] {loop_check['reason']}。工具 {blocked} 已暂时禁用，请更换策略。",
                }
            )

        compact_if_needed(messages, budget.steps_used, compact_config)

        if needs_compression(messages, compression_config):
            if compression_guard.is_exhausted():
                return "上下文空间已耗尽，结束本轮对话"
            messages = compress_history(
                messages, compression_config["keep_recent_count"]
            )
            compression_guard.record_compression()

        response = llm.chat(messages, tools=list(tool_registry.keys()))

        if not response["tool_calls"]:
            return response["content"]

        messages.append(
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            }
        )

        for call in response["tool_calls"]:
            valid = validate_tool_call(call, tool_registry)
            if not valid["ok"]:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    return "连续校验失败，任务终止"
                messages.append({"role": "system", "content": f"[校验失败] {valid['error']}"})
                continue

            consecutive_errors = 0
            tool = tool_registry[call["name"]]
            ok = True
            try:
                result = tool.run(call["args"])
            except Exception as exc:  # noqa: BLE001 - 分类错误处理见 v8
                result = f"Error: {exc}"
                ok = False
            messages.append({"role": "tool", "name": call["name"], "content": result})
            call_history.append({"tool": call["name"], "args": call["args"], "ok": ok})
```

- [ ] **Step 9: 运行测试确认全部通过**

Run: `cd v6 && python -m pytest tests/test_validator.py -v`
Expected: `5 passed`

- [ ] **Step 10: 修改 `v6/main.py`**

```python
import argparse

from harness.budget import Budget
from harness.loop import run_agent
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import build_default_tool_registry

DEFAULT_COMPACT_CONFIG = {
    "trigger_every": 3,
    "keep_recent_count": 4,
    "exempt_tools": {"read_file"},
}
DEFAULT_COMPRESSION_CONFIG = {
    "char_threshold": 4000,
    "max_compressions": 3,
    "keep_recent_count": 6,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        required=True,
        choices=[
            "happy_path",
            "runaway",
            "spin_then_recover",
            "long_search_session",
            "missing_required_arg_then_fix",
            "unknown_tool_repeated",
        ],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    args = parser.parse_args()

    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)

    try:
        result = run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 11: 手动验证**

Run: `cd v6 && python main.py --scenario missing_required_arg_then_fix`
Expected:
```
[结果] 读取成功：timeout=30。
[LLM 调用次数] 3
```

Run: `cd v6 && python main.py --scenario unknown_tool_repeated`
Expected:
```
[结果] 连续校验失败，任务终止
[LLM 调用次数] 3
```

- [ ] **Step 12: 创建 `v6/README.md`**

```markdown
# v6：输出校验与自愈

## 本版目标

到 v5 为止，系统对"模型输出格式本身有问题"完全没有防护——调用不存在的工具、漏填必填参数，都会在 `tool_registry[call["name"]]` 这一步直接抛异常崩溃整个进程。这一版加入**执行前校验**：校验失败不崩溃，把错误信息回填给模型，让它在下一轮自己修正。

## 新增/修改文件（对照 v5）

- 新增 `harness/validator.py`：`validate_tool_call(call, tool_registry)`，检查工具是否存在、必填参数是否齐全。
- 修改 `harness/loop.py`：执行每个工具调用前先跑校验；失败则把错误信息以 `system` 消息回填并 `continue`（跳过这次执行），同时用 `consecutive_errors` 计数，达到 `MAX_CONSECUTIVE_ERRORS`（3 次）就终止；任意一次校验通过就把计数清零。
- 修改 `tools.py`：把 v5 里为了触发压缩而改成超长输出的 `search_web` 改回正常长度（v5 的改动是那个版本特有的演示需要）。
- 修改 `scenarios.py`：新增 `missing_required_arg_then_fix`（漏参数后自纠）和 `unknown_tool_repeated`（连续调用不存在的工具，触发熔断）。
- 其余文件（`mock_llm.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`）与 v5 完全一致。

## 核心设计

**为什么校验失败要 `continue` 而不是直接返回错误**：模型在同一轮里可能会有多个 `tool_calls`，一个校验失败不该连累同一轮里的其它合法调用。

**为什么用"连续"校验失败计数、而不是"累计"**：偶尔犯错很正常（模型确实会漏填参数），只要中间有一次成功就说明模型在自纠正，不该被历史上的失误拖累而提前终止；只有**连续**失败才说明模型陷入了某种系统性的困境。

## 如何运行 demo

```bash
python main.py --scenario missing_required_arg_then_fix   # 漏参数 -> 报错回填 -> 模型自纠 -> 成功
python main.py --scenario unknown_tool_repeated            # 连续调用不存在的工具 -> 3 次后熔断
```

## 局限性

现在预算、循环检测、上下文治理（裁剪+压缩安全阀）、输出校验这五层防护都已经分别实现并测试过，但**从未在同一个 `run_agent` 里同时跑过、验证过它们不会互相冲突**（比如循环检测删除工具的同时，校验层要不要也跟着更新可用工具列表）。这正是 v7 要做的事：把 v2~v6 整合成一个完整骨架，并用集成测试证明多层防护协同生效。
```

- [ ] **Step 13: Commit**

```bash
cd Harness-from-scratch
git add v6/
git commit -m "feat(v6): tool-call validation with self-correction feedback loop"
```

---

## Task 7: v7 —— 里程碑：整合版

**Files:**
- Copy from v6 (unchanged): `mock_llm.py`, `tools.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`, `harness/validator.py`
- Modify (relative to v6): `v7/harness/loop.py`, `v7/scenarios.py`, `v7/main.py`
- Test: `v7/tests/test_integration.py`
- Create: `v7/README.md`

这一版**不引入任何新机制**，只做一件事：证明 v2~v6 五层防护放进同一个 `run_agent` 里能协同工作、互不冲突。因为 v6 的 `harness/loop.py` 实际上已经包含了全部五层逻辑（一路累积过来的），v7 的 `loop.py` 内容与 v6 完全相同——变化的是**测试**（新增综合场景的集成测试）和**文档**（把整个系列的设计原则总结成一篇里程碑说明）。

- [ ] **Step 1: 复制未变化的文件（包括 loop.py——本版本不修改核心逻辑，只新增集成测试）**

```bash
cd Harness-from-scratch
cp v6/mock_llm.py v7/mock_llm.py
cp v6/tools.py v7/tools.py
cp v6/harness/__init__.py v7/harness/__init__.py
cp v6/harness/budget.py v7/harness/budget.py
cp v6/harness/loop_detector.py v7/harness/loop_detector.py
cp v6/harness/context_manager.py v7/harness/context_manager.py
cp v6/harness/validator.py v7/harness/validator.py
cp v6/harness/loop.py v7/harness/loop.py
cp v6/main.py v7/main.py
```

- [ ] **Step 2: 扩展 `v7/scenarios.py`（复制 v6 全部场景 + 新增一个综合场景）**

`v7/scenarios.py` = v6 的 `SCENARIOS` 字典完整内容，再新增：

```python
    # 综合场景：先触发循环检测（5 次调用同一坏工具被禁用），
    # 紧接着模型犯了一次校验错误（漏填参数）又自己纠正，
    # 最后正常完成——验证循环检测和输出校验在同一个 run 里不冲突。
    "combined_recovery": (
        "读取 bad.txt，失败就换个办法，然后总结配置文件",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "c1", "name": "read_file", "args": {"path": "bad.txt"}}
                ],
            }
        ]
        * 5
        + [
            # read_file 已被循环检测禁用；改用 write_file 但漏填 content。
            {
                "content": None,
                "tool_calls": [
                    {"id": "c6", "name": "write_file", "args": {"path": "note.txt"}}
                ],
            },
            # 校验失败回填后，模型补全参数重试。
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "c7",
                        "name": "write_file",
                        "args": {"path": "note.txt", "content": "已记录失败原因"},
                    }
                ],
            },
            {"content": "已完成：记录了失败原因并结束任务。", "tool_calls": []},
        ],
    ),
```

- [ ] **Step 3: 写失败测试 `v7/tests/test_integration.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import build_default_tool_registry

DEFAULT_COMPACT_CONFIG = {
    "trigger_every": 3,
    "keep_recent_count": 4,
    "exempt_tools": {"read_file"},
}
DEFAULT_COMPRESSION_CONFIG = {
    "char_threshold": 4000,
    "max_compressions": 3,
    "keep_recent_count": 6,
}


def _run(scenario_name, max_steps=30):
    goal, script = get_scenario(scenario_name)
    llm = MockLLM(script)
    budget = Budget(max_steps=max_steps)
    registry = build_default_tool_registry()
    result = run_agent(
        goal, registry, llm, budget, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
    )
    return result, llm.call_count, registry


def test_combined_scenario_survives_loop_detection_and_validation_together():
    result, call_count, registry = _run("combined_recovery")

    assert result == "已完成：记录了失败原因并结束任务。"
    assert call_count == 8
    assert "read_file" not in registry  # 循环检测确实禁用了它
    assert "write_file" in registry  # 校验失败没有连带禁用其它工具


def test_budget_is_still_the_ultimate_backstop_even_with_all_layers_enabled():
    # runaway 场景：50 步完全相同的调用。循环检测会在第 5 步就命中，
    # 但即使假设某一层防护失灵，预算也必须是兜底：调用次数不会超过 max_steps。
    goal, script = get_scenario("runaway")
    llm = MockLLM(script)
    budget = Budget(max_steps=10)
    registry = build_default_tool_registry()

    run_agent(
        goal, registry, llm, budget, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
    )

    assert llm.call_count <= 10


def test_all_five_layers_are_present_in_a_single_run_agent_call():
    # 回归测试：v1~v6 的既有场景在整合版里必须继续按各自版本的预期工作。
    happy_result, happy_calls, _ = _run("happy_path")
    assert happy_result == "配置文件内容：timeout=30, retries=3。"
    assert happy_calls == 2

    validation_result, validation_calls, _ = _run("unknown_tool_repeated")
    assert validation_result == "连续校验失败，任务终止"
    assert validation_calls == 3
```

- [ ] **Step 4: 运行测试确认状态**

Run: `cd v7 && python -m pytest tests/test_integration.py -v`
Expected: 由于 `loop.py` 已经是从 v6 复制过来的完整实现，这里预期直接 `3 passed`（v7 本身不改代码，只加测试证明既有实现是对的）。如果任意一个断言失败，说明 v2~v6 的某一层防护之间存在你之前没发现的交互问题——回到对应版本修一次根因，再把修好的文件同步复制到 v7（以及后续所有版本目录）。

- [ ] **Step 5: 手动验证**

Run: `cd v7 && python main.py --scenario combined_recovery`
Expected:
```
[结果] 已完成：记录了失败原因并结束任务。
[LLM 调用次数] 8
```

- [ ] **Step 6: 运行 v7 全部测试（复制过来的旧测试 + 新的集成测试）确保没有回归**

先把 v6 的定向测试也复制过来，保证 v7 目录本身能独立验证全部五层机制（而不只是集成测试）：

```bash
cd Harness-from-scratch
cp v3/tests/test_loop_detector.py v7/tests/test_loop_detector.py
cp v4/tests/test_context_manager.py v7/tests/test_context_manager.py
cp v5/tests/test_compression_guard.py v7/tests/test_compression_guard.py
cp v6/tests/test_validator.py v7/tests/test_validator.py
```

注意：`v4/tests/test_context_manager.py` 和 `v5/tests/test_compression_guard.py` 里分别 import 了各自版本当时的 `run_agent` 签名（v4 版不含 `compression_config`，v5 版不含校验层）。这两个文件复制到 v7 后需要手动调整：

- `v7/tests/test_context_manager.py` 里所有调用 `run_agent(...)` 的地方，补上 v7 签名要求的最后一个参数 `compression_config`（用本文件顶部的 `DEFAULT_COMPRESSION_CONFIG`，先在文件里定义好，取值同 `v7/tests/test_integration.py`）。
- `v5/tests/test_compression_guard.py` 复制过来的版本，`run_agent` 调用不需要额外改动（v5 签名已经包含 `compression_config`，且 v7 的签名与 v5/v6 相同）。
- `v3/tests/test_loop_detector.py` 复制过来的版本里，`test_spin_then_recover_scenario_disables_tool_and_switches_strategy` 调用的是 3 参数版 `run_agent(goal, registry, llm, budget)`，需要补上 v7 签名要求的 `compact_config`、`compression_config` 两个参数（用 `DEFAULT_COMPACT_CONFIG`、`DEFAULT_COMPRESSION_CONFIG`）。
- `v6/tests/test_validator.py` 复制过来的版本，`_run()` 辅助函数里的 `run_agent` 调用签名与 v7 一致，不需要改动。

Run: `cd v7 && python -m pytest tests/ -v`
Expected: 全部通过（具体用例数 = v3 的 3 个 + v4 的 3 个 + v5 的 5 个 + v6 的 5 个 + v7 新增的 3 个 = 19 个，实际数字以运行结果为准，全部 `passed` 即可）。

- [ ] **Step 7: 创建 `v7/README.md`**

```markdown
# v7：里程碑 —— 整合版

## 本版目标

v2~v6 分别实现了执行预算、循环空转检测、上下文裁剪、压缩安全阀、输出校验五层防护，但都是"单独验证"的。这一版不新增机制，只做一件事：**证明这五层放进同一个 `run_agent` 里可以协同工作，互不冲突**。这是参考文章"五、整合完整的 Harness 骨架"对应的版本。

## 新增/修改文件（对照 v6）

- `harness/loop.py`：与 v6 完全相同（v6 早已包含全部五层逻辑，这里不需要改代码）。
- `scenarios.py`：新增 `combined_recovery` 综合场景——先触发循环检测（连续 5 次坏调用被禁用），再触发一次校验失败又自纠，最后正常完成。
- `tests/`：新增 `test_integration.py`，并把 v3~v6 各自的定向测试也搬了过来，保证 v7 目录本身可以独立验证全部五层机制（而不需要跑去别的版本目录验证）。
- 其余文件（`mock_llm.py`、`tools.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`）与 v6 完全一致。

## 核心设计：五层防护的执行顺序

```
每一轮循环：
  1. 预算记账 + 超限检查        —— 最先执行，是最后的兜底
  2. 循环空转检测 + 处理        —— 在调用 LLM 之前，尽早识别原地打转
  3. 上下文裁剪                —— 控制窗口大小
  4. 压缩安全阀（含熔断判断）   —— 处理裁剪不够用的情况
  5. 调用 LLM
  6. 对每个 tool_call：先校验，通过才执行
```

顺序不是随意的：**预算检查必须最先**，因为不管其它层怎么判断，一旦超过硬上限就要立刻停，不能再多花一次 LLM 调用；**循环检测必须在调用 LLM 之前**，这样命中时可以在同一轮就把工具禁用、把提示注入进下一次的 `messages`；**上下文治理（裁剪 + 压缩）必须在调用 LLM 之前完成**，否则这一轮发出去的请求还是超长的。

## 如何运行 demo

```bash
python main.py --scenario combined_recovery
```

## 局限性

到目前为止的所有防护都是围绕"单个 Agent 循环本身"展开的——没有结构化的错误分类和重试退避（工具执行失败目前只是简单地把异常字符串塞进消息里）、没有会话持久化（进程一退出所有上下文就没了）、没有并发/流式、没有权限沙箱、没有可观测性统计、也不支持动态注册工具或多智能体协作。这些是 v8~v15 要陆续补齐的工业级能力，会在后续计划中展开。
```

- [ ] **Step 8: Commit**

```bash
cd Harness-from-scratch
git add v7/
git commit -m "feat(v7): integrate all five guardrails into one milestone skeleton"
```

---

## Task 8: 更新根目录 README 的路线图状态

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 把路线图表格里 v1~v7 的行确认为已完成状态**（表格内容在 Task 0 已经写好完整链接，这一步只需要确认 v1~v7 对应的 `README.md` 文件都已存在并可点击跳转，无需改动表格文字本身）

Run: `cd Harness-from-scratch && for v in v1 v2 v3 v4 v5 v6 v7; do test -f "$v/README.md" && echo "$v OK" || echo "$v MISSING"; done`
Expected: 全部输出 `OK`

- [ ] **Step 2: 跑一遍全部版本的测试套件，确认没有相互破坏**

```bash
cd Harness-from-scratch
for v in v1 v2 v3 v4 v5 v6 v7; do
  echo "=== $v ===" && (cd "$v" && python -m pytest tests/ -q) || exit 1
done
```

Expected: 每个版本都输出类似 `N passed`，没有 `FAILED` 或 `ERROR`。

- [ ] **Step 3: 如果 Step 2 全部通过，提交（如果 Task 0~7 已经把 README 内容写对，这一步通常不会有新的文件改动；如果有遗漏的修正，一并提交）**

```bash
cd Harness-from-scratch
git status
# 如果有未提交的改动：
git add -A
git commit -m "chore: verify v1-v7 test suites pass end-to-end"
```

---

## Self-Review 记录

- **Spec 覆盖**：设计文档里 v1~v7 的每一行路线图都对应一个 Task；目录结构（`main.py`/`mock_llm.py`/`real_llm_adapter.py`/`tools.py`/`harness/`/`scenarios/`/`tests/`/`README.md`）里，`real_llm_adapter.py` 在 v1~v7 计划中**暂未包含**——这是本计划的一个已知缩减：真实 LLM 适配层不影响任何一版要演示的防护机制本身，且不接入自动化测试，优先级低于把五层防护做扎实；补充 `real_llm_adapter.py` 可以作为 v1~v7 完成后的一个独立小任务，或放进 v8~v15 计划里一并处理。`scenarios/` 目录在实现中简化为单个 `scenarios.py` 文件（内容量小，拆成目录反而增加复杂度），与设计文档"目录结构示意"的精神一致（场景定义与核心逻辑分离），已在此说明。
- **占位符扫描**：全部任务的代码块均为完整实现，无 `TODO`/`TBD`。
- **类型一致性**：`run_agent()` 签名从 v1 的 `(goal, tool_registry, llm)` 逐版增加参数，到 v5~v7 固定为 `(goal, tool_registry, llm, budget, compact_config, compression_config)`；每个版本的 `main.py`、测试文件都已核对为对应版本的签名。`Tool`、`Budget`、`CompressionGuard` 的字段名在所有引用处保持一致。
