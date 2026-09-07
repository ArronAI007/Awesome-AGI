# Harness from Scratch：渐进式 Agent Harness 教程

`agent-framework-insights` 仓库里的 `PI/`、`DeepSeek-Harness/` 两套课程拆解的是**现成的开源 Agent Harness 项目**。这个目录不一样：从一个没有任何防护的裸循环开始，一个版本只加一个优化点，逐步搭出一个工业级水准的 Agent Harness。

每个 `v{N}/` 目录都是一个**完全自包含、可直接运行**的最小 Python 项目——不依赖真实 API Key（内置脚本化的 Mock LLM 和 Mock 工具），也不依赖其他版本目录。想理解某个优化点是怎么落地的，直接对比 `v{N-1}` 和 `v{N}` 的文件差异即可：

```bash
diff -rq v2 v3   # 看 v3 相对 v2 新增/修改了哪些文件
```

## 路线图

| 版本 | 新增能力 | 一句话说明 |
|---|---|---|
| [v1](v1/README.md) | 裸循环骨架 | 无防护的 `while True` 循环，demo 演示一次停不下来的失控场景 |
| [v2](v2/README.md) | 执行预算 | 步数计数器 + 上限熔断 |
| [v3](v3/README.md) | 循环空转检测 | 工具调用参数哈希 + 连续失败率检测，临时禁用问题工具而不是杀死整个任务 |
| [v4](v4/README.md) | 上下文裁剪 | 周期性清理旧的工具输出，支持按工具名豁免 |
| [v5](v5/README.md) | 压缩安全阀 | 高水位线触发全量摘要压缩 + 最大压缩次数熔断，防止"摘要的摘要"死循环 |
| [v6](v6/README.md) | 输出校验与自愈 | 工具调用前校验存在性/必填参数，错误回填上下文让模型自纠 |
| [v7](v7/README.md) | 里程碑：整合版 | 合并 v2~v6 全部防护为一个完整骨架，集成测试证明多层防护协同生效 |
| [v8](v8/README.md) | 结构化错误处理与重试退避 | 区分可重试/不可重试错误；指数退避重试；单工具级熔断器 |
| [v9](v9/README.md) | 会话持久化与断点续跑 | 消息历史落盘 JSONL；进程重启后可从断点继续跑 |
| [v10](v10/README.md) | 并发与超时取消 | `run_agent` 转为 async；同一轮内的多个工具调用并发执行；超时自动取消，不拖死整个循环 |
| [v11](v11/README.md) | 安全权限沙箱 | allow/ask/deny 三态权限规则，执行前拦截危险操作 |
| [v12](v12/README.md) | 可观测性与成本核算 | 结构化事件日志（JSONL）；token/成本估算；运行报告导出 |
| [v13](v13/README.md) | 自动化评估框架 | 复用已有场景 + 期望断言批量评估；通过率/平均调用次数汇总；基线回归对比 |
| [v14](v14/README.md) | 动态工具/技能插件化 | `ToolRegistry` 支持运行时注册新工具；v6 校验、v11 权限检查零改动自动适配 |
| [v15](v15/README.md) | 多智能体协作 | `delegate_task` 工具委派子任务给独立子 agent，各自独立的上下文与预算，结果摘要回填主循环 |

**v1~v15 全部完成。** 从裸循环到工业级多智能体协作，完整的十五个版本可以按顺序阅读，每一版只看"和上一版本的 diff"。

## 阅读顺序

按版本号顺序读。每一版本的 `README.md` 固定包含：本版目标、新增/修改文件、核心设计、如何运行 demo、局限性（引出下一版）。建议先读 README 再看代码，最后跑一遍 `pytest`。

设计文档：[`docs/superpowers/specs/2026-08-28-progressive-harness-series-design.md`](docs/superpowers/specs/2026-08-28-progressive-harness-series-design.md)
