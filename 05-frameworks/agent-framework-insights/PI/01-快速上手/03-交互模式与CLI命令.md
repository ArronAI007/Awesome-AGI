# 交互模式与 CLI 命令

> 把 Pi 当成一个熟悉的终端伙伴而不是黑盒工具——本篇把界面构成、slash 命令和命令行参数摊开讲清楚。

## 学习目标

- 理解交互模式界面的四个组成区域
- 掌握编辑器内的关键操作（文件引用、多行输入、shell 命令等）
- 记住高频使用的 slash 命令及其作用
- 理解交互模式与非交互模式（`-p`/JSON/RPC）的本质区别
- 能够查表使用 CLI 的模型、会话、工具、资源相关参数

## 交互模式的界面构成

Pi 的交互界面（TUI，Terminal UI）由四个区域组成：

- **启动头部（Startup header）**：显示快捷键提示、已加载的上下文文件、Prompt 模板、Skills 和扩展列表
- **消息区（Messages）**：用户消息、助手回复、工具调用与结果、通知、错误信息，以及扩展自定义 UI
- **编辑器（Editor）**：你输入内容的地方，边框颜色会随当前 thinking level（思考强度）变化
- **底部状态栏（Footer）**：显示工作目录、会话名称、token/缓存用量、费用、上下文占用比例，以及当前模型

编辑器区域在打开 `/settings` 等内置面板或自定义扩展 UI 时会被临时替换。

### 编辑器常用操作

| 功能 | 操作方式 |
|------|---------|
| 引用文件 | 输入 `@` 模糊搜索项目文件 |
| 路径补全 | 按 Tab 补全路径 |
| 多行输入 | Shift+Enter，Windows Terminal 下也可用 Ctrl+Enter |
| 复制回复 | Ctrl+X 复制最后一条助手消息；在 `/tree` 中复制当前选中的消息 |
| 粘贴图片 | Ctrl+V（Windows 为 Alt+V），或直接把图片拖进终端 |
| 执行 shell 命令 | `!command` 会执行并把输出发给模型 |
| 静默 shell 命令 | `!!command` 执行但不把输出发给模型 |
| 外部编辑器 | Ctrl+G 打开 `externalEditor`、`$VISUAL`、`$EDITOR`，或 Windows 下的记事本、其他平台的 `nano` |

所有快捷键都可以在 `~/.pi/agent/keybindings.json` 中自定义，完整清单和自定义方法见《05-配置与个性化》。

## Slash 命令一览

在编辑器中输入 `/` 会弹出命令补全。扩展可以注册自定义命令，Skills 会以 `/skill:名称` 的形式出现，Prompt 模板则通过 `/模板名` 展开。内置的常用命令包括：

| 命令 | 作用 |
|------|------|
| `/login`、`/logout` | 管理 OAuth 或 API Key 凭证 |
| `/llama` | 下载、加载、卸载 llama.cpp 路由模型 |
| `/model` | 切换模型 |
| `/scoped-models` | 启用/禁用参与 Ctrl+P 循环切换的模型集合 |
| `/settings` | 调整 thinking level、主题、消息投递方式、传输协议等 |
| `/resume` | 从历史会话中选择一个恢复 |
| `/new` | 开启新会话 |
| `/name <name>` | 设置会话显示名称 |
| `/session` | 查看当前会话文件、ID、消息数、token 与费用 |
| `/tree` | 跳转到会话中的任意一个节点并从那里继续 |
| `/trust` | 保存项目信任决定，供后续会话使用 |
| `/fork` | 从历史中的某条用户消息创建一个新会话 |
| `/clone` | 把当前活跃分支复制成一个新的会话文件 |
| `/compact [prompt]` | 手动压缩上下文，可附带自定义压缩指令 |
| `/copy` | 复制最后一条助手回复到剪贴板 |
| `/export [file]` | 把会话导出为 HTML 或 JSONL |
| `/import <file>` | 从 JSONL 文件导入并恢复会话 |
| `/share` | 上传为私有 GitHub gist 并生成可分享的 HTML 链接 |
| `/reload` | 重新加载快捷键、扩展、Skills、Prompt 模板、主题和上下文文件 |
| `/hotkeys` | 显示全部快捷键 |
| `/changelog` | 查看版本更新历史 |
| `/quit` | 退出 Pi |

## 消息队列：Agent 工作时你还能做什么

Agent 执行一轮任务往往需要多次工具调用，中途你可以继续输入消息，Pi 提供两种排队方式：

- **Enter** 排队一条"引导消息"（steering message），会在当前这轮助手回复的工具调用执行完之后立即插入；
- **Alt+Enter** 排队一条"后续消息"（follow-up message），要等 Agent 彻底完成当前所有工作后才会送达；
- **Escape** 中止当前操作，并把已排队的消息重新放回编辑器；
- **Alt+Up** 把已排队的消息重新取回编辑器编辑。

这两种投递方式的具体策略（一次性发送全部排队消息，还是逐条发送）可以在 `/settings` 里通过 `steeringMode` 和 `followUpMode` 配置，详见《05-配置与个性化》。

## 交互模式 vs 非交互模式

Pi 默认启动即进入交互模式（Interactive Mode）,这也是本篇前面介绍的一切的运行环境。但 Pi 同样支持三种非交互模式，适合脚本化、CI 集成或程序化调用：

| 模式 | 说明 |
|------|------|
| 默认（不带参数） | 交互模式 |
| `-p`, `--print` | 打印一次性响应后退出 |
| `--mode json` | 把所有事件以 JSON Lines 形式输出，用于结构化解析 |
| `--mode rpc` | 基于 stdin/stdout 的 RPC 模式，用于进程间集成 |
| `--export <in> [out]` | 把一个会话文件导出为 HTML |

在 print 模式下，Pi 还会读取管道传入的 stdin 并合并进初始提示词：

```bash
cat README.md | pi -p "Summarize this text"
```

`--mode json` 和 `--mode rpc` 面向的是把 Pi 作为其他程序的"引擎"来调用的场景，具体协议格式会在后续《07-协议服务化与遥测》章节详细讲解，本篇只需要知道它们的存在和触发方式。

## 上下文文件回顾

Pi 在启动时会从 `~/.pi/agent/AGENTS.md`（全局）以及当前目录向上追溯的各级目录中加载 `AGENTS.md`/`CLAUDE.md`（项目级，逐层叠加）。若某目录存在 `AGENTS.override.md`，会替代该层原本的文件。用 `--no-context-files`（或简写 `-nc`）可以彻底关闭这一发现机制。

Pi 还支持完全替换默认系统提示词：

- 项目级：`.pi/SYSTEM.md`
- 全局级：`~/.pi/agent/SYSTEM.md`

如果只是想在默认系统提示词基础上追加内容而不是替换，用同目录下的 `APPEND_SYSTEM.md` 即可。这部分内容在《02-快速开始》中已经从"让 Pi 了解你的项目"的角度介绍过，这里作为 CLI 参考的一部分再次列出。

## CLI 参数参考

Pi 的基本调用形式：

```bash
pi [options] [@files...] [messages...]
```

### 包管理命令

```bash
pi install <source> [-l]     # 安装包，-l 表示仅当前项目生效
pi remove <source> [-l]      # 移除包
pi uninstall <source> [-l]   # remove 的别名
pi update [source|self|pi]   # 只更新 pi 本体，或更新指定包源
pi update --all              # 更新 pi 和所有包，并调和已固定的 git 引用
pi update --extensions       # 只更新包，调和已固定的 git 引用
pi update --models           # 只刷新模型目录
pi update --self             # 只更新 pi 本体
pi update --extension <src>  # 更新单个包
pi list                      # 列出已安装的包
pi config                    # 启用/禁用包资源
```

`pi update` 不会弹出项目信任询问；`pi config` 和项目包命令支持 `--approve`/`--no-approve` 为单次命令临时信任或忽略项目本地设置。这些命令用于管理 Pi 的扩展生态（详见后续 Pi Packages 相关内容），卸载 Pi CLI 本体请参考《01-安装指南》。

### 模型选项

| 选项 | 说明 |
|------|------|
| `--provider <name>` | 指定 provider，如 `anthropic`、`openai`、`google` |
| `--model <pattern>` | 模型匹配模式或 ID，支持 `provider/id` 前缀和 `:<thinking>` 后缀 |
| `--api-key <key>` | 显式指定 API Key，覆盖环境变量 |
| `--thinking <level>` | 思考强度：`off`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max` |
| `--models <patterns>` | 逗号分隔的模式列表，用于 Ctrl+P 循环切换 |
| `--list-models [search]` | 列出可用模型 |

### 会话选项

| 选项 | 说明 |
|------|------|
| `-c`, `--continue` | 继续最近一次会话 |
| `-r`, `--resume` | 浏览并选择一个历史会话 |
| `--session <path\|id>` | 使用指定的会话文件或部分 UUID |
| `--fork <path\|id>` | 把指定会话 fork 成一个新会话 |
| `--session-dir <dir>` | 自定义会话存储目录 |
| `--no-session` | 临时模式，不保存会话 |
| `--name <name>`, `-n <name>` | 启动时设置会话显示名称 |

### 工具选项

| 选项 | 说明 |
|------|------|
| `--tools <list>`, `-t <list>` | 仅允许指定的内置/扩展/自定义工具 |
| `--exclude-tools <list>`, `-xt <list>` | 禁用指定工具 |
| `--no-builtin-tools`, `-nbt` | 禁用内置工具，保留扩展/自定义工具 |
| `--no-tools`, `-nt` | 禁用全部工具 |

内置工具共 7 个：`read`、`bash`、`edit`、`write`、`grep`、`find`、`ls`。

### 资源选项

| 选项 | 说明 |
|------|------|
| `-e`, `--extension <source>` | 从路径、npm 或 git 加载一个扩展，可重复 |
| `--no-extensions` | 关闭扩展自动发现 |
| `--skill <path>` | 加载一个 Skill，可重复 |
| `--no-skills` | 关闭 Skill 自动发现 |
| `--prompt-template <path>` | 加载一个 Prompt 模板，可重复 |
| `--no-prompt-templates` | 关闭 Prompt 模板自动发现 |
| `--theme <path>` | 加载一个主题，可重复 |
| `--no-themes` | 关闭主题自动发现 |
| `--no-context-files`, `-nc` | 关闭 `AGENTS.md`/`CLAUDE.md` 自动发现 |

`--no-*` 系列参数可以和显式加载参数组合，实现"精确只加载我指定的资源，忽略配置文件里的其他设定"：

```bash
pi --no-extensions -e ./my-extension.ts
```

### 其他选项

| 选项 | 说明 |
|------|------|
| `--system-prompt <text>` | 替换默认系统提示词（上下文文件和 Skills 仍会追加） |
| `--append-system-prompt <text>` | 在默认系统提示词后追加内容 |
| `--tui-mode <mode>` | TUI 模式：`regular`（默认）或实验性的 `fullscreen` |
| `--verbose` | 强制显示详细启动信息 |
| `-a`, `--approve` | 本次运行信任项目本地文件 |
| `-na`, `--no-approve` | 本次运行忽略项目本地文件 |
| `-h`, `--help` | 显示帮助 |
| `-v`, `--version` | 显示版本号 |

### 文件参数

在文件路径前加 `@` 可以把文件内容附加进消息：

```bash
pi @prompt.md "Answer this"
pi -p @screenshot.png "What's in this image?"
pi @code.ts @test.ts "Review these files"
```

### 常用示例

```bash
# 带初始提示词的交互模式
pi "List all .ts files in src/"

# 一次性非交互调用
pi -p "Summarize this codebase"

# 非交互模式配合管道输入
cat README.md | pi -p "Summarize this text"

# 指定会话名称的一次性任务
pi --name "release audit" -p "Audit this repository"

# 指定 provider 和模型
pi --provider openai --model gpt-4o "Help me refactor"

# 用 provider 前缀指定模型
pi --model openai/gpt-4o "Help me refactor"

# 用简写指定 thinking level
pi --model sonnet:high "Solve this complex problem"

# 限制可循环切换的模型集合
pi --models "claude-*,gpt-4o"

# 只读模式，不允许写文件/执行命令
pi --tools read,grep,find,ls -p "Review the code"

# 禁用某个内置工具或扩展工具
pi --exclude-tools ask_question
```

## 设计理念小贴士

Pi 官方文档特别强调一点：它**刻意不内置** MCP（Model Context Protocol）支持、子 Agent、权限弹窗、Plan Mode、待办事项列表或后台 bash 执行这些功能。核心保持精简，把工作流相关的能力都下放给扩展、Skills、Prompt 模板和 Pi 包去实现，或者依赖容器、tmux 等外部工具组合完成。理解这个设计取舍，有助于你判断"某个功能该不该向 Pi 团队提需求"还是"该不该自己写个扩展"。

## 动手练习

1. 启动 `pi`，依次尝试 `/hotkeys`、`/session`、`/changelog` 三个命令，观察各自展示的信息。
2. 用 `pi --tools read,grep,find,ls -p "解释这个项目的目录结构"` 体验只读模式，对比它与默认全工具模式在行为上的差异。
3. 在交互会话中先发起一个复杂任务，趁 Agent 执行时按 Enter 排队一条引导消息，再按 Alt+Enter 排队一条后续消息，观察两者送达时机的差异。

## 小结

交互模式的四区域界面、常用编辑器操作和 slash 命令构成了 Pi 日常使用的骨架；`-p`/JSON/RPC 三种非交互模式则让 Pi 可以被脚本或其他程序当作引擎调用。CLI 参数按模型、会话、工具、资源四大类组织，`--no-*` 与显式加载参数搭配使用能精确控制每次运行加载哪些能力。Pi 有意把复杂工作流能力（MCP、子 Agent、权限系统等）排除在核心之外，这个设计取舍会在后面讲解扩展系统和工程实践时反复出现。

延伸阅读：会话的 JSONL 存储格式与 `/tree` 分支导航背后的实现见《03-Agent核心原理》模块；`--mode json`/`--mode rpc` 的完整协议格式见《07-协议服务化与遥测》模块。
