# Monorepo 结构与包职责地图

> pi 项目用一个 npm workspaces monorepo 管理十几个包；在深入任何一层原理之前，先搞清楚"谁依赖谁"，后面每一章讲某个包时才知道它在整个系统里的位置。

## 学习目标

- 理解 npm workspaces（工作区）在 pi 项目里是如何组织的。
- 记住 README 中列出的核心发布包及其一句话职责。
- 亲自核实（而不是猜测）各包 `package.json` 中的 `dependencies` 字段，画出真实的包依赖关系图。
- 区分"对外发布的包"和"仅用于开发/评测的私有包"。
- 知道构建脚本里的编译顺序为什么必须遵循依赖关系。

## npm workspaces 结构

pi 仓库根目录的 `package.json`（`pi-monorepo`，`private: true`）声明了如下 workspaces：

```json
"workspaces": [
  "packages/*",
  "packages/session-backends/*",
  "packages/coding-agent/examples/extensions/with-deps",
  "packages/coding-agent/examples/extensions/custom-provider-anthropic",
  "packages/coding-agent/examples/extensions/custom-provider-gitlab-duo",
  "packages/coding-agent/examples/extensions/sandbox",
  "packages/coding-agent/examples/extensions/gondolin"
]
```

可以看到三类工作区：

1. `packages/*`：核心发布包（`agent`、`ai`、`client`、`coding-agent`、`evals`、`protocol`、`server`、`telemetry`、`tui`），以及一个子目录容器 `packages/session-backends`。
2. `packages/session-backends/*`：会话持久化后端的独立子包，目前仓库里只有一个实现：`sqlite-node`。
3. `packages/coding-agent/examples/extensions/*` 中列出的几个扩展示例（`with-deps`、`custom-provider-anthropic`、`custom-provider-gitlab-duo`、`sandbox`、`gondolin`）：这些是教学/演示用的扩展工程，被显式加入 workspaces 是为了让它们能独立安装依赖、独立跑 `npm install`，但它们不是对外发布的产品包。

npm workspaces 的好处在这里体现得很直接：`npm install`（在根目录执行一次）就能把所有包的依赖装好，包之间通过 `node_modules` 的符号链接互相引用本地源码，而不用先 `npm publish` 再安装。

## 核心发布包一览

根目录 `README.md` 的 "All Packages" 表格列出了对外发布到 npm 的包：

| 包名 | 目录 | 一句话职责 |
|---|---|---|
| `@earendil-works/pi-telemetry` | `packages/telemetry` | 厂商中立的遥测契约、参考适配器、一致性测试和带类型的 schema |
| `@earendil-works/pi-ai` | `packages/ai` | 统一多 Provider 的 LLM API（OpenAI、Anthropic、Google 等） |
| `@earendil-works/pi-agent-core` | `packages/agent` | Agent 运行时，负责工具调用与状态管理 |
| `@earendil-works/pi-coding-agent` | `packages/coding-agent` | 交互式编码 Agent CLI |
| `@earendil-works/pi-tui` | `packages/tui` | 带差分渲染（differential rendering）的终端 UI 库 |

除了 README 表格里这五个"门面包"，仓库里还有几个同样会发布、但 README 正文没有单独展开介绍的包，需要打开各自的 `package.json` 才能确认职责：

| 包名 | 目录 | `package.json` 中的 description |
|---|---|---|
| `@earendil-works/pi-protocol` | `packages/protocol` | Transport-neutral CBOR protocol for remote pi sessions（面向远程会话的、与传输层无关的 CBOR 协议） |
| `@earendil-works/pi-client` | `packages/client` | Transport-neutral client for remote pi sessions over framed CBOR bytes（基于分帧 CBOR 字节流的远程会话客户端） |
| `@earendil-works/pi-server` | `packages/server` | experimental server package for pi（pi 的实验性服务端包） |
| `@earendil-works/pi-session-backend-sqlite-node` | `packages/session-backends/sqlite-node` | Node sqlite session backend for `@earendil-works/pi-agent-core` sessions（供 agent-core 会话使用的 Node SQLite 存储后端） |

还有一个不对外发布的私有包：

| 包名 | 目录 | 说明 |
|---|---|---|
| `@earendil-works/pi-evals`（`private: true`） | `packages/evals` | 评测/回归测试脚手架，通过 `devDependencies` 依赖 `pi-ai` 和 `pi-coding-agent` 来跑真实任务评测，不进入发布流程 |

## 依赖关系：以 package.json 为准，不臆测

下面的依赖方向全部来自实际读取各包 `package.json` 的 `dependencies` 字段（`devDependencies` 不计入运行时依赖关系）：

- **`pi-telemetry`**：无内部依赖，是最底层的叶子包。
- **`pi-tui`**：无内部依赖，只依赖 `get-east-asian-width`、`marked` 等第三方包，也是叶子包。
- **`pi-protocol`**：无内部依赖（只用了 `typebox`），同样是叶子包。
- **`pi-ai`**：依赖 `@earendil-works/pi-telemetry`。
- **`pi-agent-core`**（`packages/agent`）：依赖 `@earendil-works/pi-ai` 和 `@earendil-works/pi-telemetry`。
- **`pi-client`**：依赖 `@earendil-works/pi-protocol`。
- **`pi-server`**：依赖 `@earendil-works/pi-ai` 和 `@earendil-works/pi-protocol`。
- **`pi-session-backend-sqlite-node`**：依赖 `@earendil-works/pi-ai` 和 `@earendil-works/pi-agent-core`。
- **`pi-coding-agent`**：依赖 `@earendil-works/pi-agent-core`、`@earendil-works/pi-ai`、`@earendil-works/pi-client`、`@earendil-works/pi-protocol`、`@earendil-works/pi-tui`。
- **`pi-evals`**（私有，不发布）：以 `devDependencies` 形式依赖 `@earendil-works/pi-ai` 和 `@earendil-works/pi-coding-agent`。

有一个容易凭直觉猜错的地方：`pi-coding-agent` 的 `dependencies` 里**没有** `@earendil-works/pi-server`。也就是说 CLI 本身走的是 `pi-client` + `pi-protocol` 这条"协议客户端"路径，而 `pi-server` 是一个独立的、标记为 "experimental" 的服务端包，二者在依赖图上是并列关系，不是 `coding-agent → server` 的直接依赖。

## 依赖关系图（按层次展示）

把上面的依赖关系按"谁不依赖谁"分层，可以画成下面这张图（箭头表示"被谁依赖"，从下往上看）：

```
第 3 层（组装层）
        pi-coding-agent
       /   |    |    |   \
      /    |    |    |    \
第 2 层：
  pi-agent-core   pi-client   pi-server   pi-tui(叶子)
     |    \           |          |  \
     |     \          |          |   \
第 1 层：
   pi-ai   pi-session-backend-sqlite-node   pi-protocol(叶子)
     |            |     \
     |            |      \
第 0 层（叶子包，无内部依赖）：
  pi-telemetry ───┘      pi-agent-core(见上)

私有评测包（不参与发布，仅 devDependencies）：
  pi-evals ──depends on──> pi-ai, pi-coding-agent
```

用文字再复述一遍这张图的关键路径：

- `pi-telemetry`、`pi-tui`、`pi-protocol` 是三个没有任何内部依赖的地基包。
- `pi-ai` 建在 `pi-telemetry` 之上；`pi-client` 建在 `pi-protocol` 之上。
- `pi-agent-core` 建在 `pi-ai`（因而间接依赖 `pi-telemetry`）之上；`pi-server` 建在 `pi-ai` + `pi-protocol` 之上。
- `pi-session-backend-sqlite-node` 建在 `pi-ai` + `pi-agent-core` 之上，是一个可插拔的会话存储实现。
- 最顶层的 `pi-coding-agent` 把 `pi-agent-core`（运行时）、`pi-ai`（模型层）、`pi-tui`（终端渲染）、`pi-client` + `pi-protocol`（远程会话协议客户端）组装成最终的 CLI 产品。

## 根目录构建脚本印证了这个依赖顺序

根目录 `package.json` 的 `build` 脚本是一连串 `cd` 命令：

```
tui → telemetry → ai → agent → session-backends/sqlite-node → protocol → client → server → coding-agent
```

这个顺序不是随意排列的，而是依赖关系的拓扑排序（topological order）：一个包必须等它依赖的包先构建出 `dist` 产物，自己才能编译通过。比如 `agent` 排在 `ai` 之后，是因为 `agent-core` 依赖 `pi-ai`；`coding-agent` 排在最后，是因为它依赖前面几乎所有包。`build:offline` 脚本结构完全一致，唯一区别是 `ai` 那一步换成了 `npm run build:offline`（使用已有的模型数据快照而不联网刷新，具体见下一篇构建流程）。

## 动手练习

1. 在本地克隆的 `/tmp/pi-repo`（或你自己的 clone）中，对每个包运行一次：
   ```bash
   cat packages/<pkg>/package.json | grep -A 10 '"dependencies"'
   ```
   自己重新核对一遍上面列出的依赖关系表，确认没有遗漏或猜错的地方。
2. 用 `grep -rl "@earendil-works/pi-" packages/*/package.json` 找出所有内部依赖声明，尝试脱离本文档、只凭 grep 结果重新画一遍依赖关系图。
3. 思考一下：如果要新增一个 `packages/telemetry-otel`（把遥测事件转发到 OpenTelemetry），它应该放在依赖图的哪一层？哪些包可能需要在 `dependencies` 里加上它？

## 小结

pi 是一个按职责边界拆分得比较细的 npm workspaces monorepo：三个无内部依赖的地基包（`telemetry`、`tui`、`protocol`），若干个建立在地基包之上的中间层（`ai`、`client`、`agent-core`、`server`、`session-backend-sqlite-node`），最终由 `coding-agent` 把其中一部分（`agent-core`、`ai`、`tui`、`client`、`protocol`）组装成对外的 CLI 产品；`server` 虽然也依赖 `ai` 和 `protocol`，但目前和 `coding-agent` 是并列关系而非被其依赖；`evals` 则是一个不发布的私有包，专门用来跑真实任务评测。记住这张依赖图，后面每一章讲某个包内部实现时，就能知道它的输入来自哪一层、输出会被谁消费。
