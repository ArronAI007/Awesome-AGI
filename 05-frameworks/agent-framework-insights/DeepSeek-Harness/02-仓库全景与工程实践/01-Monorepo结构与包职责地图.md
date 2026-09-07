# Monorepo 结构与包职责地图

> DeepSeek Harness 的源码仓库不是一个"大项目里塞了很多文件夹",而是一个刻意设计成 **219 个可独立发布叶子包** 的能力矩阵——`packages/` 下 49 个一级目录只是"能力领域"的分类标签,真正的构建单元、发布单元、依赖单元永远是二级目录里的那个叶子包。理解这套两级目录的设计意图,是读懂整个仓库其余部分(构建体系、测试体系、供应链治理)的前提。

## 学习目标

- 通过 `pnpm-workspace.yaml` 的 `packages:` 字段,理解仓库把哪些顶层目录纳入了 workspace,以及每个顶层目录各自的角色。
- 搞清楚 `packages/` 下"一级分类目录 + 二级可发布叶子包"两级结构为什么这样设计,而不是把 219 个包直接摊平在 `packages/` 下。
- 建立一张从 `apps/cli` 入口,经过 `packages/bundle/*` 组合层,一路下钻到具体能力叶子包的"整体地图"。
- 认识 `vendor/`、`native/`、`python/`、`website`、`examples` 这几个特殊顶层目录各自承担的非常规角色。
- 能够看着任意一个 `@deepseek-ai/dsh-*` 包名,推断出它大致属于哪个能力领域、扮演什么角色(抽象座 / 本地实现 / 模型工具 / UI 插件)。

## 背景与设计动机

如果把 DeepSeek Harness 的全部代码塞进几十个"大包"——比如一个 `core`、一个 `tools`、一个 `client`——会发生什么?任何一次修改都会牵连一个体积巨大的包的重新构建、重新发布、重新做兼容性判断;想单独替换"会话持久化用 SQLite 还是 JSONL"这种实现细节,也没有清晰的边界可以替换。反过来,如果把 219 个包全部摊平在 `packages/` 下,人在 `ls packages/` 的时候会看到一堵无从下手的名字墙——`dsh-fs`、`dsh-fs-local`、`dsh-fs-sandbox`、`dsh-tool-fs`、`dsh-tool-fs-search`……这些名字之间的关系只能靠字符串前缀去猜。

这个仓库选择的答案是**两级目录**:一级目录(如 `fs/`、`shell/`、`subagent/`)是纯粹的"能力领域"分组,不参与构建、不对应发布单元,只是让人和工具能够按领域浏览;二级目录(如 `fs/fs`、`fs/fs-local`、`fs/tool-fs`)才是真正的 npm 包,拥有自己的 `package.json`、`tsconfig.json`、独立的版本号和发布边界。这背后是一条贯穿全仓库的架构原则——**能力座(abstract seam)与实现(provider)分离**:几乎每个领域都会看到一个不带后缀的抽象包(`dsh-fs`、`dsh-shell`、`dsh-sandbox`)定义 `ctx.fs`、`ctx.shell` 这类 Cordis 服务契约,再由若干个 `-local`、`-sandbox`、`-e2b` 后缀的包提供具体实现,外加 `tool-*` 前缀的包把能力座包装成模型可调用的工具。二级目录的颗粒度,直接决定了这条"座 / 实现 / 工具"三层结构能不能被讲清楚。

## 核心机制详解

### 顶层 workspace 边界:`pnpm-workspace.yaml`

仓库的 workspace 成员由根 `pnpm-workspace.yaml` 的 `packages:` 字段精确定义:

```yaml
# pnpm-workspace.yaml
packages:
  - vendor/*
  - packages/*/*
  # The Landlock launcher is developed with its harness consumers but keeps
  # its native build and publication scripts under native/landlock-run.
  - native/landlock-run
  - native/landlock-run/packages/*
  # Product assemblies over the package tier; apps/cli owns the `dsh` bin.
  - apps/*
  - website
  # The runnable demo leaves join as ONE workspace member: examples/package.json
  # declares the union of every leaf's cordis.yml plugins as workspace:*, so a
  # plain-node (`:lib`) boot of any leaf (examples/<leaf>/cordis.yml) resolves its
  # plugins through real package `exports`→lib by walking up to examples/node_modules.
  # Members for DEPENDENCY RESOLUTION only — NOT build targets: tsdown's explicit
  # globs (vendor/*, packages/*/*) exclude them.
  - examples
  # Deploy root of the single-exe build: a pure dependency manifest whose
  # closure is what the exe bundles and what the Python runtime distributes.
  - python/sdk-runtime
```

逐行拆解:

- **`vendor/*`**:vendored 进仓库的 Cordis 框架及其生态库(第 04 篇详细展开),每个子目录是一个独立包。
- **`packages/*/*`**:这才是本篇的主角——两级 glob,一级目录本身不是 workspace 成员,只有二级目录才是。
- **`native/landlock-run` 及其 `packages/*`**:Linux 沙箱后端 Landlock 的原生启动器,单独维护自己的原生构建和发布脚本,但作为 harness 的消费者之一被纳入同一个 workspace 以共享依赖解析。
- **`apps/*`**:产品层——真正被人安装、运行的东西,组装在包这一层之上。
- **`website`**:文档站点(VitePress),独立成员。
- **`examples`**:注释写得很直白——这个成员**只用于依赖解析,不是构建目标**。`examples/package.json` 把每个 demo 叶子包的 `cordis.yml` 里声明的插件全部列成 `workspace:*` 依赖,这样任何一个 demo 用纯 Node(`:lib` 模式)启动时,可以通过真实的包 `exports` 字段解析到构建产物 `lib/`,而不需要额外的模块解析黑魔法。tsdown 的构建 glob(`vendor/*`、`packages/*/*`)明确不包含它。
- **`python/sdk-runtime`**:单文件可执行构建的部署根——它本身只是一份纯依赖清单,`pnpm deploy` 据此产出的依赖闭包既是可执行文件打包的内容,也是 Python SDK 运行时分发的内容。

`linkWorkspacePackages: true` 配合 `overrides` 把 vendored 的 `@deepseek-ai/cosmokit`、`@deepseek-ai/schemastery` 强制链接回 `vendor/*` 下的本地源码,这一点第 04 篇会专门讲。

### 两级目录:一级分类,二级发布单元

用 `find packages -mindepth 2 -maxdepth 2 -type d | wc -l` 数出来的真实数字是 **219** 个叶子包,分布在 **49** 个一级分类目录下。下表是完整的"分类目录 → 一句话职责"地图(职责描述综合自各分类目录下叶子包 `package.json` 的 `description` 字段):

| 分类目录 | 一句话职责 |
|---|---|
| `acp` | Agent Client Protocol 自动化服务器,驱动 harness agent 走 JSON-RPC stdio |
| `api` | Typert 生成的 Remote 网关分发器与 Client API 端点、Remote BFF 组装 |
| `attachment` | 附件的抽象存储座与本地内容寻址实现 |
| `boot` | 启动期公共胶水:.env 加载、Loader 引导序列、命令行参数交接 |
| `bundle` | 三种可发布的整机组合:`base`(核心插件层)、`headless`(无 Host 一次性)、`web-app`(浏览器面) |
| `client` | Web 前端的 40+ 个叶子包:运行时、UI 插件、Slot 系统、连接层、主题 |
| `code-runtime` | 代码执行能力座及其 worker_thread 实现 |
| `compaction` | 会话压缩策略、LLM 摘要后端、工具结果裁剪、`/compact` 命令 |
| `context` | AGENTS.md/CLAUDE.md 加载、时间上下文、tmux 上下文、跨会话引用 |
| `core` | Agent 接口与注册表、Session 事件溯源存储、Tools 执行管线、System Prompt 组装 |
| `credentials` | 凭证抽象座与本地 `.env` 实现 |
| `e2b` | E2B 云沙箱的生命周期管理及 fs/subprocess 适配 |
| `examples` | 可运行 demo:ACP、agent-spine、JSON-RPC SDK |
| `extensions` | 模型可动态挂载/卸载的 Cordis 插件运行时("code mode"沙箱) |
| `feedback` | 会话/消息反馈的记录服务与斜杠命令 |
| `fs` | 文件系统能力座、观察策略、沙箱围栏、glob/grep 与 read/write/edit 模型工具 |
| `goal` | 同会话目标的事件溯源状态、执行时权限校验、斜杠命令 |
| `guard` | 重复工具调用提醒、工具调用超时策略 |
| `hooks` | Claude Code / Codex hook 配置在 harness 拦截点上的桥接执行 |
| `host` | Web GUI Host 侧:API 网关、静态资源服务、目录选择器、插件清单 |
| `identity` | 匿名用户 ID(遥测与反馈关联用) |
| `interaction` | 用户提问、用户审批、权限预设、人类命令注册表 |
| `jobs` | 后台任务注册表(进程内实现)及模型侧 job 控制工具 |
| `llm` | 供应商中立的 LLM 服务接口、DeepSeek 适配器、请求重试、Token 计量 |
| `lsp` | 语言服务器能力座、stdio LSP 提供者、模型侧只读 LSP 工具 |
| `mcp` | MCP 客户端桥接:连接 MCP 服务器并把其工具注册进 `ctx.tools` |
| `plan` | Plan Mode:带部署指引的计划模式与用户复核退出 |
| `preset` | 会话级 Agent 组合预设(cordis.yml)与 persona 章节 |
| `runtime-diagnostics` | 包自持有的运行时不变量注册表 |
| `sandbox` | 进程沙箱抽象座及各平台后端:bwrap、Landlock、macOS Seatbelt、Windows ACL |
| `schedule` | Agent 范围内的持久化定时提醒(after/at/fixed-rate) |
| `sdk` | 对外 stdio JSON-RPC SDK:协议、Server 插件、TypeScript 客户端 |
| `session-query` | 会话历史检索(SQLite FTS5 全文搜索)、模型侧查询工具 |
| `session` | 事件溯源持久化后端(JSONL/SQLite)、投影缓存、标题生成、遥测 |
| `settings` | 用户设置能力座与文件后端(settings.yaml) |
| `shell` | bash/pwsh 执行器座、本地/沙箱实现、持久 Bash 工具 |
| `skill` | Agent Skill 提供者注册表及内置 skill(badge、filesystem) |
| `spill` | 超大工具结果的溢出存储座与裁剪策略 |
| `storage` | KV 存储中枢及 schema 校验的领域数据表单 |
| `subagent` | 子代理能力座及七种后端:fork/spawn(进程内)、ACP、Claude Code、Codex、dsh SDK(跨进程) |
| `subprocess` | 托管子进程能力座与本地实现(输出限流、进程组升级击杀) |
| `terminal` | 持久 PTY 会话座及 bash 后端 |
| `test-support` | 测试基建:LLM mock server、回放插件、ACP 快照套件、Loader smoke 工具 |
| `todo` | `todo_write` 模型工具(基于事件溯源会话日志) |
| `typert` | TS 项目分析器、模型驱动的产物生成器/Loader 集成/运行时注册表("Typert") |
| `util` | 零依赖工具原语:原子写入、品牌类型、超时、路径、输出保留 |
| `web` | Web 访问能力座及 search/fetch 各供应商实现(Exa、Perplexity、DeepSeek) |
| `workflow` | 模型编排脚本引擎(worker_thread 执行、桥接回子代理调用) |
| `workspace` | 工作区实体注册表(会话绑定的持久工作区记录) |

这张表里能看出一个反复出现的命名规律,以 `fs` 分类为例展开成真实的叶子包列表就是最好的示范:

```text
packages/fs/
├── fs                       # @deepseek-ai/dsh-fs            —— 抽象能力座:ctx.fs 服务契约
├── fs-local                 # @deepseek-ai/dsh-fs-local       —— 本地文件系统实现
├── fs-observation-policy    # @deepseek-ai/dsh-fs-observation-policy —— 读前写策略
├── fs-sandbox                # @deepseek-ai/dsh-fs-sandbox     —— 沙箱围栏实现
├── tool-fs                  # @deepseek-ai/dsh-tool-fs        —— 模型侧 read/write/edit 工具
├── tool-fs-search           # @deepseek-ai/dsh-tool-fs-search —— 模型侧 glob/grep 工具
└── tool-str-replace-editor  # @deepseek-ai/dsh-tool-str-replace-editor —— 另一种编辑工具变体
```

一级目录 `fs` 把这七个包聚在一起,是因为它们共享同一个业务语境;但它们各自的版本号、`package.json`、构建产物完全独立——`dsh-tool-fs` 可以只依赖抽象的 `dsh-fs`,完全不知道背后跑的是 `dsh-fs-local` 还是 `dsh-fs-sandbox`。这正是"两级目录"设计要保护的边界:**一级目录是给人看的地图,二级目录才是给构建工具、给依赖解析、给发布流程看的真实单元**。

### 从入口到框架层:整体地图

把 `apps/`、`packages/`、`vendor/`、`native/`、`python/` 串起来,可以画出一条从"用户敲下 `dsh`"到"最底层的 Cordis Context"的完整链路:

```text
用户终端 / 浏览器
      │
      ▼
apps/cli  (@deepseek-ai/dsh, bin: dsh → lib/bin.js)
      │  唯一的可执行入口,也承担 `dsh web` 的浏览器 UI 别名
      ▼
packages/bundle/*  (base / headless / web-app)
      │  以 cordis.yml 补丁层的形式组合具体能力包——
      │  base 是每个 profile 的第一层补丁,headless 在其上叠加
      │  "无 Host、无 HTTP、无浏览器"的一次性运行器,web-app 叠加
      │  浏览器面补丁 + 前端 dist 服务 + web 专属系统提示词
      ▼
packages/{core,fs,shell,llm,session,...}/*  (219 个能力叶子包)
      │  能力座(seam)与实现(provider)分离,以 Cordis 插件形式
      │  相互 inject/provide 服务
      ▼
vendor/{cordis,loader,include,...}  (source-vendored 框架层)
      │  Context / Fiber / Loader / Include 等 Cordis 核心机制
      ▼
Node.js runtime
```

`apps/web`(`@deepseek-ai/dsh-web-frontend`)是这条链路上的一个侍从分支:它是"vite build over the `@deepseek-ai/dsh-client-web` shell library"——也就是说浏览器前端的真正实现代码全部在 `packages/client/*` 里,`apps/web` 只是把它 vite 构建成静态资源,交给 `apps/cli` 的 `dsh web` 子命令通过 `packages/host/frontend-static` 提供服务。这也解释了为什么 `packages/client/*` 会有单独的一套 tsconfig 和 tsdown 构建管线——这是第 02 篇的主题。

`native/landlock-run` 和 `python/sdk-runtime` 则是两个"依附但独立"的顶层目录:前者是 Linux 沙箱后端 Landlock 启动器的原生构建产物(有自己的 `docs/`、`scripts/`、`tsconfig.base.json`),被 `packages/sandbox/sandbox-local` 作为其中一种探测到即用的后端;后者不是代码,而是单文件可执行构建的"纯依赖清单",`pnpm deploy` 依据它算出的依赖闭包同时喂给可执行文件打包器和 Python SDK 的运行时分发。

### 219 个包,一个版本号:统一发布策略

两级目录带来了"独立的发布边界",但 DeepSeek Harness 并没有让 219 个叶子包各自演化出互不相同的版本号——抽查几个分布在不同分类目录下的包会发现它们此刻共享同一个版本:

```text
@deepseek-ai/dsh-agent      0.1.0-rc.5
@deepseek-ai/dsh-fs-local   0.1.0-rc.5
@deepseek-ai/dsh-brand      0.1.0-rc.5
```

这不是偶然的巧合,而是 `scripts/release/bump.ts` 里明确写死的发布策略,脚本顶部的注释直接给出了定义:

```typescript
// scripts/release/bump.ts
/**
 * Bump one release family's version and commit it, so the published version is
 * ...
 * The dsh family shares one version across its members and the workspace root:
 * every dsh package and the root manifest publish at the same version (recorded
 * as `0.0.1-rc.1`). The vendored family has one version line per package, but
 * every release advances and publishes the complete family so the next release
 * ...
 */
```

也就是说,仓库里其实活跃着**两条独立的版本线**:根 `package.json`(`@deepseek-ai/dsh-root`)和所有 `@deepseek-ai/dsh-*` 包属于"dsh family",统一共享一个版本号,`pnpm run release:dsh -- <major|minor|patch|x.y.z>` 一次性把这条族群的每个成员和 workspace 根一起推进;`vendor/*` 下的九个包属于"vendored family",各自保留自己的版本号语义(与上游同步时甚至会"倒退"到比当前版本更低的上游版本),但每次发布依然要求这个族群的全部成员一起推进,不允许只发布其中一部分。

这个设计和"两级目录、独立发布边界"并不矛盾,反而是对它的补充:**边界独立**保证的是"某个包可以被单独替换、单独依赖、单独测试覆盖",**版本统一**保证的是"消费者不需要去猜哪个 `dsh-fs` 版本能兼容哪个 `dsh-tool-fs` 版本"——219 个包在任意一个发布时间点上,永远处在同一条时间线上,兼容性问题被从"版本号排列组合"降级成了"这一次发布是否整体可用"。

### 命名空间小结:从包名反推物理位置

结合前面的 `@deepseek-ai/dsh-*` 通配路径映射(第 02 篇会深入讲 `tsconfig.base.json` 里的这套映射),包名到物理目录基本遵循这样的推断顺序:

1. 先看是否命中某个专属映射(比如 `dsh-sdk-client` 实际在 `sdk/client`,`dsh-host-*` 系列在 `host/*`,`dsh-client-*` 系列在 `client/*`)——这类前缀映射通常对应仓库里体量较大的分类目录,为了避免 `@deepseek-ai/dsh-client-ui-cordis` 这种命名被误判到 `client/ui-cordis`(实际物理路径是 `extensions/ui-cordis`),专属映射表要逐一列出例外。
2. 命中不到专属映射时,落到通配规则——去掉 `dsh-` 前缀剩下的名字,在 `core/*`、`llm/*`、`shell/*` 等几十个候选一级目录下按"第一个匹配上的目录名获胜"解析,这也是为什么二级目录名在全仓库范围内必须保证唯一,不能在两个不同分类目录下出现同名叶子包。

## 常见问题/易踩坑

- **不要把一级分类目录当成包**:`packages/fs/package.json` 是不存在的——试图 `import` 或 `pnpm add` 一级目录名会失败,必须精确到叶子包,比如 `@deepseek-ai/dsh-fs`。
- **`examples` 是依赖解析成员,不是构建目标**:如果发现 `examples/*` 下的代码没有被 tsdown 打包进产物,这是设计如此,不是遗漏——它依赖真实的 `exports` → `lib` 解析来验证"发布出去的包能不能被纯 Node 直接跑起来"这件事本身。
- **包名前缀不总能唯一确定所属分类目录**:比如 `dsh-client-ui-cordis` 实际物理路径是 `packages/extensions/ui-cordis`,而不是 `packages/client/ui-cordis`——命名空间(`dsh-client-*`)是给消费者看的产品分组,不等价于物理目录分组;具体实现可参考 `tsconfig.base.json` 里 `@deepseek-ai/dsh-client-*` 一类的路径映射,本文未逐一穷举所有例外。

## 小结

DeepSeek Harness 用"49 个一级分类 + 219 个二级叶子包"的两级目录,把"给人浏览的能力地图"和"给工具消费的发布单元"彻底分离;`apps/`、`vendor/`、`native/`、`python/`、`website`、`examples` 这几个顶层目录则分别承担产品入口、框架层、原生沙箱后端、单文件分发闭包、文档站点、依赖解析验证六种不同但边界清晰的角色。理解这张地图,是继续往下读构建体系、测试体系、供应链治理三篇的基础——它们都是在这张地图上叠加不同维度的工程约束。
