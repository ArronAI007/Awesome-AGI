# System Prompt 组装与 Agent Workspace

> "OpenClaw builds its own system prompt for every agent run; there is no runtime default prompt." 这句话看起来只是在描述一个实现细节,但它背后是一整套三层渲染架构:纯函数负责渲染、配置解析层负责查表、运行时适配器负责收集"这一次运行"的实时事实。喂给模型的最终提示词,是这三层叠加、外加 Provider 插件的有限贡献、再叠加 Workspace 里几份 Markdown 文件的结果。这篇讲清楚这条组装链路,以及 Agent Workspace 和 Agent Bindings 这两个经常被混淆的概念各自的职责边界。

## 学习目标

- 理解 System Prompt 组装的三层架构——纯渲染函数、配置解析层、运行时适配器——为什么要拆成三层而不是一个大函数。
- 理解 Provider 插件对 System Prompt 的贡献边界:只能替换三个命名 section、注入 cache 边界上下两侧的内容,理解这个边界为什么被卡得这么死。
- 读懂 Workspace Bootstrap 注入机制:哪些文件会被读进 Prompt、大小限制怎么算、在原生 Codex Harness 上为什么表现不同。
- 理解 `promptMode`(`full`/`minimal`/`none`)如何在主会话和子代理会话之间做取舍。
- 区分 Agent Workspace(身份、记忆、工作目录)和 Agent Bindings(把消息路由给哪个 Agent)这两个正交概念,不要把"配置了 Workspace"和"配置了访问控制"混为一谈。

## 背景与设计动机

多数 Agent 框架要么把 System Prompt 硬编码成一个大字符串模板,要么完全交给调用方自己拼。OpenClaw 选择了第三条路:核心自己拥有 Prompt 的组装权,但把组装过程拆成三个职责清晰的层,并且给 Provider 插件开了一道很窄的"贡献接口"而不是完全开放。`docs/concepts/system-prompt.md` 把这三层写得很直接:

> - `buildAgentSystemPrompt` renders the prompt from explicit inputs. It stays a pure renderer and does not read global config directly.
> - `resolveAgentSystemPromptConfig` resolves config-backed prompt knobs (owner display, TTS hints, model aliases, memory citation mode, sub-agent delegation mode) for a specific agent.
> - Runtime adapters (embedded, CLI, command/export previews, compaction) gather live facts (tools, sandbox state, channel capabilities, context files, provider prompt contributions) and call the configured prompt facade.

这个三层设计解决的是一个具体的一致性问题:如果"导出/预览这次会用什么 Prompt"和"真正跑这次会话用的 Prompt"是两套不同的代码路径,两者迟早会漂移。把渲染逻辑锁定成一个不读全局配置的纯函数,意味着任何一个运行时适配器(嵌入式推理循环、CLI、导出预览、压缩流程)只要传入相同的显式输入,就一定能拿到相同的渲染结果——`system-prompt.md` 对这一点的表述是"This keeps exported/debug prompt surfaces aligned with live runs without turning every runtime detail into one monolithic builder."

## 核心机制详解

### 1. Provider 对 Prompt 的贡献:三个命名 Section + Cache 边界

如果每个 Provider 插件都能随意往 System Prompt 里塞任意内容,这份 Prompt 很快会变得不可预测、也没法做 Prompt Cache。OpenClaw 把 Provider 的贡献面卡得很窄:

> Provider plugins can contribute cache-aware guidance without replacing the OpenClaw-owned prompt. A provider runtime can:
> - replace one of three named core sections: `interaction_style`, `tool_call_style`, `execution_bias`
> - inject a **stable prefix** above the prompt cache boundary
> - inject a **dynamic suffix** below the prompt cache boundary

内置的 GPT-5 家族贡献(`resolveGpt5SystemPromptContribution`)是这套机制的实际案例:它用一个 `stablePrefix` 承载执行策略、工具纪律、输出契约、完成契约这四类"行为契约",再叠加一个可选的 `interaction_style` 覆盖做语气调整;`plugins.entries.openai.config.personality` 这个配置项控制的正是这层语气覆盖(`"friendly"` 默认开启,`"off"` 只移除友好语气覆盖,底层的行为契约始终保留)。文档特别强调了兜底原则:

> Use provider-owned contributions for model-family-specific tuning. Reserve the legacy `before_prompt_build` hook for compatibility or truly global prompt changes.

也就是说,"这个模型家族需要特殊的语气/行为提示"应该走这层窄接口,而不是走一个能改任何东西的全局 Hook——**贡献面越窄,越不容易在多 Provider 之间产生互相冲突的 Prompt 补丁**。

### 2. 固定 Section 与 Cache 边界的分层原则

System Prompt 本身是一份固定结构的清单,从 Tooling、Execution Bias、Promised Work、Safety、Runtime Context,到 Workspace、Documentation、Sandbox、Temporal Context、Assistant Output Directives 等十几个命名 section。这份清单的排布不是随意的——它严格按照"内容是否随时间/每轮对话变化"分成了 Cache 边界上下两层:

> Large stable content (including **Project Context** and static **Memory Recall** instructions) stays above the internal prompt cache boundary. Volatile per-turn sections (**UI Presentation**, ... **Runtime**, **Project Memory** facts, ...) are appended below that boundary so local backends with prefix caches can reuse the stable workspace prefix across channel turns.

这条边界直接服务于 Prompt Cache 的复用率:像"当前日期时间""这一轮是哪个 Channel"这类每轮都可能变化的信息,如果混进 Prompt 靠前的稳定部分,会导致支持前缀缓存的后端(第 02 篇提到的 Anthropic Prompt Cache 断点、Bedrock 的 `cachePoint` 机制)每轮都因为前缀发生变化而缓存失效。文档甚至专门提醒:**Exec 会话、子代理状态、媒体生成进度这些本该属于"实时事实"的内容,也被特意挪到了一个专门的 Runtime Context 载体里**,用 `<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>`/`<<<END_OPENCLAW_INTERNAL_CONTEXT>>>` 分隔符包裹,而不是直接混进对话历史,这样即便这些实时状态频繁变化,也不会污染更前面的"对话历史前缀"这份缓存单元。

### 3. Workspace Bootstrap 注入:身份、记忆是怎么进入 Prompt 的

`docs/concepts/system-prompt.md` 的"Workspace bootstrap injection"一节说明了一个 Agent 的身份和记忆文件是怎么变成 Prompt 内容的:

> Agent identity, instructions, and memory are resolved from the configured agent workspace and routed to the prompt surface matching their lifetime.

具体会被注入的文件清单是:

```text
AGENTS.md
SOUL.md
IDENTITY.md
USER.md
BOOTSTRAP.md（仅全新 workspace）
MEMORY.md（存在时）
```

这里有一个容易忽略的细节:如果会话是从另一个目录(比如一个被挂载的 worktree)运行的,那个目录的 `AGENTS.md` 会作为"项目上下文"追加在配置的 Workspace 文件之后,但 `SOUL.md`/`IDENTITY.md`/`USER.md`/`MEMORY.md`/`BOOTSTRAP.md` **不会**从执行目录加载——这些是 Agent 身份和长期记忆专属的文件,不应该因为临时切换了工作目录就被替换或叠加。

大文件会被截断,截断阈值是两个可配置的字符数上限:

| 限制 | 配置键 | 默认值 |
| --- | --- | --- |
| 单文件最大字符数 | `agents.defaults.bootstrapMaxChars` | 20000 |
| 全部文件累计上限 | `agents.defaults.bootstrapTotalMaxChars` | 60000 |

截断发生时,OpenClaw 会往 Prompt 里注入一条固定的、不可配置的提示,告诉模型"部分 Bootstrap 文件被截断了,请直接读取受影响文件"——但这条提示本身故意不包含"具体哪个文件被截断了多少字符"这类细节,文件级别的原始/注入字符数只出现在 `/context list`、`/status`、doctor 输出这类诊断面里。这个设计取舍很清楚:**Prompt 本身要保持简短可预测,细粒度的诊断信息应该走专门的诊断通道,而不是让每次截断都在 Prompt 里附加一段可变长度的报告**。

原生 Codex Harness 上,这套注入逻辑又被进一步收窄了一层:

> On the native Codex harness, OpenClaw avoids repeating stable workspace files in every user turn. Codex loads the execution folder's `AGENTS.md`... through native project-doc discovery, so OpenClaw does not inject that file again... `MEMORY.md` content is not pasted into every native Codex turn either: when memory tools are available for the agent workspace, Codex turns get a small workspace-memory note directing the model to `memory_search` or `memory_get`.

这说明"往 Prompt 里塞文件内容"并不是唯一的注入手段——当 Codex 原生具备项目文档发现能力、并且 `memory_search`/`memory_get` 这类工具可用时,OpenClaw 宁可只给一条"去查记忆工具"的引导语,也不愿意把整份 `MEMORY.md` 反复贴进每一轮请求,这直接减少了每轮的 Token 开销,也避免了"记忆文件越长、Prompt 越臃肿"的恶性循环。

### 4. `promptMode`:同一套渲染逻辑,三种取舍

`buildAgentSystemPrompt` 并不是对所有会话都渲染同一份完整 Prompt。运行时会给每次运行设置一个 `promptMode`:

> - `full` (default): all sections above.
> - `minimal`: used for sub-agents; omits the memory prompt section..., **Model Aliases**, **User Identity**, **Assistant Output Directives**, **Messaging**, **Collapsible Details**, and **Silent Replies**. Tooling, **Safety**, **Skills**..., Workspace, Sandbox, Current Date & Time..., Runtime, and injected context stay available.
> - `none`: returns only the base identity line.

配合"子代理会话只注入 `AGENTS.md`,其余 Bootstrap 文件全部过滤掉"这条规则,可以看出一个明确的设计意图:**子代理需要知道"这个工作区的操作规范是什么"(`AGENTS.md`),但不需要知道"这个 Agent 的完整人格设定和长期记忆细节"**——后者是主会话专属的上下文,过度传递给临时性的子任务只会增加 Token 成本、稀释子代理本该聚焦的具体任务指令。

### 5. Agent Workspace:身份与记忆的落地位置

Workspace 是 Agent 的"家"——文件工具和工作区上下文的默认工作目录,`docs/concepts/agent-workspace.md` 一句话点出它和别的目录的区别:

> The workspace is the agent's home: the working directory used for file tools and workspace context. Keep it private and treat it as memory. This is separate from `~/.openclaw/`, which stores config, credentials, and sessions.

默认路径是 `~/.openclaw/workspace`,可以通过 `agents.defaults.workspace` 或按 Agent 单独用 `agents.entries.*.workspace` 覆盖。文档专门强调了一个容易被误解的边界:

> The workspace is the **default cwd**, not a hard sandbox. Tools resolve relative paths against the workspace, but absolute paths can still reach elsewhere on the host unless sandboxing is enabled.

也就是说,Workspace 本质上只是一个"默认相对路径起点",不是隔离边界——真正的隔离要靠 `agents.defaults.sandbox`,这是第 10 章要讲的话题。Workspace 内的文件角色划分很清楚:`AGENTS.md` 是操作指令、`SOUL.md` 是人格与语气(见 `docs/concepts/soul.md`)、`USER.md` 是带日期戳的用户偏好指令集、`IDENTITY.md` 是名字/性格/表情符号、`memory/YYYY-MM-DD.md` 是按日归档的记忆日志、`MEMORY.md` 是精炼后的长期记忆摘要。文档给出的建议是把 Workspace 纳入私有 Git 仓库做备份,但明确排除了 `~/.openclaw/` 下的配置、凭证、会话数据库——这些属于运行时状态而不是 Agent 记忆,不应该混进同一个仓库。

### 6. Agent Bindings:决定"这条消息该给谁"

如果说 Workspace 回答的是"这个 Agent 是谁、记得什么",Agent Bindings 回答的是一个完全正交的问题——"一条进来的消息应该由哪个 Agent 处理"。`docs/concepts/agent-bindings.md` 的开篇定义:

> When a message arrives on a channel, OpenClaw has to decide which agent answers it. By default that is easy: the agent marked `default: true` gets everything. An agent binding overrides that decision for a slice of your traffic.

一条 Binding 由 `agentId` 加一组匹配条件(`channel`、`accountId`、`peer`、`guildId`/`teamId`、`roles`)组成,匹配优先级"按具体程度排序"——具体的会话/群组匹配优先于账号/频道级别的兜底规则,同一优先级内按配置顺序取第一条命中的规则。文档特意用一整节纠正了一个常见误解:

> Bindings only pick the agent. They do not create channel accounts and they do not grant access — a binding is consulted only after the channel has already accepted the message through its normal pairing, allowlist, and account rules.

也就是说,**Binding 不是访问控制**。一条消息能不能被 OpenClaw 接受,取决于 Channel 自己的配对(pairing)、`dmPolicy`、群组策略、允许列表这些独立机制;Binding 只在消息已经被放行之后,决定"放行之后交给哪个 Agent"。反过来,一个指向不存在 `agentId` 的 Binding 也不会报错——它会"静默地路由错误",这是文档专门列出的常见错误之一。

### 7. Workspace 与 Bindings 如何配合

把两者放在一起看,一个典型的多 Agent 场景是:先在 `agents.entries` 里定义好每个 Agent 各自的 `workspace`(决定它的身份文件、记忆文件分别存在哪),再用顶层 `bindings` 把某个 Channel 账号、某个具体会话路由到对应的 `agentId`。文档给出的例子把这个组合关系体现得很清楚——`support` 这个 Agent 有自己独立的 `workspace-support` 目录,`bindings` 里的一条规则把 Discord 上名为 `support` 的账号路由到这个 Agent,而 `main` 仍然是兜底的默认 Agent。这两层配置各自独立生效:改 Workspace 路径不会影响任何路由规则,改 Binding 规则也不会动到任何一个 Agent 的身份/记忆文件——这正是"正交"这个词的含义。

## 常见问题/易踩坑

- **以为 Provider 插件可以随意往 Prompt 里加内容**:实际贡献面被卡得很窄,只能替换 `interaction_style`/`tool_call_style`/`execution_bias` 三个命名 section,或者往 Cache 边界的上方/下方各加一段内容。真正需要改动更大范围的场景应该走 `before_prompt_build` 这个全局 Hook,而且文档明确说这是"兼容性/真正全局变更"专用,不建议作为常规手段。
- **把每轮变化的信息塞进 Cache 边界之前的稳定前缀**:这会导致支持前缀缓存的后端每轮都缓存失效,`system-prompt.md` 的分层原则(Runtime Context 用专门的分隔符载体、时间/频道信息放在边界之后)正是为了避免这个问题。
- **误以为配置了 Workspace 就等于配置了访问控制**:Workspace 只决定文件工具的默认相对路径起点和 Agent 身份记忆的落地位置,不是沙箱边界,更不是"谁能跟这个 Agent 对话"的门禁——门禁分别是 Channel 的配对/allowlist 机制和 Agent Bindings 的路由规则,三者要分开配置、分开排查。
- **Binding 指向了一个不存在的 `agentId`**:这不会报错,只会导致消息被"静默错路由"。新增或修改 Binding 之后,建议用 `openclaw agents list --bindings` 核对一遍匹配结果。

## 小结

OpenClaw 的 System Prompt 不是一份写死的模板,而是纯渲染函数、配置解析层、运行时适配器三层叠加的结果,外加 Provider 插件在三个命名 section 和 Cache 边界两侧留出的窄接口;Workspace Bootstrap 注入机制进一步把 Agent 的身份文件、人格设定、长期记忆按照"稳定 vs 易变""主会话 vs 子代理"两个维度做了精细的取舍,原生 Codex Harness 上甚至进一步把部分注入替换成了"引导模型主动查记忆工具"。而 Agent Workspace(身份、记忆、默认工作目录)和 Agent Bindings(消息路由到哪个 Agent)是两个正交概念,分别解决"这个 Agent 是谁"和"这条消息归谁管"两个不同问题,不应该混为一谈。至此,模型与 Provider 生态这一章就讲完了 Provider 抽象、Failover、Provider 插件契约、System Prompt 组装这四条主线;下一章会把视角从"模型怎么被喂进来"转向"模型能调用哪些能力"——由 Tools、Skills、Plugins 和 MCP 共同构成的能力扩展生态。
