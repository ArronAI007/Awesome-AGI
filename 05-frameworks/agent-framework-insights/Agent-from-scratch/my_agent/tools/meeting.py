"""会议室预订工具——演示"动态注册"：加一个新工具只需要一行注册"""

from ..tool_registry import Tool


def book_meeting_room(room: str, date: str, start_time: str, end_time: str) -> dict:
    """预订会议室（演示版）"""
    print(f"🏢 预订会议室: {room}, {date} {start_time}-{end_time}")
    return {"status": "booked", "room": room, "date": date, "time": f"{start_time}-{end_time}"}


TOOL = Tool(
    name="book_meeting_room",
    description="预订会议室。当用户需要预订、预约、占用会议室时使用。",
    parameters={
        "type": "object",
        "properties": {
            "room": {"type": "string", "description": "会议室名称，如 A201、B305"},
            "date": {"type": "string", "description": "日期，如 明天、2025-07-30"},
            "start_time": {"type": "string", "description": "开始时间，如 14:00"},
            "end_time": {"type": "string", "description": "结束时间，如 15:00"},
        },
        "required": ["room", "date", "start_time", "end_time"]
    },
    func=book_meeting_room,
    category="facility",
    keywords=["会议室", "预订", "预约", "book", "占用"],
    priority=5,
)
