# CLI 命令与 Profile 机制

> `dsh` 的命令行只做一件"元"层面的事：决定装配哪一棵插件树、往树上叠加哪些补丁、以及要不要真的启动它。`profile`、`plugin`、`dump-config` 三种模式分别对应"启动"、"给某个 Profile 装插件依赖"、"只打印装配结果不启动"——搞懂这三者的边界，再配合 `--dump-config` 这个调试利器，你会发现 `dsh` 的启动行为完全是可预测、可审查的，没有任何"黑魔法"。

## 学习目标

- 读懂 `apps/cli/src/args.ts` 里三种命令行模式（`profile`/`plugin`/`dump-config`）的解析逻辑与边界规则。
- 理解 Profile 的物理结构：`$DSH_HOME/profiles/<name>` 目录下有什么，`dsh.profile.bundles` 字段如何决定叠加哪些 Bundle。
- 理解 `profile-boot.ts` 里补丁层的叠加顺序：Bundle 层 → Profile 自己的 `cordis.patch.yml` → Home 级用户层 → `--patch` 覆盖层。
- 会用 `dsh --profile headless "task"` 跑一次无人值守的一次性任务。
- 会用 `dsh --profile <name> --dump-config` 在不启动任何进程的情况下，审查一个 Profile 最终装配出的插件树。

## 背景与设计动机

如果一个 Agent 产品只支持"一种启动方式"，添加一种新的运行形态（比如"给 CI 用的无人值守模式"）往往意味着要复制一份启动逻辑、再手动同步两边的插件配置，久而久之两份逻辑就会跑偏。`dsh` 的解法是把"启动方式"整体抽象成 **Profile**：一个 Profile 不是写死的代码路径，而是"若干 Bundle 补丁层 + 用户自己的覆盖层"叠加出的一棵插件树。`web`、`headless` 只是官方内置的两个 Profile 名字，理论上任何人都可以基于同一套装配机制拼出自己的 Profile。这也解释了为什么 CLI 层的代码量很小——绝大多数"能力"都不在 CLI 包里，而在被组合进来的各个 Bundle 里。

## 核心机制详解

### 命令行的三种模式

`apps/cli/src/args.ts` 用 `commander` 解析出一个判别联合类型 `DshInvocation`：

```typescript
// apps/cli/src/args.ts
/** Boot a named profile and hand it the invocation's inner arguments. */
interface ProfileInvocation {
  mode: 'profile'
  profile: string
  patches: string[]
  args: string[]
}

/** Print a composed profile tree and exit without booting. */
interface DumpConfigInvocation {
  mode: 'dump-config'
  profile: string
  defaultOnly: boolean
  patches: string[]
}

/** Manage a profile's plugins: forward `args` to pnpm inside the profile directory. */
interface PluginInvocation {
  mode: 'plugin'
  profile: string
  args: string[]
}

export type DshInvocation = ProfileInvocation | DumpConfigInvocation | PluginInvocation
```

三种模式分别是：

- **`profile`**：真正启动一个 Profile（`dsh --profile web`、`dsh --profile headless "task"`）；
- **`dump-config`**：不启动任何进程，只把 Profile 装配出的插件树按补丁层打印出来；
- **`plugin`**：管理某个 Profile 目录下的插件依赖（本质是把参数转发给 pnpm，在 Profile 目录里执行 `pnpm add`/`remove`/`why`）。

命令行解析上有一条很重要的边界规则，写在模块顶部的注释里：

```typescript
// apps/cli/src/args.ts
/**
 * The launcher parses only what it owns — which profile to boot, which extra
 * patch overlays to apply, and the config dumps — and hands **everything after
 * its own flags** to the booted tree verbatim, where injected app plugins parse
 * their own flag families and print their own `--help` ...
 * Launcher flags therefore come first: the first token this parser does not
 * recognize starts the inner arguments, so `dsh --profile tui --resume abc`
 * boots the tui profile with `--resume abc`, and `dsh --profile web -h` prints
 * the web app's help, not this one's.
 */
```

也就是说 `dsh --profile <name>` 之后遇到的第一个"launcher 不认识"的 token，就是被启动应用自己的参数起点。这条规则由 commander 的几个配置项共同实现：

```typescript
// apps/cli/src/args.ts（节选）
program
  .name('dsh')
  .version(version, '-V, --version', 'output the version number')
  .exitOverride()
  .helpOption(false)
  .allowUnknownOption()
  .passThroughOptions()
  .enablePositionalOptions()
  .argument('[args...]', 'arguments for the booted profile\'s app (see: dsh --profile <name> --help)')
  .option('--profile <name>', 'the profile under $DSH_HOME/profiles to boot')
  .option('--patch <path>', 'extra patch-list overlay applied after the profile layer (repeatable)', collect)
  .option('--dump-config', 'print the composed profile tree and exit')
  .option('--dump-default-config', 'print the profile tree without its user layer or --patch overlays and exit')
```

`helpOption(false)` 意味着 launcher 自己不接管 `-h`——这就是为什么 `dsh --profile web -h` 打印的是 web 应用自己的帮助文本；只有裸 `dsh -h`（没有 `--profile`）才会打印 launcher 自己的帮助，这一分支在 `action` 回调里单独处理：

```typescript
// apps/cli/src/args.ts（节选）
.action((args: string[], options: BootOptions & { profile?: string }) => {
  if (options.profile === undefined) {
    if (args.some(argument => argument === '-h' || argument === '--help')) program.help()
    program.error('error: --profile <name> is required')
  }
  ...
})
```

### `--dump-config` 与 `--dump-default-config`：两种"打印而不启动"

`dump-config` 模式在同一个 `resolveBoot` 函数里判定：

```typescript
// apps/cli/src/args.ts（节选）
function resolveBoot(program: Command, profile: string, options: BootOptions, args: string[]): DshInvocation {
  const patches = options.patch ?? []
  if (patches.includes('')) program.error('error: --patch needs a path')
  if (options.dumpConfig !== true && options.dumpDefaultConfig !== true) {
    return { mode: 'profile', profile, patches, args }
  }
  if (options.dumpConfig === true && options.dumpDefaultConfig === true) {
    program.error('error: --dump-config and --dump-default-config are mutually exclusive')
  }
  // The dump is boot-free: it never runs app command-line providers, so it
  // cannot show what those flags would decide, and printing a tree that differs
  // from the same invocation's boot would mislead.
  if (args.length > 0) {
    program.error(`error: config dumps take no app arguments, got ${args.map(argument => JSON.stringify(argument)).join(' ')}`)
  }
  ...
}
```

两者的区别在于是否包含用户自己的覆盖层：`--dump-config` 打印"这次真实启动会装配出的完整树"（Bundle 层 + Profile 的 `cordis.patch.yml` + Home 级用户层 + `--patch` 覆盖），`--dump-default-config` 只打印"Bundle 自带的默认层"，跳过用户的任何自定义。代码里那句注释解释了为什么 dump 模式干脆拒绝任何 app 参数：因为 dump 从不真正启动被装配的应用，如果允许传参却不生效，打印出的树就会和真实启动的结果不一致，反而误导排查问题的人。

真正执行打印的是 `dump-config.ts`：

```typescript
// apps/cli/src/dump-config.ts
export function runDumpConfig(profile: string, defaultOnly: boolean, patches: readonly string[]): void {
  const loaded = prepareProfile(profile, !defaultOnly)
  const layers: ConfigDumpLayer[] = loaded.layers.map(layer => ({
    label: layer.packageName,
    patches: layer.patches,
  }))
  if (!defaultOnly) {
    if (existsSync(loaded.patchPath)) {
      layers.push({ label: loaded.patchPath, patches: loaded.patches })
    }
    const homePatchFile = homePatchPath()
    const homePatches = loadOptionalPatches(NAME, homePatchFile)
    if (homePatches !== undefined) {
      layers.push({ label: homePatchFile, patches: homePatches })
    }
    for (const file of patches) {
      const absolute = resolve(file)
      layers.push({ label: absolute, patches: loadOverlayPatches(NAME, absolute) })
    }
  }
  process.stdout.write(renderConfigDump(NAME, join(loaded.dir, PROFILE_ROOT_FILENAME), layers))
}
```

这个命令的价值在于：当一个插件行为不符合预期时（比如某个工具没被启用、某个配置项的值不是你以为的那样），第一反应不该是去猜测装配顺序,而是先跑一遍 `dsh --profile <name> --dump-config`，把每一层补丁（哪个 Bundle 贡献了哪一行、Profile 自己覆盖了什么、`--patch` 又覆盖了什么）按顺序打印出来直接看——这条命令完全不启动进程,也不会评估任何 `!!js` 表达式，是纯静态的补丁列表展开。

### Profile 的物理结构

一个 Profile 的定义写在 `packages/boot/app-boot/src/profile.ts` 的模块注释里：

```typescript
// packages/boot/app-boot/src/profile.ts
/**
 * A profile is a directory under `$DSH_HOME/profiles/<name>` holding a
 * `package.json` (out-of-tree plugin dependencies plus the profile manifest
 * `dsh.profile` with its ordered `bundles` list) and a `cordis.patch.yml`
 * (the user's own patch layer, applied after every bundle layer). Bundles are
 * npm packages whose manifest declares
 * `"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }`; the tree is
 * composed by applying each bundle's patch list in `dsh.profile.bundles`
 * order over an empty entry list, then the profile's own patches, then any
 * launcher layers (`--patch` files and flag-derived patches).
 */
```

拆开来看，一个 Profile 目录里有两个关键文件：

- `package.json`：里面的 `dsh.profile.bundles` 是一份**有序的包名列表**，决定按什么顺序叠加哪些 Bundle；
- `cordis.patch.yml`：用户自己在这个 Profile 上追加的覆盖层，会在所有 Bundle 层之后应用。

反过来，"Bundle"指的是任何在自己 `package.json` 里声明了 `dsh.bundle.patch` 字段的 npm 包，比如：

```json
// packages/bundle/headless/package.json（节选）
{
  "name": "@deepseek-ai/dsh-headless",
  "dsh": {
    "bundle": {
      "patch": "./cordis.patch.yml"
    }
  },
  ...
}
```

`dsh` 内置了两个官方模板，写在同一个文件里：

```typescript
// packages/boot/app-boot/src/profile.ts
/** The shipped profile templates auto-initialized on first use, by name. */
export const PROFILE_TEMPLATES: Record<string, readonly string[]> = {
  web: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'],
  headless: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless'],
}
```

也就是说 `web` Profile 是 `dsh-base`（基础能力：模型、工具、沙箱、会话……）叠加 `dsh-web-app`（HTTP 服务、WebSocket、浏览器插件roster）；`headless` Profile 则是 `dsh-base` 叠加 `dsh-headless`——一个"直接跑核心 Agent/Session，不挂任何 Host、HTTP 或浏览器层"的一次性任务驱动器,`dsh-headless` 自己的包描述写得很直接：

```json
// packages/bundle/headless/package.json（节选）
{
  "name": "@deepseek-ai/dsh-headless",
  "description": "The dsh one-shot bundle: a direct core Agent/Session runner over dsh-base with no Host, HTTP, or browser layer",
  ...
}
```

### 补丁层的叠加顺序

`apps/cli/src/profile-boot.ts` 是真正把这些补丁层拼起来的地方。`composeProfile` 函数把叠加顺序落成了代码：

```typescript
// apps/cli/src/profile-boot.ts（节选）
function composeProfile(
  name: string,
  patchFiles: readonly string[],
): ComposedProfile {
  const profile = prepareProfile(name)
  const homePatches = loadOptionalPatches(NAME, homePatchPath()) ?? []
  const overlays = patchFiles.flatMap(file => loadOverlayPatches(NAME, resolve(file)))
  const bundlePatches = profile.layers.flatMap(layer => layer.patches)
  ...
}
```

配合模块顶部注释里的完整叠加顺序说明：

```typescript
// apps/cli/src/profile-boot.ts
/**
 * Load `name` and compose its effective patch stack: bundle layers in
 * `dsh.profile.bundles` order (the base bundle gates the shell stacks by
 * platform on its own rows), the profile's user layer, the home-level user
 * layer (`$DSH_HOME/cordis.patch.yml` — machine-local preferences that apply
 * to every profile, so it outranks the per-profile layer), `--patch` overlays,
 * then the telemetry switch.
 */
```

完整顺序是：

1. **Bundle 层**（按 `dsh.profile.bundles` 声明的顺序，比如先 `dsh-base` 再 `dsh-web-app`）；
2. **Profile 自己的 `cordis.patch.yml`**（这个 Profile 独有的覆盖）；
3. **Home 级用户层**（`$DSH_HOME/cordis.patch.yml`——对**所有** Profile 都生效的机器级偏好覆盖）；
4. **`--patch` 命令行覆盖层**（单次调用临时追加的覆盖，比如调试时用 `--patch ./extra.yml` 关掉某个工具）；
5. **遥测开关**（`DSH_TELEMETRY_DISABLED` 环境变量，如果设置了，追加一条禁用遥测行的补丁）。

后面的层永远能覆盖前面的层——这也是为什么 Home 级用户层"排名高于"单个 Profile 自己的层：它是"机器级偏好"，理应比某一个具体 Profile 的默认设置优先级更高。补丁层本身在装配时可以携带 `!!js` 表达式（详见 `docs/cordis-primer.md` 的 Loader Configuration 一节），这也是为什么 `web-app` 补丁层里能写出 `host: !!js ctx.webStartup.host ?? '127.0.0.1'` 这种"命令行参数优先，否则用默认值"的写法（上一篇已经展开过）。

### 跑一次无人值守任务：`dsh --profile headless`

`dsh-headless` 这个 Bundle 的补丁层展示了一个"一次性任务驱动器"最小需要挂载哪些插件：

```yaml
# packages/bundle/headless/cordis.patch.yml
- id: system-prompt
  config:
    persona: >-
      You are a coding agent powered by the {{model}} model. Your working directory is {{cwd}}.

- id: hmr
  disabled: true

- insert:
    - id: code-runtime
      name: '@deepseek-ai/dsh-code-runtime-worker-thread'

    - id: headless-startup
      name: '@deepseek-ai/dsh-headless/startup'

    # Reads its task from the ordinary headlessStartup provider.
    - id: headless-runner
      name: '@deepseek-ai/dsh-headless'
      inject: [headlessStartup]
      config:
        task: !!js ctx.headlessStartup.task
```

这里的模式和上一篇讲的 `web-startup` 一模一样：`headless-startup` 是一个普通插件,负责解析命令行里的任务字符串（`dsh --profile headless "summarize this workspace"` 里引号内的那段文本）并把它作为 `headlessStartup` 服务发布出去；`headless-runner` 声明 `inject: [headlessStartup]`，等这个服务可用之后再用 `!!js ctx.headlessStartup.task` 把任务文本注入自己的 `config.task`。跑起来的命令形如：

```sh
pnpm dsh --profile headless "summarize this workspace"
```

`docs/development.md` 给出的说明印证了这一点：

```markdown
The one-shot Headless coding agent needs `DEEPSEEK_API_KEY` in the environment or repo-root `.env`:

pnpm dsh --profile headless "summarize this workspace"
```

这条路径完全跳过了 `dsh-web-app` 里的 HTTP 服务、WebSocket、浏览器插件 roster——`dsh-headless` 直接在 `dsh-base` 之上创建一个 Agent，把任务丢进去，等它跑完打印结果就退出，非常适合 CI 流水线或脚本化调用。

### `plugin` 模式：管理 Profile 的插件依赖

第三种模式转发到 `plugin.ts`，本质是在 Profile 目录里执行 pnpm 命令：

```typescript
// apps/cli/src/args.ts（节选）
const plugin = program.command('plugin').description('manage a profile\'s plugins by forwarding the remaining arguments to pnpm in the profile directory')
plugin
  .requiredOption('--profile <name>', 'the profile whose plugins to manage (initialized on first use)')
  .allowUnknownOption()
  .argument('[args...]', 'pnpm arguments, forwarded verbatim (add <pkg>, remove <pkg>, why <pkg>, ...)')
  .action((args: string[], options: { profile: string }) => {
    rejectParentOptions('plugin')
    if (options.profile === '') program.error('error: --profile needs a name')
    if (args.length === 0) program.error('error: plugin needs pnpm arguments to forward (e.g. add <package>)')
    resolved = { mode: 'plugin', profile: options.profile, args }
  })
```

典型用法是给某个 Profile 安装一个仓库外的第三方插件：

```sh
dsh plugin --profile tui add some-third-party-plugin
```

这条命令不会启动任何 Agent 进程,只是把 `add some-third-party-plugin` 转发给 pnpm，在对应 Profile 目录（`$DSH_HOME/profiles/tui`）下执行安装——安装完之后，还需要在这个 Profile 的 `cordis.patch.yml` 里用 `insert` 补丁把新插件真正接入装配树，安装依赖和接入装配树是两个独立的步骤。

## 常见问题/易踩坑

- **改了 `cordis.patch.yml` 却不知道生效了没有**：先跑 `--dump-config` 确认补丁层顺序和内容,而不要直接启动进程再靠日志猜测。
- **以为 `--dump-config` 会执行 `!!js` 表达式**：不会，`dump-config` 是纯静态的补丁列表展开，从不装配、也不启动树，所以看不到 `!!js` 表达式求值后的最终值，只能看到表达式本身和它所在的补丁层。
- **`dsh --profile headless` 卡住不退出**：确认 `DEEPSEEK_API_KEY` 是否可用——没有可用的凭证时模型调用会失败，而不是直接报错退出；参见第 01 篇的凭证优先级说明。
- **给 Profile 装完插件依赖后没生效**：`dsh plugin add` 只负责 pnpm 依赖安装，真正把新插件接入装配树需要手动编辑该 Profile 的 `cordis.patch.yml`。

## 小结

`dsh` 的命令行本质上是一层很薄的分发器：`profile` 模式启动装配好的插件树，`dump-config` 模式只打印装配结果不启动，`plugin` 模式管理某个 Profile 的第三方依赖。Profile 本身是"若干 Bundle 补丁层 + Home 级用户层 + 命令行覆盖层"按固定顺序叠加的结果，`web`、`headless` 只是两个内置模板，本质上没有任何特权。下一篇会深入其中一层最关键的补丁——Provider 与模型配置，看 `dsh` 如何用同一套 Seam 机制同时支持 DeepSeek 官方 API 和其他厂商的模型。
