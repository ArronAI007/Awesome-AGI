# 渐进式 Harness 教程：v12~v15 工业级扩展第二批（系列收官）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `Harness-from-scratch/` 下实现 v12~v15 四个自包含、可运行的 Agent Harness 项目，在 v11 权限沙箱的基础上依次加入可观测性与成本核算（v12）、自动化评估框架（v13）、动态工具/技能插件化（v14）、多智能体协作（v15），完成整个 v1~v15 系列。

**Architecture:** 全部建立在 v11 的 async 权限沙箱骨架之上，延续同一套模式：完全自包含目录、未变化文件用 `cp` 复制、`MockLLM` 脚本化确定性驱动、"记账+判断"式防护对象、依赖注入保证可测试性。v12 修改核心循环加入事件记录；v13 完全不改核心循环，只是批量调用已有的 `run_agent()`；v14 把 `tool_registry` 从普通 dict 换成一个行为完全兼容的 dict 子类；v15 只新增一个"内部递归调用 `run_agent()`"的工具，核心循环同样不改。

**Tech Stack:** Python 3.11+ 标准库、`pytest`（沿用 v10 起的"`asyncio.run()` 包裹普通测试函数"写法，不引入 `pytest-asyncio`）。

**依据的设计文档：** `docs/superpowers/specs/2026-08-28-progressive-harness-series-design.md` 中"实现记录：v12~v15 详细技术方案"章节。

---

## 关于本计划的约定

1. **起点是 v11**，已完成并合并到 main，位于 `Harness-from-scratch/v11/`。v12 的所有"复制"步骤都以 v11 为源。
2. **未变化文件用 `cp` 复制**，命令在任务里给出，不是占位符。
3. **测试运行方式统一**：`cd v{N} && python3 -m pytest tests/ -v`。
4. **提交前缀**：全部使用 `feat(v{N}):`。
5. **本批次不新造一个类似 v7 的"大集成"场景**——v12~v15 每个版本是独立的能力域，互相之间没有 v2~v6 那种"必须协同工作"的强耦合，额外做集成场景的教学价值有限。最后一个任务只做根目录 README 收尾 + 全量回归。
6. **v13/v14/v15 都不修改 `harness/loop.py`**——这是刻意的：v13 只是批量调用已有的 `run_agent()`；v14 的 `ToolRegistry` 是 dict 的行为兼容子类，`loop.py` 里所有 `tool_registry[...]`、`del tool_registry[...]`、`.keys()` 调用不需要任何改动；v15 的 `delegate_task` 只是一个普通工具，工具内部"递归调用 `run_agent()`"这件事完全不需要 `run_agent()` 本身知情。只有 v12 因为要在核心循环里记录事件，需要修改 `loop.py`。

---

## Task 13: v12 —— 可观测性与成本核算

**Files:**
- Copy from v11 (unchanged): `mock_llm.py`, `tools.py`, `scenarios.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`, `harness/validator.py`, `harness/errors.py`, `harness/retry.py`, `harness/session_store.py`, `harness/permissions.py`
- Create: `harness/observability.py`
- Modify (relative to v11): `harness/loop.py`, `main.py`
- Test: `tests/test_observability.py`
- Create: `README.md`

- [ ] **Step 1: 复制未变化的文件**

```bash
cd Harness-from-scratch
cp v11/mock_llm.py v12/mock_llm.py
cp v11/tools.py v12/tools.py
cp v11/scenarios.py v12/scenarios.py
cp v11/harness/__init__.py v12/harness/__init__.py
cp v11/harness/budget.py v12/harness/budget.py
cp v11/harness/loop_detector.py v12/harness/loop_detector.py
cp v11/harness/context_manager.py v12/harness/context_manager.py
cp v11/harness/validator.py v12/harness/validator.py
cp v11/harness/errors.py v12/harness/errors.py
cp v11/harness/retry.py v12/harness/retry.py
cp v11/harness/session_store.py v12/harness/session_store.py
cp v11/harness/permissions.py v12/harness/permissions.py
```

- [ ] **Step 2: 创建 `v12/harness/observability.py`**

```python
"""v12：可观测性——结构化事件日志、token/成本估算、运行报告。"""

import json
import time


def estimate_tokens(text):
    if not text:
        return 0
    return max(1, len(text) // 4)


def compute_cost(tokens_in, tokens_out, rates):
    return (tokens_in / 1000) * rates["input_per_1k"] + (tokens_out / 1000) * rates["output_per_1k"]


class EventLog:
    """把结构化事件记进内存列表，指定路径时同步追加写入 JSONL。"""

    def __init__(self, log_path=None, clock_fn=time.perf_counter):
        self.log_path = log_path
        self.clock_fn = clock_fn
        self.events = []

    def record(self, event_type, **fields):
        event = {"event_type": event_type, "timestamp": self.clock_fn(), **fields}
        self.events.append(event)
        if self.log_path is not None:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")


def build_run_report(events, rates=None):
    rates = rates or {"input_per_1k": 0.0, "output_per_1k": 0.0}
    llm_calls = [e for e in events if e["event_type"] == "llm_call"]
    tool_calls = [e for e in events if e["event_type"] == "tool_call"]
    guardrail_events = [e for e in events if e["event_type"] == "guardrail"]

    tokens_in = sum(e.get("tokens_in", 0) for e in llm_calls)
    tokens_out = sum(e.get("tokens_out", 0) for e in llm_calls)

    guardrail_counts = {}
    for e in guardrail_events:
        guardrail_counts[e["name"]] = guardrail_counts.get(e["name"], 0) + 1

    return {
        "llm_call_count": len(llm_calls),
        "tool_call_count": len(tool_calls),
        "tool_call_success_count": sum(1 for e in tool_calls if e.get("ok")),
        "tool_call_failure_count": sum(1 for e in tool_calls if not e.get("ok")),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "estimated_cost": compute_cost(tokens_in, tokens_out, rates),
        "guardrail_counts": guardrail_counts,
    }
```

- [ ] **Step 3: 写失败测试 `v12/tests/test_observability.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio

from harness.budget import Budget
from harness.loop import run_agent
from harness.observability import EventLog, build_run_report, compute_cost, estimate_tokens
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


def test_estimate_tokens_empty_string_is_zero():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0


def test_estimate_tokens_approximates_length_over_four():
    assert estimate_tokens("x" * 40) == 10
    assert estimate_tokens("x") == 1  # 不足 4 字符也至少算 1 个 token


def test_compute_cost_formula():
    cost = compute_cost(2000, 1000, {"input_per_1k": 0.5, "output_per_1k": 1.5})
    assert cost == 2000 / 1000 * 0.5 + 1000 / 1000 * 1.5


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 1.0
        return self.value


def test_event_log_records_events_in_memory_with_fake_clock():
    log = EventLog(clock_fn=FakeClock())
    log.record("llm_call", tokens_in=10, tokens_out=5)
    log.record("tool_call", tool_name="read_file", ok=True)
    assert len(log.events) == 2
    assert log.events[0]["timestamp"] == 1.0
    assert log.events[1]["timestamp"] == 2.0


def test_event_log_writes_jsonl_when_path_given(tmp_path):
    log_path = tmp_path / "events.jsonl"
    log = EventLog(log_path=log_path, clock_fn=FakeClock())
    log.record("llm_call", tokens_in=1, tokens_out=1)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_build_run_report_counts_events_correctly():
    events = [
        {"event_type": "llm_call", "tokens_in": 10, "tokens_out": 5},
        {"event_type": "llm_call", "tokens_in": 8, "tokens_out": 4},
        {"event_type": "tool_call", "tool_name": "read_file", "ok": True},
        {"event_type": "tool_call", "tool_name": "read_file", "ok": False},
        {"event_type": "guardrail", "name": "loop_detector", "tool_name": "read_file"},
    ]
    report = build_run_report(events, rates={"input_per_1k": 1.0, "output_per_1k": 1.0})
    assert report["llm_call_count"] == 2
    assert report["tool_call_count"] == 2
    assert report["tool_call_success_count"] == 1
    assert report["tool_call_failure_count"] == 1
    assert report["tokens_in"] == 18
    assert report["tokens_out"] == 9
    assert report["estimated_cost"] == 18 / 1000 + 9 / 1000
    assert report["guardrail_counts"] == {"loop_detector": 1}


def test_happy_path_scenario_produces_expected_event_counts():
    async def scenario_body():
        goal, script = get_scenario("happy_path")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry()
        event_log = EventLog()

        result = await run_agent(
            goal,
            registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            event_log=event_log,
        )

        assert result == "配置文件内容：timeout=30, retries=3。"
        report = build_run_report(event_log.events)
        assert report["llm_call_count"] == 2
        assert report["tool_call_count"] == 1
        assert report["tool_call_success_count"] == 1
        assert report["guardrail_counts"] == {}

    asyncio.run(scenario_body())


def test_spin_then_recover_scenario_logs_one_loop_detector_guardrail_event():
    async def scenario_body():
        goal, script = get_scenario("spin_then_recover")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry()
        event_log = EventLog()

        result = await run_agent(
            goal,
            registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            event_log=event_log,
        )

        assert result == "改用搜索后完成任务。"
        report = build_run_report(event_log.events)
        assert report["guardrail_counts"] == {"loop_detector": 1}
        assert report["tool_call_failure_count"] == 5  # 5 次 read_file(bad.txt) 失败
        assert report["tool_call_success_count"] == 1  # 1 次 search_web 成功

    asyncio.run(scenario_body())
```

- [ ] **Step 4: 运行测试确认部分通过**

Run: `cd v12 && python3 -m pytest tests/test_observability.py -v`
Expected: 前 6 个纯函数/`EventLog`/`build_run_report` 测试通过；后 2 个集成测试报 `TypeError: run_agent() got an unexpected keyword argument 'event_log'`（因为 `harness/loop.py` 还没有接入事件记录）。

- [ ] **Step 5: 修改 `v12/harness/loop.py`**

```python
"""v12：在 v11 的权限沙箱基础上加入可观测性——记录结构化事件，供事后统计。"""

import asyncio

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.errors import classify_error
from harness.loop_detector import detect_loop
from harness.observability import estimate_tokens
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


def _log(event_log, event_type, **fields):
    if event_log is not None:
        event_log.record(event_type, **fields)


def default_approve_fn(call):
    reply = input(f"是否批准执行 {call['name']}（参数：{call['args']}）？[y/N] ")
    return reply.strip().lower() == "y"


async def _execute_call(call, tool_registry, circuit_breaker, sleep_fn, timeout_seconds, event_log):
    tool = tool_registry[call["name"]]
    attempt = 0
    while True:
        try:
            result = await asyncio.wait_for(
                tool.run(call["args"]), timeout=timeout_seconds
            )
            circuit_breaker.record_success(call["name"])
            _log(event_log, "tool_call", tool_name=call["name"], ok=True)
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": True,
                "content": result,
            }
        except asyncio.TimeoutError:
            circuit_breaker.record_failure(call["name"])
            _log(event_log, "tool_call", tool_name=call["name"], ok=False, reason="timeout")
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
            _log(event_log, "tool_call", tool_name=call["name"], ok=False, reason=str(exc))
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
    event_log=None,
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
            _log(event_log, "guardrail", name="loop_detector", tool_name=blocked)
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
            _log(event_log, "guardrail", name="compression")

        tokens_in = estimate_tokens(str(messages))
        response = await llm.chat(messages, tools=list(tool_registry.keys()))
        tokens_out = estimate_tokens(response.get("content") or "")
        _log(event_log, "llm_call", tokens_in=tokens_in, tokens_out=tokens_out)

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
                _log(event_log, "guardrail", name="validation", tool_name=call["name"])
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
                _log(event_log, "guardrail", name="permission_deny", tool_name=call["name"])
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
                _log(event_log, "guardrail", name="permission_ask_rejected", tool_name=call["name"])
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
                _log(event_log, "guardrail", name="circuit_breaker", tool_name=call["name"])
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
                _execute_call(call, tool_registry, circuit_breaker, sleep_fn, timeout_seconds, event_log)
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

- [ ] **Step 6: 运行测试确认全部通过**

Run: `cd v12 && python3 -m pytest tests/test_observability.py -v`
Expected: `8 passed`

- [ ] **Step 7: 修改 `v12/main.py`**

```python
import argparse
import asyncio
import json
from pathlib import Path

from harness.budget import Budget
from harness.loop import run_agent
from harness.observability import EventLog, build_run_report
from harness.session_store import load_session
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
DEFAULT_COST_RATES = {"input_per_1k": 0.5, "output_per_1k": 1.5}


async def run_main(args):
    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)
    session_path = Path(args.session_file) if args.session_file else None
    event_log = EventLog() if args.report_file else None

    if session_path is not None:
        existing = load_session(session_path)
        if existing:
            print(f"[会话] 从 {len(existing)} 条历史消息续跑")
        else:
            print("[会话] 新建会话")

    try:
        result = await run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            session_path=session_path,
            timeout_seconds=args.timeout,
            permission_policy=DEFAULT_PERMISSION_POLICY,
            event_log=event_log,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")
        if event_log is not None:
            report = build_run_report(event_log.events, rates=DEFAULT_COST_RATES)
            with open(args.report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"[报告] 已写入 {args.report_file}：{report}")


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
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="单次工具调用的超时秒数"
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=None,
        help="运行报告输出路径（JSON）；指定后记录结构化事件并生成汇总报告",
    )
    args = parser.parse_args()
    asyncio.run(run_main(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: 手动验证**

Run: `cd v12 && python3 main.py --scenario spin_then_recover --report-file /tmp/harness-v12-report.json`
Expected（末尾的报告内容以实际运行为准，但 `guardrail_counts` 里应该有 `loop_detector: 1`）：
```
[结果] 改用搜索后完成任务。
[LLM 调用次数] 7
[报告] 已写入 /tmp/harness-v12-report.json：{'llm_call_count': 7, 'tool_call_count': 6, 'tool_call_success_count': 1, 'tool_call_failure_count': 5, 'tokens_in': ..., 'tokens_out': ..., 'estimated_cost': ..., 'guardrail_counts': {'loop_detector': 1}}
```

Run: `cat /tmp/harness-v12-report.json && rm /tmp/harness-v12-report.json`（确认文件是合法 JSON，然后清理）

- [ ] **Step 9: 创建 `v12/README.md`**

```markdown
# v12：可观测性与成本核算

## 本版目标

到 v11 为止，一次运行到底发生了什么——调用了几次 LLM、几次工具、哪些防护被触发了几次、大概花了多少钱——完全没有留下任何结构化记录，只能从终端打印的只言片语里猜。这一版加入结构化事件日志和运行报告，把这些信息变成可以事后查询、汇总、审计的数据。

## 新增/修改文件（对照 v11）

- 新增 `harness/observability.py`：`estimate_tokens(text)`（字符数估算，延续 v5 的思路）、`EventLog`（把事件记进内存列表，指定路径时同步落盘 JSONL）、`compute_cost(tokens_in, tokens_out, rates)`、`build_run_report(events, rates)`（从事件列表汇总出调用次数、token、成本、各类防护触发次数）。
- 修改 `harness/loop.py`：`run_agent()` 新增可选 `event_log` 参数（默认 `None`，不记录、行为与 v11 完全一致）；在每次 LLM 调用后记一条 `llm_call` 事件，每次工具执行结束后记一条 `tool_call` 事件，每次防护触发（循环检测/校验失败/权限拒绝/熔断/压缩）记一条 `guardrail` 事件。
- 修改 `main.py`：新增 `--report-file` 参数，指定后自动创建 `EventLog`、跑完后用 `build_run_report` 生成汇总报告并写入 JSON 文件。
- 其余文件（`mock_llm.py`、`tools.py`、`scenarios.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`、`harness/errors.py`、`harness/retry.py`、`harness/session_store.py`、`harness/permissions.py`）与 v11 完全一致。

## 核心设计

**为什么事件记录用一个独立的 `_log()` 辅助函数、而不是散在各处直接调用 `event_log.record(...)`**：`event_log` 是可选的（默认 `None`），每处调用点都要判断"是否启用了可观测性"，抽成一个小函数（内部做 `if event_log is not None` 判断）避免这段样板代码重复七八次。

**为什么耗时相关的字段（`timestamp`）通过注入的 `clock_fn` 而不是直接调用 `time.perf_counter()`**：和 v8 的 `sleep_fn`、v9 的会话落盘一样的思路——测试如果依赖真实时钟会引入不确定性，注入一个确定性的假时钟（每次调用返回递增的固定值）能让"时间戳按调用顺序递增"这件事本身变得可断言。

**为什么 token/成本只是估算，不接入真实 tokenizer**：这个系列从 v1 起就没有真实 LLM 依赖，`estimate_tokens` 延续 v5 `needs_compression` 的字符数估算思路（`len(text) // 4`），足够教学演示"如何组织可观测性数据"这件事本身，真实场景换成真正的 tokenizer 计数，`build_run_report` 的聚合逻辑不需要变。

## 如何运行 demo

```bash
python3 main.py --scenario spin_then_recover --report-file /tmp/report.json   # 跑完后 /tmp/report.json 里能看到 loop_detector 防护触发了 1 次
```

## 局限性

`estimate_tokens` 只是字符数除以 4 的粗略估算，中英文混合文本下这个比例并不准确，只用于演示"怎么组织成本核算数据"这件事本身。`build_run_report` 需要拿到一个已经跑完的 `EventLog.events` 列表才能汇总，本版本没有提供"运行中途实时查看报告"的能力（只能等 `run_agent()` 返回之后再汇总）。这两点都不影响 v13 要基于本版本的 `estimate_tokens` 构建的评估框架。
```

- [ ] **Step 10: Commit**

```bash
cd Harness-from-scratch
git add v12/
git commit -m "feat(v12): structured event logging with token/cost estimation and run reports"
```

---

## Task 14: v13 —— 自动化评估框架

这一版**不修改 `harness/loop.py`**——它只是批量调用 v12 已经写好的 `run_agent()`，用已有场景 + 期望断言组成 eval 用例。

**Files:**
- Copy from v12 (unchanged): `mock_llm.py`, `tools.py`, `scenarios.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`, `harness/validator.py`, `harness/errors.py`, `harness/retry.py`, `harness/session_store.py`, `harness/permissions.py`, `harness/observability.py`, `harness/loop.py`
- Create: `harness/eval_runner.py`, `evals.py`
- Modify (relative to v12): `main.py`
- Test: `tests/test_eval_runner.py`
- Create: `README.md`

- [ ] **Step 1: 复制未变化的文件（包括 `harness/loop.py`——本版本不改核心循环）**

```bash
cd Harness-from-scratch
cp v12/mock_llm.py v13/mock_llm.py
cp v12/tools.py v13/tools.py
cp v12/scenarios.py v13/scenarios.py
cp v12/harness/__init__.py v13/harness/__init__.py
cp v12/harness/budget.py v13/harness/budget.py
cp v12/harness/loop_detector.py v13/harness/loop_detector.py
cp v12/harness/context_manager.py v13/harness/context_manager.py
cp v12/harness/validator.py v13/harness/validator.py
cp v12/harness/errors.py v13/harness/errors.py
cp v12/harness/retry.py v13/harness/retry.py
cp v12/harness/session_store.py v13/harness/session_store.py
cp v12/harness/permissions.py v13/harness/permissions.py
cp v12/harness/observability.py v13/harness/observability.py
cp v12/harness/loop.py v13/harness/loop.py
```

- [ ] **Step 2: 创建 `v13/evals.py`**

```python
"""v13：eval 用例列表——直接引用 scenarios.py 里已有的场景，不新增独立的数据格式。"""

EVAL_CASES = [
    {
        "scenario": "happy_path",
        "expected_result_contains": "timeout=30",
        "max_llm_calls": 3,
    },
    {
        "scenario": "spin_then_recover",
        "expected_result_contains": "改用搜索后完成任务",
        "max_llm_calls": 8,
    },
    {
        "scenario": "flaky_api_recovers",
        "expected_result_contains": "flaky_api 最终调用成功",
        "max_llm_calls": 3,
    },
    {
        "scenario": "circuit_breaker_trips",
        "expected_result_contains": "接口修复前先记录问题并结束",
        "max_llm_calls": 6,
    },
]
```

- [ ] **Step 3: 写失败测试 `v13/tests/test_eval_runner.py`**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio

from evals import EVAL_CASES
from harness.eval_runner import (
    aggregate_results,
    compare_to_baseline,
    run_eval_case,
    run_eval_suite,
)

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


def test_aggregate_results_computes_pass_rate_and_averages():
    results = [
        {"name": "a", "passed": True, "actual_call_count": 2, "estimated_tokens": 4},
        {"name": "b", "passed": False, "actual_call_count": 6, "estimated_tokens": 8},
    ]
    report = aggregate_results(results)
    assert report["pass_rate"] == 0.5
    assert report["passed_count"] == 1
    assert report["total_count"] == 2
    assert report["avg_llm_calls"] == 4.0
    assert report["avg_tokens"] == 6.0


def test_compare_to_baseline_flags_pass_rate_drop():
    baseline = {"pass_rate": 1.0, "avg_llm_calls": 3.0}
    current = {"pass_rate": 0.75, "avg_llm_calls": 3.0}
    regressions = compare_to_baseline(current, baseline)
    assert len(regressions) == 1
    assert "通过率下降" in regressions[0]


def test_compare_to_baseline_flags_call_count_increase_beyond_tolerance():
    baseline = {"pass_rate": 1.0, "avg_llm_calls": 3.0}
    current = {"pass_rate": 1.0, "avg_llm_calls": 5.0}
    regressions = compare_to_baseline(current, baseline)
    assert len(regressions) == 1


def test_compare_to_baseline_no_regressions_when_stable():
    baseline = {"pass_rate": 1.0, "avg_llm_calls": 3.0}
    current = {"pass_rate": 1.0, "avg_llm_calls": 3.5}
    regressions = compare_to_baseline(current, baseline)
    assert regressions == []


def test_run_eval_case_happy_path_passes():
    async def body():
        case = {
            "scenario": "happy_path",
            "expected_result_contains": "timeout=30",
            "max_llm_calls": 3,
        }
        result = await run_eval_case(case, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG)
        assert result["passed"] is True
        assert result["actual_call_count"] == 2
        assert "timeout=30" in result["actual_result"]

    asyncio.run(body())


def test_run_eval_case_fails_when_expected_substring_missing():
    async def body():
        case = {"scenario": "happy_path", "expected_result_contains": "这段文字不会出现"}
        result = await run_eval_case(case, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG)
        assert result["passed"] is False

    asyncio.run(body())


def test_run_eval_case_fails_when_call_count_exceeds_max():
    async def body():
        case = {"scenario": "happy_path", "max_llm_calls": 1}
        result = await run_eval_case(case, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG)
        assert result["passed"] is False

    asyncio.run(body())


def test_run_eval_suite_all_default_cases_pass():
    async def body():
        report = await run_eval_suite(
            EVAL_CASES, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
        )
        assert report["pass_rate"] == 1.0
        assert report["total_count"] == len(EVAL_CASES)

    asyncio.run(body())
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd v13 && python3 -m pytest tests/test_eval_runner.py -v`
Expected: `ModuleNotFoundError: No module named 'harness.eval_runner'`

- [ ] **Step 5: 创建 `v13/harness/eval_runner.py`**

```python
"""v13：自动化评估框架——批量跑已有场景、和期望断言比对、和基线对比。"""

from harness.budget import Budget
from harness.loop import run_agent
from harness.observability import estimate_tokens
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import build_default_tool_registry


async def run_eval_case(case, compact_config, compression_config):
    goal, script = get_scenario(case["scenario"])
    llm = MockLLM(script)
    budget = Budget(max_steps=case.get("max_steps", 30))
    registry = build_default_tool_registry()

    result = await run_agent(
        goal, registry, llm, budget, compact_config, compression_config
    )

    passed = True
    if "expected_result_contains" in case and case["expected_result_contains"] not in result:
        passed = False
    if "max_llm_calls" in case and llm.call_count > case["max_llm_calls"]:
        passed = False

    return {
        "name": case["scenario"],
        "passed": passed,
        "actual_result": result,
        "actual_call_count": llm.call_count,
        "estimated_tokens": estimate_tokens(result),
    }


def aggregate_results(results):
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    avg_calls = sum(r["actual_call_count"] for r in results) / total if total else 0.0
    avg_tokens = sum(r["estimated_tokens"] for r in results) / total if total else 0.0
    return {
        "pass_rate": passed_count / total if total else 0.0,
        "passed_count": passed_count,
        "total_count": total,
        "avg_llm_calls": avg_calls,
        "avg_tokens": avg_tokens,
        "results": results,
    }


async def run_eval_suite(cases, compact_config, compression_config):
    results = [
        await run_eval_case(case, compact_config, compression_config) for case in cases
    ]
    return aggregate_results(results)


def compare_to_baseline(current_report, baseline_report, call_tolerance=1.0):
    regressions = []
    if current_report["pass_rate"] < baseline_report["pass_rate"]:
        regressions.append(
            f"通过率下降：{baseline_report['pass_rate']:.2f} -> {current_report['pass_rate']:.2f}"
        )
    if current_report["avg_llm_calls"] > baseline_report["avg_llm_calls"] + call_tolerance:
        regressions.append(
            f"平均 LLM 调用次数上升超过容差：{baseline_report['avg_llm_calls']:.2f} -> {current_report['avg_llm_calls']:.2f}"
        )
    return regressions
```

- [ ] **Step 6: 运行测试确认全部通过**

Run: `cd v13 && python3 -m pytest tests/test_eval_runner.py -v`
Expected: `8 passed`

- [ ] **Step 7: 修改 `v13/main.py`（新增 `--run-evals` 模式；`--scenario` 从必填改为条件必填）**

```python
import argparse
import asyncio
import json
from pathlib import Path

from evals import EVAL_CASES
from harness.budget import Budget
from harness.eval_runner import run_eval_suite
from harness.loop import run_agent
from harness.observability import EventLog, build_run_report
from harness.session_store import load_session
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
DEFAULT_COST_RATES = {"input_per_1k": 0.5, "output_per_1k": 1.5}


async def run_main(args):
    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)
    session_path = Path(args.session_file) if args.session_file else None
    event_log = EventLog() if args.report_file else None

    if session_path is not None:
        existing = load_session(session_path)
        if existing:
            print(f"[会话] 从 {len(existing)} 条历史消息续跑")
        else:
            print("[会话] 新建会话")

    try:
        result = await run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            session_path=session_path,
            timeout_seconds=args.timeout,
            permission_policy=DEFAULT_PERMISSION_POLICY,
            event_log=event_log,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")
        if event_log is not None:
            report = build_run_report(event_log.events, rates=DEFAULT_COST_RATES)
            with open(args.report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"[报告] 已写入 {args.report_file}：{report}")


async def run_evals_main():
    report = await run_eval_suite(
        EVAL_CASES, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
    )
    print(
        f"[Eval 汇总] 通过 {report['passed_count']}/{report['total_count']}，"
        f"通过率 {report['pass_rate']:.0%}，平均 LLM 调用次数 {report['avg_llm_calls']:.1f}"
    )
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['name']}（调用 {r['actual_call_count']} 次）")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
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
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="单次工具调用的超时秒数"
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=None,
        help="运行报告输出路径（JSON）；指定后记录结构化事件并生成汇总报告",
    )
    parser.add_argument(
        "--run-evals",
        action="store_true",
        help="跑一遍离线 eval 套件并打印汇总报告，忽略 --scenario",
    )
    args = parser.parse_args()

    if args.run_evals:
        asyncio.run(run_evals_main())
        return

    if not args.scenario:
        parser.error("必须指定 --scenario，除非使用 --run-evals")
    asyncio.run(run_main(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: 手动验证**

Run: `cd v13 && python3 main.py --run-evals`
Expected:
```
[Eval 汇总] 通过 4/4，通过率 100%，平均 LLM 调用次数 4.0
  [PASS] happy_path（调用 2 次）
  [PASS] spin_then_recover（调用 7 次）
  [PASS] flaky_api_recovers（调用 2 次）
  [PASS] circuit_breaker_trips（调用 5 次）
```

- [ ] **Step 9: 创建 `v13/README.md`**

```markdown
# v13：自动化评估框架

## 本版目标

到 v12 为止，"这个版本改动之后行为有没有变差"这件事完全靠人工跑几个 demo 场景肉眼观察。这一版加入一个离线批量评估框架：用已有场景配上期望断言组成一批 eval 用例，一次性跑完给出通过率和平均指标，未来还能和一份基线对比、自动标记回归。

## 新增/修改文件（对照 v12）

- 新增 `evals.py`：eval 用例列表，每条用例直接引用 `scenarios.py` 里已有的场景名字 + 期望断言（`expected_result_contains`、`max_llm_calls`），不新增独立的数据格式。
- 新增 `harness/eval_runner.py`：`run_eval_case()`（跑一个用例、和期望值比对）、`aggregate_results()`（纯函数，从一组用例结果汇总通过率/平均调用次数/平均 token）、`run_eval_suite()`（跑完整批用例再汇总）、`compare_to_baseline()`（和一份基线报告比较，标记通过率下降或平均调用次数超出容差的回归）。
- 修改 `main.py`：新增 `--run-evals` 模式；`--scenario` 从"必填"改成"除非用 `--run-evals` 否则必填"。
- 其余文件（`mock_llm.py`、`tools.py`、`scenarios.py`、`harness/loop.py` 及其余 `harness/` 子模块）与 v12 完全一致——本版本完全不修改核心循环，只是批量调用已经写好的 `run_agent()`。

## 核心设计

**为什么 eval 用例直接复用 `scenarios.py`，不新建一套独立的用例数据格式**：这个系列从 v1 起所有场景都已经是"目标 + 确定性脚本"的形式，天然适合被"再跑一遍、和期望值比对"这种评估逻辑复用；引入一套新的 YAML/JSON schema 只会带来额外的解析代码和心智负担，不会带来任何本项目场景下需要的额外表达能力。

**为什么 `aggregate_results` 单独拆成一个纯函数，而不是揉进 `run_eval_suite` 里**：`run_eval_suite` 依赖真的跑一遍场景（异步、涉及 `MockLLM`/`Budget`），测试它的汇总算术逻辑如果每次都要真的跑场景，既慢又容易因为具体场景的字符数变化而写出脆弱的断言。把"跑用例产生结果列表"和"从结果列表汇总统计数字"拆成两个函数，后者可以直接喂一组手写的、数字干净的假结果测试，不用关心真实场景内部细节。

**为什么 `compare_to_baseline` 只关心通过率下降和调用次数上升，不关心 token/成本变化**：调用次数是最直接反映"防护机制是不是被触发得更频繁了"的信号（比如某个改动意外让某个场景触发了更多重试），token/成本目前只是粗略估算，拿它做回归判断的信噪比不够高，本版本先聚焙在通过率和调用次数这两个更可靠的信号上。

## 如何运行 demo

```bash
python3 main.py --run-evals   # 跑一遍离线 eval 套件，打印通过率和每个用例的详情
```

## 局限性

`evals.py` 里的用例都是手写的、针对现有场景的断言，没有自动发现"哪些场景应该被纳入 eval 套件"的机制——加一个新场景后需要有人手动决定要不要把它加进 `EVAL_CASES`。`compare_to_baseline` 需要调用方自己准备一份 baseline 报告（本版本没有提供"自动保存/更新 baseline 文件"的 CLI 命令），这是刻意保持最小化的简化，真实系统通常会把 baseline 存成一个受版本控制的文件、在 CI 里自动比对。
```

- [ ] **Step 10: Commit**

```bash
cd Harness-from-scratch
git add v13/
git commit -m "feat(v13): offline eval framework reusing existing scenarios with baseline comparison"
```

---

## Task 15: v14 —— 动态工具/技能插件化

这一版**不修改 `harness/loop.py`**——`ToolRegistry` 是 `dict` 的行为兼容子类，`loop.py` 里所有 `tool_registry[...]`、`del tool_registry[...]`、`in`、`.keys()` 调用不需要任何改动就能继续工作。

**Files:**
- Copy from v13 (unchanged): `mock_llm.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`, `harness/validator.py`, `harness/errors.py`, `harness/retry.py`, `harness/session_store.py`, `harness/permissions.py`, `harness/observability.py`, `harness/loop.py`, `harness/eval_runner.py`, `evals.py`
- Create: `harness/tool_registry.py`
- Modify (relative to v13): `tools.py`, `scenarios.py`, `main.py`
- Test: `tests/test_tool_registry.py`
- Create: `README.md`

- [ ] **Step 1: 复制未变化的文件（包括 `harness/loop.py`——本版本不改核心循环）**

```bash
cd Harness-from-scratch
cp v13/mock_llm.py v14/mock_llm.py
cp v13/harness/__init__.py v14/harness/__init__.py
cp v13/harness/budget.py v14/harness/budget.py
cp v13/harness/loop_detector.py v14/harness/loop_detector.py
cp v13/harness/context_manager.py v14/harness/context_manager.py
cp v13/harness/validator.py v14/harness/validator.py
cp v13/harness/errors.py v14/harness/errors.py
cp v13/harness/retry.py v14/harness/retry.py
cp v13/harness/session_store.py v14/harness/session_store.py
cp v13/harness/permissions.py v14/harness/permissions.py
cp v13/harness/observability.py v14/harness/observability.py
cp v13/harness/loop.py v14/harness/loop.py
cp v13/harness/eval_runner.py v14/harness/eval_runner.py
cp v13/evals.py v14/evals.py
```

- [ ] **Step 2: 创建 `v14/harness/tool_registry.py`**

```python
"""v14：动态工具注册表——dict 的行为兼容子类，支持运行时 register/unregister。"""


class ToolRegistry(dict):
    """除了新增的 register/unregister，其余行为完全是普通 dict：
    `registry[name]`、`del registry[name]`、`name in registry`、`.keys()` 都不用改。
    """

    def register(self, tool):
        self[tool.name] = tool

    def unregister(self, name):
        self.pop(name, None)
```

- [ ] **Step 3: 写失败测试 `v14/tests/test_tool_registry.py`**

```python
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from harness.tool_registry import ToolRegistry
from harness.validator import validate_tool_call
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import Tool, build_default_tool_registry

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


async def _noop():
    return "ok"


def test_tool_registry_register_adds_tool():
    registry = ToolRegistry()
    tool = Tool("noop", _noop, {})
    registry.register(tool)
    assert "noop" in registry
    assert registry["noop"] is tool


def test_tool_registry_unregister_removes_tool():
    registry = ToolRegistry()
    registry.register(Tool("noop", _noop, {}))
    registry.unregister("noop")
    assert "noop" not in registry


def test_tool_registry_unregister_missing_tool_is_a_no_op():
    registry = ToolRegistry()
    registry.unregister("does_not_exist")  # 不应该抛异常
    assert "does_not_exist" not in registry


def test_weather_lookup_is_unknown_before_plugin_loaded():
    registry = build_default_tool_registry()
    call = {"name": "weather_lookup", "args": {"city": "北京"}}
    result = validate_tool_call(call, registry)
    assert result["ok"] is False
    assert "未知工具" in result["error"]


def test_plugin_then_use_scenario_dynamically_registers_and_calls_new_tool():
    async def scenario_body():
        goal, script = get_scenario("plugin_then_use")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry()

        result = await run_agent(
            goal, registry, llm, budget, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
        )

        assert result == "北京今天晴，22°C。"
        assert "weather_lookup" in registry

    asyncio.run(scenario_body())
```

- [ ] **Step 4: 运行测试确认部分通过**

Run: `cd v14 && python3 -m pytest tests/test_tool_registry.py -v`
Expected: 前 4 个测试通过（3 个 `ToolRegistry` 纯逻辑测试 + `test_weather_lookup_is_unknown_before_plugin_loaded`——此时 `tools.py` 确实还没有 `weather_lookup`，"未知工具"这个断言天然成立）；最后一个 `test_plugin_then_use_scenario_...` 失败，报 `KeyError: 'plugin_then_use'`（因为这一步之后才会修改 `scenarios.py` 加入这个场景，Step 5/6 都还没做）。

- [ ] **Step 5: 修改 `v14/tools.py`（`build_default_tool_registry` 返回 `ToolRegistry`，新增 `load_plugin` 和 `weather_lookup`）**

```python
"""示例工具集：内存态假文件系统 + 假搜索，配合 MockLLM 复现固定场景。"""

import asyncio

from harness.errors import TransientError
from harness.tool_registry import ToolRegistry


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
    registry = ToolRegistry()

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
        # 注意：这里在修改 fake_fs 之前没有任何 await 点，所以一旦这个协程被
        # asyncio 调度执行，就会在一个事件循环 tick 内直接跑完，asyncio.wait_for
        # 的超时永远没有机会在"已经开始写但还没写完"的中间状态把它打断。这个
        # 对超时的"安全性"只是这个函数恰好没有提前 await 带来的副产品，并不是
        # 刻意设计、可以依赖的保证——如果未来给 write_file 加上真实的 I/O 延迟
        # （比如先 await 一次网络或磁盘调用再写入 fake_fs），这个假设就不再成立。
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

    async def weather_lookup(city):
        return f"{city} 的天气（mock 数据）：晴，22°C"

    async def load_plugin(plugin_name):
        available_plugins = {
            "weather": Tool(
                "weather_lookup", weather_lookup, {"city": {"required": True}}
            ),
        }
        if plugin_name not in available_plugins:
            raise ValueError(f"未知插件: {plugin_name}")
        registry.register(available_plugins[plugin_name])
        return f"插件 {plugin_name} 已加载，新增工具：{available_plugins[plugin_name].name}"

    registry.update(
        {
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
            "load_plugin": Tool(
                "load_plugin", load_plugin, {"plugin_name": {"required": True}}
            ),
        }
    )
    return registry
```

`registry = ToolRegistry()` 在最上面创建，`load_plugin` 闭包引用的是这同一个 `registry` 变量——Python 闭包按名字延迟解析，`load_plugin` 真正被调用（远晚于 `build_default_tool_registry()` 返回）时 `registry` 早已经指向完整构建好的注册表，所以定义顺序不影响正确性。`weather_lookup` 本身**不**出现在 `registry.update(...)` 的初始集合里——它只有在 `load_plugin("weather")` 被调用后才会被注册进去，这正是"运行时动态注册"要证明的事。

- [ ] **Step 6: 扩展 `v14/scenarios.py`（复制 v13 全部场景 + 新增 1 个）**

```bash
cp v13/scenarios.py v14/scenarios.py
```

在 `SCENARIOS` 字典闭合的 `}` 之前插入：

```python
    # 第 1 轮加载 weather 插件（动态注册 weather_lookup）；第 2 轮直接调用
    # weather_lookup——证明新注册的工具能立刻通过 v6 校验、v11 权限检查并执行，
    # 不需要对这两层做任何"为了适配新工具"的改动。
    "plugin_then_use": (
        "先加载天气插件，再查询北京的天气",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "load_plugin", "args": {"plugin_name": "weather"}}
                ],
            },
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_2", "name": "weather_lookup", "args": {"city": "北京"}}
                ],
            },
            {"content": "北京今天晴，22°C。", "tool_calls": []},
        ],
    ),
```

- [ ] **Step 7: 运行测试确认全部通过**

Run: `cd v14 && python3 -m pytest tests/test_tool_registry.py -v`
Expected: `5 passed`

- [ ] **Step 8: 修改 `v14/main.py`（`--scenario` 增加 `plugin_then_use`，其余与 v13 一致）**

```python
import argparse
import asyncio
import json
from pathlib import Path

from evals import EVAL_CASES
from harness.budget import Budget
from harness.eval_runner import run_eval_suite
from harness.loop import run_agent
from harness.observability import EventLog, build_run_report
from harness.session_store import load_session
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
DEFAULT_COST_RATES = {"input_per_1k": 0.5, "output_per_1k": 1.5}


async def run_main(args):
    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)
    session_path = Path(args.session_file) if args.session_file else None
    event_log = EventLog() if args.report_file else None

    if session_path is not None:
        existing = load_session(session_path)
        if existing:
            print(f"[会话] 从 {len(existing)} 条历史消息续跑")
        else:
            print("[会话] 新建会话")

    try:
        result = await run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            session_path=session_path,
            timeout_seconds=args.timeout,
            permission_policy=DEFAULT_PERMISSION_POLICY,
            event_log=event_log,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")
        if event_log is not None:
            report = build_run_report(event_log.events, rates=DEFAULT_COST_RATES)
            with open(args.report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"[报告] 已写入 {args.report_file}：{report}")


async def run_evals_main():
    report = await run_eval_suite(
        EVAL_CASES, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
    )
    print(
        f"[Eval 汇总] 通过 {report['passed_count']}/{report['total_count']}，"
        f"通过率 {report['pass_rate']:.0%}，平均 LLM 调用次数 {report['avg_llm_calls']:.1f}"
    )
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['name']}（调用 {r['actual_call_count']} 次）")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
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
            "plugin_then_use",
        ],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--session-file",
        type=str,
        default=None,
        help="会话落盘路径；指定后支持断点续跑",
    )
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="单次工具调用的超时秒数"
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=None,
        help="运行报告输出路径（JSON）；指定后记录结构化事件并生成汇总报告",
    )
    parser.add_argument(
        "--run-evals",
        action="store_true",
        help="跑一遍离线 eval 套件并打印汇总报告，忽略 --scenario",
    )
    args = parser.parse_args()

    if args.run_evals:
        asyncio.run(run_evals_main())
        return

    if not args.scenario:
        parser.error("必须指定 --scenario，除非使用 --run-evals")
    asyncio.run(run_main(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: 手动验证**

Run: `cd v14 && python3 main.py --scenario plugin_then_use`
Expected:
```
[结果] 北京今天晴，22°C。
[LLM 调用次数] 3
```

- [ ] **Step 10: 创建 `v14/README.md`**

```markdown
# v14：动态工具/技能插件化

## 本版目标

到 v13 为止，`tool_registry` 是一次性在 `build_default_tool_registry()` 里构建好、之后只会被"删除"（循环检测禁用工具）不会被"新增"的静态集合。这一版让工具可以在运行时动态注册——更接近真实世界里"Agent 发现并加载一个新技能/插件"的场景，同时证明 v6 的输出校验和 v11 的权限检查完全不需要因为"多了一个新工具"而改动一行代码。

## 新增/修改文件（对照 v13）

- 新增 `harness/tool_registry.py`：`ToolRegistry(dict)`，新增 `register(tool)`/`unregister(name)` 两个方法，其余行为完全是普通 `dict`。
- 修改 `tools.py`：`build_default_tool_registry()` 返回 `ToolRegistry` 实例而不是普通 `dict`；新增 `load_plugin(plugin_name)` 工具（调用后把 `weather_lookup` 动态注册进 registry）和 `weather_lookup(city)` 工具本身（默认不在注册表里，只有加载插件后才存在）。
- 修改 `scenarios.py`：新增 `plugin_then_use`（先加载插件、再调用新工具）。
- 修改 `main.py`：`--scenario` 增加 `plugin_then_use`。
- 其余文件（`mock_llm.py`、`harness/loop.py` 及其余 `harness/` 子模块、`evals.py`）与 v13 完全一致——本版本不修改核心循环。

## 核心设计

**为什么 `ToolRegistry` 直接继承 `dict`，而不是包一层自己实现 `__getitem__`/`__delitem__`/`__contains__`**：v1~v13 所有代码（`harness/loop.py`、`harness/validator.py`、`harness/permissions.py`）都是用最朴素的 dict 语法操作 `tool_registry` 的——下标取值、`del`、`in`、`.keys()`。直接继承 `dict` 能免费获得这些行为的完整实现，不需要手写、也不需要担心漏实现某个魔术方法导致行为不一致；`register`/`unregister` 只是在这基础上加两个语义更清晰的方法名。

**为什么 `load_plugin` 能拿到 `registry` 自身的引用**：`load_plugin` 和 `read_file`/`write_file` 一样是 `build_default_tool_registry()` 内部定义的闭包，天然能访问同一个函数作用域里的 `registry` 变量——不需要额外的依赖注入机制，这是 Python 闭包最自然的用法。

**为什么 `weather_lookup` 不在初始注册表里、必须先 `load_plugin` 才能用**：如果 `weather_lookup` 一开始就在注册表里，"动态注册"这件事就无从谈起——本版本要证明的核心命题是"运行时新增的工具，校验和权限层不需要预先知道它的存在"，`weather_lookup` 必须真的在运行时才出现，这个证明才有意义。

## 如何运行 demo

```bash
python3 main.py --scenario plugin_then_use   # 先加载 weather 插件，再调用 weather_lookup
```

## 局限性

`load_plugin` 里"可加载的插件有哪些"是硬编码在函数内部的一个小字典（目前只有 `weather`），不是真正的"从外部文件系统/网络发现插件"这种动态发现机制——本版本只演示"注册表本身支持运行时增删"这个核心能力，真实的插件发现/加载机制（比如按约定扫描一个目录、或者对接 MCP 协议）超出本版本范围。另外，`unregister` 目前没有任何调用点使用（没有场景演示"运行时卸载一个工具"），只是为了让 `ToolRegistry` 的接口在语义上完整（有 register 就该有对应的 unregister）。
```

- [ ] **Step 11: Commit**

```bash
cd Harness-from-scratch
git add v14/
git commit -m "feat(v14): dynamic tool registry supporting runtime plugin registration"
```

---

## Task 16: v15 —— 多智能体协作（系列终点）

这一版**不修改 `harness/loop.py`**——`delegate_task` 只是一个普通工具，工具内部"递归调用 `run_agent()`"这件事完全不需要核心循环知情或配合。

**Files:**
- Copy from v14 (unchanged): `mock_llm.py`, `harness/__init__.py`, `harness/budget.py`, `harness/loop_detector.py`, `harness/context_manager.py`, `harness/validator.py`, `harness/errors.py`, `harness/retry.py`, `harness/session_store.py`, `harness/permissions.py`, `harness/observability.py`, `harness/tool_registry.py`, `harness/loop.py`, `harness/eval_runner.py`, `evals.py`
- Modify (relative to v14): `tools.py`, `scenarios.py`, `main.py`
- Test: `tests/test_delegation.py`
- Create: `README.md`

- [ ] **Step 1: 复制未变化的文件（包括 `harness/loop.py`——本版本不改核心循环）**

```bash
cd Harness-from-scratch
cp v14/mock_llm.py v15/mock_llm.py
cp v14/harness/__init__.py v15/harness/__init__.py
cp v14/harness/budget.py v15/harness/budget.py
cp v14/harness/loop_detector.py v15/harness/loop_detector.py
cp v14/harness/context_manager.py v15/harness/context_manager.py
cp v14/harness/validator.py v15/harness/validator.py
cp v14/harness/errors.py v15/harness/errors.py
cp v14/harness/retry.py v15/harness/retry.py
cp v14/harness/session_store.py v15/harness/session_store.py
cp v14/harness/permissions.py v15/harness/permissions.py
cp v14/harness/observability.py v15/harness/observability.py
cp v14/harness/tool_registry.py v15/harness/tool_registry.py
cp v14/harness/loop.py v15/harness/loop.py
cp v14/harness/eval_runner.py v15/harness/eval_runner.py
cp v14/evals.py v15/evals.py
```

- [ ] **Step 2: 扩展 `v15/scenarios.py`（复制 v14 全部场景 + 新增子任务脚本映射 + 1 个新场景）**

```bash
cp v14/scenarios.py v15/scenarios.py
```

在 `SCENARIOS = {` 这一行**之前**插入一个独立的顶层字典 `SUB_TASK_SCRIPTS`（子任务名字 -> (子任务目标, 子任务脚本)，供 `delegate_task` 工具查表使用）：

```python
# 供 delegate_task 工具查表用的子任务脚本映射：子任务名字 -> (子任务目标, 子任务脚本)。
SUB_TASK_SCRIPTS = {
    "research_pricing": (
        "调研某个产品的定价方案",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "sub_call_1", "name": "search_web", "args": {"query": "产品定价方案"}}
                ],
            },
            {"content": "调研结论：建议采用阶梯定价。", "tool_calls": []},
        ],
    ),
}


```

然后在 `SCENARIOS` 字典闭合的 `}` 之前插入新场景：

```python
    # 主循环把调研子任务委派给一个独立的子 agent（自己的 messages/Budget/
    # MockLLM），子 agent 跑 2 轮后把摘要返回，主循环收到摘要后再跑一轮完成。
    "delegate_then_finish": (
        "把价格调研委派给子任务，再总结结果",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "delegate_task", "args": {"subtask": "research_pricing"}}
                ],
            },
            {"content": "已完成价格调研并整理成最终结论。", "tool_calls": []},
        ],
    ),
```

- [ ] **Step 3: 写失败测试 `v15/tests/test_delegation.py`**

```python
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from mock_llm import MockLLM
from scenarios import SUB_TASK_SCRIPTS, get_scenario
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


def test_delegate_task_runs_subagent_and_summarizes_result_into_main_loop():
    async def scenario_body():
        goal, script = get_scenario("delegate_then_finish")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry(sub_task_scripts=SUB_TASK_SCRIPTS)

        result = await run_agent(
            goal, registry, llm, budget, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
        )

        assert result == "已完成价格调研并整理成最终结论。"
        assert llm.call_count == 2  # 主循环只有 2 轮，不包含子 agent 内部的调用次数

    asyncio.run(scenario_body())


def test_delegate_task_unknown_subtask_returns_error_without_crashing():
    async def scenario_body():
        registry = build_default_tool_registry(sub_task_scripts=SUB_TASK_SCRIPTS)
        tool = registry["delegate_task"]
        result = await tool.run({"subtask": "does_not_exist"})
        assert "未知子任务" in result

    asyncio.run(scenario_body())


def test_delegate_task_handles_subagent_script_exhaustion_gracefully():
    async def scenario_body():
        # 子任务脚本只给 1 步，且这一步还要求一次工具调用；子 agent 会在完成
        # 任务前耗尽脚本，delegate_task 需要接住这个异常、返回说明性文字，
        # 而不是让异常直接扎穿委派边界、搞崩主循环。
        incomplete_sub_scripts = {
            "flaky_subtask": (
                "一个脚本会提前耗尽的子任务",
                [
                    {
                        "content": None,
                        "tool_calls": [
                            {"id": "sc1", "name": "search_web", "args": {"query": "x"}}
                        ],
                    }
                ],
            )
        }
        registry = build_default_tool_registry(sub_task_scripts=incomplete_sub_scripts)
        tool = registry["delegate_task"]
        result = await tool.run({"subtask": "flaky_subtask"})
        assert "未能给出结果" in result

    asyncio.run(scenario_body())
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd v15 && python3 -m pytest tests/test_delegation.py -v`
Expected: 全部 3 个测试失败，均报 `TypeError: build_default_tool_registry() got an unexpected keyword argument 'sub_task_scripts'`（因为 `tools.py` 此时还是从 v14 原样复制过来的，既不接受 `sub_task_scripts` 参数也没有 `delegate_task` 工具）。

- [ ] **Step 5: 修改 `v15/tools.py`（新增 `delegate_task` 工具和 `sub_task_scripts` 参数）**

```python
"""示例工具集：内存态假文件系统 + 假搜索，配合 MockLLM 复现固定场景。"""

import asyncio

from harness.budget import Budget
from harness.errors import TransientError
from harness.loop import run_agent
from harness.tool_registry import ToolRegistry
from mock_llm import MockLLM, ScriptExhausted

_SUB_AGENT_COMPACT_CONFIG = {
    "trigger_every": 3,
    "keep_recent_count": 4,
    "exempt_tools": set(),
}
_SUB_AGENT_COMPRESSION_CONFIG = {
    "char_threshold": 4000,
    "max_compressions": 3,
    "keep_recent_count": 6,
}


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


def build_default_tool_registry(concurrency_tracker=None, sub_task_scripts=None):
    fake_fs = _make_fake_fs()
    flaky_state = {"attempts": 0}
    sub_task_scripts = sub_task_scripts or {}
    registry = ToolRegistry()

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
        # 注意：这里在修改 fake_fs 之前没有任何 await 点，所以一旦这个协程被
        # asyncio 调度执行，就会在一个事件循环 tick 内直接跑完，asyncio.wait_for
        # 的超时永远没有机会在"已经开始写但还没写完"的中间状态把它打断。这个
        # 对超时的"安全性"只是这个函数恰好没有提前 await 带来的副产品，并不是
        # 刻意设计、可以依赖的保证——如果未来给 write_file 加上真实的 I/O 延迟
        # （比如先 await 一次网络或磁盘调用再写入 fake_fs），这个假设就不再成立。
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

    async def weather_lookup(city):
        return f"{city} 的天气（mock 数据）：晴，22°C"

    async def load_plugin(plugin_name):
        available_plugins = {
            "weather": Tool(
                "weather_lookup", weather_lookup, {"city": {"required": True}}
            ),
        }
        if plugin_name not in available_plugins:
            raise ValueError(f"未知插件: {plugin_name}")
        registry.register(available_plugins[plugin_name])
        return f"插件 {plugin_name} 已加载，新增工具：{available_plugins[plugin_name].name}"

    async def delegate_task(subtask):
        if subtask not in sub_task_scripts:
            return f"Error: 未知子任务 {subtask}"

        sub_goal, sub_script = sub_task_scripts[subtask]
        sub_registry = build_default_tool_registry()
        sub_llm = MockLLM(sub_script)
        sub_budget = Budget(max_steps=10)

        try:
            sub_result = await run_agent(
                sub_goal,
                sub_registry,
                sub_llm,
                sub_budget,
                _SUB_AGENT_COMPACT_CONFIG,
                _SUB_AGENT_COMPRESSION_CONFIG,
            )
        except ScriptExhausted:
            return f"[子任务：{subtask} 未完成] 子任务脚本提前耗尽，未能给出结果"

        return f"[子任务：{subtask} 完成] {sub_result}"

    registry.update(
        {
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
            "load_plugin": Tool(
                "load_plugin", load_plugin, {"plugin_name": {"required": True}}
            ),
            "delegate_task": Tool(
                "delegate_task", delegate_task, {"subtask": {"required": True}}
            ),
        }
    )
    return registry
```

关键点：`delegate_task` 内部递归调用的 `run_agent()` 和它自己所在的这次调用是完全独立的两次 `run_agent()` 执行——各自的 `messages`、`Budget`、`MockLLM.call_count` 互不共享；子 agent 的 `sub_registry` 特意用 `build_default_tool_registry()`（不传 `sub_task_scripts`）构建，这样子 agent 自己没有 `delegate_task` 工具，杜绝无限递归委派的复杂度。`try/except ScriptExhausted` 保证子任务脚本提前耗尽这种"子 agent 自己没扛住"的情况，也能变成一条说明性的失败摘要文字返回给主循环，而不是让异常直接跨越委派边界把主循环也搞崩。

- [ ] **Step 6: 运行测试确认全部通过**

Run: `cd v15 && python3 -m pytest tests/test_delegation.py -v`
Expected: `3 passed`

- [ ] **Step 7: 修改 `v15/main.py`（构建 tool_registry 时传入 `SUB_TASK_SCRIPTS`，`--scenario` 增加 `delegate_then_finish`）**

```python
import argparse
import asyncio
import json
from pathlib import Path

from evals import EVAL_CASES
from harness.budget import Budget
from harness.eval_runner import run_eval_suite
from harness.loop import run_agent
from harness.observability import EventLog, build_run_report
from harness.session_store import load_session
from mock_llm import MockLLM, ScriptExhausted
from scenarios import SUB_TASK_SCRIPTS, get_scenario
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
DEFAULT_COST_RATES = {"input_per_1k": 0.5, "output_per_1k": 1.5}


async def run_main(args):
    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry(sub_task_scripts=SUB_TASK_SCRIPTS)
    budget = Budget(max_steps=args.max_steps)
    session_path = Path(args.session_file) if args.session_file else None
    event_log = EventLog() if args.report_file else None

    if session_path is not None:
        existing = load_session(session_path)
        if existing:
            print(f"[会话] 从 {len(existing)} 条历史消息续跑")
        else:
            print("[会话] 新建会话")

    try:
        result = await run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            session_path=session_path,
            timeout_seconds=args.timeout,
            permission_policy=DEFAULT_PERMISSION_POLICY,
            event_log=event_log,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")
        if event_log is not None:
            report = build_run_report(event_log.events, rates=DEFAULT_COST_RATES)
            with open(args.report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"[报告] 已写入 {args.report_file}：{report}")


async def run_evals_main():
    report = await run_eval_suite(
        EVAL_CASES, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
    )
    print(
        f"[Eval 汇总] 通过 {report['passed_count']}/{report['total_count']}，"
        f"通过率 {report['pass_rate']:.0%}，平均 LLM 调用次数 {report['avg_llm_calls']:.1f}"
    )
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['name']}（调用 {r['actual_call_count']} 次）")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
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
            "plugin_then_use",
            "delegate_then_finish",
        ],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--session-file",
        type=str,
        default=None,
        help="会话落盘路径；指定后支持断点续跑",
    )
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="单次工具调用的超时秒数"
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=None,
        help="运行报告输出路径（JSON）；指定后记录结构化事件并生成汇总报告",
    )
    parser.add_argument(
        "--run-evals",
        action="store_true",
        help="跑一遍离线 eval 套件并打印汇总报告，忽略 --scenario",
    )
    args = parser.parse_args()

    if args.run_evals:
        asyncio.run(run_evals_main())
        return

    if not args.scenario:
        parser.error("必须指定 --scenario，除非使用 --run-evals")
    asyncio.run(run_main(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: 手动验证**

Run: `cd v15 && python3 main.py --scenario delegate_then_finish`
Expected:
```
[结果] 已完成价格调研并整理成最终结论。
[LLM 调用次数] 2
```

（`[LLM 调用次数]` 只反映主循环的 `llm`，子 agent 内部的 2 次调用不计入这个数字——这正是"各自独立的执行预算与上下文"要证明的事。）

- [ ] **Step 9: 创建 `v15/README.md`**

```markdown
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

**为什么子 agent 的 `tool_registry` 不传 `sub_task_scripts`（也就是子 agent 自己没有 `delegate_task` 工具）**：这是刻意阻止无限递归委派——如果子 agent 也能调用 `delegate_task`，理论上可以委派出委派链，复杂度和潜在的失控风险都会显著上升，超出"最小可行的多智能体协作"这个教学目标。真实系统如果需要支持多层委派，需要额外设计委派深度限制、循环委派检测等机制，这些都留给读者自行扩展。

**为什么 `delegate_task` 要 `try/except ScriptExhausted`**：子 agent 内部也会经历 v1~v14 讲过的全部风险（脚本可能因为各种原因提前耗尽），如果不捕获，这个异常会直接从 `delegate_task` 这个工具函数里往外抛，扎穿 `_execute_call` 的 `except Exception` 兜底（`ScriptExhausted` 确实是 `Exception` 的子类，理论上会被外层 `except Exception` 接住而不是让主循环崩溃——但这样处理会把子任务失败误判成一次普通的工具执行失败，走向重试/熔断逻辑，语义上是错的：子任务没跑完不是因为工具本身不可靠，重试也解决不了"脚本没写够"这个问题）。在 `delegate_task` 内部就近捕获、转换成一条说明性文字，语义更准确，也让主循环能拿到一个有意义的失败摘要继续往下推进，而不是被无谓地重试。

## 如何运行 demo

```bash
python3 main.py --scenario delegate_then_finish
```

## 局限性

`delegate_task` 只支持一层委派（子 agent 不能再往下委派），也没有任何"多个子任务并行委派"的编排能力——如果模型一轮里发出多个 `delegate_task` 调用，它们会像其它工具一样通过 v10 的 `asyncio.gather` 并发执行，但彼此之间没有协调机制（比如子任务之间的依赖关系、结果聚合策略）。子 agent 的运行也不会计入主循环的 `event_log`（如果启用了 v12 的可观测性）、不受主循环的会话持久化配置影响——子 agent 完全独立于这些横切关注点，这是刻意的简化，真实的多智能体框架通常需要让这些能力在委派边界上传播下去。

## 系列总结

到这里，v1~v15 全部完成：从一个没有任何防护的裸循环开始，逐步加固出执行预算、循环空转检测、上下文治理、输出校验（v1~v7 里程碑整合），再到结构化错误处理、会话持久化、并发执行、权限沙箱（v8~v11），最后是可观测性、自动化评估、动态工具、多智能体协作（v12~v15）——一共十五个版本，每个版本只加一个优化点，最终拼出一个具备工业级水准的 Agent Harness 骨架。
```

- [ ] **Step 10: Commit**

```bash
cd Harness-from-scratch
git add v15/
git commit -m "feat(v15): multi-agent task delegation via a recursive run_agent tool"
```

---

## Task 17: 系列完结——更新根目录 README + v1~v15 全量回归验证

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新根目录 `README.md` 的路线图表格**，把现有的 `v12~v15` 占位行替换成 4 行具体链接 + 一句系列完结说明：

把现有表格中的

```markdown
| v12~v15 | 工业级扩展（待规划） | 见设计文档，待后续计划补充（可观测性、评估框架、动态工具、多智能体协作） |
```

替换为：

```markdown
| [v12](v12/README.md) | 可观测性与成本核算 | 结构化事件日志（JSONL）；token/成本估算；运行报告导出 |
| [v13](v13/README.md) | 自动化评估框架 | 复用已有场景 + 期望断言批量评估；通过率/平均调用次数汇总；基线回归对比 |
| [v14](v14/README.md) | 动态工具/技能插件化 | `ToolRegistry` 支持运行时注册新工具；v6 校验、v11 权限检查零改动自动适配 |
| [v15](v15/README.md) | 多智能体协作 | `delegate_task` 工具委派子任务给独立子 agent，各自独立的上下文与预算，结果摘要回填主循环 |
```

再在路线图表格下方新增一句：

```markdown
**v1~v15 全部完成。** 从裸循环到工业级多智能体协作，完整的十五个版本可以按顺序阅读，每一版只看"和上一版本的 diff"。
```

- [ ] **Step 2: 跑一遍 v12~v15 全部测试套件，确认没有相互破坏**

```bash
cd Harness-from-scratch
for v in v12 v13 v14 v15; do
  echo "=== $v ===" && (cd "$v" && python3 -m pytest tests/ -q) || exit 1
done
```

Expected: 每个版本都输出 `N passed`，没有 `FAILED` 或 `ERROR`（v12: 8 passed，v13: 8 passed，v14: 5 passed，v15: 3 passed）。

- [ ] **Step 3: 跑一遍 v1~v11 的测试，确认这一批新增代码没有意外影响到之前的版本**

```bash
cd Harness-from-scratch
for v in v1 v2 v3 v4 v5 v6 v7 v8 v9 v10 v11; do
  echo "=== $v ===" && (cd "$v" && python3 -m pytest tests/ -q) || exit 1
done
```

Expected: 全部通过（v1: 2, v2: 3, v3: 3, v4: 3, v5: 5, v6: 5, v7: 19, v8: 8, v9: 4, v10: 5, v11: 5，均为 passed）。

- [ ] **Step 4: Commit**

```bash
cd Harness-from-scratch
git add README.md
git commit -m "docs: complete the v1-v15 series with v12-v15 roadmap links"
```

---

## Self-Review 记录

- **Spec 覆盖**：设计文档"实现记录：v12~v15 详细技术方案"里针对 v12（事件日志/token估算/成本/报告）、v13（eval用例复用scenarios/批量运行/基线对比）、v14（ToolRegistry dict子类/load_plugin动态注册）、v15（delegate_task/独立子agent/结果回填）的每一条设计要点都对应到了 Task 13~16 里的具体代码和测试。"v12~v15 收尾"一节提到的"不再造一个大集成场景"在 Task 17 里得到遵守——最后一个任务只做 README 收尾 + 回归验证。
- **占位符扫描**：全部任务的代码块均为完整实现，无 `TODO`/`TBD`。
- **类型一致性**：`run_agent()` 签名从 v11 的 `(goal, tool_registry, llm, budget, compact_config, compression_config, sleep_fn, session_path, timeout_seconds, permission_policy, approve_fn)` 只在 v12 新增了 `event_log` 一个关键字参数，v13/v14/v15 完全不改这个签名——`harness/loop.py` 在 v13/v14/v15 三个版本里都是从上一版本原样复制、没有任何修改，这一点在每个任务的 Step 1 和 README 里都做了明确说明。`build_default_tool_registry()` 的签名则是 v10 引入 `concurrency_tracker`、v15 新增 `sub_task_scripts`，两个可选参数互不影响、默认值都是 `None`。`Tool`/`ToolRegistry`/`EventLog` 的字段名和方法名在所有引用处保持一致。
- **已知的、写进 README 的局限性**（非缺陷，均为刻意的范围收敛）：v12 的 token 估算只是字符数粗略换算，报告只能等运行结束后生成；v13 的 eval 用例需要手动维护、baseline 比对需要调用方自备基线报告；v14 的插件发现机制是硬编码的小字典，`unregister` 没有实际调用点；v15 只支持一层委派、不支持多子任务编排、子 agent 不继承主循环的可观测性/会话持久化配置。
