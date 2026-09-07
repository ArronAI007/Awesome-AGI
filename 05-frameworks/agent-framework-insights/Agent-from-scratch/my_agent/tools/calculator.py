"""数学计算工具"""

from ..tool_registry import Tool


def calculate(expression: str) -> dict:
    try:
        result = eval(expression)  # 演示用eval，生产环境用安全的表达式解析器
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}


TOOL = Tool(
    name="calculate",
    description="执行数学计算。当用户需要进行数学运算、数值计算、公式求值时使用。",
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "数学表达式，如 3.14 * 2 ** 3"}
        },
        "required": ["expression"]
    },
    func=calculate,
    category="utility",
    keywords=["计算", "算", "等于", "多少", "数学", "公式"],
    priority=3,
)
