import os
import json
import logging
import sys
from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI
from tools import (
    get_stock_price,
    get_financial_statements,
    get_technical_indicators,
    get_stock_detailed_info,
    get_stock_news,
    get_stock_research_report,
    search_financial_news,
    search_market_trends
)
from deepagents.backends import FilesystemBackend

# === Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# === Load environment ===
load_dotenv()

# === Config ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
RECURSION_LIMIT = int(os.getenv("RECURSION_LIMIT", 25))

# === Load core instructions ===
with open("prompts.md", "r", encoding="utf-8") as f:
    CORE_INSTRUCTIONS = f.read()

print(f"✅ 已加载核心指令: {CORE_INSTRUCTIONS} ")
# === Load subagents config ===
with open("subagents.json", "r", encoding="utf-8") as f:
    subagents_config = json.load(f)

# === 构建子智能体 ===

# 1. 基本面分析师 - 使用股票详细信息和财务报表工具
fundamental_analyst = {
    "name": subagents_config["fundamental_analyst"]["name"],
    "description": subagents_config["fundamental_analyst"]["description"],
    "system_prompt": "\n".join(subagents_config["fundamental_analyst"]["prompt"]),
    "tools": [
        get_stock_detailed_info,      # 公司详细信息（主营、概况、筹码、分红）
        get_financial_statements,     # 财务报表（资产负债表、利润表、现金流量表）
        search_market_trends,         # 搜索行业趋势和市场前景
    ],
    "model": f"openai:{OPENAI_MODEL}",
}

# 2. 技术面分析师 - 使用技术指标和股票价格工具
technical_analyst = {
    "name": subagents_config["technical_analyst"]["name"],
    "description": subagents_config["technical_analyst"]["description"],
    "system_prompt": "\n".join(subagents_config["technical_analyst"]["prompt"]),
    "tools": [
        get_technical_indicators,     # 技术指标（20+项指标）
        get_stock_price,              # 股票历史价格数据
    ],
    "model": f"openai:{OPENAI_MODEL}",
}

# 3. 消息面分析师 - 使用新闻和研报查询工具
news_analyst = {
    "name": subagents_config["news_analyst"]["name"],
    "description": subagents_config["news_analyst"]["description"],
    "system_prompt": "\n".join(subagents_config["news_analyst"]["prompt"]),
    "tools": [
        get_stock_news,               # 个股新闻
        get_stock_research_report,    # 机构研究报告
        search_financial_news,        # 搜索财经新闻和市场动态
    ],
    "model": f"openai:{OPENAI_MODEL}",
}

subagents = [fundamental_analyst, technical_analyst, news_analyst]

logging.info(f"✅ 已配置 {len(subagents)} 个子智能体")
for sa in subagents:
    logging.info(f"  - {sa['name']}: {len(sa['tools'])} 个工具")

# === 主智能体的工具（只配置搜索工具，其他工具由子智能体使用） ===
main_tools = [
    search_financial_news,        # 搜索财经新闻
    search_market_trends,         # 搜索市场趋势
]

logging.info(f"✅ 主智能体配置了 {len(main_tools)} 个搜索工具")

# === 创建 DeepAgent ===
agent = create_deep_agent(
    model=f"openai:{OPENAI_MODEL}",
    subagents=subagents,
    tools=main_tools,
    system_prompt=CORE_INSTRUCTIONS,
    backend=FilesystemBackend(root_dir="./fs", virtual_mode=True)
).with_config({"recursion_limit": RECURSION_LIMIT})

logging.info(f"✅ DeepAgent 已创建")
logging.info(f"  - 模型: {OPENAI_MODEL}")
logging.info(f"  - 递归限制: {RECURSION_LIMIT}")
logging.info(f"  - 主智能体工具: 2个搜索工具")
logging.info(f"  - 子智能体: 基本面分析师、技术面分析师、消息面分析师")

