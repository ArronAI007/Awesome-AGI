# Profile 与个性化配置

> Profile 是 Hermes 支持"同一台机器上跑多个完全隔离的实例"的核心机制——不同的 Telegram bot、不同的工作目录、不同的人格,都可以是独立的 Profile。本篇先从用户视角讲怎么用,再深入到它在源码里到底是怎么实现"隔离"的——这是本课程"快速上手"部分里唯一需要认真读架构的一篇。

## 学习目标

- 从用户视角理解 Profile 解决的问题,以及创建/切换 Profile 的基本命令
- 理解 `_apply_profile_override()` 如何在**任何模块 import 之前**把 `HERMES_HOME` 钉死在正确的目录上
- 理解 `get_hermes_home()` 的解析顺序,以及它和 `get_default_hermes_root()`、`display_hermes_home()` 的分工
- 掌握 AGENTS.md 里"profile-safe 代码规则"的具体内容,尤其是"fail-closed"这条规则背后引用的真实故障
- 了解 `SOUL.md`/`/personality` 这套个性化配置和 Profile 是两个独立但经常一起使用的机制

## 用户视角:Profile 是什么

默认情况下,Hermes 的全部状态——配置、API Key、记忆、会话历史、Skills、网关设置——都在同一个 `HERMES_HOME` 目录下(POSIX 默认 `~/.hermes`,原生 Windows 默认 `%LOCALAPPDATA%\hermes`)。**Profile** 就是"再开一个完全独立的 `HERMES_HOME`",典型场景包括:

- 你想让同一台服务器同时跑两个 Telegram bot,各自有独立的对话历史和记忆,互不干扰;
- 你想给不同的工作目录/项目分配不同的默认模型、不同的人格,不希望互相污染上下文;
- 你想在不动默认配置的前提下,拉一份完全隔离的环境去测试一个新 Skill 或新配置。

创建和切换 Profile 的顶层命令是 `hermes profile`,对应 `hermes_cli/subcommands/profile.py` 里注册的一批子命令:

```bash
hermes profile list                    # 列出所有 profile
hermes profile create coder            # 新建一个名为 coder 的 profile
hermes profile create coder --clone    # 新建时从当前激活 profile 拷贝 config.yaml、.env、SOUL.md、skills
hermes profile use coder               # 把 coder 设为"粘滞默认" profile
hermes profile delete coder            # 删除一个 profile
hermes -p coder                        # 单次调用时临时指定 profile,不改变默认
```

`hermes profile create` 还支持 `--clone-from SOURCE`(从指定 Profile 克隆而非当前激活的)、`--no-skills`(创建空 Profile,不同步内置 Skills)、`--description`(给 kanban 多 Profile 协作看板用的一段描述文字,用来按角色路由任务而不是只按名字猜)。这些细节这里不展开,记住入口和基本心智模型即可——**Profile 的核心是"完全独立的一份 HERMES_HOME"**,剩下的都是围绕这个核心的管理命令。

## 架构视角:`HERMES_HOME` 是怎么被"钉死"的

Profile 机制真正有意思的地方在于它的实现时机。AGENTS.md 里"Profiles: Multi-Instance Support"一节给出了最精炼的总结:

> The core mechanism: `_apply_profile_override()` in `hermes_cli/main.py` sets `HERMES_HOME` before any module imports. All `get_hermes_home()` references automatically scope to the active profile.

这句话里"**before any module imports**"是关键。`_apply_profile_override()` 定义在 `hermes_cli/main.py` 里,而在文件的顶层——不是在某个函数体内,是在模块被 import 时就立即执行的位置——有这样一行:

```python
# hermes_cli/main.py(模块顶层,紧跟在函数定义之后)
_apply_profile_override()

# Windows 启动器自愈……(后面才是真正 import 其他 hermes 模块的代码)
```

也就是说,**在 `hermes_cli.main` 这个模块把自己"运行"起来的那一刻,`_apply_profile_override()` 就已经执行完毕**,后面才轮到 `from hermes_cli.config import get_hermes_home` 这类会真正读取配置、建立连接的 import。这个函数自己做的事情概括起来是:

1. 手工扫描 `sys.argv`(此时 argparse 还没构建,只能自己写一个简化的 tokenizer),找 `--profile`/`-p` 参数,同时小心跳过 `hermes mcp add ... --args <透传给子命令的参数>` 这类"后面的 `--profile` 其实是别的命令的参数,不是 Hermes 自己的"的情况;
2. 如果没有显式 `-p`,再检查 `HERMES_HOME` 环境变量是否已经指向某个具体 Profile 目录,是的话直接信任;
3. 都没有的话,读取 `active_profile` 文件(记录"粘滞默认 Profile"),但**排除**被 s6 supervisor 拉起的网关子进程——因为那些子进程的 Profile 身份是通过启动参数固定分配的槽位,不应该跟随"当前粘滞默认"漂移,否则切换默认 Profile 会导致网关进程静默串到错误的 Profile 下;
4. 解析出最终的 Profile 名后,调用 `hermes_cli/profiles.py` 的 `resolve_profile_env()` 算出真正的目录路径,写进 `os.environ["HERMES_HOME"]`,并把 `--profile`/`-p` 这几个 token 从 `sys.argv` 里摘掉,好让后面 argparse 正常解析剩下的参数。

```python
# hermes_cli/main.py（节选)
if profile_name is not None:
    try:
        from hermes_cli.profiles import resolve_profile_env
        hermes_home = resolve_profile_env(profile_name)
    except Exception as exc:
        print(f"Warning: profile override failed ({exc}), using default", file=sys.stderr)
        return
    os.environ["HERMES_HOME"] = hermes_home
    if consume > 0 and profile_index is not None:
        start = profile_index + 1
        sys.argv = sys.argv[:start] + sys.argv[start + consume:]
```

注意这里的容错策略:一个 Profile 解析失败(比如 `profiles.py` 内部有 bug),**绝不能导致 Hermes 直接启动失败**——宁可打印警告、退回默认 Profile,也不让一个边缘功能的故障挡住主路径。这是一种"降级优于崩溃"的防御性编程,在这个规模的项目里随处可见。

## `get_hermes_home()`:统一的读取出口

有了 `HERMES_HOME` 环境变量被正确设置这个前提,剩下的问题是——**全代码库任何需要读写状态的地方,都必须通过同一个函数去读这个目录,而不是各自硬编码 `~/.hermes`**。这个统一出口是 `hermes_constants.py` 里的 `get_hermes_home()`:

```python
# hermes_constants.py
def get_hermes_home() -> Path:
    """Return the Hermes home directory (default: platform-native path).

    Resolution order: context-local override (see
    :func:`set_hermes_home_override`) → ``HERMES_HOME`` env var → the
    platform-native default. This is the single source of truth — all other
    copies should import this.
    """
    override = get_hermes_home_override()
    if override:
        return Path(override)

    if not os.environ.get("HERMES_HOME", "").strip():
        _warn_profile_fallback_once()

    return _hermes_home_from_env()
```

它的解析顺序是:**contextvar 级别的临时覆盖**(用于某个请求/任务临时切到另一个 Profile 的场景,比如仪表盘里"以某个 Profile 身份预览")> **进程环境变量 `HERMES_HOME`**(`_apply_profile_override()` 设置的正是这一层)> **平台原生默认路径**。

还有一个容易被忽略但很重要的旁支——`_warn_profile_fallback_once()`。如果 `HERMES_HOME` 环境变量没设置,但 `active_profile` 文件明明记录着"当前粘滞 Profile 是 xxx",这个函数会写一条**直接刷到 stderr、绕过 logging 模块**的警告:

```python
# hermes_constants.py（_warn_profile_fallback_once 内)
msg = (
    f"[HERMES_HOME fallback] HERMES_HOME is unset but active "
    f"profile is {active!r}. Falling back to {fallback_home}, which "
    f"is the DEFAULT profile — not {active!r}. Any data this "
    f"process writes will land in the wrong profile. ..."
)
```

为什么不直接抛异常?函数注释给出了理由:`get_hermes_home()` 是在**模块加载时**就会被 30 多处调用的函数,如果在这里抛异常,"会直接搞崩三十多个在模块级别调用它的调用方"。所以选择"响亮地警告,但仍然返回一个可用的默认值",把发现问题的成本让渡给可诊断性,而不是让整个进程崩溃。

与 `get_hermes_home()` 配套的还有两个容易混淆的函数,分工很清楚:

- **`get_default_hermes_root()`**——不管当前激活的是哪个具体 Profile,永远返回"Profile 存放的根目录"(`~/.hermes`,而不是 `~/.hermes/profiles/coder`)。AGENTS.md 的规则 6 专门强调了这一点:"Profile 操作是 HOME-anchored,而不是 HERMES_HOME-anchored"——`hermes profile list` 需要能看到**所有** Profile,不能因为当前激活的是 `coder` 就只看到 `coder` 自己。
- **`display_hermes_home()`**——专给用户看的展示函数,默认 Profile 下显示 `~/.hermes`,具体 Profile 下显示 `~/.hermes/profiles/coder`,不能直接拿 `get_hermes_home()` 的返回值去拼用户提示文案(否则默认 Profile 用户和具体 Profile 用户看到的路径语义不一致)。

## Profile-safe 代码规则

AGENTS.md 把上面这套心智模型,浓缩成了七条"写 Profile-safe 代码"的规则。前四条是关于路径读取的基本纪律(用 `get_hermes_home()` 而不是硬编码 `~/.hermes`、用户提示用 `display_hermes_home()`、模块级常量在 import 时缓存没问题因为那时 `_apply_profile_override()` 早就跑完了、测试 mock `Path.home()` 时必须连带 mock `HERMES_HOME`),第五、六条前面已经涉及(网关平台适配器要对独占凭证加"作用域锁"防止两个 Profile 抢同一个 bot token;Profile 操作是 HOME-anchored)。真正值得单独拿出来精读的是第七条:

> 7. **Multiplex profile-scoped env reads MUST fail closed — never borrow from `os.environ`** (`agent/secret_scope.py` contract; #72348, #86905).

背景是这样的:当 `gateway.multiplex_profiles` 开启时(一个网关进程内同时复用多个 Profile 的场景),进程级的 `os.environ` 里存的其实是**默认 Profile**的值,而某个具体的次级 Profile 自己的 `.env`(凭证、`FEISHU_ALLOWED_USERS` 这类授权名单)只活在一个每轮请求才装载的"密钥作用域"里(`_profile_runtime_scope` 负责安装)。AGENTS.md 原文给出的规则是:

> Scope installed + multiplex active → a scoped miss returns the **default**. NEVER fall through to `os.environ` — that leaks another profile's value and silently breaks routing/admission (a leaked default allowlist skips the allow-all check and rejects every secondary-profile sender, #86905).

翻译成人话:如果作用域已经装载、多路复用已经开启,那么"在这个作用域里找不到某个配置项"应该返回**明确的默认值**(比如"未授权"),**绝对不能**退回去读进程级的 `os.environ`——因为那读到的是**另一个 Profile** 的值,会导致极其隐蔽的串号故障。文档里点名的真实事故现象是:"一个泄漏出来的默认允许名单,跳过了本该有的'全员放行'检查,结果是次级 Profile 的每一条消息发送者都被误判拒绝"——从用户的角度看就是"bot 突然不回消息了",但根因是配置作用域穿透。这条规则背后是两个真实的故障编号 #72348 和 #86905,`plugins/platforms/feishu/adapter.py` 里的 `_get_scoped_secret()` 被 AGENTS.md 指定为这个模式的"canonical fail-closed copy"——文档特别提醒,这段逻辑在大约 15 个平台适配器里都是复制粘贴出来的,任何时候改动其中一份都要注意别把 `except _UnscopedSecretError: val = os.getenv(...)` 这种"兜底读环境变量"的写法带回来。

这条规则是一个很好的教学案例:**多租户/多实例隔离系统里,"读取失败时的兜底行为"往往比"正常路径"更容易埋雷**——一个看似无害的 fallback(找不到就读全局环境变量好了),在单 Profile 场景下完全无害,但在多 Profile 复用场景下就变成了信息泄漏和鉴权绕过的根源。这也是为什么 AGENTS.md 用整整一条规则、两个真实故障编号去强调它。

## 个性化配置:`/personality` 与 `SOUL.md`

Profile 解决的是"实例级"的隔离,而**人格(personality)**解决的是"这个实例里 Agent 表现出什么性格"这个更轻量的问题,两者经常搭配使用(比如给不同 Profile 配不同人格),但机制上是独立的。会话内命令是:

```text
/personality [name]
```

对应 `hermes_cli/commands.py` 里的注册项:

```python
CommandDef("personality", "Set a predefined personality", "Configuration",
           args_hint="[name]", argument_mode="options"),
```

真正的人格解析逻辑在 `hermes_cli/personality.py`(`available_personalities()`、`resolve_personality()`、`active_personality_name()`、`persist_personality()` 等函数),读取的是内置人格加上用户在配置里自定义的覆盖项。而 **`SOUL.md`** 则是更偏"这是谁"的人格/persona 文件——README 在讲 OpenClaw 迁移那一节把它列为要迁移的第一项内容("SOUL.md — persona file"),`hermes profile create --clone` 也会把 `SOUL.md` 当作要拷贝的核心文件之一。可以把两者的关系理解成:`SOUL.md` 是一份放在(某个 Profile 的)`HERMES_HOME` 里的、描述 Agent 长期人格设定的文本文件,`/personality` 命令则是在会话运行时切换预定义人格模板的快捷方式——具体的人格系统提示词拼装细节,会在后面记忆与状态章节结合 `AGENTS.md`/`SOUL.md` 的注入时机一起展开。

## 小结与思考题

Profile 的实现路径可以概括为一句话:`_apply_profile_override()` 在 `hermes_cli.main` 模块顶层、抢在任何其他 Hermes 模块被 import 之前,把 `HERMES_HOME` 环境变量钉死在正确的目录上;之后全代码库统一通过 `get_hermes_home()`(读写状态)、`get_default_hermes_root()`(Profile 级操作)、`display_hermes_home()`(用户提示)这三个函数访问路径,永远不直接拼接 `~/.hermes`。这套机制配合 AGENTS.md 里的七条 profile-safe 规则,尤其是"多路复用场景下密钥读取必须 fail-closed、绝不能兜底读 `os.environ`"这条由两次真实故障(#72348、#86905)催生的规则,构成了 Hermes 支持"同一台机器多实例隔离"的完整设计。`SOUL.md`/`/personality` 则是一层独立但经常搭配 Profile 使用的人格个性化机制。

思考题:

1. `_apply_profile_override()` 里对 s6 supervised 网关子进程做了特殊排除(不跟随粘滞 `active_profile`),如果没有这条排除,你能推演出"切换默认 Profile"这个操作会怎样意外影响正在跑的网关进程吗?
2. `get_hermes_home()` 选择"响亮警告 + 仍然返回默认路径"而不是"抛异常中断",这种取舍在什么场景下是对的,又在什么场景下可能让故障被拖得更久才被发现?
3. AGENTS.md 规则 7 提到"约 15 个平台适配器"里复制粘贴了同一段 `_get_scoped_secret()` 逻辑。如果让你重构,你会把它提炼成一个共享工具函数,还是保留现状(每个适配器一份拷贝)?复制粘贴在这里是不是纯粹的技术债,还是有什么你能想到的合理理由?
