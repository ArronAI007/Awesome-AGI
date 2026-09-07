# Seam 三元结构精讲：以 shell 为例

> DeepSeek Harness（`dsh`）几乎所有"可替换能力"都遵循同一个三段式骨架——一个只声明契约的 Service Definition、若干个实现契约的 Service Provider、以及一个把契约包装成模型可调用工具的 Consumer。这三者分处不同的包，彼此只通过 Cordis 的 `ctx.<key>` 服务查找耦合，于是"换存储""换沙箱""换模型厂商"就都变成了纯粹的插拔操作，而不是牵一发动全身的重构。本篇用 `packages/shell` 这一个官方文档指定的规范范例，把这套骨架逐层拆开。

## 学习目标

- 理解 dsh 术语表中 `capability-seam`（能力 seam）的精确定义：Service Definition / Service Provider / Consumer 三种角色，以及"seam 是完整能力而不是某一个角色"这一关键区分。
- 通读 `dsh-shell` 包，理解一个 Service Definition 如何用 Cordis 的抽象 `Service` 类而不是 TypeScript `interface` 来声明契约。
- 通读 `dsh-bash-local` 与 `dsh-bash-sandbox` 两个 Provider，理解后者如何通过继承前者、只覆写 `resolve`/`run`/`start` 三个方法就叠加了沙箱能力，而无需重写进程管理逻辑。
- 通读 `dsh-tool-bash` 这个 Consumer，理解它如何只依赖 `ctx.shell` 这一个抽象契约，完全不知道背后到底是本地执行还是沙箱执行。
- 能够把这套三元结构类推到 `fs`、`llm`、`session-persistence`、`web` 等其他能力域，看懂 dsh 的能力地图（capability seam 全景图）。

## 背景与设计动机

Agent Harness 天生要面对大量"同一件事有多种实现方式"的选择：命令要不要跑在沙箱里？会话要落盘到 JSONL 还是 SQLite？大模型走 DeepSeek 官方 API 还是走某个兼容 OpenAI 协议的中转？如果把这些选择直接硬编码在"调用工具"的那层代码里，工具本身就会被迫认识几十种执行细节，任何一次新增实现都要回头改动所有调用点。

dsh 的解法是把"能力"本身当作一等公民抽出来，形成一个独立的中间层。dsh 的术语表 `docs/glossary.md` 对这个中间层给出了精确定义：

> **seam**：一种包含三种角色的*可替换能力*：**Service Definition**（拥有自身 `ctx.<key>` 和词汇类型的 Cordis `Service`——可以是 `ShellExecutor` 这样的抽象类，也可以是 `WebRuntime` 这样的具体注册表，绝不是 TypeScript `interface`）、一个或多个 **Service Provider**，以及一个或多个注入该服务的 **Consumer**。`packages/shell` 是规范范例：`dsh-shell`（Service Definition）、`dsh-bash-local` / `dsh-bash-sandbox`（提供方），以及 `dsh-tool-bash`（Consumer）。

这里有两个容易被忽略但很关键的措辞：

1. Service Definition **必须是 Cordis 的 `Service` 子类**，不是一个纯类型层面的 `interface`。这意味着它天然拥有生命周期（构造、注册为 `ctx.<key>`、可被 `ctx.effect` 处置）、天然享受 Cordis 的重复注册检测（同一个 context 里注册两个同名服务会直接报错），也天然可以携带只读的"能力事实"（比如下文会看到的 `sandboxMode` getter）供 Consumer 在运行时探测。
2. **seam 是三个角色合起来的整体，不是其中任何一个角色的名字**。文档特别强调"该术语仅保留此义，能力成员应按其角色、类、服务、约定或扩展点命名"——也就是说,不应该把某个具体的 Provider 类也叫作"the seam"，这是三元结构里唯一容易混淆但又必须分清的地方。

`packages/shell` 恰好把这三个角色分别放进了三个物理上独立的包，边界清晰到可以逐个对照阅读。下面就按 Service Definition → Provider → Consumer 的顺序把它们过一遍。

## 核心机制详解

### Service Definition：`dsh-shell` 声明的抽象契约

`packages/shell/shell/src/index.ts` 里的 `ShellExecutor` 就是这个 seam 的 Service Definition：

```typescript
// packages/shell/shell/src/index.ts
declare module '@deepseek-ai/cordis' {
  interface Context {
    shell: ShellExecutor
  }
}

/**
 * Abstract bash execution service. Subclass, implement the abstract methods,
 * and load the subclass as a plugin — it registers as `ctx.shell` (one
 * implementation per context; loading a second throws, which is cordis'
 * standard duplicate-service behavior).
 */
export abstract class ShellExecutor extends Service {
  constructor(ctx: Context) {
    super(ctx, 'shell')
  }

  get sandboxMode(): SandboxMode | undefined {
    return undefined
  }

  abstract resolve(request: ShellExecRequest): ShellExecSpec
  abstract run(spec: ShellExecSpec): Promise<ShellRunResult>
  abstract start(spec: ShellExecSpec): ShellProcess
}
```

几个设计细节值得单独说一说：

- **`extends Service` 而不是纯接口**：`ShellExecutor` 是一个抽象类，`super(ctx, 'shell')` 这一行把自己注册成了 `ctx.shell`。任何 Provider 只需要 `extends ShellExecutor` 并实现三个抽象方法，就自动获得了"成为 `ctx.shell`"的资格；如果同一个 context 里同时加载了两个 Provider，Cordis 会在第二次注册时直接抛错——这是"一个 context 只能有一种执行方式"这条不变式的强制手段,不需要额外的业务代码去检查。
- **`declare module` 声明合并**：`interface Context { shell: ShellExecutor }` 是 TypeScript 的模块扩展写法，让 `ctx.shell` 在类型系统里全局可见,同时这个契约类型永远是抽象的 `ShellExecutor`，而不是某个具体 Provider 的类型——这就是为什么下文的 Consumer 完全不需要知道背后到底是哪个 Provider。
- **`resolve`/`run`/`start` 三个抽象方法**划出了契约的最小接口面：`resolve` 把调用方给的"请求"（`ShellExecRequest`，字段基本都是可选的）填充成一个"规范"（`ShellExecSpec`，字段基本都是必填的，超时已经被夹到配置允许的范围内）；`run` 用规范跑一次前台命令并等待结束；`start` 启动一个后台进程并立刻返回句柄。三个方法覆盖了 dsh 里"跑一条 shell 命令"所需的全部语义，不多不少。
- **`sandboxMode` 是一个"能力事实" getter**：默认返回 `undefined`（表示这个执行器不做沙箱隔离），子类可以覆写它。这不是一个业务功能，而是 Consumer 探测"我背后到底有没有沙箱"的观测点——后面在 `dsh-tool-bash` 里会看到它是怎么被用来决定要不要在工具 schema 里暴露 `sandbox_permissions` 参数的。

契约类型本身（`ShellExecRequest`/`ShellExecSpec`/`ShellRunResult`/`ShellProcess`）定义在同包的 `packages/shell/shell/src/types.ts` 里，它们就是这个 seam 的"词汇"——Provider 和 Consumer 之间唯一允许交换的数据形状。比如 `ShellRunResult`：

```typescript
// packages/shell/shell/src/types.ts
export interface ShellRunResult {
  exitCode: number | null
  signal: NodeJS.Signals | null
  timedOut: boolean
  aborted: boolean
  timeoutMs: number
  stdout: CollectedOutput
  stderr: CollectedOutput
  sandbox?: ShellSandboxInfo
}
```

注意 `sandbox?: ShellSandboxInfo` 是可选字段——一个不做沙箱的 Provider（比如下面要看的 `LocalBashExecutor`）根本不会填这个字段；只有沙箱化的 Provider 才会在结果里挂上"这次调用实际跑在什么模式下、有没有被拒绝"的事实。词汇本身就已经在为"可能存在也可能不存在的能力"留好了扩展槽位。

### Provider 一：`dsh-bash-local`，本地进程执行

`packages/shell/bash-local/src/index.ts` 里的 `LocalBashExecutor` 是最基础的 Provider，它把 `ctx.shell` 实现为"在 `ctx.subprocess`（子进程 seam，本身又是另一个 seam）上跑 `bash -c`"：

```typescript
// packages/shell/bash-local/src/index.ts
export class LocalBashExecutor extends ShellExecutor {
  static inject = ['subprocess']

  static Config: z<Config> = z.object({
    cwd: z.string(),
    timeoutMs: z.number().default(120_000),
    maxTimeoutMs: z.number().default(600_000),
    maxOutputBytes: z.number().default(64_000),
    maxSpillBytes: z.number().default(DEFAULT_MAX_SPILL_BYTES),
    graceMs: z.number().default(DEFAULT_GRACE_MS),
  })

  resolve(request: ShellExecRequest): ShellExecSpec {
    const timeoutMs = clampTimeout(
      request.timeoutMs, this.config.timeoutMs, this.config.maxTimeoutMs,
      'bash-local: request.timeoutMs',
    )
    // ...填充 workdir、stdoutMaxBytes、env、dshEnv 等字段...
  }

  async run(spec: ShellExecSpec): Promise<ShellRunResult> {
    return this.runArgv(spec, ['bash', '-c', spec.command])
  }

  start(spec: ShellExecSpec): ShellProcess {
    return this.startArgv(spec, ['bash', '-c', spec.command])
  }
}
```

这里的关键设计是 `runArgv`/`startArgv` 被声明成 `protected` 方法，而 `run`/`start` 只是把公开的 `bash -c` argv 传给它们。这个拆分不是随手为之——它专门是为了让子类只需要替换 argv，就能复用全部进程生命周期、环境变量、输出收集、超时、abort 的机制，这正是下一个 Provider 要做的事。

### Provider 二：`dsh-bash-sandbox`，用继承叠加沙箱能力

`packages/shell/bash-sandbox/src/index.ts` 里的 `SandboxBashExecutor` 不是从零实现 `ShellExecutor`，而是直接继承 `LocalBashExecutor`：

```typescript
// packages/shell/bash-sandbox/src/index.ts
export class SandboxBashExecutor extends LocalBashExecutor {
  static override inject = ['subprocess', 'sandbox', 'sandboxPolicy']

  private readonly mode: SandboxMode

  constructor(ctx: Context, config: Config) {
    super(ctx, config)
    this.mode = ctx.sandboxPolicy.defaultMode
  }

  override get sandboxMode(): SandboxMode {
    return this.mode
  }

  override resolve(request: ShellExecRequest): ShellExecSpec {
    return { ...super.resolve(request), sandboxPolicy: request.sandboxPolicy ?? this.ctx.sandboxPolicy.resolve() }
  }

  override async run(spec: ShellExecSpec): Promise<ShellRunResult> {
    const policy = spec.sandboxPolicy as SandboxExecutionPolicy
    const { mode } = policy
    if (mode === 'danger-full-access') {
      const result = await super.run(spec)
      return { ...result, sandbox: { mode, denied: false } }
    }
    const confined = this.confine(spec.command, { ...policy, mode })
    // ...把 confined.argv 交给继承来的 this.runArgv(spec, confined.argv)...
  }

  private confine(command: string, policy: SandboxPolicy): ConfinedArgv {
    return this.ctx.sandbox.confine(['bash', '-c', command], policy)
  }
}
```

这段代码把"继承式扩展"这个技巧用到了极致：

- `resolve()` 只做一件事——在父类填好的 spec 上补一个 `sandboxPolicy` 字段，其余全部字段的填充逻辑（超时、workdir、env）原样继承。
- `run()` 不是重新实现整套进程管理，而是调用另一个能力 seam（`ctx.sandbox`，将在第三篇详细展开）把原始的 `['bash', '-c', command]` 包装成一个被沙箱限制过的新 argv（`confined.argv`），再把这个新 argv 交给父类继承来的 `this.runArgv`——真正的 spawn、超时、输出收集、SIGTERM/SIGKILL 升级这些机制完全没有重复代码。
- `danger-full-access` 模式（完全放开权限）走的是最短路径：直接调 `super.run(spec)`，连 `confine` 都不调用。
- `sandboxMode` 这个能力事实被覆写成返回真实的默认模式，这样 Consumer 在探测 `ctx.shell.sandboxMode` 时，如果背后挂的是 `SandboxBashExecutor`，就能看到一个具体的 `SandboxMode` 而不是 `undefined`。

这正是"插拔"这个词的字面含义：部署方只需要在组合配置（Cordis 的 `cordis.yml`）里把加载的插件从 `dsh-bash-local` 换成 `dsh-bash-sandbox`，`ctx.shell` 这个键背后的实现就换了，而依赖 `ctx.shell` 的所有 Consumer 代码不需要改一行。

### Consumer：`dsh-tool-bash`，把 seam 包装成模型可调用的工具

`packages/shell/tool-bash/src/index.ts` 里的 `apply()` 函数是这个 seam 唯一的模型侧消费者。它对 `ctx.shell` 的了解仅限于 Service Definition 声明的抽象契约：

```typescript
// packages/shell/tool-bash/src/index.ts
export const name = 'tool-bash'
export const inject = ['tools', 'shell', 'systemPrompt', 'shellEnv']

export function apply(ctx: Context, config: Config = {}): void {
  const backgroundEnabled = config.enableRunInBackground ?? true
  const defaultMode = ctx.shell.sandboxMode
  const escalationModes: readonly SandboxMode[] = defaultMode === undefined ? [] : ESCALATION_TARGETS
  // defaultMode === undefined 时,升级参数(sandbox_permissions/justification)
  // 根本不会出现在工具 schema 里——这是运行时探测"能力事实"驱动 schema 生成的直接体现。

  ctx.tools.register(defineTool({
    name: 'bash',
    description: bashDescription(backgroundEnabled, escalationModes),
    parameters: {
      command: { type: 'string', required: true, description: 'The bash command to execute.' },
      // ...
      ...escalationModes.length > 0 ? {
        sandbox_permissions: { type: 'string' as const, enum: [...escalationModes], /* ... */ },
        justification: { type: 'string' as const, /* ... */ },
      } : {},
    },
    async execute(args: BashToolArgs, exec) {
      // ...
      const result = await ctx.shell.run(ctx.shell.resolve({
        command: args.command,
        // ...
        signal: exec.signal,
      }))
      // ...
      return { kind: 'foreground' as const, ...canonicalBashResult(result) }
    },
  }))
}
```

注意这里 `ctx.shell.resolve(...)` 和 `ctx.shell.run(...)` 两次调用,用的都是 `ShellExecutor` 抽象类上声明的方法名——`dsh-tool-bash` 这个包从头到尾 **不 import** `dsh-bash-local` 或 `dsh-bash-sandbox` 中的任何一个具体类。它甚至不知道自己此刻到底跑在本地执行器上还是沙箱执行器上,唯一能感知到差异的地方就是 `ctx.shell.sandboxMode` 这一个能力事实——如果背后换成了沙箱 Provider,`sandbox_permissions`/`justification` 这两个升级参数就会自动出现在模型看到的工具 schema 里；如果换回本地 Provider,它们就自动消失。**Consumer 的行为随 Provider 变化,但 Consumer 的代码一行都不用改**——这正是三元结构存在的意义。

### 第三个 Provider:不靠继承也能实现同一个契约

`SandboxBashExecutor` 靠继承 `LocalBashExecutor` 复用了几乎全部机制,但这不是唯一的实现路径——`packages/shell/pwsh-local` 提供的 `LocalPwshExecutor` 走的是另一条路:它**不继承** `LocalBashExecutor`,而是直接 `extends ShellExecutor`,独立实现一套几乎和 `bash-local` 逐行对应、但语义细节不同的进程管理:

```typescript
// packages/shell/pwsh-local/src/index.ts
/**
 * Local PowerShell Service Provider for the bash capability seam. Each command runs
 * as `pwsh -NoLogo -NoProfile -NonInteractive -Command <command>` in a managed
 * process spawned through `ctx.subprocess`; ...
 *
 * The command string is passed as ONE argv element to `-Command`: PowerShell
 * itself parses the text, and no intermediate shell exists, so there is no
 * shell-quoting layer to escape (the `bash -c` string domain has no
 * equivalent here). Native Win32 paths (`C:\...`) pass through unchanged.
 */
export const ENV_OVERRIDES = {
  NO_COLOR: '1',
  PAGER: 'cat',
  GIT_PAGER: 'cat',
  // TERM=dumb 是 POSIX 概念,pwsh 场景下故意不设置
} as const

export const ENCODING_PREAMBLE =
  '[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [System.Text.UTF8Encoding]::new($false); '
```

源码注释里专门写明这是"deliberate call-for-call mirror of dsh-bash-local"(刻意逐行对照 `dsh-bash-local` 的镜像实现)——两个包甚至用 `jscpd:ignore` 注释标记了这段"重复"是有意的,而不是代码坏味道。原因很直白:`bash -c` 的字符串世界有 shell 转义规则,而 `pwsh -Command` 直接把整段文本交给 PowerShell 自己解析,两者的参数拼接、编码处理(Windows PowerShell 5.1 默认用系统代码页而非 UTF-8,所以要在命令前拼一段 `ENCODING_PREAMBLE` 显式钉住编码)、环境变量约定(`TERM=dumb` 是 POSIX 概念,pwsh 场景下没有对应物)都不一样,如果强行抽出一个共享基类,反而会把两种截然不同的执行语义硬拗成同一套接口。

这个例子补上了第一个 Provider 例子留下的一个空白:**同一个 Service Definition 完全允许被互不相干的多个实现类分别满足**,继承只是"如果两个 Provider 恰好共享大量机制"时的一种优化手段,不是三元结构本身要求的关系。`ShellExecutor` 抽象类真正强制的只有 `resolve`/`run`/`start` 三个方法的签名,`LocalBashExecutor` 和 `LocalPwshExecutor` 是两条平行的实现路径,`SandboxBashExecutor` 恰好选择了在其中一条路径上做继承式叠加——三者都同等合法地满足着同一个契约。

### 为什么这套结构能让"换实现"变成插拔

把三个角色叠在一起看,能提炼出三条支撑"插拔"的具体机制:

1. **契约类型收敛在 Service Definition 一处**：`ShellExecRequest`/`ShellExecSpec`/`ShellRunResult` 等类型只在 `dsh-shell` 里定义一次,Provider 和 Consumer 都只 import 类型,不 import 彼此的实现类。类型收敛意味着"契约"本身是可以独立审查、独立演进的单一事实来源。
2. **Cordis 的服务查找是运行时的、按 key 索引的**：`ctx.shell` 在类型层面永远是 `ShellExecutor`,在运行时指向哪个具体实例完全取决于部署时加载了哪个插件。这一层间接正是"编译期依赖抽象、运行期绑定具体"的经典依赖倒置,由 Cordis 框架而不是业务代码保证。
3. **能力事实(capability fact)是显式的、可探测的**：像 `sandboxMode` 这样的只读属性,让 Consumer 可以在不知道具体 Provider 类型的前提下,根据"这个能力今天有没有开启"来调整自己的行为(是否暴露升级参数)。这避免了 Consumer 里出现 `if (executor instanceof SandboxBashExecutor)` 这种打破抽象的类型判断。

反过来,这套结构也划出了三个角色各自不能越界的边界：Service Definition 不能包含任何具体执行逻辑(它是抽象类,方法都是 `abstract`);Provider 不能定义新的模型可见接口(它只实现 Service Definition 已经声明的方法);Consumer 不能直接 spawn 进程或触碰沙箱细节(它只能通过 `ctx.shell` 这一个入口)。三个边界叠在一起,就是"能力扩展范式"的完整含义。

### 类推到其他能力域

官方能力地图文档 `docs/capability-seams.md` 用同一张 Mermaid 图和一张大表,枚举了几十个 `ctx.<key>` seam,每一个都遵循相同的三元结构。挑几个和本篇结构对称的例子,方便类推:

| `ctx.<key>` | Service Definition 所在包 | 已知 Provider | 典型 Consumer |
| --- | --- | --- | --- |
| `ctx.shell` | `packages/shell/shell` | `bash-local`、`bash-sandbox`、`pwsh-local` | `tool-bash`、`tool-pwsh` |
| `ctx.fs` | `packages/fs/fs` | `fs-local`、`fs-sandbox`、`fs-e2b` | `tool-fs` |
| `ctx.llm` | `packages/llm/llm` | `llm-deepseek`、`llm-pi-ai`、`llm-replay` | `agent-loop`、`compaction-basic` |
| `ctx.sessionPersistence` | `packages/session/session-persistence` | `session-persistence-jsonl`、`session-persistence-sqlite` | `agent-loop`、`tool-bash` |
| `ctx.web` | `packages/web/web` | `web-search-exa`、`web-search-perplexity`、`web-fetch-http` | `tool-web` |

值得一提的是 `ctx.llm`——它是 Service Definition 和 Consumer 合体在同一个包里的特例:`dsh-llm` 既声明了 `ctx.llm` 这个适配器注册表的契约,又是 `agent-loop` 之外的直接消费方之一。术语表专门提到了这种情况:"角色需要独立演进时通常位于不同包,但属于同一关注点时,一个包也可以承担多个角色"——三元结构讲的是职责边界,不是物理文件数量的强制拆分。

再看 `ctx.fs`:它的三个 Provider 分别对应三种完全不同的运行环境——本地文件系统(`fs-local`)、加了写入围栏的沙箱文件系统(`fs-sandbox`)、E2B 远程 microVM 里的文件系统(`fs-e2b`)。`tool-fs` 这个 Consumer 对这三者的区别一无所知,它调用的永远是 `ctx.fs.read`/`ctx.fs.editText`/`ctx.fs.write` 这几个抽象方法。这也解释了为什么部署方能够在"纯本地跑""本地但沙箱隔离""完全跑在云端 microVM"这三种形态之间自由切换——每一种形态换的都只是 Provider,`tool-fs` 包本身完全不用重新发布。

## 常见问题/易踩坑

**Q:能不能在同一个 context 里同时加载 `dsh-bash-local` 和 `dsh-bash-sandbox`,让部分工具走沙箱、部分工具不走?**

不能。`ShellExecutor` 在构造时用 `super(ctx, 'shell')` 注册为 `ctx.shell`,Cordis 对同一个 key 的重复注册是硬性报错,不是"后注册的覆盖前一个"。这是一处经常被新读者误解的地方:`ctx.shell` 描述的是"这个部署(或者这个 scope)默认怎么执行 shell 命令"这一个全局事实,不是"每个工具各自选择执行器"的路由表。如果确实需要"部分工具沙箱化、部分工具不沙箱化"这种细粒度差异,应该在 Consumer 层(`dsh-tool-bash`)通过 `sandbox_permissions` 升级机制或者按 scope 注册不同的工具实例来实现,而不是试图注册两个 `ctx.shell`。

**Q:`SandboxBashExecutor.resolve()` 里的 `ctx.sandboxPolicy.resolve()` 和 `dsh-tool-bash` 里调用的 `ctx.shell.resolve(...)` 是不是重复解析了两次策略?**

不是重复,是两层不同的默认值。`dsh-tool-bash` 的 `execute()` 会先自己调用 `sandbox.resolvePolicy(...)`(见第三篇的 `SandboxPolicyService`)算出这次调用应该用的策略,并把它放进 `request.sandboxPolicy` 字段传给 `ctx.shell.resolve()`;而 `SandboxBashExecutor.resolve()` 里的 `request.sandboxPolicy ?? this.ctx.sandboxPolicy.resolve()` 只是一个**兜底**——如果调用方(可能是某个不知道沙箱策略细节的内部插件,而不是 `dsh-tool-bash`)没有显式传策略,执行器自己再解析一次部署默认值。这是"Consumer 尽量算好上下文相关的策略,Provider 兜底部署级默认值"这条分层原则的体现,不是浪费的重复计算。

**Q:为什么 `ShellExecSpec` 里超时字段是必填的 `timeoutMs: number`,而 `ShellExecRequest` 里是可选的 `timeoutMs?: number`?**

这正是 `resolve()` 这一步存在的意义——`ShellExecRequest` 是调用方(可能不知道也不该关心具体默认值和上限)的请求形状,`ShellExecSpec` 是"已经填好一切默认值、已经把请求值夹到允许范围内"之后的规范形状。`run`/`start` 两个方法只接受 `ShellExecSpec`,从类型层面就杜绝了"忘记调用 `resolve()` 就直接执行一个字段不全的请求"这类错误——这是用 TypeScript 类型系统在编译期强制一个必须发生的运行时步骤的常见手法。

## 小结与思考题

`packages/shell` 把 Service Definition / Service Provider / Consumer 三种角色分别放进 `dsh-shell`、`dsh-bash-local`/`dsh-bash-sandbox`、`dsh-tool-bash` 四个包,用 Cordis 的抽象 `Service` 类做契约、用继承做能力叠加、用一个只读的能力事实(`sandboxMode`)做运行时探测点。这三条设计决策合起来,让"要不要沙箱化命令执行"从一个需要改动多处调用点的架构决策,变成了部署配置里换一行插件名的操作。dsh 里几十个 `ctx.<key>` seam 全部遵循同一套骨架,理解了 `shell` 这一个例子,就理解了整张能力地图的阅读方法。

思考题:

1. `SandboxBashExecutor` 选择"继承 `LocalBashExecutor`"而不是"独立实现 `ShellExecutor` 再在内部持有一个 `LocalBashExecutor` 实例"。如果换成后一种组合式写法,`resolve`/`run`/`start` 三个方法要怎么重写?两种写法在"未来新增第三个 Provider(比如远程执行器)"时,各自会遇到什么麻烦?
2. `ctx.shell.sandboxMode` 是一个能力事实,而不是一个配置项。如果把它做成配置项(部署方在 `cordis.yml` 里显式声明"这个部署有沙箱"),会破坏三元结构里的哪一条边界?
