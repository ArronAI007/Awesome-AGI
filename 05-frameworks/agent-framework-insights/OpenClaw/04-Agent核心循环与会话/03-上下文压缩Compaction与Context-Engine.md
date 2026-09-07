# 上下文压缩 Compaction 与 Context Engine

> 上一篇讲的 Pruning 只能裁剪工具结果,治标不治本——当整个对话历史本身逼近模型上下文窗口时,真正需要的是把旧对话摘要化。OpenClaw 把这件事拆成了两层:**Compaction** 是"怎么把旧历史变成一段摘要"的具体算法,**Context Engine** 是"每次模型调用该往上下文里放什么"的可插拔编排层,四个生命周期钩子(ingest/assemble/compact/afterTurn)覆盖了从消息入库到压缩触发的全过程。默认的 `legacy` 引擎只是把压缩这一件事委托给内置摘要器,但整套接口设计成了插件可以整体接管的形状。本篇先讲压缩本身怎么做,再讲 Context Engine 这层编排,最后用 `src/context-engine/` 的源码验证文档里几处关键断言。

## 学习目标

- 理解 Compaction 的两个触发点——接近阈值的主动压缩、provider 明确报出上下文溢出后的被动压缩重试——以及"保持工具调用与结果配对"这条切分点约束。
- 理解 `safeguard` 压缩模式的质量审计流程:摘要生成后还要过一遍校验,校验失败允许有限次数的纠正重试,始终失败就放弃这次压缩、保留原始历史。
- 理解 Context Engine 四个生命周期钩子(ingest/assemble/compact/afterTurn)各自的职责,以及 `ownsCompaction` 如何决定内置自动压缩是否让位给插件引擎。
- 通过 `legacy.ts`/`delegate.ts`/`quarantine-health.ts` 源码,验证"legacy 引擎只是把压缩请求转发给内置运行时"和"插件引擎失败时会被隔离(quarantine),而不是让整个回复链路挂掉"这两个断言。
- 理解 Compaction 和 Pruning 在"保存了什么"这个维度上的本质区别。

## 背景与设计动机

每个模型都有一个硬性的上下文窗口上限,长对话迟早会撞到这个上限。朴素的做法是"到了阈值就摘要",但这个朴素做法背后至少有三个需要认真设计的问题:

- **摘要必须在结构上尊重对话的完整性**:如果切分点恰好落在一次工具调用和它的结果中间,派生出的历史会出现一次没有结果的裸调用,这不仅让模型困惑,更严重的是可能违反 provider 侧"assistant 消息后必须紧跟工具结果"这类格式强约束。
- **摘要本身可能失败,而且失败的方式不止一种**:模型可能生成一个比原文还长的摘要(等于白干),也可能在质量上不满足要求(比如遗漏了必须保留的操作事项)。系统需要能识别这些失败,而不是无条件接受任何生成结果。
- **压缩策略应该是可替换的**,因为不同场景对"怎么压缩"有截然不同的需求——有的用户希望换一个更便宜的模型来做摘要,有的第三方插件想用向量检索或 DAG 摘要取代简单的线性摘要。

OpenClaw 用"两个触发点 + 质量审计"应对第一、二个问题,用"Context Engine 可插拔接口 + `ownsCompaction` 开关"应对第三个问题。这两层加起来,才是"上下文超限时系统怎么处理"这个问题的完整答案。

## 核心机制详解

### 触发条件:主动阈值 vs 被动溢出

自动压缩默认开启,触发条件是两种:"接近上下文限制"和"模型返回了上下文溢出错误(此时压缩后重试)"。文档专门列出了 OpenClaw 能识别的一批 provider 特定溢出错误字符串,覆盖 Anthropic、OpenAI、Bedrock、Gemini、Ollama、OpenRouter 等,例如 `request_too_large`、`context length exceeded`、Bedrock 的 `input token count exceeds the maximum number of input tokens` 等——这意味着"被动恢复"这条路径不依赖单一 provider 的错误格式,而是维护了一份跨 provider 的模式匹配表。

压缩切分点的选择遵守同一条结构约束,和上一篇 Pruning 的安全规则是同一种设计哲学:

> OpenClaw keeps assistant tool calls paired with their matching `toolResult` entries when it picks a compaction split point. If the point lands inside a tool block, OpenClaw moves the boundary so the pair stays together and the current unsummarized tail is preserved.

### 摘要器怎么处理多语言和多模态输入

内置摘要器对中日韩(CJK)字符做了专门的分块估算适配:"The built-in summarizer accounts for Chinese, Japanese, and Korean (CJK) characters in both message text and tool arguments when estimating chunk sizes"。对于图片等非文本输入,摘要器接收不到像素数据,只会插入类似 `[image data omitted from summary input]` 这样的占位标记,并且这类标记本身的体积是受控的:

> These additions, including newly retained role labels and separators, total at most 847 UTF-8 bytes per summarizer request and count toward token estimates.

847 字节这个具体数字说明这不是一个随口的"大概不会太大",而是一个被工程量化过的预算上限——占位标记本身也要计入 token 估算,不能因为"只是个占位符"就放任它无限增长。

### safeguard 模式:摘要生成之后还要过一道质量审计

新配置默认把 `agents.defaults.compaction.mode` 设为 `"safeguard"`(更严格的护栏 + 摘要质量审计),需要显式设 `mode: "default"` 才能退回旧行为。这个模式下,摘要通过审计的标准很具体:

> Required headings must remain in the retained generated body, while pending asks and exact identifiers must remain in the exact text that would be stored. Invalid output gets only the configured number of corrective attempts. If no finalized summary passes, compaction stops before writing a transcript entry, keeps the original history, and surfaces the existing recovery outcome.

也就是说,审计不是简单地"看摘要长不长",而是校验必须保留的标题结构、待办事项、精确标识符是否还留在生成文本里。纠正重试的次数是有限的,而"始终没有一份摘要通过审计"时,系统选择的是**保留原始历史、不写入这次压缩事务**,而不是"凑合接受一个不合格的摘要"或者"重试到天荒地老"。这条设计和上一篇 Pruning 的"两条硬编码安全规则"、第一篇 Agent Loop 的"写者声明栅栏"是同一个价值取向的第三次出现:**在正确性和推进之间选择正确性**。

摘要质量的另一重护栏是"不能变大":标识符保留策略默认是 `identifierPolicy: "strict"`,配合安全模式一起,确保压缩不会因为丢失关键标识符而让后续对话对不上号。

### 手动 /compact 与 focus 指令

`/compact` 支持带一段自由文本引导摘要方向,比如 `/compact Focus on the API design decisions`。这段自由文本不是直接拼进 prompt,而是有边界处理的:"The host limits operator-provided focus to 800 Unicode code points and escapes it as prompt data before adding it to model requests"——限长且转义,避免用户输入的自由文本被解释成额外的系统指令。客户端手动压缩用 `agents.defaults.compaction.keepRecentTokens`(默认 20000)作为切分预算,决定保留多少最近的对话尾部。

### Context Engine:四个生命周期钩子

如果说 Compaction 回答的是"旧历史怎么变成摘要",Context Engine 回答的是更上层的问题——"每次模型调用之前,到底该往上下文里放哪些消息"。文档把这一层的职责描述得很直接:

> A **context engine** controls how OpenClaw builds model context for each run: which messages to include, how to summarize older history, and how to manage context across subagent boundaries.

每次模型调用,这个引擎会在四个生命周期点介入:

1. **Ingest**:新消息加入会话时调用,引擎可以把消息存进自己的数据存储或索引。
2. **Assemble**:每次模型运行前调用,引擎返回一组排好序、放得进 token 预算的消息(可选附带 `systemPromptAddition`)。
3. **Compact**:上下文窗口满了,或者用户手动 `/compact` 时调用,引擎负责摘要旧历史腾出空间。
4. **After turn**:一次运行完成后调用,引擎可以持久化状态、触发后台压缩或更新索引。

OpenClaw 默认使用内置的 `legacy` 引擎——它的四个钩子实现分别是:ingest 空操作(会话管理器自己处理消息持久化)、assemble 直通(现有的 sanitize → validate → limit 流水线在运行时里处理组装)、compact 委托给内置摘要压缩、after turn 空操作。源码里能直接看到这个"委托"是怎么实现的:

```typescript
// src/context-engine/legacy.ts
export class LegacyContextEngine implements ContextEngine {
  readonly info: ContextEngineInfo = {
    id: "legacy",
    name: "Legacy Context Engine",
    version: "1.0.0",
    acceptedHostParams: [...CONTEXT_ENGINE_HOST_PARAMS],
  };

  async ingest(_params: Parameters<ContextEngine["ingest"]>[0]) {
    // No-op: SessionManager handles message persistence in the legacy flow
    return { ingested: false };
  }

  async assemble(params: Parameters<ContextEngine["assemble"]>[0]): Promise<AssembleResult> {
    return {
      messages: params.messages,
      estimatedTokens: 0, // Caller handles estimation
    };
  }

  // Preserve the canonical delegate identity so the host knows the built-in
  // runtime, rather than this engine wrapper, owns the compaction watchdog.
  readonly compact = delegateCompactionToRuntime;
}
```

注意最后一行的注释——`compact` 字段被直接赋值成 `delegateCompactionToRuntime` 这个函数引用,而不是包一层新函数体去调用它。注释解释了原因:**要保留"这是内置运行时在拥有压缩看门狗"这个身份标记**,而不是让 legacy 引擎的包装层意外地"顶替"了这个身份。`delegate.ts` 里可以看到这层身份标记的具体实现——`markRuntimeCompactionDelegate(delegateCompactionToRuntime)` 把这个函数注册进一个全局 `WeakSet`,而 `compaction-watchdog.ts` 里的 `isRuntimeCompactionDelegate()` 就是用这个 `WeakSet` 来判断"眼前这个 `compact` 方法,到底是不是内置运行时自己的那一个"。这段源码解释了为什么文档反复强调"legacy engine 是对既有行为的封装,不是重新实现"——它字面意义上就是同一个函数指针。

### ownsCompaction:接管压缩 vs 委托压缩

插件引擎有两种合法的工作模式,由 `ownsCompaction` 这个字段决定:

> **`ownsCompaction: true`**: The engine owns compaction behavior. OpenClaw disables OpenClaw runtime's built-in auto-compaction and generic pre-prompt overflow precheck for that run, and the engine's `compact()` implementation is responsible for `/compact`, provider overflow recovery compaction, and any proactive compaction it wants to do in `afterTurn()`.
>
> **`ownsCompaction: false` or unset**: OpenClaw runtime's built-in auto-compaction may still run during prompt execution, but the active engine's `compact()` method is still called for `/compact` and overflow recovery.

文档特意用一个警告框纠正了一个容易犯的错:"`ownsCompaction: false` does **not** mean OpenClaw automatically falls back to the legacy engine's compaction path"——即便设成 `false`,当前生效的引擎的 `compact()` 依然会被调用来处理 `/compact` 和溢出恢复,只是内置的自动压缩流程也可能并行生效。真正想要"委托模式"的插件,需要在自己的 `compact()` 实现里显式调用 `delegateCompactionToRuntime(...)`——`delegate.ts` 里能看到这个函数的完整实现,它做的事情是把参数桥接到运行时内部的 `compactEmbeddedAgentSessionOnDemand`,同时前置了一层身份一致性校验:

```typescript
// src/context-engine/delegate.ts(节选)
assertCompactionSessionIdentity({
  agentId,
  sessionId: params.sessionId,
  sessionKey,
  sessionTarget,
});
```

这段校验拒绝的是"调用方声称的会话身份"和"压缩目标携带的会话身份"互相矛盾的请求——注释写得很直白:"Reject contradictory caller identity before loading or invoking the compactor: target precedence inside the runtime must not hide an invalid request"。这是一个很小但很典型的例子,说明即便是"委托给内置运行时"这种看起来只是转发调用的辅助函数,也没有省略身份校验这一步。

### 失败隔离:插件引擎坏了,不能让整个回复链路陪葬

一个自定义 Context Engine 完全可能出 bug——缺失、契约校验失败、工厂创建时抛异常、某个生命周期方法运行时抛异常。文档描述的处理方式是隔离,而不是让整个 Agent Loop 跟着失败:

> OpenClaw isolates the selected plugin engine from the core reply path. ... OpenClaw quarantines that engine for the current Gateway process and downgrades context-engine work to the built-in `legacy` engine. The error is logged with the failed operation so the operator can repair, update, or disable the plugin without the agent going silent.

源码里能看到这套隔离状态是怎么在多进程环境下保持一致的——`quarantine-health.ts` 把隔离记录持久化到一个共享的运行时健康存储里,并且明确采用"最早失败者优先"的策略:

```typescript
// src/context-engine/quarantine-health.ts(节选)
// Earliest wins, matching the in-memory registry's first-failure-wins rule
// so health output points at the root cause, not follow-on failures.
pick: "earliest",
```

这个"最早失败优先"的策略是有意为之的——一次隔离触发之后,同一个引擎大概率还会因为同样的根因继续失败,如果每次失败都覆盖记录,运维看到的会是最新一次(往往是级联出来的)失败现象,而不是真正的根因。

需要单独区分的是"引擎失败被隔离"和"host requirement 不满足"这两种情况的处理方式完全不同:后者是**在运行开始之前就直接拒绝**,因为"That protects engines that would corrupt state if they ran in an unsupported host"——比如一个引擎声明自己需要 `assemble-before-prompt` 这个能力,而当前运行时(比如某些通用 CLI backend)根本不支持在真正发模型请求前由引擎控制 prompt,这种情况下 fail closed 是唯一安全的选择。

### Compaction vs Pruning:一张表说清楚

|            | Compaction                    | Pruning                          |
| ---------- | ------------------------------ | -------------------------------- |
| **做什么** | 摘要旧对话 | 裁剪旧工具结果 |
| **保存吗** | 是(摘要写进会话事务日志) | 否(仅内存投影,或由 provider 服务端清理) |
| **范围**   | 整个对话 | 仅工具结果 |

这张表和上一篇的对照表几乎一致,再次印证了这两套机制是设计上互补而非重叠的关系——"pruning keeps tool output lean between compaction cycles"。

## 常见问题/易踩坑

- **`ownsCompaction: false` 不等于自动回退到 legacy**:这是文档专门用警告框强调的一点,一个"空实现"的 `compact()` 对非接管型引擎是不安全的,因为它会悄悄关掉这个引擎槽位上正常的 `/compact` 和溢出恢复路径。
- **`maxActiveTranscriptBytes` 只对活跃 SQLite 事务日志生效**:文档专门用警告框区分了这一点——"Legacy JSONL checkpoint artifacts are not the active compaction target"。如果观察到旧的 JSONL 检查点文件体积持续增长,不能指望这个字节护栏去处理它。
- **provider 端 checkpoint 的容量上限是 16 MiB**:当嵌入式 Responses provider 返回一个压缩窗口时,OpenClaw 会连同这个 checkpoint 一起保留,但"oversized or incompatible endpoint output uses the normal client-side compaction path instead of being truncated"——超限时走的是正常压缩路径,而不是简单截断。
- **摘要模型的选择不会改变前台模型的上下文窗口**:即便配置了一个上下文窗口更大的模型专门做摘要(`agents.defaults.compaction.model`),这个改动不会让前台对话模型本身获得更大的窗口——"Choosing a larger summarization model does not increase the foreground model's context window"。

## 小结

这一篇讲了 Compaction 怎么做(两个触发点、结构完整性约束、safeguard 质量审计)和 Context Engine 怎么编排(四个生命周期钩子、`ownsCompaction` 的接管/委托两种模式、失败隔离机制),并且用 `legacy.ts`/`delegate.ts`/`quarantine-health.ts` 的源码验证了文档里几处关键断言。到这里,单个会话内部"怎么组织上下文"的问题已经讲完了。但一个常驻的 Gateway 进程面对的从来不是单个会话——多个渠道的并发消息随时可能同时抵达同一个或不同的会话。下一篇转向这个并发控制问题:命令队列(Command Queue)怎么排队,以及"引导"(steering)这种柔性中途插话机制怎么设计。
