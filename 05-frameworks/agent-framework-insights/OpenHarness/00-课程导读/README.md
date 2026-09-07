# 课程导读

> 本课程是对开源项目 [HKUDS/OpenHarness](https://github.com/HKUDS/OpenHarness)（CLI 命令 `oh`，一个开源的 Python 版 Claude Code 复刻）的系统性整理，写法与姊妹课程 [PI 课程](../../PI/00-课程导读/README.md)、[DeepSeek Harness 课程](../../DeepSeek-Harness/00-课程导读/README.md)、[Hermes Agent 课程](../../Hermes-Agent/00-课程导读/README.md)一致：先建立整体地图，再逐层拆开源码，每一篇都会摘录真实代码并讲清楚设计动机，而不是停留在使用文档层面。

## 什么是 OpenHarness

OpenHarness（`oh`）是香港大学数据科学研究院（HKUDS）开源的一个 agent harness，`pyproject.toml` 里给自己的定位非常直白——"Open-source Python port of Claude Code, an AI-powered CLI coding assistant"。这个定位决定了它和前三套姊妹课程讲的项目走了一条完全不同的路：PI、DeepSeek Harness、Hermes Agent 都是"参照 Claude Code 这类产品的思路、用自己的架构哲学重新设计"的独立系统，而 OpenHarness 选择了另一条更直接的路——**尽可能逐工具、逐机制地复刻 Claude Code 本身的行为**：40 多个内置工具的名字和语义与 Claude Code 官方工具集高度重合，权限模式、Skills 机制兼容 `anthropics/skills`、Plugins 兼容 Claude-style plugin 规范，甚至认证体系里还专门做了"复用本地已登录的 Claude Code/Codex CLI 凭据"这种只有"复刻者"才会去做的适配。这决定了本课程一个贯穿始终的视角：**不只是讲 OpenHarness 自己的代码，还要不断追问"这里为什么要长得和 Claude Code 一样"**。

但 OpenHarness 并不只是一个复刻壳。围绕核心 Agent Harness，它还长出了几块 Claude Code 本身没有的东西，也是本课程用力最多的部分：

- **双前端架构**：核心逻辑是纯 Python，但主力交互界面是一个独立的 Ink/React TypeScript 子进程（`frontend/terminal/`），Python 后端通过一套自定义的 JSON 行协议驱动它渲染；另外还有一个纯 Python 的 Textual 备用界面，同一套 `RuntimeBundle` 契约，两条完全不同的实现路径。
- **`ohmo`：基于 OpenHarness 构建的个人 Agent App**。它不是 core 的一个模式，而是一个独立打包、依赖 `openharness` 的顶层项目，用 `soul.md`/`identity.md`/`user.md`/`BOOTSTRAP.md` 这类可编辑 Markdown 文件塑造人格，再通过一个多 Profile、多 Channel 的 Gateway 把这个人格接进 Telegram、Slack、Discord、飞书、钉钉、Matrix、WhatsApp、QQ、Email、mochat 十种即时通讯平台，配合 Cron 调度做到"不等你发消息，它也能主动找你"。
- **Swarm/Coordinator 多智能体体系**：git worktree 隔离的团队协作、进程内与子进程两种执行后端、一套把"怎么编排"直接写进系统提示里的 coordinator 工作流，以及独立于两者之外、专门负责"驱动一个 OpenHarness 会话"的 Bridge 编程接口。
- **Autopilot**：一个几乎零运维成本的可观测性方案——运行快照定期写成一份 JSON，配合一个独立的 React/Vite 静态站点渲染成仪表盘，不需要常驻服务，甚至可以直接发布到 GitHub Pages。

## 课程设计思路

课程延续"先会用，再懂原理，最后能扩展"的主线，全课程分为十条主线：

1. **快速上手**（第 01 章）：一键安装、CLI 与 TUI 速览、Provider Workflow 与 Profile 机制、`--dry-run` 安全预览、`ohmo` 初探——五篇文章建立起对 `oh` 和 `ohmo` 的第一手直觉，也为后面每一章的源码级深挖埋下线头。
2. **仓库全景与工程实践**（第 02 章）：`src/openharness/` 下 30 个子包 + `ohmo/` + 两个独立前端项目的包职责地图、双前端架构的完整驱动链路、配置与路径解析体系、测试策略与工程规范。
3. **Agent 核心循环**（第 03 章）：`run_query()` 里那个不起眼的 `while` 循环才是整个引擎的心脏——流式工具调用、Provider 抽象与多模型适配、消息状态机与自动压缩、订阅复用与 OAuth 认证。
4. **工具生态与扩展**（第 04 章）：40 多个内置工具、Skills 按需加载、Plugins 插件系统、MCP 客户端集成、事件驱动的 Hooks 机制——这是"复刻 Claude Code"这条主线体现得最密集的一章。
5. **治理与安全**（第 05 章）：多级权限模式的九步决策链、Docker 沙箱执行与路径校验双重防线。
6. **记忆与会话**（第 06 章）：`CLAUDE.md`/`MEMORY.md` 的发现注入与压缩、会话存储与 Resume 机制、从对话里自动提炼用户偏好的个性化系统。
7. **多智能体协作**（第 07 章）：Swarm 架构（Team/Worktree/Mailbox）、进程内与子进程两种执行后端、Coordinator 编排模式、Task 生命周期与 Bridge 桥接——本课程篇幅和概念密度都数一数二的一章。
8. **`ohmo` 与多平台网关**（第 08 章）：Soul/Identity/Memory 的人格化设计、Gateway 网关的消息路由链路、十种 IM Channel 实现对照、Cron 调度与主动触发。
9. **可观测性与 Autopilot**（第 09 章）：运行快照服务与它的 React 仪表盘，唯一一篇同时横跨 Python 后端和前端两侧代码的文章。
10. **总结与延伸阅读**（第 10 章）：把 OpenHarness 放回 PI / DeepSeek Harness / Hermes Agent 的坐标系里做一次对照，给出进阶阅读路径。

## 适合谁学

- 已经会用 `oh`（或 Claude Code / Codex CLI / PI 等类似的编码 Agent）作为日常工具，想理解"它到底是怎么工作的"的开发者；
- 想搭一套自己的编码 Agent、又不想从零发明工具协议和权限模型的工程师——OpenHarness 大量"对齐 Claude Code"的设计选择本身就是一份现成的参考实现；
- 想给 OpenHarness 贡献新工具、新 Channel、新 Provider 适配器的贡献者；
- 想搭建自己的"个人 Agent"、对 `ohmo` 的人格化设计和多平台网关感兴趣的人；
- 对"多智能体协作""进程隔离与权限治理""事件驱动 Hooks""轻量可观测性方案"等主题感兴趣、希望有真实工业级代码案例参照学习的人；
- 已经学过姊妹课程（[PI](../../PI/00-课程导读/README.md)、[DeepSeek Harness](../../DeepSeek-Harness/00-课程导读/README.md)、[Hermes Agent](../../Hermes-Agent/00-课程导读/README.md)）的读者——四个项目解决的是同一类问题，OpenHarness 这条"贴身复刻 Claude Code"的路线和前三者的"另起炉灶"形成了鲜明对照，对照阅读收获会更大。

## 前置知识

- 具备基本的 Python 阅读能力（`async`/`await`、`asyncio.gather`、Pydantic 之类的类型化数据结构）；
- 了解大语言模型（LLM）的基本概念（对话、system prompt、工具调用/function calling、流式输出）；
- 不需要提前了解 OpenHarness 或 Claude Code 本身，本课程会从零开始介绍；如果用过 Claude Code，会在第 04 章读到大量"眼熟"的工具设计,这不是巧合。

## 学习方式建议

- 每篇文章涉及源码解读的地方都会标注具体文件路径（如 `src/openharness/engine/query.py`），建议对照本地克隆的仓库边读边操作，收获会比只读课程文字大得多；
- 各章相对独立：如果你已经会安装使用 `oh`，可以直接从第 02 章或第 03 章开始；如果你只关心"怎么给它接一个新的 IM 平台",可以直接跳到第 08 章第 3 篇；如果你只关心多智能体编排,直接从第 07 章开始也不影响理解；
- 课程里多处会诚实指出源码中的真实瑕疵（文档字符串与实现不一致、声明了却从未真正接线的配置项、名字相同但语义完全不同的两套"团队"概念等）,这些不是课程的疏漏,而是深入真实代码库时必然会遇到的东西——理解一个系统,既要理解它设计对的地方,也要理解它还没打磨到位的地方；
- 官方 `README.zh-CN.md` 本身写得很清楚，课程会在合适的地方直接引用，而不是重复劳动。

## 课程目录

完整的目录导航见仓库根目录的 [README.md](../README.md)。
