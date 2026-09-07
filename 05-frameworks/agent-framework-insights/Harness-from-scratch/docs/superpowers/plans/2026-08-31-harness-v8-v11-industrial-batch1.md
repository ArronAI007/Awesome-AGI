# 渐进式 Harness 教程：v8~v11 工业级扩展第一批 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `Harness-from-scratch/` 下实现 v8~v11 四个自包含、可运行的 Agent Harness 项目，在 v7 五层防护的基础上依次加入结构化错误处理与重试退避（v8）、会话持久化与断点续跑（v9）、并发工具调用与超时取消（v10，转为 async）、安全权限沙箱（v11）。

**Architecture:** v8/v9 延续 v1~v7 的同步风格，在已有的 `harness/loop.py` 上做增量修改；v10 把 `run_agent`、`MockLLM.chat`、`Tool.run` 全部转成 `async def`，同一轮内的多个 `tool_calls` 用 `asyncio.gather` 并发执行；v11 建在 v10 的 async 循环之上。每个版本仍然是完全自包含目录，未变化的文件用 `cp` 从上一版本复制，人工/外部干预点（重试等待、权限审批）都通过可替换的注入函数（`sleep_fn`、`approve_fn`）暴露，保持确定性可测试。每个版本一次或多次 commit。

**Tech Stack:** Python 3.11+ 标准库（`asyncio` 从 v10 起使用）、`pytest`（v10 起用 `pytest-asyncio` 或手写 `asyncio.run` 包装跑异步测试，本计划选择后者以保持零额外依赖）。

**依据的设计文档：** `docs/superpowers/specs/2026-08-28-progressive-harness-series-design.md` 中"实现记录：v8~v11 详细技术方案"章节。

---

## 关于本计划的约定

1. **起点是 v7**，已完成并合并到 main，位于 `Harness-from-scratch/v7/`。v8 的所有"复制"步骤都以 v7 为源。
2. **未变化文件用 `cp` 复制**，命令在任务里给出，不是占位符。
3. **测试运行方式统一**：`cd v{N} && python3 -m pytest tests/ -v`。v10/v11 的测试文件里用到的 async 测试函数，本计划用一个不依赖第三方库的小技巧执行：测试函数本身是普通的 `def test_xxx():`，函数体内部用 `asyncio.run(_async_body())` 包裹真正的异步逻辑——这样不需要安装 `pytest-asyncio` 插件，纯标准库即可跑。
4. **消息格式、`Tool`/`Budget`/`CompressionGuard`/`detect_loop`/`validate_tool_call` 的接口**与 v7 完全一致，本计划中所有新代码都在这套约定之上扩展，不改变已有签名（除非任务里明确说明"修改签名"）。
5. **提交前缀**：全部使用 `feat(v{N}):`。
6. **v8/v9 不需要 `--use-real-llm` 之类的开关**——本计划不引入真实 LLM 适配层（沿用 v1~v7 的既有简化，详见设计文档）。

---

## Task 8: v8 —— 结构化错误处理与重试退避

**Files:**
- Copy from v7 (unchanged): `mock_llm.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`, `harness/validator.py`
- Create: `harness/errors.py`, `harness/retry.py`
- Modify (relative to v7): `tools.py`, `harness/loop.py`, `scenarios.py`, `main.py`
- Test: `tests/test_retry.py`
- Create: `README.md`

- [ ] **Step 1: 复制未变化的文件**

```bash
cd Harness-from-scratch
cp v7/mock_llm.py v8/mock_llm.py
cp v7/harness/__init__.py v8/harness/__init__.py
cp v7/harness/budget.py v8/harness/budget.py
cp v7/harness/loop_detector.py v8/harness/loop_detector.py
cp v7/harness/context_manager.py v8/harness/context_manager.py
cp v7/harness/validator.py v8/harness/validator.py
```

- [ ] **Step 2: 创建 `v8/harness/errors.py`**

```python
"""v8：结构化错误分类——区分可重试与不可重试错误。"""


class TransientError(Exception):
    """可重试的临时性故障：网络超时、限流等。"""


def classify_error(exc):
    if isinstance(exc, TransientError):
        return "retryable"
    return "non_retryable"
```

- [ ] **Step 3: 创建 `v8/harness/retry.py`**

```python
"""v8：指数退避重试 + 单工具级熔断器。"""


def compute_backoff_delay(attempt, base_delay=1.0):
    return base_delay * (2 ** attempt)


class ToolCircuitBreaker:
    """按工具名记录连续失败次数，达到阈值就判定该工具熔断。"""

    def __init__(self, failure_threshold):
        self.failure_threshold = failure_threshold
        self.consecutive_failures = {}

    def record_success(self, tool_name):
        self.consecutive_failures[tool_name] = 0

    def record_failure(self, tool_name):
        self.consecutive_failures[tool_name] = (
            self.consecutive_failures.get(tool_name, 0) + 1
        )

    def is_tripped(self, tool_name):
        return self.consecutive_failures.get(tool_name, 0) >= self.failure_threshold
```

- [ ] **Step 4: 修改 `v8/tools.py`（在 v7 版本基础上新增 `flaky_api` 和 `always_fails_api` 两个工具）**

```python
"""示例工具集：内存态假文件系统 + 假搜索，配合 MockLLM 复现固定场景。"""

from harness.errors import TransientError


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
    flaky_state = {"attempts": 0}

    def read_file(path):
        if path not in fake_fs:
            raise FileNotFoundError(f"文件不存在: {path}")
        return fake_fs[path]

    def search_web(query):
        return f"搜索 '{query}' 的结果：暂无相关信息（mock 数据）。"

    def write_file(path, content):
        fake_fs[path] = content
        return f"已写入 {path}（{len(content)} 字符）"

    def flaky_api(query):
        flaky_state["attempts"] += 1
        if flaky_state["attempts"] <= 2:
            raise TransientError(f"临时故障（第 {flaky_state['attempts']} 次尝试）")
        return f"flaky_api 调用成功（第 {flaky_state['attempts']} 次尝试）：{query}"

    def always_fails_api(query):
        raise TransientError("这个接口一直不可用")

    return {
        "read_file": Tool("read_file", read_file, {"path": {"required": True}}),
        "search_web": Tool("search_web", search_web, {"query": {"required": True}}),
        "write_file": Tool(
            "write_file",
            write_file,
            {"path": {"required": True}, "content": {"required": True}},
        ),
        "flaky_api": Tool("flaky_api", flaky_api, {"query": {"required": True}}),
        "always_fails_api": Tool(
            "always_fails_api", always_fails_api, {"query": {"required": True}}
        ),
    }
```

- [ ] **Step 5: 扩展 `v8/scenarios.py`（复制 v7 全部 8 个场景 + 新增 3 个）**

先复制：

```bash
cp v7/scenarios.py v8/scenarios.py
```

然后在 `v8/scenarios.py` 的 `SCENARIOS` 字典里、`"combined_recovery"` 条目之后、闭合的 `}` 之前，插入以下三个新场景：

```python
    # flaky_api 前 2 次调用失败，第 3 次成功；重试发生在同一次工具调用内部，
    # 模型只看到 1 次 tool_calls，LLM 调用次数不受重试次数影响。
    "flaky_api_recovers": (
        "调用一次不稳定的接口并汇报结果",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "flaky_api", "args": {"query": "ping"}}
                ],
            },
            {"content": "flaky_api 最终调用成功。", "tool_calls": []},
        ],
    ),
    # read_file 对不存在的文件抛 FileNotFoundError，属于不可重试错误，
    # 应该立刻失败，不触发任何一次退避等待。
    "non_retryable_failure": (
        "尝试读取一个不存在的文件",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "missing.txt"}}
                ],
            },
            {"content": "文件不存在，已记录错误。", "tool_calls": []},
        ],
    ),
    # always_fails_api 永远失败：前 3 次调用各自内部重试 3 次后放弃（熔断计数
    # 逐次 +1），第 4 次调用时熔断已达到阈值 3，直接被拦截、不再产生任何重试。
    "circuit_breaker_trips": (
        "反复调用一个持续故障的接口",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": f"call_{i}", "name": "always_fails_api", "args": {"query": "x"}}
                ],
            }
            for i in range(4)
        ]
        + [{"content": "接口修复前先记录问题并结束。", "tool_calls": []}],
    ),
```

- [ ] **Step 6: 写失败测试 `v8/tests/test_retry.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.errors import TransientError, classify_error
from harness.loop import run_agent
from harness.retry import ToolCircuitBreaker, compute_backoff_delay
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


def test_classify_error_marks_transient_error_as_retryable():
    assert classify_error(TransientError("boom")) == "retryable"


def test_classify_error_marks_other_exceptions_as_non_retryable():
    assert classify_error(FileNotFoundError("missing")) == "non_retryable"


def test_compute_backoff_delay_doubles_each_attempt():
    assert compute_backoff_delay(0) == 1.0
    assert compute_backoff_delay(1) == 2.0
    assert compute_backoff_delay(2) == 4.0


def test_circuit_breaker_trips_after_threshold_failures():
    breaker = ToolCircuitBreaker(failure_threshold=3)
    for _ in range(3):
        assert breaker.is_tripped("flaky_api") is False
        breaker.record_failure("flaky_api")
    assert breaker.is_tripped("flaky_api") is True


def test_circuit_breaker_resets_on_success():
    breaker = ToolCircuitBreaker(failure_threshold=2)
    breaker.record_failure("flaky_api")
    breaker.record_success("flaky_api")
    assert breaker.is_tripped("flaky_api") is False


def _run(scenario_name, sleep_calls, max_steps=30):
    goal, script = get_scenario(scenario_name)
    llm = MockLLM(script)
    budget = Budget(max_steps=max_steps)
    registry = build_default_tool_registry()
    result = run_agent(
        goal,
        registry,
        llm,
        budget,
        DEFAULT_COMPACT_CONFIG,
        DEFAULT_COMPRESSION_CONFIG,
        sleep_fn=sleep_calls.append,
    )
    return result, llm.call_count


def test_flaky_api_recovers_after_retries_without_real_sleep():
    sleep_calls = []
    result, call_count = _run("flaky_api_recovers", sleep_calls)
    assert result == "flaky_api 最终调用成功。"
    assert call_count == 2
    assert sleep_calls == [1.0, 2.0]


def test_non_retryable_failure_never_sleeps():
    sleep_calls = []
    result, call_count = _run("non_retryable_failure", sleep_calls)
    assert result == "文件不存在，已记录错误。"
    assert call_count == 2
    assert sleep_calls == []


def test_circuit_breaker_trips_scenario_stops_retrying_after_threshold():
    sleep_calls = []
    result, call_count = _run("circuit_breaker_trips", sleep_calls)
    assert result == "接口修复前先记录问题并结束。"
    assert call_count == 5
    assert sleep_calls == [1.0, 2.0, 4.0] * 3
```

- [ ] **Step 7: 运行测试确认失败**

Run: `cd v8 && python3 -m pytest tests/test_retry.py -v`
Expected: 前 5 个纯函数测试（`classify_error` x2、`compute_backoff_delay`、`ToolCircuitBreaker` x2）通过；后 3 个集成测试报 `TypeError: run_agent() got an unexpected keyword argument 'sleep_fn'`（因为 `harness/loop.py` 还没有接入重试逻辑）。

- [ ] **Step 8: 修改 `v8/harness/loop.py`**

```python
"""v8：在 v7 的整合骨架基础上加入结构化错误处理与重试退避。"""

import time

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.errors import classify_error
from harness.loop_detector import detect_loop
from harness.retry import ToolCircuitBreaker, compute_backoff_delay
from harness.validator import validate_tool_call

MAX_CONSECUTIVE_ERRORS = 3
MAX_RETRIES = 3
CIRCUIT_BREAKER_THRESHOLD = 3


def run_agent(
    goal,
    tool_registry,
    llm,
    budget,
    compact_config,
    compression_config,
    sleep_fn=time.sleep,
):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]
    call_history = []
    compression_guard = CompressionGuard(compression_config["max_compressions"])
    consecutive_errors = 0
    circuit_breaker = ToolCircuitBreaker(CIRCUIT_BREAKER_THRESHOLD)

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

            if circuit_breaker.is_tripped(call["name"]):
                messages.append(
                    {
                        "role": "system",
                        "content": f"[熔断] 工具 {call['name']} 连续失败次数过多，已临时禁用",
                    }
                )
                continue

            consecutive_errors = 0
            tool = tool_registry[call["name"]]
            ok = True
            attempt = 0
            while True:
                try:
                    result = tool.run(call["args"])
                    circuit_breaker.record_success(call["name"])
                    break
                except Exception as exc:  # noqa: BLE001 - 分类结果决定是否重试
                    if classify_error(exc) == "retryable" and attempt < MAX_RETRIES:
                        sleep_fn(compute_backoff_delay(attempt))
                        attempt += 1
                        continue
                    result = f"Error: {exc}"
                    ok = False
                    circuit_breaker.record_failure(call["name"])
                    break
            messages.append({"role": "tool", "name": call["name"], "content": result})
            call_history.append({"tool": call["name"], "args": call["args"], "ok": ok})
```

关键点：`MAX_RETRIES = 3` 意味着最多重试 3 次、总共尝试 4 次（初次 + 3 次重试）。退避判断（`classify_error` + 重试次数）先于熔断记账——只有真正放弃时才 `record_failure`，重试过程中途的失败不计入熔断计数。

- [ ] **Step 9: 运行测试确认全部通过**

Run: `cd v8 && python3 -m pytest tests/test_retry.py -v`
Expected: `8 passed`

- [ ] **Step 10: 修改 `v8/main.py`**

```python
import argparse
import time

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
            "missing_required_arg_then_fix",
            "unknown_tool_repeated",
            "combined_recovery",
            "flaky_api_recovers",
            "non_retryable_failure",
            "circuit_breaker_trips",
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
            sleep_fn=time.sleep,
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

Run: `cd v8 && python3 main.py --scenario flaky_api_recovers`
Expected（会真的等待 1+2=3 秒，因为 CLI 用的是真实 `time.sleep`）：
```
[结果] flaky_api 最终调用成功。
[LLM 调用次数] 2
```

Run: `cd v8 && python3 main.py --scenario non_retryable_failure`
Expected（立刻返回，无等待）：
```
[结果] 文件不存在，已记录错误。
[LLM 调用次数] 2
```

不要求手动跑 `circuit_breaker_trips`（真实等待 1+2+4 秒 × 3 轮 ≈ 21 秒），自动化测试已经用假 `sleep_fn` 覆盖了这个场景；如果想手动看效果可以自行运行，属于可选项。

- [ ] **Step 12: 创建 `v8/README.md`**

```markdown
# v8：结构化错误处理与重试退避

## 本版目标

到 v7 为止，工具执行失败只是简单地把异常字符串塞进消息里，不区分"这是个可以重试的临时故障"还是"这是个重试也没用的根本性错误"，也没有机制防止对一个反复失败的工具无休止地浪费调用。这一版加入结构化错误分类、指数退避重试、以及单工具级熔断器。

## 新增/修改文件（对照 v7）

- 新增 `harness/errors.py`：`TransientError` 异常类 + `classify_error(exc)`，把异常分为 `"retryable"` / `"non_retryable"`。
- 新增 `harness/retry.py`：`compute_backoff_delay(attempt, base_delay)`（指数退避）+ `ToolCircuitBreaker`（按工具名记账连续失败次数，达到阈值后 `is_tripped()` 返回真）。
- 修改 `tools.py`：新增 `flaky_api`（前 2 次失败、第 3 次成功）和 `always_fails_api`（永远失败）两个工具，用于确定性地演示重试和熔断。
- 修改 `harness/loop.py`：执行工具调用改成一个内部重试循环——捕获异常后用 `classify_error` 判断，可重试且未超过 `MAX_RETRIES` 就调用 `sleep_fn` 退避后重试，否则记一次熔断失败；执行前先查熔断状态，命中直接拦截。`run_agent()` 新增 `sleep_fn` 参数（默认 `time.sleep`）。
- 修改 `scenarios.py`：新增 `flaky_api_recovers`、`non_retryable_failure`、`circuit_breaker_trips` 三个场景。
- 修改 `main.py`：`--scenario` 增加新场景，`run_agent` 调用传入 `sleep_fn=time.sleep`。
- 其余文件（`mock_llm.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`）与 v7 完全一致。

## 核心设计

**为什么退避等待要通过 `sleep_fn` 参数注入，而不是直接写死 `time.sleep`**：自动化测试如果真的等 1+2+4 秒会让整个测试套件变得很慢，而且熔断场景要跑 3 轮退避（共 21 秒）。注入一个可替换的睡眠函数，测试传入"记录调用参数但不真的睡"的假函数，既能验证退避延迟的计算是否正确，又不拖慢测试。CLI demo 默认用真实的 `time.sleep`，能实际感受到退避的效果。

**为什么"重试中途失败"不计入熔断，只有"最终放弃"才计入**：熔断器要回答的问题是"这个工具是不是已经彻底不可用了"，而不是"这个工具刚才抖了一下"。如果每次内部重试都计一次熔断失败，`always_fails_api` 一次调用内部重试 3 次就会瞬间触发熔断阈值 3，根本来不及体现"反复调用多轮后才熔断"的设计意图。

## 如何运行 demo

```bash
python3 main.py --scenario flaky_api_recovers      # 前 2 次失败，第 3 次成功，等待约 3 秒
python3 main.py --scenario non_retryable_failure   # 不可重试错误立刻失败，无等待
```

## 局限性

重试和熔断都是"进程内"的状态——`ToolCircuitBreaker` 在每次 `run_agent()` 调用时都是全新创建的，一旦进程重启，熔断记录和已经取得的进展全部丢失，下一次运行会从零开始重新累积失败次数。这正是 v9 要解决的问题：把消息历史落盘，支持进程重启后从断点续跑（虽然 v9 本身不会持久化熔断计数器，这一点会在 v9 的"局限性"里说明）。
```

- [ ] **Step 13: Commit**

```bash
cd Harness-from-scratch
git add v8/
git commit -m "feat(v8): structured error classification with retry backoff and circuit breaker"
```

---

## Task 9: v9 —— 会话持久化与断点续跑

**Files:**
- Copy from v8 (unchanged): `mock_llm.py`, `tools.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`, `harness/validator.py`, `harness/errors.py`, `harness/retry.py`
- Create: `harness/session_store.py`
- Modify (relative to v8): `harness/loop.py`, `scenarios.py`, `main.py`
- Test: `tests/test_session_store.py`
- Create: `README.md`

- [ ] **Step 1: 复制未变化的文件**

```bash
cd Harness-from-scratch
cp v8/mock_llm.py v9/mock_llm.py
cp v8/tools.py v9/tools.py
cp v8/harness/__init__.py v9/harness/__init__.py
cp v8/harness/budget.py v9/harness/budget.py
cp v8/harness/loop_detector.py v9/harness/loop_detector.py
cp v8/harness/context_manager.py v9/harness/context_manager.py
cp v8/harness/validator.py v9/harness/validator.py
cp v8/harness/errors.py v9/harness/errors.py
cp v8/harness/retry.py v9/harness/retry.py
```

- [ ] **Step 2: 创建 `v9/harness/session_store.py`**

```python
"""v9：会话持久化——把消息历史落盘为 JSONL，支持断点续跑。"""

import json


def append_message(session_path, message):
    with open(session_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(message, ensure_ascii=False) + "\n")


def load_session(session_path):
    if not session_path.exists():
        return []
    with open(session_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
```

- [ ] **Step 3: 扩展 `v9/scenarios.py`（复制 v8 全部 11 个场景 + 新增 2 个）**

```bash
cp v8/scenarios.py v9/scenarios.py
```

在 `SCENARIOS` 字典闭合的 `}` 之前插入：

```python
    # 用于演示断点续跑：这段脚本会在完成任务前耗尽，模拟进程崩溃。
    # 需要配合 --session-file 使用；崩溃后用 resume_phase2 场景 + 同一个
    # --session-file 续跑。
    "resume_phase1": (
        "读取配置文件并总结",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}}
                ],
            }
        ],
    ),
    # 续跑脚本：从 resume_phase1 崩溃的地方接着跑完。
    "resume_phase2": (
        "读取配置文件并总结",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_2", "name": "search_web", "args": {"query": "补充信息"}}
                ],
            },
            {"content": "配置文件内容：timeout=30, retries=3，并补充了搜索结果。", "tool_calls": []},
        ],
    ),
```

- [ ] **Step 4: 写失败测试 `v9/tests/test_session_store.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from harness.session_store import append_message, load_session
from mock_llm import MockLLM, ScriptExhausted
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


def test_append_message_writes_one_json_line_per_call(tmp_path):
    session_path = tmp_path / "session.jsonl"
    append_message(session_path, {"role": "system", "content": "a"})
    append_message(session_path, {"role": "user", "content": "b"})
    lines = session_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_load_session_returns_empty_list_when_file_missing(tmp_path):
    session_path = tmp_path / "missing.jsonl"
    assert load_session(session_path) == []


def test_load_session_round_trips_messages(tmp_path):
    session_path = tmp_path / "session.jsonl"
    append_message(session_path, {"role": "system", "content": "你是一个通用任务助手。"})
    append_message(session_path, {"role": "user", "content": "读取配置文件并总结"})
    loaded = load_session(session_path)
    assert loaded == [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": "读取配置文件并总结"},
    ]


def test_crash_then_resume_completes_with_full_message_history(tmp_path):
    session_path = tmp_path / "session.jsonl"
    goal = "读取配置文件并总结"

    phase1_script = [
        {
            "content": None,
            "tool_calls": [
                {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}}
            ],
        }
    ]
    llm_phase1 = MockLLM(phase1_script)
    budget_phase1 = Budget(max_steps=30)
    registry = build_default_tool_registry()

    crashed = False
    try:
        run_agent(
            goal,
            registry,
            llm_phase1,
            budget_phase1,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            session_path=session_path,
        )
    except ScriptExhausted:
        crashed = True

    assert crashed, "phase 1 脚本应该在完成任务前就耗尽，模拟进程崩溃"
    messages_after_crash = load_session(session_path)
    assert len(messages_after_crash) == 4  # system, user, assistant, tool

    phase2_script = [
        {
            "content": None,
            "tool_calls": [
                {"id": "call_2", "name": "search_web", "args": {"query": "补充信息"}}
            ],
        },
        {"content": "配置文件内容：timeout=30, retries=3，并补充了搜索结果。", "tool_calls": []},
    ]
    llm_phase2 = MockLLM(phase2_script)
    budget_phase2 = Budget(max_steps=30)

    result = run_agent(
        goal,
        registry,
        llm_phase2,
        budget_phase2,
        DEFAULT_COMPACT_CONFIG,
        DEFAULT_COMPRESSION_CONFIG,
        session_path=session_path,
    )

    assert result == "配置文件内容：timeout=30, retries=3，并补充了搜索结果。"
    assert llm_phase2.call_count == 2
    messages_after_resume = load_session(session_path)
    assert len(messages_after_resume) == 6  # 4 条旧的 + assistant + tool 各一条新的
    assert messages_after_resume[:4] == messages_after_crash
```

`tmp_path` 是 pytest 内置 fixture（每个测试自动分配一个临时目录），不需要额外依赖。

- [ ] **Step 5: 运行测试确认部分通过**

Run: `cd v9 && python3 -m pytest tests/test_session_store.py -v`
Expected: 前 3 个测试（`test_append_message_...`、`test_load_session_returns_empty_...`、`test_load_session_round_trips_...`）通过；`test_crash_then_resume_completes_with_full_message_history` 失败，报 `TypeError: run_agent() got an unexpected keyword argument 'session_path'`（因为 `harness/loop.py` 还没有接入持久化）。

- [ ] **Step 6: 修改 `v9/harness/loop.py`**

```python
"""v9：在 v8 的重试退避基础上加入会话持久化与断点续跑。"""

import time

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.errors import classify_error
from harness.loop_detector import detect_loop
from harness.retry import ToolCircuitBreaker, compute_backoff_delay
from harness.session_store import append_message, load_session
from harness.validator import validate_tool_call

MAX_CONSECUTIVE_ERRORS = 3
MAX_RETRIES = 3
CIRCUIT_BREAKER_THRESHOLD = 3


def _add_message(messages, message, session_path):
    messages.append(message)
    if session_path is not None:
        append_message(session_path, message)


def run_agent(
    goal,
    tool_registry,
    llm,
    budget,
    compact_config,
    compression_config,
    sleep_fn=time.sleep,
    session_path=None,
):
    existing = load_session(session_path) if session_path is not None else []
    if existing:
        messages = existing
    else:
        messages = []
        _add_message(
            messages, {"role": "system", "content": "你是一个通用任务助手。"}, session_path
        )
        _add_message(messages, {"role": "user", "content": goal}, session_path)

    call_history = []
    compression_guard = CompressionGuard(compression_config["max_compressions"])
    consecutive_errors = 0
    circuit_breaker = ToolCircuitBreaker(CIRCUIT_BREAKER_THRESHOLD)

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        loop_check = detect_loop(call_history)
        if loop_check["severity"] == "critical":
            blocked = loop_check["blocked_tool"]
            if blocked in tool_registry:
                del tool_registry[blocked]
            _add_message(
                messages,
                {
                    "role": "system",
                    "content": f"[循环检测] {loop_check['reason']}。工具 {blocked} 已暂时禁用，请更换策略。",
                },
                session_path,
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

        _add_message(
            messages,
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            },
            session_path,
        )

        for call in response["tool_calls"]:
            valid = validate_tool_call(call, tool_registry)
            if not valid["ok"]:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    return "连续校验失败，任务终止"
                _add_message(
                    messages,
                    {"role": "system", "content": f"[校验失败] {valid['error']}"},
                    session_path,
                )
                continue

            if circuit_breaker.is_tripped(call["name"]):
                _add_message(
                    messages,
                    {
                        "role": "system",
                        "content": f"[熔断] 工具 {call['name']} 连续失败次数过多，已临时禁用",
                    },
                    session_path,
                )
                continue

            consecutive_errors = 0
            tool = tool_registry[call["name"]]
            ok = True
            attempt = 0
            while True:
                try:
                    result = tool.run(call["args"])
                    circuit_breaker.record_success(call["name"])
                    break
                except Exception as exc:  # noqa: BLE001 - 分类结果决定是否重试
                    if classify_error(exc) == "retryable" and attempt < MAX_RETRIES:
                        sleep_fn(compute_backoff_delay(attempt))
                        attempt += 1
                        continue
                    result = f"Error: {exc}"
                    ok = False
                    circuit_breaker.record_failure(call["name"])
                    break
            _add_message(
                messages,
                {"role": "tool", "name": call["name"], "content": result},
                session_path,
            )
            call_history.append({"tool": call["name"], "args": call["args"], "ok": ok})
```

注意：`messages = compress_history(...)` 这一行发生"整体替换"（v5 起就是这样），不会经过 `_add_message`，所以如果运行中触发了压缩，落盘的 JSONL 文件不会同步这次替换——文件里仍然是压缩前的完整历史。这是刻意的简化（JSONL 追加写入的模型天然不适合处理"整体替换"），会写进本版本 README 的"局限性"，测试和 demo 场景都选择了不会触发压缩的短小脚本来避免这个交互。

- [ ] **Step 7: 运行测试确认全部通过**

Run: `cd v9 && python3 -m pytest tests/test_session_store.py -v`
Expected: `4 passed`

- [ ] **Step 8: 修改 `v9/main.py`**

```python
import argparse
import time
from pathlib import Path

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
            "missing_required_arg_then_fix",
            "unknown_tool_repeated",
            "combined_recovery",
            "flaky_api_recovers",
            "non_retryable_failure",
            "circuit_breaker_trips",
            "resume_phase1",
            "resume_phase2",
        ],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--session-file",
        type=str,
        default=None,
        help="会话落盘路径；指定后支持断点续跑",
    )
    args = parser.parse_args()

    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)
    session_path = Path(args.session_file) if args.session_file else None

    try:
        result = run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            sleep_fn=time.sleep,
            session_path=session_path,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: 手动验证（两次调用模拟"崩溃-续跑"）**

Run: `cd v9 && python3 main.py --scenario resume_phase1 --session-file /tmp/harness-v9-demo.jsonl`
Expected:
```
[未停止] MockLLM 脚本只有 1 步，但被调用了第 2 次
[LLM 调用次数] 1
```

Run: `wc -l /tmp/harness-v9-demo.jsonl`
Expected: `4 /tmp/harness-v9-demo.jsonl`

Run: `cd v9 && python3 main.py --scenario resume_phase2 --session-file /tmp/harness-v9-demo.jsonl`
Expected:
```
[结果] 配置文件内容：timeout=30, retries=3，并补充了搜索结果。
[LLM 调用次数] 2
```

Run: `wc -l /tmp/harness-v9-demo.jsonl`
Expected: `6 /tmp/harness-v9-demo.jsonl`

Run: `rm /tmp/harness-v9-demo.jsonl`（清理演示产生的临时文件）

- [ ] **Step 10: 创建 `v9/README.md`**

```markdown
# v9：会话持久化与断点续跑

## 本版目标

到 v8 为止，进程一旦退出，所有上下文就彻底丢失，下次只能从头开始。这一版把消息历史落盘为 JSONL，支持"进程崩溃/重启后从断点继续跑"，而不需要重新走一遍已经完成的步骤。

## 新增/修改文件（对照 v8）

- 新增 `harness/session_store.py`：`append_message(session_path, message)`（追加写入一行 JSON）、`load_session(session_path)`（文件不存在返回空列表，否则按行解析）。
- 修改 `harness/loop.py`：`run_agent()` 新增可选 `session_path` 参数。启动时如果该路径存在历史记录就直接加载、跳过初始化；此后每一条新增到 `messages` 的消息都通过内部的 `_add_message()` 辅助函数同步落盘。
- 修改 `scenarios.py`：新增 `resume_phase1`（脚本会在完成任务前耗尽，模拟崩溃）和 `resume_phase2`（从崩溃点接着跑完）两个场景，专门用来演示断点续跑。
- 修改 `main.py`：新增 `--session-file` 参数。
- 其余文件（`mock_llm.py`、`tools.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`、`harness/errors.py`、`harness/retry.py`）与 v8 完全一致。

## 核心设计

**为什么选 JSONL 而不是一次性写一个大 JSON 文件**：JSONL（每行一条 JSON）天然支持"追加写入"——每产生一条新消息就 `open(path, "a")` 写一行，不需要每次都读出整个文件、反序列化、修改、再整体写回。这对一个会持续增长的消息历史来说更自然，也更接近真实系统的日志/事件流设计。

**为什么用"脚本切成两段、跑两次 `run_agent()`"来测试断点续跑，而不是真的杀掉进程**：`MockLLM` 本身不感知历史，只按调用次数顺序吐出预设响应；真正测试价值在于验证"`run_agent()` 加载已有消息历史后，能不能正确地从那个点继续，而不是重新初始化"。用两个独立的 `MockLLM` 实例（各自 `call_count` 从 0 开始，但脚本内容分别是前后两段）分两次调用 `run_agent()`，配合同一个 `session_path`，就足以证明这一点，而不需要真的操作系统级别地杀掉进程。

## 如何运行 demo

```bash
python3 main.py --scenario resume_phase1 --session-file /tmp/demo.jsonl   # 模拟"崩溃"，文件里落了 4 条消息
python3 main.py --scenario resume_phase2 --session-file /tmp/demo.jsonl   # 续跑，文件变成 6 条消息
```

## 局限性

只有消息历史本身被持久化。`Budget`、`ToolCircuitBreaker` 等运行时计数器在每次 `run_agent()` 调用时都是全新创建的，进程重启后这些计数器会清零重新累积——这是刻意的简化，真实系统如果需要严格保留这些状态需要额外的持久化设计。另外，如果运行中触发了 v5 的压缩安全阀（`compress_history` 整体替换 `messages`），落盘的 JSONL 文件不会同步这次替换，文件里仍然是压缩前的完整历史——这是 JSONL 只支持追加写入这个设计选择本身带来的局限，本版本的测试和 demo 场景都刻意选择了不会触发压缩的短小脚本来避开这个交互。这两点都不影响本版本要证明的核心能力："消息历史可以正确地持久化和恢复"。
```

- [ ] **Step 11: Commit**

```bash
cd Harness-from-scratch
git add v9/
git commit -m "feat(v9): session persistence with JSONL history and crash-resume support"
```

---

## Task 10: v10 —— 并发工具调用 + 超时取消（转为 async）

**Files:**
- Copy from v9 (unchanged): `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`, `harness/validator.py`, `harness/errors.py`, `harness/retry.py`, `harness/session_store.py`
- Modify (relative to v9): `mock_llm.py`, `tools.py`, `harness/loop.py`, `scenarios.py`, `main.py`
- Test: `tests/test_concurrency.py`
- Create: `README.md`

这一版是本批次里最大的一次重构：`run_agent`、`MockLLM.chat`、`Tool.run` 全部从同步改成 `async def`。因为改动面广，这里不追求"改一个函数、看一个测试变绿"式的精细 TDD 节奏，而是先完成整体的 async 化改造，再用一组新测试证明并发、超时取消、以及此前版本的重试/会话持久化能力在 async 化之后仍然正确。

- [ ] **Step 1: 复制未受 async 改造影响的文件**

```bash
cd Harness-from-scratch
cp v9/harness/__init__.py v10/harness/__init__.py
cp v9/harness/budget.py v10/harness/budget.py
cp v9/harness/loop_detector.py v10/harness/loop_detector.py
cp v9/harness/context_manager.py v10/harness/context_manager.py
cp v9/harness/validator.py v10/harness/validator.py
cp v9/harness/errors.py v10/harness/errors.py
cp v9/harness/retry.py v10/harness/retry.py
cp v9/harness/session_store.py v10/harness/session_store.py
```

这 8 个文件都是纯逻辑/纯 IO 辅助函数，不涉及"调用 LLM"或"执行工具"这两个真正需要并发/超时的动作，所以原样保留、不用改成 async。

- [ ] **Step 2: 修改 `v10/mock_llm.py`（`chat` 改成 `async def`）**

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

    async def chat(self, messages, tools=None):
        if self.call_count >= len(self.script):
            raise ScriptExhausted(
                f"MockLLM 脚本只有 {len(self.script)} 步，但被调用了第 {self.call_count + 1} 次"
            )
        response = self.script[self.call_count]
        self.call_count += 1
        return response
```

- [ ] **Step 3: 修改 `v10/tools.py`（`Tool.run` 和所有工具函数改成 `async def`，新增 `ConcurrencyTracker` 和 `slow_tool`）**

```python
"""示例工具集：内存态假文件系统 + 假搜索，配合 MockLLM 复现固定场景。"""

import asyncio

from harness.errors import TransientError


class Tool:
    def __init__(self, name, func, params=None):
        self.name = name
        self.func = func
        self.params = params or {}  # param_name -> {"required": bool}

    async def run(self, args):
        return await self.func(**args)


class ConcurrencyTracker:
    """记录同一时刻有多少个工具调用正在执行，用来证明"真的并发了"而不是靠计时猜测。"""

    def __init__(self):
        self.active = 0
        self.peak = 0

    def enter(self):
        self.active += 1
        self.peak = max(self.peak, self.active)

    def exit(self):
        self.active -= 1


def _make_fake_fs():
    return {"config.yaml": "timeout: 30\nretries: 3\n"}


def build_default_tool_registry(concurrency_tracker=None):
    fake_fs = _make_fake_fs()
    flaky_state = {"attempts": 0}

    async def read_file(path):
        if concurrency_tracker is not None:
            concurrency_tracker.enter()
        try:
            await asyncio.sleep(0.01)
            if path not in fake_fs:
                raise FileNotFoundError(f"文件不存在: {path}")
            return fake_fs[path]
        finally:
            if concurrency_tracker is not None:
                concurrency_tracker.exit()

    async def search_web(query):
        if concurrency_tracker is not None:
            concurrency_tracker.enter()
        try:
            await asyncio.sleep(0.01)
            return f"搜索 '{query}' 的结果：暂无相关信息（mock 数据）。"
        finally:
            if concurrency_tracker is not None:
                concurrency_tracker.exit()

    async def write_file(path, content):
        fake_fs[path] = content
        return f"已写入 {path}（{len(content)} 字符）"

    async def flaky_api(query):
        flaky_state["attempts"] += 1
        if flaky_state["attempts"] <= 2:
            raise TransientError(f"临时故障（第 {flaky_state['attempts']} 次尝试）")
        return f"flaky_api 调用成功（第 {flaky_state['attempts']} 次尝试）：{query}"

    async def always_fails_api(query):
        raise TransientError("这个接口一直不可用")

    async def slow_tool(query):
        await asyncio.sleep(0.2)
        return f"slow_tool 终于处理完了：{query}"

    return {
        "read_file": Tool("read_file", read_file, {"path": {"required": True}}),
        "search_web": Tool("search_web", search_web, {"query": {"required": True}}),
        "write_file": Tool(
            "write_file",
            write_file,
            {"path": {"required": True}, "content": {"required": True}},
        ),
        "flaky_api": Tool("flaky_api", flaky_api, {"query": {"required": True}}),
        "always_fails_api": Tool(
            "always_fails_api", always_fails_api, {"query": {"required": True}}
        ),
        "slow_tool": Tool("slow_tool", slow_tool, {"query": {"required": True}}),
    }
```

`build_default_tool_registry()` 新增的 `concurrency_tracker` 参数是可选的（默认 `None`），不传时行为和之前完全一样——现有场景和测试不需要改动调用方式。

- [ ] **Step 4: 扩展 `v10/scenarios.py`（复制 v9 全部 13 个场景 + 新增 2 个）**

```bash
cp v9/scenarios.py v10/scenarios.py
```

在 `SCENARIOS` 字典闭合的 `}` 之前插入：

```python
    # 一轮 LLM 响应里同时给出 2 个互相独立的 tool_calls，验证它们并发执行。
    "parallel_tools": (
        "同时读取配置文件并搜索补充信息",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}},
                    {"id": "call_2", "name": "search_web", "args": {"query": "补充信息"}},
                ],
            },
            {"content": "已并发完成两个调用。", "tool_calls": []},
        ],
    ),
    # slow_tool 耗时 0.2 秒；配合很短的 timeout_seconds 验证超时取消生效，
    # 而不是让整个运行卡住。
    "slow_tool_timeout": (
        "调用一个可能很慢的工具",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "slow_tool", "args": {"query": "big-job"}}
                ],
            },
            {"content": "慢工具超时了，已记录并结束。", "tool_calls": []},
        ],
    ),
```

- [ ] **Step 5: 写测试 `v10/tests/test_concurrency.py`**

```python
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from harness.session_store import load_session
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import ConcurrencyTracker, build_default_tool_registry

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


class RecordingSleep:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)


def test_parallel_tools_scenario_runs_calls_concurrently():
    async def scenario_body():
        goal, script = get_scenario("parallel_tools")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        tracker = ConcurrencyTracker()
        registry = build_default_tool_registry(concurrency_tracker=tracker)

        result = await run_agent(
            goal, registry, llm, budget, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
        )

        assert result == "已并发完成两个调用。"
        assert tracker.peak >= 2

    asyncio.run(scenario_body())


def test_slow_tool_gets_cancelled_by_timeout_instead_of_hanging():
    async def scenario_body():
        goal, script = get_scenario("slow_tool_timeout")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry()

        result = await run_agent(
            goal,
            registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            timeout_seconds=0.05,
        )

        assert result == "慢工具超时了，已记录并结束。"

    asyncio.run(scenario_body())


def test_flaky_api_retry_still_works_with_injected_async_sleep_fn():
    async def scenario_body():
        goal, script = get_scenario("flaky_api_recovers")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry()
        sleep_fn = RecordingSleep()

        result = await run_agent(
            goal,
            registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            sleep_fn=sleep_fn,
        )

        assert result == "flaky_api 最终调用成功。"
        assert sleep_fn.calls == [1.0, 2.0]

    asyncio.run(scenario_body())


def test_circuit_breaker_still_trips_after_async_conversion():
    async def scenario_body():
        goal, script = get_scenario("circuit_breaker_trips")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry()
        sleep_fn = RecordingSleep()

        result = await run_agent(
            goal,
            registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            sleep_fn=sleep_fn,
        )

        assert result == "接口修复前先记录问题并结束。"
        assert llm.call_count == 5
        assert sleep_fn.calls == [1.0, 2.0, 4.0] * 3

    asyncio.run(scenario_body())


def test_session_persistence_still_works_after_async_conversion(tmp_path):
    async def scenario_body():
        session_path = tmp_path / "session.jsonl"
        goal = "读取配置文件并总结"
        phase1_script = [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}}
                ],
            }
        ]
        llm_phase1 = MockLLM(phase1_script)
        budget_phase1 = Budget(max_steps=30)
        registry = build_default_tool_registry()

        crashed = False
        try:
            await run_agent(
                goal,
                registry,
                llm_phase1,
                budget_phase1,
                DEFAULT_COMPACT_CONFIG,
                DEFAULT_COMPRESSION_CONFIG,
                session_path=session_path,
            )
        except ScriptExhausted:
            crashed = True

        assert crashed
        assert len(load_session(session_path)) == 4

    asyncio.run(scenario_body())
```

用 `asyncio.run(scenario_body())` 包一层普通的 `def test_xxx():` 是本计划选择的 async 测试写法——不需要安装 `pytest-asyncio`，纯标准库即可运行，每个测试内部的异步逻辑封装在一个 async 内嵌函数里。

- [ ] **Step 6: 运行测试确认失败**

Run: `cd v10 && python3 -m pytest tests/test_concurrency.py -v`
Expected: 全部失败。此时 `harness/loop.py` 还是从 v9 复制过来的同步版本，`await run_agent(...)` 会先同步执行整个函数体——函数体内部 `response = llm.chat(...)` 拿到的是一个协程对象而不是真正的响应字典，紧接着 `response["tool_calls"]` 会报类似 `TypeError: 'coroutine' object is not subscriptable` 的错误。具体报错文本不重要，5 个测试全部失败即为预期状态。

- [ ] **Step 7: 修改 `v10/harness/loop.py`（完整 async 重写）**

```python
"""v10：把 run_agent 转为 async，同一轮内的多个 tool_calls 并发执行，并支持超时取消。"""

import asyncio

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.errors import classify_error
from harness.loop_detector import detect_loop
from harness.retry import ToolCircuitBreaker, compute_backoff_delay
from harness.session_store import append_message, load_session
from harness.validator import validate_tool_call

MAX_CONSECUTIVE_ERRORS = 3
MAX_RETRIES = 3
CIRCUIT_BREAKER_THRESHOLD = 3
DEFAULT_TOOL_TIMEOUT = 5.0


def _add_message(messages, message, session_path):
    messages.append(message)
    if session_path is not None:
        append_message(session_path, message)


async def _execute_call(call, tool_registry, circuit_breaker, sleep_fn, timeout_seconds):
    tool = tool_registry[call["name"]]
    attempt = 0
    while True:
        try:
            result = await asyncio.wait_for(
                tool.run(call["args"]), timeout=timeout_seconds
            )
            circuit_breaker.record_success(call["name"])
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": True,
                "content": result,
            }
        except asyncio.TimeoutError:
            circuit_breaker.record_failure(call["name"])
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": False,
                "content": f"Error: 工具 {call['name']} 执行超过 {timeout_seconds} 秒，已取消",
            }
        except Exception as exc:  # noqa: BLE001 - 分类结果决定是否重试
            if classify_error(exc) == "retryable" and attempt < MAX_RETRIES:
                await sleep_fn(compute_backoff_delay(attempt))
                attempt += 1
                continue
            circuit_breaker.record_failure(call["name"])
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": False,
                "content": f"Error: {exc}",
            }


async def run_agent(
    goal,
    tool_registry,
    llm,
    budget,
    compact_config,
    compression_config,
    sleep_fn=asyncio.sleep,
    session_path=None,
    timeout_seconds=DEFAULT_TOOL_TIMEOUT,
):
    existing = load_session(session_path) if session_path is not None else []
    if existing:
        messages = existing
    else:
        messages = []
        _add_message(
            messages, {"role": "system", "content": "你是一个通用任务助手。"}, session_path
        )
        _add_message(messages, {"role": "user", "content": goal}, session_path)

    call_history = []
    compression_guard = CompressionGuard(compression_config["max_compressions"])
    consecutive_errors = 0
    circuit_breaker = ToolCircuitBreaker(CIRCUIT_BREAKER_THRESHOLD)

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        loop_check = detect_loop(call_history)
        if loop_check["severity"] == "critical":
            blocked = loop_check["blocked_tool"]
            if blocked in tool_registry:
                del tool_registry[blocked]
            _add_message(
                messages,
                {
                    "role": "system",
                    "content": f"[循环检测] {loop_check['reason']}。工具 {blocked} 已暂时禁用，请更换策略。",
                },
                session_path,
            )

        compact_if_needed(messages, budget.steps_used, compact_config)

        if needs_compression(messages, compression_config):
            if compression_guard.is_exhausted():
                return "上下文空间已耗尽，结束本轮对话"
            messages = compress_history(
                messages, compression_config["keep_recent_count"]
            )
            compression_guard.record_compression()

        response = await llm.chat(messages, tools=list(tool_registry.keys()))

        if not response["tool_calls"]:
            return response["content"]

        _add_message(
            messages,
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            },
            session_path,
        )

        to_execute = []
        for call in response["tool_calls"]:
            valid = validate_tool_call(call, tool_registry)
            if not valid["ok"]:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    return "连续校验失败，任务终止"
                _add_message(
                    messages,
                    {"role": "system", "content": f"[校验失败] {valid['error']}"},
                    session_path,
                )
                continue

            if circuit_breaker.is_tripped(call["name"]):
                _add_message(
                    messages,
                    {
                        "role": "system",
                        "content": f"[熔断] 工具 {call['name']} 连续失败次数过多，已临时禁用",
                    },
                    session_path,
                )
                continue

            consecutive_errors = 0
            to_execute.append(call)

        if not to_execute:
            continue

        results = await asyncio.gather(
            *[
                _execute_call(call, tool_registry, circuit_breaker, sleep_fn, timeout_seconds)
                for call in to_execute
            ]
        )

        for outcome in results:
            _add_message(
                messages,
                {"role": "tool", "name": outcome["tool"], "content": outcome["content"]},
                session_path,
            )
            call_history.append(
                {"tool": outcome["tool"], "args": outcome["args"], "ok": outcome["ok"]}
            )
```

关键设计点：
- **校验/熔断检查仍然按顺序、同步地做完，只有真正要执行的调用才进入 `asyncio.gather` 并发**——`to_execute` 列表就是这道"过滤閘"。这样校验失败、熔断拦截的行为和之前完全一致（还是逐个判断、逐个决定要不要终止整个任务），只有"真正调用工具"这个耗时的部分才是并发的。
- **`asyncio.gather` 返回结果的顺序和传入协程列表的顺序一致**，所以不需要额外的 ID 匹配逻辑——每个 `_execute_call` 的返回值本身已经带着 `tool`/`args`/`ok`/`content`，可以直接按顺序回填 `messages` 和 `call_history`。
- **重试逻辑搬进了 `_execute_call` 内部**，`sleep_fn` 默认值从 v8/v9 的 `time.sleep` 换成了 `asyncio.sleep`——在 async 函数里调用同步的 `time.sleep` 会阻塞整个事件循环，让"并发"名存实亡。
- **超时通过 `asyncio.wait_for` 实现**，捕获到的 `asyncio.TimeoutError` 走的是和其它失败一样的"记一次熔断失败、回填错误消息"路径，不做重试（网络超时到底该不该重试是一个更复杂的问题，本版本简化为"超时=失败"，不属于本版本范围）。
- **`if not to_execute: continue`**：如果一轮里所有调用都被校验或熔断拦截了，直接跳过并发执行阶段、回到循环顶部，等待模型下一轮响应。

- [ ] **Step 8: 运行测试确认全部通过**

Run: `cd v10 && python3 -m pytest tests/test_concurrency.py -v`
Expected: `5 passed`

- [ ] **Step 9: 修改 `v10/main.py`（用 `asyncio.run` 包一层）**

```python
import argparse
import asyncio
from pathlib import Path

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


async def run_main(args):
    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)
    session_path = Path(args.session_file) if args.session_file else None

    try:
        result = await run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            session_path=session_path,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


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
            "missing_required_arg_then_fix",
            "unknown_tool_repeated",
            "combined_recovery",
            "flaky_api_recovers",
            "non_retryable_failure",
            "circuit_breaker_trips",
            "resume_phase1",
            "resume_phase2",
            "parallel_tools",
            "slow_tool_timeout",
        ],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--session-file",
        type=str,
        default=None,
        help="会话落盘路径；指定后支持断点续跑",
    )
    args = parser.parse_args()
    asyncio.run(run_main(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: 手动验证**

Run: `cd v10 && python3 main.py --scenario parallel_tools`
Expected:
```
[结果] 已并发完成两个调用。
[LLM 调用次数] 2
```

Run: `cd v10 && python3 main.py --scenario slow_tool_timeout`
Expected（用默认的 `timeout_seconds=5.0`，`slow_tool` 只睡 0.2 秒，不会真的触发超时——这一步只是确认命令能正常跑通；测试里用的是刻意调小的 `timeout_seconds=0.05` 来稳定复现超时）：
```
[结果] 慢工具超时了，已记录并结束。
[LLM 调用次数] 2
```

- [ ] **Step 11: 创建 `v10/README.md`**

```markdown
# v10：并发工具调用 + 超时取消

## 本版目标

到 v9 为止，即便模型一轮返回好几个互相独立的工具调用，Harness 也是一个接一个顺序执行的；一个工具卡住不返回，整个运行就跟着卡住。这一版把 `run_agent` 改成 `async def`，同一轮里的多个工具调用改为并发执行，并给每个调用套上超时，卡住的工具会被取消而不是拖死整条运行。

## 新增/修改文件（对照 v9）

- 修改 `mock_llm.py`：`MockLLM.chat()` 改成 `async def`。
- 修改 `tools.py`：`Tool.run()` 和内部的工具函数全部改成 `async def`；新增 `ConcurrencyTracker`（记录同时在执行的调用数峰值，用来在测试里证明并发确实发生）和 `slow_tool`（人为耗时 0.2 秒，用来演示超时取消）。
- 修改 `harness/loop.py`：`run_agent()` 改成 `async def`；校验和熔断检查仍然顺序执行，只有通过检查、真正要执行的调用才通过 `asyncio.gather` 并发跑；每个调用外层套 `asyncio.wait_for(..., timeout=timeout_seconds)`。`sleep_fn` 默认值从 `time.sleep` 换成 `asyncio.sleep`。
- 修改 `scenarios.py`：新增 `parallel_tools`（一轮两个独立调用）和 `slow_tool_timeout`（演示超时取消）。
- 修改 `main.py`：新增 `run_main()` 异步入口，`main()` 用 `asyncio.run()` 驱动。
- 其余文件（`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`、`harness/errors.py`、`harness/retry.py`、`harness/session_store.py`）与 v9 完全一致，不涉及 async 改造。

## 核心设计

**为什么校验/熔断检查不并发，只有真正的工具执行并发**：校验和熔断判断本身是纯内存操作，几乎不耗时，而且它们的结果会影响"这一轮到底要不要终止整个任务"（比如连续校验失败达到阈值），这类决策必须按顺序做，不能并发；真正值得并发化的是"调用工具、等待它返回结果"这个可能有真实 I/O 延迟的部分。

**为什么用一个共享的"在途调用数"计数器而不是用真实计时来验证并发**：如果测试断言"两个调用的总耗时比顺序执行短"，测试结果会因为运行测试的机器负载、CI 环境的抖动而变得不稳定（flaky）。而"同一时刻有几个调用同时挂在 `active` 状态"这个数字不依赖具体耗时多少，只要两个协程确实同时在跑，`peak` 就一定会 `>= 2`，是一个更稳定、更直接的并发证明方式。

**为什么超时的处理方式是"记一次熔断失败"，而不是重试**：超时到底该不该重试是一个更微妙的问题（重试一个本来就慢的操作，可能只是让它更慢），本版本把它简化成和普通失败一样处理，交给已有的熔断机制去判断"这个工具是不是已经不可靠了"，不在这一版引入额外的超时专属重试策略。

## 如何运行 demo

```bash
python3 main.py --scenario parallel_tools       # 一轮两个调用并发跑完
python3 main.py --scenario slow_tool_timeout    # 演示慢工具被超时机制处理（默认超时较宽松，测试里用更短的超时更容易看到取消效果）
```

## 局限性

本版本明确不实现真正的流式增量输出——`MockLLM` 一次性返回完整的 response，没有真实的增量 token/chunk 可以流式吐出，强行把已有字符串拆成逐字符输出没有教学意义，这是与设计文档"并发与流式"标题相对应、经过确认的范围收窄。另外，超时后的工具调用在 Python 的 `asyncio.wait_for` 实现里，被取消的协程本身可能仍在后台继续运行到某个 `await` 点才真正终止（不是瞬间强杀），本版本没有对这类"僵尸任务"做额外的清理或资源回收演示，真实生产系统里这通常需要工具自身支持协作式取消（在内部检查 `asyncio.CancelledError` 并做清理）。
```

- [ ] **Step 12: Commit**

```bash
cd Harness-from-scratch
git add v10/
git commit -m "feat(v10): async run_agent with concurrent tool execution and timeout cancellation"
```

---

## Task 11: v11 —— 安全权限沙箱

**Files:**
- Copy from v10 (unchanged): `mock_llm.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`, `harness/validator.py`, `harness/errors.py`, `harness/retry.py`, `harness/session_store.py`
- Create: `harness/permissions.py`
- Modify (relative to v10): `tools.py`, `harness/loop.py`, `scenarios.py`, `main.py`
- Test: `tests/test_permissions.py`
- Create: `README.md`

- [ ] **Step 1: 复制未变化的文件**

```bash
cd Harness-from-scratch
cp v10/mock_llm.py v11/mock_llm.py
cp v10/harness/__init__.py v11/harness/__init__.py
cp v10/harness/budget.py v11/harness/budget.py
cp v10/harness/loop_detector.py v11/harness/loop_detector.py
cp v10/harness/context_manager.py v11/harness/context_manager.py
cp v10/harness/validator.py v11/harness/validator.py
cp v10/harness/errors.py v11/harness/errors.py
cp v10/harness/retry.py v11/harness/retry.py
cp v10/harness/session_store.py v11/harness/session_store.py
```

- [ ] **Step 2: 修改 `v11/tools.py`（在 v10 版本基础上新增一个危险工具 `delete_all_files`）**

```python
"""示例工具集：内存态假文件系统 + 假搜索，配合 MockLLM 复现固定场景。"""

import asyncio

from harness.errors import TransientError


class Tool:
    def __init__(self, name, func, params=None):
        self.name = name
        self.func = func
        self.params = params or {}  # param_name -> {"required": bool}

    async def run(self, args):
        return await self.func(**args)


class ConcurrencyTracker:
    """记录同一时刻有多少个工具调用正在执行，用来证明"真的并发了"而不是靠计时猜测。"""

    def __init__(self):
        self.active = 0
        self.peak = 0

    def enter(self):
        self.active += 1
        self.peak = max(self.peak, self.active)

    def exit(self):
        self.active -= 1


def _make_fake_fs():
    return {"config.yaml": "timeout: 30\nretries: 3\n"}


def build_default_tool_registry(concurrency_tracker=None):
    fake_fs = _make_fake_fs()
    flaky_state = {"attempts": 0}

    async def read_file(path):
        if concurrency_tracker is not None:
            concurrency_tracker.enter()
        try:
            await asyncio.sleep(0.01)
            if path not in fake_fs:
                raise FileNotFoundError(f"文件不存在: {path}")
            return fake_fs[path]
        finally:
            if concurrency_tracker is not None:
                concurrency_tracker.exit()

    async def search_web(query):
        if concurrency_tracker is not None:
            concurrency_tracker.enter()
        try:
            await asyncio.sleep(0.01)
            return f"搜索 '{query}' 的结果：暂无相关信息（mock 数据）。"
        finally:
            if concurrency_tracker is not None:
                concurrency_tracker.exit()

    async def write_file(path, content):
        fake_fs[path] = content
        return f"已写入 {path}（{len(content)} 字符）"

    async def flaky_api(query):
        flaky_state["attempts"] += 1
        if flaky_state["attempts"] <= 2:
            raise TransientError(f"临时故障（第 {flaky_state['attempts']} 次尝试）")
        return f"flaky_api 调用成功（第 {flaky_state['attempts']} 次尝试）：{query}"

    async def always_fails_api(query):
        raise TransientError("这个接口一直不可用")

    async def slow_tool(query):
        await asyncio.sleep(0.2)
        return f"slow_tool 终于处理完了：{query}"

    async def delete_all_files():
        fake_fs.clear()
        return "已删除所有文件（这个操作本不该被无审批地执行）"

    return {
        "read_file": Tool("read_file", read_file, {"path": {"required": True}}),
        "search_web": Tool("search_web", search_web, {"query": {"required": True}}),
        "write_file": Tool(
            "write_file",
            write_file,
            {"path": {"required": True}, "content": {"required": True}},
        ),
        "flaky_api": Tool("flaky_api", flaky_api, {"query": {"required": True}}),
        "always_fails_api": Tool(
            "always_fails_api", always_fails_api, {"query": {"required": True}}
        ),
        "slow_tool": Tool("slow_tool", slow_tool, {"query": {"required": True}}),
        "delete_all_files": Tool("delete_all_files", delete_all_files, {}),
    }
```

- [ ] **Step 3: 创建 `v11/harness/permissions.py`**

```python
"""v11：权限规则引擎——allow/ask/deny 三态，执行前拦截危险操作。"""


def check_permission(call, policy):
    return policy.get(call["name"], "allow")
```

未出现在 `policy` 字典里的工具默认 `"allow"`——权限策略是"白名单式限制"，不是"默认拒绝"，这样已有的场景在不配置任何策略时行为不变（`main.py` 之外的调用方如果不传 `permission_policy`，等价于传了一个空字典）。

- [ ] **Step 4: 扩展 `v11/scenarios.py`（复制 v10 全部 15 个场景 + 新增 3 个）**

```bash
cp v10/scenarios.py v11/scenarios.py
```

在 `SCENARIOS` 字典闭合的 `}` 之前插入：

```python
    # write_file 配置为 "ask"，假 approve_fn 批准 → 正常执行成功。
    "ask_then_approved": (
        "写一个笔记文件",
        [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "write_file",
                        "args": {"path": "note.txt", "content": "hello"},
                    }
                ],
            },
            {"content": "笔记已写入。", "tool_calls": []},
        ],
    ),
    # 同样是 "ask" 规则，这次假 approve_fn 拒绝；模型换一种方式
    # （改用 search_web）完成任务，验证拒绝后能优雅回填、不崩溃。
    "ask_then_denied": (
        "写一个笔记文件，如果不被允许就换个方式记录",
        [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "write_file",
                        "args": {"path": "note.txt", "content": "hello"},
                    }
                ],
            },
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_2",
                        "name": "search_web",
                        "args": {"query": "笔记记录替代方案"},
                    }
                ],
            },
            {"content": "改用搜索记录了替代方案。", "tool_calls": []},
        ],
    ),
    # delete_all_files 配置为 "deny"：无论 approve_fn 是什么都会被直接拦截，
    # 验证 deny 的优先级高于任何审批回调。
    "deny_dangerous_tool": (
        "清空所有文件",
        [
            {
                "content": None,
                "tool_calls": [{"id": "call_1", "name": "delete_all_files", "args": {}}],
            },
            {"content": "危险操作被拒绝，任务结束。", "tool_calls": []},
        ],
    ),
```

- [ ] **Step 5: 写失败测试 `v11/tests/test_permissions.py`**

```python
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from harness.permissions import check_permission
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


def test_check_permission_defaults_to_allow_for_unknown_tools():
    assert check_permission({"name": "search_web"}, {}) == "allow"


def test_check_permission_returns_configured_rule():
    policy = {"write_file": "ask", "delete_all_files": "deny"}
    assert check_permission({"name": "write_file"}, policy) == "ask"
    assert check_permission({"name": "delete_all_files"}, policy) == "deny"


def _run(scenario_name, permission_policy, approve_fn):
    async def scenario_body():
        goal, script = get_scenario(scenario_name)
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry()
        result = await run_agent(
            goal,
            registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            permission_policy=permission_policy,
            approve_fn=approve_fn,
        )
        return result, llm.call_count

    return asyncio.run(scenario_body())


def test_ask_rule_with_approval_executes_normally():
    result, call_count = _run(
        "ask_then_approved", {"write_file": "ask"}, lambda call: True
    )
    assert result == "笔记已写入。"
    assert call_count == 2


def test_ask_rule_with_denial_blocks_and_lets_model_recover():
    result, call_count = _run(
        "ask_then_denied", {"write_file": "ask"}, lambda call: False
    )
    assert result == "改用搜索记录了替代方案。"
    assert call_count == 3


def test_deny_rule_blocks_regardless_of_approve_fn():
    result, call_count = _run(
        "deny_dangerous_tool", {"delete_all_files": "deny"}, lambda call: True
    )
    assert result == "危险操作被拒绝，任务结束。"
    assert call_count == 2
```

- [ ] **Step 6: 运行测试确认部分通过**

Run: `cd v11 && python3 -m pytest tests/test_permissions.py -v`
Expected: 前 2 个纯函数测试（`test_check_permission_...`）通过；后 3 个集成测试报 `TypeError: run_agent() got an unexpected keyword argument 'permission_policy'`（因为 `harness/loop.py` 还没有接入权限检查）。

- [ ] **Step 7: 修改 `v11/harness/loop.py`**

```python
"""v11：在 v10 的并发骨架基础上加入安全权限沙箱。"""

import asyncio

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.errors import classify_error
from harness.loop_detector import detect_loop
from harness.permissions import check_permission
from harness.retry import ToolCircuitBreaker, compute_backoff_delay
from harness.session_store import append_message, load_session
from harness.validator import validate_tool_call

MAX_CONSECUTIVE_ERRORS = 3
MAX_RETRIES = 3
CIRCUIT_BREAKER_THRESHOLD = 3
DEFAULT_TOOL_TIMEOUT = 5.0


def _add_message(messages, message, session_path):
    messages.append(message)
    if session_path is not None:
        append_message(session_path, message)


def default_approve_fn(call):
    reply = input(f"是否批准执行 {call['name']}（参数：{call['args']}）？[y/N] ")
    return reply.strip().lower() == "y"


async def _execute_call(call, tool_registry, circuit_breaker, sleep_fn, timeout_seconds):
    tool = tool_registry[call["name"]]
    attempt = 0
    while True:
        try:
            result = await asyncio.wait_for(
                tool.run(call["args"]), timeout=timeout_seconds
            )
            circuit_breaker.record_success(call["name"])
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": True,
                "content": result,
            }
        except asyncio.TimeoutError:
            circuit_breaker.record_failure(call["name"])
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": False,
                "content": f"Error: 工具 {call['name']} 执行超过 {timeout_seconds} 秒，已取消",
            }
        except Exception as exc:  # noqa: BLE001 - 分类结果决定是否重试
            if classify_error(exc) == "retryable" and attempt < MAX_RETRIES:
                await sleep_fn(compute_backoff_delay(attempt))
                attempt += 1
                continue
            circuit_breaker.record_failure(call["name"])
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": False,
                "content": f"Error: {exc}",
            }


async def run_agent(
    goal,
    tool_registry,
    llm,
    budget,
    compact_config,
    compression_config,
    sleep_fn=asyncio.sleep,
    session_path=None,
    timeout_seconds=DEFAULT_TOOL_TIMEOUT,
    permission_policy=None,
    approve_fn=None,
):
    permission_policy = permission_policy or {}
    approve_fn = approve_fn or default_approve_fn

    existing = load_session(session_path) if session_path is not None else []
    if existing:
        messages = existing
    else:
        messages = []
        _add_message(
            messages, {"role": "system", "content": "你是一个通用任务助手。"}, session_path
        )
        _add_message(messages, {"role": "user", "content": goal}, session_path)

    call_history = []
    compression_guard = CompressionGuard(compression_config["max_compressions"])
    consecutive_errors = 0
    circuit_breaker = ToolCircuitBreaker(CIRCUIT_BREAKER_THRESHOLD)

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        loop_check = detect_loop(call_history)
        if loop_check["severity"] == "critical":
            blocked = loop_check["blocked_tool"]
            if blocked in tool_registry:
                del tool_registry[blocked]
            _add_message(
                messages,
                {
                    "role": "system",
                    "content": f"[循环检测] {loop_check['reason']}。工具 {blocked} 已暂时禁用，请更换策略。",
                },
                session_path,
            )

        compact_if_needed(messages, budget.steps_used, compact_config)

        if needs_compression(messages, compression_config):
            if compression_guard.is_exhausted():
                return "上下文空间已耗尽，结束本轮对话"
            messages = compress_history(
                messages, compression_config["keep_recent_count"]
            )
            compression_guard.record_compression()

        response = await llm.chat(messages, tools=list(tool_registry.keys()))

        if not response["tool_calls"]:
            return response["content"]

        _add_message(
            messages,
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            },
            session_path,
        )

        to_execute = []
        for call in response["tool_calls"]:
            valid = validate_tool_call(call, tool_registry)
            if not valid["ok"]:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    return "连续校验失败，任务终止"
                _add_message(
                    messages,
                    {"role": "system", "content": f"[校验失败] {valid['error']}"},
                    session_path,
                )
                continue

            consecutive_errors = 0

            decision = check_permission(call, permission_policy)
            if decision == "deny":
                _add_message(
                    messages,
                    {
                        "role": "system",
                        "content": f"[权限拒绝] 工具 {call['name']} 被策略禁止执行",
                    },
                    session_path,
                )
                continue
            if decision == "ask" and not approve_fn(call):
                _add_message(
                    messages,
                    {
                        "role": "system",
                        "content": f"[权限待批准-已拒绝] 工具 {call['name']} 未获批准",
                    },
                    session_path,
                )
                continue

            if circuit_breaker.is_tripped(call["name"]):
                _add_message(
                    messages,
                    {
                        "role": "system",
                        "content": f"[熔断] 工具 {call['name']} 连续失败次数过多，已临时禁用",
                    },
                    session_path,
                )
                continue

            to_execute.append(call)

        if not to_execute:
            continue

        results = await asyncio.gather(
            *[
                _execute_call(call, tool_registry, circuit_breaker, sleep_fn, timeout_seconds)
                for call in to_execute
            ]
        )

        for outcome in results:
            _add_message(
                messages,
                {"role": "tool", "name": outcome["tool"], "content": outcome["content"]},
                session_path,
            )
            call_history.append(
                {"tool": outcome["tool"], "args": outcome["args"], "ok": outcome["ok"]}
            )
```

关键点：权限检查发生在校验通过之后、熔断检查之前——`deny` 和 `ask`-被拒绝的调用都不会进入 `to_execute`，也不会影响熔断计数（因为它们根本没有真正尝试执行）。`approve_fn` 是普通的同步函数（不是 `async def`），默认实现用阻塞的 `input()` 真实询问终端；测试里传入的假 `approve_fn` 是确定性的 lambda，不需要真的等待人工输入。

- [ ] **Step 8: 运行测试确认全部通过**

Run: `cd v11 && python3 -m pytest tests/test_permissions.py -v`
Expected: `5 passed`

- [ ] **Step 9: 修改 `v11/main.py`**

```python
import argparse
import asyncio
from pathlib import Path

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
DEFAULT_PERMISSION_POLICY = {
    "write_file": "ask",
    "delete_all_files": "deny",
}


async def run_main(args):
    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)
    session_path = Path(args.session_file) if args.session_file else None

    try:
        result = await run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            session_path=session_path,
            permission_policy=DEFAULT_PERMISSION_POLICY,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


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
            "missing_required_arg_then_fix",
            "unknown_tool_repeated",
            "combined_recovery",
            "flaky_api_recovers",
            "non_retryable_failure",
            "circuit_breaker_trips",
            "resume_phase1",
            "resume_phase2",
            "parallel_tools",
            "slow_tool_timeout",
            "ask_then_approved",
            "ask_then_denied",
            "deny_dangerous_tool",
        ],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--session-file",
        type=str,
        default=None,
        help="会话落盘路径；指定后支持断点续跑",
    )
    args = parser.parse_args()
    asyncio.run(run_main(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: 手动验证**

`ask_then_approved` 和 `ask_then_denied` 用的是真实的 `input()` 审批（`main.py` 没有覆盖 `approve_fn`），运行时需要在终端手动输入：

Run: `cd v11 && python3 main.py --scenario ask_then_approved`，出现提示时输入 `y` 并回车。
Expected:
```
是否批准执行 write_file（参数：{'path': 'note.txt', 'content': 'hello'}）？[y/N] y
[结果] 笔记已写入。
[LLM 调用次数] 2
```

Run: `cd v11 && python3 main.py --scenario deny_dangerous_tool`（`delete_all_files` 是 `deny` 规则，不会触发任何询问）
Expected:
```
[结果] 危险操作被拒绝，任务结束。
[LLM 调用次数] 2
```

- [ ] **Step 11: 创建 `v11/README.md`**

```markdown
# v11：安全权限沙箱

## 本版目标

到 v10 为止，Harness 会执行模型要求的任何工具调用，不管这个操作有多危险。这一版加入一个简单的权限规则引擎：每个工具可以配置成 `allow`（放行）、`ask`（需要审批）、`deny`（禁止）三种状态之一，在真正执行之前拦截。

## 新增/修改文件（对照 v10）

- 新增 `harness/permissions.py`：`check_permission(call, policy)`，未配置的工具默认 `"allow"`。
- 修改 `tools.py`：新增一个危险工具 `delete_all_files`（清空内存态文件系统），用来演示 `deny` 规则。
- 修改 `harness/loop.py`：`run_agent()` 新增 `permission_policy`（字典，默认空）和 `approve_fn`（回调，默认是一个基于 `input()` 的真实终端询问函数）两个参数。校验通过之后、熔断检查之前，先做一次权限过滤：`deny` 直接拦截；`ask` 调用 `approve_fn(call)`，返回假就同样拦截。
- 修改 `scenarios.py`：新增 `ask_then_approved`、`ask_then_denied`、`deny_dangerous_tool` 三个场景。
- 修改 `main.py`：新增 `DEFAULT_PERMISSION_POLICY`（`write_file` 设为 `ask`，`delete_all_files` 设为 `deny`）。
- 其余文件（`mock_llm.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`、`harness/errors.py`、`harness/retry.py`、`harness/session_store.py`）与 v10 完全一致。

## 核心设计

**为什么 `approve_fn` 是普通同步函数，不是 `async def`**：审批本质上是一个"询问外部世界一个是/否问题"的动作，在 CLI 场景里就是阻塞地等待用户输入；把它做成同步函数反而更贴近真实语义（人不会"并发"地回答审批问题），也让测试更容易写（传一个确定性的 lambda，不需要处理协程）。

**为什么权限检查放在校验通过之后、熔断检查之前**：一个调用如果连基本格式都不对（未知工具/缺参数），根本不需要问"要不要批准"；而权限判断是"这个操作本身是否被允许"，这个问题应该先于"这个工具最近是不是老出问题"（熔断）被回答——即使一个工具从没失败过，只要策略上不允许，也不该被执行。

**为什么 `deny` 不经过 `approve_fn`**：`deny` 表示"这类操作在任何情况下都不该被执行"，是比"需要人工确认"更强的约束，不应该给模型或审批者任何绕过的机会。

## 如何运行 demo

```bash
python3 main.py --scenario ask_then_approved     # 需要在终端手动输入 y 批准
python3 main.py --scenario ask_then_denied       # 手动输入 n（或直接回车）拒绝，模型换策略完成任务
python3 main.py --scenario deny_dangerous_tool   # 危险操作被直接拦截，不会有任何询问
```

## 局限性

权限策略是一个扁平的 `{工具名: 规则}` 字典，无法根据参数内容做更细粒度的判断（比如"写入 `/tmp` 下的文件允许，写入其它路径需要审批"），也没有路径白名单/黑名单这类更精细的规则表达能力。`approve_fn` 的默认实现是阻塞式的 `input()`，如果同一轮里有多个都需要审批的调用，会一个接一个地依次询问，不会并发弹出多个审批请求——这是因为审批过滤发生在进入 `asyncio.gather` 之前的顺序阶段，和"真正执行的并发"是两个不同的关注点。

至此，v8~v11 这一批工业级扩展全部完成。v12~v15（可观测性与成本核算、自动化评估框架、动态工具/技能插件化、多智能体协作）将在下一批计划中规划。
```

- [ ] **Step 12: Commit**

```bash
cd Harness-from-scratch
git add v11/
git commit -m "feat(v11): permission sandbox with allow/ask/deny policy gating"
```

---

## Task 12: 更新根目录 README 的路线图状态 + 全量回归验证

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新根目录 `README.md` 的路线图表格**，把 v8~v11 这四行的链接从纯文字改成指向对应版本 `README.md` 的链接（其余行不变）：

把现有表格中的

```markdown
| v8~v15 | 工业级扩展 | 见设计文档，待后续计划补充（重试退避、会话持久化、并发流式、安全沙箱、可观测性、动态工具、多智能体协作） |
```

替换为：

```markdown
| [v8](v8/README.md) | 结构化错误处理与重试退避 | 区分可重试/不可重试错误；指数退避 + 抖动预留接口；单工具级熔断器 |
| [v9](v9/README.md) | 会话持久化与断点续跑 | 消息历史落盘 JSONL；进程重启后可从断点继续跑 |
| [v10](v10/README.md) | 并发与超时取消 | `run_agent` 转为 async；同一轮内的多个工具调用并发执行；超时自动取消，不拖死整个循环 |
| [v11](v11/README.md) | 安全权限沙箱 | allow/ask/deny 三态权限规则，执行前拦截危险操作 |
| v12~v15 | 工业级扩展（待规划） | 见设计文档，待后续计划补充（可观测性、评估框架、动态工具、多智能体协作） |
```

- [ ] **Step 2: 跑一遍 v8~v11 全部测试套件，确认没有相互破坏**

```bash
cd Harness-from-scratch
for v in v8 v9 v10 v11; do
  echo "=== $v ===" && (cd "$v" && python3 -m pytest tests/ -q) || exit 1
done
```

Expected: 每个版本都输出 `N passed`，没有 `FAILED` 或 `ERROR`（v8: 8 passed，v9: 4 passed，v10: 5 passed，v11: 5 passed）。

- [ ] **Step 3: 顺手跑一遍 v1~v7 的测试，确认这一批新增代码没有意外影响到之前的版本（理论上不可能，因为每个版本目录完全独立，但作为最后的保险检查）**

```bash
cd Harness-from-scratch
for v in v1 v2 v3 v4 v5 v6 v7; do
  echo "=== $v ===" && (cd "$v" && python3 -m pytest tests/ -q) || exit 1
done
```

Expected: 全部通过（v1: 2, v2: 3, v3: 3, v4: 3, v5: 5, v6: 5, v7: 19，均为 passed）。

- [ ] **Step 4: Commit**

```bash
cd Harness-from-scratch
git add README.md
git commit -m "docs: update roadmap table with v8-v11 links"
```

---

## Self-Review 记录

- **Spec 覆盖**：设计文档"实现记录：v8~v11 详细技术方案"里针对 v8/v9/v10/v11 的每一条设计要点（错误分类、退避、熔断；JSONL 持久化、断点续跑；async 化、并发、超时取消；permission 三态、`approve_fn` 注入）都对应到了 Task 8~11 里的具体代码和测试。"v8~v11 相对设计文档的范围确认"一节里提到的"v10 不做真流式输出"已经在 v10 的 README 局限性里如实记录。
- **占位符扫描**：全部任务的代码块均为完整实现，无 `TODO`/`TBD`。
- **类型一致性**：`run_agent()` 签名从 v7 的 `(goal, tool_registry, llm, budget, compact_config, compression_config)` 逐版增加关键字参数——v8 加 `sleep_fn`，v9 加 `session_path`，v10 转为 `async def` 并加 `timeout_seconds`（`sleep_fn` 默认值同时从 `time.sleep` 换成 `asyncio.sleep`），v11 加 `permission_policy`、`approve_fn`；每个版本的 `main.py`、测试文件都已核对为对应版本的签名和调用方式（v10 起测试文件统一用 `asyncio.run(scenario_body())` 包裹异步逻辑）。`Tool`、`Budget`、`CompressionGuard`、`ToolCircuitBreaker` 的字段名在所有引用处保持一致；`Tool.run()`/工具函数从 v10 起统一改为 `async def`，v11 沿用不变。
- **已知的、写进 README 的局限性**（非缺陷，均为刻意的范围收敛）：v9 的运行时计数器（`Budget`、`ToolCircuitBreaker`）不跨进程持久化，压缩触发时 JSONL 不同步"整体替换"；v10 不实现真流式输出，超时取消不处理"僵尸协程"清理；v11 的权限策略是扁平的工具名字典，不支持基于参数内容的细粒度规则，`approve_fn` 审批是顺序阻塞的、不并发弹出多个请求。

