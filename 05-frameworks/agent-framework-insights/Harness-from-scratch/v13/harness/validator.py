"""v6：工具调用输出校验——存在性 + 必填参数，供 run_agent 在执行前调用。"""


def validate_tool_call(call, tool_registry):
    tool_name = call["name"]
    if tool_name not in tool_registry:
        available = ", ".join(tool_registry.keys())
        return {"ok": False, "error": f"未知工具: {tool_name}。可用工具: {available}"}

    tool = tool_registry[tool_name]
    args = call.get("args", {})
    for param_name, spec in tool.params.items():
        if spec.get("required", True) and param_name not in args:
            return {"ok": False, "error": f"工具 {tool_name} 缺少必填参数: {param_name}"}

    return {"ok": True, "error": ""}
