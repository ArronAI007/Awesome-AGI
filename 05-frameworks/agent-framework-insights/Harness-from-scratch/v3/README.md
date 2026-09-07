# v3：循环空转检测

## 本版目标

v2 的步数上限治标不治本：阈值设低会打断正常长任务，设高又对空转浪费无能为力。这一版加入**循环空转检测**：识别"模型在原地打转"，只临时禁用那一个出问题的工具，给模型机会换策略，而不是粗暴杀死整个任务。

## 新增/修改文件（对照 v2）

- 新增 `harness/loop_detector.py`：`detect_loop(call_history)`，对最近 5 次工具调用做参数哈希，全部相同就判定为空转；同时统计最近 10 次里的失败率。
- 修改 `harness/loop.py`：`run_agent()` 新增 `call_history` 记录每次工具调用（工具名、参数、是否成功）；每轮循环在调用 LLM 之前先跑 `detect_loop`，命中 `critical` 就从 `tool_registry` 里临时删除该工具，并注入一条系统消息告知模型。
- 修改 `scenarios.py`：新增 `spin_then_recover` 场景（连续 5 次调用同一个坏工具，第 6 步换成 `search_web` 并成功）。
- 修改 `main.py`：`--scenario` 增加 `spin_then_recover` 选项。
- 其余文件（`mock_llm.py`、`tools.py`、`harness/budget.py`）与 v2 完全一致。

## 核心设计

**为什么只禁用一个工具而不是终止整个任务**：模型可能卡在 `read_file` 上，但接下来完全可以换 `search_web` 完成任务——如果一空转就杀掉整个 run，就是在浪费一个本可以被拯救的任务。

**为什么用参数哈希而不是完全比较对象**：`hash_args()` 把工具名和排序后的参数拼成字符串再取 MD5，这样即使参数字典的 key 顺序不同也能识别出"这其实是同一次调用"。

## 如何运行 demo

```bash
python main.py --scenario spin_then_recover
```

预期输出显示：模型连续 5 次调用 `read_file(bad.txt)` 后，Harness 检测到空转并禁用该工具；模型（在这个 mock 场景里是预先写好的脚本）随后改用 `search_web` 并完成任务，总共只花了 7 次 LLM 调用，而不是像 v1/v2 那样毫无察觉地继续重试。

## 局限性

如果模型在工具被临时禁用**之后**仍然尝试调用它（比如脚本没有像 demo 这样"配合"地换策略），`tool = tool_registry[call["name"]]` 会直接抛 `KeyError`，把整个进程崩溃掉——而不是像期望的那样优雅地告诉模型"这个工具现在不可用"。这正是 v6 输出校验要补上的一块：执行工具之前，先检查这个工具是否真的存在。

另外，`detect_loop()` 除了 `critical`，还会计算一种 `warning` 严重度（最近 10 次调用里失败次数达到 8 次），但目前 `run_agent()` 只针对 `critical` 分支做处理，`warning` 的结果只是被计算出来、返回，并没有接入任何日志或提示逻辑，属于预留但尚未生效的信息。如果后续版本需要更细粒度的干预（比如提前警告而非直接禁用工具），可以在此基础上扩展。
