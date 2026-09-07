import argparse
import asyncio
import json
from pathlib import Path

from evals import EVAL_CASES
from harness.budget import Budget
from harness.eval_runner import run_eval_suite
from harness.loop import run_agent
from harness.observability import EventLog, build_run_report
from harness.session_store import load_session
from mock_llm import MockLLM, ScriptExhausted
from scenarios import SUB_TASK_SCRIPTS, get_scenario
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
DEFAULT_PERMISSION_POLICY = {
    "write_file": "ask",
    "delete_all_files": "deny",
}
DEFAULT_COST_RATES = {"input_per_1k": 0.5, "output_per_1k": 1.5}


async def run_main(args):
    goal, script = get_scenario(args.scenario)
    llm = MockLLM(script)
    tool_registry = build_default_tool_registry(sub_task_scripts=SUB_TASK_SCRIPTS)
    budget = Budget(max_steps=args.max_steps)
    session_path = Path(args.session_file) if args.session_file else None
    event_log = EventLog() if args.report_file else None

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
            permission_policy=DEFAULT_PERMISSION_POLICY,
            event_log=event_log,
        )
        print(f"[结果] {result}")
    except ScriptExhausted as exc:
        print(f"[未停止] {exc}")
    finally:
        print(f"[LLM 调用次数] {llm.call_count}")
        if event_log is not None:
            report = build_run_report(event_log.events, rates=DEFAULT_COST_RATES)
            with open(args.report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"[报告] 已写入 {args.report_file}：{report}")


async def run_evals_main():
    report = await run_eval_suite(
        EVAL_CASES, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
    )
    print(
        f"[Eval 汇总] 通过 {report['passed_count']}/{report['total_count']}，"
        f"通过率 {report['pass_rate']:.0%}，平均 LLM 调用次数 {report['avg_llm_calls']:.1f}"
    )
    for r in report["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['name']}（调用 {r['actual_call_count']} 次）")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
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
            "ask_then_approved",
            "ask_then_denied",
            "deny_dangerous_tool",
            "plugin_then_use",
            "delegate_then_finish",
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
        "--timeout", type=float, default=5.0, help="单次工具调用的超时秒数"
    )
    parser.add_argument(
        "--report-file",
        type=str,
        default=None,
        help="运行报告输出路径（JSON）；指定后记录结构化事件并生成汇总报告",
    )
    parser.add_argument(
        "--run-evals",
        action="store_true",
        help="跑一遍离线 eval 套件并打印汇总报告，忽略 --scenario",
    )
    args = parser.parse_args()

    if args.run_evals:
        asyncio.run(run_evals_main())
        return

    if not args.scenario:
        parser.error("必须指定 --scenario，除非使用 --run-evals")
    asyncio.run(run_main(args))


if __name__ == "__main__":
    main()
