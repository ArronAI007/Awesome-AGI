import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.budget import Budget
from harness.loop import run_agent
from harness.session_store import load_session
from mock_llm import MockLLM, ScriptExhausted
from scenarios import get_scenario
from tools import ConcurrencyTracker, build_default_tool_registry

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


class RecordingSleep:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)


def test_parallel_tools_scenario_runs_calls_concurrently():
    async def scenario_body():
        goal, script = get_scenario("parallel_tools")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        tracker = ConcurrencyTracker()
        registry = build_default_tool_registry(concurrency_tracker=tracker)

        result = await run_agent(
            goal, registry, llm, budget, DEFAULT_COMPACT_CONFIG, DEFAULT_COMPRESSION_CONFIG
        )

        assert result == "已并发完成两个调用。"
        assert tracker.peak >= 2

    asyncio.run(scenario_body())


def test_slow_tool_gets_cancelled_by_timeout_instead_of_hanging():
    async def scenario_body():
        goal, script = get_scenario("slow_tool_timeout")
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
            timeout_seconds=0.05,
        )

        assert result == "慢工具超时了，已记录并结束。"

    asyncio.run(scenario_body())


def test_flaky_api_retry_still_works_with_injected_async_sleep_fn():
    async def scenario_body():
        goal, script = get_scenario("flaky_api_recovers")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry()
        sleep_fn = RecordingSleep()

        result = await run_agent(
            goal,
            registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            sleep_fn=sleep_fn,
        )

        assert result == "flaky_api 最终调用成功。"
        assert sleep_fn.calls == [1.0, 2.0]

    asyncio.run(scenario_body())


def test_circuit_breaker_still_trips_after_async_conversion():
    async def scenario_body():
        goal, script = get_scenario("circuit_breaker_trips")
        llm = MockLLM(script)
        budget = Budget(max_steps=30)
        registry = build_default_tool_registry()
        sleep_fn = RecordingSleep()

        result = await run_agent(
            goal,
            registry,
            llm,
            budget,
            DEFAULT_COMPACT_CONFIG,
            DEFAULT_COMPRESSION_CONFIG,
            sleep_fn=sleep_fn,
        )

        assert result == "接口修复前先记录问题并结束。"
        assert llm.call_count == 5
        assert sleep_fn.calls == [1.0, 2.0, 4.0] * 3

    asyncio.run(scenario_body())


def test_session_persistence_still_works_after_async_conversion(tmp_path):
    async def scenario_body():
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
            await run_agent(
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

        assert crashed
        assert len(load_session(session_path)) == 4

    asyncio.run(scenario_body())
