# Vendoring 策略与供应链治理

> 大多数项目对上游框架的态度是"通过 npm 依赖引入,信任维护者,等版本发布再升级";DeepSeek Harness 对 Cordis 框架及其生态选择了完全相反的路径——把源码原样拷进仓库、改名到自己的 scope 下、连本地补丁清单都逐条记录在案。这不是"重新发明轮子",而是一次关于可审计性、可控性与升级节奏的工程权衡。本篇读 `vendor/README.md` 原文,拆解 `pnpm-workspace.yaml` 里 `overrides` + `linkWorkspacePackages` 如何把这套 vendoring 落到依赖解析层面,并讲清楚 `verify-vendored-links` 这类治理脚本存在的意义。

## 学习目标

- 理解"source-vendored"策略解决的具体问题,以及它相对于"npm 依赖 + lockfile 锁版本"这条更常见路径多付出的成本和多换来的控制力。
- 读懂 `vendor/README.md` 里的 manifest 表格结构:目录、npm 包名、上游名、版本、上游仓库、commit hash 五元组分别在治理什么。
- 理解 `pnpm-workspace.yaml` 里 `linkWorkspacePackages: true` 配合 `overrides` 字段如何让"上游 semver 范围"精确解析到"仓库内被锁定的本地源码"。
- 读懂 `scripts/verify-vendored-links.ts` 是怎么用 `pnpm-lock.yaml` 的内容反向验证"没有任何一个 vendored 包偷偷从 registry 装了一份副本"的。
- 建立"vendoring"作为一种工程决策模式的普适认知,知道在什么场景下这个成本值得付。

## 背景与设计动机

如果 DeepSeek Harness 像大多数项目一样,直接在 `package.json` 里写 `"cordis": "^4.0.0-rc.7"`,会失去什么?首先是**审计边界**——框架层的每一次行为都要经过 `node_modules` 里那份不受版本控制的代码,想知道"这个版本到底改了什么"只能翻 CHANGELOG,想验证"这次升级会不会引入某个已知问题"完全依赖上游的发布纪律。其次是**补丁能力**——如果发现框架本身有一个只影响你这个场景的 bug(比如插件卸载时的竞态条件),常规做法只能等上游发新版本,或者用 `patch-package` 这类工具在 `node_modules` 层打运行时补丁,而后者的补丁内容和补丁理由通常不会进代码评审,团队里没人真正知道"我们其实在跑一份被偷偷改过的框架"。第三是**升级节奏**——依赖 npm 版本号意味着升级是"整包接受",没法只挑你需要的那部分改动。

反过来,如果每次都手写一份"我需要的这部分框架逻辑",又会陷入另一个坑:重新发明轮子,而且很可能悄悄偏离上游语义,导致自己的实现和社区认知不一致,后续没人敢碰。

DeepSeek Harness 选择的中间路径是**把上游源码原样拷进仓库**——既不重新实现,也不通过 npm 间接依赖,而是把 Cordis 及其基础库的 `src/` 目录直接作为 workspace 成员纳入代码库,所有本地修改都在一份公开的文档里逐条记录、逐条附上理由。这样"审计"变成了"读一份 markdown 加一份 diff",而不是"翻遍 node_modules 猜测行为";"补丁"变成了正常的代码评审流程;"升级"变成了主动、可控的同步操作,而不是被动接受版本号驱动的变更。

## 核心机制详解

### `vendor/README.md`:策略声明与完整 manifest

`vendor/README.md` 开篇就是策略的完整陈述:

> This directory contains source-vendored copies of the Cordis framework and its foundation libraries. They are copied into this monorepo instead of being depended on via npm, so that the harness fully owns its framework layer (auditable, patchable, pinned).

紧接着解释了为什么要**改名到 `@deepseek-ai` scope**——这不是品牌洁癖,而是发布安全的考量:

> All vendored packages are renamed into the `@deepseek-ai` scope (`cordis` → `@deepseek-ai/cordis`, `@cordisjs/plugin-<x>` → `@deepseek-ai/cordis-plugin-<x>`): every harness package declares `cordis` as a peer dependency, so publishing the harness publishes this framework layer too, and a publication under the upstream names would squat them on the registry.

也就是说:harness 的每个包都把 `cordis` 声明成 peer dependency,一旦发布,这份 vendored 框架层也会跟着一起发布出去;如果不改名,直接用上游的包名发布,就等于在公共 registry 上"抢注"了别人的包名——这是必须避免的供应链事故。

Manifest 表格本身是治理的核心数据结构,九个 vendored 包的每一行都精确记录五个维度:

```markdown
| Directory | npm name | Upstream name | Version | Upstream repo | Commit |
|---|---|---|---|---|---|
| `cosmokit/` | `@deepseek-ai/cosmokit` | `cosmokit` | 1.8.1 | https://github.com/deepseek-harness/cosmokit | `16f6fc058ade66e8ac5da0033d35a8d0f279f544` |
| `schemastery/` | `@deepseek-ai/schemastery` | `schemastery` | 3.18.0 | https://github.com/deepseek-harness/schemastery (`packages/core`) | `e67cee00ad725bd1534aee930a979ea3eec6f698` |
| `cordis/` | `@deepseek-ai/cordis` | `cordis` | 4.0.0-rc.7 | https://github.com/cordiverse/cordis (`packages/core`) | `56b3d4f725681cf4556c1a8695a709cc3b6eed74` |
| `loader/` | `@deepseek-ai/cordis-plugin-loader` | `@cordisjs/plugin-loader` | 1.0.0-rc.5 | ... | `56b3d4f725681cf4556c1a8695a709cc3b6eed74` |
| ... | | | | | |
```

`Directory` 是仓库内的物理路径,`npm name` 是发布出去的名字,`Upstream name` 是原始社区包名,`Version`/`Commit` 精确到"这份代码等价于上游哪一个具体提交"——不是"大约是 4.0 版本",而是可以拿这个 commit hash 去上游仓库对比出精确 diff 的程度。README 同时列出了哪些第三方依赖**没有**被 vendor(比如 `@standard-schema/spec`、`js-yaml`、`chokidar` 继续走 npm),以及哪些上游包"验证过未被使用,故意不 vendor"(比如 `reggol`、`@cordisjs/utils`)——这说明 vendoring 范围本身是经过盘点的决策,不是"整个上游 workspace 全抄一份"这种懒惰做法。

### 本地修改日志:每一条偏离都是可审计的

`vendor/README.md` 的"Local modifications"一节要求"exhaustive"——穷举式记录每一条与上游的偏离。这些条目本身就是这套策略价值的最好证明,举两个真实例子:

第 6 条记录了对 `cordis/src/fiber.ts` 的生命周期加固,原文描述得极其具体:

> **`cordis/src/fiber.ts` lifecycle hardening**: locally closes three reentrant disposal gaps. An effect's owner-list wrapper is registered before its setup body runs, so an unload begun from inside setup awaits setup and every collected cleanup; synchronous setup failure removes the wrapper and rolls back collected cleanup. ... Effect creation is rejected while the owner is `UNLOADING` (while `PENDING` and `LOADING` remain legal), preventing cleanup-time registrations from escaping the unload snapshot.

这是一个只有深度理解 Cordis 插件生命周期语义才能发现、也只有拥有源码才能修复的并发正确性问题——如果框架是通过 npm 依赖引入的黑盒,这类修复通常要等上游几个月甚至无限期地排队。

第 11 条记录了对 `include/src/index.ts` 的一处行为差异修复,并明确指出它服务于 harness 自己的一个具体功能(`dsh --dump-config`):

> `applyEntryPatches` also indexes each `insert`ed entry as it is added, so a later patch in the same list can configure or disable a row an earlier patch inserted; upstream built the id index once before the patch loop, leaving inserted rows silently unpatchable. ... Covered by `packages/boot/app-boot/tests/config-reload.spec.ts`.

值得注意的是每一条修改后面几乎都跟着"Covered by ...spec.ts"——本地修改不是裸改代码,而是连测试覆盖都一并记录,治理文档和测试证据是绑定在一起的。

### `pnpm-workspace.yaml`:把策略落到依赖解析层面

策略声明本身不会自动生效,真正让"vendored 源码取代 npm 副本"这件事在依赖解析层面成立的,是根 `pnpm-workspace.yaml` 里两处配合:

```yaml
# pnpm-workspace.yaml
# Vendored framework packages keep their upstream semver ranges, while local
# builds must resolve those matching names to this workspace's pinned sources.
linkWorkspacePackages: true

overrides:
  '@deepseek-ai/cosmokit': 'link:vendor/cosmokit'
  '@deepseek-ai/schemastery': 'link:vendor/schemastery'
```

`linkWorkspacePackages: true` 让 pnpm 优先把满足 semver 范围的依赖解析到 workspace 内的本地包,而不是去 registry 找。`overrides` 则是更强的一层保证——直接把 `@deepseek-ai/cosmokit`、`@deepseek-ai/schemastery` 这两个名字**无条件**重写成 `link:vendor/cosmokit`、`link:vendor/schemastery`,不管声明它们的地方写的 semver 范围是什么。注释里说得很直白:"vendored 框架包保留上游的 semver 范围写法,但本地构建必须把匹配这些名字的依赖解析到这个 workspace 内被钉死的源码"——也就是说,哪怕某个包的 `package.json` 里写着 `"@deepseek-ai/cordis": "^4.0.0-rc.7"` 这样看起来像是指向 npm registry 的版本范围,pnpm 实际解析出来的永远是 `vendor/cordis` 目录下的那份被钉死的源码,不存在"网络另一端某个发布者悄悄推送新版本"的风险。

`vendor/README.md` 里还提到一个容易被忽略的细节:Schemastery 的 `package.json` 额外声明了条件 `exports`(import → `.mjs`,require → `.cjs`),原因是 pnpm 链接的是目录本身,如果没有这份 `exports` 声明,Node 的 ESM 解析器会退回读 `main` 字段从而加载 CJS 入口,而 CJS 入口里的惰性 `require('@deepseek-ai/cosmokit')` 在 vitest 这类会做模块钩子的宿主环境下,可能和 ESM 加载同一个被链接模块产生竞态。这说明"link 到本地目录"本身也带来了新的、需要专门处理的边界情况,不是简单地把 npm 依赖换成本地路径就万事大吉。

### `verify-vendored-links.ts`:反向验证 lockfile 没有背叛策略

光靠配置声明"应该"如何解析还不够——真正的治理动作是有一个自动化脚本,在每次构建前反过来检查 lockfile 的实际解析结果是否遵守了这条策略。`scripts/verify-vendored-links.ts` 做的正是这件事:

```typescript
// scripts/verify-vendored-links.ts
/**
 * Verify that pnpm-lock.yaml resolves every vendored package name to its
 * workspace `link:` — never a registry copy. `linkWorkspacePackages: true`
 * (pnpm-workspace.yaml) makes matching upstream semver ranges resolve to the
 * pinned vendored sources; a registry copy of the same name coexisting with
 * the vendored one silently forks the framework layer (vendor/README.md).
 */

// Importer resolutions: every dependency entry naming a vendored package must
// resolve to a link:, or the build silently uses a registry copy.
for (const [importer, sections] of Object.entries(lockfile.importers ?? {})) {
  for (const [section, dependencies] of Object.entries(sections)) {
    for (const [dependency, entry] of Object.entries(dependencies as Record<string, { version?: string }>)) {
      if (!names.has(dependency)) continue
      const version = entry.version ?? ''
      if (!version.startsWith('link:')) {
        violations.push(`${importer} ${section}.${dependency} resolves to ${JSON.stringify(version)} (expected link:)`)
      }
    }
  }
}

// Package/snapshot keys: a registry copy materializes as a `<name>@<version>`
// key; vendored names must never appear there at all.
for (const section of ['packages', 'snapshots'] as const) {
  for (const key of Object.keys(lockfile[section] ?? {})) {
    const atIndex = key.lastIndexOf('@')
    if (atIndex <= 0) continue
    const packageName = key.slice(0, atIndex)
    if (names.has(packageName)) violations.push(`${section} entry ${key} is a registry copy of a vendored package`)
  }
}
```

这个脚本做了两层独立验证:第一层遍历 `pnpm-lock.yaml` 的 `importers` 部分,确认每一个引用了 vendored 包名的依赖条目,其解析出来的 `version` 字段都以 `link:` 开头——如果不是,说明某个包声明依赖的方式绕开了 `overrides`,实际装的是 registry 上的一份副本。第二层更严格,直接检查 lockfile 顶层的 `packages`/`snapshots` 键——一个 registry 副本会在这里以 `<name>@<version>` 的形式materialize 成一条独立记录,只要 vendored 的包名在这里出现过一次,不管它是否被真正使用,都判定为违规。这条注释点出了不做这层检查会有什么后果:"a registry copy of the same name coexisting with the vendored one silently forks the framework layer"——两份代码同时存在,某些间接依赖悄悄解析到了 registry 副本,团队却还以为全仓库都在用同一份被审计过的框架代码,这种"分叉"是静默发生的,不会有任何报错提示,只有这类脚本能把它揪出来。

这个脚本挂在 `package.json` 的 `hygiene` 聚合脚本里:

```json
"hygiene": "pnpm run rescope-vendor:check && pnpm run knip && pnpm run publint && pnpm run constraints && pnpm run verify-dsh-package-licenses && pnpm run verify-package-invariants && pnpm run verify-built-package-invariants && pnpm run verify-cordis-config && pnpm run verify-node-next-types && pnpm run verify-runtime-closure && pnpm run verify-vendored-links",
```

和 `rescope-vendor:check`(验证改名一致性)、`verify-cordis-config`、`verify-runtime-closure` 等一系列"仓库不变量"检查并列,成为供应链治理这一大类门禁的一部分,而不是孤立存在的脚本。

### 供应链治理的分工:AGENTS.md 里的更新流程

根 `AGENTS.md` 有专门的"Vendoring policy"一节,把更新流程收敛成一句话:

> `vendor/` packages are pinned source copies (manifest with upstream SHAs in [vendor/README.md](vendor/README.md)). Update via the sync procedure there; re-apply or retire the logged local modifications; rerun `pnpm run test && pnpm run build`.

对应 `vendor/README.md` 结尾的"Sync procedure"——记录上游 `git rev-parse HEAD`、拷贝 `src/`、重新应用或废弃本地修改清单里的每一条、更新 manifest 表格的版本号和 commit hash、跑一次完整测试和构建。这是一个刻意设计得"繁琐但可执行"的流程:每一次同步都强制回顾一遍"我们到底改了上游什么、这些改动是否还需要"——而不是简单地 `git pull` 覆盖过去。

### 不止 vendoring:npm 依赖上的另外两道治理手段

Vendoring 只覆盖了 Cordis 生态这一类"完全拥有"的框架层依赖。对于继续走 npm 依赖的第三方库,`pnpm-workspace.yaml` 里还有另外两道供应链治理手段,和 vendoring 形成互补而不是重复。

第一道是 **`patchedDependencies`**——对不打算整份 vendor、但确实需要改一行行为的第三方库,用 pnpm 原生的补丁机制:

```yaml
# pnpm-workspace.yaml
patchedDependencies:
  node-pty@1.1.0: patches/node-pty@1.1.0.patch
```

`patches/node-pty@1.1.0.patch` 里的真实内容是给 PTY 后端的 spawn-helper 路径解析加了一个可覆盖的环境变量出口:

```diff
--- a/lib/unixTerminal.js
+++ b/lib/unixTerminal.js
-var helperPath = native.dir + '/spawn-helper';
-helperPath = path.resolve(__dirname, helperPath);
+var helperPath = process.env.DSH_NODE_PTY_SPAWN_HELPER;
+if (helperPath) {
+    helperPath = path.resolve(helperPath);
+}
+else {
+    var executableSibling = process.execPath + '-spawn-helper';
+    if (fs.existsSync(executableSibling)) {
+        helperPath = executableSibling;
+    }
+    else {
+        helperPath = native.dir + '/spawn-helper';
+        ...
+    }
+}
```

这和 vendoring 是同一种治理精神在不同成本层级上的体现:`node-pty` 涉及原生二进制编译,整份 vendor 的收益不足以覆盖维护成本,所以选择 pnpm 的补丁机制——补丁文件本身进版本控制、补丁内容是可 diff 可评审的,和"偷偷在 `node_modules` 里手改一个文件"完全是两个性质。

第二道是 **`allowBuilds`**——pnpm 10+ 默认阻止任何声明了 install/build 脚本的依赖执行该脚本,除非显式列入允许清单,这是防止供应链投毒(恶意包在 `postinstall` 里执行任意代码)的默认拒绝策略:

```yaml
# pnpm-workspace.yaml
# pnpm 10+ blocks any dependency shipping an install/build script until it is
# explicitly reviewed here (strictDepBuilds defaults to true: an unlisted script
# is a hard install error). Every such package MUST be listed; we deny by
# default and only allow scripts we need.
allowBuilds:
  esbuild: true
  lefthook: true
  node-pty: true
  koffi: true
  '@google/genai': false
  protobufjs: false
  node-addon-require-builtin: false
```

每一行都带着取舍理由的注释:`esbuild`(原生二进制)、`lefthook`(git hook 安装)、`node-pty`(跨平台 PTY 后端,包括 Windows ConPTY)、`koffi`(JSONL 持久化在 Windows 上调用 `MoveFileExW`)确实需要自己的构建脚本而被允许;`@google/genai`、`protobufjs`、`node-addon-require-builtin` 则被显式**拒绝**执行脚本——即使它们声明了脚本,仓库判断这些脚本对当前用法是无操作的空跑,拒绝执行不影响安装成功。这一套白名单和 vendoring manifest 是同构的治理模式:**默认不信任,每一条例外都要有名字、有理由、留痕在版本控制里**。

再往外一层,`THIRD_PARTY_NOTICES.md` 把这套治理结果对外部消费者可见化——文件顶部声明它是自动生成、不可手改:

```markdown
<!-- Generated by scripts/gen-third-party-notices.ts — do not edit by hand.
     Run `pnpm run gen-third-party-notices` to regenerate. -->

## Vendored source (`vendor/`)

The Cordis framework and its foundation libraries are source-vendored into
this repository rather than consumed from npm, and republished under the
`@deepseek-ai` scope. All are MIT-licensed; each directory preserves its
upstream `LICENSE` file. Exact upstream commits and local modifications are
recorded in [`vendor/README.md`](vendor/README.md).
```

`lefthook.yml` 的 pre-commit hook 会在任何触及 `package.json`、`pnpm-workspace.yaml`、`pnpm-lock.yaml`、`vendor/README.md` 的提交上自动重新生成这份文件并 `git add`——治理文档和实际依赖状态之间不存在"忘记同步"这种人为失误的空间,因为生成动作是提交流程的一部分,而不是需要人记得手动去跑的可选步骤。

## 常见问题/易踩坑

- **误以为改一份 `vendor/cordis/src/*.ts` 就完事**——`vendor/README.md` 要求任何偏离上游都要同步补一条"Local modifications"记录并说明理由,否则下一次同步上游代码时,这条本地改动很可能被直接覆盖丢失。
- **给 vendored 包加新依赖时忘记它们的 `devDependencies`/`scripts`/`repository` 字段是被特意精简过的**——README 第 2 条修改记录明确写了"removed upstream devDependencies/scripts/repository fields",随手抄一份上游 `package.json` 覆盖回去会破坏这份精简约定。
- **以为 `overrides` 只在直接依赖层生效**——`linkWorkspacePackages` + `overrides` 的组合对**任何深度**的依赖图都生效,包括从已构建的 `lib/` 产物里发出的 import,这也是 `verify-vendored-links` 要检查 `packages`/`snapshots` 这类深层 lockfile 结构、而不只是检查顶层 `importers` 的原因。

## 小结与更普适的认知

Vendoring 作为一种工程决策,本质上是在"依赖上游发布节奏、享受生态默认的可维护性"和"完全拥有代码、承担同步维护成本"之间选边站。这个取舍在业界并不罕见——大型项目普遍会对某些特别核心、特别需要深度定制、或者信任边界特别敏感的依赖采取类似策略,常见形态包括:把编译器/运行时的某个关键子系统整个拷进主仓库并保留同步脚本、对安全敏感的加密库做"vendor + 定期人工审计差异"而不是自动升级、或者像很多大型单体仓库那样对整个第三方生态做"snapshot + 内部 fork"处理,理由几乎都指向同一句话——**核心路径的行为,不能交给一个自己无法直接读、改、审的黑盒**。

DeepSeek Harness 的具体实现之所以值得作为范例来读,是因为它把这套决策的每一层代价都显式化了:manifest 表格量化了"到底 vendor 了什么、精确到哪个 commit";本地修改日志量化了"到底改了什么、为什么改、测试证据在哪";`verify-vendored-links` 这类脚本量化了"这套隔离承诺是否在每一次依赖解析里都真正生效,而不是写在文档里就当作已经完成"。这三层合在一起,才是"可审计、可打补丁、版本锁死"这句开篇宣言真正落地的方式。
