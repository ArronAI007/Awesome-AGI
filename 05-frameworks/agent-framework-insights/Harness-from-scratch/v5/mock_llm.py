"""脚本化的确定性假 LLM：没有真实 API Key 也能稳定复现固定场景。"""


class ScriptExhausted(Exception):
    """脚本用尽后仍被调用——说明循环没有在预期步数内自己停下来。"""


class MockLLM:
    def __init__(self, script):
        # script: [{"content": str | None, "tool_calls": [dict, ...]}, ...]
        # tool_calls 为空列表表示模型认为任务完成，循环应当停止。
        self.script = script
        self.call_count = 0

    def chat(self, messages, tools=None):
        if self.call_count >= len(self.script):
            raise ScriptExhausted(
                f"MockLLM 脚本只有 {len(self.script)} 步，但被调用了第 {self.call_count + 1} 次"
            )
        response = self.script[self.call_count]
        self.call_count += 1
        return response
