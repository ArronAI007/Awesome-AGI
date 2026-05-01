"""
工具函数库 - 提供 Agent 可以调用的各种工具
每个工具都有详细的描述，方便 DeepSeek Agent 理解和调用
"""

import json
from datetime import datetime
from typing import Dict, Any
from tavily import TavilyClient
from config import config


# ============== 工具函数定义 ==============

def get_current_time() -> str:
    """
    获取当前时间
    这是一个本地函数，不需要调用外部 API

    返回:
        str: 当前时间的字符串表示，格式为 YYYY-MM-DD HH:MM:SS
    """
    current_time = datetime.now()
    time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][current_time.weekday()]

    result = f"当前时间: {time_str}, {weekday}"
    print(f"  📅 [工具执行] get_current_time() -> {result}")
    return result


def get_weather(city: str) -> str:
    """
    查询指定城市的天气信息
    使用 Tavily 搜索引擎获取实时天气数据

    参数:
        city (str): 城市名称，例如 "北京"、"上海"

    返回:
        str: 天气信息的字符串描述
    """
    print(f"  🌤️  [工具执行] get_weather(city='{city}')")

    if not config.TAVILY_API_KEY:
        return "错误: Tavily API Key 未配置，无法查询天气信息"

    try:
        # 使用 Tavily 搜索天气信息
        tavily_client = TavilyClient(api_key=config.TAVILY_API_KEY)
        query = f"{city} 天气 实时"

        search_result = tavily_client.search(
            query=query,
            max_results=2,
            search_depth=config.TAVILY_SEARCH_DEPTH
        )

        if search_result and "results" in search_result and len(search_result["results"]) > 0:
            # 提取搜索结果中的内容
            weather_info = search_result["results"][0]["content"]
            result = f"{city}的天气信息: {weather_info}"
            print(f"     ✅ 查询成功")
            return result
        else:
            result = f"未找到{city}的天气信息"
            print(f"     ⚠️  {result}")
            return result

    except Exception as e:
        error_msg = f"查询天气时发生错误: {str(e)}"
        print(f"     ❌ {error_msg}")
        return error_msg


def search_online(query: str) -> str:
    """
    使用 Tavily 进行在线搜索
    可以搜索最新的信息、新闻、事实等

    参数:
        query (str): 搜索查询字符串

    返回:
        str: 搜索结果的摘要信息
    """
    print(f"  🔍 [工具执行] search_online(query='{query}')")

    if not config.TAVILY_API_KEY:
        return "错误: Tavily API Key 未配置，无法进行在线搜索"

    try:
        tavily_client = TavilyClient(api_key=config.TAVILY_API_KEY)

        search_result = tavily_client.search(
            query=query,
            max_results=config.TAVILY_MAX_RESULTS,
            search_depth=config.TAVILY_SEARCH_DEPTH
        )

        if search_result and "results" in search_result and len(search_result["results"]) > 0:
            # 整理搜索结果
            results = []
            for i, item in enumerate(search_result["results"][:config.TAVILY_MAX_RESULTS], 1):
                title = item.get("title", "无标题")
                content = item.get("content", "无内容")
                url = item.get("url", "")
                results.append(f"{i}. {title}\n   {content}\n   来源: {url}")

            result = f"搜索'{query}'的结果:\n" + "\n\n".join(results)
            print(f"     ✅ 搜索成功，找到 {len(search_result['results'])} 条结果")
            return result
        else:
            result = f"未找到关于'{query}'的搜索结果"
            print(f"     ⚠️  {result}")
            return result

    except Exception as e:
        error_msg = f"在线搜索时发生错误: {str(e)}"
        print(f"     ❌ {error_msg}")
        return error_msg


# ============== 工具注册表 ==============
# 定义工具的元数据，供 DeepSeek Agent 使用

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前的日期和时间，包括星期几。当用户询问现在几点、今天日期等时间相关问题时使用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的实时天气信息。当用户询问某地天气、气温、天气状况时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "要查询天气的城市名称，例如：北京、上海、深圳等"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_online",
            "description": "在互联网上搜索最新信息、新闻、事实等。当用户询问最新的事件、新闻、不在你知识库中的信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询字符串，应该清晰准确地描述要搜索的内容"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


# ============== 工具调用映射 ==============
# 将工具名称映射到实际的函数

TOOL_FUNCTIONS = {
    "get_current_time": get_current_time,
    "get_weather": get_weather,
    "search_online": search_online
}


def execute_tool(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """
    执行指定的工具函数

    参数:
        tool_name (str): 工具名称
        tool_args (dict): 工具参数

    返回:
        str: 工具执行结果
    """
    if tool_name not in TOOL_FUNCTIONS:
        return f"错误: 未知的工具 '{tool_name}'"

    try:
        func = TOOL_FUNCTIONS[tool_name]
        result = func(**tool_args)
        return result
    except Exception as e:
        error_msg = f"执行工具 '{tool_name}' 时发生错误: {str(e)}"
        print(f"  ❌ {error_msg}")
        return error_msg
