"""
DeepSeek Agent 调用器 - 主程序
功能：调用 DeepSeek API，记录完整的 Agent 调用过程，用于后续微调或强化学习
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any
from openai import OpenAI
from config import config
from tools import TOOLS, execute_tool


class AgentCallLogger:
    """Agent 调用日志记录器 - 详细记录每次调用的全过程"""

    def __init__(self):
        self.call_history = []  # 存储所有调用记录
        self.current_session = {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "start_time": datetime.now().isoformat(),
            "conversations": []
        }

    def log_user_input(self, user_input: str):
        """记录用户输入"""
        print(f"\n{'='*60}")
        print(f"👤 用户输入: {user_input}")
        print(f"{'='*60}\n")

        self.current_session["conversations"].append({
            "type": "user_input",
            "timestamp": datetime.now().isoformat(),
            "content": user_input
        })

    def log_api_request(self, request_data: Dict[str, Any]):
        """记录发送给 API 的请求数据"""
        print(f"\n📤 发送给 DeepSeek API 的请求:")
        print(f"   模型: {request_data.get('model', 'N/A')}")
        print(f"   温度: {request_data.get('temperature', 'N/A')}")
        print(f"   最大 tokens: {request_data.get('max_tokens', 'N/A')}")
        print(f"   消息历史长度: {len(request_data.get('messages', []))} 条")
        print(f"   可用工具: {len(request_data.get('tools', []))} 个")

        # 打印最近的消息内容（最多显示最后3条）
        messages = request_data.get('messages', [])
        print(f"\n   最近消息内容:")
        for msg in messages[-3:]:
            # 处理可能是字典或 Pydantic 对象的消息
            if hasattr(msg, 'model_dump'):
                # 是 Pydantic 对象，转换为字典
                msg_dict = msg.model_dump()
            elif isinstance(msg, dict):
                # 已经是字典
                msg_dict = msg
            else:
                # 未知类型，跳过
                continue

            role = msg_dict.get('role', 'unknown')
            content = msg_dict.get('content', '')
            if content:
                content_preview = content[:100] + '...' if len(content) > 100 else content
                print(f"     [{role}]: {content_preview}")
            elif msg_dict.get('tool_calls'):
                print(f"     [{role}]: [调用了 {len(msg_dict['tool_calls'])} 个工具]")
            elif role == 'tool':
                print(f"     [{role}]: [工具执行结果]")

        # 将请求数据中的 Pydantic 对象转换为字典，以便保存为 JSON
        serializable_request_data = {
            "model": request_data.get("model"),
            "temperature": request_data.get("temperature"),
            "max_tokens": request_data.get("max_tokens"),
            "messages": [
                msg.model_dump() if hasattr(msg, 'model_dump') else msg
                for msg in request_data.get("messages", [])
            ],
            "tools": request_data.get("tools", [])
        }

        self.current_session["conversations"].append({
            "type": "api_request",
            "timestamp": datetime.now().isoformat(),
            "request_data": serializable_request_data
        })

    def log_api_response(self, response_data: Dict[str, Any]):
        """记录 API 返回的原始响应数据"""
        print(f"\n📥 DeepSeek API 原始响应:")
        print(f"   响应 ID: {response_data.get('id', 'N/A')}")
        print(f"   模型: {response_data.get('model', 'N/A')}")
        print(f"   创建时间: {response_data.get('created', 'N/A')}")

        if response_data.get('usage'):
            usage = response_data['usage']
            print(f"   Token 使用: {usage.get('prompt_tokens', 0)} (输入) + {usage.get('completion_tokens', 0)} (输出) = {usage.get('total_tokens', 0)} (总计)")

        if response_data.get('choices'):
            choice = response_data['choices'][0]
            message = choice.get('message', {})
            print(f"   完成原因: {choice.get('finish_reason', 'N/A')}")

            if message.get('content'):
                content_preview = message['content'][:150] + '...' if len(message['content']) > 150 else message['content']
                print(f"   响应内容: {content_preview}")

            if message.get('tool_calls'):
                print(f"   工具调用: {len(message['tool_calls'])} 个")
                for tc in message['tool_calls']:
                    print(f"     - {tc.get('function', {}).get('name', 'unknown')}")

        self.current_session["conversations"].append({
            "type": "api_response",
            "timestamp": datetime.now().isoformat(),
            "response_data": response_data
        })

    def log_agent_thinking(self, message: Dict[str, Any]):
        """记录 Agent 思考过程（第一次响应）"""
        print(f"\n🤖 Agent 正在思考...")

        if message.get("content"):
            print(f"   思考内容: {message['content']}")

        self.current_session["conversations"].append({
            "type": "agent_thinking",
            "timestamp": datetime.now().isoformat(),
            "content": message.get("content", ""),
            "model": message.get("model", ""),
            "role": message.get("role", "")
        })

    def log_tool_call(self, tool_call: Dict[str, Any], tool_result: str):
        """记录工具调用详情"""
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)

        print(f"\n🔧 Agent 决定调用工具:")
        print(f"   工具名称: {tool_name}")
        print(f"   工具参数: {json.dumps(tool_args, ensure_ascii=False, indent=6)}")

        # 工具执行（execute_tool 函数内部会打印执行过程）
        print(f"   执行结果: {tool_result[:200]}{'...' if len(tool_result) > 200 else ''}")

        self.current_session["conversations"].append({
            "type": "tool_call",
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_call_id": tool_call.id,
            "tool_result": tool_result
        })

    def log_final_response(self, response_content: str, usage: Dict[str, Any] = None):
        """记录 Agent 最终响应"""
        print(f"\n{'='*60}")
        print(f"✅ Agent 最终回复:")
        print(f"{response_content}")
        print(f"{'='*60}")

        if usage:
            print(f"\n📊 Token 使用情况:")
            print(f"   输入 tokens: {usage.get('prompt_tokens', 'N/A')}")
            print(f"   输出 tokens: {usage.get('completion_tokens', 'N/A')}")
            print(f"   总计 tokens: {usage.get('total_tokens', 'N/A')}")

        self.current_session["conversations"].append({
            "type": "final_response",
            "timestamp": datetime.now().isoformat(),
            "content": response_content,
            "usage": usage
        })

    def save_session(self):
        """保存当前会话到文件"""
        if not config.SAVE_CALL_LOGS:
            return

        self.current_session["end_time"] = datetime.now().isoformat()

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = config.LOG_FILE_FORMAT.format(timestamp=timestamp)
        filepath = os.path.join(config.LOG_DIR, filename)

        # 保存为 JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.current_session, f, ensure_ascii=False, indent=2)

        print(f"\n💾 会话记录已保存到: {filepath}")

    def reset_session(self):
        """重置会话（用于新的对话）"""
        self.current_session = {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "start_time": datetime.now().isoformat(),
            "conversations": []
        }


class DeepSeekAgent:
    """DeepSeek Agent 调用器"""

    def __init__(self):
        # 验证配置
        config.validate()

        # 初始化 OpenAI 客户端（DeepSeek 兼容 OpenAI API）
        self.client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )

        # 初始化日志记录器
        self.logger = AgentCallLogger()

        # 消息历史
        self.messages = [
            {"role": "system", "content": config.SYSTEM_PROMPT}
        ]

        print("✅ DeepSeek Agent 初始化成功")
        print(f"   模型: {config.DEEPSEEK_MODEL}")
        print(f"   可用工具: {len(TOOLS)} 个")
        print(f"   日志目录: {config.LOG_DIR}")

    def call(self, user_input: str) -> str:
        """
        调用 Agent 处理用户输入

        参数:
            user_input (str): 用户输入的问题或指令

        返回:
            str: Agent 的最终回复
        """
        # 记录用户输入
        self.logger.log_user_input(user_input)

        # 添加用户消息到历史
        self.messages.append({
            "role": "user",
            "content": user_input
        })

        # 开始 Agent 调用循环
        for round_num in range(config.MAX_CONVERSATION_ROUNDS):
            print(f"\n🔄 第 {round_num + 1} 轮调用...")

            # 准备请求数据
            request_data = {
                "model": config.DEEPSEEK_MODEL,
                "messages": self.messages,
                "tools": TOOLS,
                "temperature": config.TEMPERATURE,
                "max_tokens": config.MAX_TOKENS
            }

            # 记录请求数据
            self.logger.log_api_request(request_data)

            # 调用 DeepSeek API
            response = self.client.chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=self.messages,
                tools=TOOLS,
                temperature=config.TEMPERATURE,
                max_tokens=config.MAX_TOKENS
            )

            # 将响应转换为字典格式
            response_dict = response.model_dump()

            # 记录原始响应
            self.logger.log_api_response(response_dict)

            # 获取响应消息
            response_message = response.choices[0].message
            usage = response.usage.model_dump() if response.usage else {}

            # 记录 Agent 思考
            self.logger.log_agent_thinking({
                "content": response_message.content,
                "model": response.model,
                "role": response_message.role
            })

            # 检查是否需要调用工具
            if response_message.tool_calls:
                # 添加 assistant 消息到历史
                self.messages.append(response_message)

                # 处理每个工具调用
                for tool_call in response_message.tool_calls:
                    # 解析工具参数
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    # 执行工具
                    tool_result = execute_tool(tool_name, tool_args)

                    # 记录工具调用
                    self.logger.log_tool_call(tool_call, tool_result)

                    # 添加工具结果到消息历史
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": tool_result
                    })

                # 继续下一轮调用，让 Agent 基于工具结果生成最终回复
                continue

            else:
                # 没有工具调用，说明 Agent 已经完成思考
                final_response = response_message.content

                # 记录最终响应
                self.logger.log_final_response(final_response, usage)

                # 添加到消息历史
                self.messages.append({
                    "role": "assistant",
                    "content": final_response
                })

                # 保存会话
                self.logger.save_session()

                return final_response

        # 超过最大轮数
        error_msg = "达到最大对话轮数限制"
        print(f"\n⚠️  {error_msg}")
        self.logger.save_session()
        return error_msg

    def interactive_mode(self):
        """交互式对话模式"""
        print("\n" + "="*60)
        print("🚀 DeepSeek Agent 交互模式")
        print("="*60)
        print("输入 'quit' 或 'exit' 退出")
        print("输入 'clear' 清除对话历史")
        print("="*60 + "\n")

        while True:
            try:
                user_input = input("\n👤 你: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ['quit', 'exit', '退出']:
                    print("\n👋 再见！")
                    break

                if user_input.lower() in ['clear', '清除']:
                    self.messages = [
                        {"role": "system", "content": config.SYSTEM_PROMPT}
                    ]
                    self.logger.reset_session()
                    print("\n✅ 对话历史已清除")
                    continue

                # 调用 Agent
                response = self.call(user_input)

            except KeyboardInterrupt:
                print("\n\n👋 再见！")
                break
            except Exception as e:
                print(f"\n❌ 发生错误: {str(e)}")
                import traceback
                traceback.print_exc()


def main():
    """主函数"""
    # 创建 Agent 实例
    agent = DeepSeekAgent()

    # 进入交互模式
    agent.interactive_mode()


if __name__ == "__main__":
    main()
