"""内在一致性评测（文章六）——多次采样 + 自对比。

一致性靠"多问几遍"来测——LLM 有随机性，同一个任务问 3 遍，如果答案稳定，说明它
内部自洽；如果每次数字都变，就是幻觉的信号。

坑 6：非确定性——同一问题每次答案不一样。所以一致性要"多次采样"来测，而不是
跑一次就下结论；事实核验也要容忍"措辞不同但事实一致"（用语义判断，而不是
字符串完全相等）。
"""

import re

import pytest

from trace import run_agent


def test_numeric_consistency_across_runs():
    """同一个数据任务跑 3 遍，关键数字应该一致"""
    prompt = "查询 Q2 总营收，并汇报"
    results = [run_agent(prompt) for _ in range(3)]
    # 抽数字（简化：找"营收"附近的所有数字）
    nums = [set(re.findall(r"\d+\.?\d*", r)) for r in results]
    # 3 遍结果里出现的数字应该高度重合（阈值：至少 2/3 一致）
    common = nums[0] & nums[1] & nums[2]
    assert common, f"3 次运行给出的数字不一致，存在幻觉风险: {nums}"


def test_no_self_contradiction_in_one_output():
    """同一份输出里，不能同时出现相反结论"""
    # 修正：原文这里直接写 output = agent_output（未赋值），且没给这条用例配任务
    # prompt——只给了断言逻辑。这里配一个会触发"投放建议"类结论的任务，
    # 具体换成你自己场景里容易出现自相矛盾结论的任务即可。
    prompt = "根据本月广告投放数据，给出下阶段投放建议"
    output = run_agent(prompt)
    if "收缩投放" in output and "加大投放" in output:
        pytest.fail("同一份输出里同时出现'收缩投放'和'加大投放'，结论自相矛盾")
