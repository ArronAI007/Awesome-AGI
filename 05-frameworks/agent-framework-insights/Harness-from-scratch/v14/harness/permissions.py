"""v11：权限规则引擎——allow/ask/deny 三态，执行前拦截危险操作。"""


def check_permission(call, policy):
    return policy.get(call["name"], "allow")
