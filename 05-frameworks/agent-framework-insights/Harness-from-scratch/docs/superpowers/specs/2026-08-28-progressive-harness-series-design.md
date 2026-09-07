# 渐进式 Agent Harness 教程项目设计

- 日期：2026-08-28
- 位置：`Harness-from-scratch/`
- 状态：已批准，待转入实现计划

## 背景与目标

`agent-framework-insights` 仓库现有两套课程（`PI`、`DeepSeek-Harness`）都是对**现成开源 Agent Harness 项目**的源码拆解。`Harness-from-scratch` 是第三种形式：**从零手写一个 Agent Harness，用一系列版本目录（v1、v2 … v15）逐步加固**，每个版本只新增一个优化点，最终达到工业界水准的形态（并发/流式、会话持久化、安全沙箱、可观测性/评估、动态工具、多智能体协作）。

目标读者是想理解"生产级 Agent Harness 到底在防什么、怎么防"的开发者。核心教学方式是"看 diff"：对比 v{N-1} 和 v{N} 就能看清一个具体优化点是怎么落地的。

v1~v7 的技术内容以用户提供的参考文章为基础（裸循环 → 执行预算 → 循环空转检测 → 上下文裁剪 → 压缩安全阀 → 输出校验 → 整合）。v8~v15 是在此之上扩展到工业级的新能力域，由本次设计规划。

## 范围（In Scope）

- 15 个版本目录 `v1/` … `v15/`，每个都是**完全自包含、可独立运行**的最小 Python 项目。
- 每个版本目录都有一个 Mock LLM（脚本化、确定性）和一组 Mock 工具，使项目无需真实 API Key 即可运行并复现"问题场景"与"防护生效场景"。
- 每个版本从 v1 起保留一个可选的真实 LLM 适配层（读取环境变量中的 API Key），允许用户切换到真实模型，但默认路径不依赖网络或密钥。
- 每个版本目录下的 `README.md`，记录本版本新增了什么、为什么需要、和上一版本的差异、如何运行、局限性。
- 根目录 `Harness-from-scratch/README.md`：项目总览 + 完整路线图表格 + 阅读顺序建议。
- 每个版本 `tests/` 目录下针对新增机制的定向测试（不追求覆盖率指标，追求"新增机制至少一个测试能证明其生效"）。

## 范围外（Out of Scope）

- 不实现真实的生产部署形态（容器化、K8s、多租户等）。
- 不做真实的第三方模型接入测试（不消耗真实 API 配额跑 CI）；真实 LLM 适配层只是可选接口，不接入自动化测试。
- 不追求版本目录间的代码复用/共享库——刻意每个版本自包含，方便对照阅读，接受一定的代码重复。
- 不在本设计范围内规划具体的第 3 方 UI/CLI 交互层（保持命令行 `python main.py --scenario <name>` 的最小形态）。

## 版本路线图

| 版本 | 新增能力 | 说明 |
|---|---|---|
| v1 | 裸循环骨架 | 无防护的 `while True` 循环；demo 场景故意演示一次"空转不停"的失控场景，暴露问题 |
| v2 | 执行预算 | 步数计数器 + 上限熔断（`max_steps`），超限强制终止 |
| v3 | 循环空转检测 | 对最近 N 次工具调用做参数哈希；连续相同调用判定空转，临时禁用该工具并注入提示，而非直接杀死整个任务；同时检测连续失败率 |
| v4 | 上下文裁剪 | 周期性清理旧的 tool 消息内容，只保留最近 N 条完整消息，旧的替换为占位标记；支持按工具名豁免（如 `read_file` 结果不清） |
| v5 | 压缩安全阀 | Token 占用达到高水位线时触发全量历史摘要压缩；设置最大连续压缩次数熔断，防止"摘要的摘要"死循环 |
| v6 | 输出校验与自愈 | 执行工具前校验：工具是否存在、必填参数是否齐全；校验失败把错误信息回填上下文让模型自纠；连续校验失败次数达到阈值后终止 |
| v7 | 里程碑：整合版 | 合并 v2~v6 的全部防护到一个完整骨架（对应参考文章"五、整合"部分），集成测试证明多层防护协同生效、互不冲突 |
| v8 | 结构化错误处理与重试退避 | 区分可重试（网络超时、限流）与不可重试（参数错误、权限拒绝）错误；指数退避 + 抖动；单工具级熔断器（连续失败到阈值后临时下线该工具） |
| v9 | 会话持久化与断点续跑 | Session 落盘为 JSONL（每条消息/事件追加写入）；进程重启后可从最近 checkpoint 恢复上下文继续跑；支持导出与回放历史 |
| v10 | 并发与流式 | 同一轮内无依赖的多个工具调用改为并发执行（`asyncio.gather`）；LLM 输出改为流式增量返回；支持基于超时的取消（`asyncio.wait_for` / `CancelledError`） |
| v11 | 安全权限沙箱 | 工具执行前的权限规则引擎：allow / ask / deny 三态；危险操作（如删除、写系统路径）拦截；路径与网络访问白名单 |
| v12 | 可观测性与成本核算 | 结构化事件日志（JSON Lines 形式的 trace：每一步的输入/输出/耗时/token）；token 与费用统计；单次 run 的汇总报告导出 |
| v13 | 自动化评估框架 | 离线 eval 用例集（每条用例定义 Mock LLM 脚本 + 期望终止状态/步数上限）；批量运行 + 通过率/平均步数/平均 token 等指标基线对比，用于防止后续改动导致行为退化 |
| v14 | 动态工具/技能插件化 | 运行时工具注册表：工具可以在启动后动态注册/发现（类似 MCP 的 schema 描述+调用约定）；v6 的校验、v11 的权限规则自动适配新注册的工具，无需改动核心循环 |
| v15 | 多智能体协作 | 主 Agent 可以把子任务委派给独立的 subagent 实例（各自拥有独立的上下文窗口与执行预算），子任务完成后把结果摘要汇总回主循环的上下文——作为本系列的工业级终点形态 |

## 目录结构（每个版本目录内部统一约定）

```
v{N}/
├── README.md                # 本版本文档（见下方"文档规范"）
├── main.py                  # 入口：python main.py --scenario <name>
├── mock_llm.py               # 脚本化、确定性的假 LLM，按 scenario 返回预设的 tool_calls 序列
├── real_llm_adapter.py       # 可选：接入真实 LLM（如 OpenAI 兼容接口）的适配层，默认不启用
├── tools.py                  # 示例工具集的 Mock 实现（read_file / search_web / write_file 等）
├── harness/                  # 本版本累积的 Harness 核心逻辑
│   ├── loop.py                # run_agent() 主循环
│   ├── budget.py               # v2 起出现
│   ├── loop_detector.py        # v3 起出现
│   ├── context_manager.py      # v4/v5 起出现（v5 在 v4 基础上扩展压缩安全阀）
│   ├── validator.py            # v6 起出现
│   └── ...                     # v8 起按能力域继续新增文件
├── scenarios/                 # 场景定义：至少一个"暴露问题"场景 + 一个"防护生效"场景
│   └── *.py
└── tests/
    └── test_*.py               # 针对本版本新增机制的定向测试
```

**关键设计决策**：

1. **完全自包含，不跨版本 import。** 每个 `v{N}/` 都能独立 `cd` 进去运行，不依赖其他版本目录。代价是版本之间存在大量重复代码，这是刻意为之——本项目的价值是"文件级 diff 可读"，而不是代码复用。
2. **Mock LLM 必须是脚本化、确定性的**，不是接入真实模型做随机演示。每个 scenario 预先定义一串 assistant 响应（例如"连续 5 次用同一组参数调用 `read_file`"），使得"没有这层防护会怎样坏、加上防护后怎么被拦住"可以稳定复现，并写成自动化测试。
3. **真实 LLM 适配层从 v1 起就存在但默认关闭。** 通过 `--use-real-llm` 参数或环境变量切换，读取 `.env` 中的 API Key。不接入 CI/自动化测试，只保证接口形状可用。
4. **`harness/` 内的文件按能力域拆分，而不是塞进一个大文件。** 一个优化点通常对应一个新文件（或对已有文件的一处扩展），使 diff 定位到具体机制。

## 文档规范

### 每个 `v{N}/README.md` 固定结构

1. **本版目标** — 一句话说明这一版要解决什么问题
2. **新增/修改文件**（对照 v{N-1}）— 列出本版本新增或修改的文件及一句话说明
3. **核心设计与关键代码片段** — 讲清楚机制本身（为什么这样设计、边界条件怎么处理）
4. **如何运行 demo** — 具体命令 + 预期输出（包括"关掉本版本新增能力会怎样"的对照，如适用）
5. **局限性** — 这一版本还存在什么问题，为什么需要下一版本（自然过渡到下一版）

### 根目录 `Harness-from-scratch/README.md`

- 项目总览：一段话说明这是什么、和 `PI`/`DeepSeek-Harness` 两套课程的关系（后者是"拆解现成项目"，本项目是"从零渐进搭建"）
- 完整路线图表格（版本、新增能力、一句话说明），每行链接到对应 `v{N}/README.md`
- 建议阅读顺序：按版本号顺序阅读，每一版本只需理解"和上一版本的 diff"

## 测试与验证方式

- 每个版本 `tests/` 至少覆盖：
  1. 触发"本版本新增机制要防护的场景"，验证防护确实生效（如 v3 测试连续 5 次相同调用后工具被临时禁用）。
  2. 边界条件（如 v2 测试恰好等于 `max_steps` 时不终止、超过 1 步后终止）。
- 不设统一覆盖率指标，遵循"新增机制至少一个定向测试"的原则。
- v7（整合里程碑）额外要求一个集成测试，证明多层防护同时启用时互不冲突（如循环检测触发的同时上下文裁剪也在正常工作）。
- v13 起新增的评估框架本身产出的 eval 用例集，可以视为后续版本（v14、v15）的回归测试基线，但不强制要求 v14/v15 复用 v13 的框架代码（遵循"版本自包含"的原则，v14/v15 可以内置一份精简版评估脚本）。

## 技术栈

- Python 3.11+，仅使用标准库 + `pytest`（测试）+ `pyyaml`（如 scenario 用 YAML 定义则需要，否则用纯 Python dict/dataclass 定义，减少依赖）。倾向于用纯 Python 定义 scenario（dataclass/函数），避免引入 `pyyaml` 依赖。
- v10 起引入 `asyncio`（标准库，无额外依赖）。
- 真实 LLM 适配层（可选路径）用 `httpx` 或标准库 `urllib` 直接调用 OpenAI 兼容 REST 接口，不强制安装 SDK，保持依赖最小化。

## 风险与开放问题

- **工作量大**：15 个版本 × 完整可运行项目 + 文档 + 测试，实现工作量显著大于典型单文档教程。实现阶段计划分批次交付（如每次完成 3~5 个版本后向用户同步进度），而不是一次性产出全部 15 个版本。
- **v14/v15 的"高阶架构"示例复杂度控制**：动态工具插件化与多智能体协作是相对复杂的架构主题，需要在"演示清楚机制"和"保持代码量可读"之间找平衡，具体实现时以最小可行示例为准，不追求覆盖所有边界情况。

## 实现记录：v1~v7 相对本设计的简化项

v1~v7（基础加固线）已实现完成，过程中对本文档做了两处刻意简化，记录如下，供阅读 v8~v15 或复现本系列时参考：

- **未实现 `real_llm_adapter.py`**：v1~v7 全部版本都没有可选的真实 LLM 适配层，`main.py` 只支持 Mock LLM 驱动的场景。原因：五层防护本身的正确性验证不依赖真实模型，接入真实 API 会引入网络依赖和不确定性，与"确定性可复现"的教学目标冲突；真实适配层的价值主要体现在 v8 之后（结构化错误处理需要真实的网络异常、限流等场景），因此推迟到那之后的版本再评估是否需要。
- **`scenarios/` 目录简化为单个 `scenarios.py` 文件**：每个版本的场景数量少（2~7 个），拆成目录反而增加跳转成本，单文件里一个 `SCENARIOS` 字典足够清晰，与"版本自包含、易于对比 diff"的核心原则更契合。

这两处简化不影响 v1~v7 的教学目标（五层防护机制本身），已实现的 40 个测试全部通过，7 个版本的 CLI demo 全部可运行。

## 实现记录：v8~v11 详细技术方案（第一批工业级扩展）

v1~v7 分批交付原则的第一批延续：v8（结构化错误处理与重试退避）、v9（会话持久化与断点续跑）、v10（并发与流式）、v11（安全权限沙箱）。整体架构基线：v8/v9 保持同步、延续 v1~v7 风格；v10 起 `run_agent` 转为 `async def`，v11 建在 v10 之上。所有新增的"人工/外部干预点"（重试等待、权限审批）都通过依赖注入的可替换函数暴露给 `run_agent`，保持确定性可测试——这是贯穿这四个版本的统一模式，也是对 v1~v7 里 `Budget`/`CompressionGuard`"记账+判断"设计模式的延续。

### v8：结构化错误处理与重试退避

- 新增 `harness/errors.py`：`TransientError` 异常类（表示可重试的临时故障）+ `classify_error(exc)`（区分 `"retryable"` / `"non_retryable"`，默认非 `TransientError` 都判定为不可重试）。
- 新增 `harness/retry.py`：`compute_backoff_delay(attempt, base_delay)`（指数退避，`base_delay * 2**attempt`）+ `ToolCircuitBreaker` 类（按工具名分别记录连续失败次数，达到 `failure_threshold` 后判定该工具"熔断"，`is_tripped(tool_name)` 供调用方在执行前查询）。
- `tools.py` 新增 `flaky_api(query)` 工具：内部维护一个尝试次数计数器，前 N 次调用抛 `TransientError`，第 N+1 次成功——用于确定性地复现"临时故障+重试后成功"。
- `harness/loop.py`：`run_agent()` 新增 `sleep_fn` 参数（默认 `time.sleep`），执行工具调用时改为一个内部重试循环：捕获异常后用 `classify_error` 判断，`retryable` 且未超过最大重试次数就调用 `sleep_fn(compute_backoff_delay(attempt))` 后重试，否则按失败处理并让 `ToolCircuitBreaker` 记一次失败；执行前先查 `ToolCircuitBreaker.is_tripped`，命中就直接拦截，不消耗一次真实调用。
- 测试用注入的假 `sleep_fn`（记录被调用的延迟值到一个列表，不真的睡眠）断言退避延迟序列计算正确、重试确实发生了预期次数；`FileNotFoundError`（非 `TransientError`）验证不触发任何重试；一直失败的工具验证熔断在阈值处生效、之后的调用被直接拦截（不再产生新的失败记录）。

### v9：会话持久化与断点续跑

- 新增 `harness/session_store.py`：`append_message(session_path, message)`（JSONL 追加写入一条消息）、`load_session(session_path)`（不存在或为空则返回空列表，否则按行解析）。
- `harness/loop.py`：`run_agent()` 新增可选 `session_path` 参数（`pathlib.Path`）。启动时若该路径存在且非空，从中加载完整消息历史替代默认的 `[system, user]` 初始化；否则按原逻辑初始化并把这两条消息写入文件（如果传了 `session_path`）。此后每一条新增到 `messages` 的消息（assistant、tool、系统注入的提示）都会同步 `append_message` 落盘一份。
- 测试/demo 方式：把一个 `MockLLM` 脚本切成前后两段。第一次 `run_agent(..., session_path=tmp_path)` 只喂前半段脚本——脚本耗尽后抛 `ScriptExhausted`，模拟"进程崩溃"；断言此时文件里已经落盘了预期条数的消息。第二次调用换一个全新的 `MockLLM`（`call_count` 从 0 开始，但脚本内容是后半段）+ 同一个 `session_path`，断言能从断点正确续跑、最终结果与"一次性跑完整段脚本"完全一致，且文件包含两段合并后的全部消息（验证是追加而不是覆盖）。
- 局限性（会写进 v9 的 README）：只有消息历史被持久化，`Budget`/`ToolCircuitBreaker` 等运行时计数器进程重启后清零——这是刻意的简化，真实系统如果需要跨重启保留这些状态需要额外设计。

### v10：并发工具调用 + 超时取消（不含真流式输出）

- `harness/loop.py` 的 `run_agent()` 改为 `async def`；`mock_llm.py` 的 `MockLLM.chat()` 改为 `async def`；`tools.py` 的 `Tool.run()` 改为 `async def`，内部工具函数也相应改为 `async def`（不需要真实 I/O 等待的可以直接 `return`，不必额外 `await asyncio.sleep`）。
- 同一轮 LLM 响应里的多个 `tool_calls`：验证/权限检查等同步、快速的判断仍按顺序做完，真正的执行阶段用 `asyncio.gather` 并发跑；每个工具调用外层套 `asyncio.wait_for(tool.run(args), timeout=timeout_seconds)`，超时抛出的 `asyncio.TimeoutError` 按普通失败处理（不重试、不影响其它并发中的调用），避免一个卡住的工具拖死整个循环。
- 验证并发确实发生的方式：给参与并发测试的工具传入一个共享的"当前在途调用数"计数器（进入时 +1、退出前 -1，同时记录出现过的峰值），断言峰值 `> 1`；不使用真实的 `time.perf_counter()` 计时差值断言，避免测试因机器负载不同而 flaky。
- 场景：① 一轮返回 2~3 个互相独立的 `tool_calls`，验证并发峰值 `>1` 且每个调用的结果被正确对应回各自的 `call["id"]`；② 一个人为"耗时超过 `timeout_seconds`"的工具被 `asyncio.wait_for` 正确取消，运行继续而不是挂起（用极短的 `timeout_seconds`，如 0.05 秒，配合一个 `await asyncio.sleep(0.2)` 的慢工具，保持测试快速且确定性强）。
- `main.py` 用 `asyncio.run(main_async())` 包一层，CLI 使用方式不变。
- 明确不实现真正的流式增量输出：`MockLLM` 一次性返回完整 response，没有真实的增量 chunk 可流，强行拆字符流没有教学意义——这一简化会记录进 v10 的 README，作为对设计文档"并发与流式"标题的范围说明。

### v11：安全权限沙箱

- 新增 `harness/permissions.py`：`check_permission(call, policy) -> "allow" | "ask" | "deny"`，`policy` 是一个 `{tool_name: rule}` 的简单字典，未出现在字典里的工具默认 `"allow"`。
- `harness/loop.py`：`run_agent()` 新增 `permission_policy`（字典，默认全 `"allow"`）和 `approve_fn`（可调用对象，签名 `approve_fn(call) -> bool`，默认是一个基于 `input()` 的真实终端询问函数）两个参数。在校验通过、进入并发执行阶段之前，先对每个 `tool_calls` 做一次同步的权限过滤：`"deny"` 直接回填系统消息拒绝执行；`"ask"` 调用 `approve_fn(call)`，返回 `False` 就同样回填拒绝消息，返回 `True` 才进入待并发执行的列表；只有权限过滤后剩下的调用才会被 `asyncio.gather` 并发执行。
- 测试用确定性的假 `approve_fn`（要么恒定返回 `True`，要么恒定返回 `False`）驱动两种分支；`"deny"` 规则的场景不依赖 `approve_fn`，用来验证"deny 优先级高于任何审批回调"。
- 场景：① `write_file` 配置为 `"ask"`，假 `approve_fn` 批准 → 正常执行成功；② 同一个场景换成拒绝的假 `approve_fn` → 优雅回填拒绝消息、模型换一种方式完成任务（复用 v6/v7 已经验证过的"自纠正"叙事）；③ 一个配置为 `"deny"` 的危险工具（如模拟的 `delete_everything`）无论 `approve_fn` 是什么都被拦截。

### v8~v11 相对设计文档的范围确认

- v10 标题虽然是"并发与流式"，但本批次刻意把"流式"限定为不实现（详见上方 v10 小节的说明），只做并发工具调用与超时取消。这是与用户确认过的范围收敛，不是实现中途的缩水。
- v8~v11 延续 v1~v7"完全自包含、不跨版本 import"的原则；v8/v9 每个版本仍是同步代码，v10 起才引入 `asyncio`，形成第二条"架构基线"，v11~v15 都会建立在 v10 引入的 async 循环之上。

## 实现记录：v12~v15 详细技术方案（第二批工业级扩展，系列收官）

v8~v11 分批交付原则的第二批、也是最后一批：v12（可观测性与成本核算）、v13（自动化评估框架）、v14（动态工具/技能插件化）、v15（多智能体协作）。全部建立在 v11 的 async 权限沙箱骨架之上，延续同一套"自包含、MockLLM 脚本化、记账+判断式防护对象、依赖注入保证确定性可测试"的模式。

### v12：可观测性与成本核算

- 新增 `harness/observability.py`：
  - `estimate_tokens(text)`：`max(1, len(text) // 4)`（`text` 为空返回 `0`），延续 v5 `needs_compression` 的字符数估算思路，不引入真实 tokenizer 依赖。
  - `EventLog`：把结构化事件（LLM 调用、工具调用、各类防护触发）追加写入 JSONL，格式与 v9 的 `session_store` 类似但记录的是运行时指标而非对话历史；每条事件带 `step`、`event_type`、以及事件特定字段（如 `tool_name`、`tokens_in`、`tokens_out`、`duration_ms`）。耗时通过注入的 `clock_fn` 参数（默认 `time.perf_counter`）获取，测试传入一个确定性的假时钟（每次调用返回递增的固定值），避免真实计时导致的不确定性。
  - `compute_cost(tokens_in, tokens_out, rates)`：`rates` 是 `{"input_per_1k": float, "output_per_1k": float}`，返回 `tokens_in/1000*rates["input_per_1k"] + tokens_out/1000*rates["output_per_1k"]`。
  - `RunReport`：从一个 `EventLog` 的事件列表汇总出总步数、LLM 调用次数、工具调用次数（按成功/失败分类）、总 token 数、总成本、各类防护（循环检测/校验失败/熔断/压缩/权限拒绝）触发次数。
- `harness/loop.py`：`run_agent()` 新增可选 `event_log` 参数（默认 `None`），为 `None` 时完全不记录、行为与 v11 一致；传入时在 LLM 调用和每次工具执行结束后记一条事件。
- `main.py` 新增 `--report-file` 参数：跑完后把 `RunReport` 的汇总结果写成 JSON 文件并打印到终端。
- 测试：验证 `estimate_tokens`/`compute_cost` 的纯函数正确性；验证一个跑完整场景后 `EventLog` 记录的事件数量、类型与该场景已知的调用次数吻合；验证 `RunReport` 汇总的数字正确。

### v13：自动化评估框架

- 新增 `harness/eval_runner.py`：
  - `run_eval_case(case, tool_registry_factory, ...)`：`case` 是一个字典，`{"scenario": "<已有 scenario 名字>", "expected_result_contains": str, "max_llm_calls": int}`；内部用 `get_scenario` 取出脚本、跑一遍 `run_agent()`，和期望值比对，返回 `{"name": ..., "passed": bool, "actual_result": ..., "actual_call_count": ...}`。
  - `run_eval_suite(cases)`：批量跑所有用例，汇总通过率、平均 LLM 调用次数、平均 token 数（复用 v12 的 `estimate_tokens`，对每个用例的最终 `result` 字符串估算）。
  - `compare_to_baseline(current_report, baseline_report)`：和一份存进仓库的 baseline JSON 对比，通过率下降或平均调用次数超出容差就标记为回归。
- 新增 `evals.py`：eval 用例列表，直接引用 `scenarios.py` 里已有的 scenario（不新增独立的场景数据格式），如 `happy_path`、`circuit_breaker_trips`、`deny_dangerous_tool` 等各自搭配期望断言。
- `main.py` 新增 `--run-evals` 模式：跑一遍 eval 套件并打印/落盘汇总报告。
- 测试：验证单个 eval 用例通过/不通过两种情况都能被正确判定；验证套件汇总的通过率/平均值计算正确；验证 `compare_to_baseline` 能正确识别一次"变差了"的对比。

### v14：动态工具/技能插件化

- 新增 `harness/tool_registry.py`：`class ToolRegistry(dict)`，新增 `register(tool)`（`self[tool.name] = tool`）和 `unregister(name)`（`self.pop(name, None)`），不覆写任何 dict 原生方法——`registry[name]`、`del registry[name]`、`name in registry`、`.keys()` 等现有调用方式在 `harness/loop.py`、`harness/validator.py`、`harness/permissions.py` 里全部不需要改动。
- `tools.py`：`build_default_tool_registry()` 返回 `ToolRegistry` 实例而不是普通 `dict`；新增 `load_plugin(plugin_name)` 工具，闭包持有对 registry 自身的引用，调用后把一个预先定义好、但默认不在注册表里的工具（`weather_lookup`）动态 `register()` 进去。
- 场景：模型第一轮调用 `load_plugin("weather")` 完成注册；第二轮调用 `weather_lookup(...)`，直接通过 v6 的 `validate_tool_call` 和 v11 的 `check_permission`（两者都只是运行时查一次 registry/policy，没有任何需要因为"新工具"而改动的硬编码逻辑）并成功执行——证明动态注册的工具能"零改动自动适配"已有的校验与权限层。
- 测试：验证 `load_plugin` 执行前调用 `weather_lookup` 会被校验拦截（"未知工具"）；执行 `load_plugin` 后 `weather_lookup` 出现在 registry 里且可以被正常调用；验证 `ToolRegistry` 的 `register`/`unregister` 方法本身的正确性。

### v15：多智能体协作

- `tools.py` 新增 `delegate_task(subtask)` 工具：`build_default_tool_registry()` 新增可选参数 `sub_task_scripts`（默认 `None`），类型是 `{subtask_name: (sub_goal, sub_script)}`。`delegate_task` 闭包按 `subtask` 查表，取出对应的 `sub_goal`/`sub_script`，构建一个全新的子 `MockLLM(sub_script)`、子 `Budget(max_steps=...)`、子 `tool_registry`（调用 `build_default_tool_registry()`，不传 `sub_task_scripts`，故意不支持嵌套委派，避免无限递归复杂度），递归 `await` 调用同一个 `harness.loop.run_agent()`，把子任务的最终结果字符串包装成 `f"[子任务：{subtask} 完成] {result}"` 作为这次工具调用的返回值——自然回填进主循环的 `messages`，不需要任何特殊的"多智能体消息类型"。
- 主 agent 与子 agent 各自拥有独立的 `messages`、`Budget`、`llm.call_count`，互不干扰；子 agent 的 `MockLLM` 是一个完全独立的实例，其调用次数不计入主循环的 `llm.call_count`。
- 场景：主循环某一轮委派一个子任务（如"调研某个子问题"），子 agent 跑 2 轮后返回摘要，主循环收到摘要后再跑一轮完成整体任务。
- 测试：验证委派场景的最终结果、主 `llm.call_count`（只反映主循环轮次）；验证子任务脚本用尽或子任务本身触发某种防护（如子任务内部校验失败）时，子 agent 依然能返回一个说明性的结果字符串给主循环，而不是让异常直接扎穿委派边界导致主循环崩溃（`delegate_task` 内部需要捕获子 `run_agent()` 可能抛出的 `ScriptExhausted`，转换成一条说明性的失败摘要返回给主循环，而不是让主循环也跟着崩溃）。

### v12~v15 收尾

v15 完成后不再新增一个类似 v7 那样的"大集成"场景——v7 已经是 v1~v7 阶段的里程碑，v12~v15 每个版本本身就是独立的能力域（可观测性、评估、动态工具、多智能体），互相之间没有 v2~v6 那种"五层防护必须协同工作"的强耦合关系，额外做一次大集成场景的教学价值有限、且会显著增加范围。最后一个任务只做：① 根目录 `README.md` 的路线图表格补完 v12~v15 四行链接，标注整个 v1~v15 系列完成；② v1~v15 全部版本目录跑一遍测试套件做最终回归确认。
