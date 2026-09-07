# SessionDB Mixin 架构：SQLite WAL、FTS5 与 CJK 分词

> hermes-agent 把会话状态从"每个会话一个 JSONL 文件"整体迁移到了一个 15000 行的巨型模块 `hermes_state.py`——但这不是一次简单的存储介质替换。WAL 模式让 gateway 能同时服务 CLI、Telegram、Discord 等多个前端并发写读同一份 state.db；FTS5 全文检索让 `/history` 之类的会话搜索命令不必逐行扫描所有历史；而核心类 `SessionDB` 为了不让一个类膨胀到无法维护，被拆成了三个只做一件事的 mixin。本篇结合真实源码,把这套存储层的架构决策一条条讲清楚。

## 学习目标

- 理解为什么 hermes-agent 要从"per-session JSONL 文件"迁移到 SQLite：WAL 并发模型、FTS5 全文检索、事务性拆分,分别解决了什么具体问题。
- 看懂 `SessionDB(SessionSearchMixin, SessionSchemaMixin, SessionPortabilityMixin)` 这种多重继承背后的关注点分离,以及"mixin 之间不得互相 import hermes_state"这条规则为什么必要。
- 理解 schema 演进为什么用"和 `SCHEMA_SQL` 源码逐列比对、自动 `ALTER TABLE ADD COLUMN`"而不是版本化迁移脚本。
- 理解 `native/fts5_cjk` 这个自研 C 扩展为什么存在：标准 FTS5 trigram tokenizer 对中日韩文本的具体缺陷是什么。
- 理解 `parent_session_id` 链如何在数据模型层面支撑"压缩触发会话拆分"这件事——本篇只讲存储结构,压缩算法本身留给下一篇。

## 从 per-session JSONL 到 SQLite：动机

`hermes_state.py` 的模块 docstring 把设计动机写得很直白：

```python
# hermes_state.py
"""
SQLite State Store for Hermes Agent.

Provides persistent session storage with FTS5 full-text search, replacing
the per-session JSONL file approach. Stores session metadata, full message
history, and model configuration for CLI and gateway sessions.

Key design decisions:
- WAL mode for concurrent readers + one writer (gateway multi-platform)
- FTS5 virtual table for fast text search across all session messages
- Compression-triggered session splitting via parent_session_id chains
- Batch runner and RL trajectories are NOT stored here (separate systems)
- Session source tagging ('cli', 'telegram', 'discord', etc.) for filtering
"""
```

这五条对应的是五个真实痛点。第一,`hermes` 不再只是一个本地 CLI——`gateway` 让同一个 state.db 要同时被 CLI 进程、Telegram bot、Discord bot 等多个前端读写,per-session JSONL 文件很难做并发控制,而 SQLite 的 WAL 模式天然支持"多读者 + 一个写者"。第二,`/history`、`session_search` 这类跨会话全文检索,如果历史是散落的 JSONL 文件,只能逐文件 grep;FTS5 虚拟表把这个能力下沉到数据库索引层。第三,压缩触发的会话拆分(比如上下文太长,把旧会话"关闭"、开一个继承了同一份 `session_key`/`chat_id` 的新会话)需要原子性——"父会话已关闭但子会话数据丢了一半"是不可接受的中间状态,SQLite 事务能保证这一点,普通文件写入很难。第四条和第五条则划清了这个模块的边界:`batch_runner.py` 产出的训练轨迹、RL 系统的数据不进这张表(第三篇会讲的 `trajectory_compressor.py` 处理的正是这部分独立数据);`source` 字段区分会话来自哪个前端,用于按渠道过滤——比如后文会看到的:

```python
# hermes_state.py:13318
"SELECT COALESCE(NULLIF(s.source, ''), 'cli') AS source, COUNT(*) AS count "
```

## Mixin 拆分:`SessionDB(SessionSearchMixin, SessionSchemaMixin, SessionPortabilityMixin)`

一个要同时管 schema、搜索、导入导出、压缩事务的类,代码量必然庞大。hermes-agent 的做法不是拆成多个独立类互相持有引用,而是拆成三个 **mixin**,由 `hermes_state.py` 里的核心类组合而成:

```python
# hermes_state.py:4385
class SessionDB(SessionSearchMixin, SessionSchemaMixin, SessionPortabilityMixin):
```

三个 mixin 分别定义在独立文件里,每个文件头部都有几乎一字不差的"契约声明":

```python
# hermes_state_search.py:1-9
"""Full-text / trigram / CJK message search and FTS maintenance for SessionDB.

Mixin contract: this is a plain mixin class consumed by
``hermes_state.SessionDB``. It defines no ``__init__`` and no state of its
own; methods access the host's attributes (``self._conn``, ``self.db_path``,
``self._execute_write`` and other SessionDB methods) established by
``SessionDB.__init__``. It must never import hermes_state (cycle) — shared
module-level constants live in hermes_state_common.
"""
```

`hermes_state_schema.py` 和 `hermes_state_portability.py` 的头部注释除了第一句职责描述不同,后面的"契约"段落逐字相同。这不是巧合,而是刻意维持的约束:

- **mixin 不定义 `__init__`,不持有自己的状态**——它们完全依赖宿主类 `SessionDB.__init__` 建立起来的 `self._conn`/`self.db_path`/`self._execute_write` 等属性,以及互相调用对方 mixin 上的方法(比如 `SessionSchemaMixin` 里的方法可以调用 `SessionSearchMixin` 定义的方法,因为最终它们都合流到同一个 `SessionDB` 实例上)。
- **"必须不能 import hermes_state"**——如果 `hermes_state_search.py` 反过来 `from hermes_state import SessionDB` 只是为了拿一个常量,就会形成 `hermes_state → hermes_state_search → hermes_state` 的循环 import,Python 会直接报错。解法是把三个 mixin 都需要用到的常量、SQL 片段抽到第四个文件 `hermes_state_common.py`,三个 mixin 和 `hermes_state.py` 都单向依赖它,不产生环:

```python
# hermes_state_common.py:1-7
"""Shared module-level constants for the SessionDB family of modules.

Extracted verbatim from hermes_state.py so the SessionDB mixin modules
(hermes_state_search / hermes_state_schema / hermes_state_portability) can
reference them without importing hermes_state (which would be a cycle).
hermes_state re-imports every name here for backward compatibility.
"""
```

三个 mixin 各自的职责边界,可以从各自文件的实际内容归纳出来:

| Mixin | 文件 | 行数 | 核心职责 |
|---|---|---|---|
| `SessionSearchMixin` | `hermes_state_search.py` | 2510 | FTS5/trigram/CJK 全文检索、索引维护与自愈 |
| `SessionSchemaMixin` | `hermes_state_schema.py` | 1529 | 建表 DDL、列级 schema 对账(reconciliation)、FTS 触发器管理 |
| `SessionPortabilityMixin` | `hermes_state_portability.py` | 845 | 会话列表/富行展示、导出(export)、导入(import) |

`SessionDB` 本体(`hermes_state.py`,15285 行)保留的是最核心、跨关注点的部分:连接管理、WAL/日志模式处理、消息读写、压缩事务(`archive_and_compact`/`publish_compression_child`)、锁与租约等。这种拆法的好处是显而易见的:改一次全文检索的实现细节,只需要审查 2510 行的 `hermes_state_search.py`,而不用在一个 15000+ 行的文件里定位相关代码;三个模块各自的头部注释也明确写清楚了"我依赖宿主的哪些属性",降低了维护者误判耦合关系的风险。

## Schema 演进:列级对账而不是版本化迁移脚本

`hermes_state_schema.py` 没有采用"一堆 `migration_0001.sql`、`migration_0002.sql` 顺序执行"的传统迁移框架,而是维护一份 `SCHEMA_SQL`(建库时的完整期望状态),每次打开数据库都拿现有列集合去和它比对,缺什么就补什么:

```python
# hermes_state_schema.py:678
def _reconcile_columns(self, cursor: sqlite3.Cursor) -> None:
    ...
    # ALTER TABLE ADD COLUMN — 逐列比对 SCHEMA_SQL 与现有表结构后追加缺失列
```

这套机制还延伸出一个只读场景下的自愈探针 `schema_read_probe_statements`:

```python
# hermes_state_schema.py
def schema_read_probe_statements() -> tuple:
    """SELECT statements that fail iff a live store is behind SCHEMA_SQL.

    Read-only opens skip ``_reconcile_columns()`` by design (no DDL against
    another profile's live DB), so a store created before a schema addition
    keeps 500ing on read paths until something opens it writable. ...
    Derived from SCHEMA_SQL — the same source of truth the writable
    reconciler diffs against — so a column added there is covered here
    automatically. A hand-maintained probe list went stale within days of
    shipping (it never learned ``sessions.last_activity_at``, ...)
    """
```

这段注释里提到的教训很实在:早期维护过一份手写的"需要探测哪些列"清单,结果很快就漏掉了新加的 `sessions.last_activity_at` 列,导致某些只读路径悄悄返回空列表。解法是让探针语句直接从 `SCHEMA_SQL` 解析生成,而不是人工维护第二份清单——**同一个事实来源(source of truth)驱动两条路径**,新增一列时两边自动同步,不需要开发者记得同时改两处。

## FTS5 全文检索与 CJK 分词

### 为什么标准 tokenizer 对中日韩不够用

SQLite FTS5 自带的 `unicode61`/trigram tokenizer 是按空格和标点分词的,这对英文没问题,但中文、日文、韩文没有空格分隔单词。`hermes_state.py` 里有一段很直接的注释说明了这个问题的实测代价:

```python
# hermes_state.py:3720 附近
# The trigram tokenizer needs >=3 chars per query term, so 1-2 char CJK
# terms (ubiquitous in Korean/Chinese: 일본, 구글, 项目, ...) fall through
# to a LIKE full-table scan — measured 3-6s CPU per query on multi-GB
# installs and the dominant base cost of session_search on CJK workloads.
```

trigram tokenizer 要求查询词至少 3 个字符才能命中索引,而中日韩里 1-2 个字的词(比如"项目""구글")极为常见——这些查询会直接退化成全表 `LIKE` 扫描,在几个 GB 大小的 state.db 上实测要吃掉 3-6 秒 CPU,是 CJK 场景下 `session_search` 的主要性能瓶颈。

### 自研 `cjk_unicode61`:字符级 bigram

`native/fts5_cjk/` 是一个约 250 行、无外部依赖的可加载 FTS5 tokenizer,包装 `unicode61`:凡是连续的 CJK 字符,重新切成有重叠的字符 bigram(Lucene `CJKAnalyzer` 的语义),其余字符原样透传:

```python
# hermes_state.py:3753
FTS_CJK_TABLE_SQL = """
CREATE VIEW IF NOT EXISTS messages_fts_cjk_src AS
    SELECT id, role, content, tool_name, tool_calls
    FROM messages
    WHERE role <> 'tool';

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts_cjk USING fts5(
    content,
    tool_name,
    tool_calls,
    content='messages_fts_cjk_src',
    content_rowid='id',
    tokenize='cjk_unicode61'
);
"""
```

`native/fts5_cjk/README.md` 交代了它的来历和用法:

```text
# fts5_cjk — cjk_unicode61 FTS5 tokenizer

unicode61 + CJK character bigrams (Lucene CJKAnalyzer semantics). Fixes
1-2 char Korean/Chinese/Japanese terms falling through to LIKE full-table
scans in session search.

Build & install to `~/.hermes/lib/`:

    ./build.sh

Uses the system `sqlite3ext.h` when available, else the vendored copy in
`vendor/` — no libsqlite3-dev required.

Contributed by Soju06 (PR #65544).
```

`build.sh` 就是一条 `gcc -shared -fPIC -O2` 编译命令,产物 `libfts5_cjk.so` 装到 `~/.hermes/lib/`,不需要预装 `libsqlite3-dev`(优先用系统的 `sqlite3ext.h`,没有就用仓库里 vendor 的公开域头文件)。运行时加载是"尽力而为、绝不抛异常"的:

```python
# hermes_state.py:3827
def load_fts5_cjk_extension(conn: sqlite3.Connection) -> bool:
    """Best-effort load of the cjk_unicode61 tokenizer into ``conn``.

    Returns False (never raises) when the .so is absent, the feature is
    disabled via ``sessions.cjk_fts``, or this Python build has extension
    loading compiled out — every caller treats False as "behave exactly as
    before the cjk index existed".
    """
    if not _cjk_fts_config_enabled():
        return False
    path = fts5_cjk_so_path()
    if not path.exists():
        return False
    try:
        conn.enable_load_extension(True)
        try:
            conn.load_extension(str(path))
        finally:
            conn.enable_load_extension(False)
        return True
    except Exception:
        logger.warning("fts5_cjk extension load failed (%s)", path, exc_info=True)
        return False
```

这个"加载失败就退化"的设计贯穿了整个 CJK 索引:`messages_fts_cjk` 表只有在扩展成功加载时才可能被创建和维护;一旦某个进程连不上扩展(比如换了一台没编译过 `.so` 的机器),它会自我修复——丢弃 CJK 相关触发器,消息写入照常进行,索引变"陈旧"但不阻塞任何功能,等下一次在有扩展的宿主上运行 `hermes sessions optimize-storage` 时再回填。表结构本身延续了 v23 存储纪律:external-content 模式(不重复存正文,只存索引)、排除 `role='tool'` 的行(工具输出走另一张普通 `messages_fts` 索引)。

## `parent_session_id` 链:压缩触发拆分的数据模型

前面提到"压缩触发的会话拆分"需要事务性,具体的存储结构是这样的:`sessions` 表每一行都有一个可空的 `parent_session_id` 列,当一次运行时压缩(第二篇讲的 `agent/context_compressor.py`)判定要把当前会话"关闭"、开一个携带压缩摘要的新会话继续对话时,调用的是 `publish_compression_child`:

```python
# hermes_state.py:7034
def publish_compression_child(
    self,
    *,
    parent_session_id: str,
    child_session_id: str,
    source: str,
    messages: List[Dict[str, Any]],
    ...
    watermark: Optional[int] = None,
    watermark_ceiling: Optional[int] = None,
) -> None:
    """Atomically close a parent and publish its durable compression child.

    The parent closure, child row, and compacted handoff become visible in
    one transaction. Readers can therefore observe either the live parent or
    a complete child, never an ended parent with a missing/empty child.

    Concurrent-append safety (#75316): when *watermark* is provided (the
    parent's :meth:`get_active_message_watermark` captured at compression
    start), parent rows that arrived during the slow summary call
    (``id > watermark``) are cloned into the child AFTER the handoff ...
    """
```

这段实现体现了几个存储层要解决的具体问题:

1. **原子性**:父会话关闭(`ended_at`/`end_reason='compression'`)、子会话建行、压缩后的消息写入,全部在同一个 `_execute_write` 事务里完成——外部读者永远只能看到"活着的父会话"或"完整的子会话"这两种状态之一,不会看到"父已关闭但子是空的"这种损坏中间态。
2. **并发追加安全**:压缩摘要要调用 LLM,是一次慢操作(第二篇细讲),在这期间父会话完全可能又收到了新消息(比如 gateway 的另一个并发请求)。`get_active_message_watermark` 在压缩开始前先记录父会话当前的最大消息 id,`publish_compression_child` 在提交时把 `id > watermark` 的"迟到"消息克隆进子会话,保证这些并发写入不会丢在已关闭的父会话里出不来。
3. **字段继承**:子会话继承父会话的 `cwd`、`git_branch`、`session_key`、`chat_id`、`chat_type`、`profile_name` 等——这些字段大多是 gateway 路由用的(比如某个 Telegram 会话对应哪个 chat_id),压缩拆分不能打断路由链路。

链式追溯上,"父子关系"并不是唯一含义——`parent_session_id` 也被 delegate/subagent、`/branch` 分支功能复用,所以要严格区分"这是不是一次压缩延续边界"。`hermes_state.py` 用一条递归 CTE 来做这个判断,而不是在 Python 里逐跳遍历:

```python
# hermes_state.py:9675 附近
"""
``_COMPRESSION_CHILD_SQL``: a parent → child edge counts only when the
parent ended with ``end_reason = 'compression'`` and the child started
at or after the parent's ``ended_at``, which distinguishes continuations
from delegate subagents / branch children that also carry a
``parent_session_id``. Expressed as a single recursive CTE rather than a
per-hop Python walk so the edge definition lives in exactly one place.
"""
edge = _COMPRESSION_CHILD_SQL.format(a="child")
row = conn.execute(
    f"""
    WITH RECURSIVE ancestors(id) AS (
        SELECT ?
        UNION
        SELECT parent.id
        FROM ancestors a
        JOIN sessions child ON child.id = a.id
        JOIN sessions parent ON parent.id = child.parent_session_id
        WHERE {edge}
    )
    SELECT 1 FROM ancestors WHERE id = ? AND id != ? LIMIT 1
    """,
    (descendant_id, ancestor_id, descendant_id),
).fetchone()
```

值得一提的是,压缩发布之前还有一道"租约"保护:`compression_locks` 表(`hermes_state_common.py` 里的 `CREATE TABLE`)记录 `session_id → holder → expires_at`,`publish_compression_child` 在写入前会校验调用方是否仍持有租约、租约是否过期——避免两个并发进程同时对同一个会话做压缩拆分,写出两条竞争的子会话。这和本文开头"WAL 支持多读者但只有一个写者"的并发模型是一致的:WAL 解决的是"读不阻塞写",而压缩这种"必须独占执行一次"的操作,仍然需要应用层的租约机制兜底。

## 小结与思考题

hermes-agent 的会话存储层用一套组合手法应对了多个互相独立的工程问题:WAL 模式解决 gateway 多前端并发读写;FTS5(+自研 CJK 分词扩展)解决全文检索,且做到了"扩展缺失就优雅退化"而不是硬依赖;`SessionDB` 的 mixin 拆分把一个必然庞大的类按 search/schema/portability 三个关注点分离,靠"共享常量放 common 模块"这条纪律避免了循环依赖;schema 演进选择了列级对账而不是版本化迁移脚本,用同一份 `SCHEMA_SQL` 同时驱动"该建什么"和"该探测什么";`parent_session_id` 链在数据模型层面为压缩触发的会话拆分提供了原子性、并发安全性和字段继承。需要向你说明的一点是:调研摘要里提到的"三个 mixin 文件顶部注释明确写了共享常量放 `hermes_state_common.py`"和类结构描述,经过逐一核实,与真实代码完全一致,没有出入。

思考题:

1. `_reconcile_columns` 的"列级对账"方案在什么情况下会失效?如果一次 schema 变更不是新增列,而是要重命名列或改变列的语义(比如把一个 `TEXT` 列改成 `INTEGER` 并转换已有数据),这套机制还够用吗?
2. `cjk_unicode61` 的字符级 bigram 策略能让 1-2 字的中日韩查询词命中索引,但 bigram 索引的体积通常比原文本词汇索引大。如果你要评估是否该给所有语言的历史消息都建 CJK 索引(而不仅是检测到 CJK 内容才建),你会用什么指标衡量这个权衡?
3. `publish_compression_child` 用 `watermark`/`watermark_ceiling` 处理压缩期间的并发追加,`archive_and_compact`(用于同一会话内的原地压缩,不拆分成新会话)也需要类似的并发保护。如果这两条压缩路径的租约(`compression_locks`)被同一个 holder 并发触发两次,数据库层面的哪个约束会先失败,失败之后调用方应该如何处理?
