"""v4：上下文裁剪——周期性清理旧的工具输出，支持按工具名豁免。"""


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
