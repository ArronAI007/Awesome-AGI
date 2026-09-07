# 课程导读

> 本课程是对开源项目 [openclaw/openclaw](https://github.com/openclaw/openclaw)（CLI 命令 `openclaw`，一个跑在你自己设备上、接入你已经在用的聊天软件的 AI 助理）的系统性整理，写法与姊妹课程 [PI](../../PI/00-课程导读/README.md)、[DeepSeek Harness](../../DeepSeek-Harness/00-课程导读/README.md)、[Hermes Agent](../../Hermes-Agent/00-课程导读/README.md)、[OpenHarness](../../OpenHarness/00-课程导读/README.md) 一致：先建立整体地图，再逐层拆开源码，每一篇都会摘录真实代码/官方文档并讲清楚设计动机，而不是停留在使用文档层面。

## 什么是 OpenClaw，以及一个特别的说明

OpenClaw 是这套课程系列迄今规模最大的项目——仅 `docs/` 目录就有 800 多篇文档，`src/gateway/` 一个子系统就有 2600 多个文件，还有 155 个 `extensions/`、23 个共享 `packages/`、macOS/iOS/Android/Linux 四个原生 App，以及一个独立的插件市场 ClawHub。README 给自己的定位是："It connects models, tools, messaging channels, and optional companion apps through one Gateway, for a single operator or for a team whose members trust each other"——一个由单一常驻 **Gateway** 统一调度模型、工具、消息渠道、设备的个人/团队助理平台。

正因为规模悬殊,这门课程和前四套姊妹课程的写法有一处关键不同：**它不追求覆盖每一个子系统的每一处细节，而是有意识地做了取舍**——核心架构（Gateway、Agent 循环、会话、安全模型）讲得和姊妹课程一样深，但面对 155 个扩展、几十种消息渠道、五十多个内置 Skill 这类"生态型"内容，课程选择精读几个代表性样本、归纳出共同契约，而不是逐个罗列。这本身也符合 OpenClaw 自己的产品哲学——VISION.md 里反复强调"核心保持精简，能力尽量长在插件/Skill/Channel/App 这一圈里"，课程的写法某种程度上是在呼应它自己的架构取舍。另外，这个项目的官方文档（`docs/`）质量很高、和源码保持同步，很多章节会直接大段引用文档原文作为一手资料，而不是仅仅转述源码——这一点也和姊妹课程"以源码为主"的打法略有不同。

围绕这个由单一 Gateway 支撑的核心，OpenClaw 长出了几块很有分量的东西，也是本课程用力最多的部分：

- **Gateway 是唯一的控制平面**：一台宿主机上只应该有一个 Gateway，所有客户端（CLI、Dashboard、TUI、原生 App）和所有设备（Node）都通过同一个 WebSocket 协议连接它，配对与设备信任贯穿始终。
- **Channels 把助理接进你已经在用的聊天软件**：WhatsApp、Telegram、Slack、Discord、Signal、iMessage、Matrix、飞书、Google Chat 等等，渠道适配器被要求"只做传输层"，业务逻辑统一收在核心里。
- **Nodes 与 Companion Apps 把能力延伸到具体设备**：macOS/iOS/Android/Linux 原生 App 可以把相机、屏幕、地理位置这些设备本地能力暴露给 Agent 调用。
- **Memory 与 Soul**：核心把"记忆"定义成一个互斥的插件槽位，同时自带一套"Soul"（长期人格/语气设定）和"Dreaming"（后台记忆整理巩固）机制。
- **安全被当作一等公民**：`SECURITY.md`、`AGENTS.md` 里"trusted gateway, untrusted execution, deterministic policy"这条架构论断贯穿了权限模式、沙箱、审批、审计的每一处设计。
- **ClawHub 插件市场**：官方明确希望核心持续瘦身，把可选能力沉淀到插件生态里，ClawHub 承担插件发现、发布者身份、来源与安全审查的角色。

## 课程设计思路

课程延续"先会用，再懂原理，最后能扩展"的主线，全课程分为十一条主线：

1. **快速上手**（第 01 章）：一键安装、CLI/Control UI 速览、Channels 与配对速览、模型配置速览、安全基线速览——建立第一手直觉。
2. **仓库全景与工程实践**（第 02 章）：pnpm workspace 与目录地图、Doctor 配置迁移契约、测试哲学与 CI、TypeBox → JSON Schema → Swift 的协议代码生成链路。
3. **Gateway 架构与协议**（第 03 章）：单一控制平面与 WS 协议、设备配对信任模型、多 Gateway 与远程访问、Health/Heartbeat 可观测性——这是整个项目的心脏。
4. **Agent 核心循环与会话**（第 04 章）：Agent Loop 总览、Session 状态机、上下文压缩与 Context Engine、Queue 与并发控制/Steering、多代理协作与 Delegate 架构。
5. **模型与 Provider 生态**（第 05 章）：Provider 抽象与 Failover、代表性适配器对照、System Prompt 组装与 Agent Workspace。
6. **工具生态：Tools / Skills / Plugins / MCP**（第 06 章）：内置工具全景、Skills 机制、Plugin SDK 与两类插件、ACP 与 Codex 深度集成、MCP 集成——本课程篇幅最大的一章。
7. **Channels 消息网关**（第 07 章）：Channel 插件契约与 Transport-Only 原则、代表性渠道实现对照、配对与访问控制、WebChat 与 Canvas。
8. **Companion Apps 与 Nodes**（第 08 章）：Node 协议与设备能力、原生 App 概览、语音与实时能力。
9. **记忆与人格**（第 09 章）：Memory 架构总览、Active Memory 与检索溯源、Soul 与 Dreaming。
10. **安全与沙箱**（第 10 章）：安全模型与信任边界、沙箱执行与 Crabbox、Secrets 与审计。
11. **自动化与生态**（第 11 章）：Cron 与 Standing Intents、Flows/Boards/Tasks、ClawHub 插件市场与生态治理。
12. **总结与延伸阅读**（第 12 章）：把 OpenClaw 放回 PI / DeepSeek Harness / Hermes Agent / OpenHarness 的坐标系里做一次五方对照。

## 适合谁学

- 已经会用 `openclaw`（或者对"个人/团队 AI 助理"这类产品感兴趣）的用户，想理解它到底是怎么把模型、工具、聊天软件、设备串起来的；
- 想搭一套自己的"常驻 Gateway + 多客户端"架构、又想先看一个真实工业级实现怎么处理协议、配对、多端一致性的工程师；
- 想给 OpenClaw 贡献新 Channel、新 Provider、新插件的贡献者；
- 对"安全优先的 Agent 系统设计""多代理协作""设备能力接入""记忆与人格系统"感兴趣的人；
- 已经学过姊妹课程的读者——五个项目解决的是同一类问题,规模和取舍却几乎处处不同,对照阅读收获会更大。

## 前置知识

- 具备基本的 TypeScript 阅读能力；
- 了解大语言模型（LLM）的基本概念（对话、system prompt、工具调用、流式输出）；
- 不需要提前了解 OpenClaw 本身，本课程会从零开始介绍。

## 学习方式建议

- 每篇文章涉及源码/文档的地方都会标注具体路径（如 `docs/concepts/architecture.md`、`src/gateway/...`），建议对照本地克隆的仓库边读边操作；
- 这是一个"生态型"内容远多于"核心型"内容的项目，课程对 155 个扩展、几十种 Channel、五十多个 Skill 采用了"精读代表样本 + 归纳共同契约"的写法——如果你需要某个具体扩展/渠道的完整细节，请以官方文档为准，课程给出的是可迁移的理解框架；
- 各章相对独立：只关心安全模型可以直接从第 10 章开始，只关心多平台消息接入可以直接从第 07 章开始；
- 课程里多处会诚实指出源码/文档之间的出入，以及写作过程中发现的、和名字直觉不符的真实机制（比如"Active Memory"并不是一直在运行、"Dreaming"不生成内容而是巩固记忆、`src/flows/`/`src/boards/` 和"工作流/看板"这两个名字的直觉联想完全不符）——这些不是课程的疏漏，而是深入一个大型真实代码库时必然会遇到的东西，也是这门课程反复强调的方法论：先假设、再验证、发现不成立就改写。

## 课程目录

完整的目录导航见仓库根目录的 [README.md](../README.md)。
