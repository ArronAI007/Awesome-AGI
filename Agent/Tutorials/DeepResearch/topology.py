import json
import argparse
import logging
import os

from agents import ReportStructureAgent, FirstSearchAgent, FirstSummaryAgent, ReflectionAgent, ReflectionSummaryAgent, \
    ReportFormattingAgent
from state import State
from utils import tavily_search, update_state_with_search_results
from language_utils import detect_language

from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 确保必要的目录存在（在配置日志之前）
os.makedirs('logs', exist_ok=True)
os.makedirs('reports', exist_ok=True)
os.makedirs('intermediate_results', exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/research_log_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

STATE = State()
# QUERY = "Tell me something interesting about human species"
# QUERY = "请帮我调研一下RAG有哪些实用技巧以及经验总结"
QUERY = "请帮我生成一份检索增强生成RAG的综述"
NUM_REFLECTIONS = 2
NUM_RESULTS_PER_SEARCH = 3
CAP_SEARCH_LENGTH = 20000


def save_intermediate_state(state, stage, timestamp, paragraph_idx=None):
    """保存中间状态到JSON文件"""
    try:
        # 构建文件名
        if paragraph_idx is not None:
            filename = f'intermediate_results/state_{stage}_paragraph_{paragraph_idx}_{timestamp}.json'
        else:
            filename = f'intermediate_results/state_{stage}_{timestamp}.json'
        
        # 将State对象转换为可序列化的字典
        state_dict = {
            'report_title': state.report_title,
            'paragraphs': [
                {
                    'title': p.title,
                    'content': p.content,
                    'research': {
                        'search_history': [
                            {'url': s.url, 'content': s.content} for s in p.research.search_history
                        ],
                        'latest_summary': p.research.latest_summary,
                        'reflection_iteration': p.research.reflection_iteration
                    }
                } for p in state.paragraphs
            ]
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(state_dict, f, ensure_ascii=False, indent=2)
        
        logger.info(f"中间状态已保存到: {filename}")
        return filename
    except Exception as e:
        logger.error(f"保存中间状态失败: {e}")
        return None


def main(topic: str = QUERY):
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    logger.info(f"开始研究任务: {topic}")
    
    # 检测输入语言
    lang = detect_language(topic)
    logger.info(f"检测到的语言: {lang}")
    print(f"检测到的语言: {lang}")
    
    # 1. 生成报告结构
    logger.info("步骤1: 生成报告结构")
    report_structure_agent = ReportStructureAgent(topic)
    _ = report_structure_agent.mutate_state(STATE)
    
    # 保存报告结构阶段的状态
    save_intermediate_state(STATE, 'report_structure', timestamp)
    logger.info(f"报告结构生成完成，共{len(STATE.paragraphs)}个段落")
    
    # 初始化各个Agent
    first_search_agent = FirstSearchAgent()
    first_summary_agent = FirstSummaryAgent()
    reflection_agent = ReflectionAgent()
    reflection_summary_agent = ReflectionSummaryAgent()
    report_formatting_agent = ReportFormattingAgent()

    print(f"Total Number of Paragraphs: {len(STATE.paragraphs)}")
    logger.info(f"总段落数: {len(STATE.paragraphs)}")

    idx = 1
    for paragraph in STATE.paragraphs:
        print(f"\nParagraph {idx}: {paragraph.title}")
        logger.info(f"段落 {idx}: {paragraph.title}")
        idx += 1

    # 2. 处理每个段落
    for j in range(len(STATE.paragraphs)):
        logger.info(f"开始处理段落 {j + 1}: {STATE.paragraphs[j].title}")
        print(f"\n\n==============Paragraph: {j + 1}==============\n")
        print(f"=============={STATE.paragraphs[j].title}==============\n")

        ##################
        # 2.1 首次搜索
        logger.info(f"段落 {j + 1}: 执行首次搜索")
        message = json.dumps(
            {
                "title": STATE.paragraphs[j].title,
                "content": STATE.paragraphs[j].content
            }
        )

        output = first_search_agent.run(message)
        logger.info(f"段落 {j + 1}: 搜索查询 - {output.get('search_query', 'N/A')}")

        search_results = tavily_search(output["search_query"], max_results=NUM_RESULTS_PER_SEARCH)
        _ = update_state_with_search_results(search_results, j, STATE)
        
        # 保存首次搜索后的状态
        save_intermediate_state(STATE, 'first_search', timestamp, j)

        ##################
        # 2.2 首次总结
        logger.info(f"段落 {j + 1}: 执行首次总结")
        message = {
            "title": STATE.paragraphs[j].title,
            "content": STATE.paragraphs[j].content,
            "search_query": search_results["query"],
            "search_results": [result["raw_content"][0:CAP_SEARCH_LENGTH] for result in search_results["results"] if
                               result["raw_content"]]
        }

        _ = first_summary_agent.mutate_state(message=json.dumps(message), idx_paragraph=j, state=STATE)
        
        # 保存首次总结后的状态
        save_intermediate_state(STATE, 'first_summary', timestamp, j)
        logger.info(f"段落 {j + 1}: 首次总结完成")

        ##################
        # 2.3 反思迭代
        for i in range(NUM_REFLECTIONS):
            logger.info(f"段落 {j + 1}: 执行反思迭代 {i + 1}/{NUM_REFLECTIONS}")
            print(f"Running reflection: {i + 1}")

            message = {"paragraph_latest_state": STATE.paragraphs[j].research.latest_summary,
                       "title": STATE.paragraphs[j].title,
                       "content": STATE.paragraphs[j].content}

            output = reflection_agent.run(message=json.dumps(message))
            logger.info(f"段落 {j + 1}: 反思搜索查询 - {output.get('search_query', 'N/A')}")

            search_results = tavily_search(output["search_query"])
            _ = update_state_with_search_results(search_results, j, STATE)

            message = {
                "title": STATE.paragraphs[j].title,
                "content": STATE.paragraphs[j].content,
                "search_query": search_results["query"],
                "search_results": [result["raw_content"][0:20000] for result in search_results["results"] if
                                   result["raw_content"]],
                "paragraph_latest_state": STATE.paragraphs[j].research.latest_summary
            }

            _ = reflection_summary_agent.mutate_state(message=json.dumps(message), idx_paragraph=j, state=STATE)
            
            # 保存每次反思后的状态
            save_intermediate_state(STATE, f'reflection_{i+1}', timestamp, j)
            logger.info(f"段落 {j + 1}: 反思迭代 {i + 1} 完成")
        
        logger.info(f"段落 {j + 1} 处理完成")

    # 3. 生成最终报告
    logger.info("开始生成最终报告")
    report_data = [{"title": paragraph.title, "paragraph_latest_state": paragraph.research.latest_summary} for paragraph
                   in STATE.paragraphs]

    # 保存最终报告数据
    save_intermediate_state(STATE, 'final_report_data', timestamp)
    
    final_report = report_formatting_agent.run(json.dumps(report_data))
    logger.info("最终报告生成完成")

    print(final_report)

    # 保存最终报告
    report_filename = f"reports/report_{timestamp}.md"
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(final_report)
    
    logger.info(f"最终报告已保存到: {report_filename}")
    logger.info("研究任务完成")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", type=str, default=QUERY)
    args = parser.parse_args()

    main(args.topic)