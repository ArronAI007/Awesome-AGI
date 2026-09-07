# SDK 嵌入式集成

> 如果你的宿主应用本身就是 Node.js/TypeScript，那么完全没必要把 Pi 当成外部子进程通过 JSONL 协议来"隔空喊话"——直接把 `@earendil-works/pi-coding-agent` 作为库导入，在同一个进程里拿到类型安全的 `AgentSession`，是官方文档明确推荐的更优路径。

## 学习目标

- 理解 SDK 嵌入方式与上一篇 RPC 子进程方式的适用边界，知道什么时候该选哪一个
- 掌握 `createAgentSession()` 的最小启动方式和常用配置项（模型、工具、扩展、技能、系统提示词覆盖）
- 理解 `AgentSession` 与 `AgentSessionRuntime` 的职责划分：前者管理单个会话的生命周期，后者负责"替换"当前会话（新建/续接/fork/clone/导入）
- 能够订阅 `AgentSession` 事件流，正确处理流式文本增量
- 了解 `InteractiveMode` / `runPrintMode` / `runRpcMode` 这三种内置运行模式与 SDK 的关系

## 为什么要用 SDK 而不是子进程

`docs/sdk.md` 开篇第一句话就点明了适用场景：

> pi can help you use the SDK. Ask it to build an integration for your use case.

SDK 提供的是"把 Pi 的 Agent 能力嵌入到别的应用里"的编程接口，典型用例包括构建自定义 UI（Web/桌面/移动端）、把 Agent 推理能力整合进已有应用、构建带 Agent 推理的自动化流水线、构建能派生子 Agent 的自定义工具，以及以编程方式测试 Agent 行为。

和上一篇的 RPC 模式相比，文档给出了非常直接的选型建议：

**SDK 更适合的场景**：需要类型安全；运行在同一个 Node.js 进程里；需要直接访问 Agent 状态；需要以编程方式定制工具/扩展。

**RPC 模式更适合的场景**：从别的语言集成；需要进程隔离；构建语言无关的客户端。

一个容易被忽视的事实是：SDK 并不是 RPC 模式之外的另一套平行实现，而是 RPC 模式的**底层基础**。`docs/sdk.md` 明确说 `runRpcMode(runtime)` 就是 SDK 导出的一个运行模式函数——CLI 的 `pi --mode rpc` 本质上就是调用了这个函数。理解这一点后，SDK 和 RPC 之间就不再是"两种互不相关的技术"，而是"同一套核心能力的两层封装"。

## 安装与快速开始

```bash
npm install @earendil-works/pi-coding-agent
```

SDK 直接包含在主包里，不需要单独安装。最小可运行示例：

```typescript
import { createAgentSession, ModelRuntime, SessionManager } from "@earendil-works/pi-coding-agent";

const modelRuntime = await ModelRuntime.create();
const { session } = await createAgentSession({
  sessionManager: SessionManager.inMemory(),
  modelRuntime,
});

session.subscribe((event) => {
  if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await session.prompt("What files are in the current directory?");
```

这几行代码里已经出现了 SDK 的三个核心概念：`createAgentSession()` 工厂函数、`AgentSession` 上的 `subscribe()`/`prompt()`，以及用来控制持久化行为的 `SessionManager`。

## createAgentSession()：单会话工厂

`createAgentSession()` 是创建单个 `AgentSession` 的主入口。它内部依赖一个 `ResourceLoader` 来发现扩展（extensions）、技能（skills）、Prompt 模板、主题和上下文文件；如果不传，默认使用 `DefaultResourceLoader` 做标准路径发现。

```typescript
import { createAgentSession, SessionManager } from "@earendil-works/pi-coding-agent";

// 最简单：全部走默认值
const { session } = await createAgentSession();

// 自定义：只覆盖需要的选项
const { session } = await createAgentSession({
  model: myModel,
  tools: ["read", "bash"],
  sessionManager: SessionManager.inMemory(),
});
```

`AgentSession` 接口本身的形状（节选自 `docs/sdk.md`）大致是：

```typescript
interface AgentSession {
  prompt(text: string, options?: PromptOptions): Promise<void>;
  steer(text: string): Promise<void>;
  followUp(text: string): Promise<void>;
  subscribe(listener: (event: AgentSessionEvent) => void): () => void;

  sessionFile: string | undefined;
  sessionId: string;

  setModel(model: Model): Promise<void>;
  setThinkingLevel(level: ThinkingLevel): void;
  cycleModel(): Promise<ModelCycleResult | undefined>;
  cycleThinkingLevel(): ThinkingLevel | undefined;

  agent: Agent;
  model: Model | undefined;
  thinkingLevel: ThinkingLevel;
  messages: AgentMessage[];
  isStreaming: boolean;

  navigateTree(targetId: string, options?: {...}): Promise<{ editorText?: string; cancelled: boolean }>;

  compact(customInstructions?: string): Promise<CompactionResult>;
  abortCompaction(): void;

  abort(): Promise<void>;
  dispose(): void;
}
```

注意文档特别强调："新建会话、续接、fork、导入这些替换整个会话的操作，不在 `AgentSession` 上，而在 `AgentSessionRuntime` 上。"这是一个刻意的职责切分：`AgentSession` 只管一个已经存在的会话怎么对话，"换一个会话"是更高一层的运行时才该关心的事。

## createAgentSessionRuntime()：需要"替换会话"时才用

当你需要支持 `/new`、`/resume`、`/fork`、`/clone` 这类会把当前活跃会话整个换掉的操作时，就需要 `AgentSessionRuntime`。它由一个工厂函数加初始 cwd/会话目标构造：

```typescript
import {
  type CreateAgentSessionRuntimeFactory,
  createAgentSessionFromServices,
  createAgentSessionRuntime,
  createAgentSessionServices,
  getAgentDir,
  SessionManager,
} from "@earendil-works/pi-coding-agent";

const createRuntime: CreateAgentSessionRuntimeFactory = async ({ cwd, sessionManager, sessionStartEvent }) => {
  const services = await createAgentSessionServices({ cwd });
  return {
    ...(await createAgentSessionFromServices({ services, sessionManager, sessionStartEvent })),
    services,
    diagnostics: services.diagnostics,
  };
};

const runtime = await createAgentSessionRuntime(createRuntime, {
  cwd: process.cwd(),
  agentDir: getAgentDir(),
  sessionManager: SessionManager.create(process.cwd()),
});
```

几个需要特别注意的运行时语义：

- `runtime.session` 在 `newSession()`、`switchSession()`、`fork()` 等操作之后会**变成一个新对象**
- 事件订阅是绑定在某一个具体 `AgentSession` 实例上的，所以会话被替换后要重新 `subscribe()`
- 如果用了扩展，需要对新会话重新调用 `runtime.session.bindExtensions(...)`
- 运行时创建过程中产生的诊断信息挂在 `runtime.diagnostics` 上
- 运行时创建或替换失败会直接抛异常，调用方自行决定如何处理

```typescript
let session = runtime.session;
let unsubscribe = session.subscribe(() => {});

await runtime.newSession();

unsubscribe();
session = runtime.session;
unsubscribe = session.subscribe(() => {});
```

## 发送提示词与消息排队

`PromptOptions` 控制 Prompt 展开、流式期间的排队行为，以及预检通知：

```typescript
interface PromptOptions {
  expandPromptTemplates?: boolean;
  images?: ImageContent[];
  streamingBehavior?: "steer" | "followUp";
  source?: InputSource;
  preflightResult?: (success: boolean) => void;
}
```

`preflightResult` 每次调用 `prompt()` 只会触发一次：`true` 表示提示词已被接受/排队/立即处理，`false` 表示预检阶段就被拒绝了（还没被受理）。它在 `prompt()` 真正 resolve 之前就会触发；`prompt()` 本身要等到这次被接受的完整运行（包括自动重试）跑完才 resolve。受理之后发生的失败不会通过 `preflightResult(false)` 报告，而是走正常的事件流。

```typescript
// 非流式状态下的基本用法
await session.prompt("What files are here?");

// 带图片
await session.prompt("What's in this image?", {
  images: [{ type: "image", source: { type: "base64", mediaType: "image/png", data: "..." } }]
});

// 流式期间必须显式指定排队方式
await session.prompt("Stop and do this instead", { streamingBehavior: "steer" });
await session.prompt("After you're done, also check X", { streamingBehavior: "followUp" });
```

如果流式期间调用 `prompt()` 又没指定 `streamingBehavior`，会直接抛错——这一点和 RPC 模式里 `prompt` 命令的行为是一致的，只是在 SDK 层表现为异常而不是 `success: false` 的响应。也可以绕开 `prompt()` 直接调用 `session.steer()` / `session.followUp()`，两者都会展开基于文件的 Prompt 模板，但会对扩展命令报错（扩展命令不允许被排队）。

## 订阅事件

```typescript
session.subscribe((event) => {
  switch (event.type) {
    case "message_update":
      if (event.assistantMessageEvent.type === "text_delta") {
        process.stdout.write(event.assistantMessageEvent.delta);
      }
      break;
    case "tool_execution_start":
      console.log(`Tool: ${event.toolName}`);
      break;
    case "tool_execution_end":
      console.log(`Result: ${event.isError ? "error" : "success"}`);
      break;
    case "agent_end":
      // event.messages 包含本次运行新产生的消息
      break;
    case "turn_end":
      // event.message：assistant 回复；event.toolResults：本轮工具结果
      break;
    case "queue_update":
      console.log(event.steering, event.followUp);
      break;
  }
});
```

这套事件类型和上一篇 RPC/JSON 模式讲的事件词汇表是同一套底层来源（`AgentSessionEvent`），只不过在 SDK 里你拿到的是原生 TypeScript 对象而不是需要反序列化的 JSON 字符串——这正是"同进程集成"相对子进程集成的直接好处之一。

## 可配置项速览

SDK 把 Agent 的方方面面都做成了可插拔的配置项，这里按文档顺序过一遍最常用的几类。

**目录**：`cwd` 影响 `DefaultResourceLoader` 发现项目级扩展/技能/Prompt/`AGENTS.md`；`agentDir`（默认 `~/.pi/agent`）影响全局级资源、`settings.json`、`models.json`、`auth.json`、会话目录。传入自定义 `ResourceLoader` 后，这两个参数就只影响会话命名和工具路径解析，不再控制资源发现。

**模型与鉴权**：

```typescript
import { getModel } from "@earendil-works/pi-ai";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";

const modelRuntime = await ModelRuntime.create();
const opus = getModel("anthropic", "claude-opus-4-5");
const available = await modelRuntime.getAvailable();

const { session } = await createAgentSession({
  model: opus,
  thinkingLevel: "medium",
  scopedModels: [{ model: opus, thinkingLevel: "high" }],
  modelRuntime,
});
```

鉴权解析优先级由 `ModelRuntime` 处理，依次是：运行时覆盖（`setRuntimeApiKey`，不落盘）→ `auth.json` 里存储的凭证 → 环境变量（`ANTHROPIC_API_KEY` 等）→ 针对 `models.json` 自定义 provider 的兜底解析器。

**工具**：内置工具名为 `read`/`bash`/`edit`/`write`/`grep`/`find`/`ls`，默认启用前四个；`noTools: "all"` 关闭全部工具，`noTools: "builtin"` 只关闭默认内置工具（扩展和自定义工具仍启用）；`excludeTools` 在 `tools` 白名单之后再排除指定工具名。也可以用 `defineTool()` 定义自定义工具：

```typescript
import { Type } from "typebox";
import { createAgentSession, defineTool } from "@earendil-works/pi-coding-agent";

const myTool = defineTool({
  name: "my_tool",
  label: "My Tool",
  description: "Does something useful",
  parameters: Type.Object({ input: Type.String({ description: "Input value" }) }),
  execute: async (_toolCallId, params) => ({
    content: [{ type: "text", text: `Result: ${params.input}` }],
    details: {},
  }),
});

const { session } = await createAgentSession({ customTools: [myTool] });
```

**扩展、技能、上下文文件、Slash 命令**：都通过 `DefaultResourceLoader` 的 override 选项注入，模式高度一致——传一个 `xxxOverride` 回调，接收当前发现结果，返回合并后的新结果，然后 `await loader.reload()`。例如注入自定义 Prompt 模板：

```typescript
const customCommand: PromptTemplate = {
  name: "deploy",
  description: "Deploy the application",
  source: "(custom)",
  content: "# Deploy\n\n1. Build\n2. Test\n3. Deploy",
};

const loader = new DefaultResourceLoader({
  promptsOverride: (current) => ({
    prompts: [...current.prompts, customCommand],
    diagnostics: current.diagnostics,
  }),
});
await loader.reload();

const { session } = await createAgentSession({ resourceLoader: loader });
```

## 会话管理：树形结构与 SessionManager

Pi 的会话内部是一棵以 `id`/`parentId` 相连的树，支持原地分支：

```typescript
// 纯内存，不落盘
const { session } = await createAgentSession({ sessionManager: SessionManager.inMemory() });

// 新建持久化会话
const { session: persisted } = await createAgentSession({ sessionManager: SessionManager.create(process.cwd()) });

// 续接最近一次会话
const { session: continued, modelFallbackMessage } = await createAgentSession({
  sessionManager: SessionManager.continueRecent(process.cwd()),
});

// 打开指定会话文件
const { session: opened } = await createAgentSession({ sessionManager: SessionManager.open("/path/to/session.jsonl") });
```

`SessionManager` 还暴露了一套树遍历 API：`getEntries()`（不含头部的全部条目）、`getTree()`（完整树结构）、`getPath()`（根到当前叶子的路径）、`getLeafEntry()`、`getChildren(id)`，以及 `branch(entryId)` / `branchWithSummary(id, "...")` / `createBranchedSession(leafId)` 这类分支操作。这套设计和 RPC 协议里 `fork`/`clone`/`get_tree`/`get_entries` 命令是一一对应的——RPC 命令本质上就是把这些 SDK 能力包了一层 JSON 协议的壳。

## 三种内置运行模式

SDK 导出了三个运行模式函数，都构建在 `createAgentSessionRuntime()` 之上，是 CLI 三种运行方式（交互式 TUI、单次打印、RPC）背后真正的实现：

- **`InteractiveMode`**：完整的 TUI 交互模式，带编辑器、聊天历史和全部内置命令
- **`runPrintMode`**：单次模式，发送提示词、输出结果、退出
- **`runRpcMode`**：JSON-RPC 模式，供子进程集成使用，就是上一篇讲的协议的真正实现

```typescript
import { runRpcMode } from "@earendil-works/pi-coding-agent";
// runtime 的构造方式与前文 createAgentSessionRuntime 示例相同
await runRpcMode(runtime);
```

这三个函数的存在说明了一个重要事实：**RPC 模式不是与 SDK 平行的另一套实现，而是 SDK 之上的一层协议封装**。如果你在同一个 Node.js 进程里工作，直接用 SDK 提供的 `AgentSession`/`AgentSessionRuntime` 就够了；只有当你需要跨进程、跨语言时，才需要 `runRpcMode` 这一层。

## 小结与思考题

SDK 嵌入式集成的核心心智模型是：`createAgentSession()` 给你一个可以对话的 `AgentSession`；如果还需要支持"换一个会话"这类操作，再升级到 `createAgentSessionRuntime()` 拿到的 `AgentSessionRuntime`。模型、工具、扩展、技能、Prompt 模板、上下文文件、会话存储方式全部是可插拔配置项，`DefaultResourceLoader` 负责按约定路径自动发现，也可以用 `xxxOverride` 逐项覆盖。最重要的一点是：RPC 模式并非独立实现，而是 `runRpcMode()` 这个 SDK 导出函数包装出来的协议外壳，理解了 SDK 就理解了 RPC 模式的底层运作方式。

思考题：

1. 为什么 SDK 要把"单会话对话"（`AgentSession`）和"替换整个会话"（`AgentSessionRuntime`）拆成两层接口，而不是让 `AgentSession` 自己支持 `fork`/`switchSession`？这种拆分对事件订阅的生命周期管理有什么好处？
2. `preflightResult(true)` 只代表提示词"被受理"，`prompt()` 的 Promise 却要等到整个运行（含自动重试）结束才 resolve。如果你在构建一个需要"立刻知道用户输入是否合法"的 UI，应该基于哪个信号做判断，为什么不能直接 `await session.prompt(...)` 之后才更新 UI？
3. `noTools: "builtin"` 与 `excludeTools` 都能达到"少启用几个工具"的效果，但语义并不相同。如果你想构建一个"只允许调用某个自定义工具、完全禁用内置读写能力"的沙箱化子 Agent，应该用哪个组合？
