# pnpm Workspace 与目录地图

> OpenClaw 是这套课程系列里规模最大的一个项目:`src/` 下 77 个子目录、光是 `src/gateway` 一个目录就有 2639 个文件;`extensions/` 下挂着 155 个可插拔插件;`packages/` 里是 23 个共享库;`scripts/` 目录堆着 1285 个自动化脚本文件。面对这样的体量,第一件要做的事不是打开某个源文件,而是先读懂 `pnpm-workspace.yaml`——这份配置文件不仅圈定了"仓库里哪些目录是真正的构建/发布单元",还在几乎没人注意的 `minimumReleaseAge` 字段里,藏着一整套供应链安全实践。读懂这份配置,再看清顶层目录怎么分工,才有资格谈后面的 Gateway、Agent、Provider。

## 学习目标

- 通过 `pnpm-workspace.yaml` 的 `packages:` 字段,理解 OpenClaw 的 workspace 边界只有 `.`、`ui`、`packages/*`、`extensions/*`、`examples/*` 五类,而不是把 `src/`、`apps/` 也当成扁平的包目录。
- 理解 `minimumReleaseAge`(依赖冷却期)、`minimumReleaseAgeExclude`(带失效日期的例外清单)、`allowBuilds`(安装脚本白名单)这几个不常见但极其实用的供应链安全配置项分别在防什么风险。
- 建立一张"运行时核心 / 共享库 / 可插拔生态 / 内置技能 / 多端 App / Web UI / 工程自动化"七个簇的顶层目录地图,而不是死记硬背几十个目录名。
- 能用具体数字(155 个 extensions、23 个 packages、77 个 src 子目录、1285 个脚本文件)去描述这个仓库的体量构成,而不是凭印象说"很大"。

## 背景与设计动机

一个日更迭代、有上百个第三方插件生态、还要同时给 TypeScript 后端和四个原生客户端(macOS、iOS、Android、Linux)供货的项目,面临的第一个工程问题往往不是"怎么写代码",而是"怎么防止依赖链变成攻击面"。npm 生态里一个包被劫持、恶意版本发布几小时内就被大量项目自动拉取安装的供应链攻击并不罕见;而 OpenClaw 这种要连接几十个模型供应商、上百个消息 channel、还要执行 shell/浏览器/文件系统操作的 Agent Harness,一旦某个深层传递依赖被投毒,后果不是"页面样式错了",而是"运行在用户设备上的进程被远程控制"。

`pnpm-workspace.yaml` 因此不只是一份 monorepo 的成员声明,它同时承担了依赖治理的策略文件角色:哪些目录参与构建、新发布的包要等多久才允许被安装、哪些依赖版本被强制锁定、哪个包的安装脚本被允许执行——这些规则全部写在同一份 YAML 里,和 workspace 成员声明平级。

## 核心机制详解

### workspace 成员边界

根 `pnpm-workspace.yaml` 的 `packages:` 字段只列出了五类目录:

```yaml
packages:
  - .
  - ui
  - packages/*
  - extensions/*
  - examples/*
```

逐项拆解:

- **`.`**:仓库根目录本身作为一个 workspace 成员,对应根 `package.json`(`name: "openclaw"`)——这也是 CLI 包和绝大多数运行时源码(`src/**`)的归属包,`src/` 不是独立的 workspace 成员,而是根包内部的源码树。
- **`ui`**:Control UI(Web 控制台)独立成一个 workspace 成员,拥有自己的 `package.json`、`vite.config.ts`、`vitest.config.ts`,构建产物再由根包的 CLI 消费。
- **`packages/*`**:一级 glob,`packages/` 下每一个直接子目录本身就是一个可发布的共享库,不像 DeepSeek Harness 那样有"一级分类目录 + 二级叶子包"的两层结构——OpenClaw 的 `packages/` 目前只有 23 个,规模决定了不需要额外的一层分类。
- **`extensions/*`**:155 个可动态启用/停用的 bundled 插件,每个子目录是一个独立包。
- **`examples/*`**:示例项目。

`apps/`(四个原生 App 加共享 Swift 包)、`skills/`(52 个内置 Agent Skill)、`scripts/`(1285 个自动化脚本)都不在 workspace `packages:` 列表里——它们要么是完全独立的原生构建体系(Xcode/Gradle/Cargo-Tauri),要么是不参与 npm 依赖解析的纯脚本或数据文件目录。这本身就是一条有用的判断规则:**判断一个目录是不是"包",先看它有没有出现在 `pnpm-workspace.yaml` 的 `packages:` 里,而不是看它有没有 `package.json`**。

### 依赖冷却期:`minimumReleaseAge`

紧接着 workspace 声明之后,是一段大多数前端项目里根本不会出现的配置:

```yaml
minimumReleaseAge: 10080
minimumReleaseAgeStrict: true

# Trusted Codex runtimes are outside the dependency cooldown.
minimumReleaseAgeExclude:
  # Reviewed Proxyline Bun runtime fix; remove after 2026-09-13 20:51 UTC.
  - "@openclaw/proxyline@0.3.11"
  # GHSA-vp8m-p9jh-q5pm / GHSA-w293-vg96-wgc3 security fixes; remove after 2026-09-12.
  - "undici@8.10.2"
  - "undici@7.29.1"
  ...
```

`10080` 是分钟数,换算下来正好是 7 天——即 pnpm 安装依赖时,任何在 npm registry 上发布不满 7 天的版本一律被拒绝拉取,`minimumReleaseAgeStrict: true` 让这条规则没有隐藏的豁免路径。这是一条对抗"新发布即劫持"供应链攻击的实用规则:恶意维护者账号或投毒发布往往在数小时到几天内就会被社区或安全团队发现并从 registry 撤下,给依赖版本设一个强制冷却期,相当于让整条依赖链自动错开了这个高风险窗口,而不需要人工盯防每一次上游发布。

但严格的冷却期必然会挡住"我们刚确认过这是一个安全修复,但它发布还不到 7 天"这种合法诉求,`minimumReleaseAgeExclude` 就是这条规则的显式逃生舱:它不是简单的白名单,而是**带失效期注释的白名单**——每一条例外都在紧邻的注释里写清楚"为什么被排除"(GHSA 编号、审查过的运行时修复)以及"什么时候应该移除这条例外"(`remove after 2026-09-13 20:51 UTC` 这类精确到分钟的时间戳)。这把"临时开一个口子"变成了一件有明确到期时间、有人要负责回来关闭的事情,而不是一条被遗忘在配置里、逐渐失去审查意义的永久豁免。

同一份配置里还有一处补充说明——`Trusted Codex runtimes are outside the dependency cooldown`,意味着这套冷却机制本身也分信任等级:对于项目自己审查、发布节奏可控的运行时依赖,规则允许单独松绑,而不是让整条依赖树共用一个统一的冷却窗口。

### 安装脚本白名单:`allowBuilds`

供应链攻击的另一个常见入口是 npm 包的安装脚本(`postinstall` 等)——它们在 `pnpm install` 期间以当前用户权限直接执行任意代码。`pnpm-workspace.yaml` 的 `allowBuilds` 字段把"哪些包允许运行安装脚本"变成一份显式清单:

```yaml
allowBuilds:
  "@google/genai": true
  "@lydell/node-pty": true
  baileys: true
  authenticate-pam: true
  "@discordjs/opus": false
  esbuild: true
  koffi: false
  tree-sitter-bash: false
  openclaw: true
  ...
```

值得注意的是,清单里不仅有 `true`,还有显式的 `false`——`@discordjs/opus`、`koffi`、`tree-sitter-bash` 这几个包即使触发了 pnpm 的安装脚本请求,也被明确拒绝执行。这比"默认允许、出问题再拉黑"的策略更严格:pnpm 默认会阻止新依赖运行安装脚本直到显式批准,而 OpenClaw 把这份批准结果提交进了版本控制,使得"这个包为什么被允许/拒绝执行安装脚本"变成一条可审查、可追溯的记录,而不是每个开发者本地一次性点掉的确认弹窗。

### 版本覆盖与依赖替换:`overrides`

`overrides` 字段处理的是传递依赖(dependency of a dependency)层面的问题——某个直接依赖锁定了一个有漏洞的旧版本子依赖,但上游还没发新版:

```yaml
overrides:
  "@lancedb/lancedb>@huggingface/transformers": "-"
  "baileys>sharp": "-"
  axios: 1.19.0
  fast-uri: 4.1.4
  request: "npm:@cypress/request@4.0.1"
  node-domexception: "npm:@nolyfill/domexception@1.0.28"
  "werift-ice@0.2.2>ip": "npm:neoip@3.1.0"
  ...
```

这里能看到两类操作:一类是把某个传递依赖版本强制钉死(`axios: 1.19.0`),另一类更彻底——直接把一个不再维护或有已知问题的包换成社区维护的替代实现(`request` 换成 `@cypress/request`,`ip` 换成 `neoip`)。`"-"` 这种写法则是把某个可选的传递依赖直接置空,常见于原生编译依赖(`sharp`、`@huggingface/transformers`)只在特定场景下才需要、默认不希望被拉入安装闭包的情况。

### `patchedDependencies` 与安装策略微调

```yaml
patchedDependencies:
  "@awesome.me/webawesome@3.12.0": patches/@awesome.me__webawesome@3.12.0.patch
  "matrix-js-sdk@42.2.0": patches/matrix-js-sdk@42.2.0.patch
  vitest@5.0.0: patches/vitest@5.0.0.patch

nodeLinker: isolated
verifyDepsBeforeRun: false
blockExoticSubdeps: true
```

`patchedDependencies` 是 pnpm 的补丁机制——当上游库有一个已知问题但还没发布修复版本时,项目可以直接对 `node_modules` 里的那个包打一个本地 diff 补丁并提交进仓库,而不必等待上游发版或 fork 整个包。`nodeLinker: isolated` 是安装性能优化,让 pnpm 复用整包级别的 APFS clone 而不是逐文件建立硬链接。`verifyDepsBeforeRun: false` 配合注释"GWTs(Git Worktrees)share node_modules; script commands must not reconcile that shared install"说明了一个实际的多 worktree 协作场景:当多个任务共享同一份 `node_modules` 时,不应该让每次运行脚本都触发一次依赖一致性检查,否则并行工作的 worktree 之间会互相踩踏。`blockExoticSubdeps: true` 则是拒绝"非常规"的子依赖解析路径,进一步收紧依赖树的形状可预测性。

### 顶层目录地图:七个簇

理解了 workspace 边界和依赖治理策略之后,再看顶层目录就有了分类的坐标系。OpenClaw 仓库根目录下的几十个顶层条目,可以归纳成七个职责簇:

**运行时核心 —— `src/`**:77 个子目录,是整个项目的主运行时。体量最大的是 `src/gateway`,单这一个目录就有 2639 个文件,是下一章要专门展开的主题。其余子目录按领域划分,例如 `src/agents`(Agent 生命周期)、`src/channels`(消息通道适配)、`src/sessions`(会话状态)、`src/plugins`/`src/plugin-sdk`(插件加载与 SDK 定义)、`src/security`、`src/sandbox`(沙箱)、`src/mcp`(MCP 客户端桥接)、`src/tui`(终端界面)等,每个目录都有自己的 `AGENTS.md` 治理规则。

**共享库 —— `packages/`**:23 个包,是被 `src/`、`extensions/`、原生 App 共同依赖的基础设施层,例如 `@openclaw/gateway-protocol`(协议 schema 与校验器,详见本章第 4 篇)、`@openclaw/plugin-sdk`(插件开发套件)、`@openclaw/llm-core`、`@openclaw/agent-core`、`@openclaw/retry`、`@openclaw/terminal-core`、`@openclaw/tool-call-repair` 等——从包名基本能猜出各自的职责边界。

**可插拔生态 —— `extensions/`**:155 个 bundled 插件,`extensions/AGENTS.md` 明确写着"Treat it as the same boundary that third-party plugins see"——也就是说,bundled 插件和外部开发者发布的第三方插件走的是同一套 `openclaw/plugin-sdk/*` 公共契约,不允许深挖 `src/**` 内部实现。这 155 个插件大致可以再分几类:模型供应商适配(`anthropic`、`amazon-bedrock`、`deepseek`、`google`、`openai`、`xai`、`qwen`、`zai`……)、消息渠道(`slack`、`telegram`、`discord`、`whatsapp`、`signal`、`feishu`、`teams-meetings`、`zoom-meetings`……)、语音与媒体生成(`elevenlabs`、`deepgram`、`azure-speech`、`runway`、`pixverse`、`fal`……)、可观测性(`diagnostics-otel`、`diagnostics-prometheus`)、以及浏览器/文档/云沙箱一类的工具能力(`browser`、`document-extract`、`crabbox`、`e2b` 风格的 `cua-computer`、`beam`)。

**内置技能 —— `skills/`**:52 个 Agent Skill,和 `extensions/` 的插件是两个不同的概念——Skill 更接近"一份可被模型按需读取的文件化能力说明"(例如 `skills/github`、`skills/notion`、`skills/obsidian`、`skills/tmux`、`skills/spotify-player`、`skills/weather`),而不是需要运行时注册服务契约的插件。

**多端 App —— `apps/`**:`android`(Gradle/Kotlin)、`ios`(Xcode/Swift)、`macos`(Swift Package)、`macos-mlx-tts`(独立的 Swift Package,MLX 本地语音合成)、`linux`(`src-tauri`,即 Tauri 桌面壳)、`shared`(`OpenClawKit`、`OpenClawMLXTTSProtocol`、`OpenClawWatchRTC` 等跨 App 复用的 Swift 包)、`swabble`(独立 Swift Package)、`mobile`(目前只有一个 `version.json`,更像是移动端版本号的元信息占位)。这些目录完全在 npm workspace 之外,各自用原生工具链构建,只在协议层与 `src/`、`packages/gateway-protocol` 打交道——这正是第 4 篇要讲的协议代码生成链路存在的原因。

**Web UI —— `ui/`**:Control UI,独立 workspace 成员,不和 `src/` 共用构建配置。

**工程自动化 —— `scripts/`**:1285 个文件,数量上远超 `packages/` 里所有包的源码文件总和,直接说明了这个项目工程自动化程度之高——发布、CI、依赖审计、协议代码生成、文档同步、原生构建胶水脚本全部沉淀在这里,子目录按用途分类(`cloudflare`、`docker`、`docs-i18n`、`e2e`、`github`、`k8s`、`mantis`、`pre-commit`、`qa`、`secrets`、`systemd` 等),后面几篇会陆续用到其中具体的脚本作为证据。

## 常见问题/易踩坑

- **不要把 `src/` 或 `apps/` 当成 workspace 包目录去猜依赖解析规则**:只有 `pnpm-workspace.yaml` 里 `packages:` 列出的五类(`.`、`ui`、`packages/*`、`extensions/*`、`examples/*`)才参与 pnpm 的依赖图,`src/` 的代码全部挂在根包名下,`apps/` 下的原生工程完全走各自的工具链,不受 pnpm 依赖解析约束。
- **`minimumReleaseAgeExclude` 不是"发现麻烦就加一条绕过"**:每条例外都要求写明原因(GHSA 编号、审查记录)和失效时间戳,这是配置文件里的活文档,不是一次性开关。
- **`allowBuilds` 里的 `false` 是显式拒绝,不是"未配置"**:`@discordjs/opus: false` 这类条目和完全不出现在清单里含义不同——后者会被 pnpm 的默认拦截策略挡下并提示,前者是项目主动做出的"永久拒绝"决定。

## 小结

OpenClaw 的 `pnpm-workspace.yaml` 同时回答了两个问题:"仓库里哪些目录是真正的构建单元"和"依赖链上的风险要怎么被系统性地管住"——依赖冷却期、安装脚本白名单、版本覆盖、补丁机制,四件事全部沉淀在同一份配置文件里,而不是散落在人工审查习惯中。在这份边界之上,`src/`(运行时核心)、`packages/`(共享库)、`extensions/`(可插拔生态)、`skills/`(内置技能)、`apps/`(多端 App)、`ui/`(Web UI)、`scripts/`(工程自动化)七个簇分别承担不同职责,构成了这个体量庞大的仓库的整体地图。下一篇会深入其中一条贯穿全仓库的规则——`openclaw doctor --fix` 与配置/状态的兼容性契约,看看运行时代码是如何被从"永远兼容旧配置"这件事里解放出来的。
