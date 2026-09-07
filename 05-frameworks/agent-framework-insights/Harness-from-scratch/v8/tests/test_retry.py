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
