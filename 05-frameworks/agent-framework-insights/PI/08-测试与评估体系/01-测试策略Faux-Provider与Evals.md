# 测试策略：Faux Provider 与 Evals

> pi 的测试体系分三层：不依赖模型的确定性单元/集成测试、需要真实密钥才会激活的 e2e 测试，以及专门评测 Agent 在真实任务上表现质量的 evals 体系；用一个"假的"模型 provider（faux provider）把 Agent 逻辑测试和真实 API 彻底解耦，是贯穿整个测试策略的核心设计。

## 学习目标

- 理解 pi 仓库里单元/集成测试、e2e 测试、evals 三者的定位差异，以及为什么它们不能互相替代。
- 知道 `./test.sh` 具体做了什么、为什么不能直接跑完整的 `vitest` 套件，以及如何针对单个测试文件跑测试（vitest 包与 `packages/tui` 的命令是不同的）。
- 读懂 `packages/coding-agent/test/suite/harness.ts` 如何用 faux provider 搭建一个可编排对话脚本的测试沙盒。
- 理解 `packages/evals/` 的定位：它评测的是 Agent 在真实模型驱动下完成任务的质量，而不是"这行代码对不对"。
- 掌握回归测试（regression test）的目录组织约定，能够按规范新增一个回归测试文件。

## 一、三层测试体系总览

pi 的测试并不是"一个 vitest 命令跑到底"，而是按照是否需要真实模型、是否需要真实密钥，拆成了三个性质不同的层次：

| 层次 | 位置 | 是否需要真实 API/密钥 | 目的 |
|---|---|---|---|
| 单元/集成测试 | 各包 `test/`（`vitest`），`packages/tui` 用 `node:test` | 不需要（用 faux provider 或纯逻辑断言） | 验证代码逻辑正确性，CI 常态化运行 |
| e2e 测试 | 与单元测试混在同一批文件里，靠 `describe.skipIf` 判断环境变量 | 需要真实 provider 的密钥 | 验证与真实厂商 API 的对接细节（如流式协议、认证方式的边界情况） |
| Evals | `packages/evals/` | 需要真实 provider 的密钥（通过 `--provider`/`--model` 或环境变量指定） | 评测 Agent 在真实任务上的行为质量，而非断言式对错 |

这三层的关系是互补而非替代：单元测试保证"逻辑没写错"，e2e 测试保证"和真实厂商 API 对接没问题"，evals 保证"模型 + 工具 + 提示词组合出来的整体行为是好的"。三者混用同一套 `vitest`，但触发条件和运行成本完全不同，这也是为什么仓库要专门写脚本把它们分开管理。

### e2e 测试的识别方式：`describe.skipIf`

pi 没有把 e2e 测试放进单独目录，而是让它们和普通单元测试文件混在一起，通过 `describe.skipIf(!process.env.XXX_API_KEY)` 在没有密钥时自动跳过。例如 `packages/ai/test/anthropic-opus-4-8-smoke.test.ts`：

```ts
describe.skipIf(!process.env.ANTHROPIC_API_KEY)("Anthropic Opus 4.8 smoke", () => {
	...
});
```

`packages/ai/test/openai-responses-reasoning-replay-e2e.test.ts` 甚至需要两个密钥同时存在才会运行：

```ts
describe.skipIf(!process.env.OPENAI_API_KEY || !process.env.ANTHROPIC_API_KEY)(
	"OpenAI Responses reasoning replay e2e",
	() => {
		...
	},
);
```

这正是根目录 `AGENTS.md` 里那句话的依据：

> Never run the full vitest suite directly: it includes e2e tests that activate when endpoint/auth env vars are present.

也就是说，如果你在本地已经配置了某个 provider 的密钥（比如为了正常使用 pi），直接跑完整 `vitest` 套件会把这些 e2e 测试也激活，产生真实的网络请求和真实的 token 消耗——这既不确定（依赖外部服务可用性），也不便宜（消耗真实配额），因此仓库明确禁止。

## 二、`./test.sh`：如何在"干净房间"里跑测试

根目录的 `test.sh`（完整内容见仓库根目录）不是简单地调用 `npm test`，而是先构造一个隔离的执行环境，再把环境变量清空到只保留必需项，然后才执行 `npm test`。关键逻辑：

```bash
temp_parent="${TMPDIR:-/tmp}"
test_root="$(mktemp -d "$temp_parent/pi-test.XXXXXX")"
...
test_env=(
	"PATH=$PATH" "PWD=$PWD"
	"HOME=$test_root/home" "TMPDIR=$test_root/tmp"
	"XDG_CONFIG_HOME=$test_root/home/.config" "XDG_CACHE_HOME=$test_root/cache"
	"LANG=C" "LC_ALL=C" "TZ=UTC"
	"GIT_CONFIG_NOSYSTEM=1" "GIT_CONFIG_GLOBAL=/dev/null"
	...
	"PI_NO_LOCAL_LLM=1"
	...
)
echo "Running tests without API keys in isolated home: $test_root/home"
env -i "${test_env[@]}" npm test
```

这段脚本做了两件事：把 `HOME`、`TMPDIR`、npm 配置、git 配置全部重定向到一个刚创建的临时目录，避免测试读取或污染开发者本机的真实配置（例如 `~/.pi`、`~/.gitconfig`、全局 npm 缓存）；用 `env -i` 丢弃当前 shell 的所有环境变量（包括任何已经设置的 `ANTHROPIC_API_KEY`、`OPENAI_API_KEY` 等），只保留脚本显式列出的白名单。这样一来，即使开发者本机配置了真实密钥，`test.sh` 跑起来的进程里也看不到这些密钥，`describe.skipIf` 自然会跳过所有 e2e 测试。脚本结束时用 `trap cleanup EXIT` 清理临时目录，并且做了归属校验（检查 `.pi-test-owned` 标记文件）后才允许 `rm -rf`，避免误删非预期路径。

`npm test` 本身在根 `package.json` 中定义为：

```json
"test": "npm run test:scripts && npm run test --workspaces --if-present"
```

即先跑 `scripts/*.test.mjs`（用 `node --test`），再对每个 workspace 执行各自的 `test` 脚本（存在才跑）。各包的 `test` 脚本并不统一：

- `packages/ai`、`packages/agent`、`packages/coding-agent`：`"test": "vitest --run"`
- `packages/tui`：`"test": "node --test --test-reporter=dot --test-reporter-destination=stdout test/*.test.ts"`（不用 vitest，直接用 Node 内建的 `node:test`）
- `packages/evals`：`"test": "vitest run --config vitest.test.config.ts"`（注意这是 evals 包自身基础设施的单元测试，不是运行 eval 任务）

### 跑单个测试文件

`AGENTS.md` 给出的准确命令（按包类型区分）：

对使用 vitest 的包（例如 `packages/coding-agent`、`packages/ai`、`packages/agent`），从包根目录执行：

```bash
node "$(git rev-parse --show-toplevel)/node_modules/vitest/dist/cli.js" --run test/specific.test.ts
```

之所以不直接写 `npx vitest --run test/specific.test.ts`，是为了明确指向仓库根 `node_modules` 里的 vitest 可执行文件（monorepo 场景下 `npx` 有时会解析到错误的版本或提示交互式安装）。

对 `packages/tui`（用 `node:test`，不是 vitest），从 `packages/tui` 目录执行：

```bash
node --test test/specific.test.ts
```

两者命令形态完全不同，混用会直接报错——这也是为什么这条规则在 `AGENTS.md` 里被单独列出来。

## 三、Faux Provider：不消耗真实配额的假模型

`packages/coding-agent/test/suite/` 是仓库里"新一代"的 Agent 测试目录，`test/suite/README.md` 明确写了规则：

```text
Use `test/suite/` for the new harness-based test suite around `AgentSession` and `AgentSessionRuntime`.

Rules:
- Use `test/suite/harness.ts`
- Use the faux provider from `packages/ai/src/providers/faux.ts`
- Do not use real provider APIs, real API keys, network calls, or paid tokens
- Keep these tests CI-safe and deterministic
```

也就是说，任何要测试 `AgentSession`（对话生命周期、工具调用、压缩、扩展等）行为的新测试，一律不允许接触真实的模型 API，而要用 faux provider 模拟一个"听话的假模型"。

### faux provider 的核心思路

`packages/ai/src/providers/faux.ts`（708 行）实现了一个完整的、遵循 pi 内部 provider 接口的假 provider。它不会真的发网络请求，而是从一个预先设置好的"响应脚本"队列里按顺序取出结果返回给调用方，并且完整模拟了流式增量（`text_start`/`text_delta`/`text_end` 等事件）、思考内容（thinking）、工具调用、usage 估算、甚至 deferred（异步轮询）和 abort（中断）等真实 provider 才有的复杂行为。

几个关键的构建块：

```ts
export function fauxToolCall(name: string, arguments_: ToolCall["arguments"], options: { id?: string } = {}): ToolCall {
	return { type: "toolCall", id: options.id ?? randomId("tool"), name, arguments: arguments_ };
}

export function fauxAssistantMessage(
	content: string | FauxContentBlock | FauxContentBlock[],
	options: { stopReason?: AssistantMessage["stopReason"]; ... } = {},
): AssistantMessage { ... }

export type FauxResponseFactory = (
	context: Context,
	options: SimpleStreamOptions | undefined,
	state: FauxProviderState,
	model: Model<string>,
) => AssistantMessage | Promise<AssistantMessage>;

export type FauxResponseStep = AssistantMessage | FauxResponseFactory;
```

`fauxAssistantMessage` + `fauxToolCall` 组合起来，就能像编排剧本一样，声明"模型第一轮要调用哪个工具、第二轮说什么话"。响应也支持传入一个函数（`FauxResponseFactory`），根据当前上下文动态生成回复，用于测试需要"看到用户说了什么再决定怎么回"的场景。流式回复是逐 token 模拟出来的，真实还原了打字机式的增量推送（`streamWithDeltas` 内部按 `splitStringByTokenSize` 把文本切成若干"假 token"，逐块 push 到事件流里），这让依赖流式事件的 UI/日志逻辑也能被覆盖到，而不只是测试"最终结果对不对"。

### `test/suite/harness.ts`：把 faux provider 接到真实的 `AgentSession` 上

`harness.ts` 里的 `createHarness()` 做的事情，是搭一个"五脏俱全但完全内存化"的测试环境：注册 faux provider、伪造一个 provider 的 API Key（`"faux-key"`）、用内存版的 `SessionManager`/`SettingsManager`/`AuthStorage`，最后实例化一个真实的 `AgentSession`：

```ts
export async function createHarness(options: HarnessOptions = {}): Promise<Harness> {
	const tempDir = createTempDir();
	const fauxProvider: FauxProviderRegistration = registerFauxProvider({ models: options.models });
	fauxProvider.setResponses([]);
	const model = fauxProvider.getModel();
	const sessionManager = SessionManager.inMemory();
	const settingsManager = SettingsManager.inMemory(options.settings);
	const authStorage = AuthStorage.inMemory();
	if (withConfiguredAuth) {
		await authStorage.modify(model.provider, async () => ({ type: "api_key", key: "faux-key" }));
	}
	const agent = new Agent({
		getApiKey: () => (withConfiguredAuth ? "faux-key" : undefined),
		streamFn: streamSimple,
		initialState: { model, systemPrompt: options.systemPrompt ?? "You are a test assistant.", tools: [] },
		...
	});
	const session = new AgentSession({ agent, sessionManager, settingsManager, cwd: tempDir, ... });
	return {
		session, sessionManager, settingsManager, authStorage,
		faux: fauxProvider, setResponses: fauxProvider.setResponses, events, eventsOfType, tempDir,
		cleanup() {
			session.dispose();
			fauxProvider.unregister();
			if (existsSync(tempDir)) rmSync(tempDir, { recursive: true });
		},
	};
}
```

测试文件拿到 `Harness` 之后，典型用法是：先用 `harness.setResponses([...])` 编排好"模型接下来要说什么/调用哪个工具"，再调用 `harness.session.prompt(...)` 触发真实的 Agent 主循环，最后用 `harness.events`（订阅 `AgentSession` 抛出的事件）或 `getAssistantTexts(harness)`/`getUserTexts(harness)` 之类的辅助函数断言结果。`packages/coding-agent/test/suite/regressions/2023-queued-slash-command-followup.test.ts` 是一个很典型的例子：

```ts
harness.setResponses([
	fauxAssistantMessage(fauxToolCall("wait", {}), { stopReason: "toolUse" }),
	fauxAssistantMessage("first turn complete"),
	fauxAssistantMessage("queued follow-up handled by model"),
]);

const promptPromise = harness.session.prompt("start");
await sawToolStart;
extensionApi?.sendUserMessage("/testcmd queued", { deliverAs: "followUp" });
releaseToolExecution?.();
await promptPromise;

expect(commandRuns).toEqual([]);
expect(getAssistantTexts(harness)).toContain("queued follow-up handled by model");
```

这个测试完全没有联网，也没有用到任何真实密钥，却完整跑通了"用户输入 → 模型决定调用工具 → 工具执行中排队一条 slash 命令 → 工具执行完毕 → 模型继续回复"这样一条真实的、有时序竞争的业务链路。这正是 faux provider 模式的价值所在：**把"模型会怎么回复"变成一个可以由测试代码完全掌控的确定性输入**，从而让原本高度依赖外部不确定性（真实模型的输出）的 Agent 逻辑，变成可以用传统单元测试手法覆盖的确定性代码。

## 四、Evals：评测行为质量，而不是断言对错

`packages/evals/` 是一个独立的包，`packages/evals/README.md` 开篇就把它和普通测试区分开：

> Pi evals are behavioral, model-backed checks for Pi workflows. They adapt a real `AgentSession` to `vitest-evals`, run it in isolated temporary project and agent directories, and attach native Pi session artifacts. Use them to measure end-to-end behavior and compare prompts, tools, skills, models, or other harness configurations.

关键区别在于：faux provider 测试用假模型验证"代码逻辑对不对"，而 evals 用**真实模型**验证"给定这套提示词、工具、模型组合，Agent 完成真实任务的效果好不好"。这是两个完全不同维度的问题——代码逻辑正确不代表提示词写得好，反之亦然。

### `pi-harness.ts`：把真实 `AgentSession` 接入 `vitest-evals`

`packages/evals/src/pi-harness.ts` 提供的 `createPiCodingAgentHarness(...)` 是 evals 的核心脚手架。它在临时目录里创建一个真实的工作区和 agent 目录，用真实的 `ModelRuntime` 解析出真实的模型（provider + model id 来自 CLI 参数或环境变量 `PI_PROVIDER`/`PI_MODEL`），实例化一个真实的 `AgentSession` 并对其下达 prompt：

```ts
export function resolveModelSelection(
	explicitModel: PiCodingAgentModelSelection | undefined,
	environment: { PI_PROVIDER?: string; PI_MODEL?: string } = process.env,
): PiCodingAgentModelSelection {
	const provider = (explicitModel?.provider ?? environment.PI_PROVIDER)?.trim();
	const id = (explicitModel?.id ?? environment.PI_MODEL)?.trim();
	if (!provider || !id) {
		throw new Error("Select a harness model explicitly or set both PI_PROVIDER and PI_MODEL as defaults.");
	}
	return { provider, id };
}
```

运行时通过：

```bash
npm run eval -- --provider openai --model gpt-5.6-sol
# 等价于
PI_PROVIDER=openai PI_MODEL=gpt-5.6-sol npm run eval
```

也就是说，运行 evals **必须**提供一个真实可用的 provider 和模型（以及对应的认证信息，走 pi 正常的 `ModelRuntime` 逻辑，可以是订阅凭证也可以是 API Key 环境变量）。这与前面单元测试"绝不使用真实密钥"的原则形成了鲜明对比——evals 存在的意义就是观察真实模型的真实行为。

每次运行会在 `packages/evals/.eval/` 下生成一个带时间戳的 artifact 目录，`runs.jsonl` 记录每次 harness 运行，并把原生的 pi 会话 JSONL 附加在 `sessions/` 下——这意味着 eval 产物里可能包含真实的 prompt、模型输出、工具调用细节，需要按敏感数据对待。

### `smoke.eval.ts`：最基础的端到端可用性检查

`packages/evals/src/smoke.eval.ts` 是最简单的一个 eval，只验证"Agent 能不能正常跑完一轮真实对话并给出正确答案"：

```ts
const piCodingAgentHarness = createPiCodingAgentHarness({ noTools: "all" });

describeEval("Pi Coding Agent smoke", { harness: piCodingAgentHarness }, (it) => {
	it("runs a basic prompt end to end", async ({ run }) => {
		const result = await run("What's the capital of France? Respond with only the city name.");

		expect(result.output.trim()).toBe("Paris");
		expect(result.errors).toEqual([]);
		expect(result.usage.provider).toBe(process.env.PI_PROVIDER);
		expect(result.usage.model).toBe(process.env.PI_MODEL);
		expect(result.usage.totalTokens).toBeGreaterThan(0);
	});
});
```

它用 `noTools: "all"` 关闭了全部工具，只测最基础的"发消息、收回答"链路，本质上是给整条真实调用链（模型解析 → 认证 → 请求 → 解析响应 → session 记账）做一次冒烟测试（smoke test）。

### `extensions.eval.ts`：评测更复杂的、带工具调用的完整工作流

`packages/evals/src/extensions.eval.ts` 复杂得多，它验证的是"Agent 能否根据系统提示词的指引，正确地创建一个 pi 扩展、reload 加载它、再调用扩展注册的工具完成任务"。它用 `createJudge<...>(...)` 定义了一个基于规则的评委函数，检查生成的扩展源码是否 import 了正确的包、扩展是否成功加载、工具调用参数和返回值是否符合预期：

```ts
const ExtensionAuthoringJudge = createJudge<PiCodingAgentInput, ExtensionAuthoringOutput>(
	"ExtensionAuthoringJudge",
	({ output, toolCalls }) => {
		const failures: string[] = [];
		if (output.extensionSource === null) {
			failures.push("generated extension source is unavailable");
		} else if (!imports.includes("@earendil-works/pi-coding-agent")) {
			failures.push("extension does not import the canonical @earendil-works/pi-coding-agent package");
		}
		return {
			score: failures.length === 0 ? 1 : 0,
			metadata: { rationale: failures.length === 0 ? "Extension authoring workflow completed." : failures.join("; ") },
		};
	},
);
```

更值得注意的是它用 `evalHarnessTable(...)` 做了一次**对照实验**：把"系统提示词里包含扩展开发指南和 pi 文档" vs "不包含"这两种情况各跑一遍相同的任务，比较两组的通过率差异：

```ts
const extensionHarnessTable = evalHarnessTable("Pi extension authoring system prompt", {
	baseline: createExtensionAuthoringHarness("system-prompt-without-docs", excludeGuidelinesAndDocumentation),
	candidate: createExtensionAuthoringHarness("default-system-prompt", prepareDefaultPromptOverride),
});
```

这正是"评测 Agent 行为质量"和"传统断言式单元测试"的本质区别：单元测试问的是"这段代码是否符合规格"，是非黑即白的；evals 问的是"这套提示词/工具/模型的组合，在真实模型的不确定性下，完成任务的成功率有多高"，是概率性的、需要用对照组和评分机制来衡量的。`README.md` 里也明确建议对照实验类的 eval 把 `judgeThreshold: null`，让低分只作为观察记录而不直接判失败——因为真实模型输出本身就有波动。

`packages/evals/vitest.config.ts` 和 `packages/evals/vitest.test.config.ts` 是两份不同配置：前者用于跑真正的 eval 任务（`npm run eval`），后者用于跑 evals 这个包自身基础设施代码的单元测试（`npm run test`，验证 `harness-table.ts`、`summary.ts`、`artifacts.ts` 这些工具函数本身没写错）——这两者不要混淆：一个是"用 evals 评测 pi"，一个是"测试 evals 工具本身"。

## 五、回归测试的组织约定

`packages/coding-agent/test/suite/README.md` 对回归测试（regression test，即"针对某个已报告的具体 bug 补的测试"）给出了明确约定：

```text
Organization:
- Put broad lifecycle and characterization tests directly under `test/suite/`
- Put issue-specific regression tests under `test/suite/regressions/`
- Name regression tests as `<issue-number>-<short-slug>.test.ts`
- Example: `test/suite/regressions/2023-queued-slash-command-followup.test.ts`
```

翻开 `test/suite/regressions/` 目录，可以看到这条约定被严格执行，文件名清一色是 `<issue 编号>-<简短描述>.test.ts` 的格式，例如：

```text
2023-queued-slash-command-followup.test.ts
3317-network-connection-lost-retry.test.ts
5109-exclude-tools.test.ts
7290-json-stream-linear.test.ts
```

也存在个别没有编号前缀的文件（如 `pre-prompt-compaction-no-continue.test.ts`、`startup-session-rebind-duplicate-subscription.test.ts`），说明该约定的核心是"从 issue 编号能一眼追溯到问题背景"，编号是主要形式，但并非对所有回归测试都强制要求（这类没有编号的文件具体是历史遗留还是没有对应 issue，仓库文档里没有进一步说明，这里如实说明未找到确切依据）。这种命名方式的好处很直接：几年后再看到这个测试文件，不需要看测试内容就知道它在防止哪个历史 bug 复现，也能顺藤摸瓜找到当年的 issue 讨论上下文。

新增回归测试时，`AGENTS.md` 的要求是放在 `packages/coding-agent/test/suite/regressions/`，同样必须使用 `test/suite/harness.ts` 和 faux provider，不能引入真实 provider 依赖。

## 动手练习

1. **跑通一个具体的 faux provider 测试**：克隆仓库后，在 `packages/coding-agent` 目录下执行

   ```bash
   node "$(git rev-parse --show-toplevel)/node_modules/vitest/dist/cli.js" --run test/suite/regressions/2023-queued-slash-command-followup.test.ts
   ```

   跑通后，尝试修改 `harness.setResponses([...])` 里的某一步（比如把 `fauxAssistantMessage("first turn complete")` 的文本改掉），重新运行并观察哪一条断言失败，体会 faux provider 是如何让"模型说什么"变成完全可控的测试输入的。

2. **在 `packages/tui` 里跑一个 `node:test` 测试**：进入 `packages/tui` 目录，执行

   ```bash
   node --test test/keys.test.ts
   ```

   对比它和上一步 vitest 命令在调用方式、输出格式上的差异，确认自己记住了"vitest 包"和"`packages/tui`"两种不同的单测试文件运行方式。

（可选，需要真实密钥）**跑一次 smoke eval**：如果你手头有可用的 provider 密钥，可以在仓库根目录执行 `npm run eval -- --provider <你的provider> --model <你的模型> -- src/smoke.eval.ts`，跑完后查看 `packages/evals/.eval/` 下生成的 `runs.jsonl` 和会话 JSONL 文件，直观感受 evals 产物和普通测试报告的区别。

## 小结

pi 把"测试代码逻辑"和"评测 Agent 行为质量"当成两件完全不同的事情来对待：单元/集成测试靠 `packages/ai/src/providers/faux.ts` 提供的假模型 provider，把不确定的外部依赖从测试关键路径上剔除，换来又快又稳定、可以放心跑在 CI 里的确定性测试；e2e 测试通过 `describe.skipIf` 与真实密钥的环境变量挂钩，默认不跑，只有显式配置了对应密钥才会激活，因此绝不能直接跑完整 `vitest` 套件，必须用 `./test.sh` 隔离环境或针对单文件运行；evals 体系则反过来拥抱真实模型的不确定性，用 `pi-harness.ts` 把真实 `AgentSession` 接入 `vitest-evals`，配合评委函数和对照实验衡量"这套提示词/工具/模型组合完成真实任务的效果好不好"。三层各司其职，共同构成了 pi 对"一个会调用真实大模型的复杂系统"应有的测试纪律。
