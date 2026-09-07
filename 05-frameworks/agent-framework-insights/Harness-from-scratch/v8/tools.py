"""示例工具集：内存态假文件系统 + 假搜索，配合 MockLLM 复现固定场景。"""

from harness.errors import TransientError


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
    flaky_state = {"attempts": 0}

    def read_file(path):
        if path not in fake_fs:
            raise FileNotFoundError(f"文件不存在: {path}")
        return fake_fs[path]

    def search_web(query):
        return f"搜索 '{query}' 的结果：暂无相关信息（mock 数据）。"

    def write_file(path, content):
        fake_fs[path] = content
        return f"已写入 {path}（{len(content)} 字符）"

    def flaky_api(query):
        flaky_state["attempts"] += 1
        if flaky_state["attempts"] <= 2:
            raise TransientError(f"临时故障（第 {flaky_state['attempts']} 次尝试）")
        return f"flaky_api 调用成功（第 {flaky_state['attempts']} 次尝试）：{query}"

    def always_fails_api(query):
        raise TransientError("这个接口一直不可用")

    return {
        "read_file": Tool("read_file", read_file, {"path": {"required": True}}),
        "search_web": Tool("search_web", search_web, {"query": {"required": True}}),
        "write_file": Tool(
            "write_file",
            write_file,
            {"path": {"required": True}, "content": {"required": True}},
        ),
        "flaky_api": Tool("flaky_api", flaky_api, {"query": {"required": True}}),
        "always_fails_api": Tool(
            "always_fails_api", always_fails_api, {"query": {"required": True}}
        ),
    }
