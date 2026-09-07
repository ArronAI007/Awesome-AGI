"""v6：在 v5 的压缩安全阀基础上加入输出校验与自愈。"""

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.loop_detector import detect_loop
from harness.validator import validate_tool_call

MAX_CONSECUTIVE_ERRORS = 3


def run_agent(goal, tool_registry, llm, budget, compact_config, compression_config):
    messages = [
        {"role": "system", "content": "你是一个通用任务助手。"},
        {"role": "user", "content": goal},
    ]
    call_history = []
    compression_guard = CompressionGuard(compression_config["max_compressions"])
    consecutive_errors = 0

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

        compact_if_needed(messages, budget.steps_used, compact_config)

        if needs_compression(messages, compression_config):
            if compression_guard.is_exhausted():
                return "上下文空间已耗尽，结束本轮对话"
            messages = compress_history(
                messages, compression_config["keep_recent_count"]
            )
            compression_guard.record_compression()

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
            valid = validate_tool_call(call, tool_registry)
            if not valid["ok"]:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    return "连续校验失败，任务终止"
                messages.append({"role": "system", "content": f"[校验失败] {valid['error']}"})
                continue

            consecutive_errors = 0
            tool = tool_registry[call["name"]]
            ok = True
            try:
                result = tool.run(call["args"])
            except Exception as exc:  # noqa: BLE001 - 分类错误处理见 v8
                result = f"Error: {exc}"
                ok = False
            messages.append({"role": "tool", "name": call["name"], "content": result})
            call_history.append({"tool": call["name"], "args": call["args"], "ok": ok})
