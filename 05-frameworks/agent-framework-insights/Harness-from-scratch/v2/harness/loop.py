"""v2：在 v1 的裸循环基础上加入执行预算。"""


def run_agent(goal, tool_registry, llm, budget):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

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
