# Monorepo 依赖管理与构建测试流程

> hermes-agent 同时管理着一个 Python 包(`pyproject.toml` + `uv.lock`)和一个 npm workspaces
> (`package.json` 管理 `apps/*`、`ui-tui`、`web`、`tests-js`)。它的依赖管理策略里最值得学的不是"用了
> 哪个包管理器",而是围绕"供应链攻击"和"开发环境自毁"这两类真实事故形成的一整套工程约定——从
> `pyproject.toml` 里的精确版本锁定,到 `setup.py` 里干脆禁止普通人构建 wheel,再到 README 里那句
> "venv 必须建在仓库外面"的血泪教训。这些约定读起来像是"过度谨慎",但每一条背后都能找到具体动机。

## 学习目标

- 理解 `pyproject.toml` 里 `dependencies`(核心依赖)与 `optional-dependencies`(extras)的分层逻辑,
  以及为什么核心依赖要精确锁定到 `==X.Y.Z`。
- 读懂 Termux 平台为什么需要单独的 `.[termux]` extra 和 `constraints-termux.txt`。
- 理解 npm workspaces 在这个仓库里覆盖的是"前端矩阵"而不是"核心运行时"。
- 理解 `setup.py` 里那个"拒绝构建 wheel"的 guard 解决的是什么问题。
- 能解释"为什么 venv 要建在被 clone 的仓库之外"这条约定背后的具体故障模式。
- 知道 `scripts/run_tests.sh` 相对于裸调用 `pytest` 多做了哪些事,以及它为什么这么做。

## Python 侧依赖管理:uv + 精确锁定 + extras 分层

`pyproject.toml` 用 `uv` 作为包管理器,`requires-python = ">=3.11,<3.14"`。这个上界不是随意选的,
注释写得很清楚:

> Upper bound is load-bearing, not cosmetic. uv resolves the project's Python from `requires-python`,
> and an inherited `UV_PYTHON` env var (or a fresh distro whose newest interpreter uv auto-picks) will
> otherwise select 3.14, where Rust-backed transitives (e.g. pydantic-core) have no cp314 wheel yet and
> fall back to a maturin source build that fails.

也就是说:不封顶,uv 有可能自动选中一个连关键传递依赖都没有预编译 wheel 的 Python 版本,导致安装时
莫名其妙地本地编译失败。封顶让 uv 直接拒绝并报出清晰错误,而不是让用户去猜一个隐蔽的构建失败。

### 核心依赖:精确锁定到 `==X.Y.Z`

`[project].dependencies` 列表里几乎每一行都是 `包名==精确版本`,而不是常见的 `>=X.Y`。注释直接点出了
动机:

> Core — every direct dep is exact-pinned to ==X.Y.Z (no ranges). Rationale: ranges allow PyPI to ship
> a fresh version of a transitive at any time without a code review on our side. Exact pins mean the
> only way a new package version reaches a user is via an intentional update on our end... This was
> tightened on 2026-05-12 in response to the Mini Shai-Hulud worm hitting mistralai 2.4.6 on PyPI; if
> that release had been captured by `mistralai>=2.3.0,<3` rather than an exact pin, every install in
> the hours before the quarantine would have pulled it.

这条策略是从一次真实供应链投毒事件(Mini Shai-Hulud worm 命中 PyPI 上的 `mistralai` 包)倒推出来的:
如果当时用的是范围锁定,恶意版本发布后到被发现隔离之间的那几个小时内,所有新安装都会自动拉到那个带毒
版本;精确锁定则意味着"新版本只能通过我们主动改 pin + 重新生成 lockfile 才能进来"。

同一份 `dependencies` 列表里还有大量这类"这一行为什么存在"的行内注释,例如:

```python
"cryptography==50.0.0",  # CVE-2026-69247, GHSA-m2h6-j472-rp4c, GHSA-jwv3-5hgf-82ww, ...
"urllib3>=2.7.0,<3",     # 2.7.0 fixes GHSA-mf9v-mfxr-j63j / GHSA-qccp-gfcp-xxvc
```

以及一条"Scope rule"——决定一个包该不该进核心 `dependencies`:

> Scope rule: only packages used by EVERY hermes session belong here. Anything that's provider-specific
> (`anthropic`, `firecrawl-py`, `exa-py`, `fal-client`, `edge-tts`, `parallel-web`) belongs in an extra
> and gets lazy-installed via `tools/lazy_deps.py` when the user picks that backend. Smaller
> `dependencies` = smaller blast radius for the next supply-chain attack.

这条规则解释了为什么核心依赖列表相对精简:每加一个包到核心依赖,就是给"下一次供应链攻击"多开一个入口
——所以只有"每个会话都会用到"的包才配进核心,provider 专属的包一律走 extras + 运行时懒安装
(`tools/lazy_deps.py`)。

### `.[all]`、`.[termux]`:extras 的分层设计

`[project.optional-dependencies]` 里定义了几十个 extra,大致分三类:

1. **单一后端 extra**——`anthropic`、`exa`、`firecrawl`、`fal`、`modal`、`daytona`、`vercel`、`honcho`
   等,每个只在用户选中对应 provider/backend 时才需要,注释明确要求"deliberately excluded from
   `[all]`"以防某个不常用后端的上游包被投毒后拖累所有新装用户。
2. **聚合 extra**——`all` 把"每个会话都可能用到、且无法懒安装"的 extra 汇总起来:

   ```python
   all = [
     "hermes-agent[cron]", "hermes-agent[pty]", "hermes-agent[mcp]",
     "hermes-agent[homeassistant]", "hermes-agent[sms]", "hermes-agent[acp]",
     "hermes-agent[google]", "hermes-agent[web]", "hermes-agent[youtube]",
   ]
   ```

   注释里专门记录了"2026-05-12 从 `[all]` 移出了哪些 extra"(`anthropic`、`exa`、`matrix`、`voice` 等),
   理由之一很具体:`matrix` extra 拉的 `mautrix[encryption]` 依赖 `python-olm`,而 `python-olm` 只有
   Linux wheel、在 Windows/新版 macOS 上没有原生构建路径——留在 `[all]` 里会导致 Windows 上
   `uv sync --locked` 尝试从源码构建并因为 `make` 缺失而失败。
3. **平台专属 extra**——`termux` 和 `termux-all`,专为 Android/Termux 环境准备的精简集合:

   ```python
   termux = [
     "python-telegram-bot[webhooks]==22.8",
     "hermes-agent[cron]", "hermes-agent[mcp]",
     "hermes-agent[honcho]", "hermes-agent[acp]",
   ]
   ```

   README 里解释了为什么 Termux 不能直接用 `.[all]`:"the full `.[all]` extra currently pulls
   Android-incompatible voice dependencies"——语音相关依赖(`faster-whisper`、`sounddevice` 等)在
   Android/Termux 上没有可用的预编译 wheel,所以 Termux 走一条专门裁剪过的安装路径。配套的
   `constraints-termux.txt` 进一步给 `ipython`、`jedi`、`parso` 等间接依赖打了上限约束,注释写道
   "这些 pin 是为了在上游包比 Termux 兼容的 wheel 演进得更快时,保持已测试过的 Android 安装路径稳定"。

### `setup.py`:一个"拒绝构建"的构建守卫

`setup.py` 本身不是常规意义上的打包脚本,而是一个**主动拒绝**打包的 guard:

```python
"""
setup.py — wheel/sdist build guard.

pip/PyPI and Homebrew are no longer supported distribution methods for
Hermes Agent... This file overrides the ``bdist_wheel`` and ``sdist``
setuptools commands to raise an error when run outside a Nix build.
"""
_IN_NIX_BUILD = os.environ.get("HERMES_NIX_BUILD") == "1"
```

原因是 wheel 产物"会在没有那些运行时资源的情况下发布"——locales、skills、optional-mcps、
`web_dist`、`tui_dist`、插件 manifest 这些资源是在运行时通过 Nix wrapper 或者"源码 checkout 布局"
设置的环境变量解析出来的,普通 wheel 构建根本不会把它们打进去。唯一被允许的例外是 `uv2nix` 在 Nix
构建沙箱内部调用 `setuptools.build_meta.build_wheel`,这条路径由 `nix/python.nix` 设置
`HERMES_NIX_BUILD=1` 来放行。文档里特别强调:**可编辑安装(`uv sync`/`pip install -e .`)走的是
`build_editable`,不会触发 `bdist_wheel`**,所以这个 guard 完全不影响日常开发。这是一个很好的例子:
"构建脚本"不一定是用来构建的,也可以是用来**明确划定支持边界**的。

## Node 侧依赖:npm workspaces 覆盖前端矩阵,不覆盖核心运行时

根 `package.json` 是一个 `private: true` 的 npm workspaces 容器:

```json
"workspaces": ["apps/*", "ui-tui", "ui-tui/packages/*", "web", "tests-js"]
```

和 Python 侧"核心运行时 + 懒加载 provider"的结构不同,npm workspaces 在这里管理的是**四类前端产物**:
`apps/desktop`(Electron 桌面应用)、`apps/bootstrap-installer`(Tauri 安装器)、`apps/shared`(两者共享
代码)、`ui-tui`(及其内部子包)、`web`(仪表盘)、`tests-js`(前端测试)。`engines` 字段锁定
`"node": "^22.22.0 || ^24.11.0 || >=26.0.0"`,仓库根目录的 `.nvmrc` 进一步给出一个具体的开发时版本
建议,CI 里(见下一篇)统一用 Node 26。

`package.json` 里还有两处和供应链治理直接相关的字段:

- `overrides`——对特定包(如 `lodash`、`brace-expansion`、`postcss`、`tar`)强制锁定到某个版本,绕开
  传递依赖里可能引入的旧版本。
- `allowScripts`——显式允许/禁止某些包执行 install/build 脚本(`electron`、`node-pty`、`fsevents` 等
  需要原生构建的包被放行,`unicode-animations` 被显式拒绝),这与 Python 侧"默认最小可信面"的思路是
  一致的。

`scripts` 里的 `check`/`fix` 用 `npm run --ws` 对所有 workspace 广播执行,`install:web`/`install:tui`/
`install:desktop` 则允许只安装某一个子应用的依赖,不必每次都装全部前端矩阵。

## 开发环境搭建:为什么不建议裸 clone 到任意目录

README 和 `CONTRIBUTING.md` 都把"标准安装器生成的 full git checkout"作为**首选**的开发路径,而不是
"随手 `git clone` 到某个目录"。README 原文:

> Quick start for contributors — use the standard installer, then work from the full git checkout it
> creates at `$HERMES_HOME/hermes-agent` (usually `~/.hermes/hermes-agent`). This matches the layout
> used by `hermes update`, the managed venv, lazy dependencies, gateway, and docs tooling.

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
cd "${HERMES_HOME:-$HOME/.hermes}/hermes-agent"
uv pip install -e ".[all,dev]"
scripts/run_tests.sh
```

只有在"确实不想要 Hermes 的托管安装布局"(比如容器里的一次性 clone、CI job)时才走手动 clone 的
"fallback"路径。而这条 fallback 路径里,最值得记住的一条约定是:

> Create the venv **outside** the cloned source tree. A venv that lives inside the directory the agent
> operates from can be wiped by a relative-path command the agent runs against its own checkout
> (`rm -rf venv`, `uv venv venv`, etc.), which silently destroys the running runtime mid-session.
> Keeping it outside the tree means no relative path from the workspace resolves to it.

```bash
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent
uv venv ~/.hermes/venvs/hermes-dev --python 3.11   # 注意:在仓库之外
export VIRTUAL_ENV="$HOME/.hermes/venvs/hermes-dev"
export PATH="$VIRTUAL_ENV/bin:$PATH"
uv pip install -e ".[all,dev]"
npm install
```

这是一个非常值得作为教学案例的坑:Hermes 本身是一个会在自己的工作目录里执行终端命令的 Agent。如果
开发者图方便把 venv 建在被 clone 的仓库内部(`hermes-agent/venv`),那么当 Agent(在开发调试时)执行一条
类似 `uv venv venv` 或 `rm -rf venv` 的相对路径命令——即便这条命令的本意只是"重建一个不相关的
`venv/` 子目录"——也可能精确命中并删除自己正在运行所依赖的那个 venv,导致运行时在会话中途被自己的
命令悄悄摧毁。把 venv 放在仓库树之外,就切断了"工作区内任何相对路径都能解析到它"的可能性,这是一个
"环境隔离"而不是"代码隔离"的问题,普通的 `.gitignore` 规则完全防不住它。

## 测试运行:`scripts/run_tests.sh` 做了什么

`CONTRIBUTING.md` 明确要求"优先用这个脚本而不是裸调用 `pytest`,以保证本地行为和 CI 一致"。读脚本本身
(183 行),它至少做了以下几件事,每一件都在脚本注释里写明了动机:

1. **按文件隔离的并行测试**——通过 `scripts/run_tests_parallel.py` 把 pytest 拆成"每个测试文件一个
   全新 `python -m pytest <file>` 子进程",不用 `pytest-xdist`,也没有共享 worker,注释强调这样才能
   避免模块级状态在测试文件之间泄漏。
2. **venv 探测优先级**——依次探测 `.venv`、`venv`、`$HOME/.hermes/hermes-agent/venv`,并且不是"目录
   存在就选中",而是要求候选 venv 里**确实装了 `pytest`**:注释记录了一个真实故障——`~/.hermes/
   hermes-agent/venv`(生产/发布用的 venv)有 `bin/activate` 但没装 `pytest`,旧版本的"只看存在性"探测
   逻辑会误选中它,导致每个测试文件都以"No module named pytest"失败,而整体退出码是 1、却在粗看日志时
   显示"0 tests passed"这种看似无害实则是全红的输出。
3. **`env -i` 起一个"白名单式"干净环境**——`TZ=UTC`、`LANG=C.UTF-8`、`PYTHONHASHSEED=0` 保证确定性,
   同时用 `env -i` 清空继承的环境变量,只显式转发 `PATH`、`HOME`,以及一份**显式列出**的 Windows 定位
   变量(`USERPROFILE`/`LOCALAPPDATA`/`SYSTEMROOT` 等)和测试基础设施变量(`HERMES_TEST_IMAGE`/
   `HERMES_TEST_WORKERS` 等)。注释强调这是刻意做成显式白名单而不是通配符,"这样'没有任何凭证能泄漏'
   这条属性才能一眼审计出来"。
4. **预编译 `.pyc` 字节码缓存**——在启动约 2000 个测试子进程之前先跑一次
   `python -m compileall`,避免每个子进程各自重复编译同一批源码文件。

```bash
scripts/run_tests.sh                            # 全量
scripts/run_tests.sh -j 4                       # 限制并行度
scripts/run_tests.sh tests/agent/                # 只测某个目录
scripts/run_tests.sh tests/foo.py -k 'pattern'  # 路径 + 裸 pytest flag 混用
```

## 小结与思考题

hermes-agent 的依赖管理呈现出一条清晰的主线:**核心尽量小、尽量精确锁定,边缘尽量可选、尽量懒加载**。
Python 侧用"精确 pin + extras 分层 + `tools/lazy_deps.py` 运行时懒安装"应对供应链风险和平台兼容性问题
(Termux 是这套机制最典型的受益者);Node 侧用 workspaces 管理彼此独立的前端应用矩阵,而不触碰核心
运行时;`setup.py` 用一个"拒绝构建"的 guard 明确划定了"这个项目不走 PyPI/Homebrew 发布"的边界;
开发环境搭建则围绕"venv 不能被 Agent 自己的命令误删"这个具体故障模式,给出了"venv 建在仓库外"这条
反直觉但有据可查的约定。

1. 如果要新增一个只有部分平台需要的第三方 SDK 依赖,应该走"核心 `dependencies`"还是"extra +
   `tools/lazy_deps.py`"?判断标准是什么(提示:回看"Scope rule"那段引文)?
2. `constraints-termux.txt` 只约束了 `ipython`/`jedi`/`parso` 等几个包的上限,而不是给 Termux 单独
   维护一份完整的 `uv.lock`。这种"只覆盖已知会出问题的包"而非"整体重新锁定"的做法,相比维护一份完整
   平行 lockfile,多出了哪些风险、又省下了哪些维护成本?
3. 如果你在 `~/.hermes/hermes-agent` 之外手动 clone 了仓库、venv 也按规范建在了仓库外,但不小心把
   `VIRTUAL_ENV`/`PATH` 环境变量导出到了一个会话级别的 shell rc 文件里,而不是只在当前终端会话临时
   `export`——这会带来什么潜在问题?（提示:想想 `scripts/run_tests.sh` 里对 venv 的探测优先级。）
