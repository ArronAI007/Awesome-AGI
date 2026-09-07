"""Agent 测评八维度框架（文章一：《Agent测评框架——怎么判断一个AI Agent好不好用？》）。

模型榜单只测「脑子好不好使」，测不出「手脚听不听话」。
Agent 的能力 = 脑子（推理）+ 手脚（工具调用）+ 经验（记忆和纠错），
所以需要一套独立于模型榜单的测评维度。

本文件把文章里的八个维度整理成可以直接引用的结构化数据，而不是要你重新读一遍原文。
本仓库（agent评测/）目前只对其中四个维度搭了可运行的测评基座（见各 test_*.py）：
    task_completion（任务完成率）、reasoning_planning（推理与规划能力）、
    tool_use（工具使用能力）、以及知识可靠性/幻觉（文章里没有单独列为第九维度，
    但和 reasoning_planning、error_recovery 密切相关，见 test_factuality.py 等）。
其余维度（error_recovery / efficiency / reliability_consistency / safety / cost）
文章只给了评分建议，没有给代码，先留作框架，后续文章再补。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalDimension:
    """一个可以单独打分（1-5 分）的测评维度。"""

    id: str
    name: str
    core_question: str
    sub_dimensions: tuple[str, ...] = ()
    scoring_note: str = ""


DIMENSIONS: tuple[EvalDimension, ...] = (
    EvalDimension(
        id="task_completion",
        name="任务完成率 Task Completion",
        core_question="活干完了吗？",
        sub_dimensions=("完全正确", "部分正确", "完全跑偏"),
        scoring_note="同一批任务（至少 20 个），统计完全正确率；一个好用的 Agent，"
                      "完全正确率至少要在 70% 以上。",
    ),
    EvalDimension(
        id="tool_use",
        name="工具使用能力 Tool Use",
        core_question="该用什么工具？用对了吗？",
        sub_dimensions=("工具选择准确率", "参数填写准确率", "工具调用效率"),
        scoring_note="分开统计三个子维度的错误率。工具选择错误比参数填错更致命"
                      "（选了错误的工具意味着整个方向跑偏）。",
    ),
    EvalDimension(
        id="reasoning_planning",
        name="推理与规划能力 Reasoning & Planning",
        core_question="面对复杂任务，会不会拆解？",
        sub_dimensions=("任务分解", "步骤顺序", "依赖处理"),
        scoring_note="设计一些需要 3 步以上推理的任务，人工看它的执行日志。"
                      "重点不是「它有没有按你设想的方式做」，而是「它的方式是否合理且有效」。",
    ),
    EvalDimension(
        id="error_recovery",
        name="容错与纠错能力 Error Recovery",
        core_question="翻车了能不能自己兜回来？",
        sub_dimensions=("错误检测", "重试策略", "降级方案"),
        scoring_note="刻意制造一些错误场景来测——断网、传错参数、给不存在的文件路径。"
                      "好 Agent 和差 Agent 在这些极端情况下的差距非常明显。",
    ),
    EvalDimension(
        id="efficiency",
        name="效率 Efficiency",
        core_question="干完活花了多少资源？",
        sub_dimensions=("步骤数", "Token 消耗", "响应延迟（端到端耗时）"),
        scoring_note="效率低本身不是大问题——但如果效率低 + 结果还不好，就是双重减分。"
                      "适合作为「辅助维度」而非核心维度。",
    ),
    EvalDimension(
        id="reliability_consistency",
        name="稳定性与一致性 Reliability & Consistency",
        core_question="同一个任务跑 10 次，结果差别大吗？",
        sub_dimensions=("重复性", "边界的可预期性"),
        scoring_note="对关键任务至少跑 5-10 次，看结果的一致性分布。"
                      "生产环境的 Agent，稳定性评分权重应该比较高。",
    ),
    EvalDimension(
        id="safety",
        name="安全性 Safety",
        core_question="Agent 会不会干坏事？会不会被利用？",
        sub_dimensions=("权限边界", "注入防护（prompt injection）", "输出安全"),
        scoring_note="安全维度不适合打分，适合做「红线清单」——这个 Agent 能不能上线，"
                      "安全红线过了再看别的。",
    ),
    EvalDimension(
        id="cost",
        name="成本 Cost",
        core_question="用这个 Agent 干这件事，划不划算？",
        sub_dimensions=("单次任务成本", "隐性成本（开发/维护/翻车成本）"),
        scoring_note="成本要跟其他维度一起看：金融场景选完成率高的，"
                      "批量处理场景可能选单价便宜的。",
    ),
)


# 不同场景（Agent 扮演的角色），核心维度不一样，权重也不一样。
# 值是维度 id 的元组，对应 DIMENSIONS 里的 id 字段。
ROLE_WEIGHTS: dict[str, dict[str, tuple[str, ...]]] = {
    "客服 Agent": {
        "核心": ("task_completion", "reliability_consistency", "safety"),
        "次要": ("reasoning_planning", "efficiency"),
    },
    "数据分析 Agent": {
        "核心": ("reasoning_planning", "tool_use"),
        "次要": ("cost",),
    },
    "自动化运维 Agent": {
        "核心": ("error_recovery", "safety"),
        "次要": ("efficiency",),
    },
    "个人助理 Agent": {
        "核心": ("tool_use", "reasoning_planning"),
        "次要": ("cost",),
    },
    "内容创作 Agent": {
        "核心": ("task_completion", "reasoning_planning"),
        "次要": ("tool_use",),
    },
    "代码 Agent（Cursor/Devin）": {
        "核心": ("task_completion", "tool_use", "reasoning_planning"),
        "次要": ("efficiency",),
    },
}


def get_dimension(dim_id: str) -> EvalDimension:
    """按 id 查一个维度，查不到就抛错——别静默返回 None。"""
    for d in DIMENSIONS:
        if d.id == dim_id:
            return d
    raise KeyError(f"未知维度: {dim_id}")


if __name__ == "__main__":
    for dim in DIMENSIONS:
        print(f"【{dim.name}】{dim.core_question}")
        if dim.sub_dimensions:
            print(f"  子维度: {', '.join(dim.sub_dimensions)}")
        print(f"  评分建议: {dim.scoring_note}\n")
