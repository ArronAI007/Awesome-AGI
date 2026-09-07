# 快速开始:CLI 与 Gateway 速览

> Hermes 有两个入口——`hermes` 启动终端交互,`hermes gateway` 启动消息网关——但它们背后是同一个 Agent、同一套 slash 命令。本篇先建立"两个入口、一套核心"的心智模型,细节留给第 09、10 章。

## 学习目标

- 理解 `hermes`（交互式 CLI/TUI）与 `hermes gateway`（消息网关）两个入口的关系与区别
- 能跑通一次典型的终端对话,认识几个最常用的 slash 命令
- 认识 `hermes model`、`hermes tools`、`hermes config`、`hermes setup`、`hermes doctor` 这几个顶层子命令的分工
- 知道去哪里查完整的命令列表,而不是死记文档

## 两个入口,一套核心

根目录 README 用一句话概括了 Hermes 的入口设计:

> Hermes has two entry points: start the terminal UI with `hermes`, or run the gateway and talk to it from Telegram, Discord, Slack, WhatsApp, Signal, or Email. Once you're in a conversation, many slash commands are shared across both interfaces.

也就是说:

- `hermes`——启动一个**终端交互会话**（经典 REPL 或现代 TUI,取决于配置/参数),你在本地终端里直接打字对话;
- `hermes gateway`——启动一个**常驻网关进程**,同时对接 Telegram、Discord、Slack、WhatsApp、Signal 等平台,你在这些聊天软件里给 bot 发消息就是在跟同一个 Agent 对话。

这两个入口不是两套独立实现——它们背后是**同一个 Agent 循环**、**同一套 slash 命令注册表**（`hermes_cli/commands.py` 里的 `COMMAND_REGISTRY`,第 03 篇会详细拆解）。这也是为什么 README 的 "CLI vs Messaging Quick Reference" 表格里,绝大多数命令在两栏是完全一样的:

| 操作 | CLI | 消息平台 |
|------|-----|----------|
| 开始对话 | `hermes` | 运行 `hermes gateway setup` + `hermes gateway start`,然后给机器人发消息 |
| 开始新对话 | `/new` 或 `/reset` | `/new` 或 `/reset` |
| 更换模型 | `/model [provider:model]` | `/model [provider:model]` |
| 设置人格 | `/personality [name]` | `/personality [name]` |
| 重试或撤销上一轮 | `/retry`、`/undo` | `/retry`、`/undo` |
| 压缩上下文 / 查看用量 | `/compress`、`/usage`、`/insights [--days N]` | `/compress`、`/usage`、`/insights [days]` |
| 浏览技能 | `/skills` 或 `/<skill-name>` | `/<skill-name>` |
| 中断当前工作 | `Ctrl+C` 或发送新消息 | `/stop` 或发送新消息 |
| 平台特定状态 | `/platforms` | `/status`、`/sethome` |

差异集中在"平台特定"的边角——比如 CLI 里用 `Ctrl+C` 中断,消息平台没有这个概念,只能用 `/stop`;CLI 有 `/platforms` 查看网关状态,消息平台反过来有 `/sethome`（把当前会话设为"主频道"）。这种"共享内核 + 平台化外壳"的设计,后面第 09 章（多智能体网关与调度）、第 10 章（界面层）会深入讲它的实现——`CommandDef` 上的 `cli_only`/`gateway_only` 标记就是这套差异化的具体落点。

## 一次典型对话

安装完成、跑过 `hermes setup` 配好至少一个 provider 之后,最朴素的用法就是:

```bash
hermes
```

这会把你带入一个交互式会话——可以直接打字提问,Agent 会按需调用工具（读写文件、执行命令、搜索网页等）。想换一种"单次提问就退出"的脚本化用法,也可以用一次性模式:

```bash
hermes -z "总结一下当前目录里的项目结构"
```

`-z`/`--oneshot` 只打印最终回复文本,不显示 banner、spinner、工具预览,适合接入脚本管道(这个 flag 的实现细节在下一篇会展开)。

启动网关则是另一条命令线:

```bash
hermes gateway setup   # 配置要接入的平台(bot token 等)
hermes gateway start   # 后台启动网关进程
```

之后在配置好的 Telegram/Discord 等平台上给 bot 发消息,就是在跟同一个 Agent 对话——网关进程内部维护的是同一套 Agent 循环与 slash 命令分发逻辑,只是把"终端输入"换成了"平台消息"。

## 常用顶层子命令一览

除了裸的 `hermes`(进对话)和 `hermes gateway`(起网关),`hermes` 本身还是一个 argparse 驱动的多子命令 CLI。README 的 Getting Started 一节列出了最核心的几个:

```bash
hermes              # 交互式 CLI — 开始对话
hermes model        # 选择你的 LLM provider 和模型
hermes tools        # 配置启用哪些工具
hermes config set   # 设置单个配置项
hermes config get   # 打印单个配置项
hermes gateway      # 启动消息网关(Telegram、Discord 等)
hermes setup        # 运行完整设置向导(一次性配置好一切)
hermes claw migrate # 从 OpenClaw 迁移(如果你是从 OpenClaw 过来的)
hermes update       # 更新到最新版本
hermes doctor       # 诊断问题
```

这几个子命令各自的分工:

- **`hermes setup`**——首次安装后最应该跑的命令,交互式向导一次性配好 provider/模型、必要的 API Key,如果检测到 `~/.openclaw` 目录还会主动提示做 OpenClaw 迁移。也支持 `hermes setup --portal` 一条命令走 Nous Portal OAuth 登录(第 04 篇会细讲)。
- **`hermes model`**——单独调出"选择 provider + 模型"的交互式选择器,不用重新跑完整向导。
- **`hermes tools`**——管理哪些工具/工具集被启用,对应会话内的 `/tools` 命令。
- **`hermes config get`/`hermes config set`**——命令行方式读写单个配置项,适合脚本化场景,不用手改 `config.yaml`。
- **`hermes doctor`**——诊断环境问题(provider 连通性、依赖版本等),遇到"跑不起来"先跑这个。
- **`hermes claw migrate`**——从同类项目 OpenClaw 迁移 `SOUL.md`、记忆、Skills、命令白名单、消息设置、API Key 等,支持 `--dry-run` 预览。

这些子命令具体是怎么用 argparse 注册、又是怎么分发到处理函数的,下一篇《CLI 命令与 Slash 命令体系》会给出真实源码。想看完整的命令和参数列表,直接执行:

```bash
hermes --help
hermes <command> --help
```

或者查阅在线文档的 [CLI Reference](https://hermes-agent.nousresearch.com/docs/reference/cli-commands)。

## 小结与思考题

Hermes 的入口设计是"一体两面":`hermes` 面向本地终端交互,`hermes gateway` 面向多平台消息场景,但两者共享同一个 Agent 循环和同一套 slash 命令注册表,差异只体现在少数平台特有的命令(`/platforms` vs `/sethome`)和 `CommandDef` 上的 `cli_only`/`gateway_only` 标记。顶层还有一批面向配置与运维的子命令(`model`/`tools`/`config`/`setup`/`doctor`/`update`),分别对应模型切换、工具管理、配置读写、初始化向导、健康诊断和自我更新。

思考题:

1. 如果你要新增一个只在消息平台上有意义的 slash 命令(比如"把当前会话转发给某个群"),你觉得应该标记成 `gateway_only=True` 还是靠运行时判断"当前是不是网关环境"来做?两种方式各有什么代价?
2. `hermes -z` 一次性模式为什么要连 banner、spinner、session_id 都不打印?这对应的是什么样的调用场景?
3. 对比 CLI 表格里的 `Ctrl+C`(中断)和消息平台的 `/stop`,你觉得网关要正确实现 `/stop` 的语义,还需要解决哪些 CLI 不需要面对的并发问题?(提示:一个网关进程可能同时服务多个平台、多个会话)
