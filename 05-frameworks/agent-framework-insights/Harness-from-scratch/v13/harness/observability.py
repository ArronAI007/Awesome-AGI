"""v12：可观测性——结构化事件日志、token/成本估算、运行报告。"""

import json
import time


def estimate_tokens(text):
    if not text:
        return 0
    return max(1, len(text) // 4)


def compute_cost(tokens_in, tokens_out, rates):
    return (tokens_in / 1000) * rates["input_per_1k"] + (tokens_out / 1000) * rates["output_per_1k"]


class EventLog:
    """把结构化事件记进内存列表，指定路径时同步追加写入 JSONL。"""

    def __init__(self, log_path=None, clock_fn=time.perf_counter):
        self.log_path = log_path
        self.clock_fn = clock_fn
        self.events = []

    def record(self, event_type, **fields):
        event = {"event_type": event_type, "timestamp": self.clock_fn(), **fields}
        self.events.append(event)
        if self.log_path is not None:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")


def build_run_report(events, rates=None):
    rates = rates or {"input_per_1k": 0.0, "output_per_1k": 0.0}
    llm_calls = [e for e in events if e["event_type"] == "llm_call"]
    tool_calls = [e for e in events if e["event_type"] == "tool_call"]
    guardrail_events = [e for e in events if e["event_type"] == "guardrail"]

    tokens_in = sum(e.get("tokens_in", 0) for e in llm_calls)
    tokens_out = sum(e.get("tokens_out", 0) for e in llm_calls)

    guardrail_counts = {}
    for e in guardrail_events:
        name = e.get("name", "unknown")
        guardrail_counts[name] = guardrail_counts.get(name, 0) + 1

    return {
        "llm_call_count": len(llm_calls),
        "tool_call_count": len(tool_calls),
        "tool_call_success_count": sum(1 for e in tool_calls if e.get("ok")),
        "tool_call_failure_count": sum(1 for e in tool_calls if not e.get("ok")),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "estimated_cost": compute_cost(tokens_in, tokens_out, rates),
        "guardrail_counts": guardrail_counts,
    }
