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

    try:
        result = await run_agent(
            goal, registry, llm, budget, compact_config, compression_config
        )
    except Exception as exc:  # noqa: BLE001 - 单个用例异常应记为失败，不能拖垮整批评估
        return {
            "name": case["scenario"],
            "passed": False,
            "actual_result": f"Error: {exc}",
            "actual_call_count": llm.call_count,
            "estimated_tokens": 0,
        }

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
    for key in ("pass_rate", "avg_llm_calls"):
        if key not in baseline_report:
            raise ValueError(f"baseline_report 缺少必需字段：{key}")

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
