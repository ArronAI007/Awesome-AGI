import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from harness.session_store import append_message, load_session
from mock_llm import MockLLM, ScriptExhausted
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


def test_append_message_writes_one_json_line_per_call(tmp_path):
    session_path = tmp_path / "session.jsonl"
    append_message(session_path, {"role": "system", "content": "a"})
    append_message(session_path, {"role": "user", "content": "b"})
    lines = session_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_load_session_returns_empty_list_when_file_missing(tmp_path):
    session_path = tmp_path / "missing.jsonl"
    assert load_session(session_path) == []


def test_load_session_round_trips_messages(tmp_path):
    session_path = tmp_path / "session.jsonl"
    append_message(session_path, {"role": "system", "content": "你是一个通用任务助手。"})
    append_message(session_path, {"role": "user", "content": "读取配置文件并总结"})
    loaded = load_session(session_path)
    assert loaded == [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": "读取配置文件并总结"},
    ]


def test_crash_then_resume_completes_with_full_message_history(tmp_path):
    session_path = tmp_path / "session.jsonl"
    goal = "读取配置文件并总结"

    phase1_script = [
        {
            "content": None,
            "tool_calls": [
                {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}}
            ],
        }
    ]
    llm_phase1 = MockLLM(phase1_script)
    budget_phase1 = Budget(max_steps=30)
    registry = build_default_tool_registry()

    crashed = False
    try:
        run_agent(
            goal,
            registry,
            llm_phase1,
            budget_phase1,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            session_path=session_path,
        )
    except ScriptExhausted:
        crashed = True

    assert crashed, "phase 1 脚本应该在完成任务前就耗尽，模拟进程崩溃"
    messages_after_crash = load_session(session_path)
    assert len(messages_after_crash) == 4  # system, user, assistant, tool

    phase2_script = [
        {
            "content": None,
            "tool_calls": [
                {"id": "call_2", "name": "search_web", "args": {"query": "补充信息"}}
            ],
        },
        {"content": "配置文件内容：timeout=30, retries=3，并补充了搜索结果。", "tool_calls": []},
    ]
    llm_phase2 = MockLLM(phase2_script)
    budget_phase2 = Budget(max_steps=30)

    result = run_agent(
        goal,
        registry,
        llm_phase2,
        budget_phase2,
        DEFAULT_COMPACT_CONFIG,
        DEFAULT_COMPRESSION_CONFIG,
        session_path=session_path,
    )

    assert result == "配置文件内容：timeout=30, retries=3，并补充了搜索结果。"
    assert llm_phase2.call_count == 2
    messages_after_resume = load_session(session_path)
    assert len(messages_after_resume) == 6  # 4 条旧的 + assistant 和 tool 各一条新的
    assert messages_after_resume[:4] == messages_after_crash
