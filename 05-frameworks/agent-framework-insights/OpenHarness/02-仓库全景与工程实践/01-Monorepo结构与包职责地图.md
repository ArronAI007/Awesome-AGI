# Monorepo 结构与包职责地图

> OpenHarness 的仓库不是一个"多包 workspace",而是**一个 Python 发行包里塞进一整套职责簇**——`src/openharness/` 下 30 个子包共用同一个 `pyproject.toml`、同一条 CI 流水线、同一个版本号,真正意义上"独立"的只有一件事:`ohmo` 这个个人 Agent App 被物理地放在 `src/` 之外、和 `openharness` 并列,用 `pyproject.toml` 里"两个顶层包一起打进一个 wheel"这个不起眼的配置项,说明了它和 `openharness` 之间是依赖关系,而不是从属关系。理解这条边界,是读懂后面三篇(双前端、配置体系、测试策略)的地图。

## 学习目标

- 弄清楚 OpenHarness 为什么没有采用类似 pnpm workspace 那种"一堆可独立发布小包"的монорепо 策略,而是把几乎全部逻辑塞进一个 Python 包。
- 能把 `src/openharness/` 下的 30 个子包按"职责簇"归类,而不是死记硬背 30 个目录名。
- 通过 `pyproject.toml` 的 `packages = ["src/openharness", "ohmo"]` 读懂 `ohmo` 与 `openharness` 的真实关系:结构独立、依赖单向、但留了几处"可选回调"的软耦合。
- 认识 `frontend/terminal/`、`autopilot-dashboard/` 这两个独立 npm 项目是如何被"打包进"或"部署到"Python 项目周边的,而不是用 JS workspace 工具统一管理。
- 知道 `channels/impl` 和 `channels/bus` 这两个目录背后其实是从别的开源项目同步进来的代码,以及仓库是怎么记录这件事的。

## 背景与设计动机

如果你读过本系列关于 DeepSeek Harness 的第 02 章,会记得那是一个把代码拆成 **219 个可独立发布叶子包**的 Monorepo——因为它是 TypeScript/npm 生态,`pnpm workspace` 天然支持"能力座与实现分离"这种细粒度包边界,而且 Cordis 插件体系要求每个能力都能被独立注入、独立替换。

OpenHarness 面对的是完全不同的约束。它的定位是"Claude Code 的开源 Python 复刻",发行物是**一个** PyPI 包(`openharness-ai`),用户用 `pip install` 或 `uv tool install` 装一次,拿到 `oh`/`openharness`/`openh` 三个等价命令。把内部逻辑拆成几十个独立发布的 pip 包,对这个目标没有任何好处——这些子包从来不会被仓库之外的任何人单独 `pip install`,拆分只会带来几十份 `pyproject.toml`、几十条版本号需要同步的维护成本,却换不来"独立替换实现"的收益,因为 Python 的模块系统本身就足够表达"一个包内部按目录分层"这件事,不需要借助包管理器的边界。

于是 OpenHarness 选择了一条更朴素的路线:**一个 Python 包,内部用近 30 个子包按职责分层**,用目录边界而不是发布边界来管理内聚与耦合。真正值得"物理独立"的东西只有一处——`ohmo`,一个基于 OpenHarness 构建、通过 Feishu/Slack/Telegram/Discord 对话来干活的个人 Agent App。它不是 `openharness` 的一个子模块,而是仓库根目录下与 `src/` 并列的另一个顶层目录,`pyproject.toml` 用 `[tool.hatch.build.targets.wheel] packages = ["src/openharness", "ohmo"]` 把它们分别列成两个打包单元——这行配置本身就是全篇最重要的线索。

## 核心机制详解

### 一份 pyproject.toml,两个打包单元

仓库顶层没有 `frontend/terminal/pyproject.toml`、没有 `ohmo/pyproject.toml`,构建体系的全部真相都在根 `pyproject.toml` 里:

```toml
# pyproject.toml
[project.scripts]
openharness = "openharness.cli:app"
oh = "openharness.cli:app"
openh = "openharness.cli:app"
ohmo = "ohmo.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/openharness", "ohmo"]
```

四个命令行入口里,前三个(`openharness`/`oh`/`openh`)其实是同一个 Typer `app` 对象的三个别名——纯粹是给用户提供好记的短命令,不是三套不同的 CLI。第四个 `ohmo` 才是另一套体系,指向 `ohmo.cli:app`。而 `packages` 字段把 `src/openharness` 和 `ohmo` 列为两个平级的打包根:hatchling 会把它们分别当作独立的顶层 Python 包塞进同一个 wheel 里,而不是把 `ohmo` 当成 `openharness` 的子包处理。

这意味着物理目录结构上,`ohmo/` 和 `src/openharness/` 是兄弟,不是父子:

```text
OpenHarness/
├── src/
│   └── openharness/     # 30 个子包,发布为顶层包 `openharness`
└── ohmo/                 # 独立目录,发布为顶层包 `ohmo`
    ├── cli.py
    ├── gateway/
    ├── runtime.py
    └── ...
```

验证这一点最直接的方式是看 `ohmo/` 内部怎么引用 `openharness`——它是普通的跨包导入,而不是相对导入:

```python
# ohmo/cli.py
from openharness.auth.manager import AuthManager
from openharness.config import load_settings
```

```python
# ohmo/runtime.py
from openharness.ui.backend_host import run_backend_host
from openharness.ui.runtime import build_runtime, close_runtime, handle_line, start_runtime
from openharness.ui.react_launcher import _resolve_npm, _resolve_tsx, get_frontend_dir
```

`ohmo` 几乎把 `openharness.ui`、`openharness.engine`、`openharness.memory`、`openharness.services` 这些子包当作一个正常的第三方依赖来使用:复用 UI 运行时驱动对话循环,复用会话存储和记忆系统,复用鉴权管理器。这才是"依赖关系而非从属关系"的真正含义——`ohmo` 不是 `openharness` 里长出来的一个功能分支,而是构建在 `openharness` 之上的**另一个产品**,只是目前两者共享同一份 `pyproject.toml`、同一次 `uv sync`、同一个 wheel,还没有真正拆成两个可以分别安装的发行包。

### 反方向:openharness 对 ohmo 的"软依赖"

如果依赖方向是单向的,`src/openharness/` 里不应该出现任何 `import ohmo`。但实际搜索会发现三处例外,而且都用同一种防御性写法处理:

```python
# src/openharness/services/cron_scheduler.py
try:
    from ohmo.gateway.config import load_gateway_config
except Exception:  # pragma: no cover - ohmo is optional for non-ohmo cron users
    ...
```

```python
# src/openharness/channels/impl/base.py
ohmo_workspace = os.environ.get("OHMO_WORKSPACE")
if ohmo_workspace:
    from ohmo.workspace import get_attachments_dir
    root = get_attachments_dir(ohmo_workspace)
```

```python
# src/openharness/channels/impl/feishu.py
def _is_ohmo_managed_feishu_group(chat_id: str) -> bool:
    try:
        from ohmo.group_registry import load_managed_group_record
    except Exception:
        logger.exception("Failed to load ohmo managed Feishu group metadata chat_id=%s", chat_id)
```

三处全部是**函数内部的延迟导入 + 异常吞掉**,而不是模块顶层的硬依赖,注释里也直接写明"ohmo is optional for non-ohmo cron users"。这揭示了一个更准确的依赖模型:`openharness` 单独运行时完全不需要 `ohmo` 存在;但 `openharness` 的 cron 调度器和 Feishu 频道适配器留了几个"如果 ohmo 恰好也装在同一环境里,就顺便增强一下行为"的钩子——比如识别哪些飞书群是 ohmo 托管的群、往 ohmo 的工作区目录里找附件。这是一种刻意设计的单向耦合:结构上 `ohmo` 依赖 `openharness`,运行时 `openharness` 对 `ohmo` 的存在保持"知道但不依赖"的态度,靠 `try/except` 把可选集成和核心功能解耦开。

### src/openharness 内部:按职责簇理解 30 个子包

`src/openharness/` 下的 30 个目录、约 4.6 万行代码,如果按字母序或目录名死记会很难建立直觉。更有效的方式是按它们在一次对话里实际扮演的角色分组:

**核心循环簇**——驱动一次"用户输入 → 模型调用 → 工具执行 → 输出"的主链路:

| 子包 | 一句话职责 |
|---|---|
| `engine` | Agent 核心循环与流式事件(`AssistantTextDelta`、`ToolExecutionStarted` 等) |
| `api` | 对接 Anthropic / Codex / OpenAI 兼容接口的客户端封装 |
| `auth` | 统一鉴权管理:API Key、浏览器登录、设备码登录三种 Flow |
| `prompts` | 系统提示词组装,加载 `CLAUDE.md`/`AGENTS.md` 之类的项目上下文 |
| `commands` | 斜杠命令注册表 |

**工具与扩展簇**——模型能调用什么、能力如何被外部扩展:

| 子包 | 一句话职责 |
|---|---|
| `tools` | 44 个内置工具实现(文件读写、bash、grep/glob、MCP、任务、子代理等) |
| `skills` | Agent Skill 的发现与加载 |
| `plugins` | 插件系统 |
| `mcp` | MCP 客户端集成,把外部 MCP Server 的工具接入 `tools` |
| `hooks` | 拦截点上的 hook 执行(等价于 Claude Code hooks) |

**治理簇**——约束模型能做什么、在哪做:

| 子包 | 一句话职责 |
|---|---|
| `permissions` | 权限模式(Default / Plan / Full Auto)与工具审批 |
| `sandbox` | 沙箱适配层(本地、Docker 等后端) |

**记忆簇**——跨会话的知识沉淀:

| 子包 | 一句话职责 |
|---|---|
| `memory` | 项目/用户记忆文件的加载与管理 |
| `personalization` | 从会话历史里自动提取"本地规则"做个性化 |

**多智能体簇**——一个会话如何变成多个协作的 Agent:

| 子包 | 一句话职责 |
|---|---|
| `swarm` | Teammate 后端抽象:进程内、子进程、worktree 隔离 |
| `coordinator` | Coordinator 模式与内置 Agent 定义、团队注册表 |
| `bridge` | 桥接会话管理(跨进程会话的生命周期) |
| `tasks` | 后台任务(本地 Agent 任务、Shell 任务)的派发与追踪 |

**交互簇**——人和 Agent 之间的界面层:

| 子包 | 一句话职责 |
|---|---|
| `ui` | React/Ink 前端与 Textual 前端的 Python 侧运行时(第 02 篇主题) |
| `output_styles` | 输出风格加载 |
| `themes` | 终端主题系统 |
| `keybindings` | 快捷键绑定 |
| `vim` | Vim 模式切换 |
| `voice` | 语音输入(关键词提取、流式语音转文字) |

**多平台簇**——把 Agent 接到聊天平台上:

| 子包 | 一句话职责 |
|---|---|
| `channels` | 消息总线架构,对接 Telegram/Discord/Slack/飞书等 |
| `services` | 会话存储、压缩、cron 调度、LSP、内存提取等后台服务 |

**可观测簇**——仓库自己的自动化运维:

| 子包 | 一句话职责 |
|---|---|
| `autopilot` | 项目级自动巡检/排期状态机,配合 `.github/workflows/autopilot-*.yml` 定时扫描仓库、执行任务、导出仪表盘 |

这套分组不是仓库里写死的分类(OpenHarness 没有像 DeepSeek Harness 那样的一级/二级目录),而是从 `__init__.py` 的模块级 docstring 和实际依赖关系里读出来的——比如 `channels/__init__.py` 明确写着"Provides a message-bus architecture for integrating chat platforms ... with the OpenHarness query engine",`autopilot/__init__.py` 是"Repo autopilot exports"。按簇理解的好处是:当你要新增一个工具时,知道去 `tools/` 找同类实现参考、去 `permissions/` 确认它要不要走审批;当你要接入一个新聊天平台时,知道 `channels/impl/` 是适配器该落地的地方,`services/cron_scheduler.py` 是和 `ohmo` 软耦合的那一层。

### channels 内部的"迷你 vendor 目录"

`src/openharness/channels/` 下有一个不起眼但值得单独拎出来的细节——`UPSTREAM` 文件,记录了这个子包里两个目录是从别的开源项目同步过来的:

```text
# src/openharness/channels/UPSTREAM
repo: https://github.com/nanobot-ai/nanobot
commit: 473ae5ef18394ab839a3364eee66836ef9776902
synced: 2026-04-05T00:00:00Z
paths:
  nanobot/bus/     -> src/openharness/channels/bus/
  nanobot/channels/ -> src/openharness/channels/impl/
```

这是 DeepSeek Harness 课程里"`vendor/*` 顶层目录、source-vendored 框架层"那套思路的一个缩微版:OpenHarness 没有专门开一个顶层 `vendor/` 目录,而是直接在 `channels/` 内部划出 `bus/` 和 `impl/` 两个子目录,把上游 `nanobot-ai/nanobot` 项目里"消息总线"和"频道适配器"的实现原样同步进来,并用一个纯文本文件记录源仓库、commit hash、同步时间和路径映射——这样未来要跟上游同步更新时,知道该 diff 哪个 commit、覆盖哪些路径。这提醒读者一件事:**并不是每一行 `channels/` 下的代码都是 OpenHarness 团队原创的**,`bus/` 和 `impl/` 是刻意标注过来源的移植代码,而 `channels/adapter.py` 这一层才是 OpenHarness 自己写的"把 nanobot 的频道概念接进 OpenHarness query engine"的胶水代码。

### frontend/terminal 与 autopilot-dashboard:两个独立的 npm 项目

仓库里还有两个完全独立于 Python 打包体系的前端项目,它们既不是 npm workspace 成员,也没有互相引用:

- **`frontend/terminal/`**——`package.json` 里 `"private": true`,依赖 `ink`、`react`、`ink-text-input`、`marked`、`string-width`,不作为 npm 包发布,而是被 `pyproject.toml` 的 `force-include` 规则原样打进 Python wheel(下一篇细讲这条链路)。
- **`autopilot-dashboard/`**——一个独立的 React + Vite 项目,`.github/workflows/autopilot-pages.yml` 会在 `docs/autopilot/**` 或它自身变化时触发,`npm run build` 后部署到 GitHub Pages,用来可视化 `autopilot` 子系统扫描出的仓库巡检状态。

这两个前端项目没有共享的 `package.json`、没有 lerna/turborepo/pnpm workspace 之类的工具统一管理,是彻底独立的两个 Node 项目,分别通过"打进 Python wheel"和"部署到 GitHub Pages"这两条完全不同的路径融入这个仓库,而不是被当作 monorepo 里的普通成员对待。

### scripts 与 tests:两条不同气质的验证路径

顶层还有 `scripts/`(约 3200 行)和 `tests/`(约 27100 行,103 个测试文件)。这两者不是简单的"脚本"和"测试"关系——`scripts/` 下有一半是需要真实模型 API Key 才能跑的端到端脚本(`test_harness_features.py`、`test_real_skills_plugins.py`、`test_docker_sandbox_e2e.py` 等),`tests/` 下也混入了几个同样依赖真实 API 的大型集成测试(`test_untested_features.py`、`test_real_large_tasks.py`)。这套分层测试策略是第 04 篇的主题,这里先记住一点:**文件放在 `scripts/` 还是 `tests/`,不能简单等同于"是脚本"还是"是单元测试"**。

## 常见问题/易踩坑

- **不要把 `ohmo/` 误认为 `openharness` 的子模块**:它没有 `openharness.ohmo` 这样的导入路径,始终是顶层包 `ohmo`,`import ohmo.cli` 而不是 `from openharness import ohmo`。
- **`src/openharness/` 里出现 `from ohmo import ...` 不是循环依赖 bug**:这三处都在函数体内、都包了 `try/except`,是刻意设计的可选集成点,不影响 `openharness` 单独安装运行。
- **`channels/bus/` 和 `channels/impl/` 改动前先看 `UPSTREAM` 文件**:这两个目录是从 `nanobot-ai/nanobot` 同步来的,直接大改容易在下次同步上游时产生难以合并的漂移。

## 小结

OpenHarness 用"一个 Python 包 + 近 30 个按职责簇划分的子包"取代了细粒度多包 Monorepo,把内聚边界收敛到目录层面;唯一被拆成物理独立顶层包的是 `ohmo`,`pyproject.toml` 里"两个包一起打进一个 wheel"这行配置,精确刻画了它和 `openharness` 之间"结构独立、单向依赖、局部软耦合"的关系。`frontend/terminal/` 和 `autopilot-dashboard/` 则展示了两种截然不同的"前端如何融入 Python 仓库"的路径。下一篇会拆开这个仓库工程实践里最有特色的一个选择——为什么核心逻辑是纯 Python,主力交互界面却是一个用 Ink/React 写的 TypeScript 子进程,以及 Python 后端和这个跨语言前端之间到底靠什么协议对话。
