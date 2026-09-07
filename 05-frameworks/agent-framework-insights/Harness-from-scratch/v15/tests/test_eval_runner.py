import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio

import harness.eval_runner as eval_runner_module
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


def test_compare_to_baseline_raises_when_baseline_missing_required_field():
    baseline = {"pass_rate": 1.0}
    current = {"pass_rate": 1.0, "avg_llm_calls": 3.0}
    try:
        compare_to_baseline(current, baseline)
        assert False, "应该抛出 ValueError"
    except ValueError as exc:
        assert "avg_llm_calls" in str(exc)


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


def test_run_eval_case_returns_failed_result_instead_of_raising(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("模拟运行时异常")

    monkeypatch.setattr(eval_runner_module, "run_agent", boom)

    async def body():
        case = {"scenario": "happy_path"}
        result = await run_eval_case(case, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG)
        assert result["passed"] is False
        assert "模拟运行时异常" in result["actual_result"]

    asyncio.run(body())


def test_run_eval_suite_all_default_cases_pass():
    async def body():
        report = await run_eval_suite(
            EVAL_CASES, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
        )
        assert report["pass_rate"] == 1.0
        assert report["total_count"] == len(EVAL_CASES)

    asyncio.run(body())
