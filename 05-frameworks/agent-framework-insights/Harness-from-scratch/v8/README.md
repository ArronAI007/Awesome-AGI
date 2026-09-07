# v8：结构化错误处理与重试退避

## 本版目标

到 v7 为止，工具执行失败只是简单地把异常字符串塞进消息里，不区分"这是个可以重试的临时故障"还是"这是个重试也没用的根本性错误"，也没有机制防止对一个反复失败的工具无休止地浪费调用。这一版加入结构化错误分类、指数退避重试、以及单工具级熔断器。

## 新增/修改文件（对照 v7）

- 新增 `harness/errors.py`：`TransientError` 异常类 + `classify_error(exc)`，把异常分为 `"retryable"` / `"non_retryable"`。
- 新增 `harness/retry.py`：`compute_backoff_delay(attempt, base_delay)`（指数退避）+ `ToolCircuitBreaker`（按工具名记账连续失败次数，达到阈值后 `is_tripped()` 返回真）。
- 修改 `tools.py`：新增 `flaky_api`（前 2 次失败、第 3 次成功）和 `always_fails_api`（永远失败）两个工具，用于确定性地演示重试和熔断。
- 修改 `harness/loop.py`：执行工具调用改成一个内部重试循环——捕获异常后用 `classify_error` 判断，可重试且未超过 `MAX_RETRIES` 就调用 `sleep_fn` 退避后重试，否则记一次熔断失败；执行前先查熔断状态，命中直接拦截。`run_agent()` 新增 `sleep_fn` 参数（默认 `time.sleep`）。
- 修改 `scenarios.py`：新增 `flaky_api_recovers`、`non_retryable_failure`、`circuit_breaker_trips` 三个场景。
- 修改 `main.py`：`--scenario` 增加新场景，`run_agent` 调用传入 `sleep_fn=time.sleep`。
- 其余文件（`mock_llm.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`）与 v7 完全一致。

## 核心设计

**为什么退避等待要通过 `sleep_fn` 参数注入，而不是直接写死 `time.sleep`**：自动化测试如果真的等 1+2+4 秒会让整个测试套件变得很慢，而且熔断场景要跑 3 轮退避（共 21 秒）。注入一个可替换的睡眠函数，测试传入"记录调用参数但不真的睡"的假函数，既能验证退避延迟的计算是否正确，又不拖慢测试。CLI demo 默认用真实的 `time.sleep`，能实际感受到退避的效果。

**为什么"重试中途失败"不计入熔断，只有"最终放弃"才计入**：熔断器要回答的问题是"这个工具是不是已经彻底不可用了"，而不是"这个工具刚才抖了一下"。如果每次内部重试都计一次熔断失败，`always_fails_api` 一次调用内部重试 3 次就会瞬间触发熔断阈值 3，根本来不及体现"反复调用多轮后才熔断"的设计意图。

## 如何运行 demo

```bash
python3 main.py --scenario flaky_api_recovers      # 前 2 次失败，第 3 次成功，等待约 3 秒
python3 main.py --scenario non_retryable_failure   # 不可重试错误立刻失败，无等待
```

## 局限性

重试和熔断都是"进程内"的状态——`ToolCircuitBreaker` 在每次 `run_agent()` 调用时都是全新创建的，一旦进程重启，熔断记录和已经取得的进展全部丢失，下一次运行会从零开始重新累积失败次数。这正是 v9 要解决的问题：把消息历史落盘，支持进程重启后从断点续跑（虽然 v9 本身不会持久化熔断计数器，这一点会在 v9 的"局限性"里说明）。
