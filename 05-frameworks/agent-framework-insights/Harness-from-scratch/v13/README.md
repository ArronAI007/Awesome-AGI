# v13：自动化评估框架

## 本版目标

到 v12 为止，"这个版本改动之后行为有没有变差"这件事完全靠人工跑几个 demo 场景肉眼观察。这一版加入一个离线批量评估框架：用已有场景配上期望断言组成一批 eval 用例，一次性跑完给出通过率和平均指标，未来还能和一份基线对比、自动标记回归。

## 新增/修改文件（对照 v12）

- 新增 `evals.py`：eval 用例列表，每条用例直接引用 `scenarios.py` 里已有的场景名字 + 期望断言（`expected_result_contains`、`max_llm_calls`），不新增独立的数据格式。
- 新增 `harness/eval_runner.py`：`run_eval_case()`（跑一个用例、和期望值比对）、`aggregate_results()`（纯函数，从一组用例结果汇总通过率/平均调用次数/平均 token）、`run_eval_suite()`（跑完整批用例再汇总）、`compare_to_baseline()`（和一份基线报告比较，标记通过率下降或平均调用次数超出容差的回归）。
- 修改 `main.py`：新增 `--run-evals` 模式；`--scenario` 从"必填"改成"除非用 `--run-evals` 否则必填"。
- 其余文件（`mock_llm.py`、`tools.py`、`scenarios.py`、`harness/loop.py` 及其余 `harness/` 子模块）与 v12 完全一致——本版本完全不修改核心循环，只是批量调用已经写好的 `run_agent()`。

## 核心设计

**为什么 eval 用例直接复用 `scenarios.py`，不新建一套独立的用例数据格式**：这个系列从 v1 起所有场景都已经是"目标 + 确定性脚本"的形式，天然适合被"再跑一遍、和期望值比对"这种评估逻辑复用；引入一套新的 YAML/JSON schema 只会带来额外的解析代码和心智负担，不会带来任何本项目场景下需要的额外表达能力。

**为什么 `aggregate_results` 单独拆成一个纯函数，而不是揉进 `run_eval_suite` 里**：`run_eval_suite` 依赖真的跑一遍场景（异步、涉及 `MockLLM`/`Budget`），测试它的汇总算术逻辑如果每次都要真的跑场景，既慢又容易因为具体场景的字符数变化而写出脆弱的断言。把"跑用例产生结果列表"和"从结果列表汇总统计数字"拆成两个函数，后者可以直接喂一组手写的、数字干净的假结果测试，不用关心真实场景内部细节。

**为什么 `compare_to_baseline` 只关心通过率下降和调用次数上升，不关心 token/成本变化**：调用次数是最直接反映"防护机制是不是被触发得更频繁了"的信号（比如某个改动意外让某个场景触发了更多重试），token/成本目前只是粗略估算，拿它做回归判断的信噪比不够高，本版本先聚焦在通过率和调用次数这两个更可靠的信号上。

## 如何运行 demo

```bash
python3 main.py --run-evals   # 跑一遍离线 eval 套件，打印通过率和每个用例的详情
```

## 局限性

`evals.py` 里的用例都是手写的、针对现有场景的断言，没有自动发现"哪些场景应该被纳入 eval 套件"的机制——加一个新场景后需要有人手动决定要不要把它加进 `EVAL_CASES`。`compare_to_baseline` 需要调用方自己准备一份 baseline 报告（本版本没有提供"自动保存/更新 baseline 文件"的 CLI 命令），这是刻意保持最小化的简化，真实系统通常会把 baseline 存成一个受版本控制的文件、在 CI 里自动比对；如果手写的 baseline 缺少必需字段（`pass_rate`、`avg_llm_calls`），`compare_to_baseline` 会直接抛出带字段名的 `ValueError`，而不是留一个不知所云的 `KeyError`。

`run_eval_case` 会捕获 `run_agent()` 抛出的任何异常并把它折算成一条 `passed: False` 的结果（附带异常信息），这样 `EVAL_CASES` 里某一条用例意外出错（比如后续有人加了一个还没跑通的场景）不会让整批评估直接崩溃、丢掉其它已经跑完的用例结果。
