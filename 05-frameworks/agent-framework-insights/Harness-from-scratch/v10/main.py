import argparse
import asyncio
from pathlib import Path

from harness.budget import Budget
from harness.loop import run_agent
from harness.session_store import load_session
from mock_llm import MockLLM, ScriptExhausted
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


async def run_main(args):
    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry()
    budget = Budget(max_steps=args.max_steps)
    session_path = Path(args.session_file) if args.session_file else None

    if session_path is not None:
        existing = load_session(session_path)
        if existing:
            print(f"[会话] 从 {len(existing)} 条历史消息续跑")
        else:
            print("[会话] 新建会话")

    try:
        result = await run_agent(
            goal,
            tool_registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            session_path=session_path,
            timeout_seconds=args.timeout,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        required=True,
        choices=[
            "happy_path",
            "runaway",
            "spin_then_recover",
            "long_search_session",
            "oversized_tool_output",
            "missing_required_arg_then_fix",
            "unknown_tool_repeated",
            "combined_recovery",
            "flaky_api_recovers",
            "non_retryable_failure",
            "circuit_breaker_trips",
            "resume_phase1",
            "resume_phase2",
            "parallel_tools",
            "slow_tool_timeout",
        ],
    )
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--session-file",
        type=str,
        default=None,
        help="会话落盘路径；指定后支持断点续跑",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="单次工具调用的超时秒数",
    )
    args = parser.parse_args()
    asyncio.run(run_main(args))


if __name__ == "__main__":
    main()
