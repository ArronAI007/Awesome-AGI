"""v13：eval 用例列表——直接引用 scenarios.py 里已有的场景，不新增独立的数据格式。"""

EVAL_CASES = [
    {
        "scenario": "happy_path",
        "expected_result_contains": "timeout=30",
        "max_llm_calls": 3,
    },
    {
        "scenario": "spin_then_recover",
        "expected_result_contains": "改用搜索后完成任务",
        "max_llm_calls": 8,
    },
    {
        "scenario": "flaky_api_recovers",
        "expected_result_contains": "flaky_api 最终调用成功",
        "max_llm_calls": 3,
    },
    {
        "scenario": "circuit_breaker_trips",
        "expected_result_contains": "接口修复前先记录问题并结束",
        "max_llm_calls": 6,
    },
]
