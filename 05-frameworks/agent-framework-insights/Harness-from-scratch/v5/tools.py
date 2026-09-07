"""示例工具集：内存态假文件系统 + 假搜索，配合 MockLLM 复现固定场景。"""


class Tool:
    def __init__(self, name, func, params=None):
        self.name = name
        self.func = func
        self.params = params or {}  # param_name -> {"required": bool}

    def run(self, args):
        return self.func(**args)


def _make_fake_fs():
    return {"config.yaml": "timeout: 30\nretries: 3\n"}


def build_default_tool_registry():
    fake_fs = _make_fake_fs()

    def read_file(path):
        if path not in fake_fs:
            raise FileNotFoundError(f"文件不存在: {path}")
        return fake_fs[path]

    def search_web(query):
        return f"搜索 '{query}' 的结果：" + ("x" * 500)

    def write_file(path, content):
        fake_fs[path] = content
        return f"已写入 {path}（{len(content)} 字符）"

    return {
        "read_file": Tool("read_file", read_file, {"path": {"required": True}}),
        "search_web": Tool("search_web", search_web, {"query": {"required": True}}),
        "write_file": Tool(
            "write_file",
            write_file,
            {"path": {"required": True}, "content": {"required": True}},
        ),
    }
