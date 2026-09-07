# RPC 模式与 JSON 事件流

> Pi 除了能在终端里交互式使用，还提供两种"把 Pi 当作黑盒子调用"的编程化模式——一次性的 JSON 事件流和长驻双向通信的 RPC 协议，它们是把 Pi 接入 IDE、自定义 UI 或自动化流水线的两条最基础的路。

## 学习目标

- 理解 JSON 事件流模式（`--mode json`）与 RPC 模式（`--mode rpc`）在生命周期和通信方向上的本质差异
- 掌握 RPC 模式基于 JSONL（每行一个 JSON 对象）的帧格式规则，以及为什么不能直接用 Node 的 `readline`
- 熟悉 RPC 模式的核心命令族：提示词发送、状态查询、模型/思维等级控制、bash 执行、会话管理
- 能读懂 RPC 事件流中 `agent_start` / `turn_end` / `message_update` 等生命周期事件的含义
- 会写一个最小的 Node.js/Python 子进程客户端，正确处理 JSONL 分帧与流式增量文本

## 两种模式解决什么问题

Pi 的核心可执行文件是 `pi` 这个 CLI，日常交互靠的是终端里的 TUI（Terminal UI）。但当你想把 Pi 的推理能力嵌入到别的程序里——比如一个 VS Code 插件、一个 Web 后端、一个批处理脚本——直接控制一个交互式终端程序是很别扭的。`packages/coding-agent/docs/rpc.md` 和 `packages/coding-agent/docs/json.md` 描述的两种模式，就是为了解决"如何以编程方式驱动 Pi"这个问题而设计的最基础手段：**子进程 + 标准输入输出上的 JSON 协议**。

它们的分工非常清晰：

| 维度 | JSON 事件流模式 | RPC 模式 |
|---|---|---|
| 启动方式 | `pi --mode json "你的提示词"` | `pi --mode rpc [options]` |
| 进程生命周期 | 一次性：处理完这一个提示词就退出 | 长驻：进程持续运行，等待下一条命令 |
| 通信方向 | 单向：只从 stdout 输出事件 | 双向：stdin 发命令，stdout 收响应和事件 |
| 典型场景 | shell 脚本里跑一次任务、CI 流水线、`jq` 管道处理 | IDE 插件、自定义聊天界面、需要多轮交互和会话控制的集成 |

一句话概括：**JSON 模式是"问一次答一次"，RPC 模式是"打开一个可以持续对话的会话"**。

## JSON 事件流模式

```bash
pi --mode json "List files"
```

这个模式把整个会话过程中产生的所有事件，逐行输出为 JSON 到 stdout。第一行永远是会话头：

```json
{"type":"session","version":3,"id":"uuid","timestamp":"...","cwd":"/path"}
```

紧接着是事件序列，例如：

```json
{"type":"agent_start"}
{"type":"turn_start"}
{"type":"message_start","message":{"role":"assistant","content":[],...}}
{"type":"message_update","assistantMessageEvent":{"type":"text_delta","contentIndex":0,"delta":"Hello"}}
{"type":"message_end","message":{...}}
{"type":"turn_end","message":{...},"toolResults":[]}
{"type":"agent_end","messages":[...]}
```

这里的事件类型来自 `packages/coding-agent/src/core/agent-session.ts` 定义的 `AgentSessionEvent`，再叠加 `packages/agent/src/types.ts` 里更底层的 `AgentEvent`。JSON 模式的输出类型叫 `JsonAgentSessionEvent`，与 `AgentSessionEvent` 唯一的区别是：`message_update` 事件被裁剪掉了`partial`（累积快照）字段，只保留增量 delta，目的是让事件流大小随内容线性增长而不是平方增长。

这意味着如果你想拼出完整的流式文本，需要自己用 `contentIndex` 和 `delta` 累加，而不能依赖某个事件里的"当前完整文本"字段；真正权威、完整的内容只会出现在 `message_end.message` 里。

一个常见的用法是配合 `jq` 只抽取你关心的事件：

```bash
pi --mode json "List files" 2>/dev/null | jq -c 'select(.type == "message_end")'
```

因为 JSON 模式是一次性的、单向输出，它不支持中途插话、切换模型这类交互操作——这些能力属于下面要讲的 RPC 模式。

## RPC 模式：命令与事件的双向协议

```bash
pi --mode rpc [options]
```

常用启动参数（来自 `docs/rpc.md`）：

- `--provider <name>`：设置 LLM 提供商（anthropic、openai、google 等）
- `--model <pattern>`：模型匹配模式，支持 `provider/id` 及可选的 `:<thinking>` 后缀
- `--name <name>` / `-n <name>`：启动时设置会话显示名
- `--no-session`：禁用会话持久化
- `--session-dir <path>`：自定义会话存储目录

### 协议总览

RPC 模式的通信模型是：

- **命令（Commands）**：客户端通过 stdin 发送的 JSON 对象，每行一个
- **响应（Responses）**：`type: "response"` 的 JSON 对象，表示某条命令成功或失败
- **事件（Events）**：Agent 运行过程中持续从 stdout 推送的 JSON 行

命令可以带一个可选的 `id` 字段用于请求/响应关联；如果带了 `id`，对应响应会原样带回同一个 `id`；`bash_execution_update` 事件也会携带发起该 `bash` 命令的 `id`。

### 帧格式：严格的 JSONL，只认 `\n`

这是接入 RPC 模式时最容易踩坑的细节。文档明确写了：

> RPC 模式使用严格的 JSONL 语义，只把 `\n`（LF）作为记录分隔符。

对客户端实现的具体要求：

- 只按 `\n` 切分记录
- 可以接受输入里出现 `\r\n`，做法是去掉行尾多余的 `\r`
- **不要用会把 Unicode 分隔符也当作换行的通用行读取器**——Node.js 的 `readline` 就属于这一类，因为它还会按 `U+2028`、`U+2029` 分行，而这两个字符在 JSON 字符串内部是合法字符，用 `readline` 解析会把一条完整的 JSON 消息错误地切成两半。

这也是为什么后面的示例代码要手写一个基于 `indexOf("\n")` 的简单缓冲区读取器，而不是偷懒调用 `readline.createInterface()`。

### 命令一览

RPC 命令按功能大致分为几组（完整定义在 `packages/coding-agent/src/modes/rpc/rpc-types.ts`）：

**提示词类**：`prompt`（发送用户提示，流式期间需指定 `streamingBehavior: "steer" | "followUp"`）、`steer`（排队插话，当前工具调用结束后交付）、`follow_up`（排队跟进，Agent 完全停下后才交付）、`abort`（中止当前操作）、`new_session`（开新会话）。

**状态类**：`get_state`（模型、思维等级、是否在流式、会话文件路径等）、`get_messages`（完整消息历史）。

**模型/思维等级**：`set_model`、`cycle_model`、`get_available_models`、`set_thinking_level`、`cycle_thinking_level`、`get_available_thinking_levels`。

**队列模式**：`set_steering_mode`（`all` 一次性交付全部插话 vs `one-at-a-time` 每轮交付一条）、`set_follow_up_mode`（语义类似）。

**压缩与重试**：`compact`（手动压缩上下文）、`set_auto_compaction`、`set_auto_retry`、`abort_retry`。

**Bash 执行**：`bash`（直接执行 shell 命令并把结果计入会话上下文——但只在**下一次** `prompt` 时才真正进入 LLM 的上下文，这一点容易被忽略）、`abort_bash`。

**会话管理**：`get_session_stats`、`export_html`、`switch_session`、`fork`、`clone`、`get_fork_messages`、`get_entries`（可用 `since` 游标增量拉取，支持跨客户端重启续传）、`get_tree`、`get_last_assistant_text`、`set_session_name`。

**命令发现**：`get_commands`，列出可以通过 `/name` 语法在 `prompt` 里调用的扩展命令、Prompt 模板和技能（skill）。

一个具体例子，发送提示词：

```json
{"id": "req-1", "type": "prompt", "message": "Hello, world!"}
```

响应只表示"已被接受/排队/处理"，不代表任务已完成：

```json
{"id": "req-1", "type": "response", "command": "prompt", "success": true}
```

真正的执行结果通过后续事件流（`agent_start` → `turn_start` → `message_*` → `turn_end` → `agent_end` → `agent_settled`）异步到达。这种"响应只确认受理、结果走事件流"的设计,和 Web 开发里"提交任务拿到 202 Accepted，再轮询或订阅结果"的模式是一个思路。

### 事件一览

事件类型远多于命令，覆盖 Agent 生命周期（`agent_start`/`agent_end`/`agent_settled`）、回合生命周期（`turn_start`/`turn_end`）、消息生命周期（`message_start`/`message_update`/`message_end`）、工具执行（`tool_execution_start`/`update`/`end`）、Bash 直接执行输出（`bash_execution_update`）、队列变化（`queue_update`）、压缩（`compaction_start`/`compaction_end`）、自动重试（`auto_retry_start`/`auto_retry_end`）等。

`message_update` 里携带的 `assistantMessageEvent` 有一套细粒度的增量类型：`text_start`/`text_delta`/`text_end`、`thinking_start`/`thinking_delta`/`thinking_end`、`toolcall_start`/`toolcall_delta`/`toolcall_end`。和 JSON 模式一样，客户端要自己用 `contentIndex` 拼接增量，`message_end.message` 才是权威的最终内容。

RPC 模式还有一套建立在事件之上的"扩展 UI 子协议"：扩展可以通过 `ctx.ui.select()`、`ctx.ui.confirm()` 等方法向 stdout 发 `extension_ui_request`，对话类方法（`select`/`confirm`/`input`/`editor`）会阻塞等待客户端从 stdin 回一个带相同 `id` 的 `extension_ui_response`；而"即发即弃"类方法（`notify`/`setStatus`/`setWidget`/`setTitle`/`set_editor_text`）不需要响应。这套子协议让运行在无终端环境里的扩展依然可以向宿主应用请求交互。

## 动手写一个客户端

### Python 最小示例

```python
import subprocess
import json

proc = subprocess.Popen(
    ["pi", "--mode", "rpc", "--no-session"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True
)

def send(cmd):
    proc.stdin.write(json.dumps(cmd) + "\n")
    proc.stdin.flush()

def read_events():
    for line in proc.stdout:
        yield json.loads(line)

send({"type": "prompt", "message": "Hello!"})

for event in read_events():
    if event.get("type") == "message_update":
        delta = event.get("assistantMessageEvent", {})
        if delta.get("type") == "text_delta":
            print(delta["delta"], end="", flush=True)
    if event.get("type") == "agent_end":
        print()
        break
```

这里之所以能用 Python 内置的按行迭代（`for line in proc.stdout`），是因为文本模式下 Python 的行迭代只按 `\n` 分割，天然满足 RPC 模式对分帧的要求。

### Node.js 示例：手写 JSONL 分帧读取器

Node.js 场景下则必须避开 `readline`，改用一个基于 `Buffer`/`StringDecoder` 手写的分帧函数：

```javascript
const { spawn } = require("child_process");
const { StringDecoder } = require("string_decoder");

const agent = spawn("pi", ["--mode", "rpc", "--no-session"]);

function attachJsonlReader(stream, onLine) {
    const decoder = new StringDecoder("utf8");
    let buffer = "";

    stream.on("data", (chunk) => {
        buffer += typeof chunk === "string" ? chunk : decoder.write(chunk);

        while (true) {
            const newlineIndex = buffer.indexOf("\n");
            if (newlineIndex === -1) break;

            let line = buffer.slice(0, newlineIndex);
            buffer = buffer.slice(newlineIndex + 1);
            if (line.endsWith("\r")) line = line.slice(0, -1);
            onLine(line);
        }
    });

    stream.on("end", () => {
        buffer += decoder.end();
        if (buffer.length > 0) {
            onLine(buffer.endsWith("\r") ? buffer.slice(0, -1) : buffer);
        }
    });
}

attachJsonlReader(agent.stdout, (line) => {
    const event = JSON.parse(line);
    if (event.type === "message_update") {
        const { assistantMessageEvent } = event;
        if (assistantMessageEvent.type === "text_delta") {
            process.stdout.write(assistantMessageEvent.delta);
        }
    }
});

agent.stdin.write(JSON.stringify({ type: "prompt", message: "Hello" }) + "\n");

process.on("SIGINT", () => {
    agent.stdin.write(JSON.stringify({ type: "abort" }) + "\n");
});
```

这段代码的关键点全部对应前面讲的协议规则：用 `indexOf("\n")` 手动切分而不是 `readline`；对每一行做 `\r` 兜底裁剪；流结束时把残留 buffer 当作最后一行处理，避免丢弃未以换行结尾的尾部数据。

`packages/coding-agent/test/rpc-example.ts` 提供了一个更完整的交互式示例，`packages/coding-agent/src/modes/rpc/rpc-client.ts` 则是官方给出的一个带类型的子进程客户端实现，`examples/rpc-extension-ui.ts` 配合 `examples/extensions/rpc-demo.ts` 演示了扩展 UI 子协议的完整处理流程，都是深入学习时值得逐行阅读的参考代码。

## 小结与思考题

JSON 事件流模式和 RPC 模式共享同一套底层事件词汇表，区别只在于"是否需要在进程存活期间反复发命令"。如果你的场景是"跑一次任务、拿到结果就退出"（脚本、CI），选 JSON 模式；如果需要多轮对话、中途插话、切换模型、管理多个会话分支，选 RPC 模式。两者都建立在最朴素的 stdin/stdout + JSONL 之上，不依赖任何网络端口，这也是它们能被几乎任何语言的子进程调用者集成的原因。

思考题：

1. 如果一个客户端在 `prompt` 命令的响应里收到了 `success: true`，但之后再也没有收到 `agent_end` 或任何后续事件，可能是什么原因？结合"响应只表示受理"的设计想一想应该如何设计超时与重连策略。
2. `bash` RPC 命令的执行结果要等到"下一次 `prompt`"才会真正进入 LLM 上下文，这个设计对客户端的调用顺序提出了什么隐含要求？如果客户端连续发送多个 `bash` 命令而不发 `prompt`，会发生什么？
3. 为什么 RPC 模式要严格限定只用 `\n` 分帧、并明确排除 Node `readline`？如果换成一个"以消息长度前缀 + 二进制载荷"的帧格式（类似下一篇要讲的 `packages/protocol` 方案），相比 JSONL 有哪些优劣？
