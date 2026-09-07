# CI/CD 与供应链安全

> `.github/workflows/` 目录下有 29 个 workflow 文件,合计近 4400 行 YAML。这不是"堆砌检查项"式的
> 臃肿,而是一套刻意设计过的**编排(orchestrator)+ 按需触发(lane-gated)** 架构:一个 `ci.yaml` 统一
> 判断"这次改动碰了什么",再决定要不要唤起 Python 测试、前端测试、Rust 测试、Docker 构建、Nix 构建……
> 每一条 workflow 的注释都在解释"为什么是这样设计,而不是更简单的样子",这本身就是一份很好的
> CI 工程教材。

## 学习目标

- 理解 `ci.yaml` 作为编排器的设计:一次 `detect` 判定,多个 `workflow_call` 子工作流按条件触发。
- 认识多平台/多语言测试矩阵的划分逻辑:Linux 主测 + macOS/Windows 专属标记测试 + JS 测试 + Rust 测试。
- 理解两类供应链安全扫描(`supply-chain-audit.yml` 的模式扫描 vs `osv-scanner.yml` 的已知漏洞库比对)
  互补而不重复的分工。
- 理解 `skills-index-freshness.yml` 这类"针对生产环境自身产物的一致性看门狗"的设计,以及它和构建
  workflow(`skills-index.yml`)的分工关系。
- 了解 Docker 多阶段构建 + s6-overlay 的部署方式,以及 Nix flake 的模块化组织,并能说清两条部署路径
  分别解决什么问题。

## `ci.yaml`:一个"先分类、再按需调度"的编排器

`ci.yaml` 自己开头的注释就是最好的说明书:

> Orchestrator workflow. Runs `detect-changes` once, then conditionally calls the sub-workflows that a
> PR can actually affect... Sub-workflows are triggered via `workflow_call` and keep their own job
> definitions, matrices, and concurrency settings. They no longer have `push:`/`pull_request:` triggers
> of their own — everything flows through this file.

具体流程是:`detect` job 用一个本地 composite action(`./.github/actions/detect-changes`)跑
`scripts/ci/classify_changes.py`,产出一组布尔输出(`python`、`frontend`、`rust`、`docker_meta`、
`mcp_catalog`……),下游的 `tests`、`tests-os`、`lint` 等 job 各自读取对应的输出决定要不要跑:

```yaml
tests:
  name: Python tests
  needs: detect
  if: needs.detect.outputs.python == 'true'
  uses: ./.github/workflows/tests.yml
```

有一条设计原则贯穿整个 CI:**push 到 main 时分类器"失败即全开"(fail open)**——如果分类脚本本身出了
问题,宁可让所有 lane 都跑一遍,也不能因为分类误判而悄悄漏掉一次 post-merge 验证。这个"失败开放"策略
在 `nix.yml` 里被再次强调,并给出了一个具体理由:

> A `paths:` filter cannot gate this workflow correctly. The flake packages the product, and nine of
> the checks then run the built binary, so a change to `hermes_cli/` alone can fail `nix flake check`
> without touching one file under `nix/`.

也就是说,单纯按"改了哪些路径"做 `paths:` 过滤在这个仓库里是不可靠的——Nix 打包的是最终产物,Python
代码的改动完全可能间接影响到 Nix 构建出来的二进制行为,所以宁可用一个中心分类脚本统一判断,也不用
GitHub Actions 原生的 `paths:` 触发器各自为政。

安全边界上,`ci.yaml` 顶部专门写了一条 SECURITY 注释:

> this workflow runs PR-controlled actions, workflows, and code. Do not add `secrets: inherit` or
> GitHub App credentials here. Trusted main-only automation uses protected environments in its own
> workflows.

这是"外部贡献者的 PR 会触发这条流水线"这一现实倒推出的隔离原则——面向 PR diff 的 CI 绝不能拿到任何
可信凭据,可信的自动化(比如下面会讲到的技能索引构建、看门狗开 issue)必须放在**不受 PR 触发**的独立
workflow 里,并且显式声明 `environment: trusted-automation`。

## 多平台/多语言测试矩阵

CI 把测试拆成了按"平台特异性"和"语言"两个维度组织的若干条 lane:

- **`tests.yml`**——Linux 主测试(`ubuntu-latest-96-core`),覆盖平台无关和 Linux 特有的逻辑。
- **`tests-os.yml`**——macOS 和 Windows 专属测试。它的存在理由写得很直白:

  > Tests whose subject is macOS- or Windows-specific behaviour carry a marker... and are SKIPPED on
  > Linux, because faking `sys.platform` on a Linux runner selects the branch under test without
  > reproducing any of the OS behaviour that branch exists for.

  也就是说,在 Linux 上 mock `sys.platform == "win32"` 只能让被测分支被选中执行,却完全无法复现
  Windows 真实的路径分隔符、权限模型、控制台编码等行为差异——这类测试必须在真实的目标系统上跑。矩阵
  是:

  ```yaml
  matrix:
    include:
      - name: macOS-only tests
        runner: macos-latest
        marker: macos_only
      - name: Windows-only tests
        runner: windows-latest-32-core
        marker: windows_only
  ```

  这个 workflow 还有一条"零测试即失败"的自我保护:"Each lane FAILS when it selects zero tests (pytest
  exit code 5)"——如果某次标记(marker)改名或选择器写错导致实际选中零个测试,`pytest` 会以状态码 5
  退出,而不是"跑了 0 个测试、报告绿色",防止静默的覆盖率丢失被误判为通过。
- **`js-tests.yml`**——前端测试,`ubuntu-latest-32-core` 上跑,Node 版本锁定 26(与仓库 `package.json`
  的 `engines` 字段一致)。
- **`rust-tests.yml`**——`cargo test`,专门针对 `apps/bootstrap-installer/src-tauri` 这个 Tauri
  安装器的 Rust 代码。它存在的理由本身就是一个真实的"CI 盲区"故事:

  > Nothing in CI compiled this crate before: `.rs` lives under `apps/`, so the change classifier
  > matched it as `frontend` and ran the TypeScript matrix, which cannot notice a Rust error. The
  > crate's unit tests existed in the tree and had never run.

  换句话说,在这条 workflow 出现之前,`.rs` 文件因为物理上位于 `apps/` 目录下,被变更分类器归类成了
  "frontend",触发的是 TS 矩阵——TS 的 lint/test 完全不会理解 Rust 语法,导致这部分测试代码**存在于
  仓库里但从未真正被执行过**。这条 workflow 还特别选择在 Linux runner 上跑而不是 Windows,因为
  `src/powershell.rs` 里管道排空的测试需要真实的进程树、且标了 `#[cfg(unix)]`,Windows 侧的等价覆盖
  则通过 PowerShell 脚本里的 `-SelfTestPipeDrain` 自检来实现——"一个 Windows runner 会把这些测试直接
  编译掉,报告绿色却是零覆盖"。

## 供应链安全:两道互补的扫描

`supply-chain-audit.yml` 和 `osv-scanner.yml` 覆盖的是同一个大问题的两个不同侧面。

**`supply-chain-audit.yml`** 是"窄而高信号"的模式扫描,专门找恶意代码特征(比如 litellm 投毒事件那种
payload)。它的注释记录了一次自我纠偏:

> Low-signal heuristics (plain base64, plain exec/eval, dependency/Dockerfile/workflow edits, Actions
> version unpinning, outbound POST/PUT) were intentionally removed — they fired on nearly every PR and
> trained reviewers to ignore the scanner.

也就是说,早期版本里那些"宽泛"的检测规则(比如"检测到 base64"、"检测到 exec/eval")几乎每个 PR 都会
命中,结果是训练审查者养成了"看到这个扫描器报警就无视"的坏习惯——一个报警泛滥的安全工具,长期效果
等于没有工具。所以现在故意收窄到"只保留高置信度的关键模式",并且明确要求"如果你发现自己又想往这里加
WARNING 级别的规则,应该另开一个纯咨询性质的 workflow,而不是往这里塞"。

**`osv-scanner.yml`** 则是完全不同的思路:扫描 `uv.lock`、`package-lock.json` 里当前锁定的具体版本,
拿去和 OSV(Open Source Vulnerability)漏洞数据库比对已知 CVE。注释说明它和上一个 workflow 的分工:

> Complements the supply-chain-audit.yml workflow (which scans for malicious code patterns in PR
> diffs) by covering the orthogonal "currently-pinned dep became known-vulnerable" case.

它是纯检测性质,`fail-on-vuln` 被禁用——即便扫出已知漏洞也不会直接挡住合并,因为已锁定依赖的漏洞可能
需要团队按自己的节奏主动升级,而不是被扫描器强制阻断。触发方式除了每次 PR/push,还有每周一次针对
`main` 的定时扫描(`cron: '0 9 * * 1'`),用来捕捉"依赖没有变化,但漏洞是在合并之后才被公开"的情况。

## `skills-index-freshness.yml`:面向生产产物本身的一致性看门狗

这是一个很值得展开的案例,因为它体现了"CI 不只服务于 PR,也可以服务于线上产物"这个思路。要理解它,
需要先看它的搭档 `skills-index.yml`:

- `skills-index.yml` 每天 UTC 6 点和 18 点跑一次 `scripts/build_skills_index.py`,重新扫描技能来源
  (skills.sh、LobeHub、ClawHub、官方来源、GitHub、browse.sh 等),生成
  `website/static/api/skills-index.json`,再触发 `deploy-site.yml` 把新索引发布到线上文档站。
- `skills-index-freshness.yml` 则每 4 小时探测一次**线上已发布**的
  `https://hermes-agent.nousresearch.com/docs/api/skills-index.json`,检查三类问题:索引年龄是否超过
  26 小时("If the live ... index ever goes more than 26 hours stale")、`skills` 字段是否是合法的
  JSON 列表、以及各来源的技能数是否低于预设下限(比如 `skills.sh` 不低于 100、`github` 不低于 30)。
  一旦探测到"stale / parse-failed / invalid-shape / degraded"中的任意一种,就用 GitHub App token 开一
  个标题带 `[skills-index-watchdog]` 前缀的 issue(如果已有同前缀的 open issue,就追加评论而不是重复
  开新 issue,避免刷屏)。

这套设计的价值在于把"技能索引是否新鲜、是否完整"这件本来只能靠人偶然发现的事,变成了一个**主动巡检、
自动报警**的闭环——技能索引的构建 workflow 本身即使跑成功了,也不能保证它按时触发、或者产出的内容
真的健康(比如某个上游数据源批量下线导致某个来源的技能数骤降),freshness 看门狗补上的正是"构建成功
不等于线上产物健康"这一层。它不是一个会挡住 PR 合并的 CI 门禁,而是一个独立于 PR 生命周期、面向线上
状态持续巡检的自动化——这提示我们:CI/CD 里"一致性检查"的对象不必局限于代码本身,任何一个自动生成、
需要保持新鲜的产物,都值得配一个这样的看门狗。

## Docker 部署:多阶段构建 + s6-overlay 监督树

`Dockerfile` 用多阶段构建把"编译期依赖"和"运行期镜像"分开,例如专门起一个 `sqlite_build` 阶段从源码
编译一份修过 WAL 重置 bug 的 SQLite(注释解释 Debian 13 自带的 3.46.1 版本有已知损坏问题),再用
`COPY --from=` 把编译产物拷进最终镜像,避免运行时镜像携带整套编译工具链。

运行时用的是 `s6-overlay` 监督树而不是简单的 shell 脚本或 `tini`。`docker/entrypoint-dispatch.sh`
处理了一个不算罕见的边界情况——容器不一定拥有 PID 1:

```sh
if [ "$$" -eq 1 ]; then
    exec /init /opt/hermes/docker/main-wrapper.sh "$@"
fi
echo "[hermes] WARNING: container entrypoint is not PID 1; skipping s6-overlay /init ..." >&2
```

在 Fly Machines、`docker run --init`、部分 Nomad/K8s 环境下,平台自己的 init 已经占据了 PID 1,
`s6-overlay` 的 `/init` 在这种情况下会直接报错拒绝运行——这个脚本检测到这一情况后,退化为"跳过完整的
监督树,直接跑 `stage2-hook.sh` 做一次性引导,再 `exec` 主程序",牺牲了服务监督能力但保证容器仍然能
启动。`docker/stage2-hook.sh` 以 root 身份运行,负责 UID/GID 重映射、数据卷 chown、配置播种,并明确
拒绝了一种曾经常见但现在不再受支持的用法——`docker run --user $(id -u):$(id -g)`:

> Under s6-overlay this no longer works: the bootstrap (UID remap, data-volume ownership, config
> seeding) requires root, and it is skipped when the container starts non-root... An arbitrary `--user`
> UID therefore cannot repair or populate the data volume, and startup fails with EACCES.

`docker-compose.yml` 把这一整套约定封装成 `HERMES_UID`/`HERMES_GID` 两个环境变量,并在注释里给出了
明确的安全提示——dashboard 默认只绑定 `127.0.0.1`,如果要暴露到公网必须自己加认证反代,而不是直接
`--host 0.0.0.0`。`.hadolint.yaml` 则记录了几条**有意保留**的 lint 豁免及其理由,比如"不锁定
`apt-get install` 里常见工具版本"是为了让安全更新能随基础镜像的定期重建自动流入,而不是被锁死在过时
补丁版本上。

## Nix 打包:声明式、可复现的另一条路径

`flake.nix` 用 `flake-parts` 组织,依赖 `pyproject-nix` + `uv2nix` 把 `pyproject.toml`/`uv.lock`
直接翻译成 Nix 派生(而不是维护一份平行的 Nix 依赖描述)。`nix/` 目录下的模块按职责拆分得很清楚:

| 文件 | 职责 |
|---|---|
| `hermes-agent.nix` | 可被 `.override` 的核心包定义(Python 版本、可选依赖组等) |
| `devShell.nix` | 开发 shell——委托每个 npm workspace 包自行声明 `passthru.packageJsonPath`,统一跑一次 `npm ci` |
| `sandbox.nix` | Electron 运行所需的系统库集合(`alsa-lib`、`at-spi2-atk`、`dbus`、`gtk3` 等) |
| `nixosModules.nix` | NixOS 系统级模块——系统用户、状态目录、可选的 OCI 容器模式 |
| `homeManagerModules.nix` | Home Manager 用户级模块——"Hermes 是面向单个使用者的 agent,凭据/记忆/会话/cron 都属于这个人",所以用户级模块在非 NixOS 发行版上同样适用 |
| `moduleCommon.nix` | 前两个模块共享的选项定义和 config.yaml/`.env` 渲染逻辑 |
| `python.nix` / `web.nix` / `tui.nix` | 各语言子系统各自的 Nix 构建逻辑 |
| `checks.nix` | `nix flake check` 跑的一组 checks(模块求值、选项一致性、`.env` 组装、服务 argv 等) |

`nixosModules.nix` 和 `homeManagerModules.nix` 共享 `moduleCommon.nix` 里的选项定义,只在"要不要 root
权限"这一点上分叉——NixOS 模块多出系统用户创建、容器模式;Home Manager 模块则去掉这些系统级关注点,
换来"可以在任何发行版、以普通用户身份运行"的能力。

**Docker 与 Nix 的对比**可以概括为:Docker 方案提供的是"容器化隔离 + 运行时可变状态挂载",适合"我只
要一个能跑起来的镜像",部署单元是镜像层;Nix 方案提供的是"声明式、可从源码完全复现的整个系统状态"
(包依赖、systemd/launchd 服务定义、配置文件渲染都在同一份 flake 里声明),适合"我要把 Hermes 的整个
运行环境纳入我机器/服务器的声明式配置管理",部署单元是 Nix store 里的派生 + 一份可 diff 的模块配置。
两者不是互斥的选择——`nix/python.nix` 甚至可以在 Nix 沙箱内部驱动前面提到的 `setup.py` guard 走
`HERMES_NIX_BUILD=1` 那条合法路径,而普通 Docker 镜像构建走的是完全不同的编译方式(直接用 `uv sync`
装可编辑环境,再把整个目录连同资源一起打进镜像)。

`.coderabbit.yaml` 里还有一个和"信噪比"相关的治理细节,和前面 `supply-chain-audit.yml` 收窄规则是
同一种精神:仓库组织级别开启了 CodeRabbit 自动审查后,这个仓库主动把它**关掉**了,理由是"这个仓库的
合并门槛是 CI 全绿 + 维护者人工评审,CodeRabbit 的评论不计入合并权重,对全量 PR 自动开火只会增加评论
噪音而没有门禁价值",但保留了按需 `@coderabbitai review` 手动召唤的能力。

## 小结与思考题

hermes-agent 的 CI/CD 体系呈现出三个反复出现的设计原则:**用一个中心分类器代替分散的路径过滤**(
`ci.yaml`/`nix.yml` 的 `detect` job,失败即全开),**每一类检测都要窄而高信号**(supply-chain-audit
从"宽泛的低信号规则"收窄回"高置信度关键模式",CodeRabbit 从"全量自动审查"收窄回"按需召唤"),
**部署/发布路径的正确性本身也要被测试覆盖**,而不只是"能跑起来就行"(rust-tests.yml 补上了此前从未
真正执行过的 Rust 单测,tests-os.yml 用真实平台跑平台专属行为,skills-index-freshness.yml 巡检的是
线上产物而不是代码本身)。

1. 如果要新增一条只在" `docker/` 目录下文件变化"时才需要跑的 workflow,直接用 GitHub Actions 原生的
   `on.pull_request.paths` 触发器是否合适?结合 `nix.yml` 里那条"paths 过滤在这个仓库不可靠"的论证,
   你会怎么设计这条触发规则?
2. `osv-scanner.yml` 检测到已知 CVE 后不会阻断合并(`fail-on-vuln` 关闭)。这与 `supply-chain-audit.yml`
   对"高置信度恶意模式"零容忍形成了对比。这种"已知漏洞可以按节奏处理,但可疑代码模式必须立刻拦截"的
   分级策略,背后的风险判断依据是什么?
3. 如果你要给"MCP 目录条目一致性"(`optional-mcps/` 下每个目录是否都在某个索引文件里被正确登记)设计
   一条类似 `skills-index-freshness.yml` 的看门狗,你会选择"探测线上已发布产物"还是"直接在 PR 里比对
   仓库当前状态"?两种方案分别能捕捉到什么、又分别会漏掉什么?
