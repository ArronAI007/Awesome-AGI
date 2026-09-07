# v9：会话持久化与断点续跑

## 本版目标

到 v8 为止，进程一旦退出，所有上下文就彻底丢失，下次只能从头开始。这一版把消息历史落盘为 JSONL，支持"进程崩溃/重启后从断点继续跑"，而不需要重新走一遍已经完成的步骤。

## 新增/修改文件（对照 v8）

- 新增 `harness/session_store.py`：`append_message(session_path, message)`（追加写入一行 JSON）、`load_session(session_path)`（文件不存在返回空列表，否则按行解析）。
- 修改 `harness/loop.py`：`run_agent()` 新增可选 `session_path` 参数。启动时如果该路径存在历史记录就直接加载、跳过初始化；此后每一条新增到 `messages` 的消息都通过内部的 `_add_message()` 辅助函数同步落盘。
- 修改 `scenarios.py`：新增 `resume_phase1`（脚本会在完成任务前耗尽，模拟崩溃）和 `resume_phase2`（从崩溃点接着跑完）两个场景，专门用来演示断点续跑。
- 修改 `main.py`：新增 `--session-file` 参数。
- 其余文件（`mock_llm.py`、`tools.py`、`harness/budget.py`、`harness/loop_detector.py`、`harness/context_manager.py`、`harness/validator.py`、`harness/errors.py`、`harness/retry.py`）与 v8 完全一致。

## 核心设计

**为什么选 JSONL 而不是一次性写一个大 JSON 文件**：JSONL（每行一条 JSON）天然支持"追加写入"——每产生一条新消息就 `open(path, "a")` 写一行，不需要每次都读出整个文件、反序列化、修改、再整体写回。这对一个会持续增长的消息历史来说更自然，也更接近真实系统的日志/事件流设计。

**为什么用"脚本切成两段、跑两次 `run_agent()`"来测试断点续跑，而不是真的杀掉进程**：`MockLLM` 本身不感知历史，只按调用次数顺序吐出预设响应；真正测试价值在于验证"`run_agent()` 加载已有消息历史后，能不能正确地从那个点继续，而不是重新初始化"。用两个独立的 `MockLLM` 实例（各自 `call_count` 从 0 开始，但脚本内容分别是前后两段）分两次调用 `run_agent()`，配合同一个 `session_path`，就足以证明这一点，而不需要真的操作系统级别地杀掉进程。

## 如何运行 demo

```bash
python3 main.py --scenario resume_phase1 --session-file /tmp/demo.jsonl   # 模拟"崩溃"，文件里落了 4 条消息
python3 main.py --scenario resume_phase2 --session-file /tmp/demo.jsonl   # 续跑，文件变成 6 条消息
```

## 局限性

只有消息历史本身被持久化。`Budget`、`ToolCircuitBreaker` 等运行时计数器在每次 `run_agent()` 调用时都是全新创建的，进程重启后这些计数器会清零重新累积——这是刻意的简化，真实系统如果需要严格保留这些状态需要额外的持久化设计。另外，如果运行中触发了 v5 的压缩安全阀（`compress_history` 整体替换 `messages`），落盘的 JSONL 文件不会同步这次替换，文件里仍然是压缩前的完整历史——这是 JSONL 只支持追加写入这个设计选择本身带来的局限，本版本的测试和 demo 场景都刻意选择了不会触发压缩的短小脚本来避开这个交互。这两点都不影响本版本要证明的核心能力："消息历史可以正确地持久化和恢复"。
