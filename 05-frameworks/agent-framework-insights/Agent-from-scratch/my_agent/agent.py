"""Agent 主逻辑（第 1 篇）——Agent = 大模型 + 工具 + 循环。

大模型负责想，工具负责做，循环让它们反复配合直到任务完成。
这是 Agent 的最小内核：把用户消息 + 工具说明书发给大模型 → 大模型返回
"我要调哪个工具 + 参数是什么" → 我们执行工具 → 把结果告知大模型 →
大模型决定"任务完成了"还是"还需要再调一个工具"。
"""

import json
from openai import OpenAI

# 工具1：查天气
def get_weather(city: str, date: str = "今天") -> dict:
    """获取指定城市在指定日期的天气信息"""
    # 实际项目里调天气 API，这里用写死的假数据演示
    weather_data = {
        "上海-今天": {"天气": "晴", "温度": "28°C", "降水概率": "10%"},
        "上海-明天": {"天气": "中雨", "温度": "22°C", "降水概率": "85%"},
        "北京-今天": {"天气": "多云", "温度": "25°C", "降水概率": "20%"},
        "北京-明天": {"天气": "阴", "温度": "20°C", "降水概率": "40%"},
    }
    return weather_data.get(f"{city}-{date}", {"天气": "未知", "温度": "未知"})

# 工具2：发消息
def send_message(content: str) -> bool:
    """给用户发送一条提醒消息"""
    print(f"📩 已发送消息: {content}")
    return True

# 工具的"说明书"——大模型靠它理解你能干什么
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市在指定日期的天气信息，返回天气状况、温度和降水概率",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名，如 上海、北京"
                    },
                    "date": {
                        "type": "string",
                        "description": "日期，如 今天、明天、2025-01-15"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "给用户发送一条提醒或通知消息",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "要发送的消息内容"
                    }
                },
                "required": ["content"]
            }
        }
    }
]

# 把工具名和实际函数关联起来
available_functions = {
    "get_weather": get_weather,
    "send_message": send_message,
}

client = OpenAI()  # 或用你自己的 base_url 指向 DeepSeek / Qwen 等

def run_agent(user_message: str):
    # messages 数组是 Agent 的"短期记忆"，记录所有对话和工具调用历史
    messages = [{"role": "user", "content": user_message}]

    # 核心循环：跑 10 次是安全上限，防止某些边界情况无限循环
    for _ in range(10):
        # 把当前对话历史 + 工具说明书一起发给大模型
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools,
        )

        msg = response.choices[0].message

        # 如果模型没说要调工具 → 任务结束了 → 输出最终结果
        if not msg.tool_calls:
            print(f"🤖 Agent: {msg.content}")
            return

        # 模型说要调工具 → 我们执行
        for tool_call in msg.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments)

            print(f"🔧 执行: {func_name}({func_args})")

            # 真正调用函数
            result = available_functions[func_name](**func_args)

            # 🔑 关键一步：把"我调了什么工具 + 返回了什么结果"追加到 messages
            # 这样大模型做下一步决策时，知道刚才发生了什么
            messages.append(msg)  # 模型的 tool_call 响应
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False)
            })

    print("⚠️ Agent 循环次数达到上限，任务可能未完成")


if __name__ == "__main__":
    run_agent("明天上海下雨吗？如果需要带伞提醒我一下")
