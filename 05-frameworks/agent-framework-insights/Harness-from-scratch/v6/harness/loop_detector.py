"""v3：循环空转检测——对最近的工具调用做参数哈希，识别原地打转。"""

import hashlib


def hash_args(tool_name, args):
    raw = f"{tool_name}{sorted(args.items())}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def detect_loop(call_history):
    recent = call_history[-10:]

    if len(recent) >= 5:
        hashes = [hash_args(item["tool"], item["args"]) for item in recent[-5:]]
        if len(set(hashes)) == 1:
            return {
                "severity": "critical",
                "reason": "连续 5 次调用参数完全相同，判定为空转",
                "blocked_tool": recent[-1]["tool"],
            }

    fail_count = sum(1 for rec in recent if not rec["ok"])
    if fail_count >= 8:
        return {
            "severity": "warning",
            "reason": f"最近 {len(recent)} 步中有 {fail_count} 步失败",
            "blocked_tool": None,
        }

    return {"severity": "none", "reason": "", "blocked_tool": None}
