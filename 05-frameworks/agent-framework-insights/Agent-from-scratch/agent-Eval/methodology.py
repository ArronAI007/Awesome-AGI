"""评测方法论——效度、信度、区分度（文章二：《怎样科学地评一个 Agent：效度、信度与区分度》）。

大多数"评测"根本不合格——本质上只是"试玩"：随便丢几个问题，看答得顺不顺眼，
没有控制变量、没有统一题目、没有打分标准。

真正合格的评测要满足测量学（psychometrics）的三个硬标准：效度、信度、区分度。
三者会互相牵制：信度高但效度低（稳定地测错，比不稳定地测错更可怕）；
效度高但信度低（测得对但结果忽上忽下，不敢下结论）；区分度不足（测不出差距，
没法做选择）。一个好的评测，是三者同时达标。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MethodologyCheck:
    """一个评测方法论标准：是什么、自查怎么问、常见翻车、怎么改进。"""

    name: str
    core_question: str
    self_check_question: str
    common_failure: str
    how_to_improve: tuple[str, ...]


VALIDITY = MethodologyCheck(
    name="效度 Validity",
    core_question="测到的，是不是想测的？",
    self_check_question="这些测试题，真的代表我们要测的那个能力吗？",
    common_failure=(
        "用 MMLU 分数判断模型「聪不聪明」——MMLU 考的是多选题式的知识储备，"
        "和「聪明」（推理、应变、创造力）之间隔着一整条河。"
    ),
    how_to_improve=(
        "表面效度：题目看起来像不像在测那个能力",
        "内容效度：题目有没有覆盖这个能力的各个侧面",
        "构念效度：要测的能力本身定义清不清楚、测得准不准",
    ),
)

RELIABILITY = MethodologyCheck(
    name="信度 Reliability",
    core_question="同一个测试，重复测，结果稳定吗？",
    self_check_question="换个时间、换个顺序再测一遍，结论会变吗？",
    common_failure=(
        "测一次就下结论——第一次「查本周销售额」成功了就发朋友圈说这 Agent 太强了，"
        "第二天同样的问题，它把周报数据错当成了销售额。"
    ),
    how_to_improve=(
        "多次重复取平均：别只测一次，至少跑 5-10 次，看成功率和分布",
        "固定关键变量：temperature 设成 0（或固定值）、prompt 一字不改、工具环境一致",
        "用同一套标准打分流：别这次凭感觉打 4 分，下次凭心情打 2 分",
    ),
)

DISCRIMINATION = MethodologyCheck(
    name="区分度 Discrimination",
    core_question="这个测试，能把好的和差的区分开吗？",
    self_check_question="这个测试，能把好的和差的分开吗？",
    common_failure=(
        "天花板效应：题太简单，所有模型都得 95 分以上，分不出谁强谁弱；"
        "反过来是地板效应：题太难，全军覆没，同样分不出高下。"
    ),
    how_to_improve=(
        "难度要分层：简单题测基本功、中等题测真本事、难题测上限",
        "避免「送分题」堆砌：全是简单题只能测出「谁最差」",
        "关注分差而非绝对分数：92 分和 91 分大概率是噪音，92 和 70 才有意义",
    ),
)

CHECKLIST: tuple[MethodologyCheck, ...] = (VALIDITY, RELIABILITY, DISCRIMINATION)


def self_check() -> str:
    """落到实操：评一个 Agent 之前，先问自己三个问题。

    三个问题都答"是"，这个评测才站得住脚。
    """
    lines = ["评一个 Agent（或者看别人评 Agent）之前，先问三个问题："]
    for i, c in enumerate(CHECKLIST, 1):
        lines.append(f"{i}. {c.name}自查：{c.self_check_question}")
    lines.append("三个问题都答“是”，这个评测才站得住脚；任何一个拉胯，整个评测就废了。")
    return "\n".join(lines)


if __name__ == "__main__":
    for check in CHECKLIST:
        print(f"【{check.name}】{check.core_question}")
        print(f"  常见翻车: {check.common_failure}")
        for tip in check.how_to_improve:
            print(f"  - {tip}")
        print()
    print(self_check())
