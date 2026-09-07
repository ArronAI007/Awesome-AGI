"""重规划评测（文章四）——故障注入：看 Agent 会不会调整，而不是死磕。

这是规划评测里最有含金量的一环。用 mock 把某个工具中途"弄坏"，看 Agent 是死磕
还是调整。重规划要双向看：该坚持的坚持、该调整的调整——不是"挂了会不会兜"就够了，
还要看"会不会为了兜底把好好的计划改坏"。
"""

from unittest import mock

from trace import run_agent_with_trace

TASK = "帮我做一份 Q3 经营复盘（详细需求见 PRD）"


def test_agent_replans_when_data_source_down():
    # 让 query_sales 第一次调用就抛异常（模拟数据库挂了）。
    # 注意："my_agent.query_sales" 是原文里"你自己的 Agent 模块.某个工具函数"的
    # 占位写法，换成你实际项目里 query_sales 所在的模块路径——它不是指这个仓库
    # 旁边的 my_agent/ 项目（那边没有叫 query_sales 的工具）。
    with mock.patch("my_agent.query_sales", side_effect=ConnectionError("db down")):
        trace = run_agent_with_trace(TASK)
    thoughts = [e["content"] for e in trace if e["type"] == "thought"]

    # 关键判据：Agent 有没有"意识到失败并调整"，而不是反复重试同一个动作
    retry_count = sum(1 for e in trace if e["type"] == "tool_call" and e["tool"] == "query_sales")
    assert retry_count <= 2, f"数据库挂了还在反复重试 {retry_count} 次，没有重规划"
    # 有没有给出兜底（比如报告数据缺失、通知负责人）
    assert any("兜底" in t or "通知" in t or "缺失" in t for t in thoughts), \
        "数据库挂了之后，Agent 没有体现任何调整/兜底动作"
