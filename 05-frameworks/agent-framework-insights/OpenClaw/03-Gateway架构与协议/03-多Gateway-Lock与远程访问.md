# 多 Gateway、Lock 与远程访问

> 前两篇分别讲了 Gateway 的 WS 协议和设备信任模型,隐含的前提都是"这台主机上只有一个 Gateway 在跑"。但这个前提不是自动成立的——两个 Gateway 进程如果不小心同时抢占同一份状态目录或同一个端口,轻则互相报错退出,重则出现两个进程同时尝试打开同一个 WhatsApp 会话这种真正危险的场景。这一篇拆开三层锁机制如何在单机层面保证"恰好一个 Gateway",它又是如何与"故意运行多个 Gateway"(救援机器人、多租户隔离)的合法需求共存的,最后梳理远程访问 Gateway 的几种方式该在什么场景下选择。

## 学习目标

- 理解 Gateway 启动时依次获取的三层锁——状态目录所有权锁、配置锁、端口绑定——分别防止哪一类并发冲突,以及每一层锁失败时报出的具体错误信息。
- 理解 `OPENCLAW_ALLOW_MULTI_GATEWAY=1` 放开的是"配置层面的单例限制",而不是"共享可变状态的许可"——状态目录所有权锁在任何模式下都不会被跳过。
- 掌握"确实需要多个 Gateway"的两类合法场景(救援机器人、多租户隔离)以及它们必须保持哪些配置项互不相同。
- 能对照远程访问的几种方式——Tailscale Serve/Funnel、SSH 隧道、`trusted-proxy`——判断每一种适用的场景和各自的认证模式要求。

## 背景与设计动机

单一 Gateway 是架构上的既定选择(见第一篇),但"既定选择"不会自动在运行时生效——两个 Gateway 进程完全可能因为误操作(比如同时在两个终端里各跑了一次 `openclaw gateway`)而同时启动。`docs/gateway/gateway-lock.md` 把这层保护要解决的问题写得很直接:

> Only one gateway process should own a state directory ... Survive crashes/SIGKILL without leaving stale lock files behind ... Fail fast with a clear error when another gateway already owns the port.

这里有一个容易被忽略的设计张力:锁机制既要**严格**(不能让两个进程同时改同一份 SQLite 状态),又要**能自愈**(进程被 `SIGKILL` 硬杀之后,遗留的锁文件不能变成"永久卡死、必须手动删文件"的运维负担)。三层锁的设计正是在这两个目标之间找平衡点。

另一方面,"单一 Gateway"这个原则本身也不是绝对的——`docs/gateway/multiple-gateways.md` 承认了合理的多实例场景:救援机器人(主 Gateway 挂了的时候还有一条独立的调试通道)、多租户隔离(每个客户不共享同一个 Gateway 进程)。锁机制因此不能做成"一台主机永远只准起一个 Gateway",而要做成"一台主机上,同一份状态目录/配置/端口永远只准被一个进程占用",把隔离的责任交给运维者显式配置不同的 profile。

## 核心机制详解

### 三层锁:状态锁、配置锁、端口绑定

`gateway-lock.md` 描述了启动时严格按顺序执行的三个步骤:

> 1. **State ownership lock** acquires a lock keyed by the canonical state directory. Every Gateway participates, including Gateways started with `OPENCLAW_ALLOW_MULTI_GATEWAY=1` ...
> 2. **Config lock** acquires the historical per-config lock ... Multi-Gateway mode skips this config singleton but retains the state ownership lock.
> 3. **Socket bind** binds the HTTP/WebSocket listener ... as an exclusive TCP listener.

三层各自独立失败,各自抛出 `GatewayLockError`,这个分层设计的价值在于**故障定位精确**——运维者看到的错误信息直接指向问题出在哪一层,而不是一个笼统的"启动失败"。

**状态锁和配置锁**都基于一套带存活检测的机制:锁文件记录 PID、进程启动身份;如果记录的持有者进程已经不存在,启动流程会直接回收这把锁并继续,不需要人工介入:

> If a lock file is missing or the recorded owner process is gone, startup reclaims the lock and continues.

如果锁确实被另一个活跃进程持有,启动流程会重试到 5 秒超时,然后报出:

```text
GatewayLockError("gateway already running (pid <pid>); lock timeout after <ms>ms")
```

**端口绑定**是最后一道防线,专门处理 `EADDRINUSE`:

> On `EADDRINUSE`, startup retries the bind for up to 20 attempts at 500ms intervals (roughly 10 seconds total) to ride out a `TIME_WAIT` window after a recently exited process.

这个重试窗口的存在是为了容忍一种非常常见的良性场景:上一个 Gateway 进程刚退出,操作系统的 TCP `TIME_WAIT` 状态还没释放端口,新进程立刻尝试绑定同一个端口会短暂失败。与其让这种正常的重启操作直接报错,不如在约 10 秒的窗口内多试几次。超过这个窗口依然失败,才真正报出:

```text
GatewayLockError("another gateway instance is already listening on ws://127.0.0.1:<port>")
```

值得注意的是,系统服务管理器(systemd/launchd)在遇到这两类锁错误时还有一层协作逻辑:新进程会先探测 `/healthz`,如果发现已有进程是健康的,就主动放弃、把控制权留给现有进程,而不是死循环重启自己:

> Under a service supervisor, a new gateway process that hits either error above first probes `/healthz` on the existing process. If that process is healthy, the new process leaves it in control instead of failing.

在 systemd 上,这条路径退出码是 `78`,配合 `RestartPreventExitStatus=78` 让 `Restart=always` 不会对着一个"端口冲突"的场景无限重启——这一点在下一篇讲重启恢复时还会再遇到。

### 与"多 Gateway"共存:profile + 端口隔离

`OPENCLAW_ALLOW_MULTI_GATEWAY=1` 这个开关容易被误读成"关掉单例限制",但 `gateway-lock.md` 的措辞很精确:

> `OPENCLAW_ALLOW_MULTI_GATEWAY=1` permits multiple config/runtime instances, not shared mutable state. Each instance still needs a unique `OPENCLAW_STATE_DIR`.

也就是说,这个开关放开的只是**配置锁**这一层(允许多个不同配置文件的 Gateway 同时跑),状态锁——保护实际可变数据(SQLite 会话、凭证)的那一层——在任何模式下都不会被跳过。这是设计上刻意的不对称:配置隔离是运维选择,数据一致性不是可以被开关关掉的选项。

`multiple-gateways.md` 给出的隔离清单,把"必须唯一"的配置项列得很具体:

| 配置项 | 作用 |
| --- | --- |
| `OPENCLAW_CONFIG_PATH` | 每实例独立的配置文件 |
| `OPENCLAW_STATE_DIR` | 每实例独立的会话、凭证、缓存 |
| `agents.defaults.workspace` | 每实例独立的工作区根目录 |
| `gateway.port`(或 `--port`) | 每实例唯一端口 |

一个容易踩的坑是端口不是只有 `gateway.port` 一个数字——`multiple-gateways.md` 给出了派生端口的计算规则:浏览器控制服务端口是 `base + 2`,浏览器 CDP 端口范围是 `控制端口 + 9` 到 `+ 108`。这意味着规划多实例端口时,两个 Gateway 的 base 端口之间至少要留出 120 的间隔,否则派生出来的浏览器控制端口/CDP 范围会互相冲突,即使 `gateway.port` 本身看起来没有重复。

救援机器人是这套隔离机制最典型的应用场景:主 Gateway 用默认 profile,救援 Gateway 用独立 profile、独立 Telegram bot token、独立端口——这样即使主 Gateway 因为配置错误起不来,救援 Gateway 依然可以正常工作,让操作者远程修复主 Gateway 的配置。

### 远程访问的选型

Gateway 默认只绑定回环地址(`docs/gateway/index.md`:"Default bind mode: `loopback`"),这是一个刻意的保守默认——不给公网或局域网留出攻击面,把"要不要暴露、暴露多大范围"变成运维者的显式决定。`docs/gateway/remote.md` 给出的选型表把三种典型部署场景和对应的推荐方式对上号:

| 场景 | Gateway 运行位置 | 推荐方式 |
| --- | --- | --- |
| 常驻在 Tailnet 里的 Gateway | VPS 或家用服务器 | Tailscale 或 SSH |
| 家用台式机 | 台式机常开,笔记本远程连 | macOS App 的 remote 模式 |
| 笔记本本身 | 笔记本 | SSH 隧道或 Tailscale Serve,保持 `gateway.bind: "loopback"` |

`remote.md` 给远程访问的安全规则定了调:

> Keep the Gateway **loopback-only** unless you are sure you need a bind. **Loopback + SSH/Tailscale Serve** is the safest default (no public exposure).

也就是说,**首选永远不是"换一个绑定地址",而是"保持回环绑定,再用隧道/身份代理把访问权限转发进来"**。三种具体方式各自的适用场景:

**SSH 隧道**是最通用的兜底方案,任何能 SSH 到 Gateway 主机的人都能用:

```bash
ssh -N -L 18789:127.0.0.1:18789 user@gateway-host
```

隧道本身不绕过 Gateway 认证——`remote.md` 特别提示"SSH tunnels do not bypass gateway auth. For shared-secret auth, clients still must send `token`/`password` even over the tunnel."也就是说 SSH 隧道解决的只是网络可达性,认证仍然要正常走一遍。这个方式的缺点是每个客户端都要自己维护一条隧道进程,适合临时调试或单人使用,不适合多客户端长期访问。

**Tailscale Serve/Funnel** 解决的正是"多客户端长期访问"这个诉求,用一个稳定的 HTTPS/WSS URL 替代一堆各自独立的 SSH 隧道(`docs/gateway/stable-https-url.md`)。`docs/gateway/tailscale.md` 区分了两种模式:

> `serve`:Tailnet-only Serve ... The gateway stays on `127.0.0.1`. `funnel`:Public HTTPS via `tailscale funnel` ... Requires a shared password.

Serve 只在你自己的 Tailnet 内可见,Funnel 则是真正暴露到公网,因此协议层面强制要求 Funnel 必须配合密码认证——"`tailscale.mode: "funnel"` refuses to start unless auth mode is `password`, to avoid public exposure."当 `gateway.auth.allowTailscale: true` 时,Tailscale Serve 的身份头(`tailscale-user-login`)甚至可以完全替代 token/password,但这条无密码路径的前提是"信任 Gateway 主机本身"——如果同一台主机上可能跑着不受信的本地代码,应该关掉这个选项,回退到显式的共享密钥认证。

**`trusted-proxy` 模式**是给"Gateway 已经跑在身份感知反向代理(Pomerium、Caddy+OAuth、nginx+oauth2-proxy)后面"这种部署准备的:代理完成用户认证后,通过头部(如 `x-forwarded-user`)把身份传给 Gateway,Gateway 只信任来自配置好的 `gateway.trustedProxies` 地址的请求。`docs/gateway/trusted-proxy-auth.md` 的运行时校验顺序值得注意——**回环来源默认被拒绝**,除非显式打开 `allowLoopback` 并把回环地址也加进 `trustedProxies`;同时有一条专门的反欺骗检查,拒绝那些恰好匹配 Gateway 主机自身网卡地址的非回环来源。这套顺序保证了"信任代理"这件事必须被非常明确地声明,不会因为代理和 Gateway 部署在同一台机器上而意外放松。

三种方式并不互斥,可以按"默认关闭 → 需要时开一条"的顺序去选:个人独自使用,SSH 隧道够用;需要多设备长期访问自己的资源,上 Tailscale Serve;把 Gateway 部署进已经有统一身份系统的团队基础设施,用 `trusted-proxy` 对接现有的认证边界。

## 常见问题/易踩坑

- **`OPENCLAW_ALLOW_MULTI_GATEWAY=1` 不等于"可以共享状态目录"**。这个开关只放开配置锁,状态目录所有权锁在任何模式下都强制唯一,每个实例仍然必须有独立的 `OPENCLAW_STATE_DIR`。
- **规划多实例端口时不要只看 `gateway.port` 本身是否唯一**。浏览器控制端口(`base+2`)和 CDP 端口范围(`控制端口+9` 到 `+108`)是派生出来的,两个实例的 base 端口至少要间隔 120 才能避免派生端口冲突。
- **不要把"换成非回环绑定"当成远程访问的默认方案**。`remote.md` 的安全规则明确把"回环 + SSH/Tailscale Serve"列为最安全的默认,非回环绑定必须搭配 Gateway 认证(token/password/trusted-proxy),而且这条认证要求不会因为走了 SSH 隧道就被免除。

## 小结

三层锁——状态锁、配置锁、端口绑定——各自独立失败、各自可以在持有者进程消失后自愈,把"恰好一个 Gateway 控制一份状态"这条不变量落到了运行时;`OPENCLAW_ALLOW_MULTI_GATEWAY` 和 profile 隔离机制则让救援机器人、多租户这类合法的多实例场景可以显式声明自己的独立配置、状态目录和端口范围。远程访问的选型遵循"默认回环绑定、按需叠加隧道或身份代理"的原则,SSH 隧道、Tailscale Serve/Funnel、`trusted-proxy` 分别对应单人调试、多设备长期访问、企业身份系统对接三种场景。锁与远程访问都是控制平面"怎么被连上"的问题,而 Gateway 是否处于健康状态、这份健康状态如何被外部系统观测,是下一篇《Health、Heartbeat 与可观测性》要展开的内容。
