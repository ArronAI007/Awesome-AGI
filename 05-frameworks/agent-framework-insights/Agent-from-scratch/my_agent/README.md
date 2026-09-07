# my_agent

《从零造一个 AI Agent》六篇系列文章的代码，按文章顺序整理成一个可运行的项目。

## 目录结构

```
my_agent/
├── agent.py             # 第 1 篇：Agent 的最小内核（大模型 + 工具 + 循环）
├── function_calling.py  # 第 2 篇：手动拆解 Function Calling 的调度过程
├── react_loop.py        # 第 3 篇：ReAct 循环——Thought → Action → Observation
├── tool_registry.py      # 第 4 篇：可插拔工具箱（Tool / ToolRegistry / 三种筛选策略）
├── memory.py             # 第 5 篇：三层记忆系统
│   ├── ShortTermMemory / SlidingWindowMemory / SummarizingMemory   短期记忆
│   ├── LongTermMemory / TypedMemory                                长期记忆（向量数据库）
│   ├── TaskStep / WorkingMemory                                    工作记忆
│   └── MemoryAgent                                                 三层记忆整合示例
├── error_handling.py     # 第 6 篇：错误处理（重试退避 / 安全执行 / 熔断 / 降级）
├── evaluation.py         # 第 6 篇：评估体系 1-3 层（冒烟测试 / 行为验证 / 回归测试）
├── monitoring.py         # 第 6 篇：评估体系第 4 层（线上监控 + 成本估算）
├── tools/                # 第 4 篇引入的可插拔工具，一个工具一个文件
│   ├── weather.py / email.py / web_search.py / knowledge_base.py
│   ├── calculator.py / todo.py / meeting.py
│   └── __init__.py       # ALL_TOOLS：汇总以上七个 Tool 实例
├── agent_memory_db/      # ChromaDB 数据文件（首次运行 LongTermMemory 时自动生成）
└── main.py               # 入口：组装工具箱 + ProductionAgent，命令行对话
```

`agent.py` / `function_calling.py` / `react_loop.py` 三个文件各自独立、可以直接
`python -m my_agent.agent` 运行，用来单独理解某一层概念；它们内部各自带了一份最简
版的示例工具（`get_weather` / `send_message` 等），不依赖 `tools/` 包。

`tool_registry.py` 往后（工具箱、记忆、错误处理、评估、监控）是同一套工具/概念的
持续升级，最终收敛到 `main.py` 里通过 `error_handling.ProductionAgent` 对外暴露的
`chat(user_input) -> str`。

## 运行

`main.py` 及以下几层（`tool_registry.py` / `error_handling.py`）之间用的是包内相对
导入，所以要从 `my_agent/` 的上一级目录用 `-m` 方式启动，而不是 `cd my_agent &&
python main.py`：

```bash
cd Agent-from-scratch          # my_agent/ 的上一级目录
pip install -r my_agent/requirements.txt
export OPENAI_API_KEY=...        # 或改 main.py 里 OpenAI() 的 base_url 指向其他兼容服务
python -m my_agent.main
```

`memory.LongTermMemory` 把 ChromaDB 数据固定写在 `my_agent/agent_memory_db/`
（相对本文件所在目录算路径，不是相对当前工作目录），所以不管从哪里用 `-m` 启动，
数据库位置都和上面目录树里画的一致。

## 源文章

1. [Agent 的本质——不是聊天，是干活](https://mp.weixin.qq.com/s/w3v2A2DJM-sjgEY00vaxzw)
2. [Function Calling 拆解——大模型是怎么"伸手"的？](https://mp.weixin.qq.com/s/bu5f_t7FZsJUkTkPLjEMeQ)
3. [ReAct 循环——Agent 的心跳](https://mp.weixin.qq.com/s/pvbJ5281Tkvm4uNWlgC8LA)
4. [给 Agent 配上工具箱——多工具怎么管、怎么选、怎么不翻车](https://mp.weixin.qq.com/s/V9jEWzNpqt6gy_1eBE-XeA)
5. [Agent 的记忆系统——记住你说了什么、做到哪了、什么改了](https://mp.weixin.qq.com/s/my-LSQ0KRLySlmtPiDYcJw)
6. [生产级的工程问题——错误、评估、边界](https://mp.weixin.qq.com/s/7R3iqyQ8RdSvgY6uI1nobA)

## 已知局限（照抄自原文，未额外修复）

- `tool_registry.load_tools_from_config` 用 `globals().get(name)` 按函数名查找要
  注册的函数，只能找到 `tool_registry.py` 自己模块里的函数——这是原文本身的写法，
  不是移植时引入的问题。
- `evaluation.BehaviorTest` / `RegressionTestSuite` 需要真实调用一个 LLM 当裁判，
  示例里没有接掉线 mock，直接跑需要配置好 `OPENAI_API_KEY`。
- 各文件里标了「修正：」的注释，是移植时发现原文代码本身存在的小 bug（比如
  `ProductionAgent` 用到 `ToolRegistry.get_definitions()`，但第 4 篇实际定义的方法
  叫 `list_all()` + `to_openai_schema()`），按最合理的方式接上了，注释里说明了原文
  和实际实现的差异。
