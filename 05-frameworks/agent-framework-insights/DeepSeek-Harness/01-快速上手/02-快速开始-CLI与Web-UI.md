# 快速开始：CLI 与 Web UI

> `dsh web` 这一句命令背后不是"启动一个 Web 服务器"这么简单——它是一次完整的 Profile 装配：一个空的插件树被逐层打上补丁（`dsh-base` 补丁层、`dsh-web-app` 补丁层、用户自己的 `cordis.patch.yml`），装配出的树里既有跑在 Node 里的 HTTP/WebSocket 服务，也有要发到浏览器执行的插件包。理解这一层装配关系，才能真正理解"`dsh` 启动"这件事在做什么。

## 学习目标

- 分清 `npx @deepseek-ai/dsh web`（发布态，从 npm 拉取）与 `pnpm dsh web`（源码态，跑仓库里的 TypeScript 源码）两种运行方式的本质区别。
- 理解 `apps/cli` 这个包如何通过 `bin` 字段把 `dsh` 命令暴露出去，以及它依赖了哪些运行时 bundle。
- 读懂 `dsh` 命令行解析的分发逻辑（`bin.ts`），知道 `dsh web` 只是 `--profile web` 的一个硬编码别名。
- 知道 Web UI 默认绑定在哪个地址、哪个端口，以及为什么 `--host 0.0.0.0` 被故意禁止。
- 建立"用户输入任务 → 会话创建 → Agent 开始工作"的第一个心智模型，并能指出这个模型在源码里对应哪些文件。

## 背景与设计动机

一个编码 Agent 产品通常需要同时服务两类使用场景：交互式的图形界面（给人用）和无人值守的一次性任务（给自动化流水线用）。如果这两种场景各写一套启动逻辑，很容易出现"Web 版本能用的 flag，CLI 版本却解析不了"之类的漂移。`dsh` 的做法是把"启动方式"抽象成统一的 **Profile**（一组按顺序叠加的插件补丁层），`web`、`headless` 只是两个内置的 Profile 名字，CLI 层只负责"选中哪个 Profile、传哪些参数"，剩下的装配逻辑完全共享。这也是为什么 `dsh web` 在源码里根本不是一个独立的实现，而是 `dsh --profile web` 的语法糖。

## 核心机制详解

### 两种运行方式：发布态与源码态

对于已经发布到 npm 的 `dsh`，最简单的用法是直接用 `npx` 拉取运行：

```sh
npx @deepseek-ai/dsh web
```

如果你是在克隆下来的仓库里做开发，则用 `pnpm dsh`——这条命令实际跑的是仓库源码，而不是打包产物。根 `package.json` 里定义了这条脚本：

```json
// package.json（节选）
"scripts": {
  "dsh": "node --import tsx/esm apps/cli/src/bin.ts",
  ...
}
```

`node --import tsx/esm` 是关键：`dsh` 的源码是纯 ESM TypeScript，`tsx/esm` 作为一个 Node loader hook，让 Node 直接运行 `apps/cli/src/bin.ts` 而不需要提前编译成 JS。`AGENTS.md` 里专门有一条约定强调了这一点的边界：

```markdown
The `dsh` CLI source launch runs through tsx's ESM-only hook (`node --import tsx/esm`);
modules it reaches must stay ESM (no CJS-only exports) — Node's native TypeScript modes
are unavailable across the engines range.
```

也就是说，源码态运行是有代价的约束：整条被 `dsh` 源码启动路径触达的模块链，都不能引入 CJS-only 的导出方式,因为 tsx 的 ESM hook 不兼容那种写法。而发布态（`npx @deepseek-ai/dsh`）跑的是构建产物，这条限制则不适用。

所以：`pnpm dsh web` 等价于 `npx @deepseek-ai/dsh web`，只是前者跑源码、后者跑构建产物——两者最终装配出的插件树、暴露的命令行参数都是一致的。

### `apps/cli`：`dsh` 命令的真正落地

`dsh` 这个命令名从哪里来？答案在 `apps/cli/package.json`：

```json
// apps/cli/package.json（节选）
{
  "name": "@deepseek-ai/dsh",
  "description": "dsh CLI: profile boot, plugin management, and the browser UI alias",
  "type": "module",
  "bin": {
    "dsh": "lib/bin.js"
  },
  "files": [
    "lib/*.js",
    "config"
  ],
  ...
}
```

npm 包名是 `@deepseek-ai/dsh`,但它声明的 `bin.dsh` 指向构建产物 `lib/bin.js`——这正是 `apps/cli/src/bin.ts` 编译后的产物。`apps/cli` 这个包本身依赖了一长串 workspace 内部包（`dsh-base`、`dsh-web-app`、`dsh-headless`、各种 `dsh-tool-*`），这些依赖并不是运行时才动态拉取的插件，而是 CLI 包自己在 `package.json` 里显式声明的依赖——`dsh` 命令能装配出哪些 Profile,取决于这个包依赖了哪些 bundle。

### 命令分发：`bin.ts` 里的三种模式

`apps/cli/src/bin.ts` 是整个 CLI 的入口，逻辑很短：先解析参数,再按模式分发到不同的实现文件：

```typescript
// apps/cli/src/bin.ts
import { loadLayeredEnv } from '@deepseek-ai/dsh-app-boot'
import { parseDshArgs } from './args.ts'

const invocation = parseDshArgs(process.argv.slice(2), readVersion())

switch (invocation.mode) {
  case 'profile': {
    const { runProfile } = await import('./profile-boot.ts')
    await runProfile({
      environment: loadLayeredEnv('dsh'),
      profile: invocation.profile,
      patchFiles: invocation.patches,
      args: invocation.args,
    })
    break
  }
  case 'plugin': {
    const { runPlugin } = await import('./plugin.ts')
    process.exit(runPlugin(invocation.profile, invocation.args))
    break
  }
  case 'dump-config': {
    const { runDumpConfig } = await import('./dump-config.ts')
    runDumpConfig(invocation.profile, invocation.defaultOnly, invocation.patches)
    break
  }
  default:
    invocation satisfies never
    throw new Error(`dsh: unhandled invocation mode ${JSON.stringify(invocation)}`)
}
```

值得留意的是每个分支都用了**动态 `import()`**而不是顶层静态导入。模块顶部的注释解释了原因：

```typescript
// apps/cli/src/bin.ts
/**
 * dsh — command-line entry. Dynamic imports per mode keep unrelated modes out
 * of each dispatch path; the adapter prints and exits for
 * `--help`/`--version`/a parse error, so only a valid mode reaches the switch.
 */
```

也就是说，如果你只是运行 `dsh plugin --profile tui add some-package`，进程根本不需要加载 `profile-boot.ts` 里那一整套"装配插件树、启动 HTTP 服务"的代码——三种模式互不污染彼此的加载路径，启动速度和内存占用都更可控。`invocation satisfies never` 这一行是 TypeScript 的"穷尽性检查"写法：如果未来 `DshInvocation` 联合类型新增了一个模式而这里忘了处理，编译期就会报错，而不是留到运行时才发现分发逻辑漏了一支。

### `web` 是 `--profile web` 的别名

`apps/cli/src/args.ts` 用 `commander` 解析参数，模块顶部的注释直接点明了 `web` 子命令的本质：

```typescript
// apps/cli/src/args.ts
/**
 * `web` is a hardcoded alias for `--profile web`; `plugin` manages a profile's
 * plugin dependencies by forwarding to pnpm.
 */
```

对应的实现里，`web` 子命令解析完自己的 flag 之后，直接调用和默认命令共享的 `resolveBoot`，把 profile 名字硬编码为 `'web'`：

```typescript
// apps/cli/src/args.ts（节选）
const web = program.command('web').description('boot the web profile (alias of --profile web); the web app\'s own flags follow')
web
  .helpOption(false)
  .allowUnknownOption()
  .passThroughOptions()
  .enablePositionalOptions()
  .argument('[args...]', 'arguments for the web app (see: dsh web --help)')
  .option('--patch <path>', 'extra patch-list overlay applied after the profile layer (repeatable)', collect)
  .action((args: string[], options: BootOptions) => {
    rejectParentOptions('web')
    resolved = resolveBoot(web, 'web', options, args)
  })
```

所以 `dsh web --port 8080` 和 `dsh --profile web --port 8080` 是完全等价的两种写法，区别只是前者更好记。`args.ts` 顶部的帮助文本也直接给出了这种等价关系：

```typescript
// apps/cli/src/args.ts
const HELP_EXAMPLES = `
Examples:
  dsh --profile web                          boot the web profile (same as: dsh web)
  dsh --profile headless "run the tests"     answer one task, print the result, and exit
  ...
`
```

关于参数解析还有一个设计细节：`--profile` 之后的参数解析在**第一个不认识的 token** 处停下，剩下的全部原样转交给被启动的 app 自己解析（这就是为什么 `dsh --profile tui -h` 打印的是 `tui` 应用自己的帮助，而不是 launcher 的帮助）。这个边界具体如何拆分命令行、如何做 Profile 装配，第 03 篇会展开讲。

### Web UI 默认绑定地址：`127.0.0.1:3080`

Web UI 实际监听的 host/port 是在 `dsh-web-app` 这个 bundle 的补丁层里配置的：

```yaml
# packages/bundle/web-app/cordis.patch.yml（节选）
- id: webserver
  name: '@deepseek-ai/dsh-host-webserver'
  inject: [webStartup]
  config:
    host: !!js ctx.webStartup.host ?? '127.0.0.1'
    port: !!js ctx.webStartup.port ?? 3080
```

`!!js` 是 Cordis Loader（`cordis-plugin-include`）识别的一种表达式语法：`ctx.webStartup.host ?? '127.0.0.1'` 在装配阶段会被求值成"如果命令行传了 `--host`，用命令行的值；否则用字面量默认值 `'127.0.0.1'`"。端口同理，默认 `3080`。`--host`/`--port` 这两个 flag 本身在 `dsh-web-app` 自己的启动插件里解析：

```typescript
// packages/bundle/web-app/src/startup.ts（节选）
function webCommand(): Command {
  return new Command()
    .name('dsh --profile web')
    .description('Serve the DeepSeek Harness browser UI.')
    .option('--host <host>', 'bind host')
    .option('--port <port>', 'listen port; pass 0 to let the OS pick a free one')
    .option('--trusted-host <authority...>', 'extra authority the /api browser-trust fence accepts (host or host:port; repeatable)')
    ...
}

export function apply(ctx: Context): void {
  const program = webCommand()
  program.action(() => {
    const options = program.opts<WebOptions>()
    if (options.host === '0.0.0.0') {
      program.error('error: --host 0.0.0.0 is intentionally not supported yet for safety: it would expose remote code execution to the network; use 127.0.0.1 instead')
    }
    ...
  })
}
```

这里能看到一条明确写在代码里的安全策略：**`--host 0.0.0.0` 被显式拒绝**。理由很直白——Web UI 背后是一个可以执行任意 shell 命令的编码 Agent，一旦绑定到 `0.0.0.0`，局域网内任何设备都能访问到这个"远程代码执行入口"。默认只绑定 `127.0.0.1`（仅本机可访问），这不是一个可以随手改掉的配置项，而是代码里的一条硬性校验。

### 第一次会话的心智模型

不管是终端还是浏览器打开 `dsh web` 之后的地址，"用户输入一个任务"到"Agent 开始工作"这条路径的抽象是一致的：

1. **传输层接住请求**：`packages/bundle/web-app/cordis.patch.yml` 里的 `api-gateway`（`@deepseek-ai/dsh-host-apiproxy`）是"每种客户端形态共享的、与传输协议无关的分发面"，浏览器发来的 HTTP/WebSocket 请求经由 `webserver` 绑定的端口，落到这个网关上；
2. **会话被创建或恢复**：网关背后的会话相关能力（`dsh-session`、`dsh-storage`）负责把这次交互对应到一个具体的 `Session`——新会话意味着一条全新的事件日志开始被追加；
3. **Agent 循环开始驱动**：`dsh-agent`/`dsh-agent-loop` 拿到会话后，进入"读取用户消息 → 组装请求 → 调用模型 → 执行工具调用 → 写回会话日志"的循环，这正是后续章节（第 04 章"Agent 核心循环"）要深入拆解的部分；
4. **浏览器端渲染**：`web-app` 补丁层里的一长串 `ui-*` 插件（`ui-conversation`、`ui-tool`、`ui-workflow-run` 等）通过 WebSocket 订阅会话事件，把日志实时渲染成对话界面。

CLI（`apps/cli`）在这条链路里的角色，仅仅是**装配出承载这条链路的插件树，并把命令行参数原样转交给树里的具体插件**——它自己不实现任何"理解任务""调用模型"的逻辑。这也是为什么理解 `dsh` 的运行形态，最终会引向理解 Cordis 这套插件框架本身（第 03 章的主题），而不是停留在 CLI flag 层面。

### `apps/web`：真正跑 Vite 构建的前端工程

值得一提的是，"Web UI"这几个字对应的静态资源并不是 `apps/cli` 自己构建的,而是一个独立的前端工程 `apps/web`：

```json
// apps/web/package.json（节选）
{
  "name": "@deepseek-ai/dsh-web-frontend",
  "description": "Web application entry: vite build over the @deepseek-ai/dsh-client-web shell library; dist/ served by apps/cli's dsh web",
  "scripts": {
    "build": "vite build",
    "dev": "vite",
    "watch": "vite build --watch"
  },
  "dependencies": {
    "@deepseek-ai/dsh-client-web": "workspace:^",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  ...
}
```

它的 `description` 已经写明了关系：这个包用 Vite 把 `@deepseek-ai/dsh-client-web` 这个"浏览器端插件外壳库"打包成 `dist/`，而这个 `dist/` 最终是被 `apps/cli` 的 `dsh web`（也就是 `web-app` 补丁层里的 `web-runtime` 行）解析并托管出来的静态资源。这印证了课程导读里提到的"Host 与 Client 物理分离"——`apps/web` 是纯浏览器端工程，和跑在 Node 里的 `apps/cli` 是两个独立的构建产物，只通过约定好的 `dist/` 路径和运行时 WebSocket 协议衔接。

## 常见问题/易踩坑

- **以为 `dsh web` 和 `dsh --profile web` 是两套实现**：不是，前者是硬编码别名，命令行 flag 解析和装配逻辑完全共享，行为不一致大概率是理解错了参数转发边界。
- **想把 Web UI 暴露到局域网**：目前 `--host 0.0.0.0` 被显式拒绝，这不是 bug，是刻意的安全限制；如果确实需要远程访问，应该走反向代理或 SSH 隧道之类的方案，而不是绕过这条校验。
- **修改了 `apps/web` 的前端代码但页面没更新**：需要确认是走 `pnpm dev:web`（带热更新的开发模式）还是需要先 `pnpm run build:web` 生成新的 `dist/`——生产态的 `dsh web` 托管的是构建产物,不会自动感知源码变化。

## 小结

`dsh web` 和 `dsh --profile web` 是同一件事的两种写法：CLI 层只负责解析参数并选中一个 Profile，真正的"服务器绑定地址""浏览器插件树装配""任务如何变成会话"全部由被选中的 Profile（这里是 `dsh-base` + `dsh-web-app` 两层补丁叠加的结果）决定。下一篇会把 CLI 的三种模式（`profile`/`plugin`/`dump-config`）和 Profile 装配机制本身讲透，包括 `dsh --profile headless "task"` 这种一次性无人值守任务怎么跑起来。
