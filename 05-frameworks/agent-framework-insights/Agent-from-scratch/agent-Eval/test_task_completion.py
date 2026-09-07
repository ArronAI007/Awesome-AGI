"""任务完成度评测（文章三）——Agent 测评集的第一版最小基座。

Agent 和普通函数有四个本质差异，导致传统测试思路在它身上四处失灵：非确定性、
重过程（结果对不代表过程对）、有副作用（发消息、改数据库都是真实操作）、
依赖环境（同一个 Agent 换个工具环境，表现可能完全不同）。

传统测试是这样的——输入确定，输出确定，断言确定：

    def test_add():
        assert add(1, 2) == 3

同样的思路套到 Agent 身上会失效：`assert output == "期望字符串"` 这种断言，
跑三次可能绿一次红两次，你测不出是它不稳定，还是你断言写错了。

Agent 测评集 = 用例集 + 判分规则 + 评测基座：
    用例集   ——一批带"前置条件 + 输入 + 预期"的任务
    判分规则 ——每条用例怎么判"过/没过/过了多少"
    评测基座 ——跑用例、收集日志、算分、出报告的那套代码/工具

三条铁律：环境隔离（测评环境和生产隔离，否则跑一次测评可能真发出去一堆消息）、
固定变量（测评集定稿后不动，每次只改一个变量）、样本量（少于 20 条别下结论）。
"""

import pytest

from trace import run_agent_with_calls


# 可机器判定的 check：用 pytest 断言（从日志看 tool_calls）
@pytest.mark.parametrize("case_id,prompt,expect_tool", [
    ("T01", "生成本周销售周报", "query_database"),
    ("T01", "生成本周销售周报", "send_message"),
])
def test_expected_tools(case_id, prompt, expect_tool):
    log = run_agent_with_calls(prompt)
    tools = [c["tool"] for c in log["calls"]]
    assert expect_tool in tools, f"{case_id} 没调用 {expect_tool}"


# 软判断（数字对不对、指标全不全）：用 DeepEval 让 LLM 当裁判。
# 下面这段是文章给的示例骨架——`agent_answer` 需要换成 run_agent 的真实输出，
# 原文本身也是留空演示用法，没有接完整的调用链。
#
# from deepeval import assert_test
# from deepeval.metrics import GEval
# from deepeval.test_case import LLMTestCase
#
# correctness = GEval(
#     name="周报正确性",
#     criteria="周报数字与数据库一致、四项指标齐全、无编造、无无关数据混入",
# )
#
# def test_report_correctness():
#     agent_answer = run_agent_with_calls("生成本周销售周报")["final_output"]
#     test_case = LLMTestCase(
#         input="生成本周销售周报",
#         actual_output=agent_answer,
#     )
#     assert_test(test_case, [correctness])


# 用例集配比参考（避免"完成率虚高"）：
#   正常业务场景 40%（验证核心能力）
#   边界和复杂场景 20%（验证深层业务逻辑）
#   异常及工具故障 15%（验证恢复能力）
#   安全和对抗场景 15%（验证越权、注入、误操作）
#   多轮及长上下文 10%（验证记忆和上下文）
