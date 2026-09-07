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
