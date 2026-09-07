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


def test_spin_then_recover_scenario_logs_circuit_breaker_guardrail_events():
    # 注意：自 v8 引入熔断器（阈值 3）后，read_file(bad.txt) 连续失败 3 次就会
    # 被熔断器提前拦截，call_history 达不到循环检测所需的 5 条相同记录，
    # 因此这里触发的防护是 circuit_breaker（2 次），而不是 loop_detector。
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
        assert report["guardrail_counts"] == {"circuit_breaker": 2}
        assert report["tool_call_failure_count"] == 3  # 3 次 read_file(bad.txt) 失败后熔断
        assert report["tool_call_success_count"] == 1  # 1 次 search_web 成功

    asyncio.run(scenario_body())
