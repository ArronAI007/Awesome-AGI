"""互联网搜索工具"""

from ..tool_registry import Tool


def search_web(query: str) -> dict:
    # 演示用假数据
    fake_results = {
        "Python": "Python 3.13 已发布，新增多项性能优化...",
        "GPT-5": "OpenAI 发布 GPT-5，支持多模态和超长上下文...",
    }
    for key, result in fake_results.items():
        if key in query:
            return {"results": [result]}
    return {"results": [f"关于 '{query}' 的搜索结果（演示数据）"]}


TOOL = Tool(
    name="search_web",
    description="从互联网搜索最新公开信息。用于查找新闻、行业动态、技术文档、开源项目。不用于搜索公司内部文档（请用 search_knowledge_base）。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词，如 Python 3.13 新特性"}
        },
        "required": ["query"]
    },
    func=search_web,
    category="search",
    keywords=["搜索", "查找", "查询", "搜一下", "百度", "google", "检索"],
    priority=8,
)
