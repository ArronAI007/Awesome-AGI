# Doctor 迁移与配置契约

> 一个每周都在迭代的 Agent Harness,配置 schema 几乎必然会持续演化——字段改名、结构拆分、旧功能下线。多数项目的应对方式是在运行时代码里到处塞 `if (isLegacyShape(config))` 分支,时间一长,这些分支就会变成没人敢删的历史包袱。OpenClaw 选择了一条不同的路:运行时代码**只认当前 schema**,所有向后兼容的责任被集中到一个命令里——`openclaw doctor --fix`。这篇讲清楚这条设计原则,以及它如何与"运行时状态一律用 SQLite、不落地新的 JSON/JSONL"这条姊妹规则相互支撑。

## 学习目标

- 理解 `VISION.md` 里"Configuration compatibility"一节提出的原则:运行时代码不保留旧配置的兼容分支,配置变更必须搭配一个 doctor 迁移。
- 理解 `openclaw doctor` 的 `detect()`/`repair()` 契约设计,以及 `--lint`、`--fix`、`--non-interactive`、`--deep` 几种模式各自的读写边界。
- 理解为什么 doctor 迁移不是"永久支持",而是有大约两个月的生命周期,过期的旧字段会直接变成校验失败而不是被静默迁移。
- 理解 `docs/reference/database-schemas.md` 里"运行时状态一律用 SQLite,不新增 JSON/JSONL/sidecar 存储"这条规则的动机,以及它与 Doctor 迁移体系的配合关系。
- 理解 `AGENTS.md` 里"SQLite 运行时访问必须走 Kysely helper"这条规则背后要防的具体问题。

## 背景与设计动机

`VISION.md` 用直接了当的语言写出了这条原则,值得完整摘录:

```text
Configuration compatibility:

OpenClaw runtime code reads the current configuration schema only.
We do not keep long-lived aliases or compatibility branches that silently accept old, renamed, or malformed config keys.

When a config change makes existing user config invalid, the same change needs a doctor migration.
`openclaw doctor --fix` should detect the old shape, explain it, back it up when needed, and rewrite it to the canonical format.
Core-owned config and auth state are repaired in core doctor code; plugin-owned config is repaired by that plugin's doctor contract.
```

这段话的关键在于责任分离:**运行时(runtime)只负责按当前 schema 正确工作,不负责认识历史形状**;**认识历史形状、把旧配置改写成新形状**是 Doctor 一个人的工作。这和很多项目"运行时顺手兼容一下旧字段"的直觉做法正好相反——那种做法的问题在于,"顺手兼容"会不断累积,没有人能说清楚现在还有多少条隐藏的兼容分支活在代码里,也没有人敢删除它们,因为不知道是否还有用户依赖着某条旧路径。

`AGENTS.md` 的 Architecture 一节把这条原则写成了强制规则的一部分:

> Runtime reads canonical config and state. `openclaw doctor --fix` owns legacy normalization and migration; plugin-owned repair belongs to the plugin. Invalidating existing configuration requires the matching doctor migration.

也就是说,反过来看:**如果你要让某个配置变更使旧配置失效,这件事本身就要求你同时交付一个 doctor 迁移**——这不是"最好写一下",而是修改配置 schema 这件事的强制前置条件。这条规则把"配置演化"和"向后兼容"两件事解耦:前者可以想改就改,后者被强制要求跟上,但被限定在一个地方处理。

## 核心机制详解

### `openclaw doctor` 的模式矩阵

`docs/gateway/doctor.md` 把 doctor 的几种运行模式整理成了一张矩阵,核心区分是"是否提示"和"是否写配置/状态":

| Mode | Prompts | Writes config/state | Output | Use it for |
|---|---|---|---|---|
| `openclaw doctor` | yes | yes,安全迁移与确认过的修复 | 友好健康报告 | 引导式检查与修复 |
| `openclaw doctor --json` | no | no | JSON 建议报告 | 机器可读的运维检查 |
| `openclaw doctor --fix` | sometimes | yes,按修复策略 | 友好修复日志 | 应用已批准的修复 |
| `openclaw doctor --lint` | no | no | 结构化 findings | CI、preflight、评审门禁 |

`--lint` 是只读模式,明确写着"no prompts, repairs, migrations, restarts, or state writes"——这让它可以安全地跑在 CI 里做健康检查,而不用担心一次自动化跑批意外改写了生产配置。文档还专门解释了内部的契约设计:

> The contract separates `detect()` (reports findings) from `repair()` (reports changes/diffs/side effects), which keeps a path open for a future `doctor --fix --dry-run` without turning lint checks into mutation planners.

`detect()` 和 `repair()` 分离,不只是代码整洁的考虑——它保留了未来加一个 `--fix --dry-run`(只报告将要做什么改动,但不真正写)的可能性,而不需要把现在的只读 lint 检查改造成"会计算变更计划"的东西。这是一种典型的"现在按最小职责实现,但不堵死未来演进路径"的设计克制。

### 迁移不是永久的:两个月窗口

Doctor 文档里最容易被忽略、但恰恰是这套设计里最关键的一条规则,藏在一处 `<Note>` 里:

> Doctor only carries automatic migrations for roughly two months after a key is retired. Older legacy keys (for example the original `routing.queue`, `routing.bindings`, `routing.agents`/`defaultAgentId`, `routing.transcribeAudio`, top-level `agent.*`, or top-level `identity` from the pre-multi-agent config shape) no longer have a migration path; config using them now fails validation instead of being rewritten. Fix those keys by hand against the current config reference before doctor can proceed.

这意味着"配置兼容"这件事本身也有生命周期,不是一次写完就管一辈子。一个字段被废弃之后,Doctor 大约维护两个月的自动迁移路径;过了这个窗口,迁移代码本身也会被清理掉,旧字段的配置直接在校验阶段失败,提示用户手动对照当前配置参考修改。这条规则保证了 Doctor 自己的代码库不会无限膨胀成一部记录着项目从诞生至今每一次配置改名的活化石——迁移代码有明确的退休期,过期作废,而不是无限期地"以防万一"保留下去。

文档里紧接着列出的迁移表格规模也印证了这套体系的运转强度,随手摘几行:

| Legacy key | Current key |
|---|---|
| `routing.allowFrom` | `channels.whatsapp.allowFrom` |
| `session.idleMinutes` | `session.reset.idleMinutes` |
| `tools.exec.security` + `tools.exec.ask` | `tools.exec.mode` |
| `messages.tts.<provider>`(`openai`/`elevenlabs`/`microsoft`/`edge`） | `tts.providers.<provider>` |
| `agents.list` | 键值化的 `agents.entries` |
| top-level `heartbeat` | `agents.defaults.heartbeat` / `channels.defaults.heartbeat` |

这张表格在文档里有几十行,涵盖字段改名、结构从扁平变嵌套、枚举值重命名(比如 `talk.tts.provider: "edge"` 改成 `"microsoft"`)等各种形态的变更——每一行都对应一次真实发生过的 schema 演化,而运行时代码里完全不需要知道这些历史形状存在过。

### Gateway 启动时的自动迁移与拒绝启动

Doctor 不是唯一处理迁移的入口。Gateway 启动时也会尝试自动应用"确定性的、无需提示的"legacy key 迁移:

> Gateway startup automatically applies deterministic, prompt-free legacy config migrations when an otherwise invalid single-file config can be fully migrated. It uses the same migration transforms as `openclaw doctor --fix`... If any validation or legacy-key issue remains after migration, startup leaves the config unchanged, refuses to start, and prints the `openclaw doctor --fix` hint.

关键在于失败路径:如果启动时的自动迁移不能把配置完全迁移到合法状态,Gateway **拒绝启动**,而不是"凑合着用旧配置跑起来"或者试图在运行时兼容剩下的问题。这是"运行时只认当前 schema"原则在启动时序上的具体体现——宁可拒绝服务并给出明确的修复命令提示,也不让一个处于中间状态的配置进入正常运行路径。

同样的拒绝策略也出现在数据库层面。`docs/reference/database-schemas.md` 描述了 SQLite 的版本契约:

> OpenClaw applies forward-only migrations when it opens an older supported database. It refuses a database whose `user_version` is newer than the running build and reports a `newer schema version` error... When Gateway startup encounters a newer database schema, it exits with status 78 so the generated systemd service does not restart it repeatedly.

数据库 schema 只能前向迁移,遇到比自己新的 schema 版本直接拒绝打开并以退出码 78 结束进程——连 systemd 的自动重启策略都被考虑进去了(退出码 78 通常被 systemd 解读为"配置错误,不要无脑重试")。这和配置层的"迁移不了就拒绝启动"是同一种工程哲学的两处体现。

### 运行时状态一律用 SQLite

`AGENTS.md` 的 Architecture 一节里紧跟着配置迁移规则的下一条,是存储介质的规则:

> OpenClaw-owned runtime state and caches use SQLite, not new JSON/JSONL/sidecar stores. Files are for named user artifacts, imports/exports, attachments, logs, backups, or external-tool contracts. Read `docs/reference/database-schemas.md` before storage work; it owns database placement, compatibility, and migration rules.

`docs/reference/database-schemas.md` 描述了两级 SQLite 布局:

| Scope | Default path | Contents |
|---|---|---|
| Global control plane | `~/.openclaw/state/openclaw.sqlite` | 共享配置状态、注册表、审批、插件状态 |
| Per-agent data plane | `~/.openclaw/agents/<agentId>/agent/openclaw-agent.sqlite` | 会话、transcript、记忆索引、认证状态 |

这条规则和 Doctor 迁移体系是一体两面:早期版本的 OpenClaw(以及很多同类项目)习惯把会话历史存成 `sessions.json`、`sessions/*.jsonl` 这类文件,Doctor 文档里也确实记录着这类历史迁移路径——例如"Session rows and transcripts: import legacy `sessions.json` and JSONL history... into `~/.openclaw/agents/<agentId>/agent/openclaw-agent.sqlite`"。但这些迁移路径的存在,恰恰是为了**把历史遗留的文件态数据一次性搬进 SQLite 之后,就再也不必让运行时代码同时理解两种存储形态**。数据库文档也明确指出了这一点:"Gateway and local CLI startup use SQLite; they do not import, restore, or rewrite session JSON/JSONL files. When startup finds a legacy session store, it refuses readiness"——运行时遇到旧的文件态会话存储,同样是拒绝启动,而不是回退兼容读取。

### SQLite 访问必须走 Kysely

统一了存储介质之后,`AGENTS.md` 还进一步统一了访问方式:

> SQLite runtime access uses Kysely helpers; raw SQL is limited to schema/migrations, bootstrap, and justified SQLite primitives. Write transactions are synchronous: finish async planning first, then reread authoritative state before committing. No Promise or `await` in a transaction callback.

Kysely 是一个 TypeScript 查询构建器,能在编译期对 SQL 查询做类型检查。把"裸 SQL 只允许出现在 schema 定义、迁移脚本、以及少数确有必要直接使用 SQLite 原语的场景"定为规则,意味着日常业务代码里的数据库读写全部有编译期类型保障,不会因为一次手写 SQL 里的字段名拼写错误而在运行时才暴露问题。"写事务必须同步、事务回调里不能有 `await`"这条限制则是 SQLite 单写者模型的直接推论——SQLite 的写事务是阻塞性的,如果在事务回调里等待一个异步操作,等于在持有写锁的同时把控制权交还给事件循环,这正是很多 Node.js + SQLite 项目里死锁或事务超时问题的根源。规则要求提前完成所有异步规划,进入事务后只做纯同步的读写提交。

### 材料性变更需要走评审

`database-schemas.md` 的结尾部分给出了一份判断"什么样的 SQLite 变更算材料性变更、需要在实现前开一个维护者讨论"的清单——新表、canonical/derived 数据边界变化、迁移/回滚/保留策略变化、事务边界与并发语义变化、读写性能影响足以改变存储运行模型的场景,都要求先有一份被接受的设计讨论,再动手实现,并且"a schema-version bump is always material, but a change can be material even when the numeric version stays the same"——版本号没变,也可能是材料性变更(文档举了大量"同版本追加可空列"的真实案例)。这条流程性规则,本质上是把"Doctor 迁移必须配套配置变更"同一种纪律,平移到了数据库 schema 这一层。

## 常见问题/易踩坑

- **不要指望运行时代码"兼容一下"旧配置**:遇到旧字段,运行时的正确行为是校验失败并提示运行 `openclaw doctor --fix`,而不是尝试自己识别并处理历史形状——这条边界是故意的,不是遗漏。
- **迁移窗口过期后旧字段无法自动修复**:如果一个字段废弃超过两个月还没有升级配置,`doctor --fix` 不会再帮你迁移,必须手动对照当前配置文档改写。
- **`--lint` 和 `--fix` 不是同一套规则集的两种输出模式**:文档明确指出"`doctor --fix` does not use the lint default profile and does not accept `--all`",两者的规则选择逻辑并不相同,不能假设 lint 报告的问题都会被 `--fix` 处理。

## 小结

OpenClaw 把"配置需要向后兼容"这件事从一条散落在运行时代码各处的隐性负担,收敛成了一条显式的、有生命周期的工程契约:配置 schema 变更必须搭配 Doctor 迁移,迁移本身只维护约两个月就会退休,过期的旧配置直接校验失败;运行时状态统一落在 SQLite 里,遇到无法识别的旧存储形态同样是拒绝启动而不是静默兼容;SQLite 的访问方式也被 Kysely 类型化,材料性的 schema 变更需要先过评审。这四件事共同保证了运行时代码库能够持续演化,而不必背负一部永远不会被清空的兼容性历史。下一篇转向另一条同样贯穿全仓库的工程纪律——OpenClaw 的测试哲学与 CI 流水线是如何组织的。
