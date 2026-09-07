"""v8：指数退避重试 + 单工具级熔断器。"""


def compute_backoff_delay(attempt, base_delay=1.0):
    return base_delay * (2 ** attempt)


class ToolCircuitBreaker:
    """按工具名记录连续失败次数，达到阈值就判定该工具熔断。"""

    def __init__(self, failure_threshold):
        self.failure_threshold = failure_threshold
        self.consecutive_failures = {}

    def record_success(self, tool_name):
        self.consecutive_failures[tool_name] = 0

    def record_failure(self, tool_name):
        self.consecutive_failures[tool_name] = (
            self.consecutive_failures.get(tool_name, 0) + 1
        )

    def is_tripped(self, tool_name):
        return self.consecutive_failures.get(tool_name, 0) >= self.failure_threshold
