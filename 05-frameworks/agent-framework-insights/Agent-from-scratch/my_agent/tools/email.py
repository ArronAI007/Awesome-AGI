"""发邮件工具"""

from ..tool_registry import Tool


def send_email(to: str, subject: str, body: str) -> dict:
    print(f"📧 发送邮件 → {to}")
    print(f"   主题: {subject}")
    print(f"   内容: {body}")
    return {"status": "sent", "to": to}


TOOL = Tool(
    name="send_email",
    description="发送电子邮件。当用户要求发邮件、发通知、发送报告时使用。",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "收件人邮箱地址"},
            "subject": {"type": "string", "description": "邮件主题"},
            "body": {"type": "string", "description": "邮件正文"}
        },
        "required": ["to", "subject", "body"]
    },
    func=send_email,
    category="communication",
    keywords=["邮件", "email", "发送", "通知"],
    priority=5,
)
