# 课程导读

> 本课程是对开源项目 [earendil-works/pi](https://github.com/earendil-works/pi)（Pi Agent Harness）的系统性整理，目标是让你从「会用」走到「懂原理」，最终具备阅读、扩展、甚至改造这套编码 Agent 引擎的能力。

## 什么是 Pi

Pi 是一个**极简终端编码 Agent（coding agent）项目**，对外提供一个可交互的命令行工具 `pi`。它的定位不是"又一个 AI 聊天客户端"，而是一套可编程、可扩展的 **Agent 运行时（Agent Harness）**：

- 核心保持精简，几乎所有能力（工具、命令、UI、主题）都通过 TypeScript 扩展、Skills、Prompt 模板等机制挂载；
- 支持 OpenAI、Anthropic、Google、Amazon Bedrock 等多家模型厂商，统一在一层 API 之上；
- 既可以作为终端里的交互式工具直接使用，也可以通过 SDK、RPC、JSON 事件流等方式被其他程序编程调用；
- 采用 npm workspaces 管理的 monorepo，代码按职责拆分为 `agent`（运行时）、`ai`（多模型层）、`coding-agent`（CLI 与内置工具）、`tui`（终端渲染）、`protocol`/`server`/`client`（服务化能力）、`telemetry`（遥测）等十余个包。

## 课程设计思路

课程按照"**先会用，再懂原理，最后能扩展**"的顺序组织，分为四条主线：

1. **快速上手**（第 01 章）：安装、认证、第一次会话、CLI 基本用法、Provider 与个性化配置——让你在最短时间内把 `pi` 跑起来。
2. **仓库全景与工程实践**（第 02 章）：monorepo 的包职责地图、构建测试流程、发布与供应链安全、安全模型与容器化沙箱——建立对整个项目工程侧的整体认知，这是理解后续原理章节的地图。
3. **核心原理**（第 03～07 章）：这是本课程的重点，逐层拆解 Agent 运行时（`packages/agent`）、多模型统一层（`packages/ai`）、内置工具与扩展系统（`packages/coding-agent`）、终端 UI 差分渲染（`packages/tui`）、协议化与服务端/客户端架构（`packages/protocol`/`server`/`client`）、遥测体系（`packages/telemetry`）。每一章都会摘录真实源码并逐段讲解设计意图，而不是停留在 API 文档层面。
4. **工程质量与延伸**（第 08～09 章）：测试策略与评测体系（faux provider、evals）、课程总结与进阶学习路径。

## 适合谁学

- 已经会用 pi（或类似的 Claude Code / Codex CLI 等编码 Agent）作为日常工具，想理解"它到底是怎么工作的"的开发者；
- 想基于 pi 的 Agent 运行时（`@earendil-works/pi-agent-core`）或多模型层（`@earendil-works/pi-ai`）构建自己的 Agent 产品的工程师；
- 想为 pi 编写扩展（Extension）、Skills、自定义 Provider 的贡献者；
- 对"Agent 工具调用循环""上下文压缩""终端差分渲染""厂商无关的 LLM 抽象层"等主题感兴趣、希望有一个真实工业级代码案例可以参照学习的人。

## 前置知识

- 具备基本的 TypeScript/Node.js 阅读能力；
- 了解大语言模型（LLM）的基本概念（对话、system prompt、工具调用/function calling、流式输出）；
- 不需要提前了解 pi 项目本身，本课程会从零开始介绍。

## 学习方式建议

- 每篇文章都配有可实际执行的命令或练习，建议对照本地克隆的仓库边读边操作；
- 涉及源码解读的章节，文中会标注具体文件路径（如 `packages/agent/src/agent-loop.ts`），建议打开对应文件对照阅读，比只读课程文字收获更大；
- 课程各章相对独立，如果你已经会安装使用 pi，可以直接从第 02 章或第 03 章开始。

## 课程目录

完整的目录导航见仓库根目录的 [README.md](../README.md)。
