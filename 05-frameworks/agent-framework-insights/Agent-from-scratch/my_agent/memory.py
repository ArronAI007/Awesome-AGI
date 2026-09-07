"""Agent 的记忆系统——记住你说了什么、做到哪了、什么改了。

三层记忆模型：
- 第一层：短期记忆（Short-term Memory）—— 当前对话的完整历史，存在 token 窗口内。
- 第二层：长期记忆（Long-term Memory）—— 跨会话的重要信息，存在向量数据库里。
- 第三层：工作记忆（Working Memory）—— 当前任务的中间状态，存在 scratchpad 里。
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions


# ============================================================
# 第一层：短期记忆——管好对话历史
# ============================================================


class ShortTermMemory:
    """最基本的短期记忆：一个消息列表"""

    def __init__(self):
        self.messages: list[dict] = []

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})

    def get_all(self) -> list[dict]:
        return self.messages

    def clear(self):
        self.messages = []


class SlidingWindowMemory:
    """滑动窗口：只保留最近 N 条消息"""

    def __init__(self, max_messages: int = 20):
        self.messages: list[dict] = []
        self.max_messages = max_messages

    def add(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        # 超出窗口就砍掉最老的
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def get_all(self) -> list[dict]:
        return self.messages


class SummarizingMemory:
    """滑动窗口 + 自动摘要：老消息压缩后保留"""

    def __init__(self, max_recent: int = 20, summary_interval: int = 15):
        self.full_messages: list[dict] = []      # 完整消息（近期的）
        self.summary: str = ""                    # 老消息的摘要
        self.max_recent = max_recent
        self.summary_interval = summary_interval

    def add(self, role: str, content: str):
        self.full_messages.append({"role": role, "content": content})

        # 当消息累积到一定数量，触发摘要
        if len(self.full_messages) >= self.max_recent + self.summary_interval:
            self._summarize_oldest()

    def _summarize_oldest(self, llm_client=None):
        """把最老的 N 条消息压缩成摘要，加入已有摘要中"""
        # 取出要被压缩的消息
        to_summarize = self.full_messages[:self.summary_interval]
        self.full_messages = self.full_messages[self.summary_interval:]

        # 构建摘要文本
        dialog_text = "\n".join(
            f"[{m['role']}]: {m['content'][:200]}" for m in to_summarize
        )

        # 调用大模型做摘要（这里用伪代码示意，实际调用你的 LLM）
        summary_prompt = f"""请用 2-3 句话总结以下对话的关键信息。只保留对后续对话有用的内容（决定、数据、偏好、待办事项）。

已有历史摘要：{self.summary if self.summary else '（无）'}

新对话：
{dialog_text}

请输出更新后的完整摘要："""

        # new_summary = llm_client.chat(summary_prompt)  # 实际调用
        new_summary = f"[摘要] 用户提到了{dialog_text[:50]}..."
        self.summary = new_summary

    def get_context(self) -> str:
        """返回组装好的上下文：摘要 + 最近消息"""
        parts = []
        if self.summary:
            parts.append(f"## 之前的对话摘要\n{self.summary}\n")
        parts.append("## 最近的对话")
        for m in self.full_messages[-self.max_recent:]:
            parts.append(f"[{m['role']}]: {m['content']}")
        return "\n".join(parts)

    def get_messages_for_llm(self) -> list[dict]:
        """返回可直接发给 LLM 的消息列表"""
        messages = []
        if self.summary:
            messages.append({
                "role": "system",
                "content": f"以下是之前对话的摘要，请结合这些信息回复用户：\n{self.summary}"
            })
        messages.extend(self.full_messages[-self.max_recent:])
        return messages


# ============================================================
# 第二层：长期记忆——跨会话记住你
# ============================================================


class LongTermMemory:
    """长期记忆：基于向量数据库的语义存储和检索"""

    def __init__(self, collection_name: str = "agent_memory"):
        # 初始化 ChromaDB 客户端（数据存在本地文件）。
        # 修正：原文写的是 "./agent_memory_db"（相对当前工作目录）。这里改成相对
        # 本文件所在目录，这样不管从哪里启动 main.py，数据库都落在 my_agent/
        # 下面，和项目目录树里画的 agent_memory_db/ 位置对得上。
        db_path = Path(__file__).resolve().parent / "agent_memory_db"
        self.client = chromadb.PersistentClient(path=str(db_path))

        # 使用轻量级的 Embedding 模型（免费、本地运行）
        self.embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"  # 80MB，启动快，够用
        )

        # 获取或创建 collection（相当于数据库的一张表）
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}  # 用余弦相似度
        )

    def store(self, content: str, metadata: dict = None, memory_id: str = None):
        """存一条记忆"""
        if memory_id is None:
            memory_id = f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        if metadata is None:
            metadata = {}

        metadata.update({
            "timestamp": datetime.now().isoformat(),
            "content_preview": content[:100]
        })

        self.collection.add(
            documents=[content],        # 要被 Embedding 的文本
            metadatas=[metadata],       # 附带信息（时间、类型等）
            ids=[memory_id]             # 唯一 ID
        )

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """语义检索：找到最相关的记忆"""
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )

        # 整理返回格式
        memories = []
        if results['ids'] and results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                memories.append({
                    "id": doc_id,
                    "content": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "distance": results['distances'][0][i] if results['distances'] else None
                })

        return memories

    def search_by_metadata(self, key: str, value: str) -> list[dict]:
        """按元数据精确查找（比如找某个项目的所有记忆）"""
        results = self.collection.get(
            where={key: value}
        )
        memories = []
        if results['ids']:
            for i, doc_id in enumerate(results['ids']):
                memories.append({
                    "id": doc_id,
                    "content": results['documents'][i],
                    "metadata": results['metadatas'][i]
                })
        return memories

    def delete(self, memory_id: str):
        """删除一条记忆"""
        self.collection.delete(ids=[memory_id])

    def count(self) -> int:
        """记忆总数"""
        return self.collection.count()


# 一股脑把所有东西塞进向量数据库是不行的。给记忆打标签（type 字段），检索时加过滤。


class TypedMemory:
    """带类型过滤的长期记忆"""

    MEMORY_TYPES = {
        "user_profile": "用户画像：名字、角色、偏好、习惯",
        "project": "项目信息：名称、目标、进度、关键决策",
        "task": "任务记录：已完成的任务、中间结果",
        "knowledge": "知识：用户教给 Agent 的事实、规则",
        "preference": "偏好：用户喜欢怎么做事、不喜欢什么"
    }

    def __init__(self, base_memory: LongTermMemory):
        self.memory = base_memory

    def store(self, content: str, mem_type: str, **extra_meta):
        if mem_type not in self.MEMORY_TYPES:
            raise ValueError(f"未知记忆类型: {mem_type}，可选: {list(self.MEMORY_TYPES.keys())}")
        metadata = {"type": mem_type, **extra_meta}
        self.memory.store(content, metadata)

    def search(self, query: str, mem_type: str = None, top_k: int = 5) -> list[dict]:
        """检索记忆，可选按类型过滤"""
        if mem_type:
            # 先做语义检索，再按类型过滤
            results = self.memory.search(query, top_k=top_k * 2)  # 多取一些再过滤
            return [r for r in results if r['metadata'].get('type') == mem_type][:top_k]
        return self.memory.search(query, top_k)

    # ---- 以下为第七节「生产环境中你还需要考虑的事」的加固方法 ----

    def search_with_decay(self, query: str, top_k: int = 5) -> list[dict]:
        """检索时给老记忆降权"""
        results = self.memory.search(query, top_k=top_k * 2)

        scored = []
        for r in results:
            # 计算记忆的"年龄"
            timestamp = r['metadata'].get('timestamp', '')
            age_days = self._days_since(timestamp)

            # 衰减因子：7 天半衰期
            decay = 0.5 ** (age_days / 7)

            # 得分 = 语义相似度（距离越小越好） × 衰减因子
            distance = r.get('distance', 0.5)
            final_score = (1 - min(distance, 1)) * decay
            scored.append((final_score, r))

        # 按最终得分排序
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    def safe_store(self, content: str, metadata: dict = None):
        """在 store 之前检查敏感信息"""
        if contains_sensitive_info(content):
            print("⚠️ 检测到敏感信息，跳过存储")
            return
        self.memory.store(content, metadata)

    def cleanup_old_memories(self, days: int = 90):
        """删除 N 天前的记忆（策略 1：定时清理）"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        # ChromaDB 的 where 过滤
        # 注：原文用 self.collection，这里改为 self.memory.collection——
        # TypedMemory 本身没有 collection 属性，底层的 LongTermMemory 才有。
        results = self.memory.collection.get()
        to_delete = []
        for i, meta in enumerate(results['metadatas']):
            if meta.get('timestamp', '') < cutoff:
                to_delete.append(results['ids'][i])
        if to_delete:
            self.memory.collection.delete(ids=to_delete)

    def deduplicate(self, threshold: float = 0.95):
        """删除相似度过高的重复记忆（策略 2：去重）"""
        # 注：同上，改为 self.memory.collection 以匹配 LongTermMemory 的实际结构。
        all_memories = self.memory.collection.get()
        # 两两比较相似度……实际实现略复杂
        # 核心思路：同一个 content 的 Embedding 距离 < threshold 就删掉一条
        pass


# 什么时候存记忆？一个实用的"重要性判断"规则：

IMPORTANCE_TRIGGERS = [
    "记住", "别忘了", "以后", "下次",
    "我偏好", "我不喜欢", "我喜欢",
    "项目", "计划", "目标",
    "决定了", "确定了", "确认一下",
]


def should_remember(user_message: str, agent_response: str) -> bool:
    """判断一条交互是否值得存入长期记忆"""
    combined = user_message + agent_response

    # 规则 1：包含明确的关键词
    if any(trigger in combined for trigger in IMPORTANCE_TRIGGERS):
        return True

    # 规则 2：消息超过一定长度（通常包含更多信息）
    if len(user_message) > 50:
        return True

    # 规则 3：包含具体数据（数字、日期、名称）
    has_numbers = bool(re.search(r'\d+', user_message))
    has_date = bool(re.search(r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?', user_message))
    if has_numbers or has_date:
        return True

    return False


def auto_remember(user_message: str, agent_response: str, memory: TypedMemory):
    """自动判断并存入长期记忆"""
    if should_remember(user_message, agent_response):
        # 让 LLM 提取关键信息而不是直接存原始对话
        summary_prompt = f"""请从以下对话中提取值得长期记住的信息。用一句简洁的话概括。
如果用户表达了偏好、习惯、个人特征，请标注为 user_profile。
如果涉及项目、计划、目标，请标注为 project。
如果是具体任务或数据，请标注为 task。

用户: {user_message}
助手: {agent_response}

输出格式（JSON）：
{{"type": "user_profile|project|task|knowledge|preference", "content": "一句话概括"}}
"""
        # result = json.loads(llm_client.chat(summary_prompt))  # 实际调用
        # memory.store(result['content'], result['type'])

        # 简化版：直接存
        memory.store(
            content=f"用户: {user_message[:200]}\n助手: {agent_response[:200]}",
            mem_type="task"
        )


# 隐私：什么不该记。密码、银行卡号、私密对话——这些不该进向量数据库。

SENSITIVE_PATTERNS = [
    r'\b\d{16,19}\b',           # 银行卡号
    r'密码[：:]\s*\S+',          # 密码
    r'\b\d{6}(19|20)\d{8}\d{3}[\dXx]\b',  # 身份证号
    r'1[3-9]\d{9}',             # 手机号
]


def contains_sensitive_info(text: str) -> bool:
    return any(re.search(p, text) for p in SENSITIVE_PATTERNS)


# ============================================================
# 第三层：工作记忆——多步任务不迷路
# ============================================================


@dataclass
class TaskStep:
    """一个任务步骤"""
    description: str
    status: str = "pending"  # pending | in_progress | done | failed
    result: Any = None


@dataclass
class WorkingMemory:
    """工作记忆：结构化的任务便签本"""

    task: str = ""                          # 当前任务描述
    steps: list[TaskStep] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)  # 关键发现
    current_step: int = 0                   # 当前在第几步

    def start_task(self, task: str, planned_steps: list[str]):
        """开始一个新任务"""
        self.task = task
        self.steps = [TaskStep(description=s) for s in planned_steps]
        self.findings = []
        self.current_step = 0

    def mark_step_done(self, result: Any = None):
        """标记当前步骤完成，记录结果"""
        if self.current_step < len(self.steps):
            self.steps[self.current_step].status = "done"
            self.steps[self.current_step].result = result
            self.current_step += 1

    def mark_step_failed(self, error: str):
        """标记当前步骤失败"""
        if self.current_step < len(self.steps):
            self.steps[self.current_step].status = "failed"
            self.steps[self.current_step].result = f"失败: {error}"

    def add_finding(self, finding: str):
        """添加一个关键发现"""
        self.findings.append(finding)

    def to_prompt(self) -> str:
        """生成可注入 system prompt 的工作记忆摘要"""
        if not self.task:
            return "（当前无进行中的任务）"

        lines = [
            f"## 工作记忆",
            f"当前任务：{self.task}",
            f"进度：{self.current_step}/{len(self.steps)} 步完成",
            "",
            "步骤状态：",
        ]

        for i, step in enumerate(self.steps):
            icon = {"pending": "⬜", "done": "✅", "failed": "❌", "in_progress": "🔄"}
            result_str = f" → {str(step.result)[:80]}" if step.result else ""
            lines.append(f"  {icon.get(step.status, '⬜')} {step.description}{result_str}")

        if self.findings:
            lines.append("")
            lines.append("关键发现：")
            for f in self.findings:
                lines.append(f"  • {f}")

        return "\n".join(lines)

    def clear(self):
        """清空工作记忆"""
        self.task = ""
        self.steps = []
        self.findings = []
        self.current_step = 0


# ============================================================
# 六、三层联动：一个完整的记忆 Agent
# ============================================================
# 把三段代码拼起来，就是一个带完整记忆系统的 Agent。


class MemoryAgent:
    """三层记忆的完整 Agent"""

    def __init__(self, llm_client, tools):
        self.llm = llm_client
        self.tools = tools

        # 短期记忆：滑动窗口 + 摘要
        self.short_term = SummarizingMemory(max_recent=20, summary_interval=15)

        # 长期记忆：向量数据库
        base_memory = LongTermMemory(collection_name="my_agent")
        self.long_term = TypedMemory(base_memory)

        # 工作记忆：结构化便签
        self.working = WorkingMemory()

    def chat(self, user_input: str) -> str:
        """一次对话交互"""

        # 1. 如果是新任务，尝试规划步骤
        if self._is_new_task(user_input):
            plan = self._plan_steps(user_input)
            self.working.start_task(user_input, plan)

        # 2. 检索相关长期记忆
        relevant = self.long_term.search(user_input, top_k=3)

        # 3. 组装上下文
        system_prompt = self._build_context(relevant)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.short_term.get_messages_for_llm())
        messages.append({"role": "user", "content": user_input})

        # 4. 调用 LLM（带 ReAct 循环）
        final_response = self._react_loop(messages)

        # 5. 更新记忆
        self.short_term.add("user", user_input)
        self.short_term.add("assistant", final_response)
        self._maybe_store_long_term(user_input, final_response)

        return final_response

    def _is_new_task(self, user_input: str) -> bool:
        """判断是否是新任务（简单启发式）"""
        task_keywords = ["帮我", "分析", "整理", "生成", "对比", "查询", "查一下"]
        return any(kw in user_input for kw in task_keywords)

    def _plan_steps(self, user_input: str) -> list[str]:
        """让 LLM 拆解任务步骤"""
        prompt = f"""请将以下任务拆解为 3-5 个步骤，每步一句话。
只输出步骤列表，每行一个步骤，不要编号。

任务：{user_input}

步骤："""

        response = self.llm.chat([{"role": "user", "content": prompt}])
        steps = [s.strip("- ").strip() for s in response.split("\n") if s.strip()]
        return steps[:5]  # 最多 5 步

    def _build_context(self, long_term_memories: list[dict]) -> str:
        """构建 system prompt"""
        parts = ["你是一个有记忆的智能助理。"]

        # 注入长期记忆
        if long_term_memories:
            parts.append("\n## 你可能需要知道的历史信息")
            for mem in long_term_memories:
                parts.append(f"- {mem['content'][:200]}")

        # 注入工作记忆
        parts.append("\n" + self.working.to_prompt())

        # 注入工具
        parts.append("\n你有以下工具可用，根据需要调用。")

        return "\n".join(parts)

    def _react_loop(self, messages: list[dict], max_steps: int = 10) -> str:
        """带工具的 ReAct 循环"""
        for _ in range(max_steps):
            response = self.llm.chat(
                messages,
                tools=self.tools.get_definitions()  # 从 ToolRegistry 获取工具定义
            )

            if response.content and not response.tool_calls:
                return response.content

            if response.tool_calls:
                messages.append(response.message)
                for tc in response.tool_calls:
                    result = self.tools.execute(tc.name, tc.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(result)
                    })
                    # 更新工作记忆
                    self.working.add_finding(
                        f"{tc.name}: {str(result)[:100]}"
                    )
                    # 标记步骤完成
                    self.working.mark_step_done(str(result)[:100])

        return "任务步骤较多，已完成部分工作。请告诉我接下来要做什么。"

    def _maybe_store_long_term(self, user_input: str, response: str):
        """自动判断是否存入长期记忆"""
        if should_remember(user_input, response):
            # 用 LLM 提取关键信息
            extract_prompt = f"""从以下对话中提取值得长期记住的信息。输出 JSON 格式：
{{"type": "task|project|user_profile|knowledge|preference", "content": "简洁的一句话"}}

用户: {user_input}
助手: {response}"""

            try:
                extract_result = self.llm.chat([
                    {"role": "user", "content": extract_prompt}
                ])
                # 尝试解析 JSON
                info = json.loads(extract_result)
                self.long_term.store(info['content'], info['type'])
            except:
                # 解析失败就粗存
                self.long_term.store(
                    content=f"用户: {user_input[:200]}",
                    mem_type="task"
                )

# === 使用示例 ===

# from openai import OpenAI
# client = OpenAI()
# tools = ToolRegistry()  # 第 4 篇的 ToolRegistry
# tools.register(weather_tool)
# tools.register(email_tool)

# agent = MemoryAgent(llm_client=client, tools=tools)

# # 第一次对话
# agent.chat("我叫张三，是市场部负责人")
# agent.chat("帮我追踪凤凰计划的项目进度")

# # 三天后，新对话
# agent.chat("上次那个凤凰计划进展怎么样了？")
# # → Agent 从长期记忆中检索到"凤凰计划"，能接上话
