# Protocol / Server / Client 架构

> 前两篇讲的 RPC 模式和 SDK，解决的是"单个客户端驱动单个 Pi 进程"的问题；`packages/protocol`、`packages/server`、`packages/client` 这三个包合起来，解决的是一个更进一步、也更复杂的问题——一个服务端如何同时管理多个会话、支持多个客户端并发连接和断线重连，这是一套独立于 `--mode rpc` 的实验性二进制协议栈。

## 学习目标

- 分清 `packages/coding-agent` 的 JSONL RPC 协议与 `packages/protocol`/`server`/`client` 这套 CBOR 二进制协议是两套不同的东西，理解各自的定位
- 理解三个包的分层关系：protocol 定义线格式，server 实现会话管理与连接监听，client 实现连接状态机与请求/响应关联
- 读懂 `framing.ts` 的长度前缀分帧算法和 `codec.ts` 的编解码校验流程
- 理解 `PiServer` 的握手、会话获取（acquire）/释放（dispose）、快照广播机制
- 理解 `PiClient` 的会话租约（session lease）模型和 `unix.ts` 揭示的 Unix Domain Socket 传输方式

## 先说清楚：这是另一套协议

容易混淆的一点是：本文要讲的 `@earendil-works/pi-protocol`、`@earendil-works/pi-server`、`@earendil-works/pi-client` 三个包，和第一篇讲的 `pi --mode rpc`（基于 stdin/stdout 的 JSONL 协议）**不是同一套东西**，两者互不依赖。`pi --mode rpc` 是 `coding-agent` 内部 `runRpcMode()` 直接读写标准输入输出的文本协议，服务于"一个子进程对一个客户端"的场景；而 `packages/protocol` 定义的是一套**二进制（CBOR）、支持多会话、支持多客户端同时连接**的线协议，`packages/server` 和 `packages/client` 分别是这套协议的服务端和客户端参考实现。两者的 README 都明确标注为 **Experimental（实验性）**，API 和行为都可能变化。

如果说 RPC 模式是"一对一的管道"，那么 protocol/server/client 这套栈的目标是"一个常驻服务进程，多个客户端可以随时连上来，创建会话、附加到已有会话、断开重连、共享同一个会话的多个观察者"——这是构建一个真正意义上的"Pi 后端服务"所需要的基础设施。

## 分层关系总览

三个包严格分层，依赖方向单向：

```
packages/protocol   —— 线格式（wire format）：schema 定义、CBOR 编解码、字节分帧
        ↑                依赖
packages/server      —— 服务端：接受连接、握手、会话生命周期管理、快照广播
        ↑                依赖
packages/client      —— 客户端：连接状态机、请求/响应关联、会话租约封装
```

`packages/protocol` 是最底层、完全运行时无关的包（"has no Node-specific imports"是 client README 里的原话），它只关心"字节怎么变成消息、消息长什么样"，不涉及任何网络或进程细节。`packages/server` 在其之上加了"如何管理会话、如何响应命令"的业务逻辑，但同样不绑定具体传输方式——它通过 `PiServerListener` 接口把"建立连接"这件事完全委托给调用方（可以是 Unix socket、也可以是 WebSocket）。`packages/client` 则通过 `ByteTransportFactory` 接口做了同样的解耦，唯一内置的传输实现是通过独立子路径导出的 Unix Domain Socket。

## protocol 包：线格式与编解码

### 线格式：4 字节长度前缀 + CBOR

`packages/protocol/README.md` 给出了协议版本 1 的完整线格式定义：

1. 一个 4 字节的无符号大端整数，表示后续负载长度
2. 一个 definite-length（确定长度）的 CBOR 项，包含消息本体

这个格式在 `packages/protocol/src/framing.ts` 里实现。`encodeFrame()` 负责把长度写进前 4 个字节：

```typescript
export function encodeFrame(payload: Uint8Array): Uint8Array {
	const frame = new Uint8Array(FRAME_HEADER_LENGTH + payload.byteLength);
	const length = payload.byteLength;
	frame[0] = length >>> 24;
	frame[1] = length >>> 16;
	frame[2] = length >>> 8;
	frame[3] = length;
	frame.set(payload, FRAME_HEADER_LENGTH);
	return frame;
}
```

真正的复杂度在解码端。`FrameDecoder` 类要处理"字节可能被任意拆分或合并到达"这个现实——一次 `push(chunk)` 调用收到的字节，既可能不够一个完整的长度头，也可能横跨好几个完整帧。它内部维护一个状态机：先攒够 4 字节头部解析出 `expectedPayloadLength`，再把后续字节按 64KB 为单位的块（`PAYLOAD_BLOCK_SIZE`）攒进 `payloadBlocks` 数组，直到攒够 `expectedPayloadLength`，才拼成一帧输出、并重置状态开始下一帧。

这种"按块累积、避免过早整体拷贝"的写法，是为了在处理大负载（比如带图片附件的消息）时减少内存拷贝次数。解码器还会在解析出声明长度的第一时间就用 `maxFrameLength`（默认 `DEFAULT_MAX_FRAME_LENGTH = 16 * 1024 * 1024`，即 16 MiB）做校验，超限直接 `fail()` 并把解码器状态标记为 `"failed"`，防止恶意或损坏的长度头导致无限攒取内存。`end()` 方法用于流关闭时检测"半截帧"（还没收完整就断流），这类截断会被当成协议错误。

### codec.ts：带 schema 校验的编解码

`framing.ts` 只管字节层的分帧，真正把"字节"和"类型安全的协议消息"关联起来的是 `packages/protocol/src/codec.ts`。它在编码时先用 typebox 的 `Check()` 对消息做 schema 校验（`parseClientMessage()`/`parseServerMessage()`），校验通过才编码成 CBOR 再套上帧头：

```typescript
function encodeProtocolMessage<T>(value: T, parse: (candidate: unknown) => T, kind: string, options?: FrameDecoderOptions): Uint8Array {
	const validated = parse(value);
	const frame = encodeFrame(encodeCbor(validated, { maxByteLength: maxFrameLength }));
	assertCompleteFrame(frame, { maxFrameLength });
	return frame;
}
```

解码方向则是 `ClientMessageDecoder` / `ServerMessageDecoder`：先用 `FrameDecoder` 切出一帧帧字节，再 `decodeCbor()` 还原成 JS 值，最后同样过一遍 schema 校验。任何一步失败都会抛 `ProtocolValidationError`，并且解码器会把自己标记为失败状态，此后拒绝继续处理——这是刻意设计成"一旦出现协议违规就不再信任这条连接后续的字节"，避免在已知状态错乱的流上继续解析产生更隐蔽的问题。

值得一提的是编码前还有一个 `isProtocolValue()` 检查（在 `codec.ts` 顶部），它会递归确认一个值只包含 `null`/布尔/数字/字符串/数组/纯对象，拒绝原型链被污染的对象或循环引用——这是在 CBOR 编码之前的一道"协议值合法性"前置防线。

### schemas.ts：协议词汇表

`packages/protocol/src/schemas.ts` 用 typebox 定义了整套协议的类型系统，核心概念包括：

- **`Command`**（客户端可发出的命令）：`list`/`create`/`attach`/`detach`/`prompt`/`steer`/`abort`/`set_model`/`set_thinking`，注意这套命令集合比 RPC 模式的命令少得多——因为很多 RPC 模式里的能力（压缩、bash 执行、fork/clone 等）在这个协议 v1 里还没有对应命令
- **`SessionSnapshot`**：一个会话的运行时快照，包含 `phase`（`idle`/`turn`/`compaction`/`branch_summary`/`retry`）、`model`、`thinkingLevel`、`attached`、`locked`、`revision`（版本号，用于客户端判断快照是否过期）、完整的 `transcript`（对话记录数组）
- **`SessionMetadata`**：比 `SessionSnapshot` 更"轻"的持久化元数据，只需要 `id` 和 `createdAt` 是必填，其余（`updatedAt`/`parentSessionId`/`sessionName`/`cwd`）看后端存储能力决定是否提供——这是为了让"列出所有会话"这种操作不需要真的把每个会话的运行时状态都拉起来
- **`ServerEvent`**：`server_snapshot`（服务端全局快照）、`session_snapshot`（单会话快照）、`session_progress`（增量进度，只是 UI 提示，不能被当作权威状态归约）、`session_removed`
- **`ClientMessage`** / **`ServerMessage`**：分别是 `hello`（握手）+ `request`（带 `id` 的命令请求信封），以及 `hello`/`hello_error`（握手结果）+ `response`（带 `ok: true/false` 的响应信封）+ `event`（事件信封）

`ProtocolErrorCode` 是一个封闭的错误码集合：`version`/`busy`/`session_locked`/`not_found`/`invalid_request`/`not_implemented`/`internal_error`，所有跨协议边界的错误都必须落到这几个码之一，这让客户端可以做结构化的错误处理而不必解析错误消息字符串。

## server 包：会话生命周期与连接管理

### PiServer：握手与消息分发

`packages/server/src/server.ts` 里的 `PiServer` 类是整个服务端的入口。它的核心状态机围绕 `ConnectionState.stage` 展开：`awaitingHello` → `handshaking` → `ready`（之后是 `closing`/`closed`）。新连接建立后必须先收到一个 `hello` 消息（否则直接 `failProtocol`），版本校验通过后服务端回一个包含 `ServerSnapshot` 的 `hello` 响应，连接才进入 `ready` 状态可以处理业务命令。握手还设置了超时（默认 `DEFAULT_HANDSHAKE_TIMEOUT_MS = 5000` 毫秒），超时未完成握手的连接会被强制断开。

```typescript
private async finishHandshake(state: ConnectionState, hello: ClientHello): Promise<void> {
    if (!isSupportedProtocolVersion(hello.version)) {
        await this.failProtocol(state, { code: "version", message: `Unsupported protocol version ${hello.version}; expected ${PROTOCOL_VERSION}` });
        return;
    }
    const snapshot = await this.snapshots.get();
    const sent = await this.sendMessage(state, { type: "hello", version: PROTOCOL_VERSION, connectionId: state.id, snapshot });
    // 握手成功后进入 ready 状态
}
```

`PiServer` 本身不关心连接是怎么建立的——它通过构造函数接收一个 `PiServerListener[]` 数组，每个 listener 负责"完成传输层特定的认证授权，然后把已建立的连接交给 `accept()`"。这个解耦是刻意的：README 里举例说 WebSocket listener 可以在 HTTP upgrade 阶段校验凭证，Unix listener 则依赖 socket 文件系统权限，`PiServer` 自己完全不用关心这些差异。

### LiveSessionManager：会话获取与释放

`packages/server/src/sessions.ts` 的 `LiveSessionManager` 是最复杂的一块。它维护一个 `liveSessions: Map<string, LiveSession>`，每个 `LiveSession` 包含运行时实例（`PiSessionRuntime`）、当前挂载的连接集合（`connections`）、操作计数（`operationCount`）等。几个关键设计：

- **acquire 去重**：`acquire(id, acquireRuntime)` 用 `openingSessions: Map<string, Promise<LiveSession>>` 防止同一个 `id` 被并发创建两次——如果正在创建，后来者直接等同一个 Promise
- **命令执行**：`executeCommand()` 是一个大 `switch`，对 `prompt`/`steer`/`abort`/`set_model`/`set_thinking` 这类命令，统一走 `runOperation()`，它会在操作前后维护 `operationCount`，并在结束后调用 `broadcastSnapshot()` 把最新快照推给所有挂载在这个会话上的连接
- **自动释放（dispose）**：`maybeDispose()` 判断一个会话是否可以被释放——条件是没有连接挂载、没有进行中的操作、且运行时处于 `idle` 阶段（或已经处于终态）。这意味着一个会话在最后一个客户端 detach 之后，如果确实空闲，服务端会自动把它从内存中释放掉，而不需要显式的"关闭会话"命令
- **错误终止**：如果运行时通过 `subscribe()` 报出一个 `{ type: "error" }` 事件，`terminate()` 会把该会话标记为 `terminal`，断开所有挂载的连接，然后释放资源——这是运行时崩溃时的兜底清理路径

`PiServerService` 接口（定义在 `packages/server/src/types.ts`）是应用方需要实现的服务边界：`listSessions()`、`listModels()`、`createSession()`、`openSession()`。`PiServer` 本身不提供存储，具体怎么持久化会话、怎么真正驱动 Agent 运行，全部由这个接口的实现方决定——这也是为什么 README 说"这个包不提供独立的 CLI 或 coding-agent 服务，应用方需要自己提供 `PiServerService` 实现"。

### ServerSnapshotPublisher：版本化的全局快照广播

`packages/server/src/snapshots.ts` 负责维护一个单调递增的 `revision` 号，每次 `broadcast()` 都会拉取最新的会话列表和模型列表，打包成一个新的 `ServerSnapshot` 推给所有处于 `ready` 状态的连接。用一个 `broadcastQueue: Promise<void>` 串行化广播调用，避免并发广播导致 revision 乱序。客户端（下面会讲到）依据 `revision` 决定是否接受一个快照——`revision` 更旧的快照会被直接丢弃，这就是一个简单但有效的"最终一致性 + 乱序容忍"机制。

### errors.ts：受控的错误跨界

`packages/server/src/errors.ts` 定义了 `PiServerError` 及其子类（`SessionBusyError`/`SessionLockedError`/`SessionNotFoundError`/`NotImplementedError`），它们的 `code` 字段被限定为协议里 `ProtocolErrorCode` 的一个子集（`busy`/`session_locked`/`not_found`/`invalid_request`/`not_implemented`）——这些错误可以安全地跨越协议边界发给客户端。而 `InternalServerError` 则专门包一层"不安全"的原始异常，`toProtocolError()` 遇到它时只会上报到 `onError` 回调、绝不把内部细节序列化给客户端，统一返回一个通用的 `internal_error`。这种区分（"可以告诉客户端的错误" vs "只能记日志、绝不外传的错误"）是服务端安全设计里的一个基本模式。

## client 包：连接状态机与会话租约

### Connection：一个显式的状态机

`packages/client/src/connection.ts` 的 `Connection` 类把连接生命周期显式建模为 `"disconnected" | "connecting" | "connected"` 三态。`connect()` 先创建一个 `ServerMessageDecoder`，通过 `transportFactory` 拿到一个 `ByteTransport`，发送 `hello`，等服务端回 `hello` 或 `hello_error`。任何阶段的失败都统一走 `#failAndClose()`，保证连接状态和底层 transport 的生命周期严格同步——不会出现"逻辑上已断开但 socket 还开着"或反过来的情况。

### PiClient：请求/响应关联与会话租约

`packages/client/src/client.ts` 的 `PiClient` 在 `Connection` 之上加了两层东西：

**请求/响应关联**：`#request()` 给每个命令分配一个自增 `id`（`request-1`、`request-2`……），存进 `#pendingRequests` 等待响应；`#handleMessage()` 收到 `response` 消息后按 `id` 找回对应的 `resolve`/`reject`。断线时 `#rejectPendingRequests()` 会统一拒绝所有挂起请求，避免调用方永远等不到结果。

**会话租约（Session Lease）**：这是这个包里最有意思的设计。`acquireSession()`/`createSession()` 返回的不是一个原始会话引用，而是一个 `PiSessionHandle`（`SessionHandle` 类的实例），本质上是一张"租约"：

- `createSession()` 返回**独占（exclusive）**租约——同一个会话同时只能有一个独占租约，`#reserveSessionLease()` 里如果 `mode === "exclusive"` 且已有租约存在，直接抛 `PiSessionOwnershipError`
- `attachSession()` 是 `acquireSession(id, { mode: "shared" })` 的简写，**共享（shared）**租约允许多个消费者同时挂在同一个会话上，但共享租约存在时不能再申请独占租约，反之亦然
- 租约的 `dispose()`/`detach()` 只释放"这一张"租约；只有当某个会话的最后一张本地租约释放时，客户端才会真正向服务端发 `detach` 命令
- 服务端主动移除会话（`session_removed` 事件）或连接断开，会让该会话所有本地租约立刻失效（`state: "invalidated"`），此后对失效租约的操作会抛 `PiSessionDetachedError`，重复 `dispose()` 则是安全的空操作

`SessionHandle`（`packages/client/src/session-handle.ts`）把 `prompt`/`steer`/`abort`/`setModel`/`setThinking` 这几个会话内命令包成了方便调用的方法，每个方法底层都是往 `#callbacks.request()` 转发一条带 `sessionId` 的 `Command`。

### state.ts：快照缓存与版本号防乱序

`packages/client/src/state.ts` 的 `ClientState` 缓存了服务端快照（`ServerSnapshot`）和每个会话的快照（`SessionSnapshot`），并且用和服务端一致的思路——比较 `revision`——丢弃过期快照：

```typescript
applyServerSnapshot(snapshot: ServerSnapshot): void {
    if (this.#snapshot && snapshot.revision < this.#snapshot.revision) return;
    this.#snapshot = snapshot;
    this.#notify(this.#snapshotListeners, snapshot);
}
```

这保证了即使网络层出现消息乱序（例如两次广播的帧因为传输层缓冲而颠倒到达顺序），客户端状态也不会被旧快照覆盖新快照。

## unix.ts：Unix Domain Socket 传输的落地实现

前面提到 `packages/protocol` 和 `packages/client` 核心逻辑都是传输无关的，真正的传输实现通过独立子路径 `@earendil-works/pi-client/unix` 导出，对应 `packages/client/src/unix.ts`。`createUnixTransportFactory({ path })` 每次连接尝试都会创建一个全新的 `net.Socket` 并 `connect`，几个值得注意的实现细节：

- **路径长度校验**：Unix Domain Socket 的路径长度有内核限制，代码按平台区分（Linux 107 字节、其他平台 103 字节），超限直接在构造期抛错，而不是等到连接失败才发现
- **背压（backpressure）处理**：`UnixByteTransport.send()` 维护一个 `#pendingBytes` 计数器和 `maxPendingBytes` 上限（默认是协议帧长度上限的 4 倍），超过上限直接拒绝写入，防止客户端把未确认的待发送数据无限堆积在内存里
- **写入串行化**：`#writeTail` 是一条 Promise 链，保证多次 `send()` 调用严格按调用顺序落到 socket 上，即使某次写入需要等待 `drain` 事件也不会打乱顺序
- **平台限制**：构造期直接检测 `process.platform === "win32"` 并抛错，因为 Windows 不支持 Unix Domain Socket

Windows 用户如果想复用 `PiClient`，需要自己实现一个符合 `ByteTransportFactory` 接口的传输（例如基于命名管道或 TCP），这也是为什么 `unix.ts` 要作为独立子路径导出而不是打进包的默认入口——保持核心包在浏览器、Deno、Workers 等非 Node 运行时里依然可用。

## 端到端流程小结

把三层串起来看一次完整的交互：客户端通过某个 `ByteTransportFactory` 建立连接 → 发送 `hello` → 服务端校验版本、回一个带 `ServerSnapshot` 的 `hello` → 客户端调用 `createSession()`，底层发出 `{ command: "create" }` 请求 → 服务端调用 `PiServerService.createSession()` 拿到一个 `PiSessionRuntime`，`LiveSessionManager` 把它注册为 `LiveSession` 并 attach 当前连接 → 服务端把创建结果和后续的 `session_snapshot`/`session_progress` 事件持续推给客户端 → 客户端 `ClientState` 用 `revision` 去重合并，最终通过 `SessionHandle.subscribe()`/`onEvent()` 把结果交给上层应用 → 应用调用完毕后 `dispose()` 租约，最后一个租约释放时客户端发 `detach`，服务端在会话空闲后自动 `maybeDispose()` 释放运行时资源。

## 小结与思考题

`packages/protocol`/`server`/`client` 这套栈和第一篇的 JSONL RPC 协议解决的是不同量级的问题：前者是"多会话、多客户端、支持重连"的服务化基础设施，后者是"单进程单客户端"的轻量集成方案。三个包的分层（协议格式 → 服务端会话管理 → 客户端连接与租约）体现了一个清晰的原则：**把"字节怎么变成消息"、"消息怎么驱动业务"、"业务结果怎么安全地交回调用方"这三件事严格分开**，每一层都可以独立测试、独立替换传输实现。这也是为什么两个包的 README 都反复强调"传输是外部注入的""不提供默认的持久化实现"——它们提供的是骨架，不是完整产品。

思考题：

1. `PiServerError` 和 `InternalServerError` 的区分背后是"哪些错误可以告诉客户端、哪些绝不能"的安全边界。如果你要新增一个"数据库连接失败"的错误场景，应该抛出这两者中的哪一个？为什么？
2. 会话租约区分 `exclusive` 和 `shared` 两种模式。设想一个场景：一个 Web 应用既有一个"控制面板"需要独占控制会话（可以改模型、可以中止），又有多个"只读观察者"标签页只想看对话内容——应该分别用哪种租约模式？如果观察者也不小心申请了 `exclusive`，会发生什么？
3. `FrameDecoder` 在检测到损坏帧后会把自己标记为 `"failed"` 并拒绝继续处理，`ClientState` 用 `revision` 比较丢弃过期快照。这两种"拒绝处理坏数据/旧数据"的设计分别防御的是什么风险？如果协议层不做这层防御，业务层可能会遇到什么问题？
