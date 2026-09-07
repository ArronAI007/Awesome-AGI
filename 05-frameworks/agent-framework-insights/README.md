# Agent Framework Insights

> 五套面向"彻底剖析"的中文技术课程,分别系统性拆解五个真实开源 Agent Harness 项目的架构：先会用，再懂原理，最后能扩展。每篇文章都摘录真实源码并逐段讲解设计动机，而不是停留在使用文档层面。

## 课程一：PI（[earendil-works/pi](https://github.com/earendil-works/pi)）

一个极简终端编码 Agent 项目：核心保持精简，几乎所有能力都通过 TypeScript 扩展、Skills、Prompt 模板挂载；统一多模型层覆盖 OpenAI/Anthropic/Google/Bedrock。

👉 从 [PI/00-课程导读/README.md](PI/00-课程导读/README.md) 开始。

<details>
<summary>展开完整目录（30 篇）</summary>

- **00-课程导读**：[README](PI/00-课程导读/README.md)
- **01-快速上手**：[安装指南](PI/01-快速上手/01-安装指南.md) · [快速开始](PI/01-快速上手/02-快速开始.md) · [交互模式与 CLI 命令](PI/01-快速上手/03-交互模式与CLI命令.md) · [Provider 与模型配置](PI/01-快速上手/04-Provider与模型配置.md) · [配置与个性化](PI/01-快速上手/05-配置与个性化.md)
- **02-仓库全景与工程实践**：[Monorepo 结构与包职责地图](PI/02-仓库全景与工程实践/01-Monorepo结构与包职责地图.md) · [构建测试与开发流程](PI/02-仓库全景与工程实践/02-构建测试与开发流程.md) · [发布流程与供应链安全](PI/02-仓库全景与工程实践/03-发布流程与供应链安全.md) · [安全模型与容器化沙箱](PI/02-仓库全景与工程实践/04-安全模型与容器化沙箱.md)
- **03-Agent 核心原理**：[Agent 运行时架构总览](PI/03-Agent核心原理/01-Agent运行时架构总览.md) · [工具调用 Tool Calling 机制](PI/03-Agent核心原理/02-工具调用ToolCalling机制.md) · [对话循环与消息状态机](PI/03-Agent核心原理/03-对话循环与消息状态机.md) · [会话 Session 与持久化](PI/03-Agent核心原理/04-会话Session与持久化.md) · [上下文压缩 Compaction 与分支摘要](PI/03-Agent核心原理/05-上下文压缩Compaction与分支摘要.md) · [Agent 扩展点 Hook 与事件系统](PI/03-Agent核心原理/06-Agent扩展点Hook与事件系统.md)
- **04-多模型统一层 pi-ai**：[统一 LLM 接口设计原理](PI/04-多模型统一层-pi-ai/01-统一LLM接口设计原理.md) · [Provider 适配器实现剖析](PI/04-多模型统一层-pi-ai/02-Provider适配器实现剖析.md) · [模型元数据生成与维护机制](PI/04-多模型统一层-pi-ai/03-模型元数据生成与维护机制.md)
- **05-Coding Agent CLI 实战**：[内置工具全解析](PI/05-Coding-Agent-CLI实战/01-内置工具全解析.md) · [扩展 Extension 开发指南](PI/05-Coding-Agent-CLI实战/02-扩展Extension开发指南.md) · [Skills 与 Prompt Templates](PI/05-Coding-Agent-CLI实战/03-Skills与Prompt-Templates.md) · [Pi Package 生态与分发](PI/05-Coding-Agent-CLI实战/04-Pi-Package生态与分发.md)
- **06-终端 UI pi-tui**：[差分渲染架构与组件模型](PI/06-终端UI-pi-tui/01-差分渲染架构与组件模型.md)
- **07-协议服务化与遥测**：[RPC 模式与 JSON 事件流](PI/07-协议服务化与遥测/01-RPC模式与JSON事件流.md) · [SDK 嵌入式集成](PI/07-协议服务化与遥测/02-SDK嵌入式集成.md) · [Protocol Server Client 架构](PI/07-协议服务化与遥测/03-Protocol-Server-Client架构.md) · [Telemetry 遥测体系设计](PI/07-协议服务化与遥测/04-Telemetry遥测体系设计.md)
- **08-测试与评估体系**：[测试策略 Faux Provider 与 Evals](PI/08-测试与评估体系/01-测试策略Faux-Provider与Evals.md)
- **09-总结与延伸阅读**：[课程总结与进阶方向](PI/09-总结与延伸阅读/01-课程总结与进阶方向.md)

</details>

## 课程二：DeepSeek Harness（`dsh`）

DeepSeek AI 开源的 agent harness：整个运行时构建在 Cordis 这个"万物皆插件"的元框架之上并将其源码 vendor 进仓库；几乎每类能力都拆成"Service Definition → Provider → Tool"三元结构（capability seam）；Host（Node 宿主进程）与 Client（浏览器）在类型和构建上物理分离，靠编译期生成的 RPC 契约通信；还有纯 C11 手写的 Linux Landlock 沙箱内核和让 Python 把整个运行时当子进程驱动的 NDJSON-RPC SDK。

👉 从 [DeepSeek-Harness/00-课程导读/README.md](DeepSeek-Harness/00-课程导读/README.md) 开始。

<details>
<summary>展开完整目录（32 篇）</summary>

- **00-课程导读**：[README](DeepSeek-Harness/00-课程导读/README.md)
- **01-快速上手**：[安装与环境准备](DeepSeek-Harness/01-快速上手/01-安装与环境准备.md) · [快速开始：CLI 与 Web UI](DeepSeek-Harness/01-快速上手/02-快速开始-CLI与Web-UI.md) · [CLI 命令与 Profile 机制](DeepSeek-Harness/01-快速上手/03-CLI命令与Profile机制.md) · [Provider 与模型配置](DeepSeek-Harness/01-快速上手/04-Provider与模型配置.md) · [权限预设与个性化配置](DeepSeek-Harness/01-快速上手/05-权限预设与个性化配置.md)
- **02-仓库全景与工程实践**：[Monorepo 结构与包职责地图](DeepSeek-Harness/02-仓库全景与工程实践/01-Monorepo结构与包职责地图.md) · [构建体系：Host 与 Client 双面构建](DeepSeek-Harness/02-仓库全景与工程实践/02-构建体系-Host与Client双面构建.md) · [测试策略与 CI 门禁](DeepSeek-Harness/02-仓库全景与工程实践/03-测试策略与CI门禁.md) · [Vendoring 策略与供应链治理](DeepSeek-Harness/02-仓库全景与工程实践/04-Vendoring策略与供应链治理.md)
- **03-Cordis 插件框架基石**：[核心概念：Context / Service / Plugin](DeepSeek-Harness/03-Cordis插件框架基石/01-核心概念-Context-Service-Plugin.md) · [Typed Events 与四种派发模式](DeepSeek-Harness/03-Cordis插件框架基石/02-Typed-Events与四种派发模式.md) · [Registrations are Effects：可逆卸载](DeepSeek-Harness/03-Cordis插件框架基石/03-Registrations-are-Effects可逆卸载.md) · [Profile / Bundle / Preset 装配机制](DeepSeek-Harness/03-Cordis插件框架基石/04-Profile-Bundle-Preset装配机制.md)
- **04-Agent 核心循环**：[ReactLoopAgent 总览：kick / turn / step](DeepSeek-Harness/04-Agent核心循环/01-ReactLoopAgent总览-kick-turn-step.md) · [会话事件溯源：SessionEventLog 与 Surface](DeepSeek-Harness/04-Agent核心循环/02-会话事件溯源-SessionEventLog与Surface.md) · [流式输出管道：从 StreamChunk 到 UI](DeepSeek-Harness/04-Agent核心循环/03-流式输出管道-从StreamChunk到UI.md) · [上下文压缩 Compaction 与 Checkpoint 持久化](DeepSeek-Harness/04-Agent核心循环/04-上下文压缩Compaction与Checkpoint持久化.md) · [错误处理、重试与取消机制](DeepSeek-Harness/04-Agent核心循环/05-错误处理重试与取消机制.md)
- **05-能力扩展范式 Capability Seam**：[Seam 三元结构精讲：以 shell 为例](DeepSeek-Harness/05-能力扩展范式CapabilitySeam/01-Seam三元结构精讲-以shell为例.md) · [工具注册与执行管线](DeepSeek-Harness/05-能力扩展范式CapabilitySeam/02-工具注册与执行管线.md) · [权限审批与沙箱体系](DeepSeek-Harness/05-能力扩展范式CapabilitySeam/03-权限审批与沙箱体系.md) · [内置工具全解析](DeepSeek-Harness/05-能力扩展范式CapabilitySeam/04-内置工具全解析.md)
- **06-跨语言边界与部署形态**：[Native 沙箱内核 landlock-run](DeepSeek-Harness/06-跨语言边界与部署形态/01-Native沙箱内核landlock-run.md) · [Python SDK 与 NDJSON-RPC 桥接](DeepSeek-Harness/06-跨语言边界与部署形态/02-Python-SDK与NDJSON-RPC桥接.md) · [Host-Client 分离与 Typert RPC 生成](DeepSeek-Harness/06-跨语言边界与部署形态/03-Host-Client分离与Typert-RPC生成.md) · [对外协议：SDK、ACP 与生态兼容 Hooks](DeepSeek-Harness/06-跨语言边界与部署形态/04-对外协议SDK-ACP与生态兼容Hooks.md)
- **07-多智能体与工作流**：[Subagent 委派与协作模型](DeepSeek-Harness/07-多智能体与工作流/01-Subagent委派与协作模型.md) · [Workflow 引擎与 Ralph 循环](DeepSeek-Harness/07-多智能体与工作流/02-Workflow引擎与Ralph循环.md) · [Skill 技能系统与动态插件扩展](DeepSeek-Harness/07-多智能体与工作流/03-Skill技能系统与动态插件扩展.md)
- **08-工程质量与文档治理**：[测试哲学：Verify the World, not the Self-report](DeepSeek-Harness/08-工程质量与文档治理/01-测试哲学-Verify-the-World-not-the-Self-report.md) · [AGENTS.md 治理规范与文档体系](DeepSeek-Harness/08-工程质量与文档治理/02-AGENTS-md治理规范与文档体系.md) · [Postmortem 与防御性编程模式](DeepSeek-Harness/08-工程质量与文档治理/03-Postmortem与防御性编程模式.md)
- **09-总结与延伸阅读**：[课程总结与进阶方向](DeepSeek-Harness/09-总结与延伸阅读/01-课程总结与进阶方向.md)

</details>

## 课程三：Hermes Agent（[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)）

一个自我进化的个人/团队 Agent：会从经验里创建并在使用中改进 Skill、支持多种可插拔终端后端（本地/Docker/SSH/Singularity/Modal/Daytona/Vercel Sandbox）、内置 cron 调度与消息网关（Telegram/Discord/Slack/WhatsApp/Signal/Email 共用一个进程）。规模远超前两个项目——核心文件普遍是万行级的 Python 模块，是一个经过大量真实生产故障打磨出来的系统，工程气质与 PI/DeepSeek-Harness 的"干净架构展示"截然不同。

👉 从 [Hermes-Agent/00-课程导读/README.md](Hermes-Agent/00-课程导读/README.md) 开始。

<details>
<summary>展开完整目录（40 篇）</summary>

- **00-课程导读**：[README](Hermes-Agent/00-课程导读/README.md)
- **01-快速上手**：[安装与环境准备](Hermes-Agent/01-快速上手/01-安装与环境准备.md) · [快速开始：CLI 与 Gateway 速览](Hermes-Agent/01-快速上手/02-快速开始-CLI与Gateway速览.md) · [CLI 命令与 Slash 命令体系](Hermes-Agent/01-快速上手/03-CLI命令与Slash命令体系.md) · [Provider 与模型配置](Hermes-Agent/01-快速上手/04-Provider与模型配置.md) · [Profile 与个性化配置](Hermes-Agent/01-快速上手/05-Profile与个性化配置.md)
- **02-仓库全景与工程实践**：[顶层结构地图与技术栈全景](Hermes-Agent/02-仓库全景与工程实践/01-顶层结构地图与技术栈全景.md) · [Monorepo 依赖管理与构建测试流程](Hermes-Agent/02-仓库全景与工程实践/02-Monorepo依赖管理与构建测试流程.md) · [CI/CD 与供应链安全](Hermes-Agent/02-仓库全景与工程实践/03-CI-CD与供应链安全.md) · [Footprint Ladder：能力分层哲学](Hermes-Agent/02-仓库全景与工程实践/04-Footprint-Ladder能力分层哲学.md)
- **03-Agent 核心循环**：[AIAgent 总览与运行时架构](Hermes-Agent/03-Agent核心循环/01-AIAgent总览与运行时架构.md) · [turn_context 前奏与轮内状态机](Hermes-Agent/03-Agent核心循环/02-turn_context前奏与轮内状态机.md) · [错误分类、降级与重试机制](Hermes-Agent/03-Agent核心循环/03-错误分类降级与重试机制.md) · [中断与轮内改口 Steering](Hermes-Agent/03-Agent核心循环/04-中断与轮内改口Steering.md)
- **04-多 Provider 与工具系统**：[Provider Profile 注册表与原生 Adapter 双轨制](Hermes-Agent/04-多Provider与工具系统/01-Provider-Profile注册表与原生Adapter双轨制.md) · [工具自注册管线与 Schema](Hermes-Agent/04-多Provider与工具系统/02-工具自注册管线与Schema.md) · [Toolsets 组合与分发](Hermes-Agent/04-多Provider与工具系统/03-Toolsets组合与分发.md) · [Session vs Process 能力门控设计精讲](Hermes-Agent/04-多Provider与工具系统/04-Session-vs-Process能力门控设计精讲.md)
- **05-终端后端与执行安全**：[终端环境抽象与七种后端实现](Hermes-Agent/05-终端后端与执行安全/01-终端环境抽象与七种后端实现.md) · [Programmatic Tool Calling：本地 UDS 与远程文件轮询 RPC](Hermes-Agent/05-终端后端与执行安全/02-Programmatic-Tool-Calling本地UDS与远程RPC.md) · [批准模式、网络出口隔离与安全模型三层防御](Hermes-Agent/05-终端后端与执行安全/03-批准模式网络出口隔离与安全模型三层防御.md)
- **06-记忆状态与压缩**：[SessionDB Mixin 架构：SQLite WAL、FTS5 与 CJK 分词](Hermes-Agent/06-记忆状态与压缩/01-SessionDB-Mixin架构-SQLite-WAL-FTS5与CJK分词.md) · [上下文压缩：运行时策略与迭代式摘要更新](Hermes-Agent/06-记忆状态与压缩/02-上下文压缩-运行时策略与迭代式摘要更新.md) · [面向训练数据的独立压缩器 Trajectory Compressor](Hermes-Agent/06-记忆状态与压缩/03-面向训练数据的独立压缩器Trajectory-Compressor.md)
- **07-Skills 自我进化学习环**：[Learn 命令：从对话到 SKILL.md 的生成机制](Hermes-Agent/07-Skills自我进化学习环/01-Learn命令-从对话到SKILL-md的生成机制.md) · [知识库布局与 SKILL 写作规范](Hermes-Agent/07-Skills自我进化学习环/02-知识库布局与SKILL写作规范.md) · [Curator：后台复审与技能生命周期治理](Hermes-Agent/07-Skills自我进化学习环/03-Curator后台复审与技能生命周期治理.md)
- **08-插件系统与协议生态**：[PluginContext 与四种发现源](Hermes-Agent/08-插件系统与协议生态/01-PluginContext与四种发现源.md) · [插件架构对比精讲：Hermes vs Pi vs OpenCode](Hermes-Agent/08-插件系统与协议生态/02-插件架构对比精讲-Hermes-vs-Pi-vs-OpenCode.md) · [MCP 双向集成：作为 Client 与作为 Server](Hermes-Agent/08-插件系统与协议生态/03-MCP双向集成-作为Client与作为Server.md) · [ACP 适配器：接入 Zed 等标准 Agent Host](Hermes-Agent/08-插件系统与协议生态/04-ACP适配器-接入Zed等标准Agent-Host.md)
- **09-多智能体网关与调度**：[delegate_task 轻量子代理委派](Hermes-Agent/09-多智能体网关与调度/01-delegate_task轻量子代理委派.md) · [Kanban 任务看板与 Swarm 编排](Hermes-Agent/09-多智能体网关与调度/02-Kanban任务看板与Swarm编排.md) · [消息网关平台注册表：一进程多平台](Hermes-Agent/09-多智能体网关与调度/03-消息网关平台注册表-一进程多平台.md) · [Cron 调度：本地 Tick 与 Chronos 托管无服务器化](Hermes-Agent/09-多智能体网关与调度/04-Cron调度-本地Tick与Chronos托管无服务器化.md)
- **10-界面层与前端协议**：[四种前端与共享 JSON-RPC 网关协议](Hermes-Agent/10-界面层与前端协议/01-四种前端与共享JSON-RPC网关协议.md)
- **11-测试评估与研究工具**：[测试哲学：不测变更检测器](Hermes-Agent/11-测试评估与研究工具/01-测试哲学-不测变更检测器.md) · [Evals 框架：面向子系统能力的自建评测](Hermes-Agent/11-测试评估与研究工具/02-Evals框架-面向子系统能力的自建评测.md) · [Batch Runner 与训练轨迹生成](Hermes-Agent/11-测试评估与研究工具/03-Batch-Runner与训练轨迹生成.md)
- **12-总结与延伸阅读**：[课程总结与三方对比](Hermes-Agent/12-总结与延伸阅读/01-课程总结与三方对比.md)

</details>

## 课程四：OpenHarness（[HKUDS/OpenHarness](https://github.com/HKUDS/OpenHarness)）

一个开源的 Python 版 Claude Code 复刻，CLI 命令是 `oh`：40 多个内置工具的名字和语义与 Claude Code 官方工具集高度重合，权限模式、Skills 机制兼容 `anthropics/skills`、Plugins 兼容 Claude-style plugin 规范，认证体系还专门做了"复用本地已登录的 Claude Code/Codex CLI 凭据"这类只有"复刻者"才会做的适配。核心逻辑是纯 Python，主力交互界面却是独立的 Ink/React TypeScript 子进程，另有一个纯 Python 的 Textual 备用界面。围绕核心还长出了 Claude Code 本身没有的东西：基于它构建的个人 Agent App `ohmo`（人格化 system prompt + 十种 IM 平台网关 + Cron 主动触发）、Swarm/Coordinator 多智能体体系、以及几乎零运维成本的 Autopilot 快照仪表盘。

👉 从 [OpenHarness/00-课程导读/README.md](OpenHarness/00-课程导读/README.md) 开始。

<details>
<summary>展开完整目录（34 篇）</summary>

- **00-课程导读**：[README](OpenHarness/00-课程导读/README.md)
- **01-快速上手**：[安装与环境准备](OpenHarness/01-快速上手/01-安装与环境准备.md) · [快速开始：CLI 与 TUI 速览](OpenHarness/01-快速上手/02-快速开始-CLI与TUI速览.md) · [Provider Workflow 与 Profile 机制](OpenHarness/01-快速上手/03-Provider-Workflow与Profile机制.md) · [Dry-run 安全预览](OpenHarness/01-快速上手/04-Dry-run安全预览.md) · [Ohmo 初探：个人 Agent 的另一副面孔](OpenHarness/01-快速上手/05-Ohmo初探-个人Agent的另一副面孔.md)
- **02-仓库全景与工程实践**：[Monorepo 结构与包职责地图](OpenHarness/02-仓库全景与工程实践/01-Monorepo结构与包职责地图.md) · [双前端架构：Ink TUI 与 Textual 备用界面](OpenHarness/02-仓库全景与工程实践/02-双前端架构-Ink-TUI与Textual备用界面.md) · [配置与路径解析体系](OpenHarness/02-仓库全景与工程实践/03-配置与路径解析体系.md) · [测试策略与工程规范](OpenHarness/02-仓库全景与工程实践/04-测试策略与工程规范.md)
- **03-Agent 核心循环**：[QueryEngine 总览：流式工具调用循环](OpenHarness/03-Agent核心循环/01-QueryEngine总览-流式工具调用循环.md) · [Provider 抽象与多模型适配](OpenHarness/03-Agent核心循环/02-Provider抽象与多模型适配.md) · [消息状态机、上下文管理与成本跟踪](OpenHarness/03-Agent核心循环/03-消息状态机-上下文管理与成本跟踪.md) · [认证体系：订阅复用与 OAuth](OpenHarness/03-Agent核心循环/04-认证体系-订阅复用与OAuth.md)
- **04-工具生态与扩展**：[43 个内置工具全解析](OpenHarness/04-工具生态与扩展/01-43个内置工具全解析.md) · [Skills 机制：Markdown 技能与按需加载](OpenHarness/04-工具生态与扩展/02-Skills机制-Markdown技能与按需加载.md) · [Plugins 插件系统](OpenHarness/04-工具生态与扩展/03-Plugins插件系统.md) · [MCP 集成：作为 Client 接入外部工具](OpenHarness/04-工具生态与扩展/04-MCP集成-作为Client接入外部工具.md) · [Hooks 机制：事件驱动的行为注入](OpenHarness/04-工具生态与扩展/05-Hooks机制-事件驱动的行为注入.md)
- **05-治理与安全**：[多级权限模式与审批流程](OpenHarness/05-治理与安全/01-多级权限模式与审批流程.md) · [沙箱执行：Docker 后端与路径校验](OpenHarness/05-治理与安全/02-沙箱执行-Docker后端与路径校验.md)
- **06-记忆与会话**：[CLAUDE.md 与 MEMORY.md：记忆的发现、注入与压缩](OpenHarness/06-记忆与会话/01-CLAUDE-md与MEMORY-md-记忆的发现注入与压缩.md) · [会话存储与 Resume 机制](OpenHarness/06-记忆与会话/02-会话存储与Resume机制.md) · [个性化系统：从对话中提取用户偏好](OpenHarness/06-记忆与会话/03-个性化系统-从对话中提取用户偏好.md)
- **07-多智能体协作**：[Swarm 架构总览：Team / Worktree / Mailbox](OpenHarness/07-多智能体协作/01-Swarm架构总览-Team-Worktree-Mailbox.md) · [子代理执行后端：进程内与子进程两种模式](OpenHarness/07-多智能体协作/02-子代理执行后端-进程内与子进程两种模式.md) · [Coordinator 模式：单代理编排多代理团队](OpenHarness/07-多智能体协作/03-Coordinator模式-单代理编排多代理团队.md) · [Task 生命周期与 Bridge 桥接](OpenHarness/07-多智能体协作/04-Task生命周期与Bridge桥接.md)
- **08-Ohmo 与多平台网关**：[Ohmo 总览：Soul / Identity / Memory 的人格化设计](OpenHarness/08-Ohmo与多平台网关/01-Ohmo总览-Soul-Identity-Memory的人格化设计.md) · [Gateway 网关架构：多 Profile 多 Channel 路由](OpenHarness/08-Ohmo与多平台网关/02-Gateway网关架构-多Profile多Channel路由.md) · [十种 IM Channel 实现对照](OpenHarness/08-Ohmo与多平台网关/03-十种IM-Channel实现对照.md) · [Cron 调度与主动触发](OpenHarness/08-Ohmo与多平台网关/04-Cron调度与主动触发.md)
- **09-可观测性与 Autopilot**：[Autopilot 运行快照服务与 React 仪表盘](OpenHarness/09-可观测性与Autopilot/01-Autopilot运行快照服务与React仪表盘.md)
- **10-总结与延伸阅读**：[课程总结与延伸阅读](OpenHarness/10-总结与延伸阅读/01-课程总结与延伸阅读.md)

</details>

## 课程五：OpenClaw（[openclaw/openclaw](https://github.com/openclaw/openclaw)）

一个跑在你自己设备上、接入你已经在用的聊天软件的 AI 助理：核心是一个叫 Gateway 的常驻控制平面，统一调度模型、工具、消息渠道（WhatsApp/Telegram/Slack/Discord/Signal/iMessage/Matrix 等十余种）和设备（macOS/iOS/Android/Linux 原生 App，可调用相机/屏幕/地理位置）。这是这套课程系列迄今规模最大的项目——仅 `docs/` 就有 800 多篇文档，`src/gateway/` 一个目录就有 2600 多个文件，155 个 extensions、23 个共享 packages、还有独立的插件市场 ClawHub。安全被当作一等公民："trusted gateway, untrusted execution, deterministic policy"贯穿权限模式、沙箱、审批、审计的每一处设计；核心自带 Memory、Soul（长期人格设定）、Dreaming（后台记忆巩固）机制。因为规模悬殊，本课程对 155 个扩展、几十种渠道这类"生态型"内容采用了精读代表样本、归纳共同契约的写法，而不是逐项穷举。

👉 从 [OpenClaw/00-课程导读/README.md](OpenClaw/00-课程导读/README.md) 开始。

<details>
<summary>展开完整目录（44 篇）</summary>

- **00-课程导读**：[README](OpenClaw/00-课程导读/README.md)
- **01-快速上手**：[安装与一键上手](OpenClaw/01-快速上手/01-安装与一键上手.md) · [CLI 与 Control UI 速览](OpenClaw/01-快速上手/02-CLI与Control-UI速览.md) · [Channels 接入与 Pairing 速览](OpenClaw/01-快速上手/03-Channels接入与Pairing速览.md) · [模型与 Provider 配置速览](OpenClaw/01-快速上手/04-模型与Provider配置速览.md) · [安全基线与信任模型速览](OpenClaw/01-快速上手/05-安全基线与信任模型速览.md)
- **02-仓库全景与工程实践**：[pnpm Workspace 与目录地图](OpenClaw/02-仓库全景与工程实践/01-pnpm-Workspace与目录地图.md) · [Doctor 迁移与配置契约](OpenClaw/02-仓库全景与工程实践/02-Doctor迁移与配置契约.md) · [测试哲学与 CI](OpenClaw/02-仓库全景与工程实践/03-测试哲学与CI.md) · [协议代码生成：TypeBox 到 JSON Schema 再到 Swift](OpenClaw/02-仓库全景与工程实践/04-协议代码生成-TypeBox到JSON-Schema再到Swift.md)
- **03-Gateway 架构与协议**：[Gateway 总览：单一控制平面与 WS 协议](OpenClaw/03-Gateway架构与协议/01-Gateway总览-单一控制平面与WS协议.md) · [Pairing 与设备信任模型](OpenClaw/03-Gateway架构与协议/02-Pairing与设备信任模型.md) · [多 Gateway、Lock 与远程访问](OpenClaw/03-Gateway架构与协议/03-多Gateway-Lock与远程访问.md) · [Health、Heartbeat 与可观测性](OpenClaw/03-Gateway架构与协议/04-Health-Heartbeat与可观测性.md)
- **04-Agent 核心循环与会话**：[Agent Loop 总览](OpenClaw/04-Agent核心循环与会话/01-Agent-Loop总览.md) · [Session 与状态机](OpenClaw/04-Agent核心循环与会话/02-Session与状态机.md) · [上下文压缩 Compaction 与 Context Engine](OpenClaw/04-Agent核心循环与会话/03-上下文压缩Compaction与Context-Engine.md) · [Queue 与并发控制、Steering](OpenClaw/04-Agent核心循环与会话/04-Queue与并发控制-Steering.md) · [多代理协作与 Delegate 架构](OpenClaw/04-Agent核心循环与会话/05-多代理协作与Delegate架构.md)
- **05-模型与 Provider 生态**：[Model Providers 抽象与 Failover](OpenClaw/05-模型与Provider生态/01-Model-Providers抽象与Failover.md) · [Provider 扩展全景：代表性适配器对照](OpenClaw/05-模型与Provider生态/02-Provider扩展全景-代表性适配器对照.md) · [System Prompt 组装与 Agent Workspace](OpenClaw/05-模型与Provider生态/03-System-Prompt组装与Agent-Workspace.md)
- **06-工具生态：Tools / Skills / Plugins / MCP**：[Tools 总览与代表性工具](OpenClaw/06-工具生态-Tools-Skills-Plugins-MCP/01-Tools总览与代表性工具.md) · [Skills 机制](OpenClaw/06-工具生态-Tools-Skills-Plugins-MCP/02-Skills机制.md) · [Plugin SDK 与两类插件](OpenClaw/06-工具生态-Tools-Skills-Plugins-MCP/03-Plugin-SDK与两类插件.md) · [ACP 与 Codex 深度集成](OpenClaw/06-工具生态-Tools-Skills-Plugins-MCP/04-ACP与Codex深度集成.md) · [MCP 集成](OpenClaw/06-工具生态-Tools-Skills-Plugins-MCP/05-MCP集成.md)
- **07-Channels 消息网关**：[Channel 插件契约与 Transport-Only 原则](OpenClaw/07-Channels消息网关/01-Channel插件契约与Transport-Only原则.md) · [代表性 Channel 实现对照](OpenClaw/07-Channels消息网关/02-代表性Channel实现对照.md) · [Pairing、Groups 与访问控制](OpenClaw/07-Channels消息网关/03-Pairing-Groups与访问控制.md) · [WebChat 与 Canvas 托管界面](OpenClaw/07-Channels消息网关/04-WebChat与Canvas托管界面.md)
- **08-Companion Apps 与 Nodes**：[Node 协议与设备能力](OpenClaw/08-CompanionApps与Nodes/01-Node协议与设备能力.md) · [原生 App 概览：macOS / iOS / Android / Linux](OpenClaw/08-CompanionApps与Nodes/02-原生App概览-macOS-iOS-Android-Linux.md) · [语音与实时能力：Talk、TTS 与会议机器人](OpenClaw/08-CompanionApps与Nodes/03-语音与实时能力-Talk-TTS-会议机器人.md)
- **09-记忆与人格**：[Memory 架构总览](OpenClaw/09-记忆与人格/01-Memory架构总览.md) · [Active Memory、Search 与 Provenance](OpenClaw/09-记忆与人格/02-Active-Memory-Search与Provenance.md) · [Soul 与 Dreaming：人格与长期演化](OpenClaw/09-记忆与人格/03-Soul与Dreaming-人格与长期演化.md)
- **10-安全与沙箱**：[安全模型与信任边界](OpenClaw/10-安全与沙箱/01-安全模型与信任边界.md) · [沙箱执行：Elevated、Exec Approvals 与 Crabbox](OpenClaw/10-安全与沙箱/02-沙箱执行-Elevated-Exec-Approvals与Crabbox.md) · [Secrets 与 Audit](OpenClaw/10-安全与沙箱/03-Secrets与Audit.md)
- **11-自动化与生态**：[Cron 与 Standing Intents](OpenClaw/11-自动化与生态/01-Cron与Standing-Intents.md) · [Flows、Boards、Tasks 工作看板](OpenClaw/11-自动化与生态/02-Flows-Boards-Tasks工作看板.md) · [ClawHub 插件市场与生态治理](OpenClaw/11-自动化与生态/03-ClawHub插件市场与生态治理.md)
- **12-总结与延伸阅读**：[课程总结与延伸阅读](OpenClaw/12-总结与延伸阅读/01-课程总结与延伸阅读.md)

</details>

## 五个项目的架构哲学速览

| | PI | DeepSeek Harness | Hermes Agent | OpenHarness | OpenClaw |
|---|---|---|---|---|---|
| 定位 | 极简终端编码 Agent | 万物皆插件的通用 Agent Harness | 自我进化、多平台常驻的个人/团队 Agent | Python 版 Claude Code 复刻 + 基于它构建的个人 Agent App（`ohmo`） | 单一 Gateway 统一调度模型/工具/消息渠道/设备的个人与团队助理平台 |
| 扩展方式 | 精简核心 + TypeScript Extension / Skills / Prompt 模板 | 万物皆插件（Cordis），能力按 Service Definition / Provider / Tool 三元结构组织 | 文件目录 + manifest + 单一巨型 `PluginContext`；另有 Footprint Ladder 六级决策框架指导扩展面选型 | 工具 / Skills / Plugins / MCP 四条并行扩展面，无独立元框架，工具协议直接对齐 Claude Code 官方工具集 | Code Plugin（进程内同等信任，深度运行时扩展）与 Bundle-style Plugin（打包稳定外部能力，信任边界窄）二级明确区分，"核心瘦身、能力下沉插件"写进产品愿景 |
| 框架依赖 | 无独立元框架，扩展机制内建于 `coding-agent` 包 | 依赖 vendor 进仓库的 Cordis 生态（源码自持，可审计可打补丁） | 无独立元框架，插件发现内建于 `hermes_cli/plugins.py` | 无独立元框架；`channels/bus`、`channels/impl` 直接 vendor 自另一个开源项目 `nanobot-ai/nanobot` | 无独立元框架，但有独立的插件市场 ClawHub 承担发现/发布者身份/安全审查 |
| 多模型层 | `pi-ai` 统一接口 | `packages/llm/*` seam + `llm-deepseek`/`llm-pi-ai` 双 Provider 对照验证 | `providers/` Profile 元数据（多数 provider）+ 少数原生 Adapter（Anthropic/Bedrock/Gemini/Codex）混合路线 | `SupportsStreamingMessages` Protocol + 4 个具体客户端；workflow + profile 抽象；Copilot 客户端靠组合/monkeypatch OpenAI 客户端实现 | Provider 插件 SDK 契约 + 两阶段 Failover（认证 profile 轮换 → 模型降级）+ 独立的 operation 级重试层，154 个 extension 里 79 个声明 provider |
| 会话表示 | JSONL append 日志 | 事件溯源日志（`SessionEventMap`）+ Surface 投影，压缩靠 `replace` 而非删除 | SQLite（WAL + FTS5 + 自研 CJK 分词），mixin 拆分 search/schema/portability，`parent_session_id` 链支撑压缩拆分 | 纯 JSON 快照，每轮对话后落盘；另有独立的 Markdown "session memory" 检查点服务于压缩边界 | 强制 SQLite（`AGENTS.md` 明文禁止新增 JSON/JSONL 运行时存储），main session + 多种 reset 模式 + 硬性裁剪安全规则 |
| 沙箱 | 依赖外部容器化 | 自建多平台沙箱（bwrap / Seatbelt / 纯 C 手写 Landlock / Windows ACL）+ E2B 远程 | 七种可插拔终端后端（local/docker/ssh/singularity/modal/daytona/vercel）+ 批准模式（启发式）+ 网络出口隔离（OS 级） | 默认后端包装 Anthropic 外部 `srt` CLI（bubblewrap/sandbox-exec），Docker 为第二可选后端，两者靠字符串分发而非共享接口 | 沙箱/工具策略/提权三层边界；云沙箱能力被明确导流到独立项目 Crabbox 而非做成插件；审计留痕明确不等于授权 |
| 部署/进程形态 | 单一 CLI 进程 | Host（Node）/ Client（浏览器）类型与构建物理分离，Typert 编译期生成 RPC 契约 | 单进程多平台 Gateway，四种前端（classic CLI / Ink TUI / Dashboard 内嵌 PTY / Electron）共享同一套 JSON-RPC 协议 | 三种前端服务三种场景：Ink/React 终端 TUI（子进程 + 自定义 JSON 行协议）、Textual 备用界面（未接线的正交实现）、React/Vite 静态仪表盘（可发布 GitHub Pages） | 单一常驻 Gateway + WS 协议服务 CLI/Dashboard/TUI/4 个原生 App(macOS/iOS/Android/Linux)/Node 设备；TypeBox 单一数据源并行生成 Swift 与 Kotlin 类型 |
| 独有卖点 | 核心足够小，可作为引擎单独复用 | 自研沙箱内核 + 编译期生成 RPC 契约 | Skills 自我进化学习环（`/learn` + curator）+ Chronos 托管无服务器化 cron + 面向训练数据的 batch_runner | `ohmo` 个人 Agent App（人格化 system prompt + 十种 IM 平台网关 + Cron 主动触发）+ 零运维 Autopilot 快照仪表盘 | Gateway 统一配对信任模型把模型/十余种消息渠道/4 端原生 App/设备能力(相机/屏幕/位置)纳入同一套架构；Soul + Dreaming 人格与记忆长期演化机制 |

建议按 PI → DeepSeek Harness → Hermes Agent → OpenHarness → OpenClaw 的顺序阅读——前四者已经在不同规模下几乎处处做出了不同的架构选择，OpenClaw 则把同一类问题推向了目前这套课程系列里最大的规模：仅 `docs/` 就有 800 多篇文档、155 个 extensions、四个原生 App，逼着它必须把"核心该做什么、生态该做什么"写成一条明确的产品哲学（VISION.md 的"两层两条门槛"），否则系统会在自身复杂度下失控。对照阅读收获会比单读一套更大。第 08 章第 2 篇（[插件架构对比精讲](Hermes-Agent/08-插件系统与协议生态/02-插件架构对比精讲-Hermes-vs-Pi-vs-OpenCode.md)）更是直接改写自 Hermes 团队对 Pi 插件架构的源码级评审，读完 PI 课程再读这一篇会有额外收获。

---

MIT License，见 [LICENSE](LICENSE)。
