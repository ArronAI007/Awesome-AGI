# pip install -qU "langchain[anthropic]" to call the model
from dotenv import load_dotenv
load_dotenv()

from langchain.agents import create_agent


def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"


agent = create_agent(
    model="deepseek-chat",
    tools=[get_weather],
    system_prompt="You are a helpful assistant",
)


# Run the agent
result = agent.invoke(
    {"messages": [{"role": "user", "content": "what is the weather in sf"}]}
)


# 取最后一条消息的内容
print(result["messages"][-1].content)


for msg in result["messages"]:
    print(msg.type, "->", msg.content)
