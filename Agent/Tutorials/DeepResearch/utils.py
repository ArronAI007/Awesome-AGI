import os

from tavily import TavilyClient
from state import Search


def remove_reasoning_from_output(output):
    return output.split("</think>")[-1].strip()


def clean_json_tags(text):
    return text.replace("```json\n", "").replace("\n```", "")


def clean_markdown_tags(text):
    return text.replace("```markdown\n", "").replace("\n```", "")


def tavily_search(query, include_raw_content=True, max_results=5):
    tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    return tavily_client.search(query,
                                include_raw_content=include_raw_content,
                                max_results=max_results)


def update_state_with_search_results(search_results, idx_paragraph, state):
    for search_result in search_results["results"]:
        search = Search(url=search_result["url"], content=search_result["raw_content"])
        state.paragraphs[idx_paragraph].research.search_history.append(search)

    return state