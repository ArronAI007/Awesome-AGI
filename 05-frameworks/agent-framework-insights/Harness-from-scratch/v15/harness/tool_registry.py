"""v14：动态工具注册表——dict 的行为兼容子类，支持运行时 register/unregister。"""


class ToolRegistry(dict):
    """除了新增的 register/unregister，其余行为完全是普通 dict：
    `registry[name]`、`del registry[name]`、`name in registry`、`.keys()` 都不用改。
    """

    def register(self, tool):
        self[tool.name] = tool

    def unregister(self, name):
        self.pop(name, None)
