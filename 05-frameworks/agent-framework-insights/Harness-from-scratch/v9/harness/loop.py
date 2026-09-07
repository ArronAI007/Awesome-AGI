"""v9：在 v8 的重试退避基础上加入会话持久化与断点续跑。"""

import time

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.errors import classify_error
from harness.loop_detector import detect_loop
from harness.retry import ToolCircuitBreaker, compute_backoff_delay
from harness.session_store import append_message, load_session
from harness.validator import validate_tool_call

MAX_CONSECUTIVE_ERRORS = 3
MAX_RETRIES = 3
CIRCUIT_BREAKER_THRESHOLD = 3


def _add_message(messages, message, session_path):
    messages.append(message)
    if session_path is not None:
        append_message(session_path, message)


def run_agent(
    goal,
    tool_registry,
    llm,
    budget,
    compact_config,
    compression_config,
    sleep_fn=time.sleep,
    session_path=None,
):
    existing = load_session(session_path) if session_path is not None else []
    if existing:
        messages = existing
    else:
        messages = []
        _add_message(
            messages, {"role": "system", "content": "你是一个通用任务助手。"}, session_path
        )
        _add_message(messages, {"role": "user", "content": goal}, session_path)

    call_history = []
    compression_guard = CompressionGuard(compression_config["max_compressions"])
    consecutive_errors = 0
    circuit_breaker = ToolCircuitBreaker(CIRCUIT_BREAKER_THRESHOLD)

    while True:
        budget.consume_step()
        if budget.is_exceeded():
            return f"⚠️ 步骤上限已达（{budget.max_steps} 步），强制终止"

        loop_check = detect_loop(call_history)
        if loop_check["severity"] == "critical":
            blocked = loop_check["blocked_tool"]
            if blocked in tool_registry:
                del tool_registry[blocked]
            _add_message(
                messages,
                {
                    "role": "system",
                    "content": f"[循环检测] {loop_check['reason']}。工具 {blocked} 已暂时禁用，请更换策略。",
                },
                session_path,
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

        _add_message(
            messages,
            {
                "role": "assistant",
                "content": response["content"],
                "tool_calls": response["tool_calls"],
            },
            session_path,
        )

        for call in response["tool_calls"]:
            valid = validate_tool_call(call, tool_registry)
            if not valid["ok"]:
                consecutive_errors += 1
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    return "连续校验失败，任务终止"
                _add_message(
                    messages,
                    {"role": "system", "content": f"[校验失败] {valid['error']}"},
                    session_path,
                )
                continue

            if circuit_breaker.is_tripped(call["name"]):
                _add_message(
                    messages,
                    {
                        "role": "system",
                        "content": f"[熔断] 工具 {call['name']} 连续失败次数过多，已临时禁用",
                    },
                    session_path,
                )
                continue

            consecutive_errors = 0
            tool = tool_registry[call["name"]]
            ok = True
            attempt = 0
            while True:
                try:
                    result = tool.run(call["args"])
                    circuit_breaker.record_success(call["name"])
                    break
                except Exception as exc:  # noqa: BLE001 - 分类结果决定是否重试
                    if classify_error(exc) == "retryable" and attempt < MAX_RETRIES:
                        sleep_fn(compute_backoff_delay(attempt))
                        attempt += 1
                        continue
                    result = f"Error: {exc}"
                    ok = False
                    circuit_breaker.record_failure(call["name"])
                    break
            _add_message(
                messages,
                {"role": "tool", "name": call["name"], "content": result},
                session_path,
            )
            call_history.append({"tool": call["name"], "args": call["args"], "ok": ok})
