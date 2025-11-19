"""
配置文件 - 集中管理所有 API 配置和系统参数
所有敏感信息请通过环境变量设置
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Config:
    """配置类 - 统一管理所有配置项"""

    # ============== DeepSeek API 配置 ==============
    # DeepSeek API 密钥 - 从环境变量获取
    # 获取地址: https://platform.deepseek.com/api_keys
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

    # DeepSeek API 基础 URL
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"

    # DeepSeek 模型名称
    # 推荐使用 deepseek-chat，支持 function calling
    DEEPSEEK_MODEL = "deepseek-chat"

    # 温度参数 - 控制输出随机性 (0.0-2.0)
    # 较低的值使输出更确定，较高的值使输出更随机
    TEMPERATURE = 0.7

    # 最大 token 数 - 控制单次响应的最大长度
    MAX_TOKENS = 2000


    # ============== Tavily API 配置 ==============
    # Tavily API 密钥 - 用于网络搜索
    # 获取地址: https://tavily.com/
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

    # Tavily 搜索结果数量 - 控制返回多少条搜索结果
    TAVILY_MAX_RESULTS = 3

    # Tavily 搜索深度 - "basic" 或 "advanced"
    # basic: 快速搜索，advanced: 深度搜索（更详细但更慢）
    TAVILY_SEARCH_DEPTH = "basic"


    # ============== 日志配置 ==============
    # 日志输出目录 - 存放调用记录的文件夹
    LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")

    # 是否在控制台打印详细日志
    VERBOSE = True

    # 是否保存每次调用的完整记录（用于微调数据收集）
    SAVE_CALL_LOGS = True

    # 日志文件格式 - 使用时间戳命名
    LOG_FILE_FORMAT = "agent_call_{timestamp}.json"


    # ============== Agent 配置 ==============
    # Agent 系统提示词 - 定义 Agent 的行为和角色
    SYSTEM_PROMPT = """你是一个智能助手，可以使用多种工具来帮助用户。
你可以获取当前时间、查询天气信息、进行网络搜索等。
请根据用户的问题，选择合适的工具来回答。"""

    # 最大对话轮数 - 防止无限循环
    MAX_CONVERSATION_ROUNDS = 10

    # 是否在每次工具调用后打印详细信息
    PRINT_TOOL_CALLS = True


    # ============== 验证配置 ==============
    @classmethod
    def validate(cls):
        """验证必要的配置是否已设置"""
        errors = []

        if not cls.DEEPSEEK_API_KEY:
            errors.append("❌ DEEPSEEK_API_KEY 未设置，请在 .env 文件中配置")

        if not cls.TAVILY_API_KEY:
            errors.append("⚠️  TAVILY_API_KEY 未设置，网络搜索功能将不可用")

        if errors:
            print("\n配置检查结果:")
            for error in errors:
                print(error)
            print("\n请参考 .env.example 文件创建 .env 并填入正确的 API 密钥\n")

            if not cls.DEEPSEEK_API_KEY:
                raise ValueError("DeepSeek API Key 是必需的")

        # 确保日志目录存在
        os.makedirs(cls.LOG_DIR, exist_ok=True)

        print("✅ 配置验证通过")
        return True


# 导出配置实例
config = Config()
