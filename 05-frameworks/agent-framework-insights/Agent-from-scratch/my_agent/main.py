"""入口——把六篇文章的六层拼成一个可以对话的 Agent。

    第 1 篇 agent.py            Agent 的最小内核（单文件、可独立运行）
    第 2 篇 function_calling.py  手动拆解 Function Calling 的调度过程
    第 3 篇 react_loop.py        ReAct 循环：Thought → Action → Observation
    第 4 篇 tool_registry.py     可插拔的工具箱（注册 / 筛选 / 执行）
    第 5 篇 memory.py            三层记忆：短期 / 长期 / 工作记忆
    第 6 篇 error_handling.py    把以上几层用错误处理和降级策略包起来

真正跑起来的入口不是这几个文件里的任何一个 demo 函数，而是这里：
用 tool_registry 建工具箱，交给 error_handling.ProductionAgent ——
它内部会自己组装 RobustLLMClient / SafeToolExecutor / BoundedReActLoop /
MemoryAgent，对外只暴露一个 chat(user_input) -> str。
"""

from openai import OpenAI

from .error_handling import ProductionAgent
from .tool_registry import build_default_registry


def build_agent() -> ProductionAgent:
    """组装一个带完整工具箱 + 记忆 + 错误处理的生产级 Agent。"""
    client = OpenAI()  # 或用你自己的 base_url 指向 DeepSeek / Qwen 等
    registry = build_default_registry()
    return ProductionAgent(llm_client=client, tool_registry=registry)


def run_repl():
    """命令行交互：一行一句，输入 exit / quit 退出。"""
    agent = build_agent()
    print("🤖 Agent 已就绪（输入 exit 退出）")

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        response = agent.chat(user_input)
        print(f"Agent: {response}")


if __name__ == "__main__":
    run_repl()
