import streamlit as st
import json
import time
from datetime import datetime
import os

from agents import (
    ReportStructureAgent, FirstSearchAgent, FirstSummaryAgent, 
    ReflectionAgent, ReflectionSummaryAgent, ReportFormattingAgent
)
from state import State, Paragraph
from utils import tavily_search, update_state_with_search_results
from language_utils import detect_language
from dotenv import load_dotenv

load_dotenv()

# 页面配置
st.set_page_config(
    page_title="Deep Research Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Constants ---
NUM_REFLECTIONS = 2
NUM_RESULTS_PER_SEARCH = 3
CAP_SEARCH_LENGTH = 20000

def run_research_pipeline(topic: str):
    """执行完整的深度研究流程"""
    
    # 初始化状态
    STATE = State()
    
    st.write(f"开始研究任务: {topic}")
    
    # 检测输入语言
    lang = detect_language(topic)
    st.write(f"检测到的语言: {lang}")

    # 1. 生成报告结构
    with st.status("步骤1: 生成报告结构...", expanded=True) as status:
        try:
            report_structure_agent = ReportStructureAgent(topic)
            STATE = report_structure_agent.mutate_state(STATE)
            status.update(label="报告结构生成完成!", state="complete", expanded=False)
        except Exception as e:
            status.update(label=f"生成报告结构失败: {e}", state="error")
            return

    st.info(f"报告结构生成完成，共{len(STATE.paragraphs)}个段落")
    with st.expander("查看报告大纲"):
        for i, p in enumerate(STATE.paragraphs):
            st.markdown(f"**{i+1}. {p.title}**")
            st.write(p.content)

    # 初始化各个Agent
    first_search_agent = FirstSearchAgent()
    first_summary_agent = FirstSummaryAgent()
    reflection_agent = ReflectionAgent()
    reflection_summary_agent = ReflectionSummaryAgent()
    report_formatting_agent = ReportFormattingAgent()

    # 2. 处理每个段落
    for j in range(len(STATE.paragraphs)):
        paragraph_title = STATE.paragraphs[j].title
        st.markdown(f"--- ")
        st.header(f"正在研究段落 {j + 1}/{len(STATE.paragraphs)}: {paragraph_title}")

        with st.container():
            # 2.1 首次搜索
            with st.status(f"段落 {j + 1}: 首次搜索...", expanded=True) as status:
                try:
                    message = json.dumps({"title": STATE.paragraphs[j].title, "content": STATE.paragraphs[j].content})
                    output = first_search_agent.run(message)
                    search_query = output.get('search_query', 'N/A')
                    st.write(f"🔍 搜索查询: {search_query}")
                    
                    search_results = tavily_search(search_query, max_results=NUM_RESULTS_PER_SEARCH)
                    STATE = update_state_with_search_results(search_results, j, STATE)
                    status.update(label="首次搜索完成!", state="complete", expanded=False)
                except Exception as e:
                    status.update(label=f"首次搜索失败: {e}", state="error")
                    continue

            # 2.2 首次总结
            with st.status(f"段落 {j + 1}: 首次总结...", expanded=True) as status:
                try:
                    message = {
                        "title": STATE.paragraphs[j].title,
                        "content": STATE.paragraphs[j].content,
                        "search_query": search_results["query"],
                        "search_results": [result["raw_content"][0:CAP_SEARCH_LENGTH] for result in search_results["results"] if result["raw_content"]]
                    }
                    STATE = first_summary_agent.mutate_state(message=json.dumps(message), idx_paragraph=j, state=STATE)
                    status.update(label="首次总结完成!", state="complete", expanded=False)
                except Exception as e:
                    status.update(label=f"首次总结失败: {e}", state="error")
                    continue
            
            with st.expander("查看首次总结"):
                st.write(STATE.paragraphs[j].research.latest_summary)

            # 2.3 反思迭代
            for i in range(NUM_REFLECTIONS):
                with st.status(f"段落 {j + 1}: 反思迭代 {i + 1}/{NUM_REFLECTIONS}...", expanded=True) as status:
                    try:
                        message = {"paragraph_latest_state": STATE.paragraphs[j].research.latest_summary,
                                   "title": STATE.paragraphs[j].title,
                                   "content": STATE.paragraphs[j].content}
                        output = reflection_agent.run(message=json.dumps(message))
                        reflection_query = output.get('search_query', 'N/A')
                        st.write(f"🤔 反思与搜索: {reflection_query}")

                        search_results = tavily_search(reflection_query)
                        STATE = update_state_with_search_results(search_results, j, STATE)

                        message = {
                            "title": STATE.paragraphs[j].title,
                            "content": STATE.paragraphs[j].content,
                            "search_query": search_results["query"],
                            "search_results": [result["raw_content"][0:20000] for result in search_results["results"] if result["raw_content"]],
                            "paragraph_latest_state": STATE.paragraphs[j].research.latest_summary
                        }
                        STATE = reflection_summary_agent.mutate_state(message=json.dumps(message), idx_paragraph=j, state=STATE)
                        status.update(label=f"反思迭代 {i + 1} 完成!", state="complete", expanded=False)
                    except Exception as e:
                        status.update(label=f"反思迭代 {i + 1} 失败: {e}", state="error")
                        continue
                
                with st.expander(f"查看第 {i+1} 次反思后的总结"):
                    st.write(STATE.paragraphs[j].research.latest_summary)

    # 3. 生成最终报告
    st.header("生成最终报告")
    with st.spinner("正在汇总所有信息并生成最终报告..."):
        try:
            report_data = [{"title": paragraph.title, "paragraph_latest_state": paragraph.research.latest_summary} for paragraph in STATE.paragraphs]
            final_report = report_formatting_agent.run(json.dumps(report_data))
        except Exception as e:
            st.error(f"生成最终报告失败: {e}")
            return

    st.success("研究任务完成!")
    st.balloons()

    # 4. 显示并保存最终报告
    st.header("最终研究报告")
    st.markdown(final_report)

    try:
        # 保存最终报告
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        os.makedirs('reports', exist_ok=True)
        report_filename = f"reports/report_{timestamp}.md"
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(final_report)
        st.sidebar.success(f"报告已保存到: {report_filename}")
    except Exception as e:
        st.sidebar.error(f"保存报告失败: {e}")

# --- Streamlit UI ---
st.title("Deep Research Agent 🔍")
st.sidebar.header("关于")
st.sidebar.info(
    "这是一个使用LLM进行深度研究的AI代理。它会根据您的查询，" 
    "自动生成报告大纲、搜索信息、进行多轮反思，并最终生成一份详细的研究报告。"
)

st.sidebar.header("设置")
# QUERY = st.sidebar.text_input("研究主题", value="请帮我生成一份检索增强生成RAG的综述")

with st.form("research_form"):
    topic = st.text_input("请输入您的研究主题", placeholder="例如：RAG技术的最新进展")
    submitted = st.form_submit_button("开始研究")

if submitted and topic:
    run_research_pipeline(topic)
elif submitted:
    st.warning("请输入一个研究主题！")
