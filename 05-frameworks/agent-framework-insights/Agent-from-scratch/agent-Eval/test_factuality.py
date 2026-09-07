"""事实正确性评测（文章六）——黄金答案 + LLM 裁判。

评估 Agent 的知识可靠性与幻觉，本质是"钉黄金事实、拆五类幻觉、逐条溯源"。
事实对错，最稳妥的做法是让 LLM 裁判逐条比对"黄金事实"，这里用 DeepEval 的 GEval。

坑 1（最致命）：拿 Agent 自己的知识库当裁判——让"同一个模型"既写答案、又判答案
对不对，等于让犯人当法官。事实核验必须依赖外部、独立、可追溯的权威来源
（见 knowledge_base.GOLDEN_FACTS）。
坑 2：把"忠实性"和"事实性"混为一谈——材料错了、它照抄，忠实度高但事实错；
材料对、它改编错，忠实度低但看起来像事实错。两个指标要分开测（见 test_faithfulness.py）。
"""

from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase

from knowledge_base import GOLDEN_FACTS
from trace import run_agent


def test_factuality():
    for item in GOLDEN_FACTS:
        metric = GEval(
            name="事实正确性",
            criteria=(
                "对比 Agent 输出与给定的黄金事实集，逐条判断输出中的客观事实是否正确："
                "① 数字、客户名、占比等硬事实必须与黄金事实完全一致；"
                "② 出现与黄金事实相反的表述（如把'下滑'写成'增长'、把8300万写成1.2亿）判为事实错误；"
                "③ 输出中引用了黄金事实集之外的'新事实'，需标注为'疑似编造'。"
                "编造数字、张冠李戴、正负号反转，都要扣分。"
            ),
            threshold=0.7,
        )
        # 修正：原文这里直接写 actual_output=agent_output，但 agent_output 在这个
        # 函数里从未被赋值——补上"跑一遍 Agent 拿到它对这个任务的真实输出"这一步。
        agent_output = run_agent(item["task"])
        test_case = LLMTestCase(
            input=item["task"],
            actual_output=agent_output,
            expected_output=str(item["facts"]),
        )
        assert_test(test_case, [metric])
