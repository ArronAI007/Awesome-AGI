# 扩展 Extension 开发指南

> Extension（扩展）是 pi coding agent 的 TypeScript 插件机制：一个默认导出的工厂函数，拿到 `ExtensionAPI` 之后就能注册工具、命令、监听生命周期事件、定制 UI——本篇基于 `docs/extensions.md` 和 `examples/extensions/` 里的真实示例，讲清楚这套机制怎么用。

## 学习目标

- 知道扩展文件应该放在哪些目录、如何用 `--extension`/`-e` 快速试跑一个扩展。
- 理解扩展工厂函数的签名、同步/异步两种写法，以及"单文件 / 目录 / 带依赖的包"三种组织形式的适用场景。
- 掌握 `pi.registerTool()` 注册自定义工具的核心字段（`parameters`、`execute`、`promptSnippet`/`promptGuidelines`），并知道自定义的文件修改工具为什么必须接入 `withFileMutationQueue`。
- 掌握 `pi.on(event, handler)` 监听事件、拦截/修改工具调用（以 `tool_call` 为例）的写法。
- 能照抄本文给出的最小可运行示例改出自己的第一个扩展，并知道去哪里找更多参考实现。

## 扩展是什么、放在哪里

扩展是一个 TypeScript 模块，默认导出一个工厂函数，接收 `ExtensionAPI` 作为参数：

```typescript
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  // 在这里注册事件监听、工具、命令……
}
```

**安全提醒**（文档原文）：扩展以你的完整系统权限运行，可以执行任意代码，只应该从信任的来源安装。

pi 会从以下位置自动发现扩展：

| 位置 | 作用域 |
|------|--------|
| `~/.pi/agent/extensions/*.ts` | 全局（所有项目） |
| `~/.pi/agent/extensions/*/index.ts` | 全局（子目录形式） |
| `.pi/extensions/*.ts` | 项目本地 |
| `.pi/extensions/*/index.ts` | 项目本地（子目录形式，项目本地条目仅在项目被信任后才加载） |

也可以在 `settings.json` 里通过 `extensions` 数组追加任意路径，或者通过 `packages` 字段以 npm/git 包的形式分发（见第四篇《Pi Package 生态与分发》）。

放在自动发现目录下的扩展支持 `/reload` 热重载；快速验证一个还没放到正式目录的扩展文件，用：

```bash
pi -e ./my-extension.ts
# 等价写法
pi --extension ./my-extension.ts
```

**可用的导入**：`@earendil-works/pi-coding-agent`（扩展类型：`ExtensionAPI`、`ExtensionContext`、各类事件类型）、`typebox`（工具参数 schema）、`@earendil-works/pi-ai`（例如 `StringEnum`，用于兼容 Google API 的字符串枚举）、`@earendil-works/pi-tui`（自定义渲染用的 TUI 组件），以及 Node.js 内置模块（`node:fs`、`node:path` 等）。扩展目录旁放一个 `package.json` 并 `npm install`，`node_modules/` 里的第三方依赖也能正常 `import`。

## 三种组织形式

**单文件**——最简单，适合小扩展：

```
~/.pi/agent/extensions/
└── my-extension.ts
```

**目录 + index.ts**——适合多文件扩展：

```
~/.pi/agent/extensions/
└── my-extension/
    ├── index.ts        # 入口，导出默认函数
    ├── tools.ts
    └── utils.ts
```

**带依赖的包**——需要 npm 依赖时：

```
~/.pi/agent/extensions/
└── my-extension/
    ├── package.json    # 声明依赖和入口
    ├── package-lock.json
    ├── node_modules/
    └── src/
        └── index.ts
```

```json
// package.json
{
  "name": "my-extension",
  "dependencies": { "zod": "^3.0.0", "chalk": "^5.0.0" },
  "pi": { "extensions": ["./src/index.ts"] }
}
```

在该目录下运行一次 `npm install`，之后 `node_modules/` 里的依赖就能正常使用。

## 异步工厂与生命周期注意事项

工厂函数可以是异步的，用于一次性启动工作（比如拉取远程配置、探测可用模型）：

```typescript
export default async function (pi: ExtensionAPI) {
  const response = await fetch("http://localhost:1234/v1/models");
  const payload = await response.json();
  pi.registerProvider("local-openai", {
    baseUrl: "http://localhost:1234/v1",
    apiKey: "$LOCAL_OPENAI_API_KEY",
    api: "openai-completions",
    models: payload.data.map((m: any) => ({ id: m.id, name: m.name ?? m.id, /* ... */ })),
  });
}
```

如果工厂返回 `Promise`，pi 会等它 resolve 之后才继续启动流程——这意味着异步初始化会在 `session_start`、`resources_discover`、以及 `pi.registerProvider()` 排队的注册被真正应用之前就完成。

**重要**：扩展工厂可能在"根本不会启动会话"的调用中也被执行一次，所以**不要**在工厂函数体里直接启动后台资源（进程、socket、文件监听、定时器）。把这些放到 `session_start` 事件或真正用到该资源的命令/工具/事件处理器里，并注册一个幂等的 `session_shutdown` 处理器来关闭会话级资源。

## 注册工具：`pi.registerTool()`

自定义工具通过 `pi.registerTool()` 注册，字段结构和内置工具的 `ToolDefinition` 是同一套体系。最小示例（改编自 `examples/extensions/hello.ts`）：

```typescript
import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

const helloTool = defineTool({
  name: "hello",
  label: "Hello",
  description: "A simple greeting tool",
  parameters: Type.Object({
    name: Type.String({ description: "Name to greet" }),
  }),
  async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
    return {
      content: [{ type: "text", text: `Hello, ${params.name}!` }],
      details: { greeted: params.name },
    };
  },
});

export default function (pi: ExtensionAPI) {
  pi.registerTool(helloTool);
}
```

`pi.registerTool()` 在扩展加载期间和启动之后都能调用——可以在 `session_start`、命令处理器或其它事件处理器里动态注册新工具，新工具会立刻出现在 `pi.getAllTools()` 里并且可被模型调用，不需要 `/reload`（参考 `examples/extensions/dynamic-tools.ts`，它演示了在 `session_start` 里注册一个工具，再通过 `/add-echo-tool <name>` 命令在运行时继续注册新工具）。

几个容易被忽略的字段：

- **`promptSnippet`**：让工具在系统提示词的 "Available tools" 一节里获得一行说明；不设置的话自定义工具不会出现在那一节。
- **`promptGuidelines`**：往系统提示词的 "Guidelines" 一节追加针对该工具的说明条目。注意这些条目是**平铺**追加的、没有工具名前缀分组，所以每一条准则都必须显式点名工具（写"Use my_tool when..."而不是"Use this tool when..."），否则模型分不清"this"指的是哪个工具。
- **`prepareArguments(args)`**：在 schema 校验之前运行的兼容层，用来把历史上不同形状的参数统一成当前 schema 认可的样子（例如恢复一个存有旧版工具调用参数的历史会话时）。不要为了兼容旧格式而放松公开的 `parameters` schema 本身。
- **`StringEnum`**：字符串枚举请用 `@earendil-works/pi-ai` 提供的 `StringEnum`，而不是 `Type.Union`/`Type.Literal`——后者与 Google 的 API 不兼容。
- **报错方式**：要把一次工具执行标记为失败（`isError: true`），必须在 `execute` 里 `throw`；`return` 一个值永远不会被视为错误，不管返回对象里塞了什么字段。

### 自定义工具如果要改文件：必须用 `withFileMutationQueue`

pi 默认并行执行同一条模型消息里的多个工具调用。如果自定义工具会修改文件，但没有接入与内置 `edit`/`write` 相同的互斥队列，就可能出现"两个工具都读到同一份旧内容、各自计算出不同的修改、后写的覆盖先写的"这种静默丢数据的问题（例如自定义工具和内置 `edit` 在同一轮里都改了 `foo.ts`）。正确写法（文档原文示例）：

```typescript
import { withFileMutationQueue } from "@earendil-works/pi-coding-agent";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
  const absolutePath = resolve(ctx.cwd, params.path);

  return withFileMutationQueue(absolutePath, async () => {
    await mkdir(dirname(absolutePath), { recursive: true });
    const current = await readFile(absolutePath, "utf8");
    const next = current.replace(params.oldText, params.newText);
    await writeFile(absolutePath, next, "utf8");
    return { content: [{ type: "text", text: `Updated ${params.path}` }], details: {} };
  });
}
```

要点：传给 `withFileMutationQueue` 的必须是**解析后的绝对路径**（相对 `ctx.cwd` 或工具自己的工作目录），而不是模型传来的原始字符串；要把整个"读-改-写"窗口都包在队列回调里，而不是只包最后一次写入。这与第一篇《内置工具全解析》里 `edit.ts`/`write.ts` 的实现是同一套模式。

### 覆盖内置工具

扩展可以注册一个与内置工具同名（`read`/`bash`/`edit`/`write`/`grep`/`find`/`ls`）的工具来整体替换它，交互模式下会显示一条警告提示这一覆盖行为发生了。典型用途是给 `read` 加访问日志或权限控制（参考 `examples/extensions/tool-override.ts`）。

## 监听与拦截事件：`pi.on()`

`pi.on(event, handler)` 订阅生命周期事件。以最常用的 `tool_call` 事件为例——它在工具真正执行之前触发，**可以拦截**：

```typescript
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

pi.on("tool_call", async (event, ctx) => {
  if (isToolCallEventType("bash", event)) {
    // event.input 是 { command: string; timeout?: number }，可原地修改
    event.input.command = `source ~/.profile\n${event.input.command}`;
    if (event.input.command.includes("rm -rf")) {
      return { block: true, reason: "Dangerous command", terminate: true };
    }
  }
});
```

`event.input` 是可变的，原地修改会真正影响工具执行；返回 `{ block: true, reason?, terminate? }` 可以阻止这次调用（`terminate` 只在被阻止时生效，且只有当同一批次里所有已完成的工具结果都要求终止时，Agent 才会提前停止）。

其他常用事件：`session_start`（会话启动，适合做状态恢复）、`tool_result`（工具执行完成后，可以链式修改结果）、`user_bash`（用户输入 `!command` 时触发，可以整体替换执行后端）、`input`（用户输入到达时，在 skill/模板展开之前，可以 transform 或直接 handled）。`examples/extensions/confirm-destructive.ts` 展示了如何用 `session_before_switch`/`session_before_fork` 加确认弹窗：

```typescript
pi.on("session_before_switch", async (event, ctx) => {
  if (!ctx.hasUI) return;
  if (event.reason === "new") {
    const confirmed = await ctx.ui.confirm("Clear session?", "This will delete all messages in the current session.");
    if (!confirmed) return { cancel: true };
  }
});
```

## 注册命令：`pi.registerCommand()`

命令注册后可以通过 `/name` 在编辑器里调用：

```typescript
pi.registerCommand("stats", {
  description: "Show session statistics",
  handler: async (args, ctx) => {
    const count = ctx.sessionManager.getEntries().length;
    ctx.ui.notify(`${count} entries`, "info");
  },
});
```

如果多个扩展注册了同名命令，pi 会全部保留，按加载顺序自动加上数字后缀（`/review:1`、`/review:2`）区分。

## 自定义 UI：`ctx.ui`

`ctx.ui` 提供了一组交互方法，在 TUI 和 RPC 模式下都可用（用 `ctx.hasUI` 判断当前是否可以弹交互，用 `ctx.mode === "tui"` 判断是否可以用仅终端支持的 `ctx.ui.custom()`）：

```typescript
const choice = await ctx.ui.select("Pick one:", ["A", "B", "C"]);
const ok = await ctx.ui.confirm("Delete?", "This cannot be undone");
const name = await ctx.ui.input("Name:", "placeholder");
ctx.ui.notify("Done!", "info"); // "info" | "warning" | "error"
ctx.ui.setStatus("my-ext", "Processing...");   // 页脚状态，传 undefined 清除
ctx.ui.setWidget("my-ext", ["Line 1", "Line 2"]); // 编辑器上方（默认位置）的常驻小部件
```

对话框支持 `timeout` 选项自动倒计时关闭，也支持传 `AbortSignal` 手动控制取消，用来区分"超时"和"用户主动取消"两种场景（细节见 `docs/extensions.md` 的 "Timed Dialogs" 一节和 `examples/extensions/timed-confirm.ts`）。更复杂的自定义组件（选择列表、带取消的异步加载、设置项开关等）走 `ctx.ui.custom()`，配套模式收录在 `docs/tui.md` 里。

## 完整最小示例

下面这个可直接运行的扩展综合了"事件拦截 + 自定义工具 + 命令"三件事，改编自文档 Quick Start 一节与 `examples/extensions/hello.ts`、`examples/extensions/dynamic-tools.ts`：

```typescript
// ~/.pi/agent/extensions/course-demo.ts
// 改编自 pi 仓库 docs/extensions.md「Quick Start」示例
// 以及 examples/extensions/hello.ts、examples/extensions/dynamic-tools.ts
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export default function (pi: ExtensionAPI) {
  // 1. 拦截危险的 bash 命令，弹出确认框
  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName === "bash" && typeof event.input.command === "string" && event.input.command.includes("rm -rf")) {
      const ok = await ctx.ui.confirm("Dangerous!", "Allow rm -rf?");
      if (!ok) return { block: true, reason: "Blocked by user" };
    }
  });

  // 2. 注册一个自定义工具
  pi.registerTool({
    name: "greet",
    label: "Greet",
    description: "Greet someone by name",
    promptSnippet: "Greet a user by name",
    parameters: Type.Object({
      name: Type.String({ description: "Name to greet" }),
    }),
    async execute(_toolCallId, params) {
      return {
        content: [{ type: "text", text: `Hello, ${params.name}!` }],
        details: {},
      };
    },
  });

  // 3. 注册一个 /hello 命令
  pi.registerCommand("hello", {
    description: "Say hello",
    handler: async (args, ctx) => {
      ctx.ui.notify(`Hello ${args || "world"}!`, "info");
    },
  });

  pi.on("session_start", async (_event, ctx) => {
    ctx.ui.notify("course-demo extension loaded!", "info");
  });
}
```

保存到 `~/.pi/agent/extensions/course-demo.ts` 后重启一个交互式会话（或先用 `pi -e ~/.pi/agent/extensions/course-demo.ts` 快速试跑），启动即可看到 "course-demo extension loaded!" 通知，模型可以调用 `greet` 工具，用户可以输入 `/hello` 或尝试让模型执行含 `rm -rf` 的命令来触发确认框。

## 动手练习

1. 把上面的最小示例保存为 `~/.pi/agent/extensions/course-demo.ts`，用 `pi -e ~/.pi/agent/extensions/course-demo.ts` 启动一次会话，验证三件事都生效：启动通知、`/hello` 命令、以及让模型执行一条包含 `rm -rf` 的命令时会先弹出确认框。
2. 参考本文"自定义工具如果要改文件"一节，给 `greet` 工具再加一个 `save` 模式：当 `params.name` 提供时把问候语追加写入 `~/.pi/agent/greetings.log`，用 `withFileMutationQueue` 包裹整个"读旧内容 + 追加 + 写回"过程，并解释为什么不能只把 `writeFile` 这一行放进队列里。

## 小结

一个 pi 扩展就是一个默认导出工厂函数的 TypeScript 模块，通过 `ExtensionAPI` 上的 `pi.on()`、`pi.registerTool()`、`pi.registerCommand()`、`ctx.ui.*` 四组能力分别覆盖"事件拦截""自定义工具""自定义命令""自定义交互"。扩展应放在 `~/.pi/agent/extensions/` 或 `.pi/extensions/` 下以获得自动发现和 `/reload` 支持,开发调试期可以用 `-e/--extension` 快速加载单个文件。自定义工具的字段结构与内置工具共享同一套 `ToolDefinition` 体系,凡是会修改文件的自定义工具都必须像内置的 `edit`/`write` 一样接入 `withFileMutationQueue`,否则在 pi 默认的并行工具执行模式下会有丢失更新的风险。更多可直接参考、按场景分类的示例见 `packages/coding-agent/examples/extensions/README.md`。
