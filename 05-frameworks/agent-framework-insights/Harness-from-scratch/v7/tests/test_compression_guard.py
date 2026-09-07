import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.context_manager import CompressionGuard, compress_history, needs_compression
from harness.loop import run_agent
from mock_llm import MockLLM
from scenarios import get_scenario
from tools import build_default_tool_registry


def test_needs_compression_true_when_over_threshold():
    messages = [{"role": "tool", "name": "search_web", "content": "x" * 200}]
    assert needs_compression(messages, {"char_threshold": 100}) is True


def test_needs_compression_false_when_under_threshold():
    messages = [{"role": "tool", "name": "search_web", "content": "x" * 10}]
    assert needs_compression(messages, {"char_threshold": 100}) is False


def test_compress_history_keeps_system_and_recent_messages():
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "tool", "name": "search_web", "content": "old-1"},
        {"role": "tool", "name": "search_web", "content": "old-2"},
        {"role": "tool", "name": "search_web", "content": "recent"},
    ]
    compressed = compress_history(messages, keep_recent_count=1)
    assert compressed[0] == {"role": "system", "content": "system prompt"}
    assert "[compressed]" in compressed[1]["content"]
    assert compressed[-1]["content"] == "recent"


def test_compression_guard_trips_after_max_compressions():
    guard = CompressionGuard(max_compressions=3)
    for _ in range(3):
        assert guard.is_exhausted() is False
        guard.record_compression()
    assert guard.is_exhausted() is True


def test_oversized_output_scenario_trips_the_safety_valve():
    goal, script = get_scenario("oversized_tool_output")
    llm = MockLLM(script)
    budget = Budget(max_steps=30)
    tool_registry = build_default_tool_registry()
    compact_config = {"trigger_every": 100, "keep_recent_count": 100, "exempt_tools": set()}
    compression_config = {"char_threshold": 100, "max_compressions": 3, "keep_recent_count": 2}

    result = run_agent(
        goal, tool_registry, llm, budget, compact_config, compression_config
    )

    assert result == "上下文空间已耗尽，结束本轮对话"
