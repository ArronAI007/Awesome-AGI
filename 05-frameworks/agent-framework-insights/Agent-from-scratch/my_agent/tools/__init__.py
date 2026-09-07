"""工具箱：每个模块暴露一个 TOOL 实例，这里汇总成 ALL_TOOLS 供 main.py 批量注册。"""

from . import weather, email, web_search, knowledge_base, calculator, todo, meeting

ALL_TOOLS = [
    weather.TOOL,
    email.TOOL,
    web_search.TOOL,
    knowledge_base.TOOL,
    calculator.TOOL,
    todo.TOOL,
    meeting.TOOL,
]
