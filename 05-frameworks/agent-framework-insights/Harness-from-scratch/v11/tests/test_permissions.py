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
