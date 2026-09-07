# agent评测

《Agent 测评方法论》系列文章的代码整理，覆盖测评八维度中的四个：
任务完成度、推理与规划能力、工具使用能力、知识可靠性（幻觉）。

## 目录结构

```
agent评测/
├── framework.py               # 文章一：Agent 测评八维度框架（结构化数据，非代码原文）
├── methodology.py             # 文章二：效度 / 信度 / 区分度方法论（结构化数据，非代码原文）
├── trace.py                   # 文章三～六共用的评测基座：run_agent / run_agent_with_trace / run_agent_with_calls
├── knowledge_base.py           # 文章六：幻觉评测用的黄金事实集 + 来源库
├── test_task_completion.py    # 文章三：任务完成度——第一版最小基座
├── test_planning.py           # 文章四：规划能力——拆解 / 顺序 / 参数 / 参考路径相似度
├── test_replanning.py         # 文章四：规划能力——故障注入重规划
├── test_tool_selection.py     # 文章五：工具调用——工具选择 + 参数
├── test_trap_tools.py         # 文章五：工具调用——陷阱工具 + 危险工具红线测试
├── test_schema.py             # 文章五：工具调用——参数 schema 校验（pydantic）
├── test_boundary.py           # 文章五：工具调用——欠调用 / 过度调用
├── test_factuality.py         # 文章六：知识可靠性——事实正确性
├── test_faithfulness.py       # 文章六：知识可靠性——上下文忠实性
├── test_attribution.py        # 文章六：知识可靠性——引用可溯源性
├── test_consistency.py        # 文章六：知识可靠性——内在一致性（多次采样）
├── test_knowledge_boundary.py # 文章六：知识可靠性——知识边界自知 + 幻觉注入
└── requirements.txt
```

`framework.py` / `methodology.py` 两篇原文没有代码，是纯方法论文章——按用户要求
"整理一下、可以补充"，这里把八维度表格和效度/信度/区分度的自查清单整理成了
结构化的 dataclass，方便以后直接 `from framework import DIMENSIONS` 引用，
而不是每次翻文章。

## `trace.py`：为什么要把三篇文章的 harness 合成一个文件

文章三、四、五、六用的是同一套逐步长大的评测基座：
文章四引入 `run_agent_with_trace`（记 thought/tool_call/observation，测规划），
文章五引入 `run_agent_with_calls`（只记 tool_calls，测工具调用），
文章三、六用的是最简版 `run_agent`（只要最终文本）。
原文里这几个函数分散在不同文章、有的还叫 `from my_agent import run_agent`
（这里的 `my_agent` 是"你自己的 Agent 模块"的占位名，
**不是**这个仓库旁边 `Agent-from-scratch/my_agent/` 那个项目）——
整理时统一收进 `trace.py`，所有 `test_*.py` 一律 `from trace import ...`。

`trace.py` 里的三个函数本身还是原文给的"骨架代码"（`TODO` + 伪代码注释），
需要你自己接上真实的 Agent 循环才能跑起来。想接这个仓库里的 `my_agent/` 项目，
`trace.py` 文件末尾有一段注释示例。

## 已知局限 / 移植时做的修正

- `test_factuality.py` / `test_faithfulness.py` / `test_attribution.py` /
  `test_consistency.py` 里，原文有几处直接写 `actual_output=agent_output`，
  但 `agent_output` 在那个函数作用域里从未被赋值——这是原文本身的疏漏，
  移植时统一改成先 `run_agent(...)` 拿到真实输出，注释里标了"修正:"说明。
- `test_task_completion.py` / `test_planning.py` / `test_tool_selection.py`
  里"用 DeepEval 让 LLM 当裁判"的示例，原文本身也是不完整的骨架（用一个
  没有来源的 `agent_answer` / `agent_full_trace_text` 变量演示用法），
  这里保留为注释掉的示例代码，而不是伪装成能直接跑的测试。
- `test_replanning.py` 里 `mock.patch("my_agent.query_sales", ...)` 的
  `"my_agent"` 也是占位模块路径，同上，不是旁边那个 my_agent/ 项目。

## 运行

```bash
cd Agent-from-scratch/agent评测
pip install -r requirements.txt
# 先把 trace.py 里的 run_agent / run_agent_with_trace / run_agent_with_calls
# 接上你自己的 Agent（或本仓库的 my_agent.ProductionAgent），再跑：
pytest -v
```

## 源文章

1. [Agent测评框架——怎么判断一个AI Agent好不好用？](https://mp.weixin.qq.com/s/KRKKYCaGxZ5aUOWbfm_TBg)
2. [怎样科学地评一个 Agent：效度、信度与区分度](https://mp.weixin.qq.com/s/L8wUv715BxstcLOruJVatA)
3. [如何设计 Agent 的任务完成度测评集](https://mp.weixin.qq.com/s/PfRXKlMzEre_qRIjrlS5tA)
4. [如何评估 Agent 的规划与任务执行能力](https://mp.weixin.qq.com/s/rvaseZhvDLDMrRtS7ycdYw)
5. [如何评估 Agent 的 Tool 与 Skill 调用准确率](https://mp.weixin.qq.com/s/b3WFt2QRVDRTt_pIkfRL5g)
6. [如何设计 Agent 的知识可靠性与幻觉测评集](https://mp.weixin.qq.com/s/CYMfMajkR1HtsiPFoaiQ1Q)

系列后续预告（原文最后一篇提到，本次未涉及）：《如何测试 Agent 的异常处理与
故障恢复能力》——对应 `framework.py` 里的 `error_recovery` 维度。
