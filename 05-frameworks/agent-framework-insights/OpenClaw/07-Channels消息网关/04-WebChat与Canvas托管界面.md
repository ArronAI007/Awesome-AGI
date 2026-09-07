# WebChat 与 Canvas 托管界面

> 前三篇讲的都是"文字进、文字出"的消息渠道,但 Gateway 的 HTTP 服务器上还挂着两条完全不同性质的路由——`/__openclaw__/canvas/`(托管的组件文档)和 `/__openclaw__/a2ui/`(A2UI 渲染器资源),`docs/concepts/architecture.md` 把它们统称为"hosted widget surface"。这一篇要讲清楚 WebChat 这个原生客户端本身的定位,以及 Canvas 这套让 agent 生成一整块可交互网页组件、托管在 Gateway 上供多种界面复用的系统是怎么运作的。

## 学习目标

- 理解 WebChat 在 OpenClaw 架构里的定位——它是一个直连 Gateway WebSocket 的原生客户端,不是一个独立的 Web 服务器,也没有自己的持久化配置。
- 理解"hosted widget surface"这个概念:Canvas 文档和 A2UI 渲染资源为什么要托管在 Gateway HTTP 服务器的固定路径下,而不是各自散落在不同界面里。
- 通过 `src/canvas/documents.ts` 的真实实现,理解一份 Canvas 文档是怎么被物化到磁盘、怎么防止路径穿越、怎么按作用域做数量上限清理的。
- 通过 `src/canvas/wrap.ts` 的真实实现,理解 agent 生成的 widget 代码是怎么被套进一个受 CSP 约束的 iframe,以及宿主与 widget 之间那套基于 `postMessage` 的能力桥接协议。
- 理解 Canvas 与 A2UI 的边界——macOS 面板只承载 Canvas 托管文档,A2UI 组件只在 session dashboard 上渲染,两者不是同一套推送目标。

## 背景与设计动机

一个消息网关的天然表现力是有限的——文字、有限的富文本、平台原生的卡片组件。但很多场景需要 agent 展示一份更复杂的可视化结果:一张实时更新的构建状态图、一个可以点击交互的表单、一段带图表的报告。如果这类"超越纯文本"的呈现需求要靠每个消息渠道各自实现一套私有的富组件系统,就会重新制造出第一篇讲过的那种"渠道各自发明业务语义"的碎片化问题。OpenClaw 的解法是把这类内容托管成 Gateway HTTP 服务器上的静态文档,由不同的界面(聊天内联展示、macOS 原生面板、session dashboard)各自决定"要不要展示、怎么展示"，而生成和存储这份内容的逻辑只有一套。

## 核心机制详解

### WebChat:一个直连 Gateway 的原生客户端,不是独立服务

`docs/web/webchat.md` 开篇第一句话就把 WebChat 的定位讲清楚了:"the macOS/iOS SwiftUI chat UI talks directly to the Gateway WebSocket. No embedded browser, no local static server."`docs/concepts/architecture.md` 补充了它和其他消息渠道共享的底层机制:"Static UI that uses the Gateway WS API for chat history and sends. In remote setups, connects through the same SSH/Tailscale tunnel as other clients."

这意味着 WebChat 并不是一个独立部署的 Web 服务,它复用的正是前几篇讲过的同一个 Gateway WebSocket 协议——`chat.history`/`chat.send`/`chat.inject` 这些 RPC 方法背后走的是和 Telegram/Discord 完全一样的会话路由和消息分发机制。`docs/web/webchat.md` 的配置参考一节说得很直接:"WebChat has no persisted config section."——它没有自己独立的持久化配置,历史记录永远从 Gateway 现取而不做本地文件缓存,Gateway 不可达时 WebChat 直接进入只读状态,而不是回退到某份本地缓存的旧数据。这个"无本地真相源"的设计避免了 WebChat 展示的内容和 Gateway 端真实会话状态产生分歧的可能。

### Hosted Widget Surface:两条固定路由,一个端口

`docs/concepts/architecture.md` 在描述 Gateway 组成时专门列出了这两条路由:

> - The **hosted widget surface** is served by the Gateway HTTP server under:
>   - `/__openclaw__/canvas/` (hosted widget documents)
>   - `/__openclaw__/a2ui/` (A2UI renderer assets)
>
>   It uses the same port as the Gateway (default `18789`).

这两条路由复用 Gateway 已经在监听的同一个端口,而不是另开一个独立的 Web 服务——这意味着托管内容天然继承了 Gateway 已有的网络暴露面和鉴权边界,不需要为"如何安全地对外暴露一个新端口"这个问题单独设计一套方案。`docs/platforms/mac/canvas.md` 里也印证了这一点——节点通过 `canvas.navigate` 命令加载的托管路径,是"resolved through the node session's current scoped `pluginSurfaceUrls.canvas` URL",也就是说这条能力 URL 本身是绑定在已经通过节点配对(上一篇讲过的连接层信任)的会话身份上的短时效凭证,而不是一个任何人都能访问的公开静态资源路径。

### Canvas 文档的物化:从 agent 生成的内容到磁盘上的静态文件

`src/canvas/documents.ts` 里的 `createCanvasDocument(...)` 是这套系统的核心入口,它把 agent 提供的一段内容(HTML 字符串、本地文件路径、外部 URL、图片、视频)"物化"成磁盘上一个独立目录里的静态文件集合,再生成一份托管 URL。这个过程里有几处值得展开的实现细节。

**路径穿越防护是逐层做的。** 文档 ID 和逻辑路径都要经过显式校验:

```ts
function normalizeCanvasDocumentId(value: string): string {
  const normalized = value.trim();
  if (
    !normalized ||
    normalized === "." ||
    normalized === ".." ||
    !/^[A-Za-z0-9._-]+$/.test(normalized)
  ) {
    throw new Error("canvas document id invalid");
  }
  return normalized;
}
```

而把托管 URL 反向映射回本地磁盘路径的 `resolveCanvasHttpPathToLocalPath(...)`,在算出候选路径之后还要再做一次边界校验:

```ts
const candidatePath = path.resolve(
  resolveCanvasDocumentDir(documentId, options),
  normalizedEntrypoint,
);
if (!candidatePath.startsWith(`${documentsDir}${path.sep}`)) {
  return null;
}
```

这两层校验合在一起,保证了无论请求路径里出现多少层 `../` 或者非法字符,最终解析出的本地文件路径都不可能跳出 Canvas 文档的根目录——这是"托管任意 agent 生成内容"这类系统必须严肃对待的边界,因为托管内容的来源(模型输出)天然是不受信任的输入。

**不同内容类型有不同的物化策略。** 直接的 HTML 字符串被原样写成 `index.html`;图片和视频会被包进一个居中展示的最小 HTML 包装页;PDF 路径或 URL 会被包进一个 `<object>`/`<iframe>` 双重兜底的查看器,并在预览失败时给出一个"打开 PDF"的直接链接——`buildPdfWrapper(...)` 里能看到这个兜底逻辑写得很实际,不假设所有客户端都能内联渲染 PDF。

**按作用域的数量上限清理。** 每次创建文档时,如果调用方提供了 `retentionScope` 和 `maxDocumentsPerScope`,系统会在写完新文档之后清理同一作用域下最旧的多余文档:

```ts
if (input.retentionScope && options?.maxDocumentsPerScope) {
  // Bounded transcript widgets cannot grow managed Canvas storage without limit.
  await pruneCanvasDocumentsForScope({
    documentsDir: resolveCanvasDocumentsDir(options.stateDir),
    retentionScope: input.retentionScope,
    maxDocuments: options.maxDocumentsPerScope,
  });
}
```

注释里的"Bounded transcript widgets cannot grow managed Canvas storage without limit"点出了这个机制存在的原因——如果一个长期运行的会话反复调用 `show_widget` 生成新文档,而磁盘存储没有上限,Canvas 文档目录会随着会话时间线性增长下去,这道清理逻辑把增长收敛在一个按作用域配置的固定窗口内。

### Widget 文档的运行时隔离:CSP、iframe 与能力桥接

agent 生成的 widget 代码本质上是不受信任的输出——它可能来自模型的自由生成,也可能被 prompt injection 影响。`src/canvas/wrap.ts` 里的 `buildWidgetDocument(...)` 负责把这段代码套进一层受限的执行环境,核心是一条明确收紧的 CSP:

```ts
return `<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'${scriptSources}; img-src data:; connect-src ${connectSources};">
<title>${escapeHtml(title)}</title><style>${WIDGET_BASE_STYLES}</style></head>
<body${bodyClass}>${widgetBridge}${themeBridge}${chatHostBridge}${snapshotBridge}${sizeReporter}${widgetCode}</body></html>`;
```

`default-src 'none'` 是这条策略的基线——widget 文档默认不能加载任何外部资源,`connect-src` 只放行显式批准过的网络来源(对应 `show_widget` 工具参数里的 `capabilities.netOrigins`),图片只能通过 `data:` URI 内嵌而不能从网络拉取。这层策略把"widget 代码能做什么"收紧到了一个默认空白的白名单模型,和第一篇讲的渠道插件"能力必须显式声明"是同一种设计取向的另一种体现。

widget 和宿主页面之间的通信走的是显式的 `postMessage` 能力桥接,而不是让 widget 直接拥有 DOM 访问权或者全局对象访问权。`widgetBridge` 这段脚本会先向父窗口"要"一个能力票据(`ticket`),之后所有跨越 iframe 边界的操作——发送 prompt、上报状态、读取数据绑定、触发已注册的 action、触发 cron 任务——都必须带着这张票据通过一个统一的请求通道发出去:

```ts
const request = (method, params) => new P((resolve, reject) => {
  const send = () => {
    const id = "widget-" + (++sequence);
    pending.set(id, { resolve, reject });
    bridgePost({ type: "openclaw:widget-bridge-request", id, method, params, ticket });
  };
  if (ticket) send();
  else if (hostInitExpired) reject(new ErrorCtor("widget host capabilities unavailable"));
  else push.call(waiting, { send, reject });
});
```

暴露给 widget 代码的 API 也被冻结成了一个显式的能力清单——`prompt.send`、`state.emit`、`data.read`、`action.run`、`cron.trigger`——而不是给 widget 一个可以为所欲为的宿主引用:

```ts
const api = freeze({
  host,
  prompt: freeze({ send: sendPrompt }),
  state: freeze({ emit: (payload) => request("state.emit", { payload }) }),
  data: freeze({ read: (bindingId, params) => request("data.read", { bindingId: String(bindingId), params }) }),
  action: freeze({ run: (action, params) => request("action.run", { action: String(action), params: params === undefined ? {} : params }) }),
  cron: freeze({ trigger: (jobId) => request("cron.trigger", { jobId: String(jobId) }) }),
});
```

这套设计和第一篇讲的"transport-only"边界其实是同一个原则在另一个层面的重复:widget 代码不被信任去直接操纵宿主状态,它只能通过一条显式声明、逐项审批的请求通道,请求宿主代为完成某个具体动作——宿主始终掌握着"这个请求该不该被批准执行"的最终决定权。

### show_widget 工具:agent 一侧的入口契约

从 agent 的视角看,生成一个 widget 只需要调用 `show_widget` 工具,`src/canvas/widget-tool.ts` 里的 schema 定义了这个工具暴露给模型的完整参数面——`title`、`widget_code`(HTML/SVG 或者已注册的内容源)、可选的 `kind`、决定展示位置的 `presentation.target`(内联聊天消息或者具体的展示器目标)、以及 `capabilities.netOrigins`/`capabilities.tools` 这两个必须显式列出的能力授权字段。工具描述里的一句提示也值得记一笔:"Use fluid widths and wrap or stack narrow layouts; reserve horizontal scrolling for exact geometry."——这是在提醒模型,widget 最终可能被嵌入宽度差异很大的宿主容器(聊天气泡、dashboard 卡片、macOS 面板),生成的布局需要对宽度变化有弹性,而不是假设一个固定的视口尺寸。

### Canvas 与 A2UI 的边界:两套推送目标,不能混用

`docs/platforms/mac/canvas.md` 特意用一整节来澄清一个容易混淆的边界——macOS 原生面板只承载 Canvas 托管文档,不是 A2UI 的推送目标:

> A2UI widgets render on [session dashboards](/web/dashboards), where they share the same pinning, layout, approval, and interaction model as other dashboard widgets. Their renderer bundles continue to load from the Gateway's `/__openclaw__/a2ui/` asset route.
>
> The macOS panel does not accept A2UI push/reset commands and does not automatically navigate to an A2UI page.

也就是说,虽然 Canvas 文档和 A2UI 渲染资源共享同一个"hosted widget surface"的托管机制,两者服务的却是不同的呈现场景:Canvas 文档是"agent 生成一份内容,某个界面展示它",A2UI 走的是 session dashboard 那一套带 pinning、审批、交互模型的组件推送系统,面向的是需要长期驻留、可被多次更新的仪表盘卡片,而不是一次性生成的临时展示内容。文档同时提醒了 Canvas 面板本身"render-only"的定位:"Widgets in the native panel are render-only. Host-integrated widget actions remain available in Control UI chat and session dashboard surfaces, not in the panel."——macOS 面板上的 widget 只负责显示,真正带交互能力的 widget 动作(前面讲的 `action.run`、`prompt.send` 这些桥接调用)目前仍然只在 Control UI 聊天界面和 session dashboard 里可用。

## 常见问题/易踩坑

**Q:WebChat 是不是需要单独部署一个 Web 服务器?**

不需要。WebChat 是原生 SwiftUI 客户端(macOS/iOS)或者 Control UI 里的一个聊天标签页,直接连接 Gateway 的 WebSocket,没有嵌入式浏览器,也没有本地静态服务器。`docs/web/webchat.md` 明确写着"No embedded browser, no local static server."远程场景下它复用的是和其他客户端一样的 SSH/Tailscale 隧道。

**Q:agent 生成的 widget 代码能不能直接发起网络请求?**

默认不能。`buildWidgetDocument(...)` 生成的 CSP 里 `connect-src` 默认是 `'none'`,只有当 `show_widget` 工具调用时显式列出了 `capabilities.netOrigins`,对应的源才会被加进 `connect-src` 白名单。这是一处"能力必须显式声明"的具体落地,不存在"widget 代码碰巧知道某个内部接口就能调用"的隐式路径。

**Q:能不能让 macOS 原生面板展示一个 A2UI 组件?**

不能。这是两套独立的推送目标——macOS 面板只接受 Canvas 托管文档的 `canvas.navigate` 导航,不接受 A2UI 的推送/重置命令。A2UI 组件的合法呈现位置是 session dashboard,两者共享托管资源的加载路径(`/__openclaw__/a2ui/`),但不共享推送通道。

## 小结

WebChat 是一个直连 Gateway WebSocket、没有独立持久化配置的原生客户端,历史记录和会话状态永远以 Gateway 为唯一真相源。Canvas 和 A2UI 共同构成了 Gateway HTTP 服务器上的"hosted widget surface"——`/__openclaw__/canvas/` 托管 agent 生成的静态组件文档,物化过程里有逐层的路径穿越防护和按作用域的数量上限清理;`/__openclaw__/a2ui/` 托管 session dashboard 组件系统所需的渲染资源。生成的 widget 文档被套进一层默认拒绝一切外部资源的 CSP,widget 代码和宿主之间只能通过一套显式声明、逐项审批的 `postMessage` 能力桥接通信——这和第一篇讲的渠道插件契约是同一种"边界处必须显式声明能力,不能靠隐式假设"的设计纪律在另一个层面的重复。到这里,第 07 章把消息网关从渠道契约、代表性实现、访问控制,一路讲到了托管界面系统。下一章会转向设备侧——原生 Companion App 和 Node,看看手机、桌面这些真正的终端设备是怎么作为一等公民接入 Gateway,又能调用哪些渠道消息之外的原生能力。
