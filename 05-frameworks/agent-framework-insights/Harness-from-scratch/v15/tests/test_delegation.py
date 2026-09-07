import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from mock_llm import MockLLM
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


def test_delegate_task_runs_subagent_and_summarizes_result_into_main_loop():
    async def scenario_body():
        goal, script = get_scenario("delegate_then_finish")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry(sub_task_scripts=SUB_TASK_SCRIPTS)

        result = await run_agent(
            goal, registry, llm, budget, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
        )

        assert result == "已完成价格调研并整理成最终结论。"
        assert llm.call_count == 2  # 主循环只有 2 轮，不包含子 agent 内部的调用次数

    asyncio.run(scenario_body())


def test_delegate_task_unknown_subtask_returns_error_without_crashing():
    async def scenario_body():
        registry = build_default_tool_registry(sub_task_scripts=SUB_TASK_SCRIPTS)
        tool = registry["delegate_task"]
        result = await tool.run({"subtask": "does_not_exist"})
        assert "未知子任务" in result

    asyncio.run(scenario_body())


def test_delegate_task_handles_subagent_script_exhaustion_gracefully():
    async def scenario_body():
        # 子任务脚本只给 1 步，且这一步还要求一次工具调用；子 agent 会在完成
        # 任务前耗尽脚本，delegate_task 需要接住这个异常、返回说明性文字，
        # 而不是让异常直接扎穿委派边界、搞崩主循环。
        incomplete_sub_scripts = {
            "flaky_subtask": (
                "一个脚本会提前耗尽的子任务",
                [
                    {
                        "content": None,
                        "tool_calls": [
                            {"id": "sc1", "name": "search_web", "args": {"query": "x"}}
                        ],
                    }
                ],
            )
        }
        registry = build_default_tool_registry(sub_task_scripts=incomplete_sub_scripts)
        tool = registry["delegate_task"]
        result = await tool.run({"subtask": "flaky_subtask"})
        assert "未能给出结果" in result

    asyncio.run(scenario_body())
