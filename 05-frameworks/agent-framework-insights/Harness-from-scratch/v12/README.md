# v12：可观测性与成本核算

## 本版目标

到 v11 为止，一次运行到底发生了什么——调用了几次 LLM、几次工具、哪些防护被触发了几次、大概花了多少钱——完全没有留下任何结构化记录，只能从终端打印的只言片语里猜。这一版加入结构化事件日志和运行报告，把这些信息变成可以事后查询、汇总、审计的数据。

## 新增/修改文件（对照 v11）

- 新增 `harness/observability.py`：`estimate_tokens(text)`（字符数估算，延续 v5 的思路）、`EventLog`（把事件记进内存列表，指定路径时同步落盘 JSONL）、`compute_cost(tokens_in, tokens_out, rates)`、`build_run_report(events, rates)`（从事件列表汇总出调用次数、token、成本、各类防护触发次数）。
- 修改 `harness/loop.py`：`run_agent()` 新增可选 `event_log` 参数（默认 `None`，不记录、行为与 v11 完全一致）；在每次 LLM 调用后记一条 `llm_call` 事件，每次工具执行结束后记一条 `tool_call` 事件，每次防护触发（循环检测/校验失败/权限拒绝/熔断/压缩）记一条 `guardrail` 事件。
- 修改 `main.py`：新增 `--report-file` 参数，指定后自动创建 `EventLog`、跑完后用 `build_run_report` 生成汇总报告并写入 JSON 文件。
- 其余文件（`mock_llm.py`、`tools.py`、`scenarios.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`、`harness/errors.py`、`harness/retry.py`、`harness/session_store.py`、`harness/permissions.py`）与 v11 完全一致。

## 核心设计

**为什么事件记录用一个独立的 `_log()` 辅助函数、而不是散在各处直接调用 `event_log.record(...)`**：`event_log` 是可选的（默认 `None`），每处调用点都要判断"是否启用了可观测性"，抽成一个小函数（内部做 `if event_log is not None` 判断）避免这段样板代码重复七八次。

**为什么耗时相关的字段（`timestamp`）通过注入的 `clock_fn` 而不是直接调用 `time.perf_counter()`**：和 v8 的 `sleep_fn`、v9 的会话落盘一样的思路——测试如果依赖真实时钟会引入不确定性，注入一个确定性的假时钟（每次调用返回递增的固定值）能让"时间戳按调用顺序递增"这件事本身变得可断言。

**为什么 token/成本只是估算，不接入真实 tokenizer**：这个系列从 v1 起就没有真实 LLM 依赖，`estimate_tokens` 延续 v5 `needs_compression` 的字符数估算思路（`len(text) // 4`），足够教学演示"如何组织可观测性数据"这件事本身，真实场景换成真正的 tokenizer 计数，`build_run_report` 的聚合逻辑不需要变。

## 如何运行 demo

```bash
python3 main.py --scenario spin_then_recover --report-file /tmp/report.json   # 跑完后 /tmp/report.json 里能看到 circuit_breaker 防护触发了 2 次
```

注意：`spin_then_recover` 这个场景名字听起来像是在演示"循环检测"（v3 引入的 `loop_detector`），但自 v8 引入熔断器（`ToolCircuitBreaker`，阈值 3）之后，`read_file(bad.txt)` 连续失败 3 次就会被熔断器提前拦截，call_history 根本积累不到循环检测所需的 5 条相同记录——于是实际触发的防护变成了 `circuit_breaker`，而不是 `loop_detector`。这是多层防护叠加后一个真实的涌现行为：先加入的防护（更早、更敏感的阈值）会抢在后加入的防护之前生效。写运行报告时不要想当然地假设"这个场景名字对应哪个防护"，而要以 `build_run_report` 实际统计出的 `guardrail_counts` 为准。

## 局限性

`estimate_tokens` 只是字符数除以 4 的粗略估算，中英文混合文本下这个比例并不准确，只用于演示"怎么组织成本核算数据"这件事本身。`build_run_report` 需要拿到一个已经跑完的 `EventLog.events` 列表才能汇总，本版本没有提供"运行中途实时查看报告"的能力（只能等 `run_agent()` 返回之后再汇总）。这两点都不影响 v13 要基于本版本的 `estimate_tokens` 构建的评估框架。

另外，事件日志目前不是"运行终止原因"的完整记录：预算耗尽（`budget.is_exceeded()`）和压缩配额耗尽（`compression_guard.is_exhausted()`）这两条早退路径直接 `return`，不会记一条事件，所以报告里看不到"为什么在这一步停下来了"——只有真正发生过的守护动作（比如某次压缩、某次熔断）才会出现在 `guardrail_counts` 里。读报告时不要把"该守护类型未出现在 guardrail_counts 里"当成"这个守护从未生效过"的证据。
