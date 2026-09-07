# Memory 架构总览:插件化、互斥槽位与"无隐藏状态"

> OpenClaw 的记忆系统first look 上去朴素得让人意外——没有向量数据库中间件,没有独立的 memory 微服务,模型能记住的一切都写在 `~/.openclaw/workspace` 下的几个 Markdown 文件里。但真正值得深挖的是它的分层方式:core 里的 `src/memory/` 只有三个文件、不到 300 行,定义的是"记忆槽位"这个契约和文件级 provenance 记录;真正干活的 SQLite 索引、FTS5/向量混合检索、后台整理管线,全部实现在一个叫 `memory-core` 的插件里,并且这个插件槽位是**互斥的**——同一时间只能有一个记忆插件生效。这篇先把这套分层架构和"记忆即插件槽位"的产品决策讲清楚,recall 侧的细节和人格/长期演化留给后两篇。

## 学习目标

- 理解 OpenClaw 记忆系统的"无隐藏状态"设计原则:模型只记住写入磁盘的内容,每个记忆层都可以用文本编辑器直接查看和修改。
- 认清工作区里四类记忆文件(`USER.md`/`MEMORY.md`/`memory/YYYY-MM-DD.md`/`DREAMS.md`)各自的职责边界,不要把它们当成同一层东西。
- 理解 `src/memory/` 这个核心目录到底做了什么——它不是记忆系统本体,而是"定位规范文件路径"和"记录文件级 provenance(谁写的、内容有没有被篡改)"这两件薄薄的事。
- 看懂"记忆是互斥插件槽位"这条设计从配置类型到运行时解析的完整链路:`plugins.slots.memory` 这一个字符串字段,决定了同一时间只有一个插件能拿到记忆能力。
- 理解 `memory-core` 作为默认实现提供的具体能力(SQLite、FTS5、向量、混合检索、CJK 分词),以及它和 `memory-lancedb`/`memory-wiki`/Honcho 等其他选项的关系。

## 背景与设计动机

OpenClaw 的 `VISION.md` 在"Plugins & Memory"一节里,对插件体系的设计哲学说得很直接:

```text
# VISION.md
Core stays lean; optional capabilities should usually ship as plugins.
We are generally slimming down core while expanding what plugins can do.
...
The core carries a per-call tax: each core tool, prompt line, and config key
reaches every operator on every model request, so additions there face the
strictest scrutiny. Plugins, skills, channels, and apps carry no such tax...
```

这条"core 收税、plugin 免税"的原则,直接解释了为什么 `src/memory/` 这么薄——记忆的具体实现(索引怎么建、怎么检索、怎么后台整理)体量巨大,如果塞进 core,就要让每一次模型请求都为这些复杂度买单。但紧接着,`VISION.md` 单独把 memory 拎出来说了一句更关键的话:

```text
# VISION.md
Memory is a special plugin slot where only one memory plugin can be active
at a time. Today we ship multiple memory options; over time we plan to
converge on one recommended default path.
```

这和普通插件的组合方式完全不同。工具类插件、渠道类插件都可以叠加安装、同时生效;但记忆被设计成**互斥槽位**——同一个 Gateway 实例,同一时间只能有一个插件拥有"记忆运行时"。原因不难推断:记忆系统的核心矛盾是"谁有权威决定什么内容进入长期记忆、什么内容可以被自动注入到下一轮上下文"。如果两个插件同时管理 promotion(晋升到 `MEMORY.md`)和 recall(自动注入),就会出现双份索引、双份 provenance 记录、甚至两条后台整理管线互相踩踏同一个 `MEMORY.md` 文件的竞争写问题。把记忆做成互斥槽位,相当于用配置层面的强约束换取了运行时的单一权威。

同时,"今天多个选项、未来收敛到一个推荐默认路径"这句话也说明了当前状态是过渡性的:内置的 `memory-core`、外部的 `memory-lancedb`、`Honcho` 都是候选实现,`memory-wiki` 则是一个不参与竞争槽位的伴生插件(companion),专门把记忆编译成可浏览的知识库,后文会看到它如何与主记忆插件分工。

## 核心机制详解

### 四个文件,四个层级

`docs/concepts/memory.md` 把工作区记忆文件的职责划分得很清楚:

```text
# docs/concepts/memory.md
- USER.md(optional) — 稳定偏好、沟通风格、关系、活跃项目上下文,写成指令式条目。
- MEMORY.md — 长期记忆。持久化的非画像类事实和决策。
- memory/YYYY-MM-DD.md(或带 slug 的变体)— 每日笔记。运行中的上下文和观察记录。
- DREAMS.md(optional) — Dream Diary 和后台整理摘要,供人工审阅。
```

`memory-architecture.md` 进一步把这四类文件归入一个五层的 tier 模型,其中最关键的边界是**curated core**(`MEMORY.md`/`USER.md`)和**episodic**(`memory/*.md` 每日笔记)之间:

> Curated files are small, normally in context when their provenance is eligible, and written only through gated consolidation. Episodic files are large, append-friendly, and reachable only through explicit search tools or the escalation lane. Nothing crosses from episodic to curated without passing the promotion gates described below.

也就是说,`MEMORY.md` 不是原始日志的堆叠,而是一份经过审核才能进入的精炼摘要;日常工作中产生的观察、细节全部先落到 `memory/YYYY-MM-DD.md`,能不能"晋升"进 `MEMORY.md`,由第三篇要讲的 dreaming 后台管线决定,不是由模型自己临时判断的。这条边界是理解整个记忆架构的关键锚点——第二篇讲 recall、第三篇讲 dreaming,都建立在这条边界之上。

### `src/memory/`:核心里到底放了什么

题目要求精读的 `src/memory/` 目录只有三个文件,读完就会发现:**这里没有索引逻辑,没有检索逻辑,甚至没有 dreaming 逻辑**——它只做两件"地基"性质的事。

第一件事,`root-memory-files.ts` 负责定位规范的记忆文件路径,并处理新旧文件名迁移:

```typescript
// src/memory/root-memory-files.ts
/** Canonical root memory file name used by current workspaces. */
export const CANONICAL_ROOT_MEMORY_FILENAME = "MEMORY.md";
/** Legacy root memory file name kept out of auxiliary scans. */
export const LEGACY_ROOT_MEMORY_FILENAME = "memory.md";
```

以及一个专门校验"这确实是个真文件,不是符号链接"的辅助函数:

```typescript
// src/memory/root-memory-files.ts
/** Resolves the canonical root memory file only when it is a real file, not a symlink. */
export async function resolveCanonicalRootMemoryFile(workspaceDir: string): Promise<string | null> {
  ...
  if (
    entry.name === CANONICAL_ROOT_MEMORY_FILENAME &&
    entry.isFile() &&
    !entry.isSymbolicLink()
  ) {
    return path.join(workspaceDir, entry.name);
  }
  ...
}
```

拒绝符号链接不是过度设计——如果 `MEMORY.md` 可以是个指向工作区外任意文件的符号链接,那么"记忆只在工作区内、可审查"这条无隐藏状态的承诺就被绕过了。

第二件事,`memory-artifact-provenance.ts` 给工作区里的记忆文件维护一份**文件级** provenance 记录(注意区分:这是文件粒度的记录,和后面文章要讲的"索引 chunk 级 provenance"是两套机制,服务不同的信任判定)。它的核心逻辑是:一次写入只有在"写入者声称是 agent"且"写入前的内容哈希与上次记录的 agent 写入哈希完全匹配"时,才继续标记为 `agent`;否则一律降级为 `untrusted`:

```typescript
// src/memory/memory-artifact-provenance.ts
export type MemoryArtifactOriginClass = "agent" | "untrusted";
...
const originClass =
  params.originClass === "agent" &&
  (!previous ||
    (previous.originClass === "agent" && previous.fileHash === sha256(params.contentBefore)))
    ? "agent"
    : "untrusted";
```

这是一条很值得注意的"写时鉴权"规则:哪怕这次写入本身声称来自 agent,只要文件的哈希链在中途被打断过一次(比如某次写入被记成了 `untrusted`,或者文件被外部工具直接改写而没有走这套记录),后续所有写入都会连带被判定为不可信,除非重新建立起一条连续的 `agent` 哈希链。第二篇讲 provenance 时会看到,索引层的 chunk provenance 也遵循同样"宁可保守也不默认信任"的思路。

`normalizeMemoryArtifactRelativePath` 还划定了这套 provenance 机制覆盖的文件范围——只认 `MEMORY.md`、`memory.md`、`USER.md`,以及 `memory/*.md`(排除 `memory/dreaming/` 和 `memory/.dreams/` 这些内部状态目录):

```typescript
// src/memory/memory-artifact-provenance.ts
if (["MEMORY.md", "memory.md", "USER.md"].includes(normalized)) {
  return normalized;
}
if (!normalized.startsWith("memory/") || !normalized.endsWith(".md")) {
  return undefined;
}
if (normalized.startsWith("memory/dreaming/") || normalized.startsWith("memory/.dreams/")) {
  return undefined;
}
```

综合看下来,`src/memory/` 在整个记忆系统里的角色,更像是"路径规范 + 文件完整性记录"这两条地基规则,真正的存储、索引、检索、整理,都不在 core 里。

### 记忆即插件槽位:从配置类型到运行时解析

"记忆是互斥插件槽位"不只是 `VISION.md` 里的一句产品描述,而是有对应代码实现的硬约束。配置类型层面,`PluginSlotsConfig` 里 `memory` 就是一个单值字符串字段:

```typescript
// src/config/types.plugins.ts:51
export type PluginSlotsConfig = {
  /** Select which plugin owns the memory slot ("none" disables memory plugins). */
  memory?: string;
  /** Select which plugin owns the context-engine slot. */
  contextEngine?: string;
};
```

注意这里的类型是 `string`,不是 `string[]`——从类型系统的层面就杜绝了"同时指定两个记忆插件"的可能性。运行时解析这一字段时,`memory-runtime.ts` 里的函数名和注释直接点出了这条约束:

```typescript
// src/plugins/memory-runtime.ts:82
/** Resolves the configured memory slot to the single runtime plugin that may load memory. */
function resolveMemoryRuntimePluginIds(config: OpenClawConfig): string[] {
  const plugins = normalizePluginsConfig(config.plugins);
  const memorySlot = plugins.slots.memory;
  if (!plugins.enabled || typeof memorySlot !== "string" || memorySlot.trim().length === 0) {
    return [];
  }
  const pluginId = memorySlot.trim();
  if (plugins.deny.includes(pluginId) || plugins.entries[pluginId]?.enabled === false) {
    return [];
  }
  return [pluginId];
}
```

这个函数的返回值签名虽然是 `string[]`,但函数体决定了它要么返回空数组,要么返回**恰好一个元素**的数组——不存在返回两个 id 的路径。这种"用签名兼容多值、用实现强制单值"的写法,通常是为了让调用方(遍历、过滤等下游逻辑)不用为"单值 vs 多值"写两套代码,同时又在语义上锁死了槽位的互斥性。

这条约束在插件切换时的实际表现,`docs/plugins/memory-lancedb.md` 里写得很直白:

> Installing it writes the plugin entry, enables it, and switches `plugins.slots.memory` to `memory-lancedb`. If another plugin currently owns the memory slot, that plugin is disabled with a warning.

也就是说,安装一个新的记忆插件不是"新增一个记忆来源",而是**接管**槽位、把原持有者关闭。反过来,如果配置里手动把 `plugins.slots.memory` 指向一个不存在或没有标记为 `memory` 类型的插件,加载器会直接报错拒绝:

```text
# src/plugins/loader-runtime-core.ts:254
memory slot plugin not found or not marked as memory: ${memorySlot}
```

`config-activation-shared.ts` 里还能看到槽位冲突时的具体报错文案,进一步印证了这套"先到先得、后来者需要显式接管"的行为:

```text
# src/plugins/config-activation-shared.ts
memory slot set to "${params.slot}"
memory slot already filled by "${params.selectedId}"
```

值得一提的是,`memory-wiki.md` 明确说明 `memory-wiki` 不参与这场槽位竞争——它是"伴生插件",读取当前记忆插件导出的公开 artifact,编译成一份带 provenance 的知识库,不接管 recall/promotion/dreaming:

> It does not replace the active memory plugin. Recall, promotion, indexing, and dreaming stay owned by the configured memory plugin (`memory-core`, Honcho, and others). `memory-wiki` sits beside it and compiles knowledge into a maintained wiki layer.

### `memory-core`:默认实现提供了什么

槽位机制解决的是"谁能管记忆"的问题,`extensions/memory-core/` 才是实际回答"记忆怎么管"的地方。它的插件清单文件把自己明确标记为记忆类插件,并声明了三个工具契约:

```json
// extensions/memory-core/openclaw.plugin.json
{
  "id": "memory-core",
  "name": "OpenClaw Memory",
  "kind": "memory",
  "contracts": {
    "tools": ["intent", "memory_get", "memory_search"]
  }
}
```

这三个工具(`memory_search`/`memory_get`/`intent`)正是 `docs/concepts/memory.md` 里提到的"记忆工具"全集,第二篇会展开讲它们的检索机制和触发条件。作为默认引擎,`memory-builtin.md` 列出的能力清单是:

- 基于 FTS5(BM25 打分)的关键词检索;
- 基于任意受支持 provider 的向量检索;
- 结合两者的混合检索,以及默认开启的 MMR 多样性去重;
- 按 relevance/recency/importance 的确定性排序;
- 面向中日韩文本的 trigram 分词支持;
- 可选的 sqlite-vec 原生向量加速。

其中一个容易被忽略但工程上很讲究的细节是:sqlite-vec 的原生向量查询跑在**独立的只读子进程**里——

> Native sqlite-vec queries run in a separate, read-only process so a slow query does not block the Gateway event loop. Cancelling a search terminates its query process; OpenClaw does not retry that native query on the Gateway thread.

这条设计和"失败永远不能阻塞回复"的原则(第二篇会展开)是一致的:即便向量查询很慢或者被取消,也不会拖住 Gateway 的主事件循环。索引本身存放在按 agent 隔离的 SQLite 文件里:

```text
~/.openclaw/agents/<agentId>/agent/openclaw-agent.sqlite
```

这个数据库和 session、transcript 共用同一个文件,所以 `memory-builtin.md` 特别警告不要为了"重置记忆"而直接删这个文件或它的 WAL/SHM 边车——那样会连带丢掉会话历史,正确做法是用 `openclaw memory reset`,只清理记忆自己拥有的派生表。

## 小结

这一篇把 OpenClaw 记忆系统的骨架理清楚了:核心承诺是"无隐藏状态"——一切可查、可编辑;文件分层上,`USER.md`/`MEMORY.md` 是精炼后的 curated 层,`memory/*.md` 是原始的 episodic 层,晋升要经过后台整理管线;`src/memory/` 只负责路径规范和文件级 provenance 这两件地基工作;而记忆的具体实现被设计成**互斥插件槽位**——`plugins.slots.memory` 一次只能指向一个插件,`resolveMemoryRuntimePluginIds` 在代码层面保证了这一点,默认实现 `memory-core` 提供 SQLite + FTS5 + 向量 + 混合检索的完整能力,`memory-wiki` 则作为不参与槽位竞争的伴生插件存在。

下一篇把视角切到 recall 一侧:`memory_search` 的混合检索管线到底怎么打分和排序、Active Memory 这个"深度回忆"子代理在什么条件下才会触发、以及 provenance 系统如何在写入时就阻断记忆投毒,而不是依赖事后内容审查。
