# 会话 Session 与持久化

> pi 的会话文件不是一份"聊天记录导出",而是一棵用 JSONL 追加写入实现的树——每条记录都带 `id`/`parentId`,天然支持分支、回溯、压缩,而不需要任何数据库。本篇结合 `session-manager.ts` 源码和 `session-format.md` 文档,讲清楚这套持久化模型的数据结构、树形导航算法,以及"为什么是 JSONL 而不是一个大 JSON 文件"这个看似简单却影响深远的工程决策。

## 学习目标

- 理解会话文件的物理格式：JSONL、每行一个带 `type` 字段的条目、首行是 `SessionHeader`。
- 掌握树形会话模型的核心字段 `id`/`parentId`/`leafId`,以及"当前分支"是如何通过从叶子回溯到根解析出来的。
- 理解 `buildContextEntries`/`buildSessionContext` 两个函数如何把树上的一条路径,结合压缩信息,还原成真正发给 LLM 的消息列表。
- 搞清楚 `SessionManager` 的追加写策略（`_persist`）为什么要"等到第一条 assistant 消息出现才落盘”。
- 能回答"为什么用 JSONL 而不是单一 JSON 文件"这个设计问题,并给出至少三条工程依据。

## 背景与设计动机

一个编码助手的会话通常会经历：连续问答、中途用 `/tree` 回退重新尝试一种方案、上下文太长触发压缩、用 `/fork` 复制出一个新会话继续探索……如果用一个线性数组存储整个会话,"回退重试"这种操作要么破坏历史（覆盖掉被放弃的分支）,要么需要复杂的差异存储。pi 的解法是:**不用数组表示会话,而是用一棵树**——每一条会话事件（不仅是消息,还包括模型切换、压缩、分支摘要等）都是树上的一个节点,有唯一 `id` 和指向父节点的 `parentId`。"回退重试"变成了简单地把一个内存指针（`leafId`）挪到树上更早的一个节点,后续新写入的内容自然成为一条新分支,原来的分支完整保留、随时可以再切回去。

## 核心机制详解

### 物理格式:JSONL + 树形字段

会话文件存放在 `~/.pi/agent/sessions/--<编码后的cwd>--/<timestamp>_<uuid>.jsonl`,每一行是一个 JSON 对象。首行永远是没有 `id`/`parentId` 的 `SessionHeader`：

```typescript
// packages/coding-agent/src/core/session-manager.ts
export interface SessionHeader {
	type: "session";
	version?: number; // v1 会话没有这个字段
	id: string;
	timestamp: string;
	cwd: string;
	parentSession?: string; // 通过 /fork、/clone 创建的会话,记录源会话路径
}
```

其余每一行都实现 `SessionEntryBase`：

```typescript
export interface SessionEntryBase {
	type: string;
	id: string;
	parentId: string | null;
	timestamp: string;
}
```

具体的条目类型有九种（`SessionEntry` 联合类型）：`SessionMessageEntry`（真正的对话消息）、`ThinkingLevelChangeEntry`、`ModelChangeEntry`、`CompactionEntry`、`BranchSummaryEntry`、`CustomEntry`（扩展状态,不进入 LLM 上下文）、`CustomMessageEntry`（扩展注入的消息,会进入 LLM 上下文）、`LabelEntry`（用户书签）、`SessionInfoEntry`（会话显示名）。一份真实会话文件的片段大致是：

```json
{"type":"session","version":3,"id":"019...","timestamp":"2024-12-03T14:00:00.000Z","cwd":"/path/to/project"}
{"type":"message","id":"a1b2c3d4","parentId":null,"timestamp":"...","message":{"role":"user","content":"Hello"}}
{"type":"message","id":"b2c3d4e5","parentId":"a1b2c3d4","timestamp":"...","message":{"role":"assistant","content":[...],"stopReason":"stop"}}
{"type":"message","id":"c3d4e5f6","parentId":"b2c3d4e5","timestamp":"...","message":{"role":"toolResult","toolCallId":"call_123",...}}
```

每一行独立可解析,行与行之间除了 `parentId` 的引用关系外没有别的耦合——这正是选用 JSONL 而不是一个大 JSON 数组的第一个原因,下文详细展开。

### 树形导航:`leafId` 与路径回溯

`SessionManager` 只维护一个游标——`leafId`,代表"当前所在的位置"。所有查询都是从某个节点出发、沿 `parentId` 一路走到根：

```typescript
// packages/coding-agent/src/core/session-manager.ts
getBranch(fromId?: string): SessionEntry[] {
	const path: SessionEntry[] = [];
	const startId = fromId ?? this.leafId;
	let current = startId ? this.byId.get(startId) : undefined;
	while (current) {
		path.push(current);
		current = current.parentId ? this.byId.get(current.parentId) : undefined;
	}
	path.reverse();
	return path;
}
```

"追加一条新消息"和"开启一个新分支"用的是同一套底层操作,区别只在于追加前 `leafId` 指向哪里：

```typescript
appendMessage(message: Message | CustomMessage | BashExecutionMessage): string {
	const entry: SessionMessageEntry = {
		type: "message", id: generateId(this.byId), parentId: this.leafId,
		timestamp: new Date().toISOString(), message,
	};
	this._appendEntry(entry); // 内部会把 this.leafId 更新为新条目的 id
	return entry.id;
}

branch(branchFromId: string): void {
	if (!this.byId.has(branchFromId)) throw new Error(`Entry ${branchFromId} not found`);
	this.leafId = branchFromId; // 只挪指针,不删除、不修改任何已有条目
}
```

`branch()` 之后再调用任何 `appendXxx()`,新条目的 `parentId` 就会指向被回退到的那个节点,而不是原来分支的末端——原分支的所有条目原封不动地留在文件里,`getTree()` 可以把它们作为兄弟子树展示出来：

```typescript
getTree(): SessionTreeNode[] {
	// 为每个 entry 建节点,再按 parentId 挂到父节点的 children 数组,
	// children 按 timestamp 升序排列(最新的分支排在最后)
	// 返回所有 parentId === null 的节点作为森林的根
}
```

`branchWithSummary()` 是 `branch()` 的加强版——在挪动指针的同时,顺带插入一条 `BranchSummaryEntry`,把被放弃分支的内容总结成一段文本注入新分支（第五篇详细展开这个机制)。

### 从树到上下文:`buildContextEntries` 与 `buildSessionContext`

树本身只回答"这条会话历史长什么样",真正决定"这一刻要发给模型看什么"的是两个纯函数：

```typescript
// packages/coding-agent/src/core/session-manager.ts
export function buildContextEntries(
	entries: SessionEntry[], leafId?: string | null, byId?: Map<string, SessionEntry>,
): SessionEntry[] {
	const path = buildSessionPath(entries, leafId, byId); // 从 leaf 回溯到根,得到线性路径
	let compaction: CompactionEntry | null = null;
	for (const entry of path) {
		if (entry.type === "compaction") compaction = entry; // 记录路径上最新的一次压缩
	}
	if (!compaction) return path; // 没压缩过,整条路径都算数

	const compactionIdx = path.findIndex((entry) => entry.id === compaction.id);
	const contextEntries: SessionEntry[] = [compaction];
	let foundFirstKept = false;
	for (let i = 0; i < compactionIdx; i++) {
		const entry = path[i];
		if (entry.id === compaction.firstKeptEntryId) foundFirstKept = true;
		if (foundFirstKept) contextEntries.push(entry); // 只保留压缩边界之后侥幸survive的条目
	}
	contextEntries.push(...path.slice(compactionIdx + 1)); // 压缩之后新产生的条目全部保留
	return contextEntries;
}

export function buildSessionContext(
	entries: SessionEntry[], leafId?: string | null, byId?: Map<string, SessionEntry>,
): SessionContext {
	const path = buildSessionPath(entries, leafId, byId);
	const { thinkingLevel, model } = getSessionContextSettings(path); // 沿路径找最新的模型/思考级别设置
	const messages = buildContextEntries(entries, leafId, byId).flatMap(sessionEntryToContextMessages);
	return { messages, thinkingLevel, model };
}
```

`buildContextEntries` 的逻辑可以理解成:**先拿到从根到当前叶子的完整路径,如果路径上有压缩记录,就把"压缩之前被丢弃的部分"剪掉,只保留压缩条目本身 + 压缩时被判定为"应该保留"的尾部条目 + 压缩之后新产生的一切**。`sessionEntryToContextMessages` 再把每种 `SessionEntry` 投影成零条或一条 `AgentMessage`：

```typescript
export function sessionEntryToContextMessages(entry: SessionEntry): AgentMessage[] {
	if (entry.type === "message") {
		const message = entry.message;
		if ((message.role === "user" || message.role === "assistant" || message.role === "toolResult") && message.content == null) {
			return [{ ...message, content: [] }]; // 兜底:老版本/手工编辑过的会话可能有 content 缺失
		}
		return [message];
	}
	if (entry.type === "custom_message") return [createCustomMessage(entry.customType, entry.content ?? [], entry.display, entry.details, entry.timestamp)];
	if (entry.type === "branch_summary" && entry.summary) return [createBranchSummaryMessage(entry.summary, entry.fromId, entry.timestamp)];
	if (entry.type === "compaction") return [createCompactionSummaryMessage(entry.summary, entry.tokensBefore, entry.timestamp)];
	return []; // model_change / thinking_level_change / custom / label / session_info 都不产生上下文消息
}
```

也就是说,`model_change`、`thinking_level_change`、`custom`（纯扩展状态）、`label`、`session_info` 这五种条目类型只是"会话树上的元数据标记",它们会影响 `getSessionContextSettings` 解析出的当前模型/思考级别,但**从不**变成一条送进 LLM 上下文的消息。这与第三篇讲的 `AgentMessage` 角色体系正好衔接：会话持久化层的"条目(Entry)"种类,比运行时的"消息(AgentMessage)"角色更丰富,前者是后者的超集加上纯元数据。

### 追加写策略:为什么要等第一条 assistant 消息

`_persist` 方法里有一段容易被忽略但很关键的逻辑：

```typescript
// packages/coding-agent/src/core/session-manager.ts
_persist(entry: SessionEntry): void {
	if (!this.persist || !this.sessionFile) return;
	const hasAssistant = this.fileEntries.some((e) => e.type === "message" && e.message.role === "assistant");
	if (!hasAssistant) {
		if (this.flushed) {
			appendFileSync(this.sessionFile, `${JSON.stringify(entry)}\n`);
		} else {
			this.flushed = false; // 还没见到第一条 assistant 消息,先不真正建文件
		}
		return;
	}
	if (!this.flushed) {
		// 第一条 assistant 消息刚出现:把此前积累的所有条目一次性写入(含 header)
		const fd = openSync(this.sessionFile, "wx");
		for (const e of this.fileEntries) writeFileSync(fd, `${JSON.stringify(e)}\n`);
		closeSync(fd);
		this.flushed = true;
	} else {
		appendFileSync(this.sessionFile, `${JSON.stringify(entry)}\n`);
	}
}
```

这解决的是一个真实的用户体验问题：**用户刚打开 pi、输入了第一条消息,但还没等模型回复就退出了**——如果这时候就已经在磁盘上创建了一个会话文件,会话列表里就会积累大量"只有一句用户话、从没跑起来"的空壳会话。`SessionManager` 的策略是把这个决定推迟到"确认这次对话真的产生了一次 assistant 回复"为止：在此之前,新条目只累积在内存的 `fileEntries` 数组里；一旦出现第一条 `assistant` 消息,才用 `wx`（排它性创建）模式把迄今为止的全部内容一次性刷到磁盘,之后转为逐行 `appendFileSync`。这是一个"义务先延后到确定值得持久化的那一刻"的设计模式,在 CLI 工具里很常见。

### `createBranchedSession`:把一条分支导出成独立文件

如果只想保留"从根到某个叶子"这一条路径、丢掉其余分支,`createBranchedSession(leafId)` 会构造一个全新的会话文件：先用 `getBranch(leafId)` 拿到路径,过滤掉 `LabelEntry`（并重新串联 `parentId`,避免断链导致后续依赖某个标签节点的条目变成孤儿）,再把落在这条路径上的用户标签重新以标签条目的形式追加进去。这是 `/fork`（保留全部历史另起一个会话）与"提取单一分支"操作背后的核心实现。

### 会话发现与列表:`findMostRecentSession` / `SessionManager.list`

`--resume`（继续最近会话）依赖 `findMostRecentSession`,它只读取每个候选文件的**头部**（`readSessionHeader`,带 `MAX_SESSION_HEADER_SCAN_BYTES` 上限的有界扫描,避免遇到超大或损坏文件时无限读取）来判断 `cwd` 是否匹配,而不需要把整份文件解析完——这对有大量历史会话的用户是重要的性能优化。列表展示（`SessionManager.list`/`listAll`）则用 `buildSessionInfosWithConcurrency` 做了并发上限为 10 的并发加载,避免同时打开成百上千个文件句柄。

## 关键代码解读

### 一次分支切换的完整数据流

```text
初始状态:
  A(user) → B(assistant) → C(user) → D(assistant)   ← leafId 指向 D

用户执行 /tree,选择回到 B 重新尝试:
  ctx.navigateTree(B.id, { summarize: true })
    → 生成 C,D 的摘要(branch summary,详见第五篇)
    → session.branchWithSummary(B.id, summary)
        leafId = B.id
        追加 BranchSummaryEntry{ parentId: B.id, fromId: 旧leafId(D), summary }
                                                     ↑ leafId 现在指向这条摘要条目

之后用户发新消息:
  appendMessage({ role: "user", ... })
    parentId = 当前 leafId(摘要条目的 id)
    leafId = 新条目 id

最终树形结构:
        A ─── B ─┬─ C ─── D                 (旧分支,完整保留)
                  └─ [branch_summary] ─── E(新的 user 消息) ← 当前 leafId
```

`buildSessionContext()` 从当前 `leafId`（`E`）出发回溯,只会走 `B → [branch_summary] → E` 这条路径,`C`、`D` 不会出现在发给模型的上下文里,但它们依然完整保存在文件中,随时可以用 `branch(D.id)` 切回去。

### 为什么是 JSONL 而不是一个大 JSON 文件

结合以上机制,可以总结出至少四条工程依据：

1. **天然支持追加写(append-only)**：JSONL 的每一行都是独立完整的 JSON,新增一条记录只需要 `appendFileSync` 一行,不需要读出整个文件、反序列化、修改、再整体序列化写回。而如果用单一 JSON（比如顶层是一个数组）,哪怕只追加一条消息,理论上也需要重写整个文件（或者用脆弱的字符串拼接技巧在结尾插入,风险和复杂度都更高）。这对于长会话（成千上万条消息）是数量级的性能差异。
2. **崩溃安全性更好**：进程在写入中途被杀掉时,JSONL 文件最坏情况是最后一行不完整,前面所有完整的行依然是合法可解析的历史——`loadEntriesFromFile` 和 `parseSessionEntryLine` 对无法解析的行采取"跳过而不是让整个加载失败"的策略。而单一 JSON 文件一旦在写入中途损坏,整个文件通常直接无法解析。
3. **可以流式读取,不需要一次性载入整个文件**：`buildSessionInfo` 用 Node 的 `readline` 逐行扫描文件提取摘要信息（首条用户消息、消息计数等）,不需要把整份会话（可能包含大量工具输出）载入内存;`readSessionHeader` 更是只读文件开头几 KB 就能拿到头部信息。这对"列出所有历史会话"这种要扫描大量文件的场景是必要的。
4. **树形结构通过字段而不是嵌套表达,天然扁平、天然适配行式存储**：因为分支关系是通过 `id`/`parentId` 表达而不是 JSON 的嵌套结构,所以"一棵树"和"一个数组的 JSONL"完全兼容——不需要为了表达分支去发明一种嵌套或图状的文件格式。

## 小结与思考题

会话持久化的核心心智模型是：**用 JSONL 存一棵以 `id`/`parentId` 连接的树,`leafId` 是当前位置的指针,`branch()`/`branchWithSummary()` 通过挪动指针实现零成本的历史保留式回退,`buildContextEntries`/`buildSessionContext` 负责把"从根到叶子的一条路径"结合压缩信息投影成真正发给 LLM 的消息列表**。落盘策略上,`SessionManager` 用"延迟到第一条 assistant 消息出现"的策略避免产生空壳会话文件。

思考题：

1. 如果要给 pi 增加"合并两个分支"的功能（把分支 B 的部分修改整合进主分支 A）,在现有的树形 + JSONL 模型下,你会怎么设计这个操作而不破坏 append-only 的特性？
2. `buildContextEntries` 在遇到压缩条目时,为什么要保留"从 `firstKeptEntryId` 到压缩条目之间"的原始条目,而不是完全依赖压缩摘要？这与第五篇要讲的"分裂轮次(split turn)"有什么关系？
3. `sessionEntryToContextMessages` 对 `custom` 类型条目返回空数组（不产生上下文消息）,但 `custom_message` 类型条目会产生一条 `user` 消息。如果你在写一个扩展,想往会话里存一份纯粹给自己用、绝不希望进入 LLM 上下文的状态,应该用 `appendCustomEntry` 还是 `appendCustomMessageEntry`？
