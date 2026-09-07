# Pairing 与设备信任模型

> 上一篇留下了一个没展开的前提:任何客户端——不管是操作者的 CLI,还是一台 iOS 节点——凭什么能连上 Gateway 并被信任?`docs/concepts/architecture.md` 给出的答案很直接:"All WS clients (operators + nodes) include a **device identity** on `connect`. New device IDs require pairing approval; the Gateway issues a **device token** for subsequent connects." 这一篇要拆开这套设备信任模型:`connect.challenge` 的签名验证具体验证了什么、本地回环连接为什么可以自动批准而 Tailnet/LAN 连接不行、以及这套设计到底在防范什么威胁——注意,它防的不是"陌生人给你发消息",那是 channel 层面 DM 策略的职责;它防的是"未经批准的设备冒充已配对设备连接控制平面"。

## 学习目标

- 理解设备身份(device identity)是 `connect` 握手的一等公民,而不是一个可选的元数据字段。
- 读懂 `connect.challenge` 的 nonce 签名机制:`signedAt` 时间窗口、nonce 一次性校验、以及 `v2`/`v3` 两种签名负载版本的具体区别(`v3` 额外绑定 `platform`/`deviceFamily`)。
- 区分 Gateway 里两层不同的"配对":gates 住 `connect` 握手本身的**设备配对**,和 gates 住已连接节点能声明哪些能力的**节点能力批准**(`node.pair.*`)。
- 理解本地回环连接为什么可以被自动批准(包括通过 SSH 隧道转发的"远程但本地终结"的连接),以及 SSH-verified 自动批准为什么依赖密钥匹配而不是网络可达性。
- 明确这套设备信任模型要防的具体威胁:未经批准的设备冒充已配对设备连接控制平面,而不是防止陌生人触发消息处理。

## 背景与设计动机

`docs/gateway/security/index.md` 给这套系统的信任模型画了一条清晰的边界:

> **One trust boundary per gateway.** ... OpenClaw is not a hostile multi-tenant security boundary for mutually adversarial users sharing one agent or gateway.

这句话很关键:OpenClaw 假设一个 Gateway 背后是一个操作者,或者一组彼此信任的团队成员,而不是互相敌对的多租户。在这个前提下,设备配对要解决的问题就不是"识别谁是坏人",而是**"确认连上来的这台设备,确实是之前被批准过的那台设备"**——这是一个身份持续性(identity continuity)问题,不是身份验真(identity verification against a malicious sender)问题。

如果没有这层设备信任,任何知道 Gateway 地址、能构造出合法 WS 帧的进程,只要再拿到一个共享密钥(token/password),就能以"操作者"的身份连上控制平面,读取所有会话、下发 `agent` 请求、控制节点设备。共享密钥能证明"这个请求来自持有密钥的人",但证明不了"这个连接和上次批准的那个连接是同一台设备"——密钥可能被复制、被窃取、被多台机器共享。设备身份把"谁在连"这件事从"知道一个密钥"升级为"持有一份只有这台设备才有的私钥,并且这份私钥此前已经被人工批准过"。

## 核心机制详解

### 设备身份是 connect 的一等公民

`docs/gateway/protocol.md` 里的 `connect` 请求示例携带了一个完整的 `device` 对象:

```json
{
  "method": "connect",
  "params": {
    "role": "operator",
    "scopes": ["operator.read", "operator.write"],
    "auth": { "token": "…" },
    "device": {
      "id": "device_fingerprint",
      "publicKey": "…",
      "signature": "…",
      "signedAt": 1737264000000,
      "nonce": "…"
    }
  }
}
```

这里有两层认证同时存在:`auth.token`(共享密钥,证明"你知道 Gateway 的密码")和 `device`(设备签名,证明"你是这把私钥的持有者,并且这把私钥此前被批准过")。`architecture.md` 说得很直接:

> All connects must sign the `connect.challenge` nonce. ... **Non-local** connects still require explicit approval. Gateway auth (`gateway.auth.*`) still applies to **all** connections, local or remote.

也就是说,共享密钥认证和设备配对是两条独立的门槛,共享密钥过了不代表设备配对也自动过——除非命中了下文要讲的"本地信任"例外。

### connect.challenge:nonce 签名与两代负载格式

握手流程里,Gateway 先于客户端的 `connect` 请求推送一条挑战事件:

```json
{ "type": "event", "event": "connect.challenge", "payload": { "nonce": "…", "ts": 1737264000000 } }
```

客户端要用这个 `nonce` 和 `ts` 构造签名,再放进 `connect.params.device` 里回传。我们在源码 `src/gateway/server/ws-connection/connect-device-proof.ts` 里核实了服务端具体验证了哪几件事:

```typescript
// src/gateway/server/ws-connection/connect-device-proof.ts
const DEVICE_SIGNATURE_SKEW_MS = 2 * 60 * 1000;
// ...
const derivedId = deriveDeviceIdFromPublicKey(device.publicKey);
if (!derivedId || derivedId !== device.id) {
  rejectDeviceAuthInvalid("device-id-mismatch", "device identity mismatch");
}
const signedAt = device.signedAt;
if (typeof signedAt !== "number" || Math.abs(Date.now() - signedAt) > DEVICE_SIGNATURE_SKEW_MS) {
  rejectDeviceAuthInvalid("device-signature-stale", "device signature expired");
}
const providedNonce = typeof device.nonce === "string" ? device.nonce.trim() : "";
if (providedNonce !== context.handler.connectNonce) {
  rejectDeviceAuthInvalid("device-nonce-mismatch", "device nonce mismatch");
}
```

三条检查分别对应三种伪造/重放手法:

1. **设备 ID 必须能从公钥推导出来**——防止一个连接自称是"某个已配对的 `deviceId`",却用另一把公钥签名。
2. **签名时间戳必须在 2 分钟窗口内**(`DEVICE_SIGNATURE_SKEW_MS`)——防止把一次合法的历史签名录下来,过很久之后重放。
3. **nonce 必须和这条连接自己收到的挑战 nonce 完全一致**——防止把 A 连接收到的挑战签名,搬到 B 连接上使用(跨连接重放)。

真正的签名校验分两代负载格式,`src/gateway/server/ws-connection/handshake-auth-helpers.ts` 里的 `resolveDeviceSignaturePayloadVersion` 会**优先尝试 v3,失败再回退到 v2**:

```typescript
// src/gateway/server/ws-connection/handshake-auth-helpers.ts
const basePayload = {
  deviceId: params.device.id, clientId: params.connectParams.client.id,
  clientMode: params.connectParams.client.mode, role: params.role,
  scopes: params.scopes, signedAtMs: params.signedAtMs,
  token: signatureToken, nonce: params.nonce,
};
const payloadV3 = buildDeviceAuthPayloadV3({
  ...basePayload,
  platform: params.connectParams.client.platform,
  deviceFamily: params.connectParams.client.deviceFamily,
});
if (verifyDeviceSignature(params.device.publicKey, payloadV3, params.device.signature)) return "v3";

const payloadV2 = buildDeviceAuthPayload(basePayload);
if (verifyDeviceSignature(params.device.publicKey, payloadV2, params.device.signature)) return "v2";
return null;
```

这和 `architecture.md` 里的描述完全对得上:

> Signature payload `v3` also binds `platform` and `deviceFamily`; the gateway pins paired metadata on reconnect and requires repair pairing for metadata changes.

`v2` 只对 `deviceId`/`clientId`/`clientMode`/`role`/`scopes`/`signedAtMs`/`token`/`nonce` 这几项签名,`v3` 在此基础上把 `platform`(如 `macos`/`ios`)和 `deviceFamily` 也纳入签名范围——这意味着同一把私钥签出的 `v3` 签名和它当时声明的平台/设备族绑定在一起,如果有人拿着合法私钥但试图伪装成不同平台重放,`v3` 签名校验会直接失败。Gateway 同时保留对 `v2` 的兼容回退,是为了让还没升级到 `v3` 的老客户端继续可用。

### 两层批准:设备配对 vs 节点能力批准

容易混淆的一点是把"设备配对"和"节点能力批准"当成同一件事。`docs/gateway/pairing.md` 明确把它们分成两层:

> Node pairing has two layers ... **Device pairing** (role `node`) gates the `connect` handshake ... **Node capability approval** (`node.pair.*`) gates which declared capabilities/commands a connected node may expose.

也就是说:

- **设备配对**发生在连接建立之前,决定"这个设备 ID 能不能连上 Gateway"。
- **节点能力批准**发生在连接建立之后,决定"这个已经连上的节点,声明的 `camera`/`screen`/`system.run` 这些能力,能不能被实际启用"。

这两层批准的过期策略也完全不同:

> The **5-minute expiry** still applies to **device-pairing** requests, not to capability approvals on an already-paired device.

一个已经配对好的设备,如果后来声明了新的能力(比如第一次配对时只要相机权限,后来又想要 `system.run`),这个新能力请求会挂起等待审批,**不会因为超时而自动消失**,而是一直挂着直到被显式批准、拒绝,或者设备角色被移除。这个设计是合理的:设备配对请求代表"这台设备现在正在等你确认",超时清理是为了不让过期的一次性请求堆积;而能力升级请求代表"这台已经建立信任的设备现在想要更多权限",这是一个需要人工认真对待的决定,不应该因为操作者几分钟内没看手机就自动作废。

批准节点能力时,`node.pair.approve` 还有一层基于请求声明命令的**额外**授权检查(`src/infra/node-pairing-authz.ts`):

| 声明的命令 | 需要的操作者 scope |
| --- | --- |
| 无命令 | `operator.pairing` |
| 普通命令 | `operator.pairing` + `operator.write` |
| 包含 `system.run`、`system.run.prepare`、`browser.proxy` 等高风险命令 | `operator.pairing` + `operator.admin` |

这意味着批准一个只想要 `camera.snap` 的节点,和批准一个想要执行任意 shell 命令的节点,门槛完全不同——**批准动作本身也是按风险分级的**,而不是"能批准配对就能批准一切"。

### 本地信任的例外与它的边界

如果每一次同主机重连都要人工点一下批准,日常使用体验会很差。`architecture.md` 因此明确划出了一条本地信任的例外:

> Direct local loopback connects can be auto-approved to keep same-host UX smooth. ... Tailnet and LAN connects, including same-host tailnet binds, still require explicit pairing approval.

`docs/gateway/pairing.md` 补充了一个容易被忽略但很重要的细节:通过 SSH 隧道转发的连接,在 Gateway 看来同样是"回环"连接,因为 SSH 服务端在 Gateway 主机上终结了这条连接:

> The Gateway treats a loopback source address as local. This includes a client reaching a remote loopback-only Gateway through an SSH port forward: the SSH server terminates the connection on the Gateway host, so the Gateway sees the forwarded connection as loopback. This is intentional because ordinary SSH access already implies local trust.

这条设计的逻辑是:能建立 SSH 隧道本身就已经证明了"这个人已经通过了这台主机的 SSH 认证",这份信任等级不低于本地登录,所以复用同一套自动批准策略是合理的,而不是漏洞。想要更严格的策略(比如无 shell 权限的端口转发专用密钥、多用户共享的 Mac),可以关掉这个默认行为:

```json5
{ gateway: { nodes: { pairing: { autoApproveLocal: false } } } }
```

超出"回环"范围之外,自动批准就变得谨慎得多。`pairing.md` 描述的 **SSH-verified 自动批准**是一个很值得研究的例子:对于来自私有/CGNAT 地址的首次节点配对请求,Gateway 会反向 SSH 回连到请求方主机,运行 `openclaw node identity --json`,只有当**远程返回的设备 ID 和公钥与挂起请求完全匹配**时才自动批准:

> The key match is what makes this safe: reachability alone never approves, so NAT co-tenants, other users on a shared host, and LAN spoofing all fall through to the normal prompt.

这句话点出了这套机制的设计要点:**网络可达性从来不是批准的依据,密钥匹配才是**。同一个 NAT 后面的其他租户、同一台共享主机上的其他用户、局域网里的地址欺骗,都无法仅凭"网络可达"就冒充已配对设备——因为攻击者拿不出匹配的私钥。

配套的还有 trusted-CIDR 自动批准(仅对无请求任何 scope 的全新 `role: node` 配对生效,操作者/浏览器/Control UI/WebChat 一律排除在外)和 metadata-upgrade 自动批准(仅限"显示名称"这类非敏感元数据变化,scope 升级和公钥变化永远需要显式重新批准)。这几套自动批准机制有一个共同的收紧点:**转发头证据会使"本地"判定失效**——

> Gateway pairing treats a connection as loopback only when both the raw socket and any upstream proxy evidence agree. If a request arrives on loopback but carries `Forwarded`, any `X-Forwarded-*`, or `X-Real-IP` header evidence, that forwarded-header evidence disqualifies the loopback locality claim.

这是为了防止有人在反向代理后面伪造转发头,把一个实际上来自远端的连接伪装成"回环",从而蹭到本地自动批准的便利。

## 常见问题/易踩坑

- **不要把"设备配对通过"等同于"节点能力已启用"**。设备配对只解决"这个连接能不能建立",节点声明的具体能力(`camera`/`system.run` 等)走的是独立的、不会因超时而消失的能力批准队列,两者的过期策略和授权 scope 要求都不同。
- **v3 签名失败不代表设备一定有问题,先确认版本协商是否退化到了 v2**。Gateway 会先尝试 v3 校验,失败后自动回退 v2;如果客户端库版本较旧只实现了 v2 签名负载,这是预期行为而非攻击信号。
- **本地信任的边界是"回环地址",不是"局域网"**。Tailnet/LAN 连接——即使是同主机上绑定 Tailnet 地址的连接——仍然需要显式配对;只有真正的回环连接(包括通过 SSH 隧道在本机终结的连接)才享受自动批准。

## 小结

设备信任模型解决的是"这个连接是不是那台之前被批准过的设备"这个身份持续性问题:`connect.challenge` 的 nonce+时间窗签名防重放,`v3` 签名把平台/设备族也纳入校验范围,设备配对与节点能力批准是两条独立的、过期策略不同的审批链条,本地信任的例外则严格限定在"回环地址"而不是"同一局域网"。这套模型回答了"谁能连上 Gateway",但还没回答"这台宿主机上能不能同时跑好几个 Gateway 进程、以及跑在远程主机上的 Gateway 要怎么安全地被访问"——这正是下一篇《多 Gateway、Lock 与远程访问》要展开的内容。
