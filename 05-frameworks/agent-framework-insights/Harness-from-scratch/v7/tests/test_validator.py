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
