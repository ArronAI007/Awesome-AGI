import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.context_manager import compact_if_needed
from harness.loop import run_agent
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import build_default_tool_registry

DEFAULT_COMPRESSION_CONFIG = {
    "char_threshold": 4000,
    "max_compressions": 3,
    "keep_recent_count": 6,
}


def test_compact_if_needed_clears_old_tool_messages_beyond_keep_window():
    messages = [{"role": "tool", "name": "search_web", "content": "x" * 100} for _ in range(5)]
    config = {"trigger_every": 1, "keep_recent_count": 2, "exempt_tools": set()}

    compact_if_needed(messages, iteration=1, config=config)

    assert messages[0]["content"].startswith("[cleared:")
    assert messages[-1]["content"] == "x" * 100  # 最近 2 条不受影响
    assert messages[-2]["content"] == "x" * 100


def test_compact_if_needed_respects_exempt_tools():
    messages = [{"role": "tool", "name": "read_file", "content": "重要原文内容"} for _ in range(5)]
    config = {"trigger_every": 1, "keep_recent_count": 1, "exempt_tools": {"read_file"}}

    compact_if_needed(messages, iteration=1, config=config)

    assert all(m["content"] == "重要原文内容" for m in messages)


def test_long_search_session_gets_compacted_but_still_completes():
    goal, script = get_scenario("long_search_session")
    llm = MockLLM(script)
    budget = Budget(max_steps=30)
    tool_registry = build_default_tool_registry()
    compact_config = {"trigger_every": 3, "keep_recent_count": 4, "exempt_tools": set()}

    result = run_agent(
        goal, tool_registry, llm, budget, compact_config, DEFAULT_COMPRESSION_CONFIG
    )

    assert result == "8 个关键词都搜索完了。"
    assert llm.call_count == 9
