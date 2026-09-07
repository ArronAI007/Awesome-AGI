# Plugin SDK 与两类插件:Code Plugin 与 Bundle-style Plugin

> `VISION.md` "Plugins & Memory" 一节开篇就把 OpenClaw 的插件哲学定了调:"Core stays lean; optional capabilities should usually ship as plugins. We are generally slimming down core while expanding what plugins can do."(核心保持精简,可选能力通常应该以插件形式提供;我们在整体缩减 core 的同时,扩大插件能做的事)—— `VISION.md`。紧接着这句话之后,官方给出了两种插件风格的定义,以及一条明确的偏好:"Prefer bundle-style plugins when they can express the capability. They have a smaller, more stable interface and better security boundaries."(能用 bundle-style 表达的能力,优先用 bundle-style——它的接口更小、更稳定,安全边界也更好)—— `VISION.md`。本篇要讲清楚这句"优先"背后的完整机制:两种插件风格具体差在哪里,插件从声明到运行要经过哪几层,以及"两层两条门槛"这条工程哲学如何贯穿了这一切。

## 学习目标

- 能准确复述 `VISION.md` 里 code plugin 与 bundle-style plugin 的官方定义,以及"优先 bundle-style"的理由(更小更稳定的接口、更好的安全边界),而不是自己臆造一套解释。
- 理解"两层两条门槛"(core 的严格审查 vs plugins/skills/channels/apps 的宽松门槛)这条 `VISION.md` 明确写出的工程哲学,以及它试图解决的具体问题。
- 读懂 OpenClaw 原生插件的四层加载流水线(manifest + discovery → enablement + validation → runtime loading → surface consumption),理解"manifest 校验不执行插件代码"这条设计边界的意义。
- 认识 `openclaw.plugin.json` 这份原生 manifest 契约里几个关键字段(`id`/`configSchema`/`contracts`/`activation`),以及它和真正的插件运行时代码(`register(api)`)是两回事。
- 理解"Bundle"这个词在 OpenClaw 里的确切含义——四种外部生态(Agent Plugins/Codex/Claude/Cursor)的内容包如何被映射进原生 skill/hook/MCP 能力,以及这条路径为什么"信任边界更窄"。

## 背景与设计动机

到这一篇为止,前两篇已经讲了 OpenClaw 工具体系里两类扩展方式——内置 Tools(模型可调用的能力原子)和 Skills(教模型怎么用工具的说明书)。Plugin 是第三种,也是范围最大的一种:它不只是给模型加一段说明或者加一个工具,而是可以深入到 OpenClaw 运行时内部,注册 provider、channel、hook、后台服务、HTTP 路由。范围越大,风险和治理成本也越高——这正是 `VISION.md` 这一节要处理的核心张力:插件 API 要"extensive"(广泛),但不能让 core 跟着膨胀,也不能让每一个插件都拥有和 core 代码同等的、不受限的运行时信任。

`VISION.md` 给出的解法分两步。第一步是区分插件本身的"深度"——不是所有扩展需求都需要深入运行时内部,很多时候只是想"打包分发一份已经确定的能力"(一组 skill、一份 MCP 服务器配置),这种需求不需要也不应该获得和运行时代码同等的权限,于是有了 code plugin 和 bundle-style plugin 的区分。第二步是区分"扩展点在哪一层"——core 本身和 plugins/skills/channels/apps 这一圈外围能力,面对的审查标准完全不同,这就是"两层两条门槛"。理解了这两条划分,才能理解后面讲的 manifest 契约和四层加载流水线为什么长这个样子——它们都是在为这两条划分提供具体的技术落地。

## 核心机制详解

### 官方定义:Code Plugin 与 Bundle-style Plugin

`VISION.md` 用两句话给出了两种插件风格的精确定义:

> There are two broad plugin styles:
>
> - Code plugins run OpenClaw plugin code and are appropriate for deeper runtime extension.
> - Bundle-style plugins package stable external surfaces such as skills, MCP servers, and related configuration.
>
> —— `VISION.md`

Code plugin 的关键词是"run ... plugin code"——它是一段会被 OpenClaw 加载并执行的程序,运行在 Gateway 进程内部,可以深入到 provider、channel、hook、工具注册这些运行时扩展点。Bundle-style plugin 的关键词是"package stable external surfaces"——它打包的是已经成型、相对静止的外部能力(skill 内容、MCP 服务器定义、相关配置),而不是一段会被执行的运行时代码。

紧接着这条定义,`VISION.md` 给出了明确的偏好和理由:

> Prefer bundle-style plugins when they can express the capability. They have a smaller, more stable interface and better security boundaries. Use code plugins when the capability needs runtime hooks, providers, channels, tools, or other in-process extension points.
>
> —— `VISION.md`

这不是一句谦辞,而是一条可执行的决策准则:如果你要扩展的能力可以完全用"一组 skill + 一份 MCP 服务器配置"表达清楚,就不需要写一个 code plugin;只有当能力本身依赖运行时钩子、provider 注册、channel 接入、工具注册这类"必须在进程内跑代码"的扩展点时,才应该选择 code plugin。第 5 篇会讲到,MCP servers 正是 `VISION.md` 里点名的 bundle-style 典型内容之一——这条关系在 `docs/plugins/bundles.md` 里能找到具体的技术落地,后面会展开。

这条偏好为什么成立,`docs/plugins/architecture.md` 的"执行模型"一节给出了更具体的技术依据。Code plugin(文档称为"native plugin")的信任边界是彻底的进程内信任:

> Native OpenClaw plugins run **in-process** with the Gateway. They are not sandboxed. A loaded native plugin has the same process-level trust boundary as core code. ... a plugin can register tools, network handlers, hooks, and services; a plugin bug can crash or destabilize the gateway; and a malicious native plugin is equivalent to arbitrary code execution inside the OpenClaw process.
>
> —— `docs/plugins/architecture.md`

相比之下,bundle 的信任边界要窄得多:

> Compatible bundles are safer by default because OpenClaw currently treats them as metadata/content packs.
>
> —— `docs/plugins/architecture.md`

这句话和 `VISION.md` 里"更小更稳定的接口、更好的安全边界"是同一件事的两种表述——一个是产品原则层面的表态,一个是架构文档里对应的技术事实:native 插件等价于进程内任意代码执行,bundle 则被当作内容包处理,不会被当作运行时代码在进程内执行。理解了这层落差,就能明白为什么"优先 bundle-style"不只是审美偏好,而是一条实打实的安全边界选择。

### 两层两条门槛

`VISION.md` 用一句精炼的话给出了这条工程哲学的名字和理由:

> Two layers, two bars. The core carries a per-call tax: each core tool, prompt line, and config key reaches every operator on every model request, so additions there face the strictest scrutiny. Plugins, skills, channels, and apps carry no such tax, and we want that surface to keep growing. When our contribution rules read as hostile to a feature, re-check the layer: usually they object to where it plugs in, not to the feature existing.
>
> —— `VISION.md`

这段话点破了一个容易被误解的地方——如果一个贡献者提的 PR 被拒绝,很容易理解成"这个功能不被需要",但 `VISION.md` 明确说通常不是这样:被拒绝的往往只是"这个功能被放错了层"。core 里的每一行代码都要为"每一个 operator 的每一次模型请求"付出成本(prompt 里多一行、config 里多一个 key、多一个默认加载的工具),这个成本是乘数级的,所以 core 层的准入门槛必须最严格;而 plugins/skills/channels/apps 这一层,只有选择启用它的人才会承担对应的成本,所以门槛可以宽松得多,官方原文甚至是"we want that surface to keep growing"——这一层的扩张是被鼓励的。

这条哲学解释了一个常见的疑惑:为什么 OpenClaw 的贡献规则对"往 core 里加东西"如此保守,却同时维护着一个内容持续膨胀的插件生态?答案就是这两层根本不是同一套标准在评审。`VISION.md` 后面紧跟的"Recurring demand defines interfaces"一段进一步说明了两层之间如何互相流动:当足够多独立的 PR 或需求都在实现同一类能力时,正确的做法不是排队合并,而是"把这个接缝落进 core 或 SDK 里,把已有的实现搬到这个接口上,让剩下的候选者作为插件针对这个接口去实现"——也就是说,一个能力从"插件层反复出现的需求"变成"core 里的一个正式契约",本身也是一条有意为之的路径,而不是插件功能永远只能留在插件层。

### 插件生命周期:四层加载流水线

`docs/plugins/architecture.md` 把原生插件(code plugin)从声明到生效的过程,划成了四个层次:

> - **Manifest + discovery**:OpenClaw 从配置路径、workspace 根目录、全局插件根目录和内置插件里找到候选插件,发现阶段优先读取原生 `openclaw.plugin.json` manifest 和支持的 bundle manifest。
> - **Enablement + validation**:core 决定一个被发现的插件是启用、禁用、被屏蔽,还是被选中占据一个像 memory 这样的排他槽位。
> - **Runtime loading**:原生 OpenClaw 插件在进程内加载,把能力注册进一个中心注册表;打包好的 JavaScript 通过原生 `require` 加载,第三方本地源码 TypeScript 走 Jiti 作为应急兜底;兼容的 bundle 会被规范化成注册表记录,而不导入运行时代码。
> - **Surface consumption**:OpenClaw 的其余部分读这个注册表,把工具、channel、provider 配置、hook、HTTP 路由、CLI 命令、后台服务暴露出来。
>
> —— `docs/plugins/architecture.md`(节选转述)

这四层里最值得注意的是第一层和第三层之间的边界。文档专门强调了一条设计边界:

> manifest/config validation should work from **manifest/schema metadata** without executing plugin code ... native runtime behavior comes from the plugin module's `register(api)` path with `api.registrationMode === "full"`.
>
> —— `docs/plugins/architecture.md`

也就是说,OpenClaw 光凭 `openclaw.plugin.json` 这一份静态元数据,就能完成"这个插件配置对不对"、"哪些插件缺失或被禁用"这类校验和诊断,完全不需要真正执行插件代码——只有当插件被判定为需要启用时,`register(api)` 这段真正的运行时代码才会被执行。这条边界让 OpenClaw 能在插件生态膨胀的同时,依然保持"配置校验轻量、不会因为一个插件写坏了就拖垮整个启动流程去校验其他插件配置"的特性。

### manifest 契约:`openclaw.plugin.json` 讲的是"是什么",不是"怎么跑"

`docs/plugins/manifest.md` 开篇就划清楚了这份文件的定位:

> `openclaw.plugin.json` is metadata OpenClaw reads **before loading your plugin code**. Everything in it must be cheap enough to inspect without booting plugin runtime. ... **Do not use it for:** registering native runtime hooks, declaring the full plugin runtime entrypoint, or npm install metadata. Those belong in your plugin code and `package.json`.
>
> —— `docs/plugins/manifest.md`

一份最小 manifest 只需要两个必填字段:

```json
{
  "id": "voice-call",
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {}
  }
}
```

—— `docs/plugins/manifest.md`

`id`(插件在 `plugins.entries.<id>` 里的规范标识)和 `configSchema`(哪怕这个插件不接受任何配置,也必须显式声明一份空 schema)是唯二的必填字段。除此之外,`contracts.tools`(声明这个插件拥有哪些工具,让 OpenClaw 不需要真正加载插件运行时就能知道"这个工具属于谁")、`activation`(控制什么条件下触发加载,文档特别提醒"Do not treat `activation` as a lifecycle hook or a replacement for `register(...)`. It is metadata used to narrow loading.")、`kind`(声明这个插件占据 `"memory"` 或 `"context-engine"` 这类排他槽位)是几个体现"manifest 只描述元数据、不描述行为"这条原则的典型字段。真正的运行时注册逻辑,则写在插件入口代码里,用 `definePluginEntry` 包一层:

```typescript
import { Type } from "typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

export default definePluginEntry({
  id: "my-plugin",
  name: "My Plugin",
  description: "Adds a custom tool to OpenClaw",
  register(api) {
    api.registerTool({
      name: "my_tool",
      description: "Echo one input value",
      parameters: Type.Object({ input: Type.String() }),
      // ...
      async execute(_id, params) {
        return { content: [{ type: "text", text: `Got: ${params.input}` }] };
      },
    });
  },
});
```

—— `docs/plugins/building-plugins.md`

`register(api)` 里调用的 `api.registerTool(...)`/`api.registerProvider(...)`/`api.registerChannel(...)` 这类方法,就是 `docs/plugins/architecture.md` "Public capability model"一节列出的能力注册点——文本推理、CLI 推理后端、embeddings、语音、图像/音乐/视频生成、channel、gateway discovery 等十几种能力类型,每一种都有对应的 `api.register*` 方法和一份真实存在的样例插件(比如 `anthropic`/`openai` 注册文本推理,`elevenlabs`/`microsoft` 注册语音)。文档还专门定义了一套"插件形状"分类——只注册一种能力的叫 `plain-capability`,注册多种能力的叫 `hybrid-capability`,只注册 hook 不注册能力的叫 `hook-only`,注册工具/命令/服务但不注册能力的叫 `non-capability`——这套分类可以用 `openclaw plugins inspect <id>` 直接查看,说明 OpenClaw 把"一个插件到底做了什么"当成一个可以运行时内省、而不是只能靠文档猜测的事实。

### Bundle 是什么:四种外部生态的内容包,而不是运行时代码

如果说 code plugin 对应上面这套 manifest + `register(api)` 的完整契约,bundle-style plugin 在 OpenClaw 里对应的具体实现,就是 `docs/plugins/bundles.md` 讲的"Bundle"机制。这里有一个容易混淆的地方需要先澄清:文档里的"Bundle"特指对 **Agent Plugins、Codex、Claude、Cursor** 这四种外部生态既有格式的兼容支持,而不是"bundle-style"这个设计理念本身的唯一实现——但它是这个理念在代码层面最直接、最完整的落地案例。文档开篇就划清楚了 Bundle 和 native 插件的边界:

> Bundles are **not** the same as native OpenClaw plugins. Native plugins run in-process and can register any capability. Bundles are content packs with selective feature mapping and a narrower trust boundary.
>
> —— `docs/plugins/bundles.md`

OpenClaw 不要求这四种外部生态的插件作者重写一份原生 OpenClaw 插件,而是识别这些既有格式,把它们支持的内容映射进原生能力——目前支持映射的是 Skill 内容(bundle 的 skill 根目录直接当成 OpenClaw skill 加载)、Commands(Claude 的 `commands/`、Cursor 的 `.cursor/commands/` 被当作额外的 skill 根)、Hook packs(仅当使用 OpenClaw 自己的 `HOOK.md` + `handler.ts` 布局时,目前主要是 Codex 场景)、MCP tools(bundle 的 MCP 配置被合并进 embedded OpenClaw 设置)、LSP servers 和部分 Claude settings。有一些内容"能被识别但不会执行",比如 Claude 的 `agents`/`hooks/hooks.json` 自动化/`outputStyles`,Cursor 的 `.cursor/agents`/`.cursor/hooks.json`/`.cursor/rules`——`docs/plugins/bundles.md` 明确用一张表区分了"Supported now"和"Detected but not executed"这两类,这是一种诚实的能力边界声明,而不是含糊地宣称"完全兼容"。

安全边界上,`docs/plugins/bundles.md` 的表述和前面 code plugin 的"进程内任意代码执行"形成了直接对照:

> OpenClaw does **not** load arbitrary bundle runtime modules in-process. Skills and hook-pack paths must stay inside the plugin root (boundary-checked). ... Supported stdio MCP servers may be launched as subprocesses.
>
> —— `docs/plugins/bundles.md`

"不在进程内加载任意 bundle 运行时模块"这句话,正是 `VISION.md` "更好的安全边界"这句话的具体技术兑现——bundle 里唯一会真正"跑起来"的东西,是被显式支持的 stdio MCP 服务器,而且是作为独立子进程启动,不是和 Gateway 共享同一个进程空间。

### 从两类插件的视角重新看 manifest 和 bundle 的分工

把前面几节拼起来看,一个清晰的分工浮现出来:`openclaw.plugin.json` + `register(api)` 是 code plugin 的完整契约,面向"这个能力必须深入运行时内部"的场景;四种 Bundle 格式是 bundle-style plugin 在 OpenClaw 里的具体落地,面向"这个能力只是想打包分发一组 skill、一份 MCP 配置"的场景。两者共用同一套发现和加载流水线的前两层(manifest + discovery、enablement + validation),但在第三层(runtime loading)分道扬镳——一个真正加载运行时代码注册能力,一个被规范化成注册表记录而不导入任何运行时代码。这也是为什么 `docs/plugins/architecture.md` 会把"discovery 阶段优先读取原生 manifest 和支持的 bundle manifest"写在同一句话里——从系统的角度看,这两类插件从"被发现"的第一刻起就走的是同一套治理框架,只是内部路径不同。

## 常见问题/易踩坑

**Q:是不是只要不需要一个 UI 或者复杂逻辑,就应该无脑选 bundle-style?**

不是无脑选,而是看能力本身的性质。`VISION.md` 给的判断标准很具体:"Use code plugins when the capability needs runtime hooks, providers, channels, tools, or other in-process extension points."——只要这个能力依赖运行时钩子、provider 注册、channel 接入、工具注册这类必须在进程内执行代码的扩展点,就应该用 code plugin,而不是勉强把它塞进 bundle 能表达的范围(skill/MCP/配置)里。判断依据是"这个能力的本质需不需要进程内代码执行",而不是"实现起来省不省事"。

**Q:`openclaw.plugin.json` 里能不能直接写运行时逻辑,比如在 `activation` 里挂一段初始化代码?**

不能。`docs/plugins/manifest.md` 和 `docs/plugins/architecture.md` 都反复强调 manifest 只是"loading 之前"的元数据,`activation` 明确写着"It is metadata used to narrow loading"、不是生命周期钩子,也不能替代 `register(...)`。任何真正的运行时行为都必须写在插件入口模块的 `register(api)` 里,manifest 只负责描述"这个插件是什么、拥有什么、什么条件下应该被考虑加载"。

**Q:装了一个 Claude/Codex/Cursor 格式的插件,为什么它的某个功能在文档里明明写了、实际却不生效?**

先用 `openclaw plugins inspect <id>` 确认这个能力被归在"Supported now"还是"Detected but not executed"——`docs/plugins/bundles.md` 明确列出了后一类内容(比如 Claude 的 hooks.json、Cursor 的 rules),这些是"识别到了但目前不执行",不是安装出了问题。

## 小结

`VISION.md` 用两句话划清楚了 OpenClaw 插件生态里最核心的一条分界线——code plugin 深入运行时、bundle-style plugin 打包稳定外部能力,而官方明确偏好后者,理由是接口更小、更稳定、安全边界更好;这条偏好在 `docs/plugins/architecture.md` 和 `docs/plugins/bundles.md` 里能找到具体的技术对应:code plugin 等价于进程内任意代码执行,bundle 则被当作内容包处理,唯一会真正运行的部分(stdio MCP 服务器)也是以独立子进程的方式隔离出去的。"两层两条门槛"进一步说明了这条分界线为什么重要——core 层的每一次改动都要为所有用户的每一次请求付出成本,所以审查最严格;plugins/skills/channels/apps 这一层只有选择启用的人才承担成本,所以被鼓励持续生长。理解了这套分层之后,`openclaw.plugin.json` 的 manifest 契约和四种 Bundle 格式的映射规则,就都是这套哲学在具体工程细节上的体现,而不是孤立的技术选择。下一篇会转向 ACP 与 Codex 深度集成——看 OpenClaw 怎么把 OpenAI Codex 这样的外部 harness,接进这一整套工具与插件体系里。
