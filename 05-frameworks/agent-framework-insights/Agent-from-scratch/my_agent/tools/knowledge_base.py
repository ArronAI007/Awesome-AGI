"""公司内部知识库搜索工具"""

from ..tool_registry import Tool


def search_knowledge_base(query: str) -> dict:
    fake_kb = {
        "请假": "员工请假流程：1. 在OA系统提交申请 2. 直属leader审批 3. HR备案",
        "报销": "报销流程：发票拍照上传OA → 填写报销单 → leader审批 → 财务打款（3个工作日内）",
    }
    for key, result in fake_kb.items():
        if key in query:
            return {"results": [result]}
    return {"results": [f"知识库中未找到关于 '{query}' 的相关文档"]}


TOOL = Tool(
    name="search_knowledge_base",
    description="从公司内部知识库搜索文档、Wiki、流程说明。用于查找内部流程、公司政策、项目文档、技术规范。不用于搜索互联网公开信息（请用 search_web）。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词，如 请假流程 报销规定"}
        },
        "required": ["query"]
    },
    func=search_knowledge_base,
    category="search",
    keywords=["内部", "知识库", "公司", "流程", "规定", "政策", "文档", "wiki"],
    priority=8,
)
