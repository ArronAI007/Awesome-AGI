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
