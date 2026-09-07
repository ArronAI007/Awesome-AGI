"""引用可溯源性评测（文章六）——三态判定。

引用溯源的逻辑：抽引用 → 去来源里找 → 判定 supported / contradicted / not_covered。
这里给一个简化的自写版本（生产环境可以直接用 RAGAS 的 faithfulness 或专门的
citation 评测）。
"""

import re

from knowledge_base import GOLDEN_FACTS, SOURCE_DOCS
from trace import run_agent


def extract_citations(output: str) -> list[str]:
    """粗暴抽取《》里的引用名（生产环境用 NER 或正则做得更细）"""
    return re.findall(r"《([^》]+)》", output)


def judge_citation(cite: str, output_claim: str) -> str:
    """三态判定：supported / contradicted / not_covered"""
    doc = SOURCE_DOCS.get(cite)
    if doc is None:
        return "not_covered"          # 来源不存在 → 编造引用
    if any(k in output_claim for k in doc):
        return "supported"
    return "contradicted"              # 来源存在但结论对不上


def test_citations_are_traceable():
    # 修正：原文这里直接写 output = agent_output，但 agent_output 从未被赋值——
    # 补上"跑一遍 Agent 拿到它对这个任务的真实输出"这一步。
    task = GOLDEN_FACTS[0]["task"]
    output = run_agent(task)
    cites = extract_citations(output)
    assert cites, "输出里没检测到引用（如果它声称引用了来源，就该抽得到）"
    bad = []
    for c in cites:
        state = judge_citation(c, output)
        if state != "supported":
            bad.append((c, state))
    assert not bad, f"引用不可溯源或对不上: {bad}"
