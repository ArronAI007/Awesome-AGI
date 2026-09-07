"""
工具注册与筛选（第 4 篇）

工具箱 = 注册中心 + 筛选器 + 执行器：
- 注册工具 —— 把所有工具登记在册
- 筛选工具 —— 根据用户意图，只把相关的工具发给大模型
- 执行工具 —— 根据大模型的选择，找到对应的函数并执行

这个模块本身是通用框架，不认识任何具体工具——具体工具定义在 tools/ 包里，
通过 registry.register(Tool(...)) 注册进来。
"""

from typing import Callable, Any
import json
import re

from openai import OpenAI

client = OpenAI()  # 可以换成任何 OpenAI 兼容的 API


# ============================================================
# 工具定义标准格式
# ============================================================
class Tool:
    """单个工具的完整定义"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        func: Callable,
        category: str = "general",      # 工具分类
        keywords: list[str] = None,      # 触发关键词
        priority: int = 0,               # 优先级（越大越优先）
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.func = func
        self.category = category
        self.keywords = keywords or []
        self.priority = priority

    def to_openai_schema(self) -> dict:
        """转为 OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

    def __repr__(self):
        return f"Tool(name='{self.name}', category='{self.category}')"


# ============================================================
# 工具箱（注册中心）
# ============================================================
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}              # name → Tool
        self._by_category: dict[str, list[Tool]] = {}  # category → [Tool]

    def register(self, tool: Tool):
        """注册一个工具"""
        self._tools[tool.name] = tool
        if tool.category not in self._by_category:
            self._by_category[tool.category] = []
        self._by_category[tool.category].append(tool)

    def get(self, name: str) -> Tool | None:
        """按名称获取工具"""
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_categories(self) -> list[str]:
        """列出所有分类"""
        return list(self._by_category.keys())

    def count(self) -> int:
        return len(self._tools)


# ============================================================
# 注册所有工具
#
# 具体的工具函数（get_weather、send_email……）定义在 tools/ 包里，
# 每个模块导出一个 TOOL 实例。这里只负责把它们逐一注册进 ToolRegistry——
# 对应文章里"registry.register(Tool(...))"那一段，只是把 Tool(...) 的
# 定义搬去了 tools/ 下的对应模块。
#
# 用局部（函数体内）import，避免 tool_registry.py 和 tools/*.py 之间
# 出现"定义 Tool 类时就互相依赖"的真正循环导入——tools/*.py 只在模块加载时
# 需要 Tool 类，而 Tool 类本身不需要认识任何具体工具。
# ============================================================
def build_default_registry() -> ToolRegistry:
    """构建内置的默认工具箱：注册 weather / email / web_search /
    knowledge_base / calculator / todo / meeting 这七个工具。"""
    from .tools import weather, email, web_search, knowledge_base, calculator, todo, meeting

    registry = ToolRegistry()

    registry.register(weather.TOOL)
    registry.register(email.TOOL)
    registry.register(web_search.TOOL)
    registry.register(knowledge_base.TOOL)
    registry.register(calculator.TOOL)
    registry.register(todo.TOOL)

    # 需求来了：Agent 要能帮用户订会议室——动态注册，一行代码加一个新工具
    registry.register(meeting.TOOL)

    return registry


# ============================================================
# 第二层：工具筛选——三套方案，从简到难
# ============================================================

# 方案 A：按分类筛选（最简单）
def select_by_category(registry: ToolRegistry, category: str) -> list[dict]:
    """按分类筛选工具，返回 OpenAI 格式的工具列表"""
    tools = registry._by_category.get(category, [])
    return [t.to_openai_schema() for t in tools]


# 方案 B：按关键词匹配（实用派）
def select_by_keywords(registry: ToolRegistry, user_message: str, top_k: int = 5) -> list[dict]:
    """根据用户消息中的关键词匹配工具"""
    scores = []
    for tool in registry.list_all():
        score = 0
        for kw in tool.keywords:
            if kw in user_message:
                score += 1
        # 优先级作为加权
        score += tool.priority * 0.01
        if score > 0:
            scores.append((tool, score))

    # 按得分排序，取 top_k
    scores.sort(key=lambda x: x[1], reverse=True)
    selected = [tool for tool, _ in scores[:top_k]]

    print(f"🔍 用户消息: '{user_message}'")
    print(f"📋 匹配到 {len(selected)} 个工具: {[t.name for t in selected]}")
    return [t.to_openai_schema() for t in selected]


# 方案 C：用 Embedding 做语义检索（进阶版）
def get_embedding(text: str) -> list[float]:
    """获取文本的 Embedding 向量"""
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return resp.data[0].embedding


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def select_by_embedding(registry: ToolRegistry, user_message: str, top_k: int = 5) -> list[dict]:
    """基于 Embedding 语义相似度选择工具"""
    # 提前算好的工具向量（实际项目中缓存在本地）
    tool_texts = [f"{t.name}: {t.description}" for t in registry.list_all()]
    tool_embeddings = [get_embedding(text) for text in tool_texts]

    # 用户消息的向量
    query_embedding = get_embedding(user_message)

    # 计算相似度
    scores = []
    for tool, emb in zip(registry.list_all(), tool_embeddings):
        sim = cosine_similarity(query_embedding, emb)
        scores.append((tool, sim))

    scores.sort(key=lambda x: x[1], reverse=True)
    selected = [tool for tool, score in scores[:top_k] if score > 0.3]

    print(f"🔍 语义匹配 Top {top_k}：")
    for tool, score in scores[:top_k]:
        print(f"   {tool.name}: {score:.3f}")

    return [t.to_openai_schema() for t in selected]


# ============================================================
# 第三层：把工具箱接入 Agent 循环
#
# 用户输入 → 工具箱筛选（只发相关工具）→ ReAct 循环
#   （Thought-Action-Observation）→ 工具箱执行 → 返回结果
# ============================================================
SYSTEM_PROMPT = """你是一个智能助理，可以使用工具来回答用户问题。

## 输出格式

如果需要调用工具，严格按以下格式输出：
Thought: [你的推理过程]
Action: [工具名称]
Action Input: [JSON格式的参数]

如果任务已完成，输出：
Thought: [你的推理过程]
Final Answer: [最终回答]

## 规则
1. 每次只能调用一个工具
2. 必须等待工具返回结果后，才能进行下一步推理
3. 如果工具返回了错误，分析原因后决定下一步
4. 不要编造工具返回的结果
"""


def run_agent_with_toolbox(
    registry: ToolRegistry,
    user_message: str,
    max_steps: int = 10,
    top_k_tools: int = 5,
) -> str:
    """
    带工具箱的 ReAct Agent

    Args:
        registry: 工具注册中心
        user_message: 用户输入
        max_steps: 最大推理步数
        top_k_tools: 每次发给模型的工具数量上限
    """
    # 第0步：筛选相关工具
    active_tools = select_by_keywords(registry, user_message, top_k=top_k_tools)

    # 如果关键词匹配没找到，回退到全量（工具少的情况）
    if not active_tools:
        active_tools = [t.to_openai_schema() for t in registry.list_all()]

    # 构建带工具描述的系统提示
    tool_descriptions = "\n".join([
        f"- {t['function']['name']}: {t['function']['description']}"
        for t in active_tools
    ])

    full_system = SYSTEM_PROMPT + f"\n\n## 可用工具\n{tool_descriptions}"

    messages = [
        {"role": "system", "content": full_system},
        {"role": "user", "content": user_message},
    ]

    step = 0
    seen_actions = []  # 防无限循环

    while step < max_steps:
        step += 1
        print(f"\n{'='*50}\n🔄 第 {step} 步")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.3,
        )

        reply = response.choices[0].message.content
        print(f"📝 模型输出:\n{reply}")

        messages.append({"role": "assistant", "content": reply})

        # 检查是否是最终答案
        final_match = re.search(r'Final Answer:\s*(.*)', reply, re.DOTALL)
        if final_match:
            return final_match.group(1).strip()

        # 解析 Action
        action_match = re.search(r'Action:\s*(\S+)', reply)
        input_match = re.search(r'Action Input:\s*(\{.*?\})', reply, re.DOTALL)

        if not action_match or not input_match:
            # 格式不对，提示模型修正
            messages.append({
                "role": "user",
                "content": "请严格按照 Thought + Action + Action Input 格式输出，或给出 Final Answer。"
            })
            continue

        tool_name = action_match.group(1).strip()

        try:
            params = json.loads(input_match.group(1).strip())
        except json.JSONDecodeError:
            messages.append({
                "role": "user",
                "content": "Action Input 必须是合法的 JSON 格式。请重新输出。"
            })
            continue

        # 防重复：同一个工具+参数连续调2次
        action_key = f"{tool_name}:{json.dumps(params, sort_keys=True)}"
        if action_key in seen_actions:
            messages.append({
                "role": "user",
                "content": f"工具 {tool_name} 以相同参数已调用过，结果不变。请基于已有信息给出结论，或尝试其他方案。"
            })
            continue
        seen_actions.append(action_key)

        # 从工具箱获取工具并执行
        tool = registry.get(tool_name)
        if tool is None:
            # 检查是否在发给模型的列表里
            available_names = [t['function']['name'] for t in active_tools]
            messages.append({
                "role": "user",
                "content": f"工具 '{tool_name}' 不存在。可用工具: {available_names}。请重新选择。"
            })
            continue

        try:
            result = tool.func(**params)
        except Exception as e:
            result = {"error": str(e)}

        observation = json.dumps(result, ensure_ascii=False)
        print(f"🔧 执行 {tool_name}({params}) → {observation}")

        messages.append({
            "role": "user",
            "content": f"工具返回结果:\n{observation}"
        })

    return "⚠️ Agent 达到最大循环次数，任务未完成。"


# ============================================================
# 动态注册——从配置文件热加载工具
# ============================================================
def load_tools_from_config(config_path: str, registry: ToolRegistry):
    """从 YAML 配置文件加载工具定义"""
    import yaml  # 实际项目用 PyYAML

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    for tool_def in config['tools']:
        # 通过函数名字符串动态获取函数对象
        func = globals().get(tool_def['function'])
        if func is None:
            print(f"⚠️ 跳过 {tool_def['name']}: 函数 {tool_def['function']} 未找到")
            continue

        registry.register(Tool(
            name=tool_def['name'],
            description=tool_def['description'],
            parameters=tool_def['parameters'],
            func=func,
            category=tool_def.get('category', 'general'),
            keywords=tool_def.get('keywords', []),
            priority=tool_def.get('priority', 0),
        ))

    print(f"✅ 从配置文件加载了 {registry.count()} 个工具")


if __name__ == "__main__":
    registry = build_default_registry()
    print(f"✅ 已注册 {registry.count()} 个工具")
    print(f"📂 分类: {registry.list_categories()}")

    # 方案 A：按分类筛选
    weather_tools = select_by_category(registry, "weather")
    print(f"天气类工具有 {len(weather_tools)} 个: {[t['function']['name'] for t in weather_tools]}")

    # 方案 B：按关键词匹配
    test_messages = [
        "明天上海会下雨吗？",
        "帮我搜索一下公司请假流程",
        "算一下 1234 * 5678 等于多少",
        "帮我查一下今天天气，如果下雨就发邮件提醒我",
    ]
    for msg in test_messages:
        print(f"\n{'='*60}")
        select_by_keywords(registry, msg, top_k=3)
