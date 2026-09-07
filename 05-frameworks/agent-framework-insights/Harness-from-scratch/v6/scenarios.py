"""场景定义：每个场景是 (goal, script) 二元组。"""


def _repeat(response, times):
    return [response for _ in range(times)]


SCENARIOS = {
    "happy_path": (
        "读取配置文件并总结",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}}
                ],
            },
            {"content": "配置文件内容：timeout=30, retries=3。", "tool_calls": []},
        ],
    ),
    "runaway": (
        "读取 bad.txt 并总结",
        _repeat(
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_x", "name": "read_file", "args": {"path": "bad.txt"}}
                ],
            },
            50,
        ),
    ),
    # 模型连续 5 次用相同参数调用 read_file；工具被临时禁用后，
    # 第 6 次调用改用 search_web 成功，第 7 次返回空 tool_calls 结束。
    "spin_then_recover": (
        "读取 bad.txt，如果失败就想别的办法",
        _repeat(
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_x", "name": "read_file", "args": {"path": "bad.txt"}}
                ],
            },
            5,
        )
        + [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_6",
                        "name": "search_web",
                        "args": {"query": "bad.txt 内容 替代方案"},
                    }
                ],
            },
            {"content": "改用搜索后完成任务。", "tool_calls": []},
        ],
    ),
    # 连续 8 次搜索调用，每次返回一段较长的文本，用来触发上下文裁剪。
    "long_search_session": (
        "帮我依次搜索 8 个关键词并总结",
        [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{i}",
                        "name": "search_web",
                        "args": {"query": f"keyword_{i}"},
                    }
                ],
            }
            for i in range(8)
        ]
        + [{"content": "8 个关键词都搜索完了。", "tool_calls": []}],
    ),
    # 第 1 步漏填必填参数 path；第 2 步模型自纠，补上正确参数并成功。
    "missing_required_arg_then_fix": (
        "读取配置文件",
        [
            {
                "content": None,
                "tool_calls": [{"id": "call_1", "name": "read_file", "args": {}}],
            },
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_2", "name": "read_file", "args": {"path": "config.yaml"}}
                ],
            },
            {"content": "读取成功：timeout=30。", "tool_calls": []},
        ],
    ),
    # 连续 3 次调用一个不存在的工具，触发连续校验失败熔断。
    "unknown_tool_repeated": (
        "帮我删除所有临时文件",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": f"call_{i}", "name": "delete_everything", "args": {}}
                ],
            }
            for i in range(3)
        ],
    ),
}


def get_scenario(name):
    return SCENARIOS[name]
