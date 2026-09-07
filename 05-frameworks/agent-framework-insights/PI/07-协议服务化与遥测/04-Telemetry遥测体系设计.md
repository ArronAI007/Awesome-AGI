# Telemetry 遥测体系设计

> `@earendil-works/pi-telemetry` 只做一件事：定义一套与任何具体监控后端（OpenTelemetry、Sentry、日志系统……）都无关的"span/事件/属性"契约，让 Pi 的其他包可以在完全不知道最终数据流向哪里的前提下，规范地记录"程序做了什么"。

## 学习目标

- 理解为什么要把遥测契约做成"厂商中立"的，而不是直接依赖某个具体的可观测性 SDK
- 掌握 Span（跨度）、Event（事件）、Attribute（属性）、Status（状态）、Context（上下文）这五个核心概念的含义与相互关系
- 读懂 `TelemetryContext`/`TelemetrySpan` 接口定义，理解 `startSpan()` 的回调式生命周期管理
- 理解 `NOOP_TELEMETRY_CONTEXT` 和 `InMemoryTelemetryContext` 两个内置实现分别解决什么问题
- 了解类型化 Schema 系统（`defineTelemetrySchema`/`createTypedSpanStarter`）如何在保持 span API 通用性的同时提供编译期属性校验

## 为什么需要一套"厂商中立"的遥测契约

`packages/telemetry/README.md` 开篇就点明了这个包提供的东西：一个"显式的、基于回调的 `TelemetryContext`/`TelemetrySpan` 契约"、一个共享的 `NOOP_TELEMETRY_CONTEXT`、一个参考实现 `InMemoryTelemetryContext`、可序列化的 schema 定义及其类型推导工具——但**不提供导出器（exporter）、不提供全局的"当前 span"状态、不依赖任何具体的遥测后端**。

这个设计选择背后的动机很直接：Pi 的核心包（`pi-ai`、`pi-agent-core`）需要在关键路径上打点记录"发生了什么"，但它们不应该被绑死在某一个具体的可观测性方案上。如果 `pi-ai` 直接 `import` OpenTelemetry SDK，那么每一个不需要 OpenTelemetry 的使用者都要被迫拖入这个依赖；反过来，如果完全不打点，排查生产问题时就会两眼一抹黑。厂商中立契约的做法是：核心包只依赖一套极简的接口和类型，**是否要真的把数据发送到某个后端、发送到哪个后端，完全交给应用层决定**——可以用官方提供的 `InMemoryTelemetryContext` 做本地诊断，可以完全不提供（此时退化为 `NOOP_TELEMETRY_CONTEXT`），也可以自己写一个适配器桥接到 OpenTelemetry、Sentry 或者日志系统。

## 核心概念

README 用一张表把五个概念讲得很清楚：

| 概念 | 通俗含义 |
|---|---|
| **Span（跨度）** | 一次操作的带时间记录，例如加载一个账户或发起一次 AI 请求。从工作开始前起，到工作完成时结束 |
| **父子 Span** | 操作可以嵌套更小的操作。一个请求 span 可能包含一次缓存查询和一次数据库查询，它们共同构成一棵展示时间花在哪里的树 |
| **Attribute（属性）** | 挂在 span 上的一个具名事实，例如 `provider: "openai"`、`cache.hit: true`、`item_count: 12`，描述这次操作及其结果 |
| **Event（事件）** | span 期间某个时间点发生的具名事情，例如 `retry.scheduled` 或 `cache.lookup`。事件没有持续时间，可以携带自己的属性 |
| **Status（状态）** | 操作的结局：`ok` 或 `error`。错误状态可以附带错误名称和消息 |
| **Context（上下文）** | 标识"新工作应该挂在 span 树的哪个位置"的句柄。从一个 context 开始一个 span，会让它成为该 context 的子节点 |

举例来说，加载一个账户的遥测数据可能长这样：

```text
example.account.load                         span
├─ attributes: account.id=123, found=true   span 上的事实
├─ event: example.cache.lookup              span 期间的一次事件
│  └─ attribute: cache.hit=false            事件上的事实
└─ status: ok                               最终结局
```

README 特别强调了一句很重要的原则：**span 是诊断数据，不是业务状态**。记录一个 span 绝不能影响账户加载这个操作本身是否执行、是否成功、是否被持久化——遥测永远是"旁路观察"，不能反过来干预业务逻辑。

## index.ts：核心接口

`packages/telemetry/src/index.ts` 定义的核心接口非常克制：

```typescript
export type AttributeValue = string | number | boolean | readonly string[] | readonly number[] | readonly boolean[];

export interface SpanAttributes {
	[name: string]: AttributeValue | undefined;
}

export interface SpanOptions {
	name: string;
	attributes?: SpanAttributes;
}

export type SpanStatus = { status: "ok" } | { status: "error"; error?: { name: string; message: string } };

export interface TelemetryContext {
	startSpan<T>(options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T>;
}

export interface TelemetrySpan extends TelemetryContext {
	addEvent(name: string, attributes?: SpanAttributes): void;
	setAttributes(attributes: SpanAttributes): void;
	setStatus(status: SpanStatus): void;
}
```

注意 `TelemetrySpan` 继承自 `TelemetryContext`——这正是"父子关系"在类型层面的体现：一个 span 本身也是一个可以启动子 span 的 context。属性值被限制为基本标量（字符串/数字/布尔）及其只读数组，这是刻意的：遥测属性应该是低维度、可序列化、不含敏感业务数据的元数据，不应该塞任意复杂对象进去。

`TelemetryContext.startSpan()` 是整个契约里唯一的核心方法，采用"回调式生命周期管理"——没有单独的 `span.end()` 方法：

```typescript
async function loadAccount(accountId: string, telemetryContext: TelemetryContext = NOOP_TELEMETRY_CONTEXT) {
  return telemetryContext.startSpan(
    { name: "example.account.load", attributes: { "example.account.id": accountId } },
    async (span) => {
      const account = await readAccount(accountId);
      span.setAttributes({ "example.account.found": account !== undefined });
      return account;
    },
  );
}
```

`startSpan()` 拥有"结算"span 的全部权力：回调返回值或 Promise 落定的那一刻，span 就自动结束。这个设计消除了一整类常见 bug——手动调用 `span.end()` 的方案里，很容易因为提前 `return`、抛异常没走到 `finally`，或者忘记调用而导致 span 永远不结束或提前结束。

要建立父子嵌套，只需要把回调收到的 `span` 继续传给下一层 `startSpan()`：

```typescript
return telemetryContext.startSpan({ name: "example.parent" }, async (parentSpan) => {
  return parentSpan.startSpan({ name: "example.child" }, async (childSpan) => {
    childSpan.addEvent("example.cache.lookup", { "example.cache.hit": true });
    return performWork();
  });
});
```

对于"正常返回值也可能代表业务失败"的场景（比如返回一个 `{ ok: false, reason }` 而不是抛异常），需要显式调用 `setStatus()`：

```typescript
return telemetryContext.startSpan({ name: "example.save" }, async (span) => {
  const result = await save();
  if (!result.ok) {
    span.setStatus({ status: "error", error: { name: "SaveError", message: result.reason } });
  }
  return result;
});
```

Adapter（适配器，即真正对接后端的实现）契约还要求：正常完成默认视为 `ok`，抛异常/被拒绝默认视为 `error`（除非已经显式设置过状态）；重复调用 `setStatus()` 以最后一次为准；`setAttributes()` 多次调用要合并、后设置的值覆盖先设置的、`undefined` 被忽略；结算之后的任何记录调用都应该被安静地忽略；记录方法本身必须是同步、被动、不抛异常的，遥测记录失败绝不能影响业务回调的执行。

## NOOP_TELEMETRY_CONTEXT：默认禁用遥测

`packages/telemetry/src/noop.ts` 提供了一个全局共享的空实现：

```typescript
const noopTelemetrySpan: TelemetrySpan = {
	startSpan: startNoopSpan,
	addEvent: () => {},
	setAttributes: () => {},
	setStatus: () => {},
};
Object.freeze(noopTelemetrySpan);

export const NOOP_TELEMETRY_CONTEXT: TelemetryContext = noopTelemetrySpan;
```

它的实现极其简单：`addEvent`/`setAttributes`/`setStatus` 全是空函数，`startSpan()` 只是同步调用回调、原样传递返回值或异常，甚至嵌套的子 span 用的还是**同一个**冻结的单例对象（不会为每层嵌套分配新对象）。这意味着当一个应用没有提供任何具体的 `TelemetryContext` 实现时（默认参数 `= NOOP_TELEMETRY_CONTEXT`），所有的埋点调用在运行时几乎零开销——不做任何检查、不分配任何对象、不保留任何名字或属性。这正是"默认禁用遥测"的落地方式：不是靠一个 `if (telemetryEnabled)` 分支判断，而是靠一个满足同一接口、什么都不做的对象。

## InMemoryTelemetryContext：参考实现

`packages/telemetry/src/memory.ts` 提供了一个后端无关的内存实现，适合测试、本地诊断，或者应用方确实只想要"进程内捕获，不需要导出到任何外部系统"的场景：

```typescript
const telemetry = new InMemoryTelemetryContext();

await telemetry.startSpan(
  { name: "example.operation", attributes: { input: "demo" } },
  async (span) => {
    span.addEvent("example.started");
    span.setAttributes({ output_count: 3 });
  },
);

console.log(telemetry.getSpans());
```

内部实现值得细读几个点。首先是属性合并逻辑，体现了"后设置覆盖先设置、`undefined` 被忽略"的规则：

```typescript
function mergeAttributes(current: SpanAttributes, attributes: SpanAttributes): SpanAttributes {
	const merged = copyAttributes(current);
	for (const [name, value] of Object.entries(attributes)) {
		if (value !== undefined) merged[name] = copyAttributeValue(value);
	}
	return merged;
}
```

其次是自动状态推断——只有在调用方**没有**显式调用过 `setStatus()` 时，才会根据回调是否抛异常自动填充状态：

```typescript
function settleSpan(state: InMemoryTelemetryState, span: MutableRecordedTelemetrySpan, failed: boolean, error?: unknown): void {
	if (span.settled) return;
	if (failed && !span.explicitStatus) span.status = automaticErrorStatus(error);
	span.settled = true;
	span.endSequence = state.nextEndSequence++;
}
```

`explicitStatus` 这个标记正是"显式状态优先于自动推断"规则的实现载体。另外一个容易忽视但很重要的细节是：如果父 span 已经结算（`parent?.settled`），`startInMemorySpan()` 会直接退化为调用 `NOOP_TELEMETRY_CONTEXT.startSpan()`——防止在一个逻辑上已经"结束"的父节点下继续挂载新的子记录，造成数据结构上的错乱。所有记录方法（`addEvent`/`setAttributes`/`setStatus`）内部也都包了 `try/catch`，捕获到异常就静默忽略——这正是契约里"记录失败绝不能影响业务回调"要求的具体落地。

`getSpans()` 返回的是**按 span 开始顺序**排列的分离快照（`RecordedTelemetrySpan[]`），每个快照包含确定性的数字 ID、父 ID、合并后的属性、有序事件列表、最终状态、结算状态和结束序号，但**不记录任何时间戳**——因为这是一个进程内诊断工具而不是真正的性能剖析后端，保持确定性比记录真实耗时更重要（也让基于它写单元测试更容易）。

需要注意 README 里的告诫：`InMemoryTelemetryContext` 的存储是无界的、进程本地的，长期运行的进程如果一直复用同一个实例会造成内存持续增长；应该为每个测试或独立的记录范围创建新实例，并且不要在其中捕获调用方数据策略不允许的敏感属性。

## 类型化 Schema：让 span 词汇表可编译期校验

底层的 `startSpan(options, callback)` API 故意保持"开放"——名字是任意字符串，属性是任意的 `SpanAttributes` 键值包，这是为了让适配器保持通用性。但业务包（领域包）往往想要一套**封闭、可序列化**的 span 词汇表，并且希望 TypeScript 能在编译期校验属性名和类型。这就是 `defineTelemetrySchema()` 和 `createTypedSpanStarter()` 要解决的问题：

```typescript
export const EXAMPLE_TELEMETRY_SCHEMA = defineTelemetrySchema({
  version: 1,
  spans: {
    "example.read": {
      description: "Read one resource",
      parents: { kind: "any" },
      startAttributes: {
        "example.resource": { type: "string", required: true, values: ["account", "project"], description: "Resource kind" },
      },
      endAttributes: {
        "example.item_count": { type: "number", description: "Number of returned items" },
      },
      events: {
        "example.cache": {
          description: "Cache lookup result",
          attributes: { "example.cache.hit": { type: "boolean", required: true, description: "Whether the cache contained the resource" } },
        },
      },
      status: { default: "ok", errorWhen: "The read throws or returns an error result" },
    },
  },
} as const);

const startSpan = createTypedSpanStarter(telemetryContext, [EXAMPLE_TELEMETRY_SCHEMA]);
```

`defineTelemetrySchema()` 本质上只是一个"类型恒等函数"——它不做任何运行时校验，只是把传入的对象原样返回，同时利用 TypeScript 的类型推导把 schema 结构固定下来。真正产生类型魔法的是 `createTypedSpanStarter()`：它绑定一个 `TelemetryContext` 和一组 schema，返回一个"每个 span 名字一个重载"的函数，调用时 TypeScript 会强制要求传入该 span 声明的必填 `startAttributes`、拒绝未声明的多余键，回调里拿到的 `span` 对象的 `addEvent()`/`setAttributes()` 也被收窄到只接受该 span 声明的事件名和结束属性：

```typescript
await startSpan("example.read", { "example.resource": "account" }, async (span, startChildSpan) => {
  span.addEvent("example.cache", { "example.cache.hit": true });
  const accounts = await readAccounts();
  span.setAttributes({ "example.item_count": accounts.length });

  await startChildSpan("example.read", { "example.resource": "project" }, async (childSpan) => {
    const projects = await readProjects();
    childSpan.setAttributes({ "example.item_count": projects.length });
  });

  return accounts;
});
```

这里有一个值得强调的区分：`startAttributes` 是 span 开始时就已知、随创建调用一起传入的（是否必填由每个属性定义显式声明）；`endAttributes` 则代表"随着操作推进逐渐变得可知"的信息，通过回调里的 `setAttributes()` 追加，并且**永远是可选的**——因为提前失败、被取消，或者某些 provider 特定的数据在某些路径上根本不存在，都可能导致某个结束属性从未被设置。二者最终都落在同一个后端 span 上，"结束属性"只是一种语义上的分类，不是独立的存储或独立的"结束回调"。

Schema 层还支持组合多个独立版本化的 schema（`createTypedSpanStarter(context, [SCHEMA_A, SCHEMA_B])`），并在编译期拒绝跨 schema 的重复 span 名字。`defineTelemetrySchema()`/schema 对象本身只是普通的、可 JSON 序列化的数据，不会在运行时被解析或强制校验——所有的校验价值都发生在 TypeScript 编译阶段。

## 包职责划分

README 明确划分了各包在遥测这件事上的职责边界：

- **`@earendil-works/pi-telemetry`**：拥有厂商中立的契约本身、no-op 与内存参考 context、schema 工具、适配器一致性测试套件
- **`@earendil-works/pi-ai`**：在 provider 请求选项里接受并透传 `telemetryContext`，但**不拥有**任何遥测 schema
- **`@earendil-works/pi-agent-core`**：拥有并导出 Pi 自己的 AI 请求与 harness（运行时框架）schema，以及组合后的只读 schema 元组和类型化 span 辅助函数

```typescript
import {
  AGENT_TELEMETRY_SCHEMAS,
  AI_TELEMETRY_SCHEMA,
  HARNESS_TELEMETRY_SCHEMA,
  startAiSpan,
  startHarnessSpan,
} from "@earendil-works/pi-agent-core";
```

Pi 自己的 schema 使用 `pi.ai.*`、`pi.harness.*`、`pi.session.*` 这样带命名空间前缀的 span 名字。适配器可以把这些名字翻译成后端约定的命名规范，但不会改变 Pi 对外发出的这套词汇表本身——这保证了不管接入哪个具体后端，Pi 产生的遥测数据在语义上都是一致、可对比的。

## 适配器一致性测试

`@earendil-works/pi-telemetry/testing` 子路径导出了一套与测试框架无关的适配器一致性测试用例（`createTelemetryAdapterConformance()`），用法是提供一个"给出新鲜 context、并把该后端已完成的 span 转换成标准化 `RecordedTelemetrySpan` 快照"的 fixture：

```typescript
const conformance = createTelemetryAdapterConformance(async () => {
  const adapter = createMyTelemetryAdapter();
  return {
    context: adapter.context,
    getSpans: async () => adapter.normalizedSpans(),
    async [Symbol.asyncDispose]() { await adapter.close(); },
  };
});
```

这套测试套件检查的内容覆盖了前面提到的几乎所有契约要求：同步单次准入、结果与异常的原样传递、自动与显式状态、属性合并、事件顺序、结算后调用的惰性、嵌套与并发场景下的父子关系正确性，以及对不可读遥测负载失败的抑制。这意味着任何人想为 Pi 写一个自定义的 OpenTelemetry/Sentry/日志适配器，都可以直接跑这套测试来验证自己的实现是否符合契约，而不需要凭空猜测边界行为。

## 安全与可移植性

README 的最后一节强调了两条边界：第一，遥测是进程内诊断信息，不是持久化的应用状态——不应该把 `TelemetryContext`、`TelemetrySpan` 或某个后端原生的 trace 对象持久化进记录、消息、快照或延迟句柄里；第二，属性值被有意限制为基本标量和数组，领域侧的埋点代码应该避免把 Prompt、模型补全内容、工具参数或输出、文件内容、provider 原始负载、请求头、凭证或自由格式的错误细节塞进属性里，除非对应的 schema 和数据策略明确允许。这两条限制合在一起，本质上是在提醒使用者：遥测系统不应该变成"影子数据库"或"影子日志系统"，它应该始终是可丢弃的、面向可观测性场景的旁路数据。

包本身也不使用 `AsyncLocalStorage` 或其他运行时特定的隐式上下文 API，因此可以在 Node.js、Bun、浏览器和 Worker 环境中使用；具体的运行时兼容性由各个后端适配器自己负责。

## 小结与思考题

`pi-telemetry` 的设计哲学可以概括为一句话：**核心包只依赖一个几乎不能再小的接口（`startSpan`/`addEvent`/`setAttributes`/`setStatus`），把"数据到底发到哪里"这个决定完全推给应用层**。`NOOP_TELEMETRY_CONTEXT` 让"不需要遥测"成为零开销的默认状态，`InMemoryTelemetryContext` 让"只想本地看一眼"变得触手可及，类型化 Schema 系统则在不牺牲底层 API 通用性的前提下，给领域包提供了编译期就能校验的强类型埋点体验。适配器一致性测试套件进一步把这套契约的行为要求变成了可执行、可复用的验证工具，而不是停留在文档里的约定。

思考题：

1. 为什么 `TelemetryContext.startSpan()` 要设计成"接收回调、返回 Promise"的形态，而不是提供一个 `const span = context.startSpan(options); ... span.end();` 这样更"命令式"的 API？结合"span 数量必须与业务操作数量精确对应"这个隐含要求想一想。
2. `InMemoryTelemetryContext` 在父 span 已结算的情况下会退化为调用 `NOOP_TELEMETRY_CONTEXT`，而不是抛异常或忽略调用直接返回 `undefined`。这个选择对调用方代码有什么好处？如果换成"直接抛异常"，会给业务代码带来什么负担？
3. `startAttributes` 要求显式声明每个属性是否 `required`，而 `endAttributes` 永远是可选的。结合"提前失败、被取消、provider 特定数据只在部分路径存在"这几种场景，说说如果反过来把某个关键结束属性设成必填会遇到什么实际问题。
