# Agent Loop 总览

> OpenClaw 官方文档给"agent loop"下的定义只有一句话:"the serialized, per-session run that turns a message into actions and a reply: intake, context assembly, model inference, tool execution, streaming, persistence"。这句话本身就是一份提纲——接收输入、组装上下文、模型推理、工具执行、流式输出、持久化落盘,六个阶段串成一次不可交错的单会话运行。本篇沿着 `docs/concepts/agent-loop.md` 给出的真实运行序列,把这六个阶段拆开看,并把它和第三章讲过的 Gateway WS 协议对接起来——一次 `agent` RPC 调用之后,协议层面到底发生了什么。

## 学习目标

- 理解 `agent` RPC 的"立即返回 + 后续流式"两段式设计:调用方拿到 `{ runId, acceptedAt }` 之后,真正的执行在 `agentCommand` → `runEmbeddedAgent` → `subscribeEmbeddedAgentSession` 这条链路里异步展开。
- 理解排队与并发控制中最关键的一环——`activeWriterRunId`/`expectedWriterRunId` 写者声明(writer claim)——如何保证"被顶替的 run 绝不能提交过期的事务记录"。
- 理解 `lifecycle`/`assistant`/`tool` 三条事件流各自承载什么内容,以及它们如何对应第三章 Gateway WS 协议里 `event:agent` 这一类事件。
- 理解 OpenClaw 的两套 Hook 体系——内部 `HOOK.md` 脚本和插件 `api.on(...)` 类型化钩子——分别挂在循环的哪些位置。
- 理解超时体系的分层设计:`agent.wait` 的等待超时和 Agent 运行时本身的执行超时是两个独立的钟,前者不影响后者。

## 背景与设计动机

一个个人助理型 Agent 系统,天然要处理"同一个会话在短时间内收到多条消息"这种情况:用户连续发了三条微信消息,后台的心跳(heartbeat)又恰好触发,子代理的完成通知也在这个时间点回灌。如果每条输入都各自独立地去读会话、拼上下文、发模型请求,几乎必然会出现竞态——两次并发的模型调用各自往同一个会话事务日志里追加内容,谁先谁后、以谁为准,会变成一笔糊涂账。

OpenClaw 的答案是把"一次会话的一次运行"设计成严格串行的单位:同一个 `sessionKey` 在同一时刻只能有一个 run 在真正执行模型推理和工具调用,其余请求要么排队,要么被"引导"(steer)进正在跑的这次 run 里(引导机制是第四篇的主题)。这篇要讲的,是这一次 run 自己内部的完整生命周期——从 RPC 入口到最终的 `lifecycle end`,中间经历了哪些阶段,以及每个阶段各自对"正确性"做了什么保证。

## 核心机制详解

### 入口:两个 Gateway RPC + 一个 CLI 命令

文档列出的入口很直接:

> Gateway RPC: `agent` and `agent.wait`.
> CLI: `openclaw agent`.

`agent` RPC 干的事情很少:校验参数、解析出目标会话(`sessionKey`/`sessionId`)、把会话元数据落盘,然后**立即**返回 `{ runId, acceptedAt }`——调用方在这一步就拿到了一个可以后续追踪的 `runId`,但模型还没有被调用。真正驱动这次对话往前走的,是随后异步展开的 `agentCommand`。

`agent.wait`(内部实现是 `waitForAgentRun`)是配套的等待原语:它在给定的 `runId` 上等待 **lifecycle end/error**,超时或完成后返回 `{ status: ok|error|timeout, startedAt, endedAt, error? }`。文档特别强调了等待结果里还带着 `terminalReply` 和(可用时)`terminalReceipt`:

> A receipt with `sourceReplyDelivered: true` confirms a final reply reached the external source conversation.

这个细节值得注意——"model 认为自己回复完了"和"这条回复真的送达了外部渠道"是两件事,`terminalReceipt` 就是用来区分这两者的,后面第七篇讲 Channels 网关时还会再遇到这个概念。

### 五步运行序列

文档把一次运行按顺序拆成五步,这五步基本对应"RPC 层 → 命令层 → 运行时层 → 事件桥接层 → 等待层"这条自上而下的调用链:

1. `agent` RPC 校验参数、解析会话、持久化元数据,立即返回 `{ runId, acceptedAt }`。
2. `agentCommand` 跑这一轮对话:解析模型和 thinking/verbose/trace 的默认值、加载技能快照、调用 `runEmbeddedAgent`,并且在内嵌循环没有自己发出终态事件时,补发一个兜底的 **lifecycle end/error**。
3. `runEmbeddedAgent`:通过每会话和全局两级队列串行化运行、解析模型和认证 profile、构建 OpenClaw 会话、订阅运行时事件、流式输出 assistant/tool 增量、强制执行运行超时(到期即中止),最终返回响应载荷和用量元数据。文档特别指出,对于 Codex app-server 这类外部运行时的轮次,"native Codex 拥有 provider 存活判断权和精确的 `turn/completed` 结果";安静期和 assistant 输出本身并不能判定这一轮结束——这是"运行时边界"这个概念的一个具体例子,第五篇讲模型与 Provider 生态时会继续展开。
4. `subscribeEmbeddedAgentSession` 把运行时事件桥接到 `agent` 这个 stream 上:工具事件进 `stream: "tool"`,assistant 增量进 `stream: "assistant"`,生命周期事件进 `stream: "lifecycle"`(`phase: "start" | "finishing" | "end" | "error"`)。
5. `agent.wait` 在指定 `runId` 上等待 **lifecycle end/error**,返回终态。

这五步里,第 3 步是真正"重"的部分——它同时承担了排队、模型解析、会话构建、超时控制四件事,下一节展开讲排队与并发这一部分。

### 排队与并发:写者声明防止过期提交

多个 run 可能因为不同原因排队等待同一个会话——第四篇专门讲的 steer/followup/collect/interrupt 四种队列模式就是消费这套排队系统的上层策略。这里先讲底层保证:

> Runs are serialized per session key (session lane) and optionally through a global lane, preventing tool/session races.

真正有意思的是"被顶替的 run 会怎样"这个问题。文档写道:

> Before streaming, an admitted run records its durable `activeWriterRunId` claim. Every transcript append or rewrite supplies `expectedWriterRunId`, and the synchronous commit transaction verifies that it still matches the active claim. A superseded run therefore cannot commit stale transcript data.

也就是说,一个 run 被允许开始流式输出之前,先要在会话记录里登记一个"写者声明"——这个 run 的 `runId` 就是当前会话事务日志唯一认可的写者。之后每一次对话记录的追加或重写(append/rewrite),都必须带上它期望匹配的 `expectedWriterRunId`;真正提交事务的那一刻,系统会核对这个期望值和当前登记的 `activeWriterRunId` 是否一致——不一致就拒绝提交。源码里能验证到这套护栏具体长什么样:

```typescript
// src/config/sessions/session-accessor.sqlite-transcript-write-guard.ts
export function resolveTranscriptAppendRefusal(
  entry: InternalSessionEntry | undefined,
  resolved: ResolvedTranscriptScope,
  scope: SessionTranscriptWriteScope,
): TranscriptAppendRefusal | undefined {
  if (
    entry &&
    entry.sessionId === resolved.sessionId &&
    (scope.expectedLifecycleRevision === undefined ||
      entry.lifecycleRevision === scope.expectedLifecycleRevision) &&
    (scope.expectedWriterRunId === undefined ||
      entry.activeWriterRunId === scope.expectedWriterRunId)
  ) {
    return undefined;
  }
  // ... 返回 "session-entry-missing" 或 "session-rebound" 两种拒绝原因
}
```

这套机制和第三篇要讲的 checkpoint/compaction 事务是同一层次的问题——**一旦有真实副作用(追加对话记录)要发生,系统就要先证明"我还是这个会话当前唯一被认可的执行者"**。压缩、截断(truncation)复用的是同一个"事务内写者声明栅栏"(in-transaction writer-claim fence),而不是各自发明一套校验逻辑。

再往上一层是资源隔离:"The SQLite writer queue orders per-agent mutations, while the Gateway state-directory lock prevents another Gateway or `openclaw agent --local` process from owning the same state directory concurrently"——单个 Agent 内部的写入由 SQLite 写队列排序,跨进程的冲突则由 Gateway 状态目录锁挡住,两层加起来才是完整的并发安全边界。

### 会话与工作区准备

在真正调用模型之前,`runEmbeddedAgent` 还要完成几件准备工作:

- 解析并创建工作区(workspace);沙箱化的运行可能会重定向到一个沙箱工作区根目录。
- 加载技能(从快照复用,或重新加载),注入到环境变量和 system prompt 里。
- 解析 Bootstrap/上下文文件(`AGENTS.md`/`SOUL.md`/`IDENTITY.md`/`USER.md`/`MEMORY.md` 等),注入 system prompt。
- 准备好会话事务日志的写入目标和写者声明——"Later rewrites, compaction, and truncation use the same in-transaction writer-claim fence",呼应上一节讲的机制。

这一整套"工作区+会话"准备逻辑,正是第四篇专门讲 Session 生命周期文章要深入的内容;本篇只标出它在循环里的位置。

### 两套 Hook 体系

OpenClaw 区分"内部钩子"和"插件钩子"两套完全不同的挂载机制:

> - **Internal hooks**: `HOOK.md` scripts for command and lifecycle events such as `command:new`.
> - **Plugin hooks**: typed `api.on(...)` handlers inside the agent/tool lifecycle and Gateway pipeline, such as `before_tool_call`.

插件钩子表里最值得留意的几个决策点:

| Hook | 挂载时机 |
| --- | --- |
| `before_model_resolve` | 会话加载前(还没有 `messages`),用来确定性地覆盖 provider/model |
| `before_prompt_build` | 会话加载后(已有 `messages`),可以注入 `prependContext`/`systemPromptAddition`,或者用 `toolsAllow` 收窄当轮工具面 |
| `before_agent_reply` | 内联动作(inline actions)之后、真正调用 LLM 之前——插件可以在这里"截胡"整轮对话,返回一个合成回复或者直接静默 |
| `agent_end` | 完成之后,带着最终消息列表和运行元数据 |
| `before_compaction`/`after_compaction` | 观察压缩周期(注意:这两个钩子**不能**改写或否决压缩本身) |
| `before_tool_call`/`after_tool_call` | 拦截工具参数/结果 |

文档对 `before_tool_call` 的决策语义写得很明确,这类"是否拦截"的钩子普遍遵循同一条规则:

> `{ block: true }` is terminal and stops lower-priority handlers. `{ block: false }` is a no-op and does not clear a prior block.

也就是说,拦截是"一票否决制":一旦有钩子说了"block",后面优先级更低的钩子无法反悔;而"不拦截"从来不是一个主动的许可动作,只是"这个钩子没有意见"。这条规则同时适用于 `before_install` 和 `message_sending` 的 `cancel` 语义,是一条贯穿整个钩子系统的设计原则。

### 事件流:lifecycle / assistant / tool

`subscribeEmbeddedAgentSession` 桥接出的三条流是整个 Agent Loop 对外可观测性的全部来源:

- `lifecycle`:由 `subscribeEmbeddedAgentSession` 发出(`agentCommand` 在内嵌循环没有自己发出终态事件时兜底补发一个)。
- `assistant`:运行时流出的增量文本。
- `tool`:运行时流出的工具事件。

如果按第三章介绍的 Gateway WS 信封约定来标注,这三条流大致对应关系是:`agent` RPC 的调用与它的立即返回对应一次 `req:agent`;之后 `lifecycle`/`assistant`/`tool` 三条流上持续产生的每一个事件,对应协议层面一连串的 `event:agent`;而 `agent.wait` 最终等到的 `lifecycle end/error`,对应这次调用真正意义上的 `res:agent`——一次同步 RPC 的"立即确认"和一次异步流式过程的"最终结果",在协议层面是分离的两件事,`agent.wait` 就是把二者重新缝合起来的机制。

工具执行这一层还有两条附加规则值得记住:"Tool results are sanitized for size and image payloads before logging/emitting"(工具结果在记录/发出之前要做体积和图片载荷的脱敏/裁剪),以及"Messaging tool sends are tracked to suppress duplicate assistant confirmations"(消息类工具的发送会被跟踪,避免助手对同一次发送重复确认)。

Gateway 还会把 lifecycle 和工具起止事件投影进一个有边界的、只含元数据的审计台账(audit ledger):"This projection records provenance and result codes without copying prompts, messages, tool arguments, tool results, or raw errors out of the transcript/runtime path"——审计只留痕迹,不留内容,这是一条贯穿全书的安全设计取向,第十篇讲安全与沙箱时会再遇到。

### 回复整形与 NO_REPLY 静默令牌

一次运行最终交付给用户的载荷,是从几个来源拼起来的:assistant 文本(加上可选的 reasoning)、内联工具摘要(仅在 verbose 且允许时)、以及模型报错时的 assistant 错误文本。这里有三条值得记住的规则:

- 精确的静默令牌 `NO_REPLY` 会在输出载荷里被过滤掉——这是模型主动表达"这一轮不需要回复用户"的方式,第五篇讲多代理协作时会再次遇到这个令牌(子代理完成通知到达但答案已经发出时,正确的处理方式就是回一个 `NO_REPLY`)。
- 消息类工具已经发送过的内容,会从最终载荷列表里去重。
- "一次运行以工具失败收尾、且否则会让用户什么都收不到"这种情况下,才会出现一条兜底的工具错误提示——这条规则不可配置,任何已经交付给用户的回复(哪怕是消息工具自己发出的)都会让这条兜底提示不出现。

### 超时:两个独立的钟

超时体系的设计原则是"层层限界,互不覆盖"。最容易搞混的一组是:

| 超时 | 默认值 | 备注 |
| --- | --- | --- |
| `agent.wait` | 30s | 仅影响等待本身,`timeoutMs` 可覆盖;**不会**停止底层运行 |
| Agent 运行时(`agents.defaults.timeoutSeconds`) | 172800s(48h) | 真正的执行预算,到期即中止;进度不会重置这个钟;设为 `0` 表示不限时 |

`agent.wait` 超时只是"这次等待没等到结果",并不代表运行本身被取消或失败——文档专门提醒:"It does not cancel the run or identify its execution phase; wait on the same `runId` again to observe completion"。这个设计的合理性在于:等待方(可能是 webchat 的一次短轮询)和执行方(可能真的需要跑几分钟工具)的生命周期没有必要绑死在一起。

一次运行能够提前结束的四种途径,文档列得很干脆:

> - Agent timeout (abort)
> - AbortSignal (cancel)
> - Gateway disconnect or RPC timeout
> - `agent.wait` timeout (wait-only, does not stop the agent)

注意最后一项特意标注"不会停止 Agent"——它和前三种真正意义上的终止是不同性质的事件。

## 常见问题/易踩坑

- **`agent.wait` 超时不是运行失败**:很容易把"等待超时"误读成"这次对话失败了"。正确的处理方式是用同一个 `runId` 再等一次,而不是假设运行已经终止或重新发起一次新的 `agent` 调用。
- **诊断阈值区分"忙"和"卡死"**:文档定义了三种诊断状态——`session.long_running`(活跃但正常慢)、`session.stalled`(活跃但无最近进展)、`session.stuck`(可恢复的陈旧会话记账)。中止阈值"至少 5 分钟且是警告阈值的 3 倍",这个设计是为了不让"provider 响应慢"和"真的卡住了"被同一条告警误伤。
- **Codex 等外部运行时的终态判定权不在 OpenClaw**:文档反复强调"native Codex owns provider liveness and the exact `turn/completed` outcome",这意味着安静期或者已经流出 assistant 文本,都不能作为这一轮结束的判据——这条边界在后面讲运行时(agent-runtimes)差异时还会遇到。

## 小结

这一篇沿着 RPC 入口、五步运行序列、写者声明、事件流、Hook 体系、超时分层这几条线,把一次 Agent Loop 从"消息进来"到"回复出去"的完整链路过了一遍。可以看到,这条链路里有两处反复出现的设计取向:**一是把"确认接受"和"真正完成"分离**(`agent` 的立即返回 vs `agent.wait` 的终态等待、`activeWriterRunId` 声明 vs 真正的事务提交),**二是把审计/可观测性和内容本身分离**(只投影元数据的审计台账)。这两条线其实都指向同一个更底层的问题——一次运行所依附的**会话**到底是什么、它的生命周期怎么管理、多个运行在同一个会话上竞争时状态机怎么走。下一篇就转向这个问题。
