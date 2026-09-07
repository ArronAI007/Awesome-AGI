"""工具边界评测（文章五）——欠调用 / 过度调用。

坑 5：欠调用/过度调用没测，是工具调用维度最容易被漏的一层。一个 Agent 工具选择、
参数、结果全对，但该调不调（靠幻觉硬答）或者不该调瞎调（凑步骤），一样要命。
"""

from trace import run_agent_with_calls


def test_no_overcalling_on_common_knowledge():
    # 常识问题不该调工具
    calls = run_agent_with_calls("今天是星期几？")["calls"]
    assert not calls, f"常识问题不该调工具，却调了 {len(calls)} 次"


def test_no_undercalling_on_data_task():
    # 需要数据的问题必须调工具，不能硬编
    calls = run_agent_with_calls("查一下本周订单总额")["calls"]
    assert any(c["tool"] == "query_orders" for c in calls), "需要数据却没调工具，有幻觉风险"
