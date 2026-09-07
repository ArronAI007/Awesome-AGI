# Evals 框架：面向子系统能力的自建评测

> `evals/` 目录下的四套评测——`readtool`、`session_search_schema`、`compaction`、`browser_use`——都不是通用 benchmark，而是"某个具体子系统的某个具体改动，在某个特定任务分布上，效果有没有变好"这一类问题的自建答卷。它们的共同套路是 A/B 对照：固定一切无关变量,只让被测子系统本身在两组之间变化,用可复算的 oracle（而不是"看起来像不像对"）打分。本文从四套评测的真实代码出发，讲清楚这套自建评测体系的设计意图。

## 学习目标

- 理解 `evals/` 目录下四套评测各自评测的是什么能力：读文件工具的鲁棒性、`session_search` 工具 schema 改动对可用性的影响、压缩策略对召回率的影响、浏览器工具改动对 token/步数效率的影响。
- 理解这些评测为什么不是通用 benchmark，而是"针对具体子系统能力、在特定任务分布下的表现"评测。
- 读懂 `readtool`/`session_search_schema` 共享的 `runner.py`/`tasks.py`/`fixtures.py`/`report.py` 四件套结构，以及 `compaction`/`browser_use` 为什么在这个模板上做了必要的变形。
- 理解这些评测强调的"hermesbench discipline"（3 次重复起步、oracle 打分优先于 LLM judge、resume-safe）背后的统计与工程动机。
- 能够把这套评测体系和 PI 课程《测试策略 Faux Provider 与 Evals》一文中的 evals 体系对照，说清楚两者在"是否需要真实模型"和"是否做 A/B 对照"上的异同。

## 一、总览：四套评测，四种子系统能力

`evals/` 下的四个子目录各自独立成包，没有共享的运行器基类，但结构高度相似：

```
evals/
├── readtool/               fixtures.py  report.py  runner.py  tasks.py
├── session_search_schema/  fixtures.py  report.py  runner.py  tasks.py
├── compaction/             fixtures.py  policies.py  report.py  runner.py  test_region_scoping.py  scripts/
└── browser_use/            orchestrate.py  orchestrate_cloud.py  report.py  single_run.py  tasks/
```

`readtool` 和 `session_search_schema` 严格遵循同一套四件套模板（`fixtures.py` 构造测试环境、`tasks.py` 定义任务与打分函数、`runner.py` 驱动执行、`report.py` 汇总对比），`compaction` 用 `policies.py` 替代了 `tasks.py`（因为它评测的不是离散任务集合，而是一组压缩策略在同一份长对话上的表现），`browser_use` 则因为要同时驱动本地 Chrome 和云端浏览器两套编排逻辑，把 `runner.py` 拆成了 `orchestrate.py`/`orchestrate_cloud.py`/`single_run.py` 三个脚本，任务定义也从单个 `.py` 文件换成了 `tasks/easy.json`/`tasks/hard.json` 两份数据文件。这种"核心模板相同、按评测对象的形状做必要变形"的组织方式，本身就是"面向子系统能力设计"这句话的一个体现——评测的形状服务于被评测对象的形状，而不是反过来削足适履。

## 二、readtool：用真实 Agent 打真实的"刁钻文件"

`evals/readtool/README.md` 交代了这套评测的起源：

> Motivated by Command Code's read-tool writeup (Aug 2026), which benchmarked ten harnesses on hostile-file handling — and whose Hermes column contained several errors... This eval tests the failure shapes for real, through the real `AIAgent`, instead of trusting anyone's capability table.

这句话点出了自建评测相对"相信别人发布的能力对比表"的核心价值：外部评测机构测出来的结论未必准确（文中直接指出对方的 Hermes 那一列有几处错误），与其争论谁的说法对，不如自己跑一遍真实的 `AIAgent`。评测的具体做法是构造九种"刁钻文件"场景：

| fixture | 形状 | 任务 |
|---|---|---|
| `package-lock.json` | 8 万行、2.7MB——token 陷阱 | `lockfile_version` |
| `src/app.min.js` | 单行 600KB，恰好匹配 grep | `minified_backoff` |
| `logs/server.log` | 15 万行，一条 ERROR 藏在末尾 | `log_error_hunt` |
| `logs/live.pipe` | FIFO——朴素读取会挂起 | `fifo_hang` |
| `data/data.txt` | PNG 字节藏在 `.txt` 扩展名后面 | `lying_extension` |

`tasks.py` 里每个任务配一个纯函数打分器，不依赖 LLM judge：

```python
# evals/readtool/tasks.py
def _grade_lockfile(text: str) -> float:
    low = text.lower()
    version = LEFT_PAD_VERSION in low
    where = "package.json" in low
    return (0.5 * version) + (0.5 * where)

def _grade_backoff(text: str) -> float:
    low = text.lower()
    base = "250" in low
    shape = bool(re.search(r"exponential|2\s*\*\*|math\.pow|2\^|doubl", low))
    cap = bool(re.search(r"30000|30,000|30\s*s|3e4", low))
    return (0.4 * base) + (0.4 * shape) + (0.2 * cap)
```

`runner.py` 的核心不是模拟工具行为，而是真的跑一遍完整的 `AIAgent`（文件+终端+搜索工具集），在真实 provider 上产生真实响应，然后统计准确率之外的一整套效率指标：

```python
# evals/readtool/runner.py
"""Run the read-tool eval through the REAL Hermes AIAgent.

For each task: fresh temp HERMES_HOME, fresh fixture workspace, real
AIAgent with the file+terminal+search toolsets, real provider API. Collects
accuracy plus efficiency metrics (API turns, tool calls, read_file calls,
prompt/completion tokens, wall time).
"""
```

README 里的"hermesbench discipline"给出了几条明确的工程纪律：至少 3 次重复（"单次运行的 ±3% 差异是噪音，不是提升"）；跑评测期间不能改动 `tools/` 目录，因为 runner 导入的是当前活跃的代码树；刻意用两个档位的模型（能容忍粗糙读取的旗舰模型 opus，以及"硬件质量差异会显性体现"的中端开源模型 qwen-max）——"一个只对 qwen 有帮助的特性依然算数，因为那正是硬化工作要服务的人群"。

## 三、session_search_schema：把 schema 本身当成被测对象

这套评测的定位和 `readtool` 略有不同——它不跑完整的 `AIAgent`，而是构造一个最小的 agent 循环，只让 `tools/session_search_tool.py` 这一个文件在两个 git ref 之间变化：

> Unlike the readtool/browser evals, this one does not run the full AIAgent — it runs a minimal agent loop where the ONLY variable between arms is `tools/session_search_tool.py` extracted from two git refs. Everything else (seeded DB, tasks, oracles, system prompt, temperature) is held constant.

评测背景是 PR #95570 把 `session_search` 的 schema 描述从 1570 token/次压缩到 695 token/次，需要回答的问题是"把教学性质的长描述从 schema 挪到 response hint 里，会不会让模型更不会用这个工具"。六个任务分别对应不同的工具使用形态（发现型查询、强制翻页、AND 查询失败后需要放宽条件、原文链接格式、profile 链接解析、浏览型摘要），每个任务配一个程序化 oracle，不用 LLM 打分：

```text
| t2_scroll | 强制向前翻页——事实被安排在 ±5 窗口之外、书签之外 | 命中 `statement_timeout` + `45` |
| t3_broaden | AND 查询漏检，必须放宽为 OR/更少词——两个查询名词从不在同一条消息里共现 | 命中端口 `3000` |
```

`README.md` 给出的参考结果表格是这套评测最有说服力的部分：108 次运行（3 模型 × 6 任务 × 3 重复 × 2 分支）里，diet 分支（精简后的 schema）在准确率上从 49/54 提升到 52/54，平均 token 消耗从 7.0k 降到 5.3k——这组数字直接回答了"精简 schema 会不会伤害可用性"这个问题：不会，反而略有提升，因为把教学性内容挪到只在需要时出现的 response hint 里，减少了每次调用的固定负担。规则里特别强调"弱/中端模型才是信号，旗舰模型会掩盖 schema 工程的效果"——这与 `readtool` 里"故意用两档模型"的动机完全一致。

## 四、compaction：测的是召回率，不是 token 数

压缩评测的立意在 `README.md` 开篇写得很清楚：

> Measures what context compaction actually costs in *recall*, not just tokens.

这是一句很容易被忽视但很关键的话：压缩策略最容易被拿来衡量的指标是"省了多少 token"，但真正决定一个压缩策略好不好的是"被压缩掉的内容里，还能不能问出正确答案"。整套流程是：

1. 取一份真实的长对话（`{"messages": [...]}` 格式）；
2. 从"即将被压缩策略摘要掉的区域"生成一批事实性回忆问题（按 transcript 缓存，保证可复现）；
3. 用 `policies.py` 里定义的每一种策略（当前默认策略、激进尾部策略、codex 风格策略等）跑一遍 `ContextCompressor.compress()`；
4. 对每种策略，让一个全新的 LLM 只用压缩后的上下文回答那批问题，用金标准答案打分；
5. 产出记分卡：召回准确率 vs. 保留 token 数，按策略对比。

`README.md` 里"Building transcripts from real sessions"一节交代了真实数据的来源——压缩轮转导致单个活跃会话很少超过 30 万 token，但完整的父子会话链（lineage）才携带全部未压缩历史，需要用 `scripts/reconstruct_lineage.py` 从真实 `state.db` 里重建出评测用的 transcript，并且强调"永远先复制数据库，不要直接指向真实的 `state.db`"。这套评测的成本也交代得很直白：问题生成和评委打分都要走 `agent.auxiliary_client.call_llm`，消耗真实 token，README 建议 `--also-uncompacted` 加一组用完整原始 transcript 回答的对照组作为"召回天花板"。

`test_region_scoping.py` 是这套评测里少见的一个纯 pytest 测试（而不是完整评测流程），职责是一条"防跑偏"的绊线：在会话的头/中/尾各埋一个哨兵值，断言摘要器实际处理的输入只包含中间（被压缩）区域，覆盖新旧两种模式——这条测试保证评测测的确实是"压缩策略处理中间区域的效果"，而不会因为区域边界算错而把头尾内容也喂给了摘要器。

## 五、browser_use：效率对比，而非能力对比

浏览器工具评测的立意是"准确率打平的前提下，比谁更省"：

> `base` runs the built-in twelve `browser_*` tools from a merge-base checkout; `pr` runs `browser_exec` (`browser.backend: browser-use`) from the branch checkout; `prns` is `pr` with the schema's helpers digest stripped to the header (isolates the digest's value).

三个"臂"（arm）分别对应旧的十二工具方案、新的单一 `browser_exec` 驱动方案、以及去掉 schema 里 helper 摘要的消融对照，任务集合按难度分成 `easy.json`（价格查询、类目提取、计数聚合、登录、翻页）和 `hard.json`（多页全类目爬取、评分聚合、JS 延迟渲染、登录链、跨类目比较），全部用可复算的正则 oracle 校验最终答案。硬任务战报的数字很直观：

```
model      arm       ok  tok_mean  tok_med  calls  wall_s  vs base tok
opus4.8    base   18/18     64594    63776    4.1    25.2            —
opus4.8    pr     18/18     25934    25030    2.0    17.5         -60%
```

准确率两个分支都是满分，但 token 消耗直接砍掉六成——这正是"效率对比而非能力对比"的典型形态：两个分支都能把任务做对，评测要回答的是"用更少的资源做对"这件事本身有没有被验证过，而不是简单地问"哪个能做对"。`README.md` 里"Provenance"一节还记录了一段真实的工程事故：原始的逐次运行结果文件存在 `/tmp/bu-bench/`（tmpfs），主机重启后丢失，最终是从当时那次评测运行的 session 事件溯源记录里逐字恢复的——这也从侧面印证了这些评测产物本身具有值得保留的研究价值，而不只是一次性的临时输出。

## 六、共同设计意图：不是通用 benchmark，是子系统假设检验

把四套评测放在一起看，能提炼出几条共同的设计原则：

- **变量隔离到极致**：`session_search_schema` 只让一个工具文件在两个 git ref 之间变化，其余（种子数据库、任务、oracle、系统提示词、温度）全部锁定；`browser_use` 的三个 arm 只在"工具树 + 配置"上不同，连密钥都要清空以确保每个 arm 都得真的驱动浏览器。这是标准的受控实验思路，目的是让观察到的差异只能归因于被测子系统本身。
- **oracle 优先于 LLM judge**：`readtool`/`session_search_schema`/`browser_use` 的打分器全部是确定性的字符串/正则匹配，成本低、可复算、不会因为评委模型自身的不稳定引入额外噪音；只有 `compaction` 因为要评测"语义层面的信息保留"这种本质上无法用正则表达的能力，才引入 LLM 判分,并且专门设了"仅看原文回答"的对照组去校准这套判分本身的天花板。
- **可复现执行纪律（hermesbench discipline）**：3 次重复起步、resume-safe（`browser_use` 的 `results/*.jsonl` 里已完成的 cell 会在重跑时被跳过）、两档模型对比而非只测旗舰模型——这些规则背后是同一个统计常识：n=1 的胜负在真实模型的输出方差面前毫无意义。
- **评测对象是"这次具体改动"，不是"这个系统整体有多强"**：每一套评测都绑定一个具体的 PR/场景（`session_search_schema` 绑定 PR #95570，`browser_use` 绑定 PR #81958），评测本身随着代码演进会被重新运行、结果会被覆盖，`SUMMARY.md`/参考结果表格记录的是"当时这次改动的效果"，而不是一份声称"Hermes 有多强"的通用能力认证。

## 小结与思考题

`evals/` 目录下的四套评测回答的都是同一类问题的不同变体：**这个具体的子系统改动，在这个具体的任务分布上，是不是真的更好**。它们刻意避开了"跑一个通用 benchmark 拿一个分数"的做法，转而为每一次值得关注的改动（读文件工具硬化、工具 schema 瘦身、压缩策略调整、浏览器驱动方式切换）搭建一套量身定制、变量隔离、可复现的 A/B 实验框架，用 oracle 或者受控的 LLM 判分给出可信的效果对比。

和 PI 课程《测试策略 Faux Provider 与 Evals》一文对照：两者都坚持"evals 必须用真实模型，不能用假 provider"这条底线，因为两者要验证的都是"提示词/工具/模型这套组合在真实不确定性下完成任务的效果"，而不是代码逻辑对不对。区别在于，PI 的 `extensions.eval.ts` 用 `evalHarnessTable()` 做的对照实验（系统提示词包含文档 vs. 不包含）是这套体系里的一个特例；而 Hermes 的四套评测里，A/B 对照（`session_search_schema`、`browser_use`）和非对照的策略矩阵评测（`compaction`）、纯能力评测（`readtool`）并存，覆盖面更广，且每一套都配了详尽的"运行纪律"（重复次数、模型档位、resume 语义）作为方法论沉淀，这与 Hermes 背后同时是一个做模型训练的研究机构、需要频繁验证工程改动对真实 agent 行为影响这一背景直接相关。

思考题：

1. `session_search_schema` 评测里，两个 arm 除了 `session_search_tool.py` 之外的一切都锁定不变。如果一次 schema 改动同时伴随着对应工具实现逻辑的修改（不只是描述文字），这套"只换一个文件"的隔离方法还能不能成立？需要做什么调整？
2. `compaction` 评测用 LLM 生成问题、又用 LLM 评委打分，`README.md` 提到"评委能看到金标准答案，回答者看不到"来降低偏差。这套设计能在多大程度上防止评委模型和回答模型之间的"系统性偏好一致"（比如两者恰好都是同一家 provider 的模型，对某种表达方式有共同的偏好）？
3. `browser_use` 的 `README.md` 记录了原始结果文件因主机重启丢失、靠会话事件溯源找回的真实事故。如果这套评测体系要为未来的评测运行建立更稳健的产物留存机制，你会在 `orchestrate.py`/`single_run.py` 里补充什么具体的持久化策略？
