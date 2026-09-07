"""查天气工具"""

from ..tool_registry import Tool


def get_weather(city: str, date: str = "今天") -> dict:
    weather_data = {
        "上海-今天": {"天气": "晴", "温度": "28°C", "降水概率": "10%"},
        "上海-明天": {"天气": "中雨", "温度": "22°C", "降水概率": "85%"},
        "北京-今天": {"天气": "多云", "温度": "25°C", "降水概率": "20%"},
        "北京-明天": {"天气": "阴", "温度": "20°C", "降水概率": "40%"},
    }
    return weather_data.get(f"{city}-{date}", {"天气": "未知", "温度": "未知"})


TOOL = Tool(
    name="get_weather",
    description="获取指定城市在指定日期的天气信息，返回天气状况、温度和降水概率。当用户询问天气、气温、是否下雨、需要带伞时使用。",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名，如 上海、北京"},
            "date": {"type": "string", "description": "日期，如 今天、明天、2025-01-15"}
        },
        "required": ["city"]
    },
    func=get_weather,
    category="weather",
    keywords=["天气", "下雨", "温度", "气温", "带伞", "晴天", "阴天", "刮风"],
    priority=10,
)
