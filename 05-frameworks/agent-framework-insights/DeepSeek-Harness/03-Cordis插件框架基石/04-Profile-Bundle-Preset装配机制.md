# Profile、Bundle、Preset：dsh 的装配语言

> 前三篇讲的是"一个插件怎么写、插件之间怎么通信、卸载怎么保证干净"——都是单个插件视角的机制。这一篇换到系统视角：一个真实的 `dsh` 进程启动时，到底装配了多少插件、以什么顺序、又是怎么被拆成"可安装的层"的？答案是三个逐层收窄的概念——Bundle 是可安装的补丁层，Profile 是具名的装配结果，Preset 是会话级别的 Agent 组合——它们共同构成了 dsh 的"装配语言"，而 `dsh --dump-config` 就是这门语言的调试器。

## 学习目标

- 理解 Bundle 的本质：一个声明了 `dsh.bundle.patch` 字段的 npm 包，携带一份 Cordis 补丁列表，可以被安装进任意 Profile。
- 理解 Profile 的装配顺序——Bundle 层 → Profile 自己的补丁 → Home 级补丁 → `--patch` 覆盖——以及"后写的层覆盖先写的层"这条统一规则。
- 理解 Preset 是另一个维度的装配：不是"进程启动装配什么服务"，而是"这一次会话的 Agent 拥有哪些工具和提示词"，靠的是 `isolate` 域而不是补丁层覆盖。
- 读一份真实的生产 Preset 文件（`agent.cordis.yml`），理解为什么某些行要放进 `isolate` 分组、某些行不需要。
- 学会用 `dsh --dump-config` 验证"我以为装配出来的树"和"实际装配出来的树"是否一致——这是调试装配问题的第一步，而不是最后一步。

## 背景与设计动机

前三篇建立的机制回答了"一个插件怎么工作"，但没有回答一个更实际的问题：dsh 要同时支持"命令行一次性跑一个任务"（headless）和"起一个本地网页界面持续对话"（web）两种截然不同的部署形态，这两种形态共享绝大多数插件（模型适配器、工具、会话持久化），只在少数几行上不同（要不要起 HTTP 服务器、要不要挂浏览器客户端）。如果每种部署形态都维护一份完整的 `cordis.yml`，维护成本会随着共享插件数量线性增长——共享部分改一次，就要在每份配置文件里同步改一次。

同样的问题在会话粒度上又出现了一次：同一个部署里，不同的对话可能想要不同的 Agent 能力组合——一个专门做代码评审的 Agent、一个专门写代码的 Agent，它们共享"这个部署支持哪些模型、怎么持久化会话"这类进程级配置，但各自拥有不同的工具集合和系统提示词，而且不能互相踩到对方注册的同名服务。

dsh 用两套独立但呼应的机制分别解决这两个层面的问题：**Bundle + Profile** 解决"进程级装配"的复用，**Preset** 解决"会话级装配"的复用与隔离。`docs/architecture.md` 用一句话概括了这套体系存在的理由：

> There is no privileged core to patch: you extend dsh by mounting a plugin beside the others, and registrations are effects that unwind when their plugin unloads.

## 核心机制详解

### Bundle：可安装的补丁层

一个 Bundle 就是一个普通的 npm 包，唯一的特殊之处是它的 `package.json` 里带一个 `dsh.bundle.patch` 字段，指向一份 Cordis 补丁文件。`packages/bundle/base/package.json` 是 dsh 自带的最核心的 Bundle：

```json
// packages/bundle/base/package.json（节选）
{
  "name": "@deepseek-ai/dsh-base",
  "description": "The shared dsh core as a profile bundle: every profile's first patch layer, inserting the base plugin rows over the empty profile root",
  "dsh": {
    "bundle": {
      "patch": "./cordis.patch.yml"
    }
  }
}
```

`dsh.bundle.patch` 指向的文件是一份 YAML，顶层是一个 `insert` 列表，列表里每一行都是一条标准的 Cordis Loader 配置行（`id` + `name` + 可选的 `config`）。`packages/bundle/base/cordis.patch.yml` 的开头几行：

```yaml
# packages/bundle/base/cordis.patch.yml（节选）
- insert:
    - id: timer
      name: '@deepseek-ai/cordis-plugin-timer'

    - id: hmr
      name: '@deepseek-ai/cordis-plugin-hmr'
      config:
        root: ['.']

    - id: llm
      name: '@deepseek-ai/dsh-llm'

    - id: session
      name: '@deepseek-ai/dsh-session'

    - id: agent
      name: '@deepseek-ai/dsh-agent'

    - id: agent-default-model
      name: '@deepseek-ai/dsh-agent-default-model'
      config:
        provider: deepseek-official
        model: deepseek-v4-flash
```

这份文件本身不做任何事情——它只是数据，一份"我要插入哪些行"的清单。dsh 目前自带三个 Bundle，`packages/bundle/README.md` 用一张表说明了它们的分工：

| Package | Role | ctx key |
|---|---|---|
| `base/` | The shared dsh core every profile applies first | — (patch only) |
| `web-app/` | Browser surface: web patch layer + runtime glue plugin | mounts rows |
| `headless/` | Direct one-shot task mode over base, with no Host or Web layer | mounts `headless-runner` |

一个 Bundle 只关心"我要往树里插入哪些行"，完全不关心自己会被安装进哪个 Profile、和哪些其他 Bundle 叠在一起——这正是它能被复用的原因：`dsh-base` 这份补丁同时是 `web` Profile 和 `headless` Profile 的第一层。

### Profile：一个具名的插件树装配

Profile 是"选中哪些 Bundle、以什么顺序叠加、再叠加一份用户自己的补丁"这件事的具名结果。`packages/boot/app-boot/src/profile.ts` 定义了 dsh 自带的两个 Profile 模板：

```ts
// packages/boot/app-boot/src/profile.ts
/** The shipped profile templates auto-initialized on first use, by name. */
export const PROFILE_TEMPLATES: Record<string, readonly string[]> = {
  web: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'],
  headless: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless'],
}
```

`web` Profile 就是"`dsh-base` 加 `dsh-web-app` 这两个 Bundle 按顺序叠起来"，`headless` Profile 是"`dsh-base` 加 `dsh-headless`"——共享的核心能力只维护在 `dsh-base` 一份补丁里，两种部署形态只在各自的 Bundle 里追加自己特有的几行。

真正把多层补丁叠成一棵最终插件树的函数是 `composeEntries`，源码就在同一个文件里：

```ts
// packages/boot/app-boot/src/profile.ts
/**
 * Compose patch layers into the effective entry list over an empty root —
 * the same single `applyEntryPatches` call the boot include makes, so flag
 * derivation and config dumps see exactly what mounts.
 * @param layers - patch lists in application order.
 * @returns the composed entry list.
 */
export function composeEntries(
  layers: readonly PatchOptions[][], warn: (message: string) => void = () => {},
): EntryOptions[] {
  return applyEntryPatches([], structuredClone(layers.flat()), (message: string, ...args: unknown[]) => {
    let index = 0
    warn(message.replace(/%C/g, () => JSON.stringify(args[index++])))
  })
}
```

注释里特意强调了一点值得记住的工程细节：**这个函数和真正启动进程时用的是同一个 `applyEntryPatches` 调用**——也就是说"离线算出装配结果给你看"（比如 `--dump-config`）和"真正启动进程时的装配"走的是完全相同的代码路径，不存在"文档说的和实际跑的不一样"这种偏差。

装配的分层顺序，`docs/architecture.md` 用一句话讲清楚了：

> Layers apply to an empty entry list in this order: each bundle in the profile's listed order, then the profile's `cordis.patch.yml`, then the home-level one, then any `--patch` overlay. A patch targets a row by id and replaces its whole config, or inserts new rows.

翻译成具体规则：Bundle 层最先叠加，Profile 自己的 `cordis.patch.yml`（用户为这一个 Profile 写的覆盖）叠在 Bundle 之上，`$DSH_HOME/cordis.patch.yml`（跨所有 Profile 共享的机器级偏好）再叠一层，命令行传入的 `--patch <file>` 覆盖层最后叠加、优先级最高。**每一层的补丁都是按 `id` 定位一整行、整体替换 `config`，不是逐字段深合并**——`packages/bundle/base/cordis.patch.yml` 开头的注释对这一点讲得很直白：

> A patch replaces the targeted row's whole `config` rather than merging into it, so a row whose value differs by mode does NOT live here: it belongs to each mode bundle.

这也是为什么"哪个模式该有的字段"的判断标准是"这个字段的取值会不会因部署形态而不同"——会不同的字段就不该放在 `dsh-base` 这一层，否则任何一个更上层的覆盖都要把整行重新抄一遍。

### Preset：会话级别的 Agent 组合

Profile 解决的是"这个进程装配了哪些服务"，是进程启动时一次性决定、跨所有会话共享的。而"这一次对话里 Agent 能用哪些工具、系统提示词写了什么"是每个会话可能各不相同的——这正是 Preset 存在的层级。`packages/preset/agent-presets/README.md` 给出的定义：

> A **preset** is a directory holding one `agent.cordis.yml`; the roster mounts it ONCE per process under a standing scope, and each session that names it joins by having its agent scope key parented to the mount's.

关键的机制差异在这里：Preset 不是靠"补丁覆盖"实现隔离的，而是靠上一篇提到的 `isolate` 域。dsh 自带的 `standard` Preset（`apps/cli/config/agent-presets/standard/agent.cordis.yml`）是一份真实的生产文件，摘录其中"计划模式"这一段最能说明问题：

```yaml
# apps/cli/config/agent-presets/standard/agent.cordis.yml（节选）
# Plan state is per-agent by nature, so an entry-local realm is not a
# workaround here — it is the correct lifetime.
- id: planning
  name: cordis:group
  group: true
  isolate:
    planMode: true
  config:
    - id: plan-mode
      name: '@deepseek-ai/dsh-plan-mode'
      config:
        section: |
              You are in plan mode. Stay in plan mode until exit_plan_mode succeeds...
```

`cordis:group` 加 `isolate: { planMode: true }` 的意思是："这个分组内部注册的 `planMode` 服务，只在这个分组自己的作用域里可见，且这个分组每被挂载一次（也就是每个会话加入这个 Preset 一次），就获得一份专属的、互不干扰的 `planMode` 实例"。这正是第一篇提到的 `ctx.isolate(name, label?)` 在生产配置里的用法——不需要写一行 TypeScript，靠 YAML 里的 `isolate` 字段就能声明"这个服务不能是进程全局的，必须一会话一份"。

同一份文件的注释里还展示了反面判断——哪些行**不**应该放进 `isolate` 分组：

```yaml
# apps/cli/config/agent-presets/standard/agent.cordis.yml（节选）
# Only the model-facing controls. The task REGISTRY stays on the host plane:
# ... The registry is keyed by owning agent anyway, so one host instance
# serves every session. What a preset chooses is whether its agent can
# collect and stop background work at all.
- id: tool-jobs
  name: '@deepseek-ai/dsh-tool-jobs'
```

判断标准很清楚：如果一个服务本身已经按会话/Agent 做了内部键控（比如任务注册表内部用 `owning agent` 做 key），那么它天然就该是进程级单例，Preset 只需要决定"这个会话能不能看到操作它的工具"，不需要再套一层 `isolate`——多套一层反而会让浏览器等跨会话读取方看不到这个服务。这也是为什么 `packages/preset/agent-presets/src/mount.ts` 里的 `mountPreset` 会在挂载后主动检查有没有服务"泄漏"到了根作用域：一个本该 `isolate` 却忘了加的服务，会被 `leakedServices()` 检测出来并直接拒绝挂载，而不是留下一个悄悄跨会话共享的 bug。

Preset 的另一个关键差异——它不像 Profile 那样靠补丁覆盖来定制，而是靠**整个目录复制**来定制。`packages/preset/agent-presets/README.md` 写得很明确：

> Authoring is copy-only. A new preset is a whole-directory copy of an existing one — composition, metadata, skill directories, assets — landed under the first `user` root... Everything after creation happens in the preset's own files.

一个 Preset 的可配置服务，通过 `Config` 接口暴露：

```ts
// packages/preset/agent-presets/src/preset.ts
/** Plugin config: which preset is the default, and where presets live. */
export interface Config {
  /** Preset id mounted when a caller names none. Missing at mount time fails loud. */
  default: string
  /** Scanned roots in precedence order; an earlier root wins a duplicate id. */
  roots: PresetRoot[]
  /**
   * Append the harness home's `USER_PRESET_DIR` as a `user` root, after every
   * configured root. False mounts a roster over `roots` alone.
   */
  includeUserRoot: boolean
}
```

`trust: 'system' | 'user'` 这个区分（同一文件里的 `PresetTrust` 类型）也值得留意：系统自带的 Preset 和用户本地复制出来的 Preset 携带不同的信任级别，前者被认为和部署方声明的能力等价，后者"和 shell 访问权限同等信任"——这条注释直白地提醒了一件事：**能自己往 `agent.cordis.yml` 里加一行插件配置的人，等同于能在这台机器上执行任意代码**，Preset 的隔离机制解决的是"会话之间互不干扰"，而不是"防止本地用户做恶意配置"。

### 用 `dsh --dump-config` 验证装配结果

Bundle、Profile、Preset 叠了三层装配逻辑之后，"这次到底装出了什么"很容易和直觉产生偏差——这正是本课程第一章介绍过的 `dsh --dump-config` 存在的意义：它不启动进程，只把 `composeEntries` 算出来的最终树按 YAML 打印出来。`apps/cli/reference/README.md` 描述了它和 `--dump-default-config` 的区别：

> `--dump-default-config` prints only the bundle layers; `--dump-config` adds the profile's `cordis.patch.yml`, the home-level `$DSH_HOME/cordis.patch.yml`, and `--patch` overlays. Both print comments naming the file that supplied each row and every overlay that changed it; `!!js` expressions remain unevaluated, and unmatched patch targets are reported on stderr.

两个命令分别对应"只看共享的核心装配"和"看叠加了我自己所有覆盖之后的最终结果"：

```sh
# apps/cli/reference/README.md
dsh --profile web --dump-default-config
dsh --profile web --patch ./extra.yml --dump-config
```

值得记住的两个细节：**每一行输出都带着"这一行是从哪个文件来的"的注释**——这意味着排查"为什么我期望被覆盖的一行没有生效"时，第一步永远应该是跑一次 `--dump-config`，看那一行最终被标注为来自哪一层，而不是直接去改代码猜测；**没有匹配到任何目标行的补丁会被报告到 stderr**——一个 `id` 写错了的补丁不会被静默忽略，但也不会中止装配，需要主动检查 stderr 才能发现。把这条命令当成本章装配机制的调试器：任何"我以为装出来的树"和"实际跑起来的行为"不一致的时候，先用它把两棵树的差异摊开来看，再回头去查是哪一层补丁、哪一个 Bundle 版本、或者哪一个 Preset 的 `isolate` 分组导致的。

## 常见问题/易踩坑

- **在共享 Bundle 里写了随部署形态变化的字段**：`dsh-base` 的补丁注释已经把这条规则写死——凡是"值会因模式不同"的字段，都不该出现在共享层，否则任何模式专属 Bundle 想要覆盖它，都得把整行 `config` 重新抄一遍，一旦共享层加了新字段，各个模式层就要同步补齐，退化成手工维护的重复劳动。
- **给本该进程唯一的服务套了不必要的 `isolate`**：`standard` Preset 里 `tool-jobs` 那段注释是一个很好的反例参照——如果一个服务的注册表本身已经按 Agent/Session 做了内部键控，给它加 `isolate` 只会让跨会话读取方（比如宿主自己的诊断接口）看不到它，而不会带来任何额外的隔离收益。
- **把补丁覆盖当成深合并**：任何一层补丁替换的是目标行的**整个 `config`**，不是逐字段合并。覆盖一行里的一个字段时，务必先用 `--dump-config` 看清楚这一行当前完整的 `config` 是什么，再把需要保留的字段一起抄进覆盖补丁里，否则会在不知不觉中把没打算动的字段重置成了缺省值。

## 小结

Bundle、Profile、Preset 是同一套"分层装配、按层覆盖"思想在两个不同粒度上的应用：Bundle 是可安装、可复用的补丁层，Profile 把若干 Bundle 按固定顺序叠加成一个具名的进程级装配（再叠上用户自己的覆盖），这一切都建立在第三篇讲过的"注册即副作用"之上——每一层补丁增删的插件行，卸载时都会干净地撤销。Preset 是另一个维度：不靠补丁覆盖，而靠 `isolate` 域把同一份 Agent 组合安全地复用到多个并发会话上，一次挂载、多会话共享，同时保证互不串扰。`dsh --dump-config` 把这套多层装配逻辑的最终结果暴露成一份可读的 YAML，是排查"装配结果和预期不一致"这类问题时最先应该想到的工具，而不是最后的手段。

至此，本章从"一个插件长什么样"（第一篇），到"插件之间怎么通信"（第二篇），到"卸载怎么保证干净"（第三篇），再到"这些插件在系统和会话两个粒度上怎么被组装起来"（本篇），构成了理解 dsh 运行时架构所需要的完整 Cordis 基础——后续章节里出现的任何一个具体子系统，都是在这套基础之上长出来的一棵插件树。
