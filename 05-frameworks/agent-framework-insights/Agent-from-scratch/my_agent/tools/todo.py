"""待办事项工具"""

from ..tool_registry import Tool


def add_todo(task: str, priority: str = "normal") -> dict:
    print(f"✅ 已添加待办: [{priority}] {task}")
    return {"status": "added", "task": task, "priority": priority}


TOOL = Tool(
    name="add_todo",
    description="添加一条待办事项。当用户说要记住某事、提醒自己、添加任务、记录待办时使用。",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "待办事项内容"},
            "priority": {"type": "string", "description": "优先级: low, normal, high", "enum": ["low", "normal", "high"]}
        },
        "required": ["task"]
    },
    func=add_todo,
    category="productivity",
    keywords=["待办", "提醒", "记住", "别忘了", "todo", "任务"],
    priority=5,
)
