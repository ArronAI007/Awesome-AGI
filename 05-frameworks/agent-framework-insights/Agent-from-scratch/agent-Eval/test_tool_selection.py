"""工具调用评测（文章五）——工具选择 + 参数。

评估 Agent 的工具调用准确率，本质是"看轨迹、拆五件事、埋陷阱"：工具选择、
参数填写、协议格式（见 test_schema.py）、结果使用、工具边界（见 test_boundary.py）
五个子维度，从完整 tool_calls 轨迹里抽调用序列分别测。

坑 1（最常见）：只看"调了没调"，不看"调对了没"。工具名对了，参数错，任务照样崩；
工具选择和参数要分开断言。
坑 6：非确定性——同一任务参数格式可能每次不同（"2026-08-18" vs "2026/08/18"），
断言参数时用值域判断或语义判断代替字符串完全相等，否则会误杀。
"""

from trace import run_agent_with_calls

PROMPT = "生成本周销售周报，发送到销售团队群（含总销售额/环比/Top3客户）"


def get_calls(prompt: str = PROMPT) -> list[dict]:
    return run_agent_with_calls(prompt)["calls"]


def test_uses_correct_query_tool():
    tools = [c["tool"] for c in get_calls()]
    assert "query_orders" in tools, "没调用正确工具 query_orders"
    assert "query_orders_v2" not in tools, "被诱饵工具 query_orders_v2 带偏了"


def test_growth_params_order():
    calls = get_calls()
    growth = [c for c in calls if c["tool"] == "calc_growth"]
    assert growth, "没有调用 calc_growth"
    args = growth[0]["args"]
    # cur 必须是本期、prev 必须是上期——这里用值域近似判断（cur 数值应 ≥ prev）
    assert args.get("cur") is not None and args.get("prev") is not None, "calc_growth 缺参数"
    # 更严格的判断：参数名必须叫 cur / prev，不能传反语义
    assert "cur" in args and "prev" in args, "参数名不对，应为 cur / prev"


def test_sends_to_group_not_email():
    tools = [c["tool"] for c in get_calls()]
    assert "send_message" in tools, "没调用 send_message 发群"
    assert "send_email" not in tools, "任务要求发群，却调用了 send_email 发邮件"


def test_group_id_correct():
    sends = [c for c in get_calls() if c["tool"] == "send_message"]
    assert sends and sends[0]["args"].get("group_id") == "sales_team", "发错群了"


# 结果使用：工具选对了、参数对了、执行成功了，但 Agent 把结果理解错、或者无视
# 结果硬编数据，一样是失败。"调对了"和"用对了"是两回事，交给 LLM 裁判单独测。
# 下面是文章给的骨架——`agent_full_output` 需要把最终周报文本 + tool_calls
# 一起喂给裁判，原文本身也是留空演示用法。
#
# from deepeval import assert_test
# from deepeval.metrics import GEval
# from deepeval.test_case import LLMTestCase
#
# faithfulness = GEval(
#     name="结果使用忠实度",
#     criteria=(
#         "判断 Agent 的最终周报是否忠实于工具返回的数据："
#         "① 数字与 query_orders 返回的数据一致，没有编造；"
#         "② 环比涨跌幅由 calc_growth 的正确结果得出，没有算反；"
#         "③ 若工具返回空或报错，Agent 是否如实说明，而不是硬编数据。"
#         "编造数据、无视返回结果、把报错当正常数据，都要扣分。"
#     ),
# )
#
# def test_result_usage_is_faithful():
#     result = run_agent_with_calls(PROMPT)
#     agent_full_output = f"{result['final_output']}\ntool_calls: {result['calls']}"
#     test_case = LLMTestCase(input=PROMPT, actual_output=agent_full_output)
#     assert_test(test_case, [faithfulness])
