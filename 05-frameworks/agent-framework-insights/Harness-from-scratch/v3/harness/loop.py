"""v3：在 v2 的执行预算基础上加入循环空转检测。"""

from harness.loop_detector import detect_loop


def run_agent(goal, tool_registry, llm, budget):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]
    call_history = []

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        loop_check = detect_loop(call_history)
        if loop_check["severity"] == "critical":
            blocked = loop_check["blocked_tool"]
            if blocked in tool_registry:
                del tool_registry[blocked]
            messages.append(
                {
                    "role": "system",
                    "content": f"[循环检测] {loop_check['reason']}。工具 {blocked} 已暂时禁用，请更换策略。",
                }
            )

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
            ok = True
            try:
                result = tool.run(call["args"])
            except Exception as exc:  # noqa: BLE001 - v1 尚无分类错误处理，见 v6/v8
                result = f"Error: {exc}"
                ok = False
            messages.append({"role": "tool", "name": call["name"], "content": result})
            call_history.append({"tool": call["name"], "args": call["args"], "ok": ok})
