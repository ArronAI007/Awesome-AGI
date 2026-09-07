# Batch Runner 与训练轨迹生成

> `batch_runner.py`（1380 行）是一套面向"批量生成 tool-calling 训练数据"的并行运行器：给定一个 JSONL 数据集，它会用多进程池并行地把每一条 prompt 喂给真实的 `AIAgent`，按 `toolset_distributions.py` 定义的概率分布随机采样工具集合，把完整的对话轨迹写成 JSONL，并支持按内容匹配的方式从中断处断点续跑。它生产的原始轨迹，正是本课程第 6 章 `trajectory_compressor.py` 要处理的输入——一个是"生成"，一个是"压缩"，构成了 Hermes 背后 Nous Research 研究团队的一条完整数据生产线。

## 学习目标

- 理解 `batch_runner.py` 存在的目的：不是给终端用户用的功能，而是给 Nous Research 生成/收集下一代 tool-calling 模型训练数据的批处理工具。
- 读懂 `BatchRunner` 类如何把一个 JSONL 数据集切分成批次、用 `multiprocessing.Pool` 并行分发给多个 worker 进程执行。
- 理解断点续跑机制的核心设计——按 prompt 内容而非索引匹配已完成任务，以及为什么这比按索引匹配更健壮。
- 读懂 `toolset_distributions.py` 如何用"每个工具集独立按概率采样"的方式，为不同应用场景（如 `image_gen`）预设工具集合的分布。
- 理解 `batch_runner.py`（生成轨迹）与第 6 章 `trajectory_compressor.py`（压缩已生成轨迹）之间的上下游关系，不需要重复讲压缩算法本身。

## 一、这是什么：训练数据生产线的入口

`batch_runner.py` 顶部的 docstring 把用途讲得很直接：

```python
#!/usr/bin/env python3
"""
Batch Agent Runner

This module provides parallel batch processing capabilities for running the agent
across multiple prompts from a dataset. It includes:
- Dataset loading and batching
- Parallel batch processing with multiprocessing
- Checkpointing for fault tolerance and resumption
- Trajectory saving in the proper format (from/value pairs)
- Tool usage statistics aggregation across all batches

Usage:
    python batch_runner.py --dataset_file=data.jsonl --batch_size=10 --run_name=my_run
    python batch_runner.py --dataset_file=data.jsonl --batch_size=10 --run_name=my_run --resume
    python batch_runner.py --dataset_file=data.jsonl --batch_size=10 --run_name=my_run --distribution=image_gen
"""
```

这段话里"Trajectory saving in the proper format (from/value pairs)"是关键线索——`from`/`value` 是 ShareGPT 风格对话数据集常用的字段命名（一条消息标注"说话者是谁"和"内容是什么"），这说明 `batch_runner.py` 产出的 JSONL 直接面向后续的模型训练管线，而不是面向普通用户查看的会话记录。`AGENTS.md` 的项目结构一节里，`batch_runner.py` 被归类为"Parallel batch processing"，和 `run_agent.py`（`AIAgent` 核心循环）、`cli.py`（交互 CLI）并列成为"File Dependency Chain"图里三个直接依赖 `model_tools.py`/`tools/registry.py` 的顶层入口——也就是说，批量运行器复用的是和交互式 CLI 完全相同的 Agent 核心和工具发现机制，只是换了一种"驱动方式"：不是人在打字，而是从数据集里逐条取 prompt 喂给 Agent。

CLI 接口用 Google 的 `fire` 库构建（`fire.Fire(main)`），这意味着 `main()` 函数签名里的每一个具名参数都自动变成一个 `--参数名=值` 的命令行选项，不需要额外写 `argparse` 样板代码：

```python
# batch_runner.py
def main(
    dataset_file: str = None,
    batch_size: int = None,
    run_name: str = None,
    distribution: str = "default",
    model: str = "anthropic/claude-sonnet-4.6",
    ...
    reasoning_effort: str = None,
    reasoning_disabled: bool = False,
    prefill_messages_file: str = None,
    max_samples: int = None,
):
    ...

if __name__ == "__main__":
    fire.Fire(main)
```

参数覆盖面很能说明这是一个面向研究场景、而非面向终端用户的工具：`providers_allowed`/`providers_ignored`/`providers_order`/`provider_sort` 这类 OpenRouter 供应商偏好、`reasoning_effort`/`reasoning_disabled` 这类推理强度调节、`prefill_messages_file` 这类 few-shot 前置对话注入，都是数据生成场景才会关心的旋钮,普通交互式使用完全用不到。

## 二、`BatchRunner`：切分、并行、聚合

`BatchRunner.__init__` 做的第一件事是校验 `distribution` 参数合法、创建输出目录 `data/<run_name>/`、加载数据集并按 `batch_size` 切分成批次：

```python
# batch_runner.py
self.dataset_file = Path(dataset_file)
...
if not validate_distribution(distribution):
    raise ValueError(f"Unknown distribution: {distribution}. Available: {list(list_distributions().keys())}")

self.output_dir = Path("data") / run_name
self.output_dir.mkdir(parents=True, exist_ok=True)
self.checkpoint_file = self.output_dir / "checkpoint.json"
self.stats_file = self.output_dir / "statistics.json"

self.dataset = self._load_dataset()
if self.max_samples and self.max_samples < len(self.dataset):
    self.dataset = self.dataset[:self.max_samples]
self.batches = self._create_batches()
```

`_create_batches()` 只是简单地把数据集按 `batch_size` 切片，同时保留每条数据在原始数据集里的索引：

```python
# batch_runner.py
def _create_batches(self) -> List[List[Tuple[int, Dict[str, Any]]]]:
    batches = []
    for i in range(0, len(self.dataset), self.batch_size):
        batch = [(idx, entry) for idx, entry in enumerate(self.dataset[i:i + self.batch_size], start=i)]
        batches.append(batch)
    return batches
```

真正的并行发生在 `run()` 方法里，用标准库 `multiprocessing.Pool` 把每个批次分发给独立的 worker 进程，用 `pool.imap_unordered()` 而不是 `pool.map()`——这个选择意味着哪个批次先跑完就先收集哪个的结果，不用等待队列前面的慢批次，同时配合 `rich.progress.Progress` 画一个持续刷新的进度条：

```python
# batch_runner.py
with Pool(processes=self.num_workers) as pool:
    tasks = [
        (batch_num, batch_data, str(self.output_dir), completed_prompts_set, config)
        for batch_num, batch_data in enumerate(self.batches)
    ]
    with Progress(
        SpinnerColumn(), TextColumn("[bold blue]📦 Batches"), BarColumn(bar_width=40),
        MofNCompleteColumn(), TextColumn("•"), TimeRemainingColumn(),
        console=console, refresh_per_second=2, transient=False,
    ) as progress:
        task = progress.add_task("Processing", total=len(tasks))
        for result in pool.imap_unordered(_process_batch_worker, tasks):
            results.append(result)
            ...
```

值得注意的一处细节是 API key 的跨进程传递问题：`multiprocessing.Pool` 要求传给 worker 的参数能被 pickle 序列化，但如果认证方式是 Azure Foundry 的 Entra ID bearer token（一个返回短时效令牌的零参数可调用对象），闭包本身是不可 pickle 的。`run()` 里专门处理了这种情况：

```python
# batch_runner.py
# ``self.api_key`` may be a zero-arg callable (Azure Foundry Entra ID
# bearer provider). Such closures are not safely picklable across the
# multiprocessing.Pool boundary. Drop the callable here and let each
# worker rebuild its own provider via ``resolve_runtime_provider()``.
if callable(self.api_key) and not isinstance(self.api_key, str):
    worker_api_key = None
    print("ℹ️  Detected Entra ID bearer provider — workers will rebuild credentials from config.yaml in each process.")
else:
    worker_api_key = self.api_key
```

这是一处很具体的工程取舍：与其想办法把闭包序列化过进程边界（脆弱且容易踩坑），不如让每个 worker 进程各自根据 `config.yaml` 重新构建一份认证凭据——`azure-identity` 的令牌缓存本来就是进程内的，每个 worker 独立缓存反而更符合其设计假设。

`ALL_POSSIBLE_TOOLS` 是另一处值得一提的设计：

```python
# batch_runner.py
# All possible tools - auto-derived from the master mapping in model_tools.py.
# This stays in sync automatically when new tools are added to TOOL_TO_TOOLSET_MAP.
# Used for consistent schema in Arrow/Parquet (HuggingFace datasets) and for
# filtering corrupted entries during trajectory combination.
ALL_POSSIBLE_TOOLS = set(TOOL_TO_TOOLSET_MAP.keys())
```

`_normalize_tool_stats()` 用这份自动派生的全集补齐每条轨迹记录里缺失的工具统计字段（未使用的工具记 `{'count': 0, 'success': 0, 'failure': 0}`），保证所有输出 JSONL 记录有完全一致的 schema——这正是为了让后续用 HuggingFace `datasets` 库直接加载成 Arrow/Parquet 格式时不会因为 schema 不一致而报错，也是"这套工具服务于训练数据生产"这一定位的又一处佐证。

## 三、断点续跑：按内容匹配，而不是按索引

批量任务动辄跑几千条 prompt，中途中断（限流、机器重启、代码调整）几乎是常态。`AGENTS.md` 附近的测试文件命名（`test_batch_runner_checkpoint.py`、`test_batch_runner_discard_resume.py`、`test_batch_runner_durability.py`）也说明这块逻辑本身被反复加固过。核心机制是 `_scan_completed_prompts_by_content()`：

```python
# batch_runner.py
def _scan_completed_prompts_by_content(self) -> set:
    """
    Scan all batch files and extract completed prompts by their actual content.

    This provides a more robust resume mechanism that matches on prompt text
    rather than indices, allowing recovery even if indices don't match.
    """
    completed_prompts = set()
    batch_files = sorted(self.output_dir.glob("batch_*.jsonl"))
    for batch_file in batch_files:
        with open(batch_file, 'r', encoding='utf-8') as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get("failed", False):
                    continue
                prompt_text = _entry_prompt_text(entry)
                if prompt_text:
                    completed_prompts.add(prompt_text)
    return completed_prompts
```

这里的注释直接点出了设计初衷：按**内容**（prompt 文本本身）匹配已完成任务，而不是按数据集里的**索引**匹配。索引匹配的脆弱之处在于——如果两次运行之间数据集文件本身发生了任何变化（重新打乱顺序、去重、增删几条），索引和内容的对应关系就会错位，按索引续跑要么重复处理、要么遗漏处理；按内容匹配则完全不依赖数据集的物理顺序，哪怕数据集被重新整理过，只要某条 prompt 的文本此前已经被成功处理并写进了 `batch_*.jsonl`，续跑时就会正确跳过它。标记为 `failed` 的条目会被排除在"已完成"之外，保证会被重新尝试；而"discard 墓碑"（deliberately dropped，见 issue #93527 相关处理）则被算作已完成——因为这类条目是被评审逻辑主动丢弃的，重跑只会再次得到同样的丢弃结果。

`run(resume=True)` 用这份已完成集合过滤数据集、重新按 `batch_size` 切出待处理批次，并打印一份对比清晰的续跑摘要：

```python
# batch_runner.py
print("\n" + "=" * 70)
print("📊 RESUME SUMMARY")
print("=" * 70)
print(f"   Original dataset size:     {len(self.dataset):,} prompts")
print(f"   Already completed:         {len(skipped_indices):,} prompts")
print(f"   🎯 RESUMING WITH:          {len(filtered_entries):,} prompts")
```

检查点本身（`checkpoint.json`）用 `atomic_json_write()` 原子写入，并配合一把 `multiprocessing.Lock` 防止并发写坏文件——这是"批量任务中途崩溃后重新跑起来，不能读到一个写了一半的 JSON"这个常见问题的标准解法。

## 四、`toolset_distributions.py`：按场景预设工具集合的概率分布

批量生成训练数据时，如果每条轨迹都用完全相同的工具集合，模型学到的"什么时候该用什么工具"信号会很单一。`toolset_distributions.py` 解决的正是这个问题：把每个应用场景定义成一份"工具集合 → 出现概率"的映射，`image_gen` 分布是其中最典型的一个：

```python
# toolset_distributions.py
DISTRIBUTIONS = {
    "default": {
        "description": "All available tools, all the time",
        "toolsets": {
            "web": 100, "vision": 100, "image_gen": 100,
            "terminal": 100, "file": 100, "browser": 100
        }
    },
    "image_gen": {
        "description": "Heavy focus on image generation with vision and web support",
        "toolsets": {
            "image_gen": 90,   # 80% chance of image generation tools
            "vision": 90,      # 60% chance of vision tools
            "web": 55,         # 40% chance of web tools
            "terminal": 45
        }
    },
    # 还有 research / science / development / safe / balanced /
    # minimal / terminal_only / terminal_web 等场景
}
```

采样逻辑不是"从分布里选一个工具集"，而是让每个工具集独立地按自己的概率抛一次硬币，这样一条轨迹里可以同时激活多个工具集：

```python
# toolset_distributions.py
def sample_toolsets_from_distribution(distribution_name: str) -> List[str]:
    dist = get_distribution(distribution_name)
    selected_toolsets = []
    for toolset_name, probability in dist["toolsets"].items():
        if not validate_toolset(toolset_name):
            continue
        # Roll the dice - if random value is less than probability, include this toolset
        if random.random() * 100 < probability:
            selected_toolsets.append(toolset_name)

    # If no toolsets were selected, ensure at least one is picked
    if not selected_toolsets and dist["toolsets"]:
        highest_prob_toolset = max(dist["toolsets"].items(), key=lambda x: x[1])[0]
        if validate_toolset(highest_prob_toolset):
            selected_toolsets.append(highest_prob_toolset)
    return selected_toolsets
```

`image_gen` 分布里 `image_gen: 90`、`vision: 90`、`web: 55`、`terminal: 45` 意味着每条轨迹独立地有 90% 概率带上图像生成工具、90% 概率带上视觉工具、55% 概率带上网络工具——四个概率互相独立地抛硬币，因此实际出现的工具组合会有相当的多样性（可能只有 `image_gen`，也可能 `image_gen` + `vision` + `terminal` 同时出现），而不是四选一。最后那段"保底"逻辑处理了一种边界情况：如果一次采样恰好所有硬币都没中（低概率但确实会发生），至少强制选中概率最高的那个工具集，避免生成一条"什么工具都没有"的空轨迹。这套设计的价值在于：真实使用场景里，用户请求往往需要多个工具协同（生成一张图之前先搜一下参考、生成完再用视觉工具检查效果），概率化的独立采样比"每次固定用某一套工具"更能覆盖训练数据里工具组合的多样性,同时通过手动调节每个场景的概率表，研究人员可以刻意让某类场景（比如图像生成任务）里出现更多和该场景相关的工具组合，控制数据分布的倾向性。

## 五、和 `trajectory_compressor.py` 的上下游关系

`batch_runner.py` 产出的轨迹落在 `data/<run_name>/batch_*.jsonl` 里，本课程第 6 章讲过的 `trajectory_compressor.py` 正是消费这份输出的下一道工序——它的用法示例直接以 `data/my_run` 这个目录作为输入：

```python
# trajectory_compressor.py
"""
Trajectory Compressor

Post-processes completed agent trajectories to compress them within a target
token budget while preserving training signal quality.

Usage:
    # Compress a directory of JSONL files
    python trajectory_compressor.py --input=data/my_run
"""
```

两者的分工非常清楚：`batch_runner.py` 负责"生成"——并行驱动真实 Agent 在多样化的工具分布下完成任务，产出未经处理的原始轨迹；`trajectory_compressor.py` 负责"精加工"——对已经生成好的轨迹做离线压缩，把超长的中间轮次替换成摘要，在不破坏训练信号质量的前提下把轨迹控制在目标 token 预算内。这是一条典型的"生成 → 后处理"数据管线：前者关心的是任务覆盖面和工具分布的多样性，后者关心的是单条轨迹的长度分布是否适合拿去训练。压缩算法本身（如何选择保护区、如何生成摘要）已经在第 6 章详细讲过，这里不再重复。

## 小结与思考题

`batch_runner.py` 和 `toolset_distributions.py` 共同构成了 Hermes 数据生成管线的"生成"端：`fire` 驱动的命令行接口、`multiprocessing.Pool` 并行、按内容而非索引匹配的断点续跑、以及按场景预设概率分布的工具采样，这些设计全部服务于同一个目标——高效、可中断、可控地批量生产用于训练下一代 tool-calling 模型的对话轨迹。这是 PI 和 DeepSeek Harness 两门课程都没有涉及的一个模块类别：那两个项目定位都是"给终端用户/开发者用的 agent 产品"，测试和评测体系服务的是"这个产品本身好不好用"；而 Hermes 背后的 Nous Research 同时是一家做基础模型训练的机构，`batch_runner.py`/`toolset_distributions.py`/`trajectory_compressor.py` 这一整条链路服务的是另一个目的——把"agent 产品在真实使用中的行为"转化成"可以喂给下一次模型训练的数据"。这种"agent 产品"和"训练数据生产线"合流的思路，是理解 Hermes 为什么会同时维护如此多看似和终端用户体验无关的模块（`evals/`、`batch_runner.py`、`toolset_distributions.py`、`trajectory_compressor.py`）的关键背景。

思考题：

1. `sample_toolsets_from_distribution()` 里每个工具集独立抛硬币的采样方式，理论上可能采样出"逻辑上不太合理"的组合（比如某个场景下 `terminal` 和 `image_gen` 同时被选中，但该场景的 prompt 内容其实和终端操作毫无关系）。你会如何在不牺牲现有多样性收益的前提下，让采样结果和 prompt 本身的语义更相关？
2. 断点续跑用 prompt 文本做去重键，如果数据集里存在两条文本完全相同但期望产生不同轨迹的 prompt（比如故意用相同问题测试模型的不确定性/多样性），这套"按内容匹配"的机制会把第二条误判为"已完成"而跳过。这种场景在实践中大概率存在吗？如果存在，你会如何修改 `_entry_prompt_text()`/`_scan_completed_prompts_by_content()` 来正确区分它们？
3. `batch_runner.py` 和 `trajectory_compressor.py` 之间用"文件系统里的 `data/<run_name>/` 目录"作为隐式契约衔接，而不是通过某种更显式的接口（比如一个共享的 manifest 文件声明这批轨迹的 schema 版本、生成参数）。如果未来 `batch_runner.py` 的输出 schema 发生变化，`trajectory_compressor.py` 要如何在读取旧版本轨迹时保持兼容？
