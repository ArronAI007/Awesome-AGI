# 课程导读

> 本课程是对开源项目 [DeepSeek Harness](https://github.com/deepseek-ai)（内部/对外代号 `dsh`，由 DeepSeek AI 开发的 agent harness）的系统性整理，目标是让你从「会用」走到「懂原理」，最终具备阅读、扩展、甚至改造这套编码 Agent 引擎的能力。写法与姊妹课程 [PI 课程](../../PI/00-课程导读/README.md) 一致：先建立整体地图，再逐层拆开源码，每一篇都会摘录真实代码并讲清楚设计动机，而不是停留在使用文档层面。

## 什么是 DeepSeek Harness

DeepSeek Harness（`dsh`）是 DeepSeek AI 开源的一个 **agent harness（智能体运行框架）**，定位与 Claude Code、OpenAI Codex CLI、以及姊妹课程讲的 `pi` 属于同一类产品：一个可以在终端和浏览器里跑的、支持多模型、多工具、可插拔扩展的编码 Agent 运行时。但它在架构选择上走了一条相当独特的路：

- **一切皆插件**：整个运行时构建在 [Cordis](https://github.com/cordiverse/cordis) 这个"万物皆插件"的 Meta-Framework 之上，并把 Cordis 及其生态库**源码 vendor 进仓库**（`vendor/`），而不是当作普通 npm 依赖——框架层完全由项目自己拥有、可审计、可打补丁。
- **能力以"Seam（服务缝隙）"的方式组织**：几乎每一类能力（文件系统、Shell、终端、沙箱、LLM、会话持久化、Web 搜索……）都被拆成"抽象接口定义 → 一个或多个 Provider 实现 → 面向模型的 Tool 消费者"的三元结构，换存储后端、换沙箱实现、换模型厂商都只是插拔一个 Provider 包。
- **Host 与 Client 物理/类型双重分离**：Node 宿主进程（Host）负责跑 Agent 循环、工具执行、持久化；浏览器端（Client）是一整套插件化的 UI 组件，两者通过编译期生成的类型安全 RPC（Typert）和 WebSocket 通信，互不污染类型系统。
- **真正的跨语言边界**：既有用纯 C11 手写 Linux Landlock 沙箱启动器的 `native/landlock-run`，也有让 Python 用户把整个 Node 运行时当子进程驱动的 `python/sdk`（NDJSON-RPC over stdio）。
- **工程治理极其严格**：`packages/*/*/src` 逐文件 100% 测试覆盖率、Registrations-are-effects（一切注册都可逆卸载）、Model-visible ⟺ logged（模型看到的一切都必须能从会话事件日志重建）等规则被写进 `AGENTS.md` 强制执行。

## 课程设计思路

课程延续"**先会用，再懂原理，最后能扩展**"的主线，但因为 dsh 的核心是一套插件框架，比 `pi` 多了一层"框架基石"必须单独讲清楚，否则后面所有"能力扩展"都无法理解。全课程分为六条主线：

1. **快速上手**（第 01 章）：环境准备、CLI 与 Web UI、Profile 机制、Provider 配置、权限预设——让你在最短时间内把 `dsh` 跑起来，并对它的运行形态有直觉认识。
2. **仓库全景与工程实践**（第 02 章）：229 个叶子包的 monorepo 地图、Host/Client 双面构建体系、分层测试与 CI 门禁、vendoring 治理——建立理解后续所有章节所需的工程地图。
3. **Cordis 插件框架基石**（第 03 章）：Context / Service / Plugin / Typed Events 四个核心概念，以及 Profile-Bundle-Preset 装配机制。**这是本课程和 PI 课程最大的不同之处**：不理解 Cordis，后面讲的"能力 Seam""可逆注册"都无从谈起。
4. **Agent 核心循环**（第 04 章）：`ReactLoopAgent` 的 `kick → turn → step` 驱动模型、会话事件溯源、流式输出管道、上下文压缩与 Checkpoint 持久化、错误重试与取消——这是引擎的心脏。
5. **能力扩展范式与跨语言边界**（第 05～07 章）：Capability Seam 三元结构、工具注册与执行管线、权限审批与多沙箱后端、内置工具全解析、Native 沙箱内核与 Python SDK 桥接、Host/Client RPC 生成、子代理与工作流引擎——这是本课程篇幅最大的部分，逐一拆开 dsh"插件化能力"的具体案例。
6. **工程质量与总结**（第 08～09 章）：测试哲学、文档治理规范、故障复盘（Postmortem）、课程总结与和 Claude Code / Codex / pi 的对比、进阶阅读路径。

## 适合谁学

- 已经会用 `dsh`（或 Claude Code / Codex CLI / pi 等类似的编码 Agent）作为日常工具，想理解"它到底是怎么工作的"的开发者；
- 想基于 Cordis 这类插件框架构建自己的 Agent 产品、或想理解"能力 Seam / 依赖注入"这套设计范式的工程师；
- 想为 dsh 编写新 Provider、新工具、新 Bundle 的贡献者；
- 对"事件溯源会话日志""ReAct 工具调用循环""多沙箱后端""Host/Client 类型安全 RPC""跨语言（C / Python）边界设计"等主题感兴趣、希望有真实工业级代码案例参照学习的人；
- 已经学过姊妹课程 [PI 课程](../../PI/00-课程导读/README.md) 的读者——两个项目解决的是同一类问题，架构选择却几乎处处不同，对照阅读收获会更大（课程中会在相关章节标注两者的差异点）。

## 前置知识

- 具备基本的 TypeScript/Node.js 阅读能力；
- 了解大语言模型（LLM）的基本概念（对话、system prompt、工具调用/function calling、流式输出）；
- 不需要提前了解 Cordis 或 dsh 项目本身，本课程会从零开始介绍；有 Koishi/依赖注入框架经验会更快上手第 03 章，但不是必需。

## 学习方式建议

- 每篇文章涉及源码解读的地方都会标注具体文件路径（如 `packages/core/agent-loop/src/agent.ts`），建议对照本地克隆的仓库边读边操作，收获会比只读课程文字大得多；
- 仓库体量很大（`packages/` 下约 49 个分类目录、219 个可发布叶子包），不需要通读全部代码——课程会明确指出每一章"值得精读"的最小文件集合；
- 官方文档本身质量很高且和源码保持同步（`docs/architecture.md`、`docs/cordis-primer.md`、`docs/tool-catalog.md` 等大量文档由脚本从源码生成），课程会在合适的地方直接引用，而不是重复劳动；
- 课程各章相对独立，如果你已经会安装使用 `dsh`，可以直接从第 02 章或第 03 章开始；如果你只关心"如何加一个新工具/新沙箱"，可以直接跳到第 05～06 章。

## 课程目录

完整的目录导航见仓库根目录的 [README.md](../README.md)。
