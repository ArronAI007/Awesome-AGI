# 第 6 篇：生产级的工程问题——错误处理
# 一个生产级 Agent 的调用链路：
#   用户输入 → Agent 推理 → 调用工具 1 → 解析结果 → 再推理 → 调用工具 2 → 解析结果 → 输出回复
# 这条链上每一环都可能炸：LLM API 不可靠、工具调用三重风险（不存在/参数错/工具本身崩）、
# ReAct 循环超限、大模型输出不可控。本模块把这几个翻车点一个个修掉。
import json
import re
import signal
import time
import traceback
import random
from typing import Any, Callable, Optional

from .memory import MemoryAgent
from .tool_registry import ToolRegistry


# ============================================================
# 翻车点①：LLM API 不可靠——指数退避重试
# ============================================================
def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = (ConnectionError, TimeoutError)
) -> Any:
    """
    指数退避重试：每次失败后等待时间翻倍
    第 1 次失败 → 等 1~2 秒
    第 2 次失败 → 等 2~4 秒
    第 3 次失败 → 等 4~8 秒
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except retryable_exceptions as e:
            last_exception = e
            if attempt == max_retries:
                break

            # 指数退避 + 随机抖动（避免所有重试同时发起）
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.5)
            wait_time = delay + jitter

            print(f"⚠️ 第 {attempt + 1} 次重试失败，{wait_time:.1f}s 后重试... "
                  f"错误: {type(e).__name__}")
            time.sleep(wait_time)

    raise last_exception


# 使用示例
class RobustLLMClient:
    """带重试的 LLM 客户端"""

    def __init__(self, base_client, max_retries: int = 3):
        self.client = base_client
        self.max_retries = max_retries

    def chat(self, messages: list[dict], **kwargs) -> Any:
        def _call():
            # 修正：原文这里直接返回 ChatCompletion 对象，但下游 BoundedReActLoop
            # 把 chat() 的返回值当成已经带 .content / .tool_calls 的消息在用。
            # 真实的 openai SDK 里 .choices[0].message 才是那个对象，这里取出来。
            return self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                **kwargs
            ).choices[0].message

        return retry_with_backoff(
            _call,
            max_retries=self.max_retries,
            retryable_exceptions=(
                ConnectionError,
                TimeoutError,
            )
        )

    def chat_with_fallback(self, messages: list[dict], **kwargs) -> Any:
        """
        多模型 fallback：主模型挂了自动切备选
        """
        model_chain = [
            ("gpt-4o", {}),
            ("claude-3-5-sonnet", {"max_tokens": 4096}),
            ("gpt-4o-mini", {}),  # 最后的保底
        ]

        last_error = None
        for model, extra_kwargs in model_chain:
            try:
                merged = {**kwargs, **extra_kwargs}
                return retry_with_backoff(
                    lambda m=model, mk=merged: self.client.chat.completions.create(
                        model=m, messages=messages, **mk
                    ),
                    max_retries=1  # fallback 时重试少一些
                )
            except Exception as e:
                print(f"⚠️ 模型 {model} 调用失败: {e}")
                last_error = e
                continue

        raise RuntimeError(f"所有模型均调用失败。最后一个错误: {last_error}")


# ============================================================
# 翻车点②③④：工具调用的三重风险——工具不存在 / 参数格式错 / 工具本身崩了
# ============================================================
class SafeToolExecutor:
    """安全的工具执行器：捕获所有异常，永远不会让 Agent 裸奔"""

    def __init__(self, tool_registry):
        self.registry = tool_registry

    def execute(self, tool_name: str, arguments: dict) -> dict:
        """
        执行一个工具调用，永远返回 dict 而不是抛异常。
        返回格式统一为 {"success": bool, "result": Any, "error": Optional[str]}
        """

        # 检查 1：工具是否存在
        tool = self.registry.get(tool_name)
        if tool is None:
            # 修正：ToolRegistry 没有 list_names()，改为从 list_all() 取 name。
            return {
                "success": False,
                "result": None,
                "error": f"工具 '{tool_name}' 不存在。"
                        f"可用工具: {', '.join(t.name for t in self.registry.list_all())}"
            }

        # 检查 2：参数校验
        validated, error_msg = self._validate_args(tool, arguments)
        if not validated:
            return {
                "success": False,
                "result": None,
                "error": f"参数校验失败: {error_msg}"
            }

        # 检查 3：执行 + 异常捕获 + 超时保护
        try:
            result = self._execute_with_timeout(tool, arguments, timeout=30)
            return {"success": True, "result": result, "error": None}
        except TimeoutError:
            return {
                "success": False,
                "result": None,
                "error": f"工具 '{tool_name}' 执行超时（30s）。请简化查询或稍后重试。"
            }
        except Exception as e:
            # 打印完整堆栈到日志，但只把简洁信息返回给 Agent
            traceback.print_exc()
            return {
                "success": False,
                "result": None,
                "error": f"工具 '{tool_name}' 执行失败: {type(e).__name__}: {str(e)[:200]}"
            }

    def _validate_args(self, tool, arguments: dict) -> tuple[bool, Optional[str]]:
        """
        根据工具的 JSON Schema 校验参数
        """
        # 修正：tool 是真实的 Tool 实例，不是 dict，直接取 .parameters 属性。
        schema = tool.parameters
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        # 检查必填参数
        for param in required:
            if param not in arguments or arguments[param] is None:
                return False, f"缺少必填参数: {param}"

        # 检查参数类型
        for param_name, param_value in arguments.items():
            if param_name not in properties:
                continue  # 允许额外参数

            expected_type = properties[param_name].get("type", "string")

            # 简单的类型检查
            type_checks = {
                "string": lambda v: isinstance(v, str),
                "number": lambda v: isinstance(v, (int, float)),
                "integer": lambda v: isinstance(v, int),
                "boolean": lambda v: isinstance(v, bool),
                "array": lambda v: isinstance(v, list),
                "object": lambda v: isinstance(v, dict),
            }

            checker = type_checks.get(expected_type)
            if checker and not checker(param_value):
                return False, (
                    f"参数 '{param_name}' 类型错误: "
                    f"期望 {expected_type}，实际 {type(param_value).__name__}"
                )

        return True, None

    def _execute_with_timeout(self, tool, arguments: dict, timeout: int) -> Any:
        """带超时的工具执行"""

        def _timeout_handler(signum, frame):
            raise TimeoutError(f"工具执行超过 {timeout} 秒")

        # 设置超时（仅在主线程可用）
        # 修正：tool 是真实的 Tool 实例，调用其 .func，不是 dict 里的 "function" 键。
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            result = tool.func(**arguments)
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
            return result
        except AttributeError:
            # 非主线程不支持 signal，改用简单的直接调用
            return tool.func(**arguments)


# ============================================================
# 翻车点⑤：ReAct 循环超限——死循环检测 + 步数/时间熔断
# ============================================================
class BoundedReActLoop:
    """带熔断机制的 ReAct 循环"""

    def __init__(self, max_steps: int = 10, max_same_tool_calls: int = 3, max_total_time: int = 120):
        self.max_steps = max_steps
        self.max_same_tool_calls = max_same_tool_calls  # 同一工具最多连续调用几次
        self.max_total_time = max_total_time  # 总时间上限（秒）

    def run(self, agent, user_input: str) -> dict:
        start_time = time.time()
        tool_call_counts = {}  # 统计每个工具调用次数
        consecutive_same = 0   # 连续调用同一工具的次数
        last_tool = None

        messages = [{"role": "user", "content": user_input}]

        for step in range(self.max_steps):
            # 检查总时间
            elapsed = time.time() - start_time
            if elapsed > self.max_total_time:
                return {
                    "success": False,
                    "result": "任务执行超时，已执行部分步骤。请尝试拆分为更小的任务。",
                    "steps_used": step,
                    "error": "total_timeout"
                }

            # 调用 LLM
            # 修正：ToolRegistry 没有 get_definitions()，用 list_all() + to_openai_schema() 组装。
            response = agent.llm.chat(
                messages,
                tools=[t.to_openai_schema() for t in agent.tools.list_all()]
            )

            # 如果是文本回复（无工具调用），任务完成
            if response.content and not response.tool_calls:
                return {
                    "success": True,
                    "result": response.content,
                    "steps_used": step + 1
                }

            # 处理工具调用
            if response.tool_calls:
                # 修正：response 现在就是消息对象本身（见 RobustLLMClient.chat 的修正），
                # 不再有 .message 这一层。
                messages.append(response)

                for tc in response.tool_calls:
                    # 统计
                    tool_call_counts[tc.name] = tool_call_counts.get(tc.name, 0) + 1

                    # 检测死循环：连续调用同一个工具太多次
                    if tc.name == last_tool:
                        consecutive_same += 1
                    else:
                        consecutive_same = 1
                        last_tool = tc.name

                    if consecutive_same > self.max_same_tool_calls:
                        return {
                            "success": False,
                            "result": (
                                f"检测到连续 {consecutive_same} 次调用 '{tc.name}'，可能陷入死循环。"
                                f"已为你中断。请尝试换一种方式描述你的需求。"
                            ),
                            "steps_used": step + 1,
                            "error": "loop_detected"
                        }

                    # 安全执行工具
                    result = agent.safe_executor.execute(tc.name, tc.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })

        return {
            "success": False,
            "result": (
                f"任务已达到最大步数限制（{self.max_steps} 步），"
                f"已完成部分工作。请尝试拆分任务或简化需求。"
                f"\n\n工具调用统计: {json.dumps(tool_call_counts, ensure_ascii=False)}"
            ),
            "steps_used": self.max_steps,
            "error": "max_steps_reached"
        }


# ============================================================
# 翻车点⑥：大模型输出不可控——结构化输出 + 降级处理
# ============================================================
class ResponseValidator:
    """响应校验 + 修复 + 降级"""

    @staticmethod
    def extract_json(text: str) -> dict:
        """
        从 LLM 返回的文本中提取 JSON。
        LLM 经常在 JSON 前后加废话，比如：
        "好的，这是结果：\n```json\n{...}\n```\n希望对你有帮助"
        """
        # 尝试 1：直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试 2：提取 ```json ... ``` 代码块
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试 3：提取第一个 { ... } 块
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # 全挂了
        raise ValueError(f"无法从 LLM 回复中提取 JSON: {text[:200]}...")

    @staticmethod
    def validate_final_response(response: str, min_length: int = 10) -> tuple[bool, str]:
        """
        检查最终回复是否可用
        """
        # 太短
        if len(response.strip()) < min_length:
            return False, "回复过短，可能不完整"

        # 包含明显的错误标记
        error_markers = [
            "I apologize", "I'm sorry", "as an AI",
            "我不能", "我无法", "抱歉，我"
        ]
        for marker in error_markers:
            if marker in response and len(response) < 100:
                return False, f"回复包含错误标记: {marker}"

        # 全是乱码/重复字符
        unique_chars = len(set(response[:100]))
        if unique_chars < 5 and len(response) > 20:
            return False, "回复疑似乱码"

        return True, "ok"


class GracefulAgent:
    """带降级策略的 Agent"""

    def chat(self, user_input: str) -> str:
        try:
            # 正常流程
            result = self.bounded_loop.run(self, user_input)

            if result["success"]:
                # 校验回复质量
                valid, reason = ResponseValidator.validate_final_response(result["result"])
                if valid:
                    return result["result"]
                else:
                    return self._degraded_response(user_input, f"回复质量异常: {reason}")
            else:
                return self._degraded_response(user_input, result["error"])

        except Exception as e:
            traceback.print_exc()
            return self._degraded_response(user_input, str(e))

    def _degraded_response(self, user_input: str, error_info: str) -> str:
        """
        降级回复：当所有流程都失败时的保底策略
        """
        return (
            f"抱歉，处理你的请求时遇到了一些问题。\n\n"
            f"你可以尝试：\n"
            f"1. 换一种更简单的说法重新描述需求\n"
            f"2. 把任务拆成几个小步骤分别处理\n"
            f"3. 稍后再试\n\n"
            f"（错误信息: {error_info[:100]}）"
        )


# ============================================================
# 1.6 完整的错误处理架构——把上面的代码拼起来
# ============================================================
class ProductionAgent:
    """
    整合了所有错误处理机制的生产级 Agent
    """

    def __init__(self, llm_client, tool_registry):
        # 带重试和 fallback 的 LLM 客户端
        self.llm = RobustLLMClient(llm_client)

        # 安全的工具执行器
        self.safe_executor = SafeToolExecutor(tool_registry)

        # 工具注册表
        self.tools = tool_registry

        # 带熔断的 ReAct 循环
        self.bounded_loop = BoundedReActLoop(
            max_steps=10,
            max_same_tool_calls=3,
            max_total_time=120
        )

        # 记忆系统（第 5 篇）
        self.memory = MemoryAgent(llm_client, tool_registry)

        # 响应校验器
        self.validator = ResponseValidator()

    def _build_system_prompt(self, long_term_memories: list[dict]) -> str:
        # 修正：原文调用了 self._build_system_prompt(...) 但从未定义它（这个方法
        # 缺失会导致 chat() 一进来就 AttributeError）。复用第 5 篇 MemoryAgent 已有的
        # 上下文拼装逻辑，和原文一样——这里只是把变量算出来，没有真的接入
        # bounded_loop（原文自己也没接），保留这个已知局限而不是顺手扩大改动范围。
        return self.memory._build_context(long_term_memories)

    def chat(self, user_input: str) -> str:
        # 最外层兜底
        try:
            # 检索记忆
            relevant = self.memory.long_term.search(user_input, top_k=3)

            # 构建 system prompt
            system_prompt = self._build_system_prompt(relevant)

            # 执行带熔断的 ReAct 循环
            result = self.bounded_loop.run(self, user_input)

            if result["success"]:
                # 校验回复
                valid, reason = self.validator.validate_final_response(result["result"])
                if valid:
                    # 更新记忆
                    self.memory.short_term.add("user", user_input)
                    self.memory.short_term.add("assistant", result["result"])
                    return result["result"]

            # 降级回复
            return GracefulAgent._degraded_response(None, user_input, result.get("error", "unknown"))

        except Exception as e:
            traceback.print_exc()
            return GracefulAgent._degraded_response(None, user_input, str(e))
