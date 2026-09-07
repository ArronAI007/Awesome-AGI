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
    # 每次工具返回一段 500 字符的超长文本，用来触发压缩安全阀：
    # 即使压缩后，保留的最近消息本身依然超过阈值，会连续压缩到熔断为止。
    # （v6 的 scenarios.py 在新增校验相关场景时遗漏了这一个；v7 补回，
    # 以便 tests/test_compression_guard.py 能在本目录独立验证压缩安全阀。）
    "oversized_tool_output": (
        "反复查询一个返回超长内容的接口",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": f"call_{i}", "name": "search_web", "args": {"query": f"big_{i}"}}
                ],
            }
            for i in range(10)
        ]
        + [{"content": "查询完成。", "tool_calls": []}],
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
    # 综合场景：先触发循环检测（5 次调用同一坏工具被禁用），
    # 紧接着模型犯了一次校验错误（调用了一个不存在的工具）又自己纠正，
    # 最后正常完成——验证循环检测和输出校验在同一个 run 里不冲突。
    "combined_recovery": (
        "读取 bad.txt，失败就换个办法，然后总结配置文件",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "c1", "name": "read_file", "args": {"path": "bad.txt"}}
                ],
            }
        ]
        * 5
        + [
            # read_file 已被循环检测禁用；模型调用了一个不存在的工具 append_note。
            {
                "content": None,
                "tool_calls": [
                    {"id": "c6", "name": "append_note", "args": {"path": "note.txt"}}
                ],
            },
            # 校验失败回填后，模型补全参数重试。
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "c7",
                        "name": "write_file",
                        "args": {"path": "note.txt", "content": "已记录失败原因"},
                    }
                ],
            },
            {"content": "已完成：记录了失败原因并结束任务。", "tool_calls": []},
        ],
    ),
    # flaky_api 前 2 次调用失败，第 3 次成功；重试发生在同一次工具调用内部，
    # 模型只看到 1 次 tool_calls，LLM 调用次数不受重试次数影响。
    "flaky_api_recovers": (
        "调用一次不稳定的接口并汇报结果",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "flaky_api", "args": {"query": "ping"}}
                ],
            },
            {"content": "flaky_api 最终调用成功。", "tool_calls": []},
        ],
    ),
    # read_file 对不存在的文件抛 FileNotFoundError，属于不可重试错误，
    # 应该立刻失败，不触发任何一次退避等待。
    "non_retryable_failure": (
        "尝试读取一个不存在的文件",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "missing.txt"}}
                ],
            },
            {"content": "文件不存在，已记录错误。", "tool_calls": []},
        ],
    ),
    # always_fails_api 永远失败：前 3 次调用各自内部重试 3 次后放弃（熔断计数
    # 逐次 +1），第 4 次调用时熔断已达到阈值 3，直接被拦截、不再产生任何重试。
    "circuit_breaker_trips": (
        "反复调用一个持续故障的接口",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": f"call_{i}", "name": "always_fails_api", "args": {"query": "x"}}
                ],
            }
            for i in range(4)
        ]
        + [{"content": "接口修复前先记录问题并结束。", "tool_calls": []}],
    ),
    # 用于演示断点续跑：这段脚本会在完成任务前耗尽，模拟进程崩溃。
    # 需要配合 --session-file 使用；崩溃后用 resume_phase2 场景 + 同一个
    # --session-file 续跑。
    "resume_phase1": (
        "读取配置文件并总结",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}}
                ],
            }
        ],
    ),
    # 续跑脚本：从 resume_phase1 崩溃的地方接着跑完。
    "resume_phase2": (
        "读取配置文件并总结",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_2", "name": "search_web", "args": {"query": "补充信息"}}
                ],
            },
            {"content": "配置文件内容：timeout=30, retries=3，并补充了搜索结果。", "tool_calls": []},
        ],
    ),
    # 一轮 LLM 响应里同时给出 2 个互相独立的 tool_calls，验证它们并发执行。
    "parallel_tools": (
        "同时读取配置文件并搜索补充信息",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "config.yaml"}},
                    {"id": "call_2", "name": "search_web", "args": {"query": "补充信息"}},
                ],
            },
            {"content": "已并发完成两个调用。", "tool_calls": []},
        ],
    ),
    # slow_tool 耗时 0.2 秒；配合很短的 timeout_seconds 验证超时取消生效，
    # 而不是让整个运行卡住。
    "slow_tool_timeout": (
        "调用一个可能很慢的工具",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "slow_tool", "args": {"query": "big-job"}}
                ],
            },
            {"content": "慢工具超时了，已记录并结束。", "tool_calls": []},
        ],
    ),
    # write_file 配置为 "ask"，假 approve_fn 批准 → 正常执行成功。
    "ask_then_approved": (
        "写一个笔记文件",
        [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "write_file",
                        "args": {"path": "note.txt", "content": "hello"},
                    }
                ],
            },
            {"content": "笔记已写入。", "tool_calls": []},
        ],
    ),
    # 同样是 "ask" 规则，这次假 approve_fn 拒绝；模型换一种方式
    # （改用 search_web）完成任务，验证拒绝后能优雅回填、不崩溃。
    "ask_then_denied": (
        "写一个笔记文件，如果不被允许就换个方式记录",
        [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "name": "write_file",
                        "args": {"path": "note.txt", "content": "hello"},
                    }
                ],
            },
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_2",
                        "name": "search_web",
                        "args": {"query": "笔记记录替代方案"},
                    }
                ],
            },
            {"content": "改用搜索记录了替代方案。", "tool_calls": []},
        ],
    ),
    # delete_all_files 配置为 "deny"：无论 approve_fn 是什么都会被直接拦截，
    # 验证 deny 的优先级高于任何审批回调。
    "deny_dangerous_tool": (
        "清空所有文件",
        [
            {
                "content": None,
                "tool_calls": [{"id": "call_1", "name": "delete_all_files", "args": {}}],
            },
            {"content": "危险操作被拒绝，任务结束。", "tool_calls": []},
        ],
    ),
    # 第 1 轮加载 weather 插件（动态注册 weather_lookup）；第 2 轮直接调用
    # weather_lookup——证明新注册的工具能立刻通过 v6 校验、v11 权限检查并执行，
    # 不需要对这两层做任何"为了适配新工具"的改动。
    "plugin_then_use": (
        "先加载天气插件，再查询北京的天气",
        [
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "name": "load_plugin", "args": {"plugin_name": "weather"}}
                ],
            },
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_2", "name": "weather_lookup", "args": {"city": "北京"}}
                ],
            },
            {"content": "北京今天晴，22°C。", "tool_calls": []},
        ],
    ),
}


def get_scenario(name):
    return SCENARIOS[name]
