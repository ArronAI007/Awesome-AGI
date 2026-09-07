# Autopilot 运行快照服务与 React 仪表盘

> Autopilot 的可观测性方案里没有服务端进程,没有 WebSocket,甚至没有一个"定时刷新"的调度器——它把每一次任务状态变更,顺手换算成一次静态文件写入:`rebuild_active_context()` 每次改完 registry 都会在末尾调用一次 `export_dashboard()`,把当前状态整份序列化成 `docs/autopilot/snapshot.json`。前端是一个独立的 React + Vite 项目,构建产物直接落进后端写快照的同一个目录,靠 `fetch("./snapshot.json")` 把 JSON 渲染成看板。整条链路不需要任何常驻服务——GitHub Pages 就是它的"后端"。本篇把这套零运维的可观测性方案从数据模型、落盘时机一路读到前端渲染,顺带揪出一个真实存在的、docstring 与实现不一致的坑。

## 学习目标

- 理解 Autopilot 要解决的问题:当 Agent 通过 cron 无人值守地长期自主运行时,用户如何在不连进任何进程的情况下随时看到"现在在干什么"。
- 通读 `RepoTaskCard` 的十三态状态机(`types.py`)和 `RepoAutopilotStore` 的三份落盘文件(registry / journal / active_context),理解每一份文件各自记录哪一段历史。
- 理解快照导出的触发时机——不是定时任务,而是挂在每一次状态变更(`enqueue_card`/`update_status`/`scan_all_sources`)之后,通过 `rebuild_active_context()` 的尾部调用触发。
- 逐字段核对 `_build_dashboard_snapshot()` 产出的结构与仓库里真实的 `docs/autopilot/snapshot.json`,搞清楚快照里到底装了什么。
- 理解 `autopilot-dashboard` 这个独立 React/Vite 项目的部署形态:`vite.config.ts` 里 `base`/`outDir` 的选择如何让它和后端产物共享同一个静态目录,最终变成一个可以直接托管在 GitHub Pages 上的零后端站点。
- 对照 `types.py` 和 `dashboard/src/types.ts` 两侧的字段,理解"一份 JSON 快照即契约"这种前后端解耦方式的取舍,以及它和第 02 章讲过的 Ink TUI/Textual 双前端相比,服务的是完全不同的场景。

## 背景与设计动机

Autopilot 是 OpenHarness 用来"自我进化"的一条流水线:`RepoAutopilotStore` 会扫描 GitHub issues、GitHub PR、以及本机 `claude-code` 目录下的候选想法,把它们归一化成一张张 `RepoTaskCard`,依次拉出一个 git worktree、跑 Agent 修改代码、跑校验命令、开 PR、轮询 CI、必要时自动合并。这条流水线被设计为可以完全脱离人的实时看护运行——`install_default_cron()` 会注册两个 cron 任务:每 30 分钟 `oh autopilot scan all` 拉取新的候选任务,每 2 小时 `oh autopilot tick` 在空闲时跑一张队列里优先级最高的卡片。

问题是,一旦交给 cron 无人值守地跑起来,用户就失去了"开着终端盯着输出"这个默认的可观测性手段:没人知道现在卡在哪个状态、哪个 PR 的 CI 挂了、上一次失败是为什么。第 07 章讲的 Swarm/Task 协作是"有人在场、主动发起并观察"的场景;Autopilot 面对的是完全相反的一端——周期性、自主触发、随时可能没有人在看。它需要的不是一个更好的终端输出格式,而是一个"随时能打开看一眼"的东西,并且这个东西不应该要求用户先 SSH 到某台机器、连上某个正在运行的进程。

Autopilot 的解法是把状态"物化"成文件:每次状态变更都被写进本地的 registry/journal,同时投影出一份公开可读的 `snapshot.json`;再用一个独立的静态前端项目把这份 JSON 渲染成看板,发布到 GitHub Pages。整条观测链路里,"最新状态"永远只比"最后一次状态变更"晚一步,而且不需要任何专门为可观测性而常驻的服务进程。

## 核心机制详解

### RepoTaskCard 的十三态状态机

`src/openharness/autopilot/types.py` 定义了 Autopilot 管理的全部状态:

```python
# src/openharness/autopilot/types.py
RepoTaskStatus = Literal[
    "queued",
    "accepted",
    "preparing",
    "running",
    "verifying",
    "pr_open",
    "waiting_ci",
    "repairing",
    "completed",
    "merged",
    "failed",
    "rejected",
    "superseded",
]
RepoTaskSource = Literal[
    "ohmo_request",
    "manual_idea",
    "github_issue",
    "github_pr",
    "claude_code_candidate",
]


class RepoTaskCard(BaseModel):
    """One normalized repo-level work item."""

    id: str
    fingerprint: str
    title: str
    body: str = ""
    source_kind: RepoTaskSource
    source_ref: str = ""
    status: RepoTaskStatus = "queued"
    score: int = 0
    score_reasons: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float
    updated_at: float
```

一张卡片从 `queued`（入队）经 `accepted`/`preparing`/`running`/`verifying` 一路跑到 `pr_open`,再进入 `waiting_ci` 等 CI 结果,失败了可能回到 `repairing` 重试,最终落在 `completed`/`merged`/`failed`/`rejected`/`superseded` 五个终态之一。`fingerprint` 用来在重复扫描时把同一个 issue/PR 去重合并进已有卡片,而不是每次扫描都新建一张——这也是为什么下面 `enqueue_card` 里"找到已存在卡片就刷新、找不到才新建"这条分支是必需的。`RepoJournalEntry`、`RepoAutopilotRegistry`、`RepoVerificationStep`、`RepoRunResult` 是围绕这张卡片的辅助模型,分别对应下面要讲的追加日志、注册表整体、单条校验命令结果、一次执行的最终结果。

### 三份文件各管一段历史

`RepoAutopilotStore`(`src/openharness/autopilot/service.py`)把状态拆成三份职责完全不同的文件,都落在项目内的 `.openharness/autopilot/` 目录下(`config/paths.py` 里的 `registry.json` / `repo_journal.jsonl` / `active_repo_context.md`):

- **registry.json**——`RepoAutopilotRegistry`,当前所有卡片的最新快照,每次更新都整体重写,是"现在是什么状态"的权威来源。
- **repo_journal.jsonl**——一行一条 JSON 的追加写日志,记录"发生过什么",永远不会被覆盖或压缩。
- **active_repo_context.md**——一份为 Agent 自己准备的、人类可读的 Markdown 摘要,每次状态变更后重新生成,用来在下一次 Agent 调用时作为系统上下文注入,告诉它"现在整个仓库的自动化任务处于什么状态"。

`update_status()` 是这三者如何被同时驱动的典型例子:

```python
# src/openharness/autopilot/service.py
def update_status(
    self,
    card_id: str,
    *,
    status: RepoTaskStatus,
    note: str | None = None,
    metadata_updates: dict[str, Any] | None = None,
) -> RepoTaskCard:
    registry = self._load_registry()
    card = next((item for item in registry.cards if item.id == card_id), None)
    if card is None:
        raise ValueError(f"No autopilot card found with ID: {card_id}")
    card.status = status
    card.updated_at = time.time()
    if note:
        card.metadata["last_note"] = note.strip()
    if metadata_updates:
        card.metadata.update(metadata_updates)
    card.score, card.score_reasons = self._score_card(card)
    self._save_registry(registry)
    summary = f"{status}: {card.title}"
    if note:
        summary = f"{summary} ({_shorten(note, limit=80)})"
    self.append_journal(kind=f"status_{status}", summary=summary, task_id=card.id)
    self.rebuild_active_context()
    return card
```

一次状态迁移做了三件事:重写 registry(最新状态)、追加一条 journal 条目(历史事件)、重建 active context(agent 上下文)。三份文件语义不同,但由同一次调用原子地驱动更新,不存在"registry 更新了但 journal 没跟上"这种不一致窗口。

### 快照导出不是定时任务,而是挂在每次状态变更之后

`rebuild_active_context()` 的最后两行是整个可观测性方案里最容易被忽略、但也是最关键的一处设计:

```python
# src/openharness/autopilot/service.py（rebuild_active_context 尾部)
content = "\n".join(lines).strip() + "\n"
atomic_write_text(self._context_path, content)
self.export_dashboard()
return content
```

也就是说,`enqueue_card()`、`update_status()`、`scan_all_sources()` 这些会改变状态的方法,最终都会调用 `rebuild_active_context()`,而后者顺带把 `export_dashboard()` 也调用了一遍。这意味着 `docs/autopilot/snapshot.json` 从来不需要一个独立的"每隔 N 秒重新生成快照"的调度循环——它天然就是"最多落后一次状态变更"的,因为凡是能改变状态的代码路径,末端都汇聚到同一处导出调用。

`export_dashboard()` 本身很直接:

```python
# src/openharness/autopilot/service.py
def export_dashboard(self, output_dir: str | Path | None = None) -> Path:
    target_dir = Path(output_dir) if output_dir is not None else self._cwd / "docs" / "autopilot"
    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot = self._build_dashboard_snapshot()
    atomic_write_text(
        target_dir / "snapshot.json",
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=_json_default) + "\n",
    )
    atomic_write_text(target_dir / "index.html", self._render_dashboard_html(snapshot))
    atomic_write_text(target_dir / ".nojekyll", "")
    return target_dir
```

`oh autopilot export-dashboard` CLI 命令直接暴露了这个方法,便于在 CI 里显式触发一次导出(比如即使没有任何卡片状态变化,也想在部署流水线里刷新一次 `generated_at` 时间戳);但绝大多数情况下,快照是被动跟随状态变更"顺便"生成的,不需要额外操心。

### 快照里到底装了什么

`_build_dashboard_snapshot()` 把 registry 和 journal 投影成前端要消费的完整结构:

```python
# src/openharness/autopilot/service.py（节选)
return {
    "generated_at": time.time(),
    "repo_name": self._cwd.name,
    "repo_path": str(self._cwd),
    "focus": focus,
    "counts": counts,
    "status_order": status_order,
    "columns": columns,
    "cards": [self._serialize_card(card) for card in cards],
    "journal": [
        {
            "timestamp": entry.timestamp,
            "kind": entry.kind,
            "summary": entry.summary,
            "task_id": entry.task_id,
            "metadata": entry.metadata,
        }
        for entry in self.load_journal(limit=30)
    ],
    "policies": {
        "autopilot": str(get_project_autopilot_policy_path(self._cwd)),
        "verification": str(get_project_verification_policy_path(self._cwd)),
        "release": str(get_project_release_policy_path(self._cwd)),
    },
    "active_context": self.load_active_context(),
}
```

仓库里 `docs/autopilot/snapshot.json` 是一份真实生成过的样例(空闲状态,没有任何进行中的卡片),字段结构和上面的代码逐一对得上:

```json
{
  "generated_at": 1776338766.0050209,
  "repo_name": "OpenHarness-new",
  "repo_path": "/home/tangjiabin/OpenHarness-new",
  "focus": null,
  "counts": { "queued": 0, "accepted": 0, "...": 0 },
  "status_order": ["queued", "accepted", "..."],
  "columns": { "queued": [], "accepted": [], "...": [] },
  "cards": [],
  "journal": [],
  "policies": {
    "autopilot": "/home/tangjiabin/OpenHarness-new/.openharness/autopilot/autopilot_policy.yaml",
    "verification": "...",
    "release": "..."
  },
  "active_context": "# Active Repo Context\n\n..."
}
```

值得注意的几点设计:`columns` 是按状态分桶的看板视图(每个状态一个数组),`cards` 又把全部卡片平铺了一份——这是"给看板用的分组视图"和"给搜索/过滤用的扁平列表"两种消费形态各存一份,前端不需要自己再做分组计算。`focus` 是从 `repairing`/`waiting_ci`/`running`/`verifying`/`preparing`/`accepted`/`queued` 这个优先级顺序里挑出的第一张"当前最值得关注"的卡片,直接决定了仪表盘首屏那句"CURRENT_FOCUS"文案。`active_context` 把前面讲过的那份 Markdown 原文整段塞进了快照——这份原本是写给 Agent 自己看的上下文,顺手也成了给人看仪表盘时的补充信息,一份文本两种消费者。

`_serialize_card()` 展开的 `metadata` 字段明显比 `RepoTaskCard.metadata` 这个自由字典宽:

```python
# src/openharness/autopilot/service.py（_serialize_card 节选)
"metadata": {
    "last_note": _safe_text(card.metadata.get("last_note")),
    "url": _safe_text(card.metadata.get("url")),
    "execution_model": _safe_text(card.metadata.get("execution_model")),
    "assistant_summary_preview": _safe_text(card.metadata.get("assistant_summary_preview")),
    "human_gate_pending": bool(card.metadata.get("human_gate_pending")),
    "verification_failed": bool(card.metadata.get("verification_failed")),
    "attempt_count": int(card.metadata.get("attempt_count", 0) or 0),
    "max_attempts": int(card.metadata.get("max_attempts", 0) or 0),
    "linked_pr_number": card.metadata.get("linked_pr_number"),
    "linked_pr_url": _safe_text(card.metadata.get("linked_pr_url")),
    "last_ci_conclusion": _safe_text(card.metadata.get("last_ci_conclusion")),
    "last_ci_summary": _safe_text(card.metadata.get("last_ci_summary")),
    "last_failure_stage": _safe_text(card.metadata.get("last_failure_stage")),
    "last_failure_summary": _safe_text(card.metadata.get("last_failure_summary")),
    "verification_steps": verification_steps,
},
```

`RepoTaskCard.metadata` 在类型定义里只是一个 `dict[str, Any]`,真正的"这张卡片该有哪些看得懂的字段"其实是由这个序列化函数事后白名单式地整理出来的——快照契约的真正定义者不是 Pydantic 模型,而是这个投影函数。

### docs/autopilot/ 是一个零运维的静态站点

`.nojekyll` 是专门为 GitHub Pages 准备的:Pages 默认会用 Jekyll 处理发布目录,而 Jekyll 会忽略下划线开头的文件/目录,这和 Vite 打包产物里可能出现的目录命名冲突;放一个空的 `.nojekyll` 文件能彻底关掉 Jekyll 处理,让目录下的文件原样发布。这也解释了为什么 `export_dashboard()` 每次都会重写这个空文件——它不依赖任何构建工具,只要 Python 侧跑一次导出就足够保证这个开关一直开着。

不过 `_render_dashboard_html()` 的 docstring 和它的调用方式有一处明显的不一致,值得当成一个真实的坑记录下来:

```python
# src/openharness/autopilot/service.py
def _render_dashboard_html(self, snapshot: dict[str, Any]) -> str:
    """Return a minimal fallback HTML page.

    The primary dashboard is now a React + Vite app built from
    ``autopilot-dashboard/``.  This fallback is only written when
    no pre-built ``index.html`` already exists in the output
    directory, so local ``snapshot.json`` generation still works
    without a Node.js toolchain.
    """
```

docstring 说这个极简 fallback 页面"只有在输出目录里还没有预构建的 index.html 时才会被写入",但回头看上一节 `export_dashboard()` 的实现——`atomic_write_text(target_dir / "index.html", self._render_dashboard_html(snapshot))` 是无条件执行的,没有任何"目录里已经有 index.html 就跳过"的判断。也就是说,如果你在本地跑过 `cd autopilot-dashboard && npm run build` 产出了完整的 React 页面,之后任何一次会触发 `rebuild_active_context()` 的操作(哪怕只是 `oh autopilot scan issues` 扫到一个新 issue)都会把 `docs/autopilot/index.html` 静默替换回这个极简 fallback 页——`assets/*.js`/`*.css` 还在目录里,只是没人再引用它们了,页面直接从看板退化成一段"请自己去构建"的说明文字。这不是理论推演,是直接对照 docstring 与其调用方代码得出的真实不一致;遇到"刚构建完看板,过一会儿又变回了 fallback 页"的现象,原因就在这里,解法是重新跑一次 `npm run build`。

### 前端:autopilot-dashboard——第三种前端形态

`autopilot-dashboard/` 是一个完全独立的 React + Vite + TypeScript 项目,依赖极简:

```json
// autopilot-dashboard/package.json
{
  "dependencies": {
    "react": "^19.1.0",
    "react-dom": "^19.1.0"
  },
  "devDependencies": {
    "@types/react": "^19.1.2",
    "@types/react-dom": "^19.1.2",
    "@vitejs/plugin-react": "^4.4.1",
    "typescript": "~5.8.3",
    "vite": "^6.3.2"
  }
}
```

没有状态管理库、没有路由、没有图表库——`components/HeroBackground.tsx` 和 `components/PipelineAnimation.tsx` 里那些赛博朋克风格的背景网格、粒子和管道动画,全部用内联 SVG + SMIL 动画手写,零运行时依赖。这是一个刻意保持"能自己独立 `npm run build`、产物是纯静态文件"的项目边界。

`vite.config.ts` 的两个配置项直接决定了它的部署形态:

```typescript
// autopilot-dashboard/vite.config.ts
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../docs/autopilot",
    emptyOutDir: false,
  },
});
```

`base: "./"` 用相对路径而不是绝对路径引用资源,这样这份站点不管被 GitHub Pages 发布在 `username.github.io/`、还是某个项目的 `/reponame/` 子路径下,都不需要根据仓库名重新配置。`outDir: "../docs/autopilot"` 让前端构建产物直接写进后端 `export_dashboard()` 写快照的**同一个目录**——这正是"前后端通过一份 JSON 快照解耦"在文件系统层面的落地:Python 侧负责生产 `snapshot.json`(和兜底的 `index.html`/`.nojekyll`),Node 侧负责生产真正的 `index.html` 和带哈希的 `assets/*.js`/`*.css`,两边各自独立运行,共享的只是一个目录路径和一份 JSON 格式约定。`emptyOutDir: false` 同样是刻意的——Vite 默认构建前会清空 `outDir`,如果不关掉,每次前端重新构建都会先把后端刚写入的 `snapshot.json` 一并删除。

页面的数据加载逻辑同样是这个"零运维"哲学的延续:

```typescript
// autopilot-dashboard/src/App.tsx
useEffect(() => {
  fetch("./snapshot.json", { cache: "no-store" })
    .then((r) => r.json())
    .then(setSnapshot)
    .catch((e) => setError(String(e)));
}, []);
```

这不是轮询,也不是 WebSocket 订阅——它只在组件挂载时 `fetch` 一次,`cache: "no-store"` 只是确保这一次请求不会被浏览器 HTTP 缓存拦截拿到旧文件,并不会建立任何持续连接。换句话说,这个仪表盘的"实时性"边界很明确:打开或刷新页面才会看到最新状态,开着标签页挂在那里不会自动跳出新卡片。这正是它和第 02 章讲过的 Ink TUI/Textual 双前端截然不同的地方——那两套前端服务的是"有人正在终端里主动驱动、需要即时交互反馈"的场景;而 Autopilot 仪表盘是第三种前端形态,服务的是"没人在场时,任何人随时打开浏览器看一眼"的被动监控场景,选择用最朴素的静态站点 + 手动刷新去换取"不需要任何常驻服务、任何时候都能通过一个 URL 访问"这个更重要的属性。

### 前后端字段对照:一份 JSON,没有共享类型

`src/types.ts` 是前端对快照结构的类型声明:

```typescript
// autopilot-dashboard/src/types.ts
export interface TaskCard {
  id: string;
  title: string;
  body?: string;
  status: string;
  score: number;
  score_reasons?: string[];
  source_kind?: string;
  source_ref?: string;
  labels?: string[];
  updated_at?: number;
  metadata?: {
    last_note?: string;
    last_ci_summary?: string;
    last_failure_summary?: string;
    human_gate_pending?: boolean;
    verification_steps?: { status: string; command: string }[];
  };
}

export interface Snapshot {
  generated_at: number;
  repo_name: string;
  focus?: TaskCard;
  counts: Record<string, number>;
  status_order: string[];
  columns: Record<string, TaskCard[]>;
  cards: TaskCard[];
  journal: JournalEntry[];
}
```

拿它和后端 `_serialize_card()` 实际吐出来的字段对照,可以看出这不是一份严格的共享 schema,而是"前端只声明自己会用到的那部分"——`metadata` 在这里只列了 `last_note`/`last_ci_summary`/`last_failure_summary`/`human_gate_pending`/`verification_steps` 五个键,而后端真实吐出的 `metadata` 还有 `execution_model`、`attempt_count`、`max_attempts`、`linked_pr_number`、`linked_pr_url`、`last_ci_conclusion`、`last_failure_stage` 等一整批字段。TypeScript 的结构化类型不会因为对象里多出几个没声明的字段就报错,这些多余字段在前端只是被安静地忽略,不需要重新生成或同步一份共享类型定义,后端新增字段也完全不会破坏前端的编译。这是"用一份 JSON 快照当契约"这种松耦合集成方式的真实样子:宽进严出,前端挑自己认识的字段用,其余的字段就当作透明数据搬运过去,谁都不强制谁。

前端还在 `types.ts` 里定义了一层后端完全不知道的展示逻辑——`KANBAN_GROUPS`,把后端的十三种状态重新分组成四条看板列:

```typescript
// autopilot-dashboard/src/types.ts
export const KANBAN_GROUPS: KanbanGroup[] = [
  { key: "todo",        label: "To Do",       color: "#64748b", statuses: ["queued", "accepted"] },
  { key: "in_progress", label: "In Progress", color: "#00d4aa", statuses: ["preparing", "running", "repairing"] },
  { key: "in_review",   label: "In Review",   color: "#3b82f6", statuses: ["verifying", "pr_open", "waiting_ci"] },
  { key: "done",        label: "Done",        color: "#8b5cf6", statuses: ["completed", "merged", "failed", "rejected", "superseded"] },
];
```

后端只负责给出真实、细粒度的状态机(十三态),至于这些状态在 UI 上要不要合并展示、合并成几列、用什么颜色,完全是前端自己的决定,不需要后端为了"看起来更像一个 vibe-kanban 风格的四列看板"而改动自己的状态定义。`autopilot-dashboard/public/snapshot.json` 是一份和 `docs/autopilot/snapshot.json` 结构完全相同的空状态样例,供 `npm run dev` 本地开发时直接读取,不需要跑一个真实的 Python 后端就能看到页面骨架——这也印证了这套契约本身足够轻量,轻到可以直接复制一份 JSON 文件当 mock 数据用。

## 常见问题/易踩坑

- **构建好的仪表盘被静默还原成 fallback 页**:如上文所述,`export_dashboard()` 无条件重写 `index.html`,和 `_render_dashboard_html()` 的 docstring 描述不符。任何触发 `rebuild_active_context()` 的操作都会覆盖你手动 `npm run build` 出来的完整页面。规避方式是每次需要查看真实看板前都重新构建一次前端,或者在部署流程里把"跑 `oh autopilot ...`"和"跑 `npm run build`"接在同一条流水线里,构建步骤放在最后。
- **`emptyOutDir: false` 不是可选项**:如果去掉这个配置,`npm run build` 会先清空 `docs/autopilot/`,把后端刚写好的 `snapshot.json` 一并删掉,导致构建出来的页面打开就报 "Failed to load snapshot.json"。
- **页面不会自动刷新**:`App.tsx` 只在挂载时 `fetch` 一次,没有轮询也没有 `EventSource`。把这个仪表盘长期开在一个标签页里等着看新卡片是没用的,需要手动刷新页面。

## 小结

- Autopilot 的可观测性方案分三层:数据模型层(`types.py` 里的十三态 `RepoTaskCard` 状态机)→ 落盘与投影层(registry/journal/active_context 三份职责不同的文件,以及挂在每次状态变更之后、而非定时器上的 `export_dashboard()`)→ 前端消费层(独立的 React/Vite 静态站点,一次性 `fetch` 快照并自行分组渲染)。
- 这是本课程里第三种前端形态:不同于第 02 章服务"有人在场、主动交互"的 Ink TUI/Textual 双前端,Autopilot 仪表盘服务的是"无人值守、随时可能有人打开看一眼"的被动监控场景,用零运维的静态站点(GitHub Pages + `.nojekyll` + 一份 JSON)换取"不需要任何常驻服务"这一更重要的属性,代价是它不是实时推送,只是"最多落后一次状态变更"的轮询式快照。
- 前后端通过一份 JSON 快照解耦、而非共享类型定义,是这套系统里松耦合集成的一个具体样本:后端只管把真实状态如实序列化,前端只挑自己认识的字段消费,谁都不必因为对方的变化而被迫同步升级。

到这里,PI、DeepSeek Harness、Hermes Agent、OpenHarness 四套 Agent Harness 的核心机制已经逐层拆解完毕。下一章也是本课程最后一章,不再深入新的源码,而是把 OpenHarness 放回这几个姊妹项目的坐标系里做一次系统性对照,回顾它们在架构选择上的异同,并给出继续深入的延伸阅读方向。
