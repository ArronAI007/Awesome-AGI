"""Function Calling 拆解（第 2 篇）——大模型是怎么"伸手"的？

Function Calling ≠ 模型执行了函数。模型只输出"调用指令"，你的代码负责执行。
模型是大脑，你的代码是手。

这里手写一版不依赖 OpenAI 原生 tool_calls 的 Agent：把工具描述拼到 prompt
里 → 让模型输出 JSON → 解析 JSON → 执行函数 → 把结果拼回去。如果哪天用了
一个不支持原生 Function Calling 的模型，这套手写方案就是兜底手段。
"""

import json
from openai import OpenAI

client = OpenAI()

# 把工具描述转成 prompt 里的文字
TOOL_PROMPT = """
你可以调用以下函数来完成用户的请求。当你需要调用函数时，请严格按照以下 JSON 格式输出，
不要输出任何其他内容：

{"function": "函数名", "arguments": {"参数名": "参数值"}}

可用的函数：

1. get_weather - 获取指定城市在指定日期的天气信息，返回天气状况、温度和降水概率
   参数:
     - city (string, 必填): 城市名，如 上海、北京
     - date (string, 可选): 日期，如 今天、明天、2025-01-15

2. send_message - 给用户发送一条提醒或通知消息
   参数:
     - content (string, 必填): 要发送的消息内容

如果不需要调用任何函数，直接回复用户即可。
"""

# 工具执行器（和上一篇一样）
def get_weather(city: str, date: str = "今天") -> dict:
    weather_data = {
        "上海-今天": {"天气": "晴", "温度": "28°C", "降水概率": "10%"},
        "上海-明天": {"天气": "中雨", "温度": "22°C", "降水概率": "85%"},
        "北京-今天": {"天气": "多云", "温度": "25°C", "降水概率": "20%"},
        "北京-明天": {"天气": "阴", "温度": "20°C", "降水概率": "40%"},
    }
    return weather_data.get(f"{city}-{date}", {"天气": "未知", "温度": "未知"})

def send_message(content: str) -> bool:
    print(f"📩 已发送消息: {content}")
    return True

available_functions = {
    "get_weather": get_weather,
    "send_message": send_message,
}

def run_agent_manual(user_message: str):
    """手写版 Agent——不依赖 OpenAI 原生 tool_calls"""
    # system prompt 里放工具说明
    messages = [
        {"role": "system", "content": TOOL_PROMPT},
        {"role": "user", "content": user_message},
    ]

    for step in range(10):
        # 注意：这里不传 tools 参数，工具描述已经在 system prompt 里了
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )

        reply = response.choices[0].message.content.strip()
        print(f"\n📝 第 {step+1} 轮，模型输出: {reply[:200]}...")

        # 尝试解析 JSON——看模型是不是想调工具
        try:
            # 处理可能被 markdown 代码块包裹的情况
            if "```" in reply:
                reply = reply.split("```")[1]
                if reply.startswith("json"):
                    reply = reply[4:]
                reply = reply.strip()

            command = json.loads(reply)
            func_name = command.get("function", "")
            func_args = command.get("arguments", {})

            if func_name in available_functions:
                print(f"🔧 执行: {func_name}({func_args})")
                result = available_functions[func_name](**func_args)

                # 把"我调了什么 + 结果是什么"追加到对话
                messages.append({"role": "assistant", "content": reply})
                messages.append({
                    "role": "user",
                    "content": f"函数 {func_name} 的执行结果: {json.dumps(result, ensure_ascii=False)}"
                })
                continue  # 继续循环，让模型看结果后决定下一步

        except (json.JSONDecodeError, KeyError, IndexError):
            pass

        # 解析失败或没有 tool call → 模型在正常回复 → 任务结束
        print(f"🤖 Agent 最终回复: {reply}")
        return

    print("⚠️ Agent 循环达到上限")


if __name__ == "__main__":
    # 跑一下
    run_agent_manual("明天上海下雨吗？需要带伞提醒我一下")
