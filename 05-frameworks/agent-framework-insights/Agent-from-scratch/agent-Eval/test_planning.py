"""规划能力评测（文章四）——拆解、顺序、工具选择、目标一致性。

评估 Agent 的规划能力，本质是"看轨迹、拆五件事、对黄金路径"：把规划拆成
拆解、排序、工具选择、重规划（见 test_replanning.py）、目标一致性五个子能力，
从完整轨迹里抽步骤序列，用断言 + 参考路径 + LLM 裁判 + 故障注入四种手段分别测。

它和"任务完成度"最大的区别——前者问"活干完没"，后者问"活是怎么干完的"；
只有两个都测，才能把"碰巧完成"和"规划完成"分开。

避坑提醒（原文"避坑清单"）：
- 只看最终结果 = 没测规划；结果对 ≠ 规划对。
- 黄金路径是参考答案，不是标准答案——Agent 合并步骤、换个等价顺序，
  只要依赖关系满足、结果对，不该被误杀，用相似度阈值做软过滤。
- 轨迹只记 tool_call、漏了 thought，规划这几项就全测不了。
- 任务太简单测不出规划——至少三步以上、带依赖、有分支。
- 非确定性：同一任务多次跑，路径可能不同，别拿单次路径下结论。
"""

from difflib import SequenceMatcher

from trace import run_agent_with_trace

TASK = "帮我做一份 Q3 经营复盘（详细需求见 PRD）"

# 参考路径（"黄金路径"）：任务拆解应该长什么样，作为相似度对比的参考答案，
# 不是要求 Agent 必须一模一样地走。
GOLDEN_PLAN = [
    "query_sales", "query_marketing", "clean_data", "calc_metrics",
    "find_decline_region", "analyze_cause", "write_report", "send_report",
]


def get_tool_sequence(prompt: str) -> list[str]:
    """把轨迹抽成工具调用序列"""
    trace = run_agent_with_trace(prompt)
    return [e["tool"] for e in trace if e["type"] == "tool_call"]


def get_tool_sequence_with_args(prompt: str) -> list[tuple[str, dict]]:
    trace = run_agent_with_trace(prompt)
    return [(e["tool"], e["args"]) for e in trace if e["type"] == "tool_call"]


def plan_similarity(actual: list[str]) -> float:
    """算 Agent 实际路径和黄金路径的相似度（软过滤用，别要求 100% 一致）"""
    return SequenceMatcher(None, actual, GOLDEN_PLAN).ratio()


# ① 拆解断言：必要子任务都出现了（"不漏"）
def test_necessary_subtasks_present():
    seq = get_tool_sequence(TASK)
    required = ["query_sales", "query_marketing", "calc_metrics",
                "find_decline_region", "write_report", "send_report"]
    for tool in required:
        assert tool in seq, f"缺失必要步骤: {tool}"


# ② 依赖顺序断言：先后关系必须满足
def test_dependency_order():
    seq = get_tool_sequence(TASK)
    # 数据必须先于计算，计算必须先于找下滑区域，报告必须先于发送
    assert seq.index("query_sales") < seq.index("calc_metrics")
    assert seq.index("calc_metrics") < seq.index("find_decline_region")
    assert seq.index("write_report") < seq.index("send_report")


# ③ 工具参数断言：这一步"选对工具"之外，还要"填对参数"
def test_analyze_cause_targets_decline_region():
    calls = get_tool_sequence_with_args(TASK)
    analyze = [args for tool, args in calls if tool == "analyze_cause"]
    assert analyze, "没有调用 analyze_cause"
    # 分析对象必须是"下滑最严重区域"，而不是全公司
    assert analyze[0].get("region") != "全公司"


# 参考路径对比：断言只能查"有没有""顺序对不对"，查不了"整体像不像"。
def test_plan_close_to_golden():
    seq = get_tool_sequence(TASK)
    sim = plan_similarity(seq)
    assert sim >= 0.6, f"规划路径与黄金路径相似度过低: {sim:.2f}"


# 子任务覆盖 + 目标一致性：拆解得"全不全"、有没有"跑题"，这类软判断交给 LLM-as-Judge。
# 下面是文章给的骨架——`agent_full_trace_text` 需要把整条轨迹（thought+tool_call）
# 拼成文本喂给裁判，原文本身也是留空演示用法。
#
# from deepeval import assert_test
# from deepeval.metrics import GEval
# from deepeval.test_case import LLMTestCase
#
# coverage = GEval(
#     name="拆解完整性",
#     criteria=(
#         "判断 Agent 是否识别出任务的必要子任务：拉销售数据、拉市场活动数据、"
#         "清洗数据、计算同比环比、定位下滑最严重区域、分析原因、生成报告、发送给管理层。"
#         "漏掉的必要子任务越少，得分越高；出现与任务无关的步骤则扣分。"
#     ),
# )
#
# consistency = GEval(
#     name="目标一致性",
#     criteria="判断 Agent 的每一步是否围绕'季度经营复盘'这一原始目标，有没有跑题或越做越偏。",
# )
#
# def test_plan_covers_subtasks_and_stays_on_goal():
#     trace = run_agent_with_trace(TASK)
#     agent_full_trace_text = "\n".join(f"[{e['type']}] {e.get('content', e.get('tool'))}" for e in trace)
#     test_case = LLMTestCase(input=TASK, actual_output=agent_full_trace_text)
#     assert_test(test_case, [coverage, consistency])
