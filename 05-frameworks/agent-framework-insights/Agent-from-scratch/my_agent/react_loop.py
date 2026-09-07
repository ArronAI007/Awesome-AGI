"""ReAct 循环（第 3 篇）——Agent 的心跳。

ReAct = Reasoning + Acting，中文可以叫"推理-行动循环"。
Thought → Action → Observation → 重复。每一步都是"看过结果后的新决策"，
而不是一次性的工具选择。这是不依赖 OpenAI 原生 tool_calls 的纯手写实现：
一段精心设计的 prompt 让模型按特定格式输出，再用正则表达式解析。

生产级 ReAct 需要三个保护层：
① 防止无限循环（重复检测 + 步数上限）
② 防止格式飘移（格式检测 + 强制纠正）
③ 防止幻觉（禁止模型自编 Observation）
"""

import re
import json
from openai import OpenAI

client = OpenAI()

# ============================================================
# System Prompt
# ============================================================
REACT_SYSTEM_PROMPT = """你是一个能使用工具的 AI Agent，采用 ReAct（推理-行动）模式工作。

## 可用工具
1. get_weather: 获取指定城市的天气信息
   参数: city (城市名), date (日期)
   示例: get_weather(city="上海", date="明天")

2. search_trains: 查询两个城市之间的火车票
   参数: from (出发城市), to (到达城市), date (日期)
   示例: search_trains(from="上海", to="北京", date="明天")

3. send_message: 给用户发送提醒消息
   参数: content (消息内容)
   示例: send_message(content="明天上海有雨，记得带伞")

## 输出格式
严格按以下格式输出，只能选一种：

需要调工具时：
Thought: [你的推理过程]
Action: tool_name(param1="value1", param2="value2")

任务完成时：
Thought: [总结性思考]
Final Answer: [给用户的自然语言回复]

## 规则
1. 每次只输出一个 Thought + 一个 Action
2. 不要自己编造 Observation，系统会提供
3. 同一个工具连续调用 2 次返回相同结果 → 不要继续，基于现有信息判断
4. 信息不够时如实告知用户，不要瞎编
5. 在推理前先问自己：信息够了吗？有没有漏掉什么？
"""

# ============================================================
# 工具函数
# ============================================================
def get_weather(city: str, date: str = "今天") -> dict:
    data = {
        "上海-今天": {"天气": "晴", "温度": "28°C", "降水概率": "10%"},
        "上海-明天": {"天气": "中雨", "温度": "22°C", "降水概率": "85%"},
        "北京-今天": {"天气": "多云", "温度": "25°C", "降水概率": "20%"},
        "北京-明天": {"天气": "晴", "温度": "28°C", "降水概率": "5%"},
    }
    key = f"{city}-{date}"
    if key not in data:
        return {"状态": "无数据", "原因": f"暂无 {city} {date} 的天气数据", "建议": "尝试查询其他日期或城市"}
    return data[key]

def search_trains(from_: str, to: str, date: str) -> dict:
    routes = {
        ("上海", "北京"): {
            "车次": ["G2 08:00-12:30", "G14 10:00-14:30", "G18 15:00-19:30"],
            "票价": ["二等座 553元", "一等座 933元"]
        },
    }
    result = routes.get((from_, to))
    if not result:
        return {"状态": "无结果", "原因": f"未找到 {date} 从 {from_} 到 {to} 的火车票", "建议": "尝试相邻日期或反向查询"}
    result["状态"] = "有票"
    return result

def send_message(content: str) -> dict:
    return {"状态": "已发送", "内容": content}

TOOLS = {"get_weather": get_weather, "search_trains": search_trains, "send_message": send_message}

# ============================================================
# 解析器
# ============================================================
def parse_react_output(text: str) -> dict:
    # 去掉 markdown 代码块包裹
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines)

    # 匹配 Action
    m = re.search(r"Thought:\s*(.+?)\s*\n\s*Action:\s*(.+?)\s*$", clean, re.DOTALL)
    if m:
        return {"type": "action", "thought": m.group(1).strip(), "action": m.group(2).strip()}

    # 匹配 Final Answer
    m = re.search(r"Thought:\s*(.+?)\s*\n\s*Final Answer:\s*(.+?)\s*$", clean, re.DOTALL)
    if m:
        return {"type": "final_answer", "thought": m.group(1).strip(), "answer": m.group(2).strip()}

    return {"type": "unknown", "raw": text}

def parse_action(s: str) -> tuple:
    m = re.match(r"(\w+)\((.*)\)", s.strip())
    if not m:
        return None, {}
    fn, astr = m.group(1), m.group(2)
    args = {}
    for am in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', astr):
        args[am.group(1)] = am.group(2)
    return fn, args

# ============================================================
# 主循环
# ============================================================
def run_react_agent(user_message: str, verbose: bool = True, max_steps: int = 15) -> str:
    messages = [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    last_tool_calls = []

    for step in range(1, max_steps + 1):
        resp = client.chat.completions.create(model="gpt-4o", messages=messages)
        reply = resp.choices[0].message.content.strip()

        if verbose:
            print(f"\n{'─'*50}\n🔄 第 {step} 轮\n{'─'*50}\n{reply}")

        parsed = parse_react_output(reply)

        if parsed["type"] == "final_answer":
            if verbose:
                print(f"\n✅ 任务完成!")
            return parsed["answer"]

        if parsed["type"] == "action":
            fn, args = parse_action(parsed["action"])
            call_key = f"{fn}({args})"
            last_tool_calls.append(call_key)

            # 检测重复调用
            if len(last_tool_calls) >= 3 and len(set(last_tool_calls[-3:])) == 1:
                obs = "⚠️ 你连续调用了同一个工具 3 次。请基于现有信息做出最终判断，不要继续循环。"
            elif fn in TOOLS:
                try:
                    obs = json.dumps(TOOLS[fn](**args), ensure_ascii=False)
                except Exception as e:
                    obs = json.dumps({"状态": "错误", "原因": str(e)}, ensure_ascii=False)
            else:
                obs = json.dumps({"状态": "错误", "原因": f"工具 '{fn}' 不存在", "可用工具": list(TOOLS.keys())}, ensure_ascii=False)

            if verbose:
                print(f"⏎ Observation: {obs}")

            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": f"Observation: {obs}\n\n(继续使用 Thought + Action 或 Thought + Final Answer 格式)"})
            continue

        # 格式不对 → 提醒
        if verbose:
            print("⚠️ 格式异常，提醒模型修正")
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": "你的输出格式不符合要求。请严格按照 Thought + Action 格式（需要调工具时）或 Thought + Final Answer 格式（任务完成时）输出。"})

    return "⚠️ Agent 达到最大循环次数，任务未完成。"

# ============================================================
# 跑起来
# ============================================================
if __name__ == "__main__":
    result = run_react_agent(
        "帮我看看明天上海和北京的天气。如果哪个城市下雨，"
        "就帮我查一下两个城市之间明天的火车票，然后告诉我该怎么安排。"
    )
    print(f"\n{'='*50}\n🎯\n{result}")
