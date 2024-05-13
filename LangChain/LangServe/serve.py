# -*- coding: utf-8 -*-


from typing import List

from fastapi import FastAPI
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.schema import BaseOutputParser
from langserve import add_routes

# 定义链
class CommaSeparatedListOutputParser(BaseOutputParser[List[str]]):
    "将LLM的输出内容解析为列表"
    def parse(self, text:str):
        "解析LLM调用的输出"
        return text.strip().split(",")


template = """你是一个能生成以逗号分隔的列表的助手，用户会传入一个类别，你应该生成该类别下的5个对象，并以逗号分隔的形式返回。
只返回以逗号分隔的内容，不要包含其他内容。"""
human_template = "{text}"

chat_prompt = ChatPromptTemplate.from_messages([("system", template),("human", human_template),])
first_chain = chat_prompt | ChatOpenAI() | CommaSeparatedListOutputParser()

# 应用定义
app = FastAPI(title = "第一个LangChain应用", version = "0.0.1", description = "LangChain应用接口",)

# 添加链路由
add_routes(app, first_chain, path="/first_app")
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8000)