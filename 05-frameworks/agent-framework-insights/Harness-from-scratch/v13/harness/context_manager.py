"""v5：在 v4 的上下文裁剪基础上加入压缩安全阀。"""


def compact_if_needed(messages, iteration, config):
    trigger_every = config["trigger_every"]
    if iteration % trigger_every != 0:
        return

    keep_recent = config["keep_recent_count"]
    exempt_tools = config.get("exempt_tools", set())

    for i in range(len(messages) - keep_recent):
        msg = messages[i]
        if msg["role"] != "tool":
            continue
        if msg.get("name") in exempt_tools:
            continue
        if msg["content"].startswith("[cleared:"):
            continue
        original_len = len(msg["content"])
        msg["content"] = f"[cleared: {original_len} chars]"


def needs_compression(messages, config):
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    return total_chars > config["char_threshold"]


def compress_history(messages, keep_recent_count):
    system_msgs = [m for m in messages if m["role"] == "system"]
    non_system = [m for m in messages if m["role"] != "system"]
    kept = non_system[-keep_recent_count:] if keep_recent_count else []
    compressed_count = len(non_system) - len(kept)

    summary = {
        "role": "system",
        "content": f"[compressed] 已将 {compressed_count} 条历史消息压缩为摘要。",
    }
    return system_msgs + [summary] + kept


class CompressionGuard:
    """连续压缩次数熔断，防止「摘要的摘要」死循环。"""

    def __init__(self, max_compressions):
        self.max_compressions = max_compressions
        self.compression_count = 0

    def record_compression(self):
        self.compression_count += 1

    def is_exhausted(self):
        return self.compression_count >= self.max_compressions
