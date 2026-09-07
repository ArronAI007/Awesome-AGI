"""评测基座：给 Agent 包一层，把执行过程记下来。

文章三、四、五、六用的是同一套逐步长大的 harness——每一篇在上一篇的基础上，
多留一种视角的轨迹。本文件把四篇文章里散落的三个函数合到一起：

    run_agent(prompt) -> str
        最简版：只要最终回复文本。文章三、六都是拿它做「黑盒」断言用的
        （比如知识边界测试只关心最终说了什么，不关心中间怎么做的）。

    run_agent_with_trace(prompt) -> list[dict]
        文章四引入：记录每一步的 thought / tool_call / observation，
        用来测「规划」——拆解全不全、顺序对不对、依赖有没有搞反、
        出故障了会不会重规划。只记 tool_call、漏了 thought，规划这几项就全测不了。

    run_agent_with_calls(prompt) -> dict
        文章五引入：只关心 tool_calls 这条轨迹（工具名、参数、返回值）+ 最终输出，
        用来测「工具调用」——选没选对工具、参数填没填对、有没有碰陷阱/危险工具。

三个函数都还是「对接你的 Agent 循环」的骨架代码——原文写的就是伪代码，
真正跑起来需要你把下面标了「TODO」的地方换成自己 Agent 的执行循环。
如果你要接的是这个仓库里 my_agent/ 项目的 ProductionAgent，可以参考
本文件末尾 `# === 接入 my_agent.ProductionAgent 的例子 ===` 那段注释。
"""

from typing import Any


def run_agent(prompt: str) -> str:
    """跑一次 Agent，只要最终回复文本。"""
    # TODO: 对接你的 Agent 入口，返回最终回复的字符串。
    # 例如: return your_agent.chat(prompt)
    raise NotImplementedError("请把 run_agent 接到你自己的 Agent 入口")


def run_agent_with_trace(prompt: str) -> list[dict]:
    """跑一次 Agent，记录每一步：thought / tool_call / observation。

    返回的每个元素形如：
        {"type": "thought", "content": "..."}
        {"type": "tool_call", "tool": "...", "args": {...}}
        {"type": "observation", "content": "..."}
    """
    trace: list[dict] = []
    # TODO: 这里对接你的 Agent 循环：每轮把它的思考、工具调用、返回结果 append 进 trace。
    # 伪代码：
    # for step in agent.run(prompt):
    #     trace.append({"type": "thought", "content": step.thought})
    #     for call in step.tool_calls:
    #         trace.append({"type": "tool_call", "tool": call.name, "args": call.args})
    #         trace.append({"type": "observation", "content": call.result})
    return trace


def run_agent_with_calls(prompt: str) -> dict[str, Any]:
    """跑一次 Agent，只关心 tool_calls 轨迹 + 最终输出。

    返回: {"calls": [{"tool": ..., "args": {...}, "result": ...}, ...], "final_output": "..."}
    """
    result: dict[str, Any] = {"calls": [], "final_output": ""}
    # TODO: 对接你的 Agent 循环，把每轮 tool_call 落下来。
    # 伪代码：
    # for step in agent.run(prompt):
    #     for call in step.tool_calls:
    #         result["calls"].append({
    #             "tool": call.name,
    #             "args": call.arguments,      # dict
    #             "result": call.result,
    #         })
    # result["final_output"] = agent.final_answer
    return result


# === 接入 my_agent.ProductionAgent 的例子（不是原文内容，供参考） ===
#
# from my_agent.main import build_agent
#
# _agent = build_agent()
#
# def run_agent(prompt: str) -> str:
#     return _agent.chat(prompt)
#
# ProductionAgent.chat() 目前只返回最终文本，没有对外暴露逐步的 thought/tool_call
# 轨迹，所以 run_agent_with_trace / run_agent_with_calls 想接真实数据，
# 需要先在 error_handling.BoundedReActLoop.run() 里把每一步过程记下来再传出来
# ——这是 my_agent/ 项目本身的改动，不属于这次移植范围。
