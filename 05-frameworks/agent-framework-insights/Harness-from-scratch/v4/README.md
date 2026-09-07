# v4：上下文裁剪

## 本版目标

工具返回的结果会不断塞进消息列表，上下文窗口是硬性资源。这一版加入**周期性裁剪**：定期清理较旧的工具输出，只保留最近 N 条完整消息，并支持按工具名豁免（比如 `read_file` 的原文不能清，模型编辑代码要依赖它）。

## 新增/修改文件（对照 v3）

- 新增 `harness/context_manager.py`：`compact_if_needed(messages, iteration, config)`，每隔 `trigger_every` 轮触发一次裁剪，把 `keep_recent_count` 之前的旧 `tool` 消息内容替换成 `[cleared: N chars]` 占位标记，`exempt_tools` 里的工具名跳过。
- 修改 `harness/loop.py`：`run_agent()` 新增 `compact_config` 参数，在每轮调用 LLM 之前跑一次 `compact_if_needed`。
- 修改 `scenarios.py`：新增 `long_search_session`（连续 8 次搜索调用）用来触发裁剪。
- 修改 `main.py`：新增默认裁剪配置 `DEFAULT_COMPACT_CONFIG`（豁免 `read_file`）。
- 其余文件（`mock_llm.py`、`tools.py`、`harness/budget.py`、`harness/loop_detector.py`）与 v3 完全一致。

## 核心设计

裁剪策略必须可配置，因为"哪些内容能清"是业务相关的判断：搜索结果、日志这类一次性信息可以安全裁剪，但代码编辑类场景里 `read_file` 的原文清了模型就没法正确 `edit`。`exempt_tools` 就是为了把这个业务判断暴露成配置项，而不是写死在代码里。

裁剪只替换 `content`，不删除消息本身——保留消息结构（`role`、`name`）方便后续排查是"这一步确实调用过某个工具"，只是内容被清空了。

## 如何运行 demo

```bash
python main.py --scenario long_search_session
```

## 局限性

裁剪只是把旧内容换成一个短占位符，**并不会真正大幅压缩已经很长的单条消息**，也没有基于 token 数的整体水位控制——如果每条工具返回本身就很长，裁剪掉的这几条省下来的空间可能远远不够。而且目前完全没有对"整个上下文是不是已经太大了"做出判断和响应。这正是 v5 压缩安全阀要解决的问题：基于总量水位触发的全量摘要压缩，以及防止压缩本身失控的熔断机制。
