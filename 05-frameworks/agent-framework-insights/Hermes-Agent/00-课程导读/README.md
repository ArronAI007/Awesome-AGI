# 课程导读

> 本课程是对开源项目 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)（Hermes Agent）的系统性拆解，目标是让你从「会用」走到「懂原理」，最终具备阅读、扩展、甚至为这个项目贡献代码的能力。

## 什么是 Hermes Agent

Hermes Agent 是 [Nous Research](https://nousresearch.com) 开源的**自我进化 AI Agent**。它对外提供一个终端可执行命令 `hermes`，但定位远不止"又一个 AI 聊天客户端"：

- **闭环学习**：它会在复杂任务后自动从经验里提炼 Skill，Skill 在后续使用中持续自我改进；agent 管理的记忆会定期"自我提醒"去持久化知识；FTS5 全文索引让它能搜索自己过去的会话，并结合 [Honcho](https://github.com/plastic-labs/honcho) 做跨会话的用户建模。
- **双入口架构**：同一套核心既能以 `hermes` 启动为终端交互（CLI/TUI），也能以 `hermes gateway` 启动为常驻网关进程，同时对接 Telegram、Discord、Slack、WhatsApp、Signal 等多个消息平台——两种入口共享同一套 slash 命令注册表和 Agent 循环。
- **不挑执行环境**：内置七种终端后端（本地、Docker、SSH、Singularity、Modal、Daytona、Vercel Sandbox），Daytona/Modal 还支持"空闲休眠、按需唤醒"的 Serverless 持久化，跑在 5 美元 VPS 上也没问题。
- **不挑模型**：`hermes model` 一条命令切换 provider/模型，内置数十家 provider 的 Profile（OpenRouter、Anthropic、Bedrock、Nous Portal 等），也支持 Nix、pip entry point 等多种方式扩展。
- **内置调度与委派**：cron 调度器可以把日报、夜间备份这类任务用自然语言描述后无人值守运行；还支持派生隔离子代理并行处理工作流。

技术栈以 Python 为主，代码按职责分布在 `agent/`（Agent 核心与工具执行）、`hermes_cli/`（CLI 与配置）、`cli.py`（终端 REPL）、`gateway/` 与 `tui_gateway/`（消息网关与现代 TUI）、`providers/` + `plugins/model-providers/`（模型 Provider 注册）、`plugins/`（平台与功能插件）、`tools/`（内置工具实现）等目录。

## 课程设计思路

课程按照"**先会用，再懂原理，最后能扩展**"的顺序组织，围绕以下几条主线展开：

1. **快速上手**（第 01 章）：安装、CLI 与 Gateway 双入口速览、Slash 命令体系、Provider 与模型配置、Profile 多实例与个性化——让你在最短时间内把 `hermes` 跑起来，并建立对整个项目"入口在哪、配置在哪"的第一手认知。
2. **仓库全景与工程哲学**（第 02 章）：巨型模块化的取舍、`AGENTS.md` 这份内部工程手册、依赖与发布策略。
3. **Agent 核心循环**（第 03 章）：Agent 主循环、工具调用、系统提示词的构造方式。
4. **多 Provider 与工具系统**（第 04 章）：Provider Profile 注册机制、工具集（toolset）与内置工具实现。
5. **终端后端与执行安全**（第 05 章）：本地/Docker/SSH/Modal 等七种执行后端、命令审批与沙箱隔离。
6. **记忆状态与压缩**（第 06 章）：会话状态机、上下文压缩、`hermes_state*` 系列模块。
7. **Skills 自我进化学习环**（第 07 章）：Skill 的创建、自我改进、Skills Hub 生态。
8. **插件系统与协议生态**（第 08 章）：`plugins/` 插件契约、MCP 集成。
9. **多智能体网关与调度**（第 09 章）：消息网关架构、cron 调度、子代理委派与并行。
10. **界面层**（第 10 章）：TUI 差分渲染、CLI/TUI/Gateway 共享的 slash 命令层。
11. **测试评估与研究工具**（第 11 章）：测试策略、批量轨迹生成与轨迹压缩。
12. **总结与延伸阅读**（第 12 章）。

完整目录导航见仓库根目录的 [README.md](../README.md)。

## 适合谁学

- 已经在用 Hermes Agent（或 Claude Code、Codex CLI、OpenClaw 等同类工具）作为日常工具，想搞懂"它到底是怎么工作的"的工程师；
- 想基于 Hermes 的 Agent 核心、工具系统或网关架构构建自己 Agent 产品的开发者；
- 想为 Hermes 贡献 Provider Profile、平台适配器（Platform Adapter）、工具或 Skill 的贡献者；
- 对"多平台消息网关""Agent 学习闭环""多实例隔离（Profile）""终端沙箱后端"等主题感兴趣，希望有一个真实的、超大规模工业级代码案例可以参照学习的人。

## 前置知识

- 具备基本的 Python 阅读能力（不要求精通，但要能看懂 `argparse`、装饰器、`dataclass` 这类常见写法）；
- 了解大语言模型（LLM）与 Agent 的基本概念（对话、system prompt、工具调用/function calling、流式输出）；
- 不需要提前了解 Hermes Agent 项目本身，本课程会从零开始介绍。

## 学习方式建议

- **这是一个比 PI、DeepSeek Harness 大得多的仓库**：核心文件普遍是万行级别的巨型模块（`cli.py` 约 2 万行、`hermes_cli/main.py` 近 1.5 万行、`hermes_cli/config.py` 6000+ 行）。不要试图通读这些文件，也不用死记行号——本课程标注的行号仅供参考，请习惯用 `grep -n` / ripgrep 定位关键函数名、类名、字符串常量再对照阅读；
- 每篇涉及源码解读的章节都会标注具体文件路径，建议对照本地克隆的仓库边读边操作；
- 仓库根目录的 `AGENTS.md`（约 95KB）是理解这个项目工程实践的第一手资料，里面记录了大量真实的设计决策和历史故障编号，值得单独通读一遍，第 02 章会重点展开；
- 各章相对独立，如果你已经会安装使用 Hermes，可以直接从第 02 章或第 03 章开始。

## 与其他课程的关系

本仓库还收录了另外两门同类课程：《PI》（`earendil-works/pi`，TypeScript 编写的极简终端编码 Agent）和《DeepSeek Harness》。三者解决的是同一类问题——"如何构建一个可扩展、可编程的 Agent 运行时"——但选择了三条截然不同的工程路径：Pi 追求极简与 monorepo 分包，Hermes Agent 走的是"单体 Python 大文件 + 插件化边缘扩展"的路线,并额外把"多平台消息网关"和"自我进化学习"作为核心卖点。建议在学完某一门之后,对照阅读另外两门,会对"同一个问题不同工程哲学下的取舍"有更具体的体感。
