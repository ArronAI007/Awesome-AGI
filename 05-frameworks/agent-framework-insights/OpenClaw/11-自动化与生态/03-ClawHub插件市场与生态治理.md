# ClawHub 插件市场与生态治理

> `VISION.md` 里有一句话几乎可以当作 OpenClaw 整个仓库工程决策的判据:"Two layers, two bars."(两层,两套标准)。核心(core)里的每一个工具、每一行 prompt、每一个配置键,都会被打到每一次模型请求上,所以审查必须最严;插件(plugin)、skill、channel、app 不背这份税,所以鼓励在那里增长。这句话不是一句公关口号——它直接决定了一条 PR 会被合并、被要求改造成插件、还是被直接拒绝。本篇要做的是把这条哲学从 `VISION.md` 的文字落到三个可验证的地方:插件清单里"核心 59 个、外部 91 个"这个真实的数字分布;`openclaw plugins install` 在真正安装一个第三方包之前做的那套 capability consent 审查;以及核心代码库自己用一张兼容性注册表,有纪律地把旧路径"做减法"退场,而不是无限堆积。ClawHub(`https://clawhub.ai/`)在这整条链路里的角色,不是"锦上添花的插件商店",而是这套治理哲学能够落地的具体执行面——发现、官方发布者身份、来源与安全审查都汇聚在这一个入口上。

## 学习目标

- 能完整复述"Two layers, two bars"这条设计原则,并说出它对应的两个具体后果:核心 PR 的审查标准更严,插件/skill/channel/app 的准入门槛更低。
- 理解"Recurring demand defines interfaces"这条规则解决的是什么问题——当多个独立 PR 反复实现同一类能力时,正确的响应是把它抽成一个契约放进核心或 SDK,让候选实现改为对着这个契约做插件,而不是持续接受重复实现的 PR。
- 能用 `docs/plugins/plugin-inventory.md` 里的真实数字说明"核心保持精简"不是一句口号,而是一套持续被 CI 生成校验的清单事实。
- 理解 ClawHub 在整套治理里具体承担的三件事:插件发现(discover/search)、官方发布者身份(official catalog)、来源与安全审查(capability consent + provenance)。
- 理解核心代码库如何用一张状态化的兼容性注册表(`active`/`deprecated`/`removal-pending`/`removed`)有纪律地退役旧路径,这是"核心保持精简"在时间维度上的对应机制。

## 背景与设计动机

几乎所有能被第三方扩展的系统,迟早都会面对同一个压力:新功能的需求源源不断,而核心代码库的复杂度只会单调递增,除非有人主动做减法。大多数项目要么放任核心膨胀("这个功能很有用,先塞进去再说"),要么用一刀切的"我们不接受新功能"来自我保护,两种做法都不可持续。OpenClaw 在 `VISION.md` 里给出的答案不是一刀切,而是一条**分层的成本模型**:承认"核心"和"插件"其实是两种完全不同经济性的容器,核心的每一次增加都会被复制到每个用户的每一次模型请求上(prompt token、工具定义、配置解析都要摊在这个成本里),插件的增加则只影响真正启用它的那部分用户。一旦承认这个成本不对称是真实存在的,后面所有的准入规则都可以从这一条经济学事实推导出来,而不需要诉诸主观的"我们不喜欢这个功能"。

这条分层哲学如果只停留在 `VISION.md` 的文字里,很容易变成一句没有约束力的口号。OpenClaw 把它落到了三个可以被读者自己验证的地方:一份持续由脚本生成、任何人都能核对的插件清单(证明核心真的没有无限膨胀);一套安装时刻的 capability consent 流程(证明"信任"这件事是显式审查出来的,不是默认给的);以及一张状态化的兼容性注册表(证明核心不仅"不轻易新增",还会有纪律地"主动做减法")。ClawHub 是这三件事共同的落地入口——它既是插件被发现的地方,也是官方身份被记录的地方,也是安装前来源审查所依赖的可信记录来源。

## 核心机制详解

### Two layers, two bars

`VISION.md` 原文把这条原则讲得很直白:

```
Two layers, two bars.
The core carries a per-call tax: each core tool, prompt line, and config key
reaches every operator on every model request, so additions there face the
strictest scrutiny. Plugins, skills, channels, and apps carry no such tax, and
we want that surface to keep growing.
When our contribution rules read as hostile to a feature, re-check the layer:
usually they object to where it plugs in, not to the feature existing.
```
—— `VISION.md`

最后一句是这条原则里最容易被忽略、却最实用的一句:当一个贡献者觉得 OpenClaw 的贡献规则"对某个功能很不友好"时,真正需要重新检查的往往不是"这个功能该不该存在",而是"它被接入的位置对不对"。同一个功能,如果试图作为核心工具/核心 prompt/核心配置项落地,可能会被严格挡下;但完全相同的功能,如果改成一个插件、一个 skill、一个 channel,大概率会被欢迎。这条区分直接体现在插件体系的两种风格划分上:

```
There are two broad plugin styles:

- Code plugins run OpenClaw plugin code and are appropriate for deeper
  runtime extension.
- Bundle-style plugins package stable external surfaces such as skills, MCP
  servers, and related configuration.

Prefer bundle-style plugins when they can express the capability. They have a
smaller, more stable interface and better security boundaries.
```
—— `VISION.md`

也直接体现在"What We Will Not Merge (For Now)"这份清单里——它的第一条就是"New core skills when they can live on ClawHub"(新的核心 skill,只要能放到 ClawHub 上,就不会被合并进核心),后面还有"Heavy orchestration layers that duplicate existing agent and tool infrastructure"(重复已有 agent/tool 基础设施的重型编排层)、"Cloud-based sandbox providers as OpenClaw plugins; implement provider support in Crabbox instead"(云端沙箱 provider 不作为 OpenClaw 插件接入,应该去 Crabbox 项目实现)。这些条目乍看是在"拒绝功能",细读会发现它们拒绝的都是**接入位置**,而不是能力本身——文档甚至在清单末尾补了一句"This list is a roadmap guardrail, not a law of physics. Strong user demand and strong technical rationale can change it.",承认这是一份治理策略而非教条。

### Recurring demand defines interfaces

如果说"两层两标准"回答的是"新功能应该往哪儿放",那么"Recurring demand defines interfaces"回答的是一个更进阶的问题:当同一类需求被反复提出、反复实现的时候,该怎么办?

```
Recurring demand defines interfaces.
Once several independent PRs or requests wire in the same kind of
capability, the right response is a contract, not a queue of merges: land
the seam in core or the SDK, port the bundled implementation onto it, and
let the remaining candidates ship as plugins against it.
```
—— `VISION.md`

这条规则的关键词是"a contract, not a queue of merges"(一份契约,而不是一队排队合并的 PR)。如果三个不同的贡献者都想给 OpenClaw 加一个"云端沙箱 provider",正确的做法不是把这三个 PR 都合并进核心(那样核心会积累三套几乎重复的沙箱管理代码),也不是简单粗暴地都拒绝(那样会浪费三份真实存在的需求信号),而是把"沙箱 provider"这件事本身抽象成一个稳定的契约接口,放进核心或 SDK 里,然后让已有的实现改造成对着这个契约的插件,后续候选者也对着同一个契约提交插件即可——核心因此只多了"一个接口"的重量,而不是"N 个具体实现"的重量。这正是上一篇里 Task Flow 这层编排契约存在的理由之一:当 ACP 派生、subagent 派生这类"detached background work"反复需要一套跟踪机制时,正确答案是把"tasks + Task Flow"这套契约沉淀进核心,而不是让每一种派生执行各自维护一套跟踪逻辑。

### 用真实数字验证"核心保持精简"

`docs/plugins/plugin-inventory.md` 是一份由脚本(`pnpm plugins:inventory:gen`)持续生成的清单,不是手写维护的静态文档,这一点本身就保证了它不会因为疏忽而失真。它把所有插件分成三层:

```
## Definitions

- Core npm package: built into the `openclaw` npm package and available
  without a separate plugin install.
- Official external package: OpenClaw-maintained plugin omitted from the
  core npm package, kept in this official inventory, and installed on
  demand through ClawHub and/or npm.
- Source checkout only: repo-local plugin omitted from published npm
  artifacts and not advertised as an installable package.
```
—— `docs/plugins/plugin-inventory.md`

截至这份文档生成时,三层的数字分布是核心 npm 包 59 个、官方外部包 91 个、仅源码检出 3 个——**外部包数量比核心里多出足足 32 个**,这不是巧合,而是"两层两标准"被持续执行的结果:模型 provider(OpenAI、Anthropic、Google、xAI 之外的几十家)、绝大多数 channel(Discord、Slack、Matrix、Mattermost、IRC、Nostr、Zoom Meetings……)、几乎所有 TTS/STT 供应商,默认都不在核心包体积里,只有在用户显式选择时才通过 `openclaw plugins install` 拉进来。连 Workboard 这样一个已经"included in OpenClaw"、随核心包一起分发的插件,也仍然默认禁用("Workboard is bundled but disabled by default"),需要用户显式 `openclaw plugins enable workboard` 才会真正加载——即便是"已经在核心包体积里"的能力,也不代表它默认打到每一次请求上。

### ClawHub 在这条治理链路里的三个具体角色

**发现**:`docs/plugins/community.md` 把 ClawHub 定义为"the primary discovery surface for public community plugins"。Control UI 的 Discover 标签页会内联查询 ClawHub(`https://clawhub.ai/plugins`),CLI 有对应的 `openclaw plugins search "calendar"`。这解决的是"核心保持精简"之后必然出现的副作用——能力分散在几十上百个外部包里,用户需要一个统一的地方去找。

**官方发布者身份**:`docs/plugins/plugin-inventory.md` 明确区分"OpenClaw-maintained"(官方维护)和第三方社区插件,`docs/plugins/community.md` 给出的发布前检查清单里专门要求"Active maintenance"(活跃维护)和"Public GitHub repo"(公开仓库,便于源码审查),发布命令本身也要求显式声明 owner scope:

```
clawhub package publish your-org/your-plugin --dry-run
clawhub package publish your-org/your-plugin
```

发布之后"ClawHub validates owner scope, package name, version, file limits, and source metadata before creating a release, then keeps new releases hidden from normal install and download surfaces until review and verification finish"——新发布的版本在通过审查之前,默认对普通安装和下载入口不可见。

**来源与安全审查**:这是三者里工程实现最深的一环,直接体现在 `openclaw plugins install`/`enable` 的安装时刻行为里。`docs/plugins/manage-plugins.md` 描述了一套"capability consent"机制——安装或启用一个第三方插件前,OpenClaw 会展示它声明的 channel、provider、tool、hook、MCP server、CLI 命令、skill,以及任何危险配置项,要求操作者显式确认:

```
OpenClaw asks you to review a third-party plugin's declared capabilities
before installing or enabling it. The consent screen identifies the plugin,
its version and source, artifact integrity, and available trust information.
```
—— `docs/plugins/manage-plugins.md`

但这套审查对"已验证的官方目录插件"有一条明确的豁免,而这条豁免本身就是 ClawHub 存在意义的直接证明——豁免的前提不是"插件 id 恰好和官方名字一样",而是必须能对上 ClawHub 记录的真实来源:

```
Outside AI onboarding, bundled plugins and verified first-party plugins from
OpenClaw's official catalog do not require this capability review during
install, enable, update, or Doctor repair. For separately installed
first-party plugins, OpenClaw checks the actual package identity against
its catalog and verified npm source record or official-channel record from
`https://clawhub.ai`. A matching plugin id or package name alone is
insufficient: local copies, archives, git installs, custom ClawHub
registries, and conflicting source records still require review.
```
—— `docs/plugins/manage-plugins.md`

换句话说,"官方身份"不是一个可以被随意声明的字符串标签,而是需要在 ClawHub 或者 npm 的可验证来源记录里对得上号——一个从本地路径、archive、或者自定义 ClawHub registry 装进来的、id 恰好叫"telegram"的包,并不会自动继承"telegram"官方插件的信任豁免,仍然要走完整的 capability consent 审查。这套设计把"信任"从"名字匹配"提升成了"来源可验证",是 ClawHub 承担"来源与安全审查"职责最直接的证据。

审查记录本身也不是一次性的——它对"插件声明的能力面"做哈希,而不是对可执行文件本身做哈希:

```
The review token hashes the exact declared capability surface, not the
plugin's executable files. Acceptance separately records installer-provided
artifact integrity when available.
```
—— `docs/plugins/manage-plugins.md`

这意味着如果一次更新只是修 bug、没有扩大声明的能力面,已有的用户同意可以被复用;但只要新版本声明了额外的能力(新增一个 channel、新增一个危险配置项),就必须重新走一遍审查——这是"信任不会随版本升级被悄悄放大"的具体实现。

### 依赖治理:核心只管生命周期,插件自己管依赖图

"核心保持精简"不只体现在功能层面,也体现在依赖管理的责任划分上。`docs/plugins/dependency-resolution.md` 把这条边界写得非常干脆:

```
OpenClaw handles plugin dependencies at install/update time only. Runtime
loading never runs a package manager, repairs a dependency tree, or mutates
the OpenClaw package directory.
```
—— `docs/plugins/dependency-resolution.md`

OpenClaw 核心只负责插件的**生命周期**——发现来源、按需安装/更新、记录安装元数据、加载入口、在依赖缺失时给出可操作的报错;插件包自己的运行时依赖(`dependencies`/`optionalDependencies`)完全由插件自己的 `package.json` 声明和维护,核心不会替它修复依赖树,也不会在运行时悄悄拉起一个包管理器。这条边界同样是"两层两标准"的延伸:如果核心要为每一个插件的依赖图负责,核心自身的复杂度和故障面会随插件数量线性甚至超线性增长;把依赖图的所有权下放给插件本身,核心需要保证的只是"发现-安装-加载"这一条稳定契约。

### 兼容性注册表:核心如何有纪律地"做减法"

"核心保持精简"不是一次性打扫,而是需要持续对抗代码天然的堆积倾向。OpenClaw 用一张状态化的兼容性注册表(`src/plugins/compat/registry.ts`,记录定义在 `src/plugins/compat/types.ts`)把每一条历史遗留的兼容路径都显式建档:

```ts
// src/plugins/compat/types.ts:1-24(节选)
type PluginCompatStatus = "active" | "deprecated" | "removal-pending" | "removed";

export type PluginCompatRecord<Code extends string = string> = {
  code: Code;
  status: PluginCompatStatus;
  owner: PluginCompatOwner;
  introduced: string;
  deprecated?: string;
  warningStarts?: string;
  removeAfter?: string;
  removalGate?: "next-plugin-sdk-major";
  replacement?: string;
  docsPath: string;
  ...
};
```

每一条记录都必须声明"谁拥有它"(`owner`:sdk/config/setup/channel/provider/plugin-execution/agent-runtime/core)、什么时候引入、是否已经废弃、废弃后的替代方案指向哪里。`docs/plugins/compatibility.md` 把废弃流程写成了一套固定的七步序列,任何一条兼容路径的退场都必须走完这七步才能真正删除:

```
1. Add the new contract.
2. Keep the old behavior wired through a named compatibility adapter.
3. Emit diagnostics or warnings when plugin authors can act.
4. Document the replacement and timeline.
5. Test both old and new paths.
6. Wait through the announced migration window.
7. Remove only with explicit breaking-release approval.
```
—— `docs/plugins/compatibility.md`

有一条自动化守卫专门防止这份注册表本身变成一堆"永远说要删、永远没删"的僵尸记录——`pnpm check:doctor-deprecation-registry` 会检查每一条 `deprecated` 记录是否已经越过了自己声明的 `removeAfter` 日期,越过之后如果还停留在 `deprecated` 状态就直接判定失败,维护者要么真正删除它,要么显式把它挪到 `removal-pending` 并写明还卡在什么条件上。这套机制保证了"核心保持精简"不会退化成一句空话——旧路径的退场有明确的日期承诺和自动化校验,而不是无限期地"以后再说"。

## 常见问题/易踩坑

- **把"官方插件"等同于"插件 id 名字对得上"**:如前所述,信任豁免要求 ClawHub 或 npm 的来源记录能对上,本地路径/archive/git 安装即使 id 相同也不会自动获得豁免。
- **误以为 ClawHub 只是一个可有可无的插件市场首页**:它同时是发布审查(owner scope、包名、版本、文件大小限制、来源元数据校验)、发现搜索、以及安装时刻信任判定的依据来源,三件事共用同一份底层记录。
- **把"两层两标准"理解成"核心团队讨厌新功能"**:`VISION.md` 明确说这条规则"is a roadmap guardrail, not a law of physics",拒绝的通常是接入位置而不是能力本身,强用户需求和技术论证可以让边界移动。
- **以为兼容性注册表的存在意味着旧代码会永远保留**:恰恰相反,这张注册表和它绑定的日期守卫是为了防止旧代码无限期滞留——它是"做减法"的工具,不是"暂缓做减法"的借口。

## 小结

这一篇把 `VISION.md` 里两句听起来像口号的话——"Two layers, two bars"和"Recurring demand defines interfaces"——落到了三处可验证的工程事实:插件清单里核心与外部包数量的真实对比;安装时刻基于 ClawHub/npm 来源记录的 capability consent 审查;以及一张有日期承诺、有自动化守卫的兼容性注册表。三者共同证明了"核心保持精简、能力尽量长在生态里"不是一句公关辞令,而是一套贯穿贡献准入、依赖治理、安装信任、废弃退场全流程的、可以被读者自己验证的工程纪律。至此,本章"自动化与生态"三篇——钟点与事件的双轨触发、Task Flow/tasks/Workboard 的三个独立系统、以及支撑整个插件生态的治理哲学——已经把 OpenClaw 作为"能长期自主运行、能被生态持续扩展"的框架讲完整。下一章也是本课程最后一章:课程总结,把 OpenClaw 放回 PI、DeepSeek Harness、Hermes Agent、OpenHarness 这几个姊妹项目的坐标系里,做一次五方对照。
