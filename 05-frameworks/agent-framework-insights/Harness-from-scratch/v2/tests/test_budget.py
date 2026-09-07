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
