import os
import logging
from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from tools import search
from deepagents.backends import FilesystemBackend

from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore
# === Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# === Load environment ===
load_dotenv()

# === Config ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
RECURSION_LIMIT = int(os.getenv("RECURSION_LIMIT", 25))

# === 系统指令 ===
SYSTEM_PROMPT = """你是一个股票分析助手。

你的任务是帮助用户分析股票，使用 search 工具搜索相关信息。

工作流程：
1. 理解用户要分析的股票代码和名称
2. 使用 search 搜索该股票的相关信息
3. 基于搜索结果，提供清晰的分析报告

输出要求：
- 使用中文
- 结构清晰，逻辑严密
- 引用搜索到的信息来源
- 提供有价值的见解

注意：
- 股市有风险，投资需谨慎
- 搜索结果仅供参考，不构成投资建议
- 把股票分析结果保存成/reports下面的Markdown文件
- 把用户分析过的股票名称保存到/memories/my_stocks.md中，方便下次调用
"""

logging.info("✅ 系统指令已加载")

# === 主智能体的工具 ===
main_tools = [
    search,  # 通用网络搜索工具
]

logging.info(f"✅ 主智能体配置了 {len(main_tools)} 个工具")

from langchain.embeddings import init_embeddings

def make_backend(runtime):
    return CompositeBackend(
        default=FilesystemBackend(root_dir="./fs", virtual_mode=True),  
        routes={
            "/memories/": StoreBackend(runtime) 
        }
    )

# === 创建 DeepAgent（无后端，无子智能体）===
agent = create_deep_agent(
    model=f"openai:{OPENAI_MODEL}",
    tools=main_tools,
    backend=make_backend,
    system_prompt=SYSTEM_PROMPT,debug=True
).with_config({"recursion_limit": RECURSION_LIMIT})

logging.info(f"✅ 简单 DeepAgent 已创建")
logging.info(f"  - 模型: {OPENAI_MODEL}")
logging.info(f"  - 递归限制: {RECURSION_LIMIT}")
logging.info(f"  - 工具: search")
logging.info(f"  - 子智能体: 无")
logging.info(f"  - 后端: 无")

# === 测试运行 ===
if __name__ == "__main__":
    import sys
    
    # 从命令行获取股票代码，如果没有则使用默认值
    stock_query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "分析贵州茅台 600519"
    
    logging.info(f"\n{'='*60}")
    logging.info(f"开始分析: {stock_query}")
    logging.info(f"{'='*60}\n")
    
    try:
        # 运行 agent
        result = agent.invoke({"messages": [{"role": "user", "content": stock_query}]})
        
        # 输出结果
        print("\n" + "="*60)
        print("分析结果：")
        print("="*60 + "\n")
        
        # 获取最后一条消息
        if result and "messages" in result:
            last_message = result["messages"][-1]
            if hasattr(last_message, "content"):
                print(last_message.content)
            else:
                print(last_message)
        else:
            print("未获取到分析结果")
            
    except Exception as e:
        logging.error(f"分析过程中出错: {str(e)}", exc_info=True)