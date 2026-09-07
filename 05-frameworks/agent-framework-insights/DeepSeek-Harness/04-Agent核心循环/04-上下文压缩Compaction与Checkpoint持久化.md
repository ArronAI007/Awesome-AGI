# 上下文压缩 Compaction 与 Checkpoint 持久化

> 一次长会话迟早会撑爆模型的上下文窗口——`dsh` 对这个问题的处理分成"主动"和"被动"两条腿：`agent/pre-step` 钩子在每一步开始前检测 token 压力,提前把旧历史折叠成摘要；`agent/request-error` 钩子在模型真的报出"上下文超限"之后做一次带重试的溢出恢复。两条腿共享同一套"剪枝 → 选区 → 摘要 → 替换"的事务流程,而且都建立在同一个前提之上——`session-checkpoint-policy` 保证了"发模型请求前""执行工具前"这两个会产生真实副作用的时刻,会话日志一定已经落盘。本篇把这两套机制拆开看：压缩为什么要分两个触发点、每一步具体做了什么、以及"发请求/执行工具前必须先 flush"这件事为什么是 fail-closed 而不是普通的定时 autosave。

## 学习目标

- 理解压缩的两个触发点——`agent/pre-step` 的主动压力检测和 `agent/request-error` 的被动溢出恢复——分别在什么条件下被激活,以及为什么被动路径要绕过正常的阈值和保留尾部策略。
- 通读 `BasicCompactionEngine.compactIfNeeded()`,理解"剪枝（prune）→ 选区（selectCompactableRange）→ 摘要（summarizeWithLlm）→ 替换（compactSurfaceRegion）"四个阶段各自的职责,以及为什么要先剪枝再选区。
- 理解 `compactSurfaceRegion` 如何用 `compaction/start`/`compaction/end` 这一对标记事件把整个压缩过程做成一个可检测、可从崩溃中恢复的事务。
- 理解 `session-checkpoint-policy` 在哪三个副作用边界（模型请求、工具执行、下一次 pre-step）上强制 `flush`,以及为什么这是 fail-closed（校验失败就不发起副作用）而不是"先做后补记"。
- 理解 `SessionWriteBehind` 的写批量策略（默认 200ms 窗口）如何在"不阻塞热路径"和"checkpoint 必须可靠"这两个目标之间做取舍。

## 背景与设计动机

上下文压缩要解决的问题很直观：会话历史越长,占用的 token 越多,总有一刻会撑爆模型的上下文窗口甚至让每次请求都变贵变慢。但把"什么时候压缩、压缩什么、压缩失败怎么办"这几个问题认真想一遍,会发现朴素的"到了阈值就自动摘要"策略有明显漏洞：

- **阈值判断本身可能就是错的**：如果 token 计数方式和 provider 的真实计费/限制口径不一致,可能出现"本地觉得还没到阈值,但 provider 已经拒绝了这次请求"的情况——这种情况不能只靠事先的阈值预测来兜底,必须有一条"收到 provider 明确报错之后立刻补救"的恢复路径。
- **压缩本身是一次异步、可能失败的操作**：摘要请求要发给模型,发请求就可能超时、可能被取消、可能中途会话又发生了变化（比如摘要还没写完,同一段历史又被别的什么操作动过）。如果压缩过程中途崩溃,日志里必须能明确判断"这次压缩到底有没有成功",不能留下模糊状态。
- **副作用（发模型请求、执行工具）一旦发生就不可逆**：如果会话记录还没有落盘就已经把请求发给了模型,一旦这时候进程崩溃,重启后的会话历史就会和"模型实际看到过什么"产生分歧——这类分歧一旦发生,是无法事后修复的。

`dsh` 用两个独立但复用同一套底层机制的钩子应对第一个问题;用"compaction/start … compaction/end 标记对 + 每一步失败都补记一次收尾"应对第二个问题;用一套三处强制 flush 的 checkpoint 策略应对第三个问题。三者共同的底线都是同一句话:**宁可拒绝执行一次副作用,也不能让日志和真实发生的事情脱节**。

## 核心机制详解

### 触发点一：agent/pre-step 的主动压力检测

`packages/compaction/compaction-basic/src/index.ts` 的 `BasicCompactionEngine` 在构造时,如果 `config.auto` 为真,会挂上两个监听器。第一个挂在 `agent/pre-step`——也就是第一篇讲过的、`preStep()` 里那个决定"这一步该不该进入模型调用"的 waterfall 钩子:

```typescript
// packages/compaction/compaction-basic/src/index.ts
ctx.on('agent/pre-step', async ({ agent, signal }, next): Promise<PreStepDecision> => {
  if (!signal.aborted) {
    try {
      const result = await this.compactIfNeeded(agent, 'pressure', signal)
      if (result !== null) logResult(result, 'step pressure')
    } catch (error: unknown) {
      if (error instanceof TargetPressureConfigError) {
        if (this.warnedPressureConfigTargets.has(error.targetKey)) return next()
        this.warnedPressureConfigTargets.add(error.targetKey)
      }
      const message = error instanceof Error ? error.message : String(error)
      ctx.logger.warn(`step compaction failed: ${message}; continuing the turn`)
    }
  }
  return next()
})
```

这里有一个刻意的容错策略：无论 `compactIfNeeded` 是成功、失败还是配置缺失,最后都会 `return next()` 放行这一步继续走下去——**压缩失败不应该阻塞正常对话**。唯一的特殊处理是 `TargetPressureConfigError`（比如某个 provider/model 组合没有配置 `contextWindow`,导致压力判断根本算不出来）只会打印一次告警而不是每一步都刷屏。

`compactIfNeeded()` 在 `'pressure'` 这个触发场景下的完整判断逻辑：

```typescript
// packages/compaction/compaction-basic/src/index.ts（节选，pressure 分支）
const context = (await this.ctx.llm.resolveModelInfo(target.provider, target.model, signal)).context
const spec = resolveCompactSpec(policy, context.contextWindow)
if (measurement.totalTokens < spec.thresholdTokens) return null

if (prune !== undefined) {
  prune.pruneSession(agent.session)
  measurement = meter.measure(agent.session)
}
if (measurement.totalTokens < spec.thresholdTokens) return null

let result: CompactionResult | null = null
for (let attempt = 0; attempt <= spec.compactionRetries; attempt += 1) {
  const range = selectCompactableRange(agent.session, measurement, spec.retainTokens)
  if (range === null) {
    if (result === null) return null
    break
  }
  result = await this.compactRegion(range.start, range.end, agent, signal)
  measurement = meter.measure(agent.session)
  if (measurement.totalTokens < spec.thresholdTokens) return result
}
```

流程是：先按当前路由的模型 `contextWindow` 算出一个阈值（`resolveCompactSpec`),如果当前估算的 token 数还没到阈值,直接返回 `null`（什么都不做)。到了阈值之后,先尝试一次**不需要调用模型的剪枝**（`prune.pruneSession`,由可选的 `toolResultPruner` 服务提供,专门清理旧的工具结果,详见下一节),剪枝完重新测量一次,如果这样就已经降到阈值以下,压缩到此为止,连摘要请求都不用发。只有剪枝仍然不够,才真的进入"选区 → 摘要 → 替换"的循环,而且这个循环有 `compactionRetries` 次重试上限——因为一次摘要可能因为原文太长导致摘要本身也超出预期,这时会再选一段范围重新压缩,直到测量结果降到阈值以下或者重试次数耗尽。

### 触发点二：agent/request-error 的被动溢出恢复

第二个监听器挂在 `agent/request-error`——第一篇 `step()` 里"模型请求失败后决定要不要重试"的那个 waterfall 钩子（下一篇会讲重试插件 `llm-retry` 也挂在同一个钩子上,两者互不冲突,谁先注册谁先跑）：

```typescript
// packages/compaction/compaction-basic/src/index.ts
ctx.on('agent/request-error', async ({ agent, failure, signal }, next) => {
  if (failure.code !== CONTEXT_WINDOW_EXCEEDED_CODE || signal.aborted) return next()
  this.overflowAgents.set(agent.session, agent)
  const target = routedTarget(agent.session)
  if (target === undefined) return next()
  const policy = resolveTargetPolicy(this.config, target)
  const retries = this.overflowRetries.get(agent) ?? 0
  if (retries >= policy.maxOverflowRetries) return next()

  const generation = agent.session.surface.replaceGeneration
  let result: CompactionResult | null
  try {
    result = await this.compactIfNeeded(agent, 'context-overflow', signal)
  } catch (recoveryError: unknown) {
    if (!signal.aborted && agent.session.surface.replaceGeneration > generation) {
      this.overflowRetries.set(agent, retries + 1)
      return { kind: 'retry' }
    }
    return next()
  }
  if (signal.aborted || agent.session.surface.replaceGeneration <= generation) return next()
  this.overflowRetries.set(agent, retries + 1)
  return { kind: 'retry' }
})
```

只有当 `failure.code === CONTEXT_WINDOW_EXCEEDED_CODE`（第三篇讲过的,provider 明确报出"上下文超限"这一稳定错误码）才会介入,否则直接 `next()` 交给别的监听器（比如普通的网络重试）处理。判断"这次恢复算不算成功"用的是 `agent.session.surface.replaceGeneration`——第二篇讲过,这个计数器只有在真的发生过 `replace` 写入时才会增加——如果压缩过程本身抛了异常,但 `replaceGeneration` 已经比开始前大了,说明"至少有一次模型免费的剪枝已经落地生效",这个部分成果足够支撑一次重试（"a model-free prune can land before later summary work fails. That durable reduction is sufficient retry proof"),不需要因为后续摘要阶段失败就把已经生效的剪枝也一并放弃。返回 `{ kind: 'retry' }` 会让 `step()` 里那个 `while (true)` 循环重新走一遍 `buildRequest()`——用刚刚压缩过的、更短的历史重新发一次请求。

`compactIfNeeded()` 在 `'context-overflow'` 这个触发场景下的逻辑明显更激进,直接跳过阈值判断：

```typescript
// packages/compaction/compaction-basic/src/index.ts（节选，context-overflow 分支）
if (trigger === 'context-overflow') {
  if (prune !== undefined) {
    prune.pruneSession(agent.session)
    measurement = meter.measure(agent.session)
  }
  const range = selectCompactableRange(agent.session, measurement, 0)
  if (range === null) return null
  return this.compactRegion(range.start, range.end, agent, signal)
}
```

`selectCompactableRange` 的第三个参数 `retainTokens` 直接传 `0`——意味着"不刻意为最近若干 token 的对话留后手,能压多少就压多少"。因为这时候已经是"provider 已经明确拒绝了这次请求"的紧急状态,目标是尽快把请求压到能被接受的大小,而不是像主动压力检测那样细水长流地保留最近的对话尾部。

### 压缩四阶段：剪枝 → 选区 → 摘要 → 替换

**剪枝（prune）**由独立的 `packages/compaction/compaction-tool-result-pruner` 包提供,通过 `this.ctx.get('toolResultPruner')` 可选地接入——它的职责严格限定为"只删旧的工具结果,不动对话本体",因为工具结果（比如一次 `bash` 输出的完整日志)往往是历史里最占 token、又最不需要被模型反复重新阅读的部分。

**选区（selectCompactableRange）**是一个纯函数,负责决定"到底压缩哪一段":

```typescript
// packages/compaction/compaction-basic/src/region.ts
export function selectCompactableRange(
  session: Session, measurement: TokenMeasurement, retainTokens: number,
): { start: number; end: number } | null {
  const pricedNodes = measurement.nodes
  const surfaceNodes = session.surface.nodes
  let accumulated = 0
  let keepFromIdx = pricedNodes.length
  for (let index = pricedNodes.length - 1; index >= 0; index -= 1) {
    accumulated += pricedNodes[index]!.tokens
    keepFromIdx = index
    if (accumulated >= retainTokens) break
  }
  if (keepFromIdx === 0) return null
  while (keepFromIdx > 0) {
    if (toolPairingBalancedBefore(session, surfaceNodes[keepFromIdx]!)) break
    keepFromIdx -= 1
  }
  if (keepFromIdx === 0) return null
  const first = surfaceNodes[0]!
  const cutoff = surfaceNodes[keepFromIdx - 1]!
  return { start: first, end: cutoff }
}
```

策略是"从尾部往前累计,凑够 `retainTokens` 就停",定下一个初步的切分点后,再往前微调到最近一个"不会切断一次工具调用/结果配对"的边界（`toolPairingBalancedBefore`）——**绝不能让压缩把一次 `tool/call` 和它对应的 `tool/result` 从中间切开**,否则派生出的历史会出现一次没有结果的裸调用,模型看到会困惑,更严重的是会破坏 provider 侧对"assistant 消息紧跟工具结果"这类格式的强约束。

**摘要（summarizeWithLlm）**是唯一需要调用模型的一步。`buildSummarizationInput()`（`region.ts`)专门负责复用会话自己的 `system` 和 `tools`：

```typescript
// packages/compaction/compaction-basic/src/region.ts
function buildSummarizationInput(session: Session, shadowedSeqs: readonly number[]): SummarizationInput {
  const header = session.requestHeader()
  return {
    ...header?.system === undefined ? {} : { system: header.system },
    ...header?.tools === undefined ? {} : { tools: header.tools },
    messages: shadowedSeqs.map(seq => session.deriveEventMessage(events[seq]!)).filter(/* not null */),
  }
}
```

复用同一份 `system`/`tools` 前缀不是随意的选择——它让摘要请求在 provider 侧看起来是"同一个对话的自然延续",能够复用 provider 端的 KV 缓存（prompt caching）,而不是每次摘要都要重新处理一遍完整的系统提示词。摘要生成后还有一道安全检查：

```typescript
// packages/compaction/compaction-basic/src/region.ts
const framedSummaryTokenCount = dependencies.meter.estimateMessage(checkpointMessage)
if (framedSummaryTokenCount >= prepared.shadowedTokenCount) {
  throw new Error(`summary is not smaller than the shadowed content (...)`)
}
```

如果生成的摘要本身比被压缩的原文还长（模型偶尔会这样),整个压缩事务直接判定失败——压缩存在的意义就是"变小",一个不变小的压缩没有任何价值,不应该被接受。

**替换（commitCompactionBody）**把摘要结果落回日志,用的正是第二篇讲过的 `{ op: 'replace' }` Surface 写入原语：

```typescript
// packages/compaction/compaction-basic/src/region.ts
const summaryEvent = session.append('compaction/summary', { /* ... */ })
session.append('user/message', checkpointMessage, {
  surfaceOp: { op: 'replace', start, end },
  sourceEventSeqs: [startEvent.seq, summaryEvent.seq, ...shadowedSeqs],
})
```

### compaction/start … compaction/end：把压缩做成可检测的事务

四个阶段被 `compactSurfaceRegion()` 整体包在一对标记事件之间：

```typescript
// packages/compaction/compaction-basic/src/region.ts（节选）
const startEvent = session.append('compaction/start', lifecycle)
try {
  const prepared = prepareCompaction(dependencies, session, selection)
  const summarized = await summarizeCompaction(dependencies, prepared, agent, compactionId, sourceCommandId, signal)
  assertStable(dependencies, session, summarized)
  const pending = commitCompactionBody(session, startEvent, summarized)
  const endEvent = session.append('compaction/end', lifecycle)
  result = completeCompaction(pending, endEvent)
} catch (error: unknown) {
  failure = { error, stage: closing ? 'commit' : stage }
  if (!closing) {
    try {
      session.append('compaction/end', { ...lifecycle, error: errorChain(error) })
      closed = true
    } catch (closeError: unknown) {
      failure = { error: closeError, stage: 'commit' }
    }
  }
}
```

无论摘要阶段成功还是失败,`compaction/end` 几乎总会被写下（成功时携带正常结果,失败时携带 `error` 字段）——这保证了日志上"一个 `compaction/start` 后面一定跟着一个 `compaction/end`",一旦扫描日志发现有 `compaction/start` 没有匹配的 `compaction/end`,就能明确判定"这是一次真正被进程崩溃打断的压缩",而不是"逻辑上失败但优雅收尾的压缩"。`assertStable()` 还会在摘要生成完成后重新核对一遍"这段要被替换的历史,在异步等待摘要期间有没有被别的操作改动过"（`assertWholeSurfaceUnchanged`/`assertSelectedSpanStable` 两种稳定性校验,取决于是自动压缩还是手动 `compactNow()`）——一旦发现变了,直接拒绝这次替换,而不是盲目地把摘要塞进一个可能已经不对应的位置。

### session-checkpoint-policy：三处 fail-closed 的强制 flush

压缩本身依赖一个更底层的保证:任何"会产生真实副作用"的操作,发生之前会话状态必须已经落盘。这套语义由 `packages/session/session-checkpoint-policy/src/index.ts` 完整实现,一共挂了三个监听器:

```typescript
// packages/session/session-checkpoint-policy/src/index.ts
export function apply(ctx: Context): void {
  ctx.on('llm/stream', (options, next): AsyncIterable<StreamChunk> => {
    if (options.sessionId === undefined) return next()
    const session = ctx.sessions.get(options.sessionId)
    return session === undefined ? next() : afterCheckpoint(ctx, session, next)
  })

  ctx.on('tools/execute', async (exec, next): Promise<ToolExecutionResult> => {
    if (exec.agent === undefined || exec.parent !== undefined) return next()
    await ctx.sessions.flush(exec.agent.session)
    if (exec.signal.aborted) return abortedBeforeDispatchResult()
    return next()
  })

  ctx.on('agent/pre-step', async ({ agent }, next): Promise<PreStepDecision> => {
    await ctx.sessions.flush(agent.session)
    return next()
  })
}
```

三处分别对应第三篇讲过的 `'llm/stream'` waterfall（发起模型请求之前)、顶层工具执行的 `'tools/execute'` 钩子（真正跑工具体之前,注意 `exec.parent !== undefined` 时会跳过——嵌套的子调用复用外层已经落盘的调用记录,不需要重复 flush)、以及第一篇讲过的 `'agent/pre-step'`（在组装下一步请求之前,先把上一步已经提交的内容落盘)。三处的共同结构都是**先 `await flush`,flush 失败就直接向上抛异常,`next()` 根本不会被调用**——这就是"fail-closed"的具体含义:checkpoint 校验失败,下游的模型调用或者工具执行**根本不会发生**,而不是"先执行,再想办法补记一条日志"。这个顺序不能颠倒:一旦真的先发了请求、执行了工具,产生的副作用就是不可逆的,事后补记的日志已经无法改变这个事实。

值得留意的是,这套策略并没有让"每一步都要等一次磁盘 I/O",因为它调用的是同一个 `flush()`,而这个 flush 具体做了什么、代价有多大,取决于下一节的写批量策略——**语义上的"必须落盘"和实现上的"批量写入优化"是两个独立的层次**。

### SessionWriteBehind：批量写入而不是逐事件同步落盘

`ctx.sessions.flush()` 最终落到 `PersistenceCoordinator`（`packages/session/session-persistence/src/coordinator.ts`)持有的每会话 `SessionWriteBehind` 实例上。日常追加事件走的是"攒一批再写"的路径:

```typescript
// packages/session/session-persistence/src/write-behind.ts
enqueue(event: SessionEvent): void {
  const wasEmpty = this.pending.length === 0
  this.pending.push(structuredClone(event))
  if (this.barrier !== undefined) return
  if (this.automaticPaused) { this.automaticPaused = false; this.deadlineExpired = false; this.armTimer() }
  else if (wasEmpty) { this.armTimer() }
}

private armTimer(): void {
  this.timer = setTimeout(() => { this.onDeadline() }, this.options.maxDelayMs)
}
```

```typescript
// packages/session/session-persistence/src/coordinator.ts
export const DEFAULT_WRITE_BATCH_MAX_DELAY_MS = 200
```

默认的批量窗口是 200 毫秒——`enqueue()` 只在队列从空变非空、或者上一批写入失败恢复后重新排队时才会启动一个新的定时器,窗口内到达的所有事件会被合并成一次真正的持久化写入。`flush()` 则是明确要求"现在立刻结清,不要等定时器":

```typescript
// packages/session/session-persistence/src/write-behind.ts
flush(): Promise<void> {
  if (this.barrier !== undefined) return this.barrier
  this.cancelTimer()
  const barrier = Promise.withResolvers<void>()
  this.barrier = barrier.promise
  void this.drainBarrier(barrier.resolve, barrier.reject)
  return barrier.promise
}

private async drainBarrier(resolve, reject): Promise<void> {
  try {
    const overlapping = this.active
    if (overlapping !== undefined) await Promise.allSettled([overlapping])
    while (this.pending.length > 0) await this.startWrite(false)
  } catch (error: unknown) {
    this.barrier = undefined
    reject(error)
    return
  }
  this.barrier = undefined
  resolve()
}
```

`flush()` 取消掉还没触发的定时器,等正在进行中的写入完成,然后**同步地、不经过延迟窗口**把剩下所有排队事件写完——这正是 `session-checkpoint-policy` 三处调用所依赖的行为:调用 `flush()` 之后拿到的 `Promise` resolve,意味着此刻为止追加的所有事件都已经真正落盘,才安全地继续往下走。这套设计让"绝大多数普通事件追加"走一条便宜的、批量摊销的路径,只有真正需要durability 保证的那几个关键时刻才付出"立刻写入"的代价——**语义上的可靠性从不打折,但性能代价被精确限制在必须付出的地方**。

## 常见问题/易踩坑

- **主动压缩失败不会中断对话,被动溢出恢复失败会**：`agent/pre-step` 上的压力检测把任何异常都 `catch` 掉、打个警告后继续放行；`agent/request-error` 上的溢出恢复如果确实没有任何进展（`replaceGeneration` 没变化),会 `return next()` 把原始的"上下文超限"错误原样交给外层处理——不会无休止地重试一个注定失败的恢复。
- **`selectCompactableRange` 绝不会切断一次工具调用/结果配对**——如果你的自定义压缩策略需要选择别的切分范围,一定要复用 `toolPairingBalancedBefore`/`toolPairingBalancedAfter` 这类校验,而不是自己按 token 数硬切。
- **`ctx.sessions.flush()` 的调用方永远应该假设它可能失败并向上传播**——三处 checkpoint 监听器都没有 `catch` 这个调用,这是有意为之：flush 失败就应该让整个请求/工具执行失败,而不是吞掉错误继续往下走。
