# v6：输出校验与自愈

## 本版目标

到 v5 为止，系统对"模型输出格式本身有问题"完全没有防护——调用不存在的工具、漏填必填参数，都会在 `tool_registry[call["name"]]` 这一步直接抛异常崩溃整个进程。这一版加入**执行前校验**：校验失败不崩溃，把错误信息回填给模型，让它在下一轮自己修正。

## 新增/修改文件（对照 v5）

- 新增 `harness/validator.py`：`validate_tool_call(call, tool_registry)`，检查工具是否存在、必填参数是否齐全。
- 修改 `harness/loop.py`：执行每个工具调用前先跑校验；失败则把错误信息以 `system` 消息回填并 `continue`（跳过这次执行），同时用 `consecutive_errors` 计数，达到 `MAX_CONSECUTIVE_ERRORS`（3 次）就终止；任意一次校验通过就把计数清零。
- 修改 `tools.py`：把 v5 里为了触发压缩而改成超长输出的 `search_web` 改回正常长度（v5 的改动是那个版本特有的演示需要）。
- 修改 `scenarios.py`：新增 `missing_required_arg_then_fix`（漏参数后自纠）和 `unknown_tool_repeated`（连续调用不存在的工具，触发熔断）。
- 其余文件（`mock_llm.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`）与 v5 完全一致。

## 核心设计

**为什么校验失败要 `continue` 而不是直接返回错误**：模型在同一轮里可能会有多个 `tool_calls`，一个校验失败不该连累同一轮里的其它合法调用。

**为什么用"连续"校验失败计数、而不是"累计"**：偶尔犯错很正常（模型确实会漏填参数），只要中间有一次成功就说明模型在自纠正，不该被历史上的失误拖累而提前终止；只有**连续**失败才说明模型陷入了某种系统性的困境。

## 如何运行 demo

```bash
python main.py --scenario missing_required_arg_then_fix   # 漏参数 -> 报错回填 -> 模型自纠 -> 成功
python main.py --scenario unknown_tool_repeated            # 连续调用不存在的工具 -> 3 次后熔断
```

## 局限性

现在预算、循环检测、上下文治理（裁剪+压缩安全阀）、输出校验这五层防护都已经分别实现并测试过，但**从未在同一个 `run_agent` 里同时跑过、验证过它们不会互相冲突**（比如循环检测删除工具的同时，校验层要不要也跟着更新可用工具列表）。这正是 v7 要做的事：把 v2~v6 整合成一个完整骨架，并用集成测试证明多层防护协同生效。
