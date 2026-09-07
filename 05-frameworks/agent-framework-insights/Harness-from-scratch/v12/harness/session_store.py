"""v9：会话持久化——把消息历史落盘为 JSONL，支持断点续跑。"""

import json


def append_message(session_path, message):
    with open(session_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(message, ensure_ascii=False) + "\n")


def load_session(session_path):
    if not session_path.exists():
        return []
    with open(session_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
