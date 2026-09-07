# 面向训练数据的独立压缩器 Trajectory Compressor

> 前两篇讲的 `agent/context_compressor.py` 服务于一个正在进行的对话——它必须小心翼翼,保证压缩之后模型还能无缝继续工作。`trajectory_compressor.py` 解决的是一个完全不同的问题:一批已经跑完的 agent 轨迹(可能来自 `batch_runner.py` 批量生产、也可能已经发布成 HuggingFace 数据集)体积超过了训练时的 `max_seq_len`,需要在保留训练信号质量的前提下压缩到可训练的 token 预算内。这是 Nous Research 作为一家同时做"agent 产品"和"模型训练"的机构,独有的一块拼图——本篇结合真实源码把这个独立工具的策略讲清楚。

## 学习目标

- 理解 `trajectory_compressor.py` 和 `agent/context_compressor.py` 的根本区别:服务对象不同(训练数据整理 vs 运行时对话延续)决定了两者在数据格式、约束条件、失败容忍度上的全部差异。
- 理解它的压缩算法:如何确定"受保护区域"、如何计算需要压缩多少、如何避免切断 `<tool_call>`/`<tool_response>` 配对。
- 理解为什么压缩后的摘要要以 `human` 角色插入,而不是 `gpt`(assistant)角色。
- 理解为什么 Nous Research 这样的模型训练机构需要一个独立于运行时之外的轨迹压缩工具——这是"agent 产品"与"训练数据生产线"合流的一个具体例子。
- 了解 `batch_runner.py`/`mini_swe_runner.py` 作为它的上游数据来源,以及它们之间的数据格式契约(`conversations` 字段,`from`/`value` 结构)。

## 根本区别:运行时压缩 vs 训练数据整理

`trajectory_compressor.py` 的模块 docstring 开门见山地写清楚了它的定位:

```python
# trajectory_compressor.py:1-16
"""
Trajectory Compressor

Post-processes completed agent trajectories to compress them within a target
token budget while preserving training signal quality.

Compression Strategy:
1. Protect first turns (system, human, first gpt, first tool)
2. Protect last N turns (final actions and conclusions)
3. Compress MIDDLE turns only, starting from 2nd tool response
4. Compress only as much as needed to fit under target
5. Replace compressed region with a single human summary message
6. Keep remaining tool calls intact (model continues working after summary)
"""
```

关键词是 **"Post-processes completed agent trajectories"**——它处理的对象是**已经跑完**的轨迹,而不是一个仍在进行中的对话。这个前提差异决定了它和 `context_compressor.py` 在几乎每个维度上都不同:

| | `agent/context_compressor.py` | `trajectory_compressor.py` |
|---|---|---|
| 处理对象 | 正在进行的活 session | 已经跑完、静态存档的轨迹 |
| 数据格式 | OpenAI 风格 `role`/`content` 消息列表 | ShareGPT 风格 `conversations` 里的 `from`/`value` turn 列表(`system`/`human`/`gpt`/`tool`) |
| 目标 | 让对话能继续下去,模型看得懂摘要+尾部 | 让整条轨迹能塞进训练时的 `max_seq_len`,同时不破坏训练信号质量 |
| 触发时机 | 每轮实时判断 `should_compress()` | 离线批处理,一次性对整个数据集(目录/JSONL/HF 数据集)跑一遍 |
| 失败容忍度 | 必须优雅降级(有确定性兜底摘要),不能让对话崩掉 | 摘要生成失败时同样有兜底文案,但更看重"是否要保留这条训练样本"这类数据集层面的判断 |
| 摘要角色 | 插入为专门标记的、带元数据的摘要消息,前端可识别渲染 | 插入为 `human` 角色的一条消息(细节见下文) |

`trajectory_compressor.py` 用的输入格式来自真实的 HF 数据集约定——脚本处理的字段是 `entry["conversations"]`,每个元素是 `{"from": "system"|"human"|"gpt"|"tool", "value": "..."}`:

```python
# trajectory_compressor.py:1021-1057(节选)
if "conversations" not in entry:
    ...
trajectory = entry["conversations"]
...
result["conversations"] = compressed_trajectory
```

## 压缩策略深挖

### 确定受保护区域:头部四种角色的首次出现 + 固定条数尾部

`_find_protected_indices` 先扫描出 `system`/`human`/`gpt`/`tool` 四种角色各自第一次出现的位置,按配置决定是否保护;再无条件保护最后 N 轮(默认 4):

```python
# trajectory_compressor.py:477-523
def _find_protected_indices(self, trajectory: List[Dict[str, str]]) -> Tuple[set, int, int]:
    n = len(trajectory)
    protected = set()
    first_system = first_human = first_gpt = first_tool = None
    for i, turn in enumerate(trajectory):
        role = turn.get("from", "")
        if role == "system" and first_system is None:
            first_system = i
        elif role == "human" and first_human is None:
            first_human = i
        elif role == "gpt" and first_gpt is None:
            first_gpt = i
        elif role == "tool" and first_tool is None:
            first_tool = i

    if self.config.protect_first_system and first_system is not None:
        protected.add(first_system)
    if self.config.protect_first_human and first_human is not None:
        protected.add(first_human)
    if self.config.protect_first_gpt and first_gpt is not None:
        protected.add(first_gpt)
    if self.config.protect_first_tool and first_tool is not None:
        protected.add(first_tool)

    for i in range(max(0, n - self.config.protect_last_n_turns), n):
        protected.add(i)

    head_protected = [i for i in protected if i < n // 2]
    tail_protected = [i for i in protected if i >= n // 2]
    compressible_start = max(head_protected) + 1 if head_protected else 0
    compressible_end = min(tail_protected) if tail_protected else n
    return protected, compressible_start, compressible_end
```

模块 docstring 里"从第二个 tool 响应开始压缩"的表述,对应的正是这里"保护首次出现的 `tool` 轮次、之后的 tool 响应才进入可压缩区间"这个效果——任务最初的一步操作(通常带着最关键的初始上下文)始终保留,真正体积庞大的、重复性高的中间过程(第二次及以后的工具调用往返)才是压缩目标。

### 绝不切断 `<tool_call>`/`<tool_response>` 配对

ShareGPT 风格的轨迹里,一个 `tool` 角色的轮次(承载 `<tool_response>` 内容)总是紧跟在触发它的 `gpt` 轮次(承载 `<tool_call>`)之后。如果压缩边界恰好落在 `tool` 轮次上,就会切出一个"有响应没调用"或"有调用没响应"的孤儿轮次,污染训练数据。`_is_boundary_clean`/`_snap_boundary` 专门处理这个问题:

```python
# trajectory_compressor.py:525-562
@staticmethod
def _is_boundary_clean(trajectory: List[Dict[str, str]], idx: int) -> bool:
    """A boundary is only clean when it sits at the very end of the
    trajectory or on a non-``tool`` turn."""
    return idx >= len(trajectory) or trajectory[idx].get("from") != "tool"

@classmethod
def _snap_boundary(cls, trajectory, idx, min_idx, max_idx) -> int:
    """Move a compression boundary onto the nearest clean turn boundary.

    Moving forward is preferred so that an orphaned ``tool`` turn is folded
    into the region that already holds its ``gpt`` turn; if no clean
    boundary exists ahead ... the boundary is moved backward instead.
    """
    forward = idx
    while forward < max_idx and not cls._is_boundary_clean(trajectory, forward):
        forward += 1
    if cls._is_boundary_clean(trajectory, forward):
        return forward
    backward = idx
    while backward > min_idx and not cls._is_boundary_clean(trajectory, backward):
        backward -= 1
    return backward
```

这套"先向前吸附、吸附不到再向后"的策略,和第一篇讲的 FTS5/schema 对账、第二篇讲的"绝不能在 toolResult 处切断"是同一类工程直觉的不同实现——凡是"调用-响应"这种强配对关系,压缩/裁剪算法都必须显式绕开它,而不是简单按 token 数或消息数硬切。

### 主循环:累积到够省为止,替换成一条摘要

`compress_trajectory` 的核心循环是"从可压缩区间起点开始累加 token,累加到能覆盖'需要节省的 token 数 + 摘要本身的 token 预算'时停止":

```python
# trajectory_compressor.py:796-844(节选)
tokens_to_save = total_tokens - self.config.target_max_tokens
target_tokens_to_compress = tokens_to_save + self.config.summary_target_tokens

accumulated_tokens = 0
compress_until = compress_start
for i in range(compress_start, compress_end):
    accumulated_tokens += turn_tokens[i]
    compress_until = i + 1
    if accumulated_tokens >= target_tokens_to_compress:
        break

if accumulated_tokens < target_tokens_to_compress and compress_until < compress_end:
    compress_until = compress_end
    accumulated_tokens = sum(turn_tokens[compress_start:compress_end])

compress_until = self._snap_boundary(trajectory, compress_until, compress_start, compress_end)
if compress_until <= compress_start:
    ...  # 快照后区间坍缩,放弃压缩

if sum(turn_tokens[compress_start:compress_until]) <= self.config.summary_target_tokens:
    ...  # 压缩这段换来的净收益是负的,不值得做
```

这里有两处"宁可不压缩也不做无意义的事"的保护:一是快照(snap)边界后如果可压缩区间坍缩成空,直接放弃;二是如果被压缩区域本身的 token 数还不如摘要预算大,压缩反而会让轨迹变长,同样直接放弃——这和第二篇讲的 `context_compressor.py` "如果生成的摘要比原文还长就判定失败"是同一种朴素但必要的自检:压缩存在的唯一意义是"变小",不产生净收益的压缩没有必要执行(还要多花一次昂贵的摘要 API 调用)。

确定好压缩区间后,用一次辅助模型调用生成摘要正文,再拼装最终轨迹:

```python
# trajectory_compressor.py:860-878(节选)
compressed = []
for i in range(compress_start):
    turn = trajectory[i].copy()
    if turn.get("from") == "system" and self.config.add_summary_notice:
        turn["value"] = turn["value"] + self.config.summary_notice_text
    compressed.append(turn)

compressed.append({
    "from": "human",
    "value": summary
})

for i in range(compress_until, len(trajectory)):
    compressed.append(trajectory[i].copy())
```

值得留意的一个具体设计:压缩摘要被插入为 **`human`(用户)角色**,而不是 `gpt`(assistant)角色。结合 `summary_notice_text` 默认文案——"Some of your previous tool responses may be summarized to preserve context."(会被追加到 system 消息里)——可以推断出这个设计的意图:摘要在语义上更接近"用户/环境告知模型此前发生了什么背景",模型看到它之后应该像收到一条新的用户输入一样继续往下推理和调用工具,而不是把它当成自己说过的话。这与训练目标是一致的:被压缩掉的中间轮次不再参与 loss 计算(它们被替换了),保留下来的尾部 `gpt` 轮次需要能在"读到一条 human 摘要"之后自然地继续工作,训练信号的因果链条(human 说了什么 → gpt 做了什么)不因为压缩而错位。

### 摘要生成的容错

摘要调用支持通过 `agent.auxiliary_client`(与运行时压缩共享同一套 provider 路由能力)或直接用 OpenAI 兼容 client 调用,默认走 OpenRouter:

```python
# trajectory_compressor.py:605-631(节选)
prompt = f"""Summarize the following agent conversation turns concisely. ...
Write the summary from a neutral perspective describing what the assistant did
and learned. Include:
1. What actions the assistant took (tool calls, searches, file operations)
2. Key information or results obtained
3. Any important decisions or findings
4. Relevant data, file names, values, or outputs
Target approximately {self.config.summary_target_tokens} tokens.
...
Write only the summary, starting with "[CONTEXT SUMMARY]:" prefix."""
```

多次重试失败后有一个确定性兜底文案(`"[CONTEXT SUMMARY]: [Summary generation failed - ...]"`),保证一次批处理任务不会因为单条轨迹的摘要 API 调用失败而整体中断——这一点上它和运行时压缩器的"确定性 fallback 摘要"思路是相通的,但目的不同:运行时的 fallback 要保证对话能继续,这里的 fallback 要保证一次跑几千条轨迹的批处理管道不会因为个别几次网络抖动就整体失败。

## 为什么 Nous Research 需要这样一个独立工具

批量跑 agent(`batch_runner.py`)产出的轨迹是真实、可用于监督微调(SFT)的训练数据,但 agentic 轨迹——尤其是工具调用密集的任务(终端操作、多文件读写、SWE 类任务)——很容易长到远超训练时设定的 `max_seq_len`。`CompressionConfig` 里的默认值能看出这个尺度感:

```python
# trajectory_compressor.py:83-100(节选)
tokenizer_name: str = "moonshotai/Kimi-K2-Thinking"
target_max_tokens: int = 15250
summary_target_tokens: int = 750
protect_last_n_turns: int = 4
summarization_model: str = "google/gemini-3-flash-preview"
```

一条超长轨迹如果直接丢弃(不训练)或者暴力截断(丢失结尾的关键动作和结论),都会造成训练数据的浪费或者信号缺失;`trajectory_compressor.py` 提供的是"保留任务开头的意图、保留结尾的关键动作和结论、把中间冗长但信息密度低的过程压缩成一段中立叙述摘要"这个折中方案——docstring 里"while preserving training signal quality"这半句话就是它存在的全部理由。

仓库里 `scripts/sample_and_compress.py` 印证了这套工具真实服务于"发布训练数据集"这件事——它直接从 HuggingFace 下载多个真实存在的数据集、抽样、跑压缩、再产出适配训练预算的版本:

```python
# scripts/sample_and_compress.py
"""
Sample and Compress HuggingFace Datasets

Downloads trajectories from multiple HuggingFace datasets, randomly samples them,
and runs trajectory compression to fit within a target token budget.
"""
DEFAULT_DATASETS = [
    "NousResearch/swe-terminus-agent-glm-kimi-minimax",
    "NousResearch/hermes-agent-megascience-sft1",
    "NousResearch/Hermes-Agent-Thinking-GLM-4.7-SFT2",
    "NousResearch/Hermes-Agent-Thinking-GLM-4.7-SFT1",
    "NousResearch/terminal-tasks-glm-hermes-agent",
]
```

这正是"agent 产品"和"训练数据生产线"合流的具体例子:同一个仓库,既要维护一个日常可用的 agent CLI/gateway(前两篇讲的一切:SessionDB、运行时压缩),又要为 Nous Research 自己训练下一代模型持续产出、清洗、压缩训练数据集——`trajectory_compressor.py` 就是这条数据生产线上专门负责"体积整理"的一环,而且是 PI、DeepSeek-Harness 这类纯 coding-agent 项目课程完全不会涉及的一类模块,因为那些项目本身不承担模型训练的职责。

## 上游调用方:`batch_runner.py` / `mini_swe_runner.py`

`trajectory_compressor.py` 不是被 `batch_runner.py` 直接函数调用的——两者之间是数据管道上下游的关系,通过约定好的 JSONL 字段格式衔接。`batch_runner.py` 的模块 docstring 明确写了它的产出格式:

```python
# batch_runner.py:1-11
"""
Batch Agent Runner

This module provides parallel batch processing capabilities for running the agent
across multiple prompts from a dataset. It includes:
...
- Trajectory saving in the proper format (from/value pairs)
- Tool usage statistics aggregation across all batches
"""
```

它在保存结果时,把 agent 运行产生的轨迹写进 `entry["conversations"]`:

```python
# batch_runner.py:490(节选)
"conversations": result["trajectory"],
```

这正是 `trajectory_compressor.py` 期望读取的字段名和结构。`mini_swe_runner.py`(另一个独立的、面向 SWE 类任务的批量运行器)的头部注释直接点名了这条契约:

```python
# mini_swe_runner.py:1-11
"""
SWE Runner with Hermes Trajectory Format

A runner that uses Hermes-Agent's built-in execution environments
(local, docker, modal) and outputs trajectories in the Hermes-Agent format
compatible with batch_runner.py and trajectory_compressor.py.
"""
```

也就是说,`batch_runner.py`/`mini_swe_runner.py` 是"生产原始轨迹"的上游,`trajectory_compressor.py`(通常经由 `scripts/sample_and_compress.py` 这类脚本封装)是"整理成可训练格式"的下游后处理步骤——两者靠一份稳定的 `conversations`/`from`/`value` 字段契约衔接,而不是直接的函数调用关系。`batch_runner.py` 本身的整体架构(数据集加载、多进程并行、checkpoint 容错、工具使用统计)留给第十一章详细展开。

## 小结与思考题

`trajectory_compressor.py` 和 `agent/context_compressor.py` 表面上都叫"压缩",内核却是两件事:一个要让对话能够继续下去,必须保证"看得懂、能干活";一个要让已经跑完的轨迹塞进训练用的 token 预算,必须保证"训练信号不失真"。它的压缩算法(保护首尾、只压中间、绝不切断工具调用配对、净收益检查)在直觉上和运行时压缩、和第一篇讲的 SessionDB 存储层设计遵循同一套工程原则,但服务的目标——离线整理 SFT 训练数据、支撑 Nous Research 自己的模型训练管道——是 PI、DeepSeek-Harness 这类课程完全没有涉及的独特领域,值得单独强调。

需要向你说明的一点是:由于 `trajectory_compressor.py` 与 `batch_runner.py` 之间没有直接的函数调用关系(不是"batch_runner 调用 trajectory_compressor"这种耦合,而是通过 `conversations` 字段格式契约衔接、由 `scripts/sample_and_compress.py` 这类独立脚本在两者之间起后处理作用),这一点与最初调研摘要里"批量跑一次性 upstream 调用"的表述略有出入,已经按实际代码结构在文中做了修正。

思考题:

1. 摘要被插入为 `human` 角色而不是 `gpt` 角色——如果一条训练轨迹里,压缩后紧跟在摘要后面的第一个 `gpt` 轮次本该是"回应上一个 human 提问"的语气,而不是"接收一段背景陈述后继续干活"的语气,这种角色错位会不会在 SFT 训练里引入系统性的风格偏差?你会怎么设计实验去检测这种偏差?
2. `_find_protected_indices` 只保护"第一次出现的" system/human/gpt/tool 各一条,而不是"第一轮完整的多轮交互"。如果任务的第一轮本身就产生了大量工具调用(比如一次性列出整个仓库结构),这种保护粒度会不会让"受保护头部"本身就占用了大部分的 `target_max_tokens`,导致中间可压缩区间名存实亡?
3. `scripts/sample_and_compress.py` 从多个真实的 HuggingFace 数据集采样再压缩,这意味着同一条原始轨迹可能会被不同的压缩参数(`target_max_tokens`、`summarization_model`)处理出多个版本。如果你要维护这样一条数据生产线,你会如何设计版本追踪,以确保训练时能明确知道某条样本经过了怎样的压缩历史?
