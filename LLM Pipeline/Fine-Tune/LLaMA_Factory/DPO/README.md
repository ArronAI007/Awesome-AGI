# DeepSeek Agent 调用器

一个轻量级的 DeepSeek Agent 调用项目，重点记录 Agent 的完整调用过程，用于生成微调和强化学习的训练数据。

## 功能特点

- 🤖 **DeepSeek Agent 调用**: 使用 DeepSeek API 的 function calling 功能
- 📝 **详细日志记录**: 记录每一步 Agent 的思考、工具选择、执行结果
- 🛠️ **多种工具**: 内置时间获取、天气查询、在线搜索等工具
- 💾 **数据导出**: 自动保存调用记录为 JSON 格式，方便后续微调使用
- ⚙️ **灵活配置**: 所有参数集中在配置文件中，易于调整

## 项目结构

```
公开课/
├── config.py           # 配置文件 - 所有 API 配置和系统参数
├── tools.py            # 工具函数库 - Agent 可调用的工具
├── agent_caller.py     # 主程序 - Agent 调用逻辑和日志记录
├── requirements.txt    # Python 依赖包
├── .env.example        # 环境变量模板
├── .env                # 环境变量配置（需自行创建）
├── README.md           # 本文档
└── logs/               # 日志目录（自动生成）
    └── agent_call_*.json
```

## 快速开始

### 1. 安装依赖

```bash
cd 公开课
pip install -r requirements.txt
```

### 2. 配置 API 密钥

复制环境变量模板并填入你的 API 密钥：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 API 密钥：

```env
# DeepSeek API Key (必需)
# 获取地址: https://platform.deepseek.com/api_keys
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx

# Tavily API Key (可选，用于在线搜索和天气查询)
# 获取地址: https://tavily.com/
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxx
```

**API 获取说明：**

- **DeepSeek API**:
  1. 访问 https://platform.deepseek.com/
  2. 注册/登录账号
  3. 进入 API Keys 页面创建新密钥

- **Tavily API** (可选):
  1. 访问 https://tavily.com/
  2. 注册账号
  3. 获取免费 API Key（有一定的免费额度）

### 3. 运行程序

```bash
python agent_caller.py
```

## 使用示例

启动程序后，你可以向 Agent 提问：

```
👤 你: 现在几点了？

🤖 Agent 正在思考...
🔧 Agent 决定调用工具:
   工具名称: get_current_time
   工具参数: {}
   📅 [工具执行] get_current_time() -> 当前时间: 2025-11-09 18:45:30, 周六
   执行结果: 当前时间: 2025-11-09 18:45:30, 周六

✅ Agent 最终回复:
现在是 2025年11月9日 18:45:30，星期六。
```

```
👤 你: 北京今天天气怎么样？

🤖 Agent 正在思考...
🔧 Agent 决定调用工具:
   工具名称: get_weather
   工具参数: {"city": "北京"}
   🌤️  [工具执行] get_weather(city='北京')
      ✅ 查询成功

✅ Agent 最终回复:
北京今天多云，气温 15-25℃，空气质量良好...
```

```
👤 你: 帮我搜索一下最新的 AI 新闻

🤖 Agent 正在思考...
🔧 Agent 决定调用工具:
   工具名称: search_online
   工具参数: {"query": "最新 AI 人工智能新闻"}
   🔍 [工具执行] search_online(query='最新 AI 人工智能新闻')
      ✅ 搜索成功，找到 3 条结果

✅ Agent 最终回复:
根据最新搜索结果，以下是近期的 AI 新闻...
```

## 可用命令

- **quit/exit/退出**: 退出程序
- **clear/清除**: 清除对话历史，开始新会话

## 配置说明

所有配置项都在 [config.py](config.py) 中，主要包括：

### DeepSeek 配置
- `DEEPSEEK_API_KEY`: API 密钥
- `DEEPSEEK_MODEL`: 模型名称（默认 `deepseek-chat`）
- `TEMPERATURE`: 温度参数，控制输出随机性（0.0-2.0）
- `MAX_TOKENS`: 单次响应最大 token 数

### Tavily 配置
- `TAVILY_API_KEY`: API 密钥
- `TAVILY_MAX_RESULTS`: 搜索结果数量
- `TAVILY_SEARCH_DEPTH`: 搜索深度（`basic` 或 `advanced`）

### 日志配置
- `LOG_DIR`: 日志存储目录
- `VERBOSE`: 是否打印详细日志
- `SAVE_CALL_LOGS`: 是否保存调用记录
- `LOG_FILE_FORMAT`: 日志文件命名格式

### Agent 配置
- `SYSTEM_PROMPT`: Agent 系统提示词
- `MAX_CONVERSATION_ROUNDS`: 最大对话轮数
- `PRINT_TOOL_CALLS`: 是否打印工具调用详情

## 日志数据格式

每次对话都会生成一个 JSON 日志文件，保存在 `logs/` 目录下，格式如下：

```json
{
  "session_id": "20251109_184530",
  "start_time": "2025-11-09T18:45:30.123456",
  "end_time": "2025-11-09T18:45:35.654321",
  "conversations": [
    {
      "type": "user_input",
      "timestamp": "2025-11-09T18:45:30.123456",
      "content": "现在几点了？"
    },
    {
      "type": "agent_thinking",
      "timestamp": "2025-11-09T18:45:31.234567",
      "content": "",
      "model": "deepseek-chat",
      "role": "assistant"
    },
    {
      "type": "tool_call",
      "timestamp": "2025-11-09T18:45:31.345678",
      "tool_name": "get_current_time",
      "tool_args": {},
      "tool_call_id": "call_xxx",
      "tool_result": "当前时间: 2025-11-09 18:45:31, 周六"
    },
    {
      "type": "final_response",
      "timestamp": "2025-11-09T18:45:35.456789",
      "content": "现在是 2025年11月9日 18:45:31，星期六。",
      "usage": {
        "prompt_tokens": 150,
        "completion_tokens": 25,
        "total_tokens": 175
      }
    }
  ]
}
```

**数据用途：**
- 直接用于微调数据集构建
- 分析 Agent 的决策过程
- 评估工具选择准确性
- 强化学习训练数据生成

## 工具说明

### 1. get_current_time
获取当前时间，包括日期和星期。

**参数**: 无

**示例**: "现在几点？"、"今天是星期几？"

### 2. get_weather
查询指定城市的天气信息（使用 Tavily 搜索）。

**参数**:
- `city` (string): 城市名称

**示例**: "北京天气怎么样？"、"上海今天下雨吗？"

### 3. search_online
在线搜索最新信息（使用 Tavily API）。

**参数**:
- `query` (string): 搜索查询

**示例**: "搜索最新的 AI 新闻"、"查一下今天的热点事件"

## 添加自定义工具

你可以轻松添加自己的工具，只需在 [tools.py](tools.py) 中：

1. **定义工具函数**:
```python
def your_custom_tool(param1: str, param2: int) -> str:
    """
    工具描述
    """
    # 实现逻辑
    return result
```

2. **注册工具**（在 `TOOLS` 列表中添加）:
```python
{
    "type": "function",
    "function": {
        "name": "your_custom_tool",
        "description": "工具功能描述",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "参数描述"
                },
                "param2": {
                    "type": "integer",
                    "description": "参数描述"
                }
            },
            "required": ["param1", "param2"]
        }
    }
}
```

3. **添加到映射字典**（在 `TOOL_FUNCTIONS` 中）:
```python
TOOL_FUNCTIONS = {
    # ... 其他工具
    "your_custom_tool": your_custom_tool
}
```

## 常见问题

### Q: DeepSeek API Key 从哪里获取？
A: 访问 https://platform.deepseek.com/api_keys 注册并创建 API Key。

### Q: 没有 Tavily API Key 可以使用吗？
A: 可以，时间获取功能不需要 Tavily。但天气查询和在线搜索需要 Tavily API。

### Q: 如何用于微调训练？
A: 程序会自动保存每次对话的完整记录到 `logs/` 目录，JSON 格式包含了用户输入、工具调用、Agent 响应等所有信息，可以直接用于构建微调数据集。

### Q: 如何修改 Agent 的行为？
A: 修改 [config.py](config.py) 中的 `SYSTEM_PROMPT` 来调整 Agent 的角色和行为模式。

### Q: 日志文件太多怎么办？
A: 可以在 [config.py](config.py) 中设置 `SAVE_CALL_LOGS = False` 来关闭日志保存，或定期清理 `logs/` 目录。

## 技术栈

- **DeepSeek API**: 大语言模型和 Function Calling
- **OpenAI SDK**: 兼容 DeepSeek API
- **Tavily API**: 在线搜索和信息检索
- **Python 3.8+**: 推荐使用 Python 3.8 或更高版本

## 开发建议

1. **测试工具**: 先单独测试每个工具函数，确保返回正确
2. **调整提示词**: 根据实际需求修改 `SYSTEM_PROMPT`
3. **监控 Token**: 注意 API 调用的 token 消耗
4. **数据清洗**: 收集到的日志数据可能需要清洗后再用于微调

## 许可证

本项目仅用于学习和研究目的。

## 联系方式

如有问题或建议，请通过 Issue 反馈。
