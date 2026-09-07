# Secrets 与 Audit

> `AGENTS.md` 在给贡献者的规则里,对审计系统留了一条格外郑重的批注:"Audit, execution identity, or receipt producers/consumers: read `docs/gateway/audit.md` in full. Its opt-in provenance is never authorization; changes to collection, reader scope, retained fields, bounds, or contracts require approval."——审计留痕永远不能被当作授权凭证,任何改动都要经过审批。这条批注和 secrets 系统里反复出现的另一句话是同一枚硬币的两面:"SecretRefs stop credentials from being persisted in config...but they are not a process-isolation boundary"——密钥引用能防止凭据落地成明文配置,但不是进程隔离边界。本篇把这两套机制——凭据怎么在不进入模型上下文的前提下被使用,审计记录怎么被设计成"只留痕、不背书"——一次讲透。

## 学习目标

- 理解 SecretRef 契约的四种来源(`env`/`file`/`exec`/`store`)以及它解决的具体问题:让受支持的凭据不必以明文形式写进配置文件。
- 理解"agent 可读边界":SecretRef 消除的是配置文件里的明文残留,不是进程级隔离——一个能读文件的 agent 依然能读到磁盘上残留的明文凭据。
- 理解出站哨兵(sentinel)机制和密钥出站代理(egress proxy)如何让 Gateway 托管的 exec 进程使用凭据而不接触明文,以及这套机制承认自己防不住什么。
- 理解认证凭据的语义模型——token 的过期规则、OAuth 材料为什么被排除在 SecretRef 静态解析之外、个人模型账号的凭据边界。
- 理解审计账本的"元数据留痕、不是授权证据"这条设计原则的具体落地:哪些字段永远不会被记录,"enforced"这个标签什么时候才成立,以及"没有记录不代表没发生过"这条声明。

## 背景与设计动机

Secrets 文档开篇就先把"这套机制到底解决什么问题"说清楚,同时坦率承认了它的边界:

> "OpenClaw supports additive SecretRefs so supported credentials do not need to live as plaintext in configuration."
> —— `docs/gateway/secrets.md`

> "Plaintext credentials remain agent-readable when they sit in files the agent can inspect, including `openclaw.json`, `.env`, retired auth-profile JSON archives, or generated `agents/*/agent/models.json` files. SecretRefs reduce that local blast radius once every supported credential is migrated and `openclaw secrets audit --check` reports no plaintext residue."
> —— `docs/gateway/secrets.md`

这段警告值得在动手配置 SecretRef 之前先读懂:SecretRef 不是"把凭据加密"或者"把凭据从 agent 眼皮底下藏起来",它做的事情更朴素——**让配置文件里不再需要写明文凭据**。如果某个凭据类型暂时不被 SecretRef 支持,或者一份旧的明文配置备份还留在磁盘上,agent 只要有文件读取权限,依然能读到它。这条边界和上一篇讲的"沙箱不是完美安全边界"是同一种诚实的表达方式——文档没有把自己包装成银弹,而是精确划定了这套机制实际覆盖的范围。

审计系统这边,`docs/gateway/audit.md` 一开篇就把这份记录的定位讲清楚:它回答的是"哪个 agent 跑了、什么时候跑的、怎么结束的"这类**运维问题**,而不是构建一份可以当证据链使用的合规档案:

> "The Gateway keeps a bounded, metadata-only audit ledger in the shared OpenClaw state database. ... The ledger stores identity, ordering, provenance, action, status, and normalized outcome codes. It never stores prompts, message bodies, tool arguments, tool results, attachments, filenames, URLs, command output, or raw error text."
> —— `docs/gateway/audit.md`

这两套机制放在一起看,共享同一个设计哲学:**明确划定机制的边界,并且拒绝让使用者产生"这已经足够安全/足够完整"的错觉**。下面逐个展开。

## 核心机制详解

### SecretRef 契约:四种来源,一套形状

所有受支持的凭据字段都可以接受同一个对象形状:

```json5
{ source: "env" | "file" | "exec" | "store", provider: "default", id: "..." }
```

四种来源分别对应四类凭据托管方式:

- **`env`**:从环境变量读取,例如 `{ source: "env", provider: "default", id: "OPENAI_API_KEY" }`,也支持 `${OPENAI_API_KEY}` 这种简写形式。
- **`file`**:从本地文件读取,支持 JSON 指针寻址(`mode: "json"`)或整份文件内容(`mode: "singleValue"`)。
- **`exec`**:运行一个配置好的可执行文件来解析凭据,这是 1Password、Vault、Bitwarden、`pass`、sops 这类外部密钥管理器的接入方式。
- **`store`**:从 OpenClaw 自己维护的共享 SQLite 密钥库读取。

`exec` provider 的安全校验值得单独一提,因为它直接面对"配置里写一个可执行文件路径"这种天然危险的操作:

> "Runs the configured absolute binary path directly, no shell.
> `command` must not be a symlink, must not be group- or world-writable, and on POSIX must be owned by the current user."
> —— `docs/gateway/secrets.md`

不走 shell、拒绝符号链接、拒绝组/其他用户可写、要求属主匹配——这几条校验组合起来,堵住的是"配置文件被篡改后指向一个被替换过的可执行文件"这类供应链风险。

### Agent 可读边界:SecretRef 不是进程隔离

这是整个 secrets 系统里最容易被误解的一点,文档专门用一整节 Agent-access boundary 把话说穿:

> "SecretRefs stop credentials from being persisted in config and generated model files, but they are not a process-isolation boundary. A plaintext credential left on disk in a path the agent can read is still readable via file or shell tools, bypassing API-level redaction."
> —— `docs/gateway/secrets.md`

文档进一步给出了"迁移完成"的判定标准,而不是一句空洞的"用了 SecretRef 就安全了":

> "For production deployments where agent-accessible files are in scope, treat migration as complete only when all of these hold:
> - Supported credentials use SecretRefs instead of plaintext values.
> - Legacy plaintext residue is scrubbed from `openclaw.json`, the SQLite auth-profile store, `.env`, and generated `models.json` files.
> - `openclaw secrets audit --check` is clean after migration.
> - Any remaining unsupported or rotating credentials are protected by OS isolation, container isolation, or an external credential proxy."
> —— `docs/gateway/secrets.md`

四条缺一不可,这也是为什么文档把 `secrets audit` / `secrets configure` / `secrets apply` 这一组命令称为"安全迁移闸门"而不是"便利工具":

> "This is why the audit/configure/apply workflow is a security migration gate, not just a convenience helper."
> —— `docs/gateway/secrets.md`

### 出站哨兵与密钥出站代理:让凭据只在离开进程的那一刻才现身

对模型提供商凭据,OpenClaw 在鉴权解析阶段就铸造一个不透明的、进程本地的"哨兵"值,代替真实凭据流经大部分运行时代码路径:

> "OpenClaw mints an opaque, process-local sentinel during model-auth resolution. Auth storage, stream options, SDK configuration, logs, error objects, and most runtime introspection therefore see a value such as `oc-sent-v2.<authenticated-ciphertext>.end`, not the provider credential."
> —— `docs/gateway/secrets.md`

真正的替换发生在请求真正离开进程之前的最后一刻,而且对无法识别的哨兵形状值,系统选择直接拒绝发送而不是把未解析的哨兵原样转发出去:

> "Unknown sentinel-shaped values fail closed before network activity. OpenClaw refuses to send the request rather than forwarding an unresolved sentinel to a provider."
> —— `docs/gateway/secrets.md`

但文档同样诚实地划出了这套机制的边界——哨兵减少的是"凭据在调用链里以明文形式流经的次数",不是进程隔离:

> "Sentinels reduce plaintext exposure across the model-call chain, but they are not process isolation. The real value still exists in same-process memory and appears at the final adapter boundary."
> —— `docs/gateway/secrets.md`

针对 Gateway 托管的 exec 子进程,还有一层默认关闭的密钥出站代理(secret egress proxy),它的思路是让子进程环境里只出现哨兵,由一个 Gateway 拥有的回环代理在请求即将出站时才做替换:

> "The secret egress proxy lets Gateway-hosted agent subprocesses use shared-store `secret` entries without receiving their plaintext. OpenClaw puts the existing authenticated sentinel in the subprocess environment, then a Gateway-owned loopback proxy replaces it in request URLs, headers, and streamed bodies immediately before egress."
> —— `docs/gateway/secrets.md`

这套代理有一条硬性约束——每个密钥必须显式声明允许替换的目标主机,精确匹配、不支持通配符:

> "Each secret must also name the exact HTTPS hosts where substitution is allowed. Hostnames are stored lowercase in ASCII/punycode form and matched exactly; wildcards, suffix matching, and ports are not supported. A secret with no allowed hosts is never substituted."
> —— `docs/gateway/secrets.md`

但文档同样明确列出了这条"目标主机绑定"防不住的攻击面:

> "Destination binding does not make an allowed host trustworthy. A bound service that reflects request credentials can still return the plaintext to the agent. DNS-level compromise can redirect a permitted hostname because policy is hostname-based, not an IP pin."
> —— `docs/gateway/secrets.md`

以及这套代理天然只能约束"配合的客户端"——一个不遵守代理环境变量的子进程完全可以绕开它直接开原始 socket:

> "The traffic allowlist constrains only cooperating clients that honor the proxy environment (`HTTPS_PROXY` and the CA variables). A subprocess can ignore those variables and open raw sockets, so the allowlist is defense in depth; destination-bound sentinels remain the primary defense because they survive proxy bypass."
> —— `docs/gateway/secrets.md`

这一整套"哨兵 + 出站代理"设计和上一篇 Hermes 课程里的"网络出口隔离"遥相呼应,但覆盖的具体威胁不同:Hermes 的 squid allowlist 防的是"沙箱内命令能不能连到公网",OpenClaw 这里防的是"即使命令能连到公网,它能不能把真实凭据带出去"——两者可以叠加使用,互不替代。

### 共享密钥库:两种存取模式,一处诚实的警告

OpenClaw 维护一个 Gateway 级、团队作用域的共享密钥库,条目有两种明确区分的访问模式:

> "**Protected secret** (`kind: "secret"`) values are write-only after saving. Gateway list results, the Control UI, and CLI list/get output never include them; there is no reveal RPC.
> **Agent-readable environment** (`kind: "env"`) values remain visible to administrators in the Control UI and can be returned by `store list` and `store get`. ... The agent can print, transmit, or persist these values."
> —— `docs/gateway/secrets.md`

选择用哪一种,取决于运维者是否真的需要 agent 拿到明文——protected secret 从写入之后就没有"读回明文"这条路径,agent-readable env 则是显式承认"这个值会被 agent 看到,agent 可能会把它打印、转发或持久化"。这个二分法把"要不要让 agent 碰到明文"变成了一个显式的、每条目独立的决策,而不是一刀切。

密钥库本身的存储安全等级,文档也没有回避:

> "Store values are not encrypted at rest. They are stored unencrypted in the shared state SQLite database (`state/openclaw.sqlite`), protected by the same `0600` file and `0700` directory permissions as other credentials in that database. Operators who need stronger storage isolation should use an external exec provider such as the 1Password plugin or Vault SecretRefs."
> —— `docs/gateway/secrets.md`

对存储隔离等级要求更高的场景,答案不是"信任这个 SQLite 文件的权限位",而是直接把凭据托管转给外部密钥管理器,通过 `exec` provider 接入。

### 认证凭据的语义模型:token 的生命周期与 OAuth 的排除

`docs/auth-credential-semantics.md` 补上了另一块拼图——模型提供商认证凭据(token/api_key/oauth)自己的资格判定规则。Token 类凭据的过期校验非常具体:

> "1. A token profile is ineligible when both `token` and `tokenRef` are absent (`missing_credential`).
> 2. `expires` is optional. When present it must be a finite number of Unix epoch milliseconds greater than `0` and no larger than the maximum JavaScript `Date` timestamp.
> ...
> 4. If `expires` is in the past, the profile is ineligible with `expired`.
> 5. `tokenRef` does not bypass `expires` validation."
> —— `docs/auth-credential-semantics.md`

第 5 条值得注意:即使凭据本身是通过 `tokenRef`(而不是内联明文)配置的,过期校验依然照常执行——SecretRef 化不会让一个已经过期的 token 绕过有效期检查。

更值得关注的是一条专门针对 OAuth 材料的守卫规则,它解释了为什么 OAuth 凭据不能简单地塞进 SecretRef:

> "SecretRef input is for static credentials only. OAuth credentials are runtime-mutable (refresh flows persist rotated tokens), so SecretRef-backed OAuth material would split mutable state across stores.
> - If a profile credential is `type: "oauth"`, SecretRef objects are rejected for any credential material field on that profile.
> - Violations are hard failures (thrown errors) in startup/reload secret preparation and profile resolution paths."
> —— `docs/auth-credential-semantics.md`

这条规则的逻辑很清楚:SecretRef 假设的是"这个值由外部系统管理、OpenClaw 只读取它",而 OAuth 的 refresh token 会在运行时被 OpenClaw 自己重写(刷新流程会持久化新的 token)。如果允许 OAuth 材料走 SecretRef,就会出现"可变状态被拆分到两个各自认为自己是权威来源的存储"这种一致性风险,所以系统直接把这种组合当作硬性错误拒绝,而不是尝试兼容。

个人模型账号(Settings → Profile → Connected accounts 里连接的账号)则有独立的隔离边界:

> "Accounts connected from Settings → Profile → Connected accounts have an identity-scoped owner in the shared state database. Their credentials and usage state never enter shared or agent-local auth stores, external CLI mirrors, or global runtime snapshots. A runtime loads at most the one personal credential selected by its session."
> —— `docs/auth-credential-semantics.md`

这条边界保证了"用自己的账号登录连接"这件事不会意外把个人凭据泄漏进团队共享的凭据存储或者另一个人的会话里。

### Audit:元数据留痕,不是授权证据

回到开篇引用的那条 `AGENTS.md` 规则——"Its opt-in provenance is never authorization"。要理解这句话的分量,需要先看清楚审计账本到底记录了什么、不记录什么。

先看"不记录什么",这是审计系统隐私模型的基石:

> "The ledger stores identity, ordering, provenance, action, status, and normalized outcome codes. It never stores prompts, message bodies, tool arguments, tool results, attachments, filenames, URLs, command output, or raw error text."
> —— `docs/gateway/audit.md`

再看"opt-in"这个词的具体含义——执行身份记录默认是关闭的,即使是全新安装或升级后的实例:

> "Execution identity recording is off by default, including on fresh installs and upgrades. Enable it explicitly, then restart the Gateway."
> —— `docs/gateway/audit.md`

这份记录即便开启,持久化本身也是尽力而为、允许丢失的:

> "Persistence remains best-effort. Queue saturation, storage failure, shutdown timeout, and process crashes can lose evidence; they log only a bounded operational warning and never abort the run."
> —— `docs/gateway/audit.md`

这就是"opt-in provenance 永远不是授权"这句规则的第一层含义:这份记录连"完整性"都不保证,自然也不可能被下游逻辑当作"这个操作已经被批准过"的证明。文档在 Coverage and proof limits 一节把这一点讲得更彻底:

> "**Absence of a row proves nothing.** Pre-admission inbound drops, sends from plugin-local or direct-send paths that bypass shared durable delivery, a dropped admission envelope, and crash-lost queued work can leave no record."
> —— `docs/gateway/audit.md`

这句话的推论同样重要——**存在一行记录**同样不能被过度解读。文档专门定义了"`enforced`"这个标签的严格触发条件,只有当审批人/策略真正改变了结果、且执行上下文三元组(context/execution/run)完整校验通过时才会打上这个标签:

> "`enforced` receipt coverage is diagnostic, not authority: emit it only when the owner changed the outcome and the exact context/execution/run tuple validates. ... Stale, released, replaced, or throwing authority emits no receipt, not `unknown`."
> —— `docs/gateway/audit.md`

即使是终态的人工批准记录(operator approvals),它的角色也是被审计系统**读取**而不是**替代**的权威来源:

> "Terminal operator approvals are a separate authoritative source. Run inspection adapts their existing first-answer-wins rows directly into decision receipts; it does not copy approvals into the audit ledger or the generic decision-fact table."
> —— `docs/gateway/audit.md`

这句话划清了一条关键边界:批准记录本身(`operator_approvals` 表)才是那个"这件事被谁批准了"的权威数据源,审计系统只是把它**投影**成一份对外展示的收据,从不把它复制一份变成审计账本自己的记录——这样即使审计管线出了 bug,也不会污染批准记录本身的权威性。

隐私模型这边,消息级审计默认关闭,即使开启也用installation-local 的 HMAC 伪名而不是原始平台标识符:

> "Account, conversation, message, and target identifiers, when correlation is available, are exported only as installation-local keyed pseudonyms (`hmac-sha256:v1:<keyId>:<digest>`). ... This is **correlation, not anonymization**: anyone with read access to the state database also has the key and can test candidate raw identifiers against the pseudonyms."
> —— `docs/gateway/audit.md`

"correlation, not anonymization"这句话再次体现了整套文档一以贯之的诚实风格——伪名化只能让同一份数据里的记录彼此关联,不能真正阻止一个拥有数据库读权限的人反推出原始身份。

留存策略上,记录被限定在 30 天窗口和行数上限内,过期即清理:

> "Queries never return records older than 30 days, and the ledger is capped at 100,000 rows; expired rows are pruned during startup, hourly maintenance, and later writes."
> —— `docs/gateway/audit.md`

文档最后把这份记录的定位钉死——它是运维诊断工具,不是合规档案,如果需要不丢数据的完整记录,应该用外部系统承接:

> "This ledger supports debugging and operational review. It is not a lossless compliance archive; if you need one, use an external system fed by OpenTelemetry or channel-level tooling."
> —— `docs/gateway/audit.md`

`AGENTS.md` 那条批注要求的"changes to collection, reader scope, retained fields, bounds, or contracts require approval",正是因为这套系统的每一个参数(采集范围、读取权限、保留字段、留存窗口)都直接决定了它作为"运维诊断证据"这个定位是否成立——放宽任何一项都可能让使用者误以为自己拿到了一份比实际更完整、更权威的记录。

## 常见问题/易踩坑

- **不要把"配置了 SecretRef"等同于"这个凭据安全了"**——只要有支持的凭据类型没迁移完,或者磁盘上还留着旧的明文残留(`openclaw.json` 备份、`.env`、退役的 auth-profile JSON、生成的 `models.json`),agent 只要有文件读权限依然能读到明文。判定迁移完成的标准是四条一起满足,尤其是 `openclaw secrets audit --check` 必须干净。
- **OAuth 凭据不能塞进 SecretRef**——因为刷新流程会在运行时改写 token,这会导致可变状态被拆分到两个都自认为权威的存储里,系统会直接把这种配置组合当作硬失败拒绝,而不是静默兼容。
- **密钥出站代理的目标主机绑定不是万能的**——它防不住一个被绑定的合法服务把凭据明文回显给 agent,也防不住 DNS 层面的劫持,更防不住不遵守代理环境变量、直接开原始 socket 的子进程。
- **审计记录里"存在一行"和"不存在一行"都不能直接当结论**——存在一行不代表这个操作被授权过(`enforced` 有严格的触发条件),不存在一行也不代表这个操作没发生过(记录管道本身允许丢失)。
- **`operator_approvals` 才是权威的批准记录,审计账本只是它的一份对外收据**——不要把两者的角色搞反,审计系统从不把批准记录复制进自己的表。

## 小结

这一篇把凭据管理和审计留痕这两套机制的"能做什么、不能做什么"讲清楚了。SecretRef 消除的是配置文件里的明文残留,靠出站哨兵和密钥出站代理进一步压缩凭据以明文形式流经调用链的窗口,但从头到尾都不构成进程隔离——一个能读文件的 agent,读到的东西取决于磁盘上到底还留没留明文,而不取决于配置里写没写 SecretRef。审计系统的设计哲学同样克制:它记录元数据、拒绝记录内容,默认关闭执行身份采集,持久化允许尽力而为地丢失,"存在一行记录"和"不存在一行记录"都不能被过度解读为结论。这两套机制共享同一句潜台词——文档不断提醒使用者,任何留痕、任何引用、任何绑定,都不能被下游逻辑当成一个比它实际提供的保证更强的凭证。下一章要从安全与沙箱转向另一个方向:自动化与生态——Cron 定时任务、工作流看板,以及 ClawHub 插件市场如何让 OpenClaw 的能力边界继续向外扩展。
