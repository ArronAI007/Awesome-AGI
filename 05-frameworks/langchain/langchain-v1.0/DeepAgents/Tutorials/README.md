以下内容来自：https://github.com/pingcy/deepagents-demo/tree/main
DeepAgents Demo
基于 LangGraph 和 DeepAgents 框架的 A 股股票分析智能体示例项目。

项目简介
本项目演示了如何使用 DeepAgents 框架构建多智能体协作系统，用于 A 股股票的全面分析。系统包含三个专业分析师智能体，分别负责基本面、技术面和消息面分析。

功能特点
🤖 多智能体协作：基本面分析师、技术面分析师、消息面分析师协同工作
📊 全面数据分析：股票价格、财务报表、技术指标、新闻资讯、研究报告
📝 自动生成报告：输出 Markdown 格式的结构化股票分析报告
🔍 智能搜索：集成 Tavily 和 SearXNG 搜索引擎
💾 持久化存储：支持文件系统后端存储分析结果
项目结构
.
├── research_simple_deep_agent.py    # 简单股票分析 Agent（单一智能体）
├── research_stock_deep_agent.py     # 完整股票分析 Agent（多智能体协作）
├── tools.py                         # 股票分析工具集
├── prompts.md                       # 主智能体系统提示词
├── subagents.json                   # 子智能体配置
├── pyproject.toml                   # 项目依赖配置
└── fs/                              # 文件系统后端存储目录
    └── analysis/                    # 生成的分析报告
工具集
股票数据工具
get_stock_price - 获取 A 股历史行情数据
get_technical_indicators - 计算 20+ 项技术指标
get_financial_statements - 获取财务报表（资产负债表/利润表/现金流量表）
get_stock_detailed_info - 获取公司详细信息、主营业务、分红情况
get_stock_news - 获取个股最新新闻
get_stock_research_report - 获取机构研究报告
搜索工具
search - 通用网络搜索
search_financial_news - 搜索财经新闻
search_market_trends - 搜索市场趋势
数据来源：AKShare、Baostock

快速开始
1. 环境要求
Python >= 3.13
OpenAI API Key（或兼容的 API）
Tavily API Key（可选，用于网络搜索）
2. 安装依赖
推荐使用 uv 进行包管理：

# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步依赖
uv sync
或使用 pip：

pip install -e .
3. 配置环境变量
复制 .env.example 为 .env 并填写配置：

cp .env.example .env
编辑 .env 文件：

# OpenAI API 配置
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini

# Tavily 搜索 API（可选）
TAVILY_API_KEY=your_tavily_api_key_here

# SearXNG 搜索引擎（可选）
SEARXNG_URL=http://localhost:8080

# Agent 配置
RECURSION_LIMIT=25
4. 运行示例
简单版本（单一智能体）
python research_simple_deep_agent.py "分析贵州茅台 600519"
完整版本（多智能体协作）
python research_stock_deep_agent.py
然后在交互式对话中输入：

分析贵州茅台 600519
使用说明
分析师角色
基本面分析师

公司基本情况和主营业务
财务报表深度分析
盈利能力、偿债能力、成长性评估
行业趋势和估值水平
技术面分析师

价格趋势判断
技术指标分析（均线、MACD、KDJ、RSI 等）
支撑位和阻力位识别
买卖时机建议
消息面分析师

重大新闻梳理
机构研报观点汇总
市场情绪分析
催化剂识别
输出结果
分析报告将保存在 fs/analysis/ 目录下，格式为 Markdown。

技术栈
LangGraph - 多智能体编排框架
DeepAgents - 深度智能体框架
LangChain - LLM 应用开发框架
AKShare - A 股数据获取
Baostock - 证券数据接口
Tavily - AI 搜索引擎（可选）
注意事项
本项目仅供学习和研究使用
股票分析结果仅供参考，不构成投资建议
股市有风险，投资需谨慎
API Key 请妥善保管，不要泄露
License
MIT

免责声明
本项目提供的股票分析功能仅供参考，不构成任何投资建议。投资者应根据自身情况独立决策，并自行承担投资风险。