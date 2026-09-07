"""v12：在 v11 的权限沙箱基础上加入可观测性——记录结构化事件，供事后统计。"""

import asyncio

from harness.context_manager import (
    CompressionGuard,
    compact_if_needed,
    compress_history,
    needs_compression,
)
from harness.errors import classify_error
from harness.loop_detector import detect_loop
from harness.observability import estimate_tokens
from harness.permissions import check_permission
from harness.retry import ToolCircuitBreaker, compute_backoff_delay
from harness.session_store import append_message, load_session
from harness.validator import validate_tool_call

MAX_CONSECUTIVE_ERRORS = 3
MAX_RETRIES = 3
CIRCUIT_BREAKER_THRESHOLD = 3
DEFAULT_TOOL_TIMEOUT = 5.0


def _add_message(messages, message, session_path):
    messages.append(message)
    if session_path is not None:
        append_message(session_path, message)


def _log(event_log, event_type, **fields):
    if event_log is not None:
        event_log.record(event_type, **fields)


def default_approve_fn(call):
    reply = input(f"是否批准执行 {call['name']}（参数：{call['args']}）？[y/N] ")
    return reply.strip().lower() == "y"


async def _execute_call(call, tool_registry, circuit_breaker, sleep_fn, timeout_seconds, event_log):
    tool = tool_registry[call["name"]]
    attempt = 0
    while True:
        try:
            result = await asyncio.wait_for(
                tool.run(call["args"]), timeout=timeout_seconds
            )
            circuit_breaker.record_success(call["name"])
            _log(event_log, "tool_call", tool_name=call["name"], ok=True)
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": True,
                "content": result,
            }
        except asyncio.TimeoutError:
            circuit_breaker.record_failure(call["name"])
            _log(event_log, "tool_call", tool_name=call["name"], ok=False, reason="timeout")
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": False,
                "content": f"Error: 工具 {call['name']} 执行超过 {timeout_seconds} 秒，已取消",
            }
        except Exception as exc:  # noqa: BLE001 - 分类结果决定是否重试
            if classify_error(exc) == "retryable" and attempt < MAX_RETRIES:
                await sleep_fn(compute_backoff_delay(attempt))
                attempt += 1
                continue
            circuit_breaker.record_failure(call["name"])
            _log(event_log, "tool_call", tool_name=call["name"], ok=False, reason=str(exc))
            return {
                "tool": call["name"],
                "args": call["args"],
                "ok": False,
                "content": f"Error: {exc}",
            }


async def run_agent(
    goal,
    tool_registry,
    llm,
    budget,
    compact_config,
    compression_config,
    sleep_fn=asyncio.sleep,
    session_path=None,
    timeout_seconds=DEFAULT_TOOL_TIMEOUT,
    permission_policy=None,
    approve_fn=None,
    event_log=None,
):
    permission_policy = permission_policy or {}
    approve_fn = approve_fn or default_approve_fn

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
            _log(event_log, "guardrail", name="loop_detector", tool_name=blocked)
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
            _log(event_log, "guardrail", name="compression")

        tokens_in = estimate_tokens(str(messages))
        response = await llm.chat(messages, tools=list(tool_registry.keys()))
        tokens_out = estimate_tokens(response.get("content") or "")
        _log(event_log, "llm_call", tokens_in=tokens_in, tokens_out=tokens_out)

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

        to_execute = []
        for call in response["tool_calls"]:
            valid = validate_tool_call(call, tool_registry)
            if not valid["ok"]:
                consecutive_errors += 1
                _log(event_log, "guardrail", name="validation", tool_name=call["name"])
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    return "连续校验失败，任务终止"
                _add_message(
                    messages,
                    {"role": "system", "content": f"[校验失败] {valid['error']}"},
                    session_path,
                )
                continue

            consecutive_errors = 0

            decision = check_permission(call, permission_policy)
            if decision == "deny":
                _log(event_log, "guardrail", name="permission_deny", tool_name=call["name"])
                _add_message(
                    messages,
                    {
                        "role": "system",
                        "content": f"[权限拒绝] 工具 {call['name']} 被策略禁止执行",
                    },
                    session_path,
                )
                continue
            if decision == "ask" and not approve_fn(call):
                _log(event_log, "guardrail", name="permission_ask_rejected", tool_name=call["name"])
                _add_message(
                    messages,
                    {
                        "role": "system",
                        "content": f"[权限待批准-已拒绝] 工具 {call['name']} 未获批准",
                    },
                    session_path,
                )
                continue

            if circuit_breaker.is_tripped(call["name"]):
                _log(event_log, "guardrail", name="circuit_breaker", tool_name=call["name"])
                _add_message(
                    messages,
                    {
                        "role": "system",
                        "content": f"[熔断] 工具 {call['name']} 连续失败次数过多，已临时禁用",
                    },
                    session_path,
                )
                continue

            to_execute.append(call)

        if not to_execute:
            continue

        results = await asyncio.gather(
            *[
                _execute_call(call, tool_registry, circuit_breaker, sleep_fn, timeout_seconds, event_log)
                for call in to_execute
            ]
        )

        for outcome in results:
            _add_message(
                messages,
                {"role": "tool", "name": outcome["tool"], "content": outcome["content"]},
                session_path,
            )
            call_history.append(
                {"tool": outcome["tool"], "args": outcome["args"], "ok": outcome["ok"]}
            )
