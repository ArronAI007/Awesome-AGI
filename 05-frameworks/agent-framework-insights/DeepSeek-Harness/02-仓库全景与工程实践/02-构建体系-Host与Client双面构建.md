# 构建体系:Host 与 Client 双面构建

> 整个仓库的 TypeScript 类型检查被硬性拆成两个永不合并的 `ts.Program`——一个覆盖 Node 端的 Host,一个覆盖浏览器端的 Client。这不是工程洁癖式的"拆着玩",而是因为 Host 和 Client 各自往同一个 Cordis `Context` 接口上 `declare module` augment 了不同的服务键(有些键名甚至相同、类型却不同),一旦这两组 augmentation 落进同一个编译单元,类型系统会把两侧的能力表合并成一张谁都看不清边界的假地图。本篇通过真实的 `tsconfig.*.json` 和 `tsdown.config.ts` 拆解这套"双面构建"的来龙去脉。

## 学习目标

- 理解 `tsconfig.json` 里 `files: []` + 两个 `references` 意味着什么:根配置本身是"无程序"的纯引用清单,永不参与真实编译。
- 搞清楚 `tsconfig.host.json` 与 `tsconfig.client.json` 分别覆盖哪些源文件/测试文件,以及它们各自 `references` 列表里为什么会有重叠的叶子包。
- 理解 Cordis `Context` 类型合并机制,以及"host/client 在同一个键上挂载不同的服务"这件事为什么会让单一 `ts.Program` 失真。
- 理解 `tsdown.config.ts` 里 `DSH_BUILD_FACE` 环境变量如何驱动两条完全不同的打包管线,以及 `packages/client/tsdown.client.ts` 里"每个客户端包自带浏览器打包配置"的机制。
- 能够判断一个新写的包应该走 Host 构建、Client 构建,还是像 `packages/client/*` 里那样双面都要构建。

## 背景与设计动机

假设不做这个拆分,把 `packages/client/*` 里几十个 UI 插件包和 `packages/host/*`、`packages/core/*` 等 Node 端包全部塞进同一个 `tsc -b` 编译单元会发生什么?TypeScript 的模块声明合并(declaration merging)是**全局**生效的——只要某个 `.ts` 文件在这个编译单元里被加载过,它对 `declare module '@deepseek-ai/cordis'` 里 `Context` 接口做的任何扩展,都会合并进整个程序里唯一的那份 `Context` 类型。也就是说,Node 端插件声明的 `ctx.fs`(文件系统能力座)、`ctx.sandbox`(进程沙箱)会和浏览器端插件声明的 `ctx.theme`(主题运行时)、`ctx.modules`(客户端模块系统)合并成同一张服务表。写浏览器端代码的人本该在编译期就被 TypeScript 挡下来的错误——比如误用一个只在 Node 里存在的 `ctx.fs`——因为类型系统"看得到"这个键,反而会编译通过,直到打包阶段才因为找不到对应的运行时实现而崩溃,甚至更糟——悄悄地把一份不该在浏览器里出现的 Node 依赖打进产物。

更麻烦的是**同名键、不同类型**的情况。根 `tsconfig.client.json` 的注释直接点出了这一点:

```jsonc
// tsconfig.client.json
{
  // Client-side typecheck aggregate: packages/client tests (.ts and .tsx).
  // Split from the host aggregate because both sides merge cordis Context
  // under the same keys (sessions, loader) with different services; shared
  // leaves (session/llm/tools/apiproxy/...) build once and are referenced by
  // both programs through each client package's own references.
  "extends": "./tsconfig.base.client.json",
  ...
}
```

`sessions`、`loader` 这两个键在 Host 侧和 Client 侧都存在,但背后的服务类型完全不同。比如 `loader` 这个键,vendored 的 Cordis Loader 插件在 Node 端是这样声明的:

```typescript
// vendor/loader/src/index.ts
interface Context {
  loader: Loader
}
```

这里的 `Loader` 是 Node 端管理插件生命周期的类。如果 Client 侧某个包又在同一个合并单元里给 `ctx.loader`(或类似的 `ctx.modules`)声明了另一套浏览器端的类型,单一 `ts.Program` 就会拿到两个互相冲突或互相覆盖的类型定义——merge 会静默吃掉其中一份,而不是报错提醒你"这其实是两个不同的东西"。这正是本篇标题里"双面构建"存在的根本原因:**必须让 Host 和 Client 的 Context 合并各自独立发生,谁也看不见谁的那一份**。

## 核心机制详解

### 根 `tsconfig.json`:一个"无程序"的引用清单

```jsonc
// tsconfig.json
{
  // Solution file: the whole-repo graph for `tsc -b tsconfig.json` and the
  // tsserver entry. `extends` carries the base paths for get-tsconfig
  // consumers — tsx running examples/ and scripts/ (no nearer tsconfig)
  // resolves workspace imports through this file. `files: []` keeps it
  // program-less, so the host/client cordis Context merges never meet.
  // NEVER add include/files entries, and NEVER flatten this solution into a
  // single ts.Program (scripts seed tsconfig.host.json or tsconfig.client.json).
  "extends": "./tsconfig.base.json",
  "files": [],
  "references": [
    { "path": "./tsconfig.host.json" },
    { "path": "./tsconfig.client.json" }
  ]
}
```

关键是 `"files": []`。TypeScript 的 Project References 模式下,一个 solution 文件如果自己不声明任何 `files`/`include`,就永远不会被实例化成一个真正的 `ts.Program`——它只是给 `tsc -b`(批量构建)和 tsserver(编辑器智能提示)一个"这里有两个独立子工程"的路标。注释里写得很直白:**永远不要往这个文件加 `include`/`files`,永远不要把这个 solution 压平成单一 `ts.Program`**——这两条禁令直接对应前面讲的合并风险。同时它 `extends` 了 `tsconfig.base.json`,这样像 `tsx` 这种没有更贴近的 tsconfig 可用的场景(运行 `examples/` 或 `scripts/` 下的脚本),依然能通过这份基础路径映射解析到工作区内的包。

### `tsconfig.host.json`:Node 端聚合工程

```jsonc
// tsconfig.host.json
{
  // Host aggregate (one of the two check units; see tsconfig.json). packages/client
  // type-checks in tsconfig.client.json: the two sides merge cordis Context under
  // the same keys, one program cannot see both.
  "extends": "./tsconfig.base.json",
  "compilerOptions": {
    "noEmit": true,
    "rewriteRelativeImportExtensions": false
  },
  "include": [
    "apps/web/tests/scaffold.ts",
    ...
    "apps/cli/tests/**/*.ts",
    "examples/*/src/**/*.ts",
    "packages/*/*/tests/**/*.ts",
    "scripts/**/*.ts",
    ...
  ],
  "exclude": [
    "packages/client/*/src/**",
    "packages/*/*/tests/**/*.client.ts",
    "packages/*/*/tests/**/*.client.tsx",
    "packages/*/*/tests/**/*.client.spec.ts",
    "packages/*/*/tests/**/*.client.spec.tsx",
    ...
  ],
  "references": [
    { "path": "./vendor/cosmokit" },
    { "path": "./vendor/cordis" },
    ...
    { "path": "./packages/core/agent-loop" },
    { "path": "./apps/cli" }
  ]
}
```

几个要点:

- **`include` 里几乎不出现 `packages/client/*/src`**——`exclude` 显式把它排除掉了(`packages/client/*/src/**`)。Host 工程只覆盖 Node 端源码、脚本、以及测试文件里**不带** `.client.` 后缀的部分。
- **`*.client.ts` / `*.host.spec.ts` 是两套互斥的文件名约定**:一个 client 包如果同时有 Node 半区和浏览器半区,测试文件用文件名后缀标注自己属于哪一半——`*.client.*` 归 Client 聚合,`*.host.spec.ts` 归 Host 聚合。两边互相 `exclude` 对方的后缀,所以公共的测试 glob(`packages/*/*/tests/**/*.ts`)不需要为每个文件单独配置。
- **`references` 列出上百个具体叶子包的路径**——这是 TypeScript Project References 的硬性要求:引用必须显式列出,不支持 glob 通配。这也是为什么 `tsconfig.base.json` 里那份路径映射表(下面会看到)需要用 `paths` 通配符做另一层补充——`references` 管的是"编译顺序和增量缓存边界",`paths` 管的是"裸模块名怎么解析到源码"。

### `tsconfig.client.json` 与 `tsconfig.base.client.json`:浏览器端聚合工程

```jsonc
// tsconfig.base.client.json
{
  // Client-side compiler shape shared by tsconfig.client.json and every
  // packages/client/* package: browser library API, React JSX, no ambient
  // node types (packages that need them override locally).
  "extends": "./tsconfig.base.json",
  "compilerOptions": {
    "jsx": "react-jsx",
    "lib": ["ES2024", "DOM", "DOM.Iterable"],
    "types": []
  }
}
```

`tsconfig.client.json` 继承的正是这份 `tsconfig.base.client.json`,而不是 `tsconfig.host.json` 继承的 `tsconfig.base.json`——差异只有三处,却每一处都在划清"这是浏览器代码"的边界:`lib` 换成 `["ES2024", "DOM", "DOM.Iterable"]`(能用 `document`、`window`,不能用 Node 的 ambient 类型);`jsx: "react-jsx"`(浏览器端才需要 JSX 转换);`types: []`(不隐式引入任何全局类型包,包括 `@types/node`——需要 Node 类型的个别包必须在自己的 tsconfig 里显式声明)。

`tsconfig.client.json` 本身:

```jsonc
// tsconfig.client.json
{
  "extends": "./tsconfig.base.client.json",
  "compilerOptions": {
    "noEmit": true,
    "rewriteRelativeImportExtensions": false,
    // Tests execute under vitest on node (e2e files spawn processes); browser
    // purity of package src is each package's own tsconfig plus
    // scripts/client-bundle-purity.spec.ts.
    "types": ["node"]
  },
  "include": [
    "packages/client/*/src/css-modules.d.ts",
    "packages/client/*/tests/**/*.ts",
    "packages/client/*/tests/**/*.tsx",
    "packages/*/*/tests/**/*.client.spec.ts",
    ...
  ],
  "exclude": [
    "packages/client/*/tests/**/*.host.spec.ts"
  ],
  "references": [
    { "path": "./packages/host/webserver" },
    { "path": "./packages/compaction/compaction" },
    { "path": "./packages/client/ui-slots" },
    ...
    { "path": "./apps/web" }
  ]
}
```

注意这里 `types` 反而被设成了 `["node"]`——注释解释得很清楚:**这份聚合工程编译的是测试文件**,测试跑在 vitest 之上、跑在 Node 进程里(e2e 测试还会 spawn 子进程),所以测试代码需要 Node 类型;而"包源码本身是否保持浏览器纯净"是另一件事,由每个客户端包自己的 tsconfig(继承 `tsconfig.base.client.json`,`types: []`)加上 `scripts/client-bundle-purity.spec.ts` 这个专门的构建期校验来保证。这是"测试聚合工程的类型环境"和"被测源码的类型环境"故意错开的一个细节。

`references` 里能看到**共享叶子包**同时出现在 Host 和 Client 的引用列表里,比如 `packages/compaction/compaction`。这些包(`session`、`llm`、`tools`、`apiproxy` 等)本身不依赖 Cordis 的 `Context` 类型合并——它们只导出纯类型或不含跨插件运行时身份的东西,所以可以只构建一次,被两个程序分别引用,而不违反"两侧合并互不可见"的约束。

### 两侧真的会挂载同名键,不同类型:一个可验证的例子

Host 侧,`packages/core/session/src/index.ts` 给 `Context` 挂了 `sessions` 键:

```typescript
// packages/core/session/src/index.ts
declare module '@deepseek-ai/cordis' {
  interface Context {
    sessions: SessionStore
  }
  interface Events {
    /** ... */
  }
}
```

`loader` 键则是 vendored Cordis Loader 插件在 Node 端声明的:

```typescript
// vendor/loader/src/index.ts
interface Context {
  loader: Loader
}
```

而 Client 侧的等价能力,走的是完全不同的类型和键名——比如主题运行时:

```typescript
// packages/client/ui-theme/src/client/index.ts
declare module '@deepseek-ai/cordis' {
  interface Context {
    theme: ThemeRuntime
  }
  interface Events {
    'theme/change'(snapshot: ThemeSnapshot): void
  }
}
```

`sessions`、`loader` 这两个键名在浏览器端语境下另有所指(`tsconfig.client.json` 注释明确点名了这两个键),背后类型与 Node 端并不相同。如果两侧的 `declare module` 语句被同一个 `ts.Program` 加载,TypeScript 会把二者做接口合并——合并结果既不是 Host 期望的类型,也不是 Client 期望的类型,而是两者字段的并集(遇到同名同结构字段会合并、遇到冲突签名可能直接报错或产生令人费解的联合类型)。拆成两个 `ts.Program` 之后,Host 编译时只加载 Host 侧那组 `declare module`,Client 编译时只加载 Client 侧那组,两份 `Context` 类型永远互不相见,这才是"谁也看不见谁的那一份"在类型系统层面的真实含义。

### 构建管线:`DSH_BUILD_FACE` 驱动的两条 tsdown 通路

类型检查分两半只是故事的一半,产物构建同样分两条流水线。根 `package.json` 里:

```json
"build:lib": "npm run build:lib:host && npm run build:lib:client",
"build:lib:host": "tsc -b tsconfig.host.json && tsdown --env.DSH_BUILD_FACE host",
"build:lib:client": "tsc -b tsconfig.client.json && tsdown --env.DSH_BUILD_FACE client",
```

每一面先用对应的 `tsc -b` 把 TypeScript 降级成 JavaScript(降级到各自 `lib/types` 目录),再用 tsdown 把 JS 打包成最终发布产物。`tsdown.config.ts` 就是这条分流的入口:

```typescript
// tsdown.config.ts
import { defineConfig } from 'tsdown'
import { typertPlugin } from './packages/typert/generator/lib/types/tsdown-plugin.js'

function isBuildFaceClient(value: unknown): boolean {
  if (value === undefined || value === 'host') return false
  if (value === 'client') return true
  throw new Error(`tsdown: --env.DSH_BUILD_FACE must be host or client, received ${String(value)}`)
}

/**
 * The ordinary workspace build consumes JavaScript emitted by the Host
 * TypeScript project and runs Typert. The Client pass selects packages that
 * declare a browser bundle and lets their package-local configs emit both
 * their Node loader entry and browser artifact.
 */
export default defineConfig(({ env }) => {
  const client = isBuildFaceClient(env?.DSH_BUILD_FACE)
  return {
    workspace: ['vendor/*', 'packages/*/*', 'apps/cli'],
    entry: client ? '' : ['lib/types/{index,invariant,startup}.js'],
    outDir: 'lib',
    format: ['esm'],
    platform: 'node',
    target: 'es2024',
    fixedExtension: false,
    dts: false,
    clean: false,
    plugins: client ? [] : [typertPlugin({ mode: 'workspace', faces: ['host'] })],
  }
})
```

这里的分流策略很微妙:Host Pass(`DSH_BUILD_FACE=host`,或不传)对**每一个** workspace 包统一打包 `lib/types/{index,invariant,startup}.js` 三个标准入口,并顺手跑一次 Typert 产物生成器。Client Pass(`DSH_BUILD_FACE=client`)则把 `entry` 清空(`''`)——也就是说对绝大多数包什么都不做,真正需要产出浏览器 bundle 的包必须**自带一份 package 级 `tsdown.config.ts`**,用自己的配置覆盖掉这份根配置,自行决定要不要在 Client Pass 里再emit 一份 Node 半区和一份浏览器半区。

这份"包级覆盖"的公共实现就是 `packages/client/tsdown.client.ts`,它导出的 `clientBundle()` 帮助函数被每个 UI 插件包的 `tsdown.config.ts` 调用:

```typescript
// packages/client/tsdown.client.ts
export function clientBundle(
  id: string,
  libEntry: readonly string[],
  options: ClientBundleOptions = {},
): BuildFaceConfig {
  const lib = clientLibraryConfig(id, libEntry, options.lib)
  return ({ env }) => {
    const face = buildFace(env?.DSH_BUILD_FACE)
    const client = clientConfig(id, face === undefined
      ? 'src/client/index.ts'
      : 'lib/types/client/index.js')
    const node = [lib, ...(options.companions ?? [])]
    if (face === 'host') return options.hostPhase === true ? node : [SKIP_WORKSPACE_BUILD]
    if (face === 'client') return options.hostPhase === true ? [client] : [...node, client]
    return [...node, client]
  }
}
```

默认情况下(`options.hostPhase` 不设置),一个客户端插件包在 Host Pass 里完全跳过(`SKIP_WORKSPACE_BUILD` = `{ entry: '' }`),把 Node 半区和浏览器半区**都**留给 Client Pass 一起产出——这样浏览器 bundle 打包时,Rolldown 能直接看到刚生成的 `lib/types/client/index.js`,不需要额外的跨阶段协调。`clientConfig()` 里还藏着浏览器打包必须处理的一整套细节:

```typescript
// packages/client/tsdown.client.ts
function clientConfig(id: string, entry: string): UserConfig {
  return {
    name: `${id}/client`,
    entry: { client: entry },
    outDir: 'lib',
    format: 'cjs',
    platform: 'browser',
    dts: false,
    sourcemap: true,
    clean: false,
    external: [...CLIENT_EXTERNALS],
    define: {
      'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV ?? 'production'),
      'import.meta.env.MODE': JSON.stringify(process.env.NODE_ENV ?? 'production'),
      'import.meta.env': JSON.stringify({ MODE: process.env.NODE_ENV ?? 'production' }),
    },
    noExternal: (id: string) => (CLIENT_EXTERNALS.includes(id) ? undefined : true),
    plugins: [{
      name: 'dsh-client-bundle-purity',
      resolveId(source: string) {
        if (!source.startsWith('@deepseek-ai/')) return null
        if (CLIENT_EXTERNALS.includes(source)) return null // platform module: external wins
        if (VENDORED_LIBRARY.test(source)) return null // vendored library: inline, no shared identity
        if (INLINE_SAFE.test(source) || GENERATED_REMOTE.test(source)) return null
        throw new Error(
          `client bundle purity: "${source}" is not a platform module (CLIENT_EXTERNALS), an inline-safe wire layer, or a generated /remote contribution — `
          + 'cross-plugin value imports are forbidden; collaborate through cordis services (type-only imports are erased and never reach this gate)',
        )
      },
    }, /* ...CSS Modules 内联插件... */],
    outputOptions: {
      entryFileNames: 'client.js',
      sourcemapPathTransform: browserSourcePath,
      banner: `window.__ModuleLoader__.load({ id: ${JSON.stringify(id)}, factory: (require) => {`,
      footer: 'return module.exports; } });',
      intro: 'var module = { exports: {} }; var exports = module.exports;',
    },
  }
}
```

这段配置里 `dsh-client-bundle-purity` 插件是构建期对"双面构建"约束的又一层强制——它在 `resolveId` 阶段拦截每一个 `@deepseek-ai/*` 的导入,只允许三类情况通过:平台模块(`CLIENT_EXTERNALS`,走浏览器端的模块加载表,不打进 bundle)、vendored 库(如 `cosmokit`,没有跨插件运行时身份,可以安全内联)、显式标记为"无运行时身份的线路层"的包。任何其他跨插件的**值导入**都会在构建期直接抛错——类型系统层面"两侧互不可见"的约束,在打包器层面变成了"跨插件协作只能走 Cordis 服务,不能靠 import 抄近路"的强制检查。

## 常见问题/易踩坑

- **误以为 `packages/client/*/src` 会被 `tsc -b tsconfig.host.json` 检查到**——不会,`tsconfig.host.json` 的 `exclude` 显式排除了它;如果在 Host 侧看到某个客户端包的类型错误没被报出来,先确认没有搞错编译入口。
- **新增一个客户端叶子包却忘了在 `tsconfig.client.json` 的 `references` 里补上路径**——TypeScript Project References 不支持通配符,漏加引用会导致 tsserver 报"找不到模块"或增量构建顺序错乱,即便 `tsconfig.base.json` 的 `paths` 映射表里已经写对了。
- **给一个客户端包写 `tsdown.config.ts` 时忘记覆盖根配置的 `entry: ['lib/types/{index,invariant,startup}.js']`**——根配置对 Client Pass 默认清空 entry,包级配置如果没有正确调用 `clientBundle()`/`clientOnly()` 之类的帮助函数,很容易导致 Client Pass 什么都没产出。

## 小结

Host/Client 双面构建的根源是 Cordis `Context` 类型的全局声明合并特性:两侧会在同一批服务键上(有些键名甚至完全相同)挂载完全不同的类型,一旦这些 `declare module` 落进同一个 `ts.Program`,类型系统看到的就是一张失真的能力表。仓库用 `tsconfig.json`(`files: []` 的纯引用清单)分裂出 `tsconfig.host.json` 和 `tsconfig.client.json` 两个独立编译单元,再用 `tsdown.config.ts` 的 `DSH_BUILD_FACE` 环境变量驱动两条对应的打包管线——Host Pass 统一产出所有包的标准入口,Client Pass 把浏览器 bundle 的产出权交给每个客户端包自己的 `tsdown.config.ts`(多数基于 `packages/client/tsdown.client.ts` 提供的 `clientBundle()`),并在打包期用 purity 插件把"跨插件只能走 Cordis 服务"这条架构约束变成一道硬性的构建门禁。
