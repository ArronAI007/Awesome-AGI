# 上下文压缩 Compaction 与分支摘要

> 模型的上下文窗口是有限资源,而一次长时间的编码会话很容易产生远超窗口大小的历史记录。pi 用两套几乎同构的机制应对这个问题：**压缩(compaction)**在上下文快装不下时把旧历史折叠成一段结构化摘要,**分支摘要(branch summarization)**在用户用 `/tree` 放弃一条探索路径时把它的精华保留下来。本篇结合 `compaction.ts` 源码和 `compaction.md` 文档,讲清楚触发时机、裁剪算法与摘要生成流程。

## 学习目标

- 理解为什么需要压缩：上下文窗口限制、成本控制、以及模型在超长上下文里表现会下降的现实约束。
- 掌握压缩触发的两个条件（阈值触发 `threshold` 与错误恢复触发 `overflow`）及其判定代码。
- 理解"裁剪点(cut point)"的选取算法 `findCutPoint`,以及"分裂轮次(split turn)"这种边界情况如何被特殊处理。
- 理解分支摘要与压缩共享的文件追踪、消息序列化、结构化摘要格式三套基础设施。
- 知道扩展如何通过 `session_before_compact`/`session_before_tree` 事件接管或取消这两套流程。

## 背景与设计动机

上下文窗口不是越大越好用——即使模型支持 100 万 token 的窗口,一次请求带着几十万 token 的历史发过去,既昂贵又会稀释模型对近期真正相关信息的注意力。所以 pi 的策略不是"一直塞到塞不下为止",而是主动地、渐进式地把旧内容"折叠"成摘要,只在上下文里保留：一段结构化的历史摘要 + 最近一段时间内完整保留的原始消息。这本质上是一种有损压缩,但压缩的对象是"人类/模型自己生成的结构化总结",而不是简单截断——所以关键信息(文件路径、决策依据、未完成事项)能够跨越多次压缩持续传递下去。

## 核心机制详解

### 触发条件:何时启动压缩

`packages/coding-agent/src/core/compaction/compaction.ts` 给出了最基础的判定函数：

```typescript
export function shouldCompact(contextTokens: number, contextWindow: number, settings: CompactionSettings): boolean {
	if (!settings.enabled) return false;
	return contextTokens > contextWindow - settings.reserveTokens;
}
```

默认配置（`DEFAULT_COMPACTION_SETTINGS`）是 `reserveTokens: 16384`（给本轮模型回复预留的空间）、`keepRecentTokens: 20000`（压缩后至少保留的近期 token 数）。这个函数在 `AgentSession`（`packages/coding-agent/src/core/agent-session.ts`）里的调用点紧跟在每一轮 `turn_end` 处理之后：

```typescript
// packages/coding-agent/src/core/agent-session.ts(节选)
let contextTokens: number;
const directContextTokens = assistantMessage.usage ? calculateContextTokens(assistantMessage.usage) : 0;
if (assistantMessage.stopReason === "error" || directContextTokens === 0) {
	// Provider 报错或返回了全零 usage 时,退化成基于字符数的估算
	const messages = this.agent.state.messages;
	const estimate = estimateContextTokens(messages);
	if (estimate.lastUsageIndex === null) return false;
	// 校验 usage 来源是不是压缩之后的——避免"刚压缩完就用旧的、偏大的 usage 误判又该压缩了"
	const usageMsg = messages[estimate.lastUsageIndex];
	if (compactionEntry && usageMsg.role === "assistant" &&
		(usageMsg as AssistantMessage).timestamp <= new Date(compactionEntry.timestamp).getTime()) {
		return false;
	}
	contextTokens = estimate.tokens;
} else {
	contextTokens = directContextTokens;
}
if (shouldCompact(contextTokens, contextWindow, settings)) {
	return await this._runAutoCompaction("threshold", false);
}
```

也就是说,pi 优先用 **Provider 在响应里报告的真实 token 使用量**（`assistantMessage.usage`）来判断,只有在报错或者拿到全零 usage 这类异常情况下才退回到`estimateContextTokens`——一种基于字符数的保守启发式估算（大致是"4 个字符≈1 个 token",图片按固定 4800 字符估算,详见 `estimateTokens` 函数）。这种"优先用真实数据、退化路径用估算"的分层策略,在准确性和鲁棒性之间做了平衡。

除了这种**阈值触发(`threshold`)**,还有一种**溢出恢复触发(`overflow`)**——当一次模型请求因为上下文实际超限被 Provider 直接拒绝时,pi 会先压缩再重试这次请求（`willRetry` 参数标记这种场景）。两种触发对应 `session_before_compact`/`session_compact` 事件里的 `reason` 字段（`"manual" | "threshold" | "overflow"`）,`"manual"` 对应用户主动执行 `/compact`。

### 裁剪点算法:`findCutPoint`

压缩要回答的核心问题是"从哪里切一刀,切之前的历史拿去总结,切之后的原样保留"。`findCutPoint` 的算法是**从最新消息往前累加 token 估算值,一旦达到 `keepRecentTokens` 就在该处附近找一个合法的切点**：

```typescript
// packages/coding-agent/src/core/compaction/compaction.ts
export function findCutPoint(
	entries: Entry[], startIndex: number, endIndex: number, keepRecentTokens: number,
): CutPointResult {
	const cutPoints = findValidCutPoints(entries, startIndex, endIndex);
	if (cutPoints.length === 0) return { firstKeptEntryIndex: startIndex, turnStartIndex: -1, isSplitTurn: false };

	let accumulatedTokens = 0;
	let cutIndex = cutPoints[0];
	for (let i = endIndex - 1; i >= startIndex; i--) {
		const entry = entries[i];
		if (entry.type !== "message") continue;
		accumulatedTokens += estimateTokens(entry.message as AgentMessage);
		if (accumulatedTokens >= keepRecentTokens) {
			for (let c = 0; c < cutPoints.length; c++) {
				if (cutPoints[c] >= i) { cutIndex = cutPoints[c]; break; }
			}
			break;
		}
	}
	// 微调:向前吸附到最近的合法边界(不能切在 compaction/tool result 中间)
	while (cutIndex > startIndex) {
		const prevEntry = entries[cutIndex - 1];
		if (prevEntry.type === "compaction" || prevEntry.type === "message") break;
		cutIndex--;
	}
	const cutEntry = entries[cutIndex];
	const isUserMessage = cutEntry.type === "message" && cutEntry.message.role === "user";
	const turnStartIndex = isUserMessage ? -1 : findTurnStartIndex(entries, cutIndex, startIndex);
	return { firstKeptEntryIndex: cutIndex, turnStartIndex, isSplitTurn: !isUserMessage && turnStartIndex !== -1 };
}
```

哪些位置是"合法的切点"由 `findValidCutPoints` 决定：

```typescript
function findValidCutPoints(entries: Entry[], startIndex: number, endIndex: number): number[] {
	const cutPoints: number[] = [];
	for (let i = startIndex; i < endIndex; i++) {
		const entry = entries[i];
		if (entry.type === "message") {
			const role = entry.message.role;
			switch (role) {
				case "bashExecution": case "custom": case "branchSummary": case "compactionSummary":
				case "user": case "assistant":
					cutPoints.push(i);
					break;
				case "toolResult":
					break; // 绝不能在这里切
			}
		}
		if (entry.type === "branch_summary") cutPoints.push(i);
	}
	return cutPoints;
}
```

规则很直接：**永远不能在 `toolResult` 消息处切断**,因为工具结果必须和触发它的那个 `toolCall`（在 assistant 消息里）保持在同一段上下文中——如果把 `assistant(含toolCall)` 保留下来而把紧随其后的 `toolResult` 切进摘要里去掉,模型下次看到的历史就会出现"一个从未被回答的工具调用",这是绝大多数 Provider 都会拒绝或产生异常行为的非法状态。

### 分裂轮次(Split Turn):当一整轮就超过了保留预算

如果用户的一次请求引发了一长串工具调用(比如连续读了几十个文件),仅这一"轮"（从 user 消息开始,到下一个 user 消息之前）就可能超过 `keepRecentTokens`,此时找到的切点会落在轮次中间的某条 assistant 消息上,而不是轮次开头的 user 消息——这就是"分裂轮次(split turn)"：

```typescript
// findCutPoint 的收尾判断
const isUserMessage = cutEntry.type === "message" && cutEntry.message.role === "user";
const turnStartIndex = isUserMessage ? -1 : findTurnStartIndex(entries, cutIndex, startIndex);
return { ..., isSplitTurn: !isUserMessage && turnStartIndex !== -1 };
```

`compaction.md` 用一张图说明了这种情况：

```text
entry:  0     1     2      3     4      5      6     7      8
      ┌─────┬─────┬─────┬──────┬─────┬──────┬──────┬─────┬──────┐
      │ hdr │ usr │ ass │ tool │ ass │ tool │ tool │ ass │ tool │
      └─────┴─────┴─────┴──────┴─────┴──────┴──────┴─────┴──────┘
              ↑                                     ↑
       turnStartIndex = 1                  firstKeptEntryId = 7
              └──── turnPrefixMessages(1-6) ────────┘
                                                    └── kept(7-8)
```

处理分裂轮次时,`prepareCompaction`/`compact` 会生成**两段摘要并拼接**：

```typescript
// packages/coding-agent/src/core/compaction/compaction.ts(节选自 compact 函数)
if (isSplitTurn && turnPrefixMessages.length > 0) {
	let historyText = "No prior history.";
	if (messagesToSummarize.length > 0) {
		const historyResult = await generateSummaryWithUsage(messagesToSummarize, ...); // 轮次之前的全部历史
		historyText = historyResult.value.text;
	}
	const turnPrefixResult = await generateTurnPrefixSummary(turnPrefixMessages, ...); // 本轮被切掉的前半部分
	summary = `${historyText}\n\n---\n\n**Turn Context (split turn):**\n\n${turnPrefixResult.value.text}`;
}
```

`generateTurnPrefixSummary` 用一个专门的、更简短的提示词（`TURN_PREFIX_SUMMARIZATION_PROMPT`）,只要求总结"这一轮最初的请求是什么、前半段做了哪些早期工作、后半段(被保留部分)需要哪些上下文才能看懂"——因为这段摘要要拼接在"完整历史摘要"之后、"被保留的轮次后半段"之前,承担的是承上启下的角色,不需要重复历史摘要已经覆盖的内容。

### 摘要生成:结构化格式与增量更新

压缩摘要不是自由格式的文本总结,而是要求模型按固定结构输出（`SUMMARIZATION_PROMPT`）：

```text
## Goal
## Constraints & Preferences
## Progress
### Done
### In Progress
### Blocked
## Key Decisions
## Next Steps
## Critical Context
```

这种结构化格式的价值在于：它把"总结"这个开放式任务约束成了一份**可预测、可被下一次总结增量更新**的检查点文档。第二次及以后的压缩会用 `UPDATE_SUMMARIZATION_PROMPT`,把上一次的摘要作为 `<previous-summary>` 传入,要求模型"保留所有旧信息,把新进展并入对应章节,把已完成的条目从 `In Progress` 挪到 `Done`"——这样多次压缩之后,摘要不会无限膨胀,也不会因为反复"总结的总结"而信息失真,而是始终维持一份结构固定、随对话推进滚动更新的"项目检查点"。

在真正调用模型之前,原始消息要先经过序列化（`serializeConversation`,定义在 `packages/coding-agent/src/core/compaction/utils.ts`）变成一段纯文本：

```text
[User]: 用户说了什么
[Assistant thinking]: 内部推理
[Assistant]: 回复文本
[Assistant tool calls]: read(path="foo.ts"); edit(path="bar.ts", ...)
[Tool result]: 工具输出(超过 2000 字符会被截断)
```

这样处理有两个目的：一是防止模型把"待总结的历史"误认成"需要继续的对话"而直接续写下去（`SUMMARIZATION_SYSTEM_PROMPT` 也明确写了"Do NOT continue the conversation"）;二是把工具结果截断到 2000 字符,因为 `read`/`bash` 之类工具的输出往往是历史中体积最大的部分,不加控制会让摘要请求本身也超预算。

### 文件操作的累积追踪

压缩和分支摘要都会额外提取"这段历史里读过哪些文件、改过哪些文件",并且是**跨多次压缩累积**的：

```typescript
// packages/coding-agent/src/core/compaction/compaction.ts
function extractFileOperations(messages: AgentMessage[], entries: Entry[], prevCompactionIndex: number): FileOperations {
	const fileOps = createFileOps();
	if (prevCompactionIndex >= 0) {
		const prevCompaction = entries[prevCompactionIndex] as CompactionEntry;
		if (prevCompaction.details) {
			const details = prevCompaction.details as CompactionDetails;
			for (const f of details.readFiles ?? []) fileOps.read.add(f);
			for (const f of details.modifiedFiles ?? []) fileOps.edited.add(f);
		}
	}
	for (const msg of messages) extractFileOpsFromMessage(msg, fileOps);
	return fileOps;
}
```

新一次压缩会把**上一次压缩记录里已经积累的文件集合**作为起点,再叠加这一批新消息里出现的文件操作,最终结果既写进摘要正文（`<read-files>`/`<modified-files>` 标签,`formatFileOperations`）,也写进 `CompactionEntry.details`供下一次压缩继续累加。这保证了即使经过很多轮压缩,"这个项目里到底碰过哪些文件"这个信息永远不会丢失——即使某次压缩的摘要文字里因为篇幅限制没提到某个文件,`details.readFiles`/`details.modifiedFiles` 依然完整保留着。

### 分支摘要:与压缩共用的基础设施

分支摘要（`packages/coding-agent/src/core/compaction/branch-summarization.ts`）解决的是不同场景,但复用了压缩的摘要格式、文件追踪、消息序列化三套设施。触发时机是 `/tree` 导航：

```typescript
export function collectEntriesForBranchSummary(
	session: ReadonlySessionManager, oldLeafId: string | null, targetId: string,
): CollectEntriesResult {
	if (!oldLeafId) return { entries: [], commonAncestorId: null };
	const oldPath = new Set(session.getBranch(oldLeafId).map((e) => e.id));
	const targetPath = session.getBranch(targetId);
	// 找 oldPath 和从根到 targetId 路径的最深公共节点,再收集 oldLeafId 到该节点之间被放弃的条目
	...
}
```

`compaction.md` 给出的示意图：

```text
Tree before navigation:
         ┌─ B ─ C ─ D (old leaf, being abandoned)
    A ───┤
         └─ E ─ F (target)
Common ancestor: A
Entries to summarize: B, C, D

After navigation with summary:
         ┌─ B ─ C ─ D
    A ───┤
         └─ E ─ F ─ [summary of B,C,D] (new leaf)
```

分支摘要与压缩的一个关键区别是：压缩是"删除历史、用摘要顶替",而分支摘要是"保留完整的旧分支不动,在新分支上追加一条包含摘要的新节点"——这与第四篇讲的"`branch()` 只挪指针、从不删除任何条目"的设计完全一致,被放弃的分支`B-C-D`依然完整存在于文件里,可以随时用 `session.branch(D.id)` 切回去,分支摘要只是让**新分支**在不重新翻阅旧分支全部细节的前提下,也能知道"那条被放弃的路上发生了什么"。

## 关键代码解读

### 扩展如何接管压缩流程

`session_before_compact` 事件让扩展可以完全接管或取消一次压缩（`packages/coding-agent/docs/compaction.md`)：

```typescript
pi.on("session_before_compact", async (event, ctx) => {
	const { preparation, branchEntries, customInstructions, reason, willRetry, signal } = event;
	// preparation.messagesToSummarize / turnPrefixMessages / previousSummary / fileOps / tokensBefore / firstKeptEntryId

	// 取消这次压缩:
	return { cancel: true };

	// 或者提供自定义摘要(比如用另一个更便宜的模型来做总结):
	return {
		compaction: {
			summary: "Your summary...",
			firstKeptEntryId: preparation.firstKeptEntryId,
			tokensBefore: preparation.tokensBefore,
			details: { /* custom data */ },
		},
	};
});
```

要拿到"待总结内容的纯文本形式"给自己的模型调用使用,可以直接复用 pi 内部同一套序列化逻辑：

```typescript
import { convertToLlm, serializeConversation } from "@earendil-works/pi-coding-agent";

pi.on("session_before_compact", async (event) => {
	const conversationText = serializeConversation(convertToLlm(event.preparation.messagesToSummarize));
	const { summary, usage } = await myModel.summarize(conversationText);
	return { compaction: { summary, firstKeptEntryId: event.preparation.firstKeptEntryId, tokensBefore: event.preparation.tokensBefore, usage } };
});
```

`session_before_tree` 是分支摘要的对应事件,结构类似,同样可以 `{ cancel: true }` 或者提供自定义 `summary`。这两个事件是第六篇要系统讲的扩展点体系里,与本篇内容直接呼应的两个具体案例。

### `CompactionEntry` 与 `retainedTail`

`compaction.md` 文档提到较新版本的压缩条目会直接在 `CompactionEntry` 上携带 `retainedTail`（保留下来的原始消息本体),而不是仅仅依赖 `firstKeptEntryId` 指针：

```json
{"type":"compaction","id":"f6g7h8i9","parentId":"e5f6g7h8","summary":"...","tokensBefore":50000,
 "retainedTail":[{"role":"user","content":"latest request"},{"role":"assistant","content":[...],"stopReason":"stop"}]}
```

这让压缩条目本身成为一个"自包含的检查点"——重建这一点之后的上下文不再需要回头遍历压缩之前的旧条目,`firstKeptEntryId` 只是为了兼容早期版本保留下来的字段。`CompactResult` 类型（`packages/agent/src/harness/compaction/compaction.ts`,即 `packages/agent` 里更新的 harness 抽象层对同一套压缩逻辑的重新实现）里明确把 `retainedTail: AgentMessage[]` 列为核心字段之一,印证了这是压缩机制演进的方向：从"指针 + 重新遍历"逐步走向"自包含检查点"。

## 小结与思考题

压缩与分支摘要共享同一套底层设施（结构化摘要格式、消息序列化、文件操作累积追踪),分别应对两种不同的"历史过载"场景：压缩是纵向的("这条时间线太长了,折叠掉旧的部分"),分支摘要是横向的("那条路不走了,但精华要带过来")。压缩的裁剪点选取要在"尽量少总结、尽量多保留"和"永远不能切断工具调用与其结果"之间找平衡,分裂轮次是这个约束下的必然产物,需要两段式摘要来处理。

思考题：

1. 如果 `keepRecentTokens` 设置得非常小（比如 1000）,`findCutPoint` 找到的切点大概率会落在最近几轮对话中间,导致频繁触发"分裂轮次"。这对摘要质量和调用成本分别有什么影响？
2. `extractFileOperations` 在跨多次压缩累积文件列表时,如果某个文件先被读取、后被删除（比如被 `bash rm` 掉了）,现有机制能感知到这个文件已经不存在了吗？如果不能,你会如何改进文件追踪逻辑？
3. 分支摘要保留了被放弃分支的完整原始数据（未被删除,只是不在当前上下文路径里),而压缩理论上也可以做成"不删除旧条目,只是新增一条压缩条目并让上下文路径跳过它们"——事实上 `buildContextEntries` 正是这么做的。既然两者的落盘方式如此相似,为什么用户体感上"压缩"和"分支摘要"是两个完全不同的操作？
