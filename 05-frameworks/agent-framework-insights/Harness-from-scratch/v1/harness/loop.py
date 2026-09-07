"""v1：最朴素的 Agent 循环，没有任何防护。"""


def run_agent(goal, tool_registry, llm):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]

    while True:
        response = llm.chat(messages, tools=list(tool_registry.keys()))

        if not response["tool_calls"]:
            return response["content"]

        messages.append(
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            }
        )

        for call in response["tool_calls"]:
            tool = tool_registry[call["name"]]
            try:
                result = tool.run(call["args"])
            except Exception as exc:  # noqa: BLE001 - v1 尚无分类错误处理，见 v6/v8
                result = f"Error: {exc}"
            messages.append({"role": "tool", "name": call["name"], "content": result})
