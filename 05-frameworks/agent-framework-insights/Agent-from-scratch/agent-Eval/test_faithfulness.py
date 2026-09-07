"""上下文忠实性评测（文章六）——claim 抽取 + 上下文比对。

忠实性的标准做法是：把 Agent 输出拆成一条条 claim，逐条判断"给定上下文支不支持"。
这里用 DeepEval 的 FaithfulnessMetric（内置了 claim 抽取）。

⚠️ 忠实性 ≠ 事实性：一个回答可能完全忠实于材料（材料本身错了，它照抄），
也可能材料是对的、它改编错了。所以本文件和 test_factuality.py 要分开测、分开报，
不能用一个指标替代另一个。
"""

from deepeval import assert_test
from deepeval.metrics import FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from knowledge_base import GOLDEN_FACTS
from trace import run_agent


def test_faithfulness():
    for item in GOLDEN_FACTS:
        context_text = "\n".join(item["context"].values())
        metric = FaithfulnessMetric(threshold=0.7)
        # 修正：原文这里直接写 actual_output=agent_output，但 agent_output 在这个
        # 函数里从未被赋值——补上"跑一遍 Agent 拿到它对这个任务的真实输出"这一步。
        agent_output = run_agent(item["task"])
        test_case = LLMTestCase(
            input=item["task"],
            actual_output=agent_output,
            retrieval_context=[context_text],   # 工具返回的上下文
        )
        assert_test(test_case, [metric])
