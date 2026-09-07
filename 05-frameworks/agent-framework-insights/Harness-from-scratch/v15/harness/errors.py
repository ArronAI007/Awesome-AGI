"""v8：结构化错误分类——区分可重试与不可重试错误。"""


class TransientError(Exception):
    """可重试的临时性故障：网络超时、限流等。"""


def classify_error(exc):
    if isinstance(exc, TransientError):
        return "retryable"
    return "non_retryable"
