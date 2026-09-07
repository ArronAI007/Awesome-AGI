# Skills 机制

> `docs/tools/skills.md` 开篇给 Skill 下的定义很朴素:"Skills are markdown instruction files that teach the agent how and when to use tools. Each skill lives in a directory containing a `SKILL.md` file with YAML frontmatter and a markdown body."——Skill 不是新工具,而是"怎么用工具"的说明书。但 OpenClaw 把这份说明书的加载、过滤、编写、审核、乃至"从对话里自动提炼"这一整条链路都做成了正式机制:七级优先级的加载顺序、按环境/二进制/配置动态过滤的门控规则、一套不允许模型直写 `SKILL.md` 的提案队列(Skill Workshop),以及建立在这套队列之上、边界写得极其克制的"自学习"能力。本篇把这几层拆开讲清楚,重点是"为什么不能让模型直接改 SKILL.md""自学习到底在多严格的条件下才会触发"这两处最容易被简化误读的地方。

## 学习目标

- 能说清一个 Skill 由哪些文件/字段构成,系统按怎样的优先级顺序发现和加载它。
- 理解 `creating-skills.md` 描述的手写 Skill 流程,和 Skill Workshop 提供的"提案—审核—应用"式创作辅助流程的分工边界。
- 精确掌握 `self-learning.md` 描述的机制——它触发的具体前置条件、能做什么、不能做什么,不能把它简化成"系统自动进化"。
- 理解 `skills.entries`、`agents.*.skills`、`metadata.openclaw.requires` 这几层配置如何分别控制"是否加载"“谁能看见”“何时生效”。
- 能结合真实内置 Skill(如 `coding-agent`、`github`、`skill-creator`)的目录结构,说明 SKILL.md 与配套文件(`scripts/`、`examples/`)之间的分工。

## 背景与设计动机

一个 agent 框架迟早会遇到这个问题:工具本身通用(`exec`、`web_fetch`、`browser`),但"在这个项目里该怎么用这些工具"却是高度场景化的知识——比如"改一个 Git 仓库前必须先建隔离 worktree 并验证 HEAD","GitHub PR 只有验证到 `state: MERGED` 才算真正合并完成"。这类知识如果硬编码进系统 prompt,会让 prompt 随着场景数量线性膨胀且难以裁剪;如果完全交给模型临场发挥,又会在同一类任务上反复踩同样的坑。Skill 就是 OpenClaw 对这类"过程性知识"给出的载体:把它们从系统 prompt 中剥离成独立、可复用、可按需加载的 markdown 文件。

但一旦 Skill 变成"可写"的知识,新的问题立刻出现:谁能写、写在哪、写坏了怎么办、模型自己能不能改自己正在用的说明书。OpenClaw 的答案分成两条轨道——人工手写走 `creating-skills.md` 描述的直接文件流程;凡是"agent 生成或修改"的 Skill,一律要经过 Skill Workshop 这道"提案—扫描—应用"关卡,不允许直接落地为生效的 `SKILL.md`。这条设计边界,加上建立在其上的"自学习"能力被反复加了触发门槛和保守判据,构成了本篇要讲清楚的核心命题。

## 核心机制详解

### SKILL.md 的最小构成

`docs/tools/skills.md` 给出的最小可用样例只有两个必填字段:

```markdown
---
name: image-lab
description: Generate or edit images via a provider-backed image workflow
---

When the user asks to generate an image, use the `image_generate` tool...
```

`name`(小写字母/数字/连字符的 slug)和 `description`(一行、供模型和 `$` 选择器发现)是唯一必填项。文档特别注明 frontmatter 先按 YAML 解析,失败则退化为单行解析器;`metadata` 这类嵌套块会被压平成 JSON 字符串再按 JSON5 重新解析——这是为了让 Gating 一节里那种多层嵌套的 `metadata.openclaw` 对象既能写成规范 YAML,也能兼容更随意的写法。正文里可以用 `{baseDir}` 占位符引用 Skill 自己目录下的文件,不需要写死绝对路径。

可选 frontmatter 字段里有三个决定了 Skill 的"可见方式":
- `user-invocable`(默认 `true`):是否作为用户可调用的斜杠命令暴露。
- `disable-model-invocation`(默认 `false`):设为 `true` 后,这条 Skill 的说明不会进入模型的常规 prompt,也不出现在 `$` 选择器里,但一次显式的 `$skill-name` 引用仍然能唤起它——"the flag only hides the skill from model-initiated selection"。
- `command-dispatch: tool`:让斜杠命令绕过模型,直接分发给 `command-tool` 指定的工具。

这三个开关合起来说明一件事:Skill 不是只有"喂给模型当指令"这一种用法,它同时是斜杠命令系统和直接工具分发系统的入口,三者可以独立开关。

### 门控(Gating):让 Skill 只在条件成立时出现

`metadata.openclaw.requires` 决定一条 Skill 在加载时是否"有资格"进入这次会话的目录。文档给的示例:

```markdown
metadata:
  {
    "openclaw":
      {
        "requires": { "bins": ["uv"], "env": ["GEMINI_API_KEY"], "config": ["browser.enabled"] },
        "primaryEnv": "GEMINI_API_KEY",
      },
  }
```

`requires.bins` 要求每个二进制都在 `PATH` 上;`requires.anyBins` 只要求其中一个存在;`requires.env` 要求环境变量存在(进程里或配置里);`requires.config` 要求某个 `openclaw.json` 路径为真值。`os` 是硬平台过滤,`always: true` 可以跳过 `requires.*` 检查但跳不过 `os` 过滤。

内置 `coding-agent` Skill 就是门控的一个真实例子——它的 frontmatter 写着:

```json5
"requires": {
  "anyBins": ["claude", "codex", "opencode"],
  "config": ["skills.entries.coding-agent.enabled"],
}
```

也就是说这条 Skill 同时要求"至少装了一个编码 CLI"和"配置里显式打开了开关"两个条件——`skills.md` 里也确认了这一点:"The `coding-agent` bundled skill is opt-in — set `skills.entries.coding-agent.enabled: true` and ensure one of `claude`, `codex`, `opencode`, or another supported CLI is installed and authenticated"。这是一处刻意的双重保险:即使某台机器上恰好装了 `claude` CLI,只要配置没有显式打开,这条会调起后台编码 agent、能读写 Git 仓库的高权限 Skill 依然不会出现在模型面前。

### 加载顺序:七级优先级与"位置≠可见性"

`docs/tools/skills.md` 给出的加载顺序表(数字越小优先级越高):

| 优先级 | 来源 | 路径 |
| --- | --- | --- |
| 1 | Workspace skills | `<workspace>/skills` |
| 2 | Project agent skills | `<workspace>/.agents/skills` |
| 3 | Personal agent skills | `~/.agents/skills`(仅默认 state) |
| 4 | Managed / local skills | `<state-dir>/skills` |
| 5 | Workshop skills | `<state-dir>/agents/<agentId>/agent/workshop-skills` |
| 6 | Bundled skills / Custodian skills | 随安装包发布 |
| 7 | Extra directories | `skills.load.extraDirs` + 插件 Skill |

同名 Skill 出现在多处时,高优先级覆盖低优先级。这个顺序本身透露了一个设计意图:工作区手写的 Skill 永远能覆盖任何自动生成或社区安装的同名 Skill——即便 Workshop 自学习生成了一条名字冲突的 Skill,只要工作区里有同名文件,加载时依然用工作区那份。

文档专门强调了一句容易被忽略的区分:"Skill **location**(precedence)and skill **visibility**(which agent can use it)are separate controls"。也就是说,一条 Skill 从哪个目录被发现,和某个 agent 能不能看到它,是两套完全独立的判断——后者由 `agents.defaults.skills` / `agents.entries.*.skills` 这层允许列表控制,后面配置一节详细展开。

Skill 根目录还支持分组布局——只要某个配置根下 6 层以内任意位置出现 `SKILL.md` 就会被发现,发现后立即停止向下遍历,`SKILL.md` 所在目录名不影响 Skill 的名字(名字始终来自 frontmatter 的 `name`,缺省才退回目录名)。这意味着团队可以把 Skill 按主题分文件夹整理,不用担心分类目录本身被误当成一个 Skill 名字。

会话开始时,OpenClaw 会对当次会话生效的 Skill 列表做一次快照,并在整个会话生命周期内复用——"OpenClaw snapshots eligible skills **when a session starts** and reuses that list for all subsequent turns"。这解释了为什么改了 Skill 文件或配置后,正在进行的会话不会立刻感知变化,必须开新会话,或者依赖默认开启的文件监听在下一轮对话时刷新快照。

### 创建流程:手写 Skill 的四步

`docs/tools/creating-skills.md` 给出的手写流程很直接:建目录 → 写 `SKILL.md` → `openclaw skills list` 验证已加载(必要时 `/new` 开新会话或重启 Gateway 让快照刷新)→ `openclaw agent --message "..."` 或直接聊天测试。文档给的命名建议是"lowercase letters, digits, and hyphens for `name`""目录名尽量和 frontmatter `name` 保持一致""`description` 一行、160 字符以内"。这条路径面向的是有仓库/工作区文件写权限的人类操作者,不涉及审核流程——因为写的人本来就有权直接改文件。

条件门控的写法和前面 Gating 一节一致;发布到 ClawHub 的流程走 `clawhub skill publish`,需要先确认 `name`/`description`/`metadata.openclaw` 门控字段齐备。这条链路(手写 → ClawHub 发布 → 他人 `openclaw skills install` 安装)是"人写、人审、人分发"的完整闭环,和下面要讲的 Workshop 完全是两条轨道。

### Skill Workshop:一条"提案先行"的创作辅助通道

Skill Workshop 解决的核心问题,`docs/tools/skill-workshop.md` 说得很直接:"agents and operators create a **proposal**(pending draft with content, target binding, scanner state, hashes, and rollback metadata)that becomes a live skill only when applied"。换句话说,凡是走 Workshop 这条路径生成或修改的 Skill,永远先落地成 `PROPOSAL.md`,只有显式 `apply` 之后才会写成生效的 `SKILL.md`——"Apply is the only live write: create, update, and revise never change active skills"。

这套机制解决的具体问题至少有三个:

1. **校验与安全扫描**:`apply` 之前会重跑安全扫描器,只有 critical 级别的发现会拦下应用,warn 级别可见但不阻塞。
2. **可回滚**:`apply` 会先写入 rollback 元数据再落地文件,发生问题可以恢复。
3. **版本一致性**:更新类提案会绑定当前目标 Skill 的哈希,如果目标在提案生成后被别处改动过,提案会自动变成 `stale` 状态,防止"审核的是旧版本、应用的却是新版本"这种错位。

生命周期是一条明确的状态机:`create/update -> pending`,然后可以 `revise`(仍是 pending)、`evaluate`(仍是 pending)、`apply -> applied`、`reject -> rejected`、`quarantine -> quarantined`,或者因为目标被外部改动而变成 `stale`。只有 `pending` 状态的提案能被 revise/apply/reject/quarantine。

Workshop 生成的 Skill 只写入该 agent 专属的 `<state-dir>/agents/<agentId>/agent/workshop-skills` 目录,"create fails if the target already exists in that agent's Workshop directory"——这条边界配合前面的加载顺序表,意味着 Workshop 永远不能覆盖工作区、项目、托管库里已有的同名 Skill,只能在自己的沙盒目录里创建或修改自己创建过的东西。CLI 上对应的是一组显式子命令:

```bash
openclaw skills workshop propose-create --name ... --description ... --proposal ./PROPOSAL.md
openclaw skills workshop inspect <proposal-id>
openclaw skills workshop evaluate <proposal-id>
openclaw skills workshop apply <proposal-id>
```

`evaluate` 这一步值得单独说一下:它会调用"live Gateway plugin registry"里注册的 `skill_proposal_evaluate` 钩子,插件可以对候选提案(更新类还会拿到完整的基线 Skill)返回带归因的发现、指标,以及可选的 `pass`/`revise`/`block` 决定——只有 `block` 能真正拦下 `apply`。这一层设计把"Workshop 本身"和"具体校验规则"解耦:Workshop 只负责提案存储和生命周期,校验逻辑可以由插件按需扩展,`skills.proposals.events.list` 还能让外部编排系统消费提案事件、按 `revisionHash` 精确评估——但文档明确说"OpenClaw does not schedule, auto-revise, or decide when such a loop should stop",这类外部优化循环需要调用方自己搭。

聊天里最常用的入口是 `/learn`:不带参数时,让 agent 从当前对话里提炼可复用流程;带路径/URL/关键词时,把这些来源当作素材。`/learn` 只会去修订一个匹配的 pending 提案,或者更新一个匹配的已生效 Skill,找不到匹配才新建提案——并且"`/learn` never applies it",提案永远停在 pending,需要人工或 `auto` 模式的自动应用流程接手。

### 自学习(self-learning):严格限定条件下的一条后台复查通道

这是最容易被夸大成"系统自动进化"的一块,必须以文档原文为准精确复述。`docs/tools/self-learning.md` 定义了两条完全独立的路径。

**第一条:即时修复(Immediate repair)**,发生在前台 agent 自己的当前对话轮次里——"When the foreground agent discovers that a skill it used is wrong or incomplete, it reads the current live skill and drafts a targeted patch through Skill Workshop in the same turn"。这条路径仍然要走 Workshop 的提案存储、哈希绑定、安全扫描器和回滚元数据,只是发生得比较"即时"。它改的是新会话会加载的活跃 Skill,"It does not rewrite the skill snapshot already loaded into the running session"——也就是说,当前这个正在运行的会话,即使自己刚刚修好了一条 Skill,本轮剩余的对话里用的还是旧快照。

**第二条:体验复查(Experience review)**,是一次"detached background review",触发条件写得非常具体,文档列出了六个必须同时成立的门槛:

- 前台这一轮"completed 或被中断,但没有以 provider 或 prompt 错误结束"(以 provider/prompt 错误收尾的轮次永远不会安排复查,因为这被判定为"transient environment noise");
- 当前这一轮至少经过了 10 次模型迭代;
- 这是一次"eligible foreground conversation",明确排除 cron、heartbeat、memory、overflow、hook、subagent、review 这些内部运行;
- 运行时(runtime)必须报告了已解析的 provider、model,以及 `skill_workshop` 的实际可用性;
- 系统已经安静了 30 秒;
- 没有其他 agent 或 reply 运行仍在进行中。

即便所有前置条件都满足,复查是否真的产出结果还要过一道"保守判据":文档给的标准是"a concrete recovery pattern or a stable procedure that would remove at least two future model or tool calls"——一个能救回未来至少两次模型/工具往返的具体可复现的procedure,而不是任何看起来"有用"的内容。文档同时列出了应该主动放弃(abstain)的情形:一次性请求、个人事实和简单偏好、临时环境或服务故障、没有具体证据支撑的泛泛建议、未经证实的负面断言,以及秘密和凭据材料。这条"宁可不产出也不能滥产出"的判据,是整个自学习机制里最核心的保守设计。

复查一旦被排上,行为完全由 `skills.workshop.autonomous.mode` 决定,这是三选一而不是开关:

| 模式 | 行为 |
| --- | --- |
| `off` | 不创建体验复查的捕获 |
| `propose` | 只能调用 `skill_workshop`,最多暂存一个 create/patch/update/revision 提案,永远停在 pending,不会自动应用 |
| `auto`(默认) | 用普通的 agent 文件工具(目录、文件、patch、shell)直接维护 Workshop 目录里的 Skill,不经过提案存储、不跑安全扫描、不生成自动回滚快照 |

这里有一处极容易被误读的地方需要澄清:`auto` 模式听起来"权限更大",但它换来的是**跳过 Workshop 的提案层**,直接用普通文件工具编辑——这不是"AI 获得了额外权限",而是"复查这次运行沿用了发起它的那个前台会话本来就有的权限模式、工具限制和 shell 审批策略",文档原话是"the run preserves the source session's permission mode, tool restrictions, and shell approval policy. Conversation evidence does not grant extra access"。也就是说 auto 模式下的自我维护,能做的事情上限就是"这个 agent 平时能做的事",没有因为是"自学习"就获得任何额外授权。

复查的动作范围被限定得很窄:文件工具的根目录锁死在该 agent 的 Workshop 目录,不能碰工作区、托管库或其他来源的 Skill;每次复查只有一次尝试机会,失败就记为失败,不会自动重试;它遵循的编辑准则和每周一次的"collection review"(集合复查)完全一样——"audit before editing, give a procedure one home, preserve distinct tasks, and verify the resulting files"。换句话说,自学习不是一个独立的"进化算法",而是复用了 Workshop 集合维护本来就有的那套编辑纪律,只是触发时机和证据来源不同。

最后两点边界同样重要:一是复查是"detached"的——它的对话内容不会进入前台会话的 transcript 或 session 记录,前台的回答不会等它跑完;二是复查会把符合条件的对话内容(包括工具输入输出)发给配置的模型 provider 做一次额外的模型调用,文档专门加了一条警告:"Choose a provider and mode that match the workspace privacy and data-handling requirements"。这不是隐性发生的免费操作,而是有明确的成本和隐私边界的一次显式模型调用。

不满意某次捕获,可以直接拒绝:

```bash
openclaw skills workshop reject <proposal-id> --reason "Not reusable"
```

或者把模式调回 `propose` 逐条人工审核,乃至 `off` 完全关闭。

### 配置项:三层控制——是否加载、谁可见、怎样授权

`docs/tools/skills-config.md` 把 Skill 相关配置划成了几个正交的维度。

**是否加载 / 是否启用**(`skills.entries.<key>`):

```json5
{
  skills: {
    entries: {
      "image-lab": {
        enabled: true,
        apiKey: { source: "env", provider: "default", id: "GEMINI_API_KEY" },
        env: { GEMINI_API_KEY: "GEMINI_KEY_HERE" },
        config: { endpoint: "https://example.invalid" },
      },
      sag: { enabled: false },
    },
  },
}
```

`enabled: false` 可以强制关闭一条内置或已安装的 Skill,即使它的门控条件本来满足;`apiKey`/`env` 是为该 Skill 单独注入密钥或环境变量,但**只作用于宿主进程这一次 agent 运行**,不会进入沙盒——`skills.md` 里专门给了这条 Warning:"Env injection is scoped to the **host** agent run, not the sandbox"。想让沙盒内的 Skill 用到密钥,需要单独在 `agents.defaults.sandbox.docker.env` 里配置。

**谁能看见**(`agents.defaults.skills` / `agents.entries.*.skills`):

```json5
{
  agents: {
    defaults: { skills: ["github", "weather"] },
    entries: {
      writer: { default: true },        // 继承 github, weather
      docs: { skills: ["docs-search"] }, // 完全替换默认列表
      "locked-down": { skills: [] },     // 不暴露任何 Skill
    },
  },
}
```

这层允许列表遵循"不合并、只替换"的规则——一旦某个 agent 显式写了非空的 `skills` 列表,它就是这个 agent 能看到的**最终**集合,不会和 `defaults` 叠加。文档特别提醒这不是主机层面的授权边界:"This is not a host shell authorization boundary. If the same agent can use `exec`, constrain that shell separately"——允许列表只影响 Skill 的可见性(prompt 拼装、斜杠命令发现、沙盒同步、快照),真正的执行权限还要靠 `exec` 自己的策略去卡。

**`skills.allowBundled`** 是单独针对**内置** Skill 的一个白名单,设置后只有列表里的内置 Skill 才有资格,托管库和工作区 Skill 不受影响——这是专门给"想精简内置目录但不想动其他来源"的场景准备的开关。

**Workshop 相关**(`skills.workshop.*`)前面已经讲过 `autonomous.mode`;另外两个值得记住:`approvalPolicy`(默认 `"auto"`,agent 发起的 apply/reject/quarantine 不需要额外审批提示;设为 `"pending"` 则每次都要人工确认)和 `maxPending`(每个 agent 最多同时保留多少 pending/quarantined 提案,默认 50,范围 1–200)、`maxSkillBytes`(提案正文字节上限,默认 40000,自主生成的提案还额外有 10000 字符的硬上限)。

这三层配置合起来构成一个清晰的心智模型:`metadata.openclaw.requires` 决定 Skill 本身"有没有资格存在"(环境/二进制/配置层面),`skills.entries.<key>.enabled` 是运营者对单条 Skill 的强制开关,`agents.*.skills` 决定"这个 agent 能不能看见它",而 `skills.workshop.*` 专门管理"自动生成的那部分 Skill 走多快、审得多严"。四个维度互不覆盖,同时生效。

### 真实内置 Skill 的目录结构佐证

抽查素材根目录下 `skills/` 里的几个内置 Skill 可以直接验证前面讲的结构。最简单的两个——`skills/coding-agent/` 和 `skills/github/`——都只有一个文件:

```text
skills/coding-agent/SKILL.md
skills/github/SKILL.md
```

`coding-agent/SKILL.md` 的 frontmatter 正是前面 Gating 一节引用的双重门控示例(`requires.anyBins` + `requires.config`),正文则是一份非常具体的操作手册——强制 `background:true`、Codex 要用独立的 `CODEX_HOME` 认证目录、必须在合并 PR 前验证 Git worktree 的初始 `HEAD`、完成后必须用 `openclaw message send` 主动上报而不能依赖心跳。这说明"轻量、纯 markdown、无配套文件"完全是一种合法且常见的 Skill 形态——不是所有 Skill 都需要脚本。

更复杂一点的例子是 `skills/skill-creator/`:

```text
skills/skill-creator/SKILL.md
skills/skill-creator/license.txt
skills/skill-creator/scripts/quick_validate.py
skills/skill-creator/scripts/package_skill.py
skills/skill-creator/scripts/test_quick_validate.py
skills/skill-creator/scripts/test_package_skill.py
```

它的 `SKILL.md` 正文里直接引用了同目录下的脚本——"Run `python {baseDir}/scripts/quick_validate.py <skill-directory>`"——这正是前面提到的 `{baseDir}` 占位符的真实用法:Skill 正文不写死路径,而是相对自己的目录引用配套脚本。有意思的是,这条 Skill 本身讲的就是"如何创建/校验其他 Skill",它的第 4 步"Draft and persist"里明确写着"Live workspace skill: use `skill_workshop` to create or revise a pending proposal; keep live files unchanged until apply"——也就是说,连"教模型怎么写 Skill"这条 Skill 自己都遵循"生成类内容必须走 Workshop 提案"这条规则,而不是教模型绕过它直接写文件。

另一个例子 `skills/taskflow/` 的目录是:

```text
skills/taskflow/SKILL.md
skills/taskflow/examples/pr-intake.lobster
skills/taskflow/examples/inbox-triage.lobster
```

配套文件放进了 `examples/` 子目录——这和 `docs/tools/skill-workshop.md` 里对 Workshop 支持文件的约束(必须落在 `assets/`、`examples/`、`references/`、`scripts/`、`templates/` 之一)是同一套目录约定,说明手写 Skill 和 Workshop 生成 Skill 在支持文件的组织方式上遵循同一套规范,只是落地路径(工作区 vs. agent 专属 Workshop 目录)不同。

## 常见问题/易踩坑

**Q:模型能不能自己直接改一条正在用的 `SKILL.md`?**

不能,至少在"生成/修改类"场景下不能。文档明确规定 Agent 必须用 `skill_workshop` 工具来做这类工作,"must not create or change skill or proposal files directly during foreground authoring"。唯一的例外是每周一次的集合复查(collection review)和 `auto` 模式下的自学习复查——这两者被明确授权用普通文件工具直接编辑 Workshop 目录,但活动范围也被限制在该 agent 自己的 Workshop 目录里,不能碰工作区或托管库里的 Skill。

**Q:自学习是不是意味着 agent 会持续、自动地变得更强?**

不是这个含义。它是一条有严格前置门槛(至少 10 次模型迭代、非错误结束、30 秒静默期等六个条件)、且要求"能省下至少两次未来调用"这条保守判据才会产出结果的后台复查;绝大多数普通对话根本不会触发它,触发了也可能因为证据不够而"abstain"不产出任何东西。它改的是新会话会加载的 Skill 集合,不会回头修改当前会话已经加载的快照。

**Q:`auto` 模式下自学习是不是获得了比平时更大的权限?**

没有。`auto` 模式换掉的是"走不走 Workshop 提案层"这件事(跳过提案存储、扫描、回滚快照,改用普通文件工具),但它依然沿用发起它的那次前台会话原有的权限模式、工具限制和 shell 审批策略——"Conversation evidence does not grant extra access"。

**Q:Skill 允许列表(`agents.*.skills`)能不能当作安全边界用?**

不能单独依赖它。它只控制 Skill 在 prompt、斜杠命令、沙盒同步里的可见性,不是主机层面的授权边界——如果同一个 agent 还能用 `exec`,那么真正的操作权限还是要靠沙盒隔离、OS 用户隔离、`exec` 自己的允许/拒绝名单去卡。

## 小结

一条 Skill 的最小构成只是"目录 + `SKILL.md`(`name` + `description` 必填)",但围绕它的加载顺序(工作区 > 项目 > 个人 > 托管 > Workshop > 内置/Custodian > 额外目录)、门控条件(`requires.bins`/`env`/`config`/`os`)、可见性开关(`user-invocable`/`disable-model-invocation`/`command-dispatch`)构成了一套完整的动态过滤系统。手写 Skill 走的是"建目录、写文件、验证加载"的直接流程;而任何"agent 生成或修改"的 Skill 都必须经过 Skill Workshop 的提案队列——先落地成 `PROPOSAL.md`,经过安全扫描和哈希绑定校验,只有显式 `apply` 才会写成生效的 `SKILL.md`。建立在 Workshop 之上的自学习能力,边界写得极其克制:它只在六项前置条件同时成立、且判据达到"能省下至少两次未来调用"的门槛时才会产出一条待审提案或一次直接维护性编辑,`propose`/`auto`/`off` 三档模式控制的是"要不要经过人工确认",而不是"要不要给模型更大权限"。`skills.entries`、`agents.*.skills`、`skills.workshop.*` 这三层配置分别管住了"是否加载""谁能看见""自动生成的部分审得多严",四个维度互不覆盖。下一篇转向 Plugin SDK:当 Skill 已经能教会 agent"怎么用工具"之后,OpenClaw 是怎么用插件系统给 Gateway 本身注入新工具、新 Provider、新 Channel 这两类完全不同形态的扩展能力的。
