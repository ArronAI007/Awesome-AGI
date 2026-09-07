# Pi Package 生态与分发

> 前两篇讲了怎么写单个 Extension、Skill、Prompt Template；本篇讲怎么把它们打包成一个可以用 `pi install` 一条命令分发给别人的 Pi Package——基于 `docs/packages.md` 逐条讲清楚安装管理命令、三种包来源、manifest 写法、依赖处理和过滤语法。

## 学习目标

- 理解 Pi Package 的本质：用 `package.json` 里的 `pi` 字段或约定目录，把 extensions/skills/prompts/themes 打包在一起。
- 熟练使用 `pi install`/`pi remove`/`pi list`/`pi update` 系列命令，理解全局 vs 项目本地（`-l`）的区别。
- 掌握 npm/git/本地路径三种包来源的语法差异和各自的安装目录、版本锁定规则。
- 掌握 `peerDependencies` 与 `bundledDependencies` 在 Pi Package 里的不同用途，避免把核心包错误地打包进 tarball。
- 掌握包过滤语法（`+path`/`-path`/`!pattern`/`[]`），能针对一个大包只启用其中几个资源。

## Pi Package 是什么

Pi Package 把 extensions、skills、prompt templates、主题（themes）打包在一起，通过 npm 或 git 分发。一个包可以在 `package.json` 的 `pi` 字段里显式声明资源目录，也可以完全不写 manifest、靠约定目录名让 pi 自动发现。

**安全提醒**（文档原文）：Pi Package 运行时拥有完整系统权限。Extension 可执行任意代码，Skill 可以指示模型执行任何操作（包括运行可执行文件）。安装第三方包前务必先审查源码。

## 安装与管理命令

```bash
pi install npm:@foo/bar@1.0.0
pi install git:github.com/user/repo@v1
pi install https://github.com/user/repo   # 裸 URL 也可以直接用
pi install /absolute/path/to/package
pi install ./relative/path/to/package

pi remove npm:@foo/bar
pi list                     # 查看 settings 中已安装的包
pi update                   # 只更新 pi 本身
pi update --all             # 更新 pi、更新所有包、并调和已固定的 git 引用
pi update --extensions      # 只更新包并调和固定的 git 引用
pi update --models          # 只刷新模型目录
pi update --self            # 只更新 pi 本身
pi update --self --force    # 即使当前已是最新版也强制重装 pi
pi update npm:@foo/bar      # 只更新某一个包
pi update --extension npm:@foo/bar
```

`pi install`/`pi remove` 默认写入**用户级配置**（`~/.pi/agent/settings.json`）；加 `-l` 改为写入**项目级配置**（`.pi/settings.json`）。项目级配置可以提交给团队共享——项目被信任后，pi 启动时会自动安装其中缺失的包。

只想临时试用、不想真正安装，用 `--extension`/`-e`：会安装到一个仅本次运行有效的临时目录。

```bash
pi -e npm:@foo/bar
pi -e git:github.com/user/repo
```

## 三种包来源

### npm

```
npm:@scope/pkg@1.2.3
npm:pkg
```

- 带版本号的写法会被固定（pinned），`pi update --extensions`/`pi update --all` 不会去更新它。
- 用户级安装落在 `~/.pi/agent/npm/`，项目级安装落在 `.pi/npm/`。
- 想固定 npm 的包查找/安装命令走某个版本管理器包装（比如 `mise`、`asdf`），在 `settings.json` 里设置 `npmCommand`：

```json
{ "npmCommand": ["mise", "exec", "node@20", "--", "npm"] }
```

### git

```
git:github.com/user/repo@v1
git:git@github.com:user/repo@v1
https://github.com/user/repo@v1
ssh://git@github.com/user/repo@v1
```

- 不带 `git:` 前缀时，只接受标准协议 URL（`https://`、`http://`、`ssh://`、`git://`）。
- 带 `git:` 前缀时，可以用简写形式，包括 `github.com/user/repo` 和 `git@github.com:user/repo`。
- HTTPS 和 SSH 两种 URL 都支持；SSH URL 会自动使用你本机配置好的 SSH key（遵循 `~/.ssh/config`）。
- 非交互式环境（比如 CI）里，可以设 `GIT_TERMINAL_PROMPT=0` 关掉凭据交互提示，设 `GIT_SSH_COMMAND`（例如 `ssh -o BatchMode=yes -o ConnectTimeout=5`）让连接失败时快速报错而不是卡住。
- 引用（ref）是固定的 tag 或 commit。`pi update --extensions`/`pi update --all` **不会**把它们移动到更新的 ref 上，但**会**把已有的本地克隆调和（reconcile）到当前配置的 ref。
- 想把包移动到新的 ref，用 `pi install git:host/user/repo@new-ref`——这会同时更新配置并把已有包移动到新引用。
- 克隆位置：全局 `~/.pi/agent/git/<host>/<path>`，项目级 `.pi/git/<host>/<path>`。
- 当调和操作导致本地检出内容变化时，pi 会重置并清理该克隆，然后在存在 `package.json` 时自动运行一次 `npm install`。

SSH 三种写法示例：

```bash
pi install git:git@github.com:user/repo             # git@host:path 简写（需要 git: 前缀）
pi install ssh://git@github.com/user/repo            # ssh:// 协议格式
pi install git:git@github.com:user/repo@v1.0.0       # 带版本引用
```

### 本地路径

```
/absolute/path/to/package
./relative/path/to/package
```

本地路径指向磁盘上已存在的文件或目录，写入配置时**不会被拷贝**。相对路径相对于它所在的那个 settings 文件解析。如果路径指向一个文件，会被当作单个 extension 加载；如果指向一个目录，按包规则加载其中的资源。

## 创建一个 Pi Package

在 `package.json` 里加一个 `pi` manifest，并加上 `pi-package` 关键字以便被发现：

```json
{
  "name": "my-package",
  "keywords": ["pi-package"],
  "pi": {
    "extensions": ["./extensions"],
    "skills": ["./skills"],
    "prompts": ["./prompts"],
    "themes": ["./themes"]
  }
}
```

路径相对于包根目录解析，数组支持 glob 通配和 `!排除项`。

### Gallery 元数据

[包 Gallery](https://pi.dev/packages) 会展示带 `pi-package` 关键字的包。加 `video` 或 `image` 字段可以显示预览：

```json
{
  "name": "my-package",
  "keywords": ["pi-package"],
  "pi": {
    "extensions": ["./extensions"],
    "video": "https://example.com/demo.mp4",
    "image": "https://example.com/screenshot.png"
  }
}
```

`video` 仅支持 MP4，桌面端悬停自动播放、点击进入全屏播放；`image` 支持 PNG/JPEG/GIF/WebP，展示为静态预览图。两者都设置时优先展示 `video`。

## 包结构：约定目录

如果没有 `pi` manifest，pi 会按下面的约定目录自动发现资源：

- `extensions/`：加载其中的 `.ts` 和 `.js` 文件
- `skills/`：递归查找包含 `SKILL.md` 的目录，同时把顶层的 `.md` 文件当作技能加载
- `prompts/`：加载其中的 `.md` 文件
- `themes/`：加载其中的 `.json` 文件

## 依赖处理

第三方运行时依赖放进 `package.json` 的 `dependencies`；不注册 extension/skill/prompt/theme 的普通依赖也放这里。pi 从 npm 或 git 安装包时会自动跑一次 `npm install`，所以 `dependencies` 会被自动装好。

pi 自带了一批核心包供 extension 和 skill 使用。如果你的代码 `import` 了下面这些包，必须把它们列进 `peerDependencies`（版本范围写 `"*"`），**不要**打包进 tarball：

```
@earendil-works/pi-ai
@earendil-works/pi-agent-core
@earendil-works/pi-coding-agent
@earendil-works/pi-tui
typebox
```

除此之外的**其他 pi package**（比如你依赖了另一个第三方 pi 扩展包）必须打包进你自己的 tarball：加进 `dependencies` 和 `bundledDependencies`，再通过 `node_modules/` 路径引用它们的资源。pi 给每个包加载独立的模块根，所以不同的安装之间不会互相冲突或共享模块。

```json
{
  "dependencies": {
    "shitty-extensions": "^1.0.1"
  },
  "bundledDependencies": ["shitty-extensions"],
  "pi": {
    "extensions": ["extensions", "node_modules/shitty-extensions/extensions"],
    "skills": ["skills", "node_modules/shitty-extensions/skills"]
  }
}
```

判断标准很直接：**pi 核心包（上面列出的五个）→ `peerDependencies`，不打包**；**其他任何 pi package → `dependencies` + `bundledDependencies`，必须打包**；**其他普通第三方运行时库 → 普通 `dependencies`**。

## 包过滤语法

用 settings 里的对象形式可以过滤一个包实际加载哪些资源：

```json
{
  "packages": [
    "npm:simple-pkg",
    {
      "source": "npm:my-package",
      "extensions": ["extensions/*.ts", "!extensions/legacy.ts"],
      "skills": [],
      "prompts": ["prompts/review.md"],
      "themes": ["+themes/legacy.json"]
    }
  ]
}
```

`+path` 和 `-path` 是相对包根目录的**精确路径**。规则：

- 省略某个字段：加载该类型的全部资源。
- 写 `[]`：该类型一个都不加载。
- `!pattern`：从已匹配集合里排除。
- `+path`：强制包含某个精确路径（即使原本被排除）。
- `-path`：强制排除某个精确路径（即使原本被包含）。
- 过滤规则是叠加在 manifest 之上的一层限制，只能"缩小"manifest 已经允许的范围，不能"扩大"它。

上面示例里的效果：`my-package` 的所有 `extensions/*.ts` 都加载，除了 `legacy.ts`；技能一个都不加载；只加载 `prompts/review.md` 这一个提示词模板；主题按 manifest 默认规则加载，并强制加上本来可能被排除的 `themes/legacy.json`。

## 启用与禁用资源

用 `pi config` 可以对已安装包和本地目录里的 extensions/skills/prompt templates/themes 逐项启用或禁用。`pi config` 默认从全局配置（`~/.pi/agent/settings.json`）打开，按 Tab 切换到项目本地模式；用 `pi config -l` 直接从项目覆盖配置（`.pi/settings.json`）打开，此时继承自全局的资源会以灰显方式呈现。

## 作用域与去重

同一个包可以同时出现在全局配置和项目配置里。当两边都出现时，**项目级条目优先**；但如果项目级条目显式设置了 `autoload: false`，则它会被当作叠加在全局条目之上的增量（delta）应用，而不是整体覆盖。

包的"身份"（用于判断是不是同一个包）判定规则：

- npm 包：按包名判断
- git 包：按去掉 ref 后的仓库 URL 判断
- 本地包：按解析后的绝对路径判断

## 动手练习

1. 用 `pi list` 查看当前环境已安装的包（如果为空，先用 `pi -e npm:<任意一个你了解的 pi 社区包>` 或本地路径试装一次，观察 `pi list` 输出的变化和 `~/.pi/agent/settings.json` 里新增的 `packages` 条目）。
2. 参照"创建一个 Pi Package"一节，把你在前两篇练习里写好的一个 Extension 和一个 Skill 放进同一个目录，按约定目录结构（`extensions/`、`skills/`）组织（不写 `pi` manifest），用 `pi install ./你的目录路径 -l` 装到当前项目，然后用 `pi config -l` 打开配置界面确认两个资源都被正确发现并可以单独启用/禁用。

## 小结

Pi Package 是 pi 生态分发 Extension、Skill、Prompt Template、主题的标准形式，可以来自 npm、git 或本地路径，通过 `pi install`/`pi remove`/`pi list`/`pi update` 一套命令管理，默认写入全局配置、加 `-l` 写入项目配置。包结构上，要么用 `package.json` 里的 `pi` manifest 显式声明资源目录，要么完全依赖 `extensions/`/`skills/`/`prompts/`/`themes/` 四个约定目录名自动发现。依赖处理上要分清三类：pi 五个核心包走 `peerDependencies` 不打包，其他 pi package 依赖走 `dependencies` + `bundledDependencies` 必须打包进 tarball，普通运行时库走 `dependencies` 由 pi 自动 `npm install`。包过滤语法（`!`/`+`/`-`/`[]`）让使用者可以只启用一个大包里的部分资源，而作用域与去重规则（项目优先、`autoload: false` 走增量、身份按包名/仓库 URL/绝对路径判定）保证了全局与项目配置共存时行为可预测。
