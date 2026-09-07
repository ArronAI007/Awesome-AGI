# v5：压缩安全阀

## 本版目标

v4 的周期性裁剪只是把旧消息换成占位符，省下来的空间有限。这一版加入基于总量水位的**全量摘要压缩**，以及压缩本身的**熔断机制**——防止摘要之后空间还是不够、于是又摘要、变成"摘要的摘要的摘要"最后把原始信息全部丢光的死循环。

## 新增/修改文件（对照 v4）

- 修改 `harness/context_manager.py`：新增 `needs_compression(messages, config)`（按总字符数估算是否超过高水位线）、`compress_history(messages, keep_recent_count)`（保留 system 消息 + 最近 N 条，其余压成一条摘要消息）、`CompressionGuard` 类（记录连续压缩次数，达到上限就报告耗尽）。
- 修改 `harness/loop.py`：`run_agent()` 新增 `compression_config` 参数；在裁剪之后、调用 LLM 之前检查是否需要压缩，命中且 `CompressionGuard` 未耗尽就压缩并计数，耗尽则直接终止。
- 修改 `scenarios.py` / `tools.py`：新增 `oversized_tool_output` 场景，工具返回一段超长字符串，用来在测试里稳定触发安全阀。
- 其余文件（`mock_llm.py`、`harness/budget.py`、`harness/loop_detector.py`）与 v4 完全一致。

## 核心设计

`needs_compression` 用字符数估算 token 占用，足够教学演示用；生产系统通常换成真实的 tokenizer 计数，接口形状不变。

`CompressionGuard` 独立成一个类而不是一个裸计数器，是延续 v2 `Budget` 的设计模式：一个对象只负责"记账 + 判断是否耗尽"。**熔断检查必须在压缩动作之前**——不能先压缩再判断，否则第 `max_compressions + 1` 次会白白再做一次无意义的压缩。

`compress_history` 不调用真实 LLM 做摘要（本项目全程不依赖网络），而是用一个确定性的占位摘要（"已将 N 条历史消息压缩为摘要"）代表"这里本该有一次真实的 LLM 摘要调用"。生产实现里这一步会换成对 LLM 的一次调用，压缩本身逻辑（保留 system + 最近 N 条、其余替换）保持不变。

## 如何运行 demo

```bash
python main.py --scenario oversized_tool_output --max-steps 30
```

实际输出：
```
[结果] 查询完成。
[LLM 调用次数] 11
```

10 次 `search_web` 调用（每次 query 参数都不同，避免撞上 v3 遗留的循环检测——早期版本里这 10 次调用参数完全相同，会被循环检测在第 5 次后禁用工具，导致脚本化的 mock LLM 在第 6 次调用时崩溃）全部顺利执行，模型正常返回"查询完成。"结束对话。用默认的 `char_threshold=4000` 时，这个场景累积的历史总量还不足以触发压缩安全阀；想亲眼看到熔断效果，参考 `tests/test_compression_guard.py` 里用的更激进的 `char_threshold=100`。

## 局限性

现在系统一共有四层独立的防护（预算、循环检测、裁剪、压缩安全阀），但它们的顺序、交互、以及"发生冲突时听谁的"还没有专门验证过——目前只是简单地依次执行。如果模型输出的工具调用本身格式就有问题（比如调用了一个不存在的工具、或者漏填了必填参数），当前所有版本都没有防护，会在 `tool_registry[call["name"]]` 这一步直接抛异常崩溃。这正是 v6 要解决的问题：执行工具之前先校验，校验失败把错误回填给模型而不是让进程崩溃。
