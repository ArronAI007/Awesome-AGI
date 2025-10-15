import json
from json.decoder import JSONDecodeError
import openai
import tiktoken
from config import config
from prompts import SYSTEM_PROMPT_REPORT_STRUCTURE, SYSTEM_PROMPT_FIRST_SEARCH, SYSTEM_PROMPT_FIRST_SUMMARY, \
    SYSTEM_PROMPT_REFLECTION, SYSTEM_PROMPT_REPORT_FORMATTING, SYSTEM_PROMPT_REFLECTION_SUMMARY, get_prompt
from state import State, Paragraph, Research, Search
from utils import clean_json_tags, remove_reasoning_from_output, clean_markdown_tags


def truncate_message(message, max_tokens=40000):
    """
    截断消息以确保不超过token限制
    使用tiktoken库精确计算token数量
    """
    try:
        # 根据模型选择合适的编码器
        encoding = tiktoken.get_encoding("cl100k_base")
        # 计算消息的token数量
        tokens = encoding.encode(message)
        token_count = len(tokens)
        
        if token_count > max_tokens:
            # 如果超过最大token数，截断到最大token数
            truncated_tokens = tokens[:max_tokens]
            return encoding.decode(truncated_tokens) + "... [内容因长度限制被截断]"
        return message
    except Exception as e:
        # 如果tiktoken出错，回退到原来的字符估算方法
        print(f"Tiktoken error: {e}, falling back to character estimation")
        char_limit = max_tokens * 4
        if len(message) > char_limit:
            return message[:char_limit] + "... [内容因长度限制被截断]"
        return message


class ReportStructureAgent:

    def __init__(self, query: str):
        self.openai_client = openai.OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )
        self.query = query

    def run(self) -> str:
        truncated_query = truncate_message(self.query)
        response = self.openai_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL_REASON,
            messages=[{"role": "system", "content": get_prompt(SYSTEM_PROMPT_REPORT_STRUCTURE, truncated_query)},
                      {"role": "user", "content": truncated_query}]
        )
        return response.choices[0].message.content

    def mutate_state(self, state: State) -> State:
        report_structure = self.run()
        report_structure = remove_reasoning_from_output(report_structure)
        report_structure = clean_json_tags(report_structure)

        report_structure = json.loads(report_structure)

        for paragraph in report_structure:
            state.paragraphs.append(Paragraph(title=paragraph["title"], content=paragraph["content"]))

        return state


class FirstSearchAgent:

    def __init__(self):
        self.openai_client = openai.OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )

    def run(self, message) -> str:
        truncated_message = truncate_message(message)
        response = self.openai_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL_CHAT,
            messages=[{"role": "system", "content": get_prompt(SYSTEM_PROMPT_FIRST_SEARCH, truncated_message)},
                      {"role": "user", "content": truncated_message}]
        )

        response = remove_reasoning_from_output(response.choices[0].message.content)
        response = clean_json_tags(response)

        response = json.loads(response)

        return response


class FirstSummaryAgent:

    def __init__(self):

        self.openai_client = openai.OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )

    def run(self, message) -> str:
        truncated_message = truncate_message(message)
        response = self.openai_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL_CHAT,
            messages=[{"role": "system", "content": get_prompt(SYSTEM_PROMPT_FIRST_SUMMARY, truncated_message)},
                      {"role": "user", "content": truncated_message}]
        )
        return response.choices[0].message.content

    def mutate_state(self, message: str, idx_paragraph: int, state: State) -> State:
        summary = self.run(message)
        summary = remove_reasoning_from_output(summary)
        summary = clean_json_tags(summary)

        try:
            summary = json.loads(summary)
        except JSONDecodeError:
            summary = {"paragraph_latest_state": summary}

        state.paragraphs[idx_paragraph].research.latest_summary = summary["paragraph_latest_state"]

        return state


class ReflectionAgent:

    def __init__(self):
        self.openai_client = openai.OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )

    def run(self, message) -> str:
        truncated_message = truncate_message(message)
        response = self.openai_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL_CHAT,
            messages=[{"role": "system", "content": get_prompt(SYSTEM_PROMPT_REFLECTION, truncated_message)},
                      {"role": "user", "content": truncated_message}]
        )

        response = remove_reasoning_from_output(response.choices[0].message.content)
        response = clean_json_tags(response)
        response = json.loads(response)

        return response


class ReflectionSummaryAgent:

    def __init__(self):

        self.openai_client = openai.OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )

    def run(self, message) -> str:
        truncated_message = truncate_message(message)
        response = self.openai_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL_CHAT,
            messages=[{"role": "system", "content": get_prompt(SYSTEM_PROMPT_REFLECTION_SUMMARY, truncated_message)},
                      {"role": "user", "content": truncated_message}]
        )
        return response.choices[0].message.content

    def mutate_state(self, message: str, idx_paragraph: int, state: State) -> State:

        summary = self.run(message)
        summary = remove_reasoning_from_output(summary)
        summary = clean_json_tags(summary)

        try:
            summary = json.loads(summary)
        except JSONDecodeError:
            summary = {"updated_paragraph_latest_state": summary}

        state.paragraphs[idx_paragraph].research.latest_summary = summary["updated_paragraph_latest_state"]

        return state


class ReportFormattingAgent:

    def __init__(self):
        self.openai_client = openai.OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL
        )

    def run(self, message) -> str:
        truncated_message = truncate_message(message)
        response = self.openai_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL_REASON,
            messages=[{"role": "system", "content": get_prompt(SYSTEM_PROMPT_REPORT_FORMATTING, truncated_message)},
                      {"role": "user", "content": truncated_message}]
        )
        summary = response.choices[0].message.content
        summary = remove_reasoning_from_output(summary)
        summary = clean_markdown_tags(summary)

        return summary