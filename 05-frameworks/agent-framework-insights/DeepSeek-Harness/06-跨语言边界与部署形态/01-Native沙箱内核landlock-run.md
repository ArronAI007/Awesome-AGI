# Native 沙箱内核 landlock-run

> `bwrap`（bubblewrap）是 dsh 在 Linux 上的第一选择沙箱后端，但它依赖 mount namespace 权限——容器套容器、CI runner、某些企业级安全策略下的宿主机,往往直接不允许创建 namespace。这种"降级到不设防"是不可接受的,dsh 的答案是再造一个更轻量、只依赖 Landlock LSM 的独立启动器：`native/landlock-run`。本篇通读它唯一的源码文件 `main.c`（约 298 行手写 C11）和消费它的 TypeScript 胶水代码,搞清楚一个"自我限制后再 exec"的沙箱启动器是怎么把内核 UAPI、fail-closed 设计和 Node 生态的包分发揉在一起的。

## 学习目标

- 理解为什么 dsh 在 `bwrap` 之外还需要一条 Landlock 路径：mount namespace 权限不可用时的降级方案,而不是 `bwrap` 的替代品。
- 弄清楚 `native/landlock-run` 的真实实现形态——纯 C11 直连内核 UAPI 的独立可执行文件,不依赖 `<linux/landlock.h>`,也不是 Rust/Zig 或 N-API/FFI 绑定。
- 理解包名 `@deepseek-ai/node-addon-landlock-run` 里 "node-addon-" 前缀的真实含义：它模仿的是 esbuild 式"一个入口包 + 每平台一个二进制包"的分发模型,而不是真正的 Node addon。
- 掌握 fail-closed 设计的具体落地：任何启动器级失败退出码 125 且绝不 `execve` 目标命令。
- 理解 `--probe` 探测机制为什么要"真的施加一次最大化规则集"而不是只查内核版本号。
- 搞清楚 full/partial enforcement 的区分依据,以及 Landlock 规则如何随 `execve` 继承、实现白名单式的安全模型。

## 背景与设计动机

dsh 的沙箱层（`packages/sandbox/sandbox-local`）需要在不同操作系统、不同权限环境下,把"允许访问哪些路径"这件事强制落实到子进程身上。Linux 上最常见的方案是 `bwrap`：它通过 mount namespace 把整个文件系统视图重新拼装成一个受限视图,能力强,但前提是调用者能创建 user namespace / mount namespace——很多生产环境出于安全考虑直接关闭了这个权限(`CAP_SYS_ADMIN` 受限、`unprivileged_userns_clone` 被禁用、容器已经跑在受限的 seccomp/AppArmor 策略下等)。

Landlock 是 Linux 5.13 引入的一个专门为"非特权自我限制"设计的 LSM(Linux Security Module)：任何进程都可以在不需要额外权限的情况下,给自己施加一个文件系统访问的白名单规则集,规则一旦施加就无法撤销,并且会随 `execve` 继承给后续所有子进程。这正好补上了 `bwrap` 权限不可用时的空白——它不如 `bwrap` 全面(目前只管文件系统访问),但足够轻、足够安全,可以作为一条无需特殊权限的备选沙箱路径。

`native/landlock-run` 就是 dsh 为这条路径写的启动器。它的目录结构是：

```text
native/landlock-run/
├── docs/                    # cli-contract.md / architecture.md / naming.md / support-matrix.md / packaging.md
├── packages/
│   ├── entry/                          # @deepseek-ai/node-addon-landlock-run,ESM JS 入口
│   │   └── src/{main.c, index.ts}
│   ├── linux-x64/                      # @deepseek-ai/node-addon-landlock-run-linux-x64,纯二进制包
│   └── linux-arm64/                    # 同上,arm64
├── scripts/                 # 构建脚本
└── test/                    # launcher.test.js / entry.test.js
```

全部沙箱逻辑压缩进唯一一个源码文件 `packages/entry/src/main.c`。这个设计选择本身就是一种安全声明——文件头注释写得很直接：

```c
// native/landlock-run/packages/entry/src/main.c:30-35
 * Plain C11 over the raw Landlock UAPI — no libraries beyond libc (musl,
 * linked statically), so the whole audit surface is this file plus the
 * kernel's stable syscall contract. Built natively per architecture by
 * `scripts/build.ts` into the per-platform npm packages
 * (`@deepseek-ai/node-addon-landlock-run-linux-{x64,arm64}`); the argv grammar,
 * exit codes, and report lines are pinned in `docs/cli-contract.md`.
```

"审计面就是这一个文件加上内核的稳定系统调用契约"——没有第三方库,没有动态链接的 glibc,连内核头文件都不用,可审计性被做到了极致。

## 核心机制详解

### 手写 Landlock UAPI,而不是 `#include <linux/landlock.h>`

`main.c` 顶部只引入标准 libc 头文件,没有内核头:

```c
// native/landlock-run/packages/entry/src/main.c:38-48
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
```

Landlock 的结构体和常量是照抄内核头文件的布局,手写在源码里:

```c
// native/landlock-run/packages/entry/src/main.c:50-68
/*
 * The Landlock UAPI, defined locally instead of via <linux/landlock.h>: the
 * kernel's user-space ABI is stable by contract, self-defining it keeps the
 * build independent of the toolchain's header vintage, and the definitions
 * double as the audit record of exactly which kernel API this launcher
 * touches. Layouts and values are verbatim from the kernel header (the
 * path-beneath struct is packed there, so it must be packed here).
 */
struct landlock_ruleset_attr {
  uint64_t handled_access_fs;
};

struct landlock_path_beneath_attr {
  uint64_t allowed_access;
  int32_t parent_fd;
} __attribute__((packed));

#define LANDLOCK_CREATE_RULESET_VERSION (1U << 0)
#define LANDLOCK_RULE_PATH_BENEATH 1
```

系统调用号也是手写的回退定义,因为 Landlock 至今没有 libc 包装:

```c
// native/landlock-run/packages/entry/src/main.c:96-105
/*
 * Landlock has no libc wrappers; these are the raw syscalls. The numbers are
 * identical on every architecture (the post-2011 unified table) — the
 * fallbacks only matter to a libc older than the feature.
 */
#ifndef __NR_landlock_create_ruleset
#define __NR_landlock_create_ruleset 444
#define __NR_landlock_add_rule 445
#define __NR_landlock_restrict_self 446
#endif
```

三个核心系统调用直接用 `syscall()` 裸调用发起,不经过任何封装：

```c
// 创建/协商 ABI 版本(main.c:231)
long abi = syscall(__NR_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION);
// 创建正式 ruleset(main.c:241)
int ruleset_fd = (int)syscall(__NR_landlock_create_ruleset, &attr, sizeof attr, 0);
// 添加一条规则(main.c:211)
syscall(__NR_landlock_add_rule, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, &attr, 0)
// 施加规则到自身(main.c:257)
syscall(__NR_landlock_restrict_self, ruleset_fd, 0)
```

这四行就是整个沙箱的内核交互面——不依赖任何"Landlock 库",连内核头文件的版本都不需要对齐,只要目标机器的内核支持这几个系统调用号即可。

### 不是 N-API 绑定,是独立可执行文件 + 子进程调用

`@deepseek-ai/node-addon-landlock-run` 这个包名带着"node-addon-"前缀,第一次看很容易误认为是 N-API/FFI 那种"编译进 Node 进程内存空间"的原生模块。实际情况完全不同——`main.c` 编译产出的是一个**独立的命令行可执行文件**,Node 侧只是用 `spawnSync`/`spawn` 去启动它,和调用 `bash`/`git` 没有本质区别。

`packages/entry/src/index.ts` 的导入只有这四个标准 Node 模块：

```ts
// native/landlock-run/packages/entry/src/index.ts:16-19
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
```

全文再也没有出现任何 `node:ffi`、`.node` 二进制加载、`process.binding`、`require('bindings')` 之类真正 N-API/addon 才会有的代码。真正解释这个命名来源的是 `docs/architecture.md`：

```text
// native/landlock-run/docs/architecture.md:3
consumers decide which paths a run may read or write; this package family
provides the launcher that enforces those grants and the JavaScript API that
resolves and speaks to it. The packaging follows the per-platform-package
model of `node-addon-require-builtin` (and esbuild), adapted from Node
addons to standalone static executables.
```

即：命名模式是照搬 `node-addon-require-builtin`/esbuild 那种"一个 JS 入口包 + 每平台一个二进制包"的分发结构,但作者自己特别注明"adapted from Node addons to standalone static executables"——沿用了打包命名习惯,但内容物已经从"进程内加载的原生模块"换成了"进程外的独立可执行文件"。平台包 `linux-x64/package.json` 的描述也写得很直白：

```json
// native/landlock-run/packages/linux-x64/package.json
"description": "Prebuilt landlock-run Landlock launcher binary for linux-x64 (static musl) — resolved as a file path by @deepseek-ai/node-addon-landlock-run, never imported"
```

"never imported"——它从未被 `require`/`import`,只是被当作一个文件路径字符串消费。`entry/package.json` 里用 `optionalDependencies` 声明了两个平台包：

```json
// native/landlock-run/packages/entry/package.json
"optionalDependencies": {
  "@deepseek-ai/node-addon-landlock-run-linux-arm64": "workspace:*",
  "@deepseek-ai/node-addon-landlock-run-linux-x64": "workspace:*"
}
```

npm 的 `os`/`cpu` 字段（平台包里声明为 `"os": ["linux"]`、`"cpu": ["x64"]`）在安装期就会自动只装匹配当前平台的那一个,不匹配的平台包不会落地。运行时,`launcherPath()` 用 `require.resolve` 去找当前平台对应的包,再拼出二进制路径：

```ts
// native/landlock-run/packages/entry/src/index.ts:69-83
export function launcherPath(
  resolvePackageJson: (specifier: string) => string = createRequire(import.meta.url).resolve,
): string {
  const platformPackage = `@deepseek-ai/node-addon-landlock-run-${process.platform}-${process.arch}`
  try {
    return join(dirname(resolvePackageJson(`${platformPackage}/package.json`)), 'bin', LAUNCHER_BIN)
  } catch {
    // Unresolvable platform package: no such package exists for this host, or
    // it was not installed. Fall back to the path pnpm's layout WOULD use —
    // absolute, inside this package's boundary (never cwd-relative: a
    // spawnable relative path here would hand cwd control over which binary
    // confines), and nonexistent exactly when the package is absent.
    return fileURLToPath(new URL(`../node_modules/${platformPackage}/bin/${LAUNCHER_BIN}`, import.meta.url))
  }
}
```

这里的注释同样值得留意:回退路径特意选择"绝对路径、包边界之内",而不是任何 cwd 相关的路径——因为"哪个二进制来限制这个进程"这个决定,绝不能受调用时的当前目录影响。整个模块的头部注释把这个原则说得更绝：

```ts
// native/landlock-run/packages/entry/src/index.ts:12-15
 * Deliberately no environment-variable overrides anywhere in this module:
 * which binary confines a process must never be decidable by the ambient
 * environment. Test injection is by function parameter.
```

没有任何环境变量能改变"用哪个二进制去限制进程"这件事——这条约束在 `docs/naming.md` 和仓库根 `AGENTS.md` 里被重复强调为"运行时安全规则"而不只是编码习惯。

### 协议:`--ro`/`--rw`/`--` 与 `grantArgs()`

`docs/cli-contract.md` 把整个命令行协议钉死为：

```text
// native/landlock-run/docs/cli-contract.md:7-18
landlock-run [--ro <path>]... [--rw <path>]... -- <argv>...
landlock-run --probe

- `--ro <path>`: grant read + execute beneath `<path>`.
- `--rw <path>`: grant full filesystem access beneath `<path>` (every access
  the negotiated kernel ABI can govern).
- Everything not granted is denied — Landlock rulesets are allow-lists.
- `--`: mandatory separator; everything after it is the command argv, exec'd
  via `execvp` with the launcher's environment unchanged.
- `--probe`: mutually exclusive with grants and a command.
- No other flags, no environment-variable inputs.
```

对应的 C 侧解析逻辑是手写的,四个 flag 不值得引入解析库：

```c
// native/landlock-run/packages/entry/src/main.c:142-182(节选)
/*
 * Hand-rolled argv parsing — four flags do not justify a parsing library.
 * Returns 0 on success, else the process exit code (message already printed).
 */
static int parse(int argc, char **argv, struct cli *cli) {
  int index = 1;
  while (index < argc) {
    const char *arg = argv[index];
    if (strcmp(arg, "--probe") == 0) {
      if (argc != 2) return fail_usage("--probe takes no other arguments", NULL);
      cli->probe = 1;
      index += 1;
    } else if (strcmp(arg, "--ro") == 0 || strcmp(arg, "--rw") == 0) {
      if (index + 1 >= argc) return fail_usage(arg, " requires a path");
      if (strcmp(arg, "--ro") == 0) cli->ro[cli->ro_count++] = argv[index + 1];
      else cli->rw[cli->rw_count++] = argv[index + 1];
      index += 2;
    } else if (strcmp(arg, "--") == 0) {
      cli->command = &argv[index + 1];
      break;
    } else {
      return fail_usage("unknown argument: ", arg);
    }
  }
  if (!cli->probe && (cli->command == NULL || cli->command[0] == NULL)) {
    return fail_usage("missing `-- <argv>...` command", NULL);
  }
  return 0;
}
```

JS 侧的 `grantArgs()` 只是把 `{ readOnly, readWrite }` 对象拼成对应的 flag 数组,不做任何路径校验(校验和拒绝的责任在 C 二进制里)：

```ts
// native/landlock-run/packages/entry/src/index.ts:94-99
export function grantArgs(grants: LauncherGrants): string[] {
  return [
    ...(grants.readOnly ?? []).flatMap(root => ['--ro', root]),
    ...(grants.readWrite ?? []).flatMap(root => ['--rw', root]),
  ]
}
```

`test/entry.test.js` 里锁死了拼接顺序（只读参数在前,读写在后,与调用者传参顺序无关）：

```js
// native/landlock-run/test/entry.test.js:24-31
assert.deepEqual(grantArgs({}), []);
assert.deepEqual(grantArgs({ readOnly: ['/'] }), ['--ro', '/']);
assert.deepEqual(
  grantArgs({ readOnly: ['/', '/opt'], readWrite: ['/tmp/work'] }),
  ['--ro', '/', '--ro', '/opt', '--rw', '/tmp/work'],
);
```

真正跑沙箱的一方(比如 `packages/sandbox/sandbox-local`)把 `[launcherPath(), ...grantArgs(...), '--', ...实际命令]` 拼成一整条 argv,交给自己的进程管理器 `spawn`——`landlock-run` 只是这条 argv 数组第一个位置的可执行文件,和普通命令没有任何特殊之处。README 给出的最简用法印证了这一点：

```js
// native/landlock-run/README.md:27-35
import { grantArgs, launcherPath, probe } from '@deepseek-ai/node-addon-landlock-run';

const launcher = launcherPath();
if (probe(launcher) !== 'unusable') {
  const argv = [launcher, ...grantArgs({ readOnly: ['/'], readWrite: ['/tmp/work'] }), '--', 'bash', '-c', command];
  // spawn argv with your process runner of choice
}
```

### `--probe`:真的施加一次最大规则集,而不是查版本号

内核支持 Landlock 语义(有没有编译进这个 LSM、有没有被启用)不能靠 uname 或版本号猜测——同一个版本号的内核,可能因为编译选项或 `CONFIG_SECURITY_LANDLOCK` 被关闭而完全不支持。`--probe` 的做法是老老实实走一遍完整流程：用 `--ro /` 构建一个覆盖全盘的规则集,真的对当前(即将退出的)探测进程施加限制,看内核会不会真的接受：

```c
// native/landlock-run/packages/entry/src/main.c:269-283
if (cli.probe) {
  /* The functional probe: build and enforce a maximal ruleset in THIS
   * short-lived process (the probe run exits right after). `--version`
   * style checks would miss a kernel that has the syscalls but refuses
   * enforcement; actually restricting is the only honest signal. The one
   * report line is part of the launcher CLI contract — the executor reads
   * enforcement completeness from it. */
  static const char *probe_root = "/";
  struct cli probe = { .ro = &probe_root, .ro_count = 1 };
  int partial = 0;
  code = restrict_self(&probe, &partial);
  if (code != 0) return code;
  printf("landlock: %s\n", partial ? "partially enforced (older ABI)" : "fully enforced");
  return 0;
}
```

注释里的理由很关键:"版本号式检查会漏掉内核有 syscall 但拒绝执行 enforcement 的情况——真的去限制一次才是唯一诚实的信号"。这一行 stdout 输出是协议的一部分,`index.ts` 的 `probe()` 函数直接用正则去解析它：

```ts
// native/landlock-run/packages/entry/src/index.ts:116-127
export function probe(
  launcher: string = launcherPath(),
  options: { timeoutMs?: number } = {},
): LandlockEnforcement {
  const result = spawnSync(launcher, ['--probe'], {
    timeout: options.timeoutMs ?? 2000,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
  })
  if (result.status !== 0) return 'unusable'
  return /partially enforced/.test(result.stdout) ? 'partial' : 'full'
}
```

`spawnSync` 加上 2 秒默认超时,退出码非 0 直接归为 `unusable`;stdout 里出现 `partially enforced` 归为 `partial`,否则归为 `full`。这三个值——`full`/`partial`/`unusable`——正是消费方 `sandbox-local` 用来决定"能不能选 Landlock 这条路径"的判据。

### fail-closed:退出码 125,绝不 `execve` 目标命令

任何"启动器级"失败(参数错误、内核不支持、规则路径打不开、施加规则失败)都必须在还没跑到 `execvp` 之前返回,并且要用一个和被包装命令自身退出码"几乎不可能撞车"的固定退出码,让外层调用方能明确区分"是启动器失败"还是"是被包装的命令自己失败了"：

```c
// native/landlock-run/packages/entry/src/main.c:107-112
/*
 * Every fatal launcher error prints `landlock-run: <message>` to stderr
 * and exits 125 — a code the wrapped command itself is unlikely to use, so
 * the executor can tell launcher failures from command failures.
 */
#define EXIT_LAUNCHER_FAILURE 125
```

内核完全不支持 Landlock 时(`ENOSYS`/`EOPNOTSUPP`)的处理是直接拒绝,注释直接写明了这是"宁可不跑,也不裸奔"的原则：

```c
// native/landlock-run/packages/entry/src/main.c:230-236
static int restrict_self(const struct cli *cli, int *partial) {
  long abi = syscall(__NR_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION);
  if (abi < 0) {
    /* ENOSYS: kernel built without Landlock; EOPNOTSUPP: built but disabled.
     * Either way: not enforceable — fail CLOSED, never exec unconfined. */
    return fail(NOT_ENFORCED_MESSAGE, NULL);
  }
  ...
```

某条授权路径本身打不开(比如调用方传了个不存在的目录)也是同样的处理方式,哪怕"悄悄缩小授权范围"看起来是安全的,也不采纳这个选项：

```c
// native/landlock-run/packages/entry/src/main.c:194-202
static int add_rule(int ruleset_fd, const char *path, uint64_t access) {
  int path_fd = open(path, O_PATH | O_CLOEXEC);
  if (path_fd < 0) {
    /* Fail closed on an unopenable grant root: silently narrowing the
     * granted set would be safe, but running with a profile the caller did
     * not get is not worth the ambiguity. */
    fprintf(stderr, "landlock-run: cannot open rule path: %s: %s\n", path, strerror(errno));
    return EXIT_LAUNCHER_FAILURE;
  }
  ...
```

`main()` 的主流程严格按"每一步失败就直接 return,永远不往下走"的方式串联,只有全部成功才会到达最后一行的 `execvp`：

```c
// native/landlock-run/packages/entry/src/main.c:295-297
execvp(cli.command[0], cli.command);
/* exec only returns on failure. */
return fail("exec failed", strerror(errno));
```

`test/launcher.test.js` 用一个真实的失败场景做了断言,证明"命令永远不会落地"不是空话：

```js
// native/landlock-run/test/launcher.test.js:127-135
// --- fail closed: an unopenable grant root refuses to exec at all ---
{
  const marker = path.join(os.tmpdir(), `nalr-should-not-exist-${process.pid}`);
  const badGrant = run(['--ro', '/no/such/grant/root', '--', '/bin/sh', '-c', `echo x > ${marker}`]);
  assert.equal(badGrant.status, LAUNCHER_FAILURE_EXIT);
  assert.ok(badGrant.stderr.startsWith(FATAL_PREFIX));
  assert.match(badGrant.stderr, /cannot open rule path/);
  assert.ok(!fs.existsSync(marker), 'the command must never run when the launcher fails');
}
```

授权路径不存在 → 启动器退出 125 → 那条本该往 marker 文件写入的 `echo` 命令根本没有机会执行,文件也就根本不存在。

消费方 `packages/sandbox/sandbox-local/src/index.ts` 把这条"125 + `landlock-run: ` 前缀"的信号接进自己的失败分类规则里：

```ts
// packages/sandbox/sandbox-local/src/index.ts:231-237(节选)
const RUNNER_FAILURE_RULES = {
  bwrap: [{ fatalSignatures: ['bwrap: '] }],
  landlock: [{
    allowedExitCodes: [LAUNCHER_FAILURE_EXIT],
    fatalSignatures: [`${LAUNCHER_BIN}: `],
    informationalLines: [`${LAUNCHER_BIN}: partial enforcement (older Landlock ABI)`],
  }],
  ...
} as const
```

`allowedExitCodes: [LAUNCHER_FAILURE_EXIT]` 加上 `fatalSignatures` 前缀匹配,让上层能把"启动器本身失败"和"业务命令正常返回非零"区分开——这正是 `EXIT_LAUNCHER_FAILURE = 125` 这个约定在跨语言边界另一侧发挥作用的地方。

### full vs partial enforcement:旧内核 ABI 的诚实降级

Landlock 是一个持续演进的 LSM,每个新的内核 ABI 版本会新增可治理的文件系统访问类型(比如 ABI 2 加了 `LANDLOCK_ACCESS_FS_REFER`,ABI 3 加了 truncate 治理,ABI 5 加了设备 ioctl 治理)。`landlock-run` 在协商阶段会问内核"你支持到哪一版",然后把规则集缩到内核实际能治理的子集,而不是要求"全有或全无"：

```c
// native/landlock-run/packages/entry/src/main.c:90-94
/*
 * Newest ABI this build knows; the negotiation below scales the actual
 * ruleset down to what the running kernel supports.
 */
#define MAX_ABI 5L
```

```c
// native/landlock-run/packages/entry/src/main.c:184-191
/* The filesystem accesses the running kernel's ABI can govern. */
static uint64_t fs_mask_for_abi(long abi) {
  uint64_t mask = LL_ABI1_MASK;
  if (abi >= 2) mask |= LL_FS_REFER;
  if (abi >= 3) mask |= LL_FS_TRUNCATE;
  if (abi >= 5) mask |= LL_FS_IOCTL_DEV;
  return mask;
}
```

协商出的 `abi` 一旦小于 `MAX_ABI`,`*partial` 就被标记为真,但这不是失败,只是降级——规则集依然会被施加,只是范围比"最新 ABI 能治理的全集"小一点：

```c
// native/landlock-run/packages/entry/src/main.c:237-238
*partial = abi < MAX_ABI;
uint64_t handled = fs_mask_for_abi(abi < MAX_ABI ? abi : MAX_ABI);
```

```c
// native/landlock-run/packages/entry/src/main.c:285-293
int partial = 0;
code = restrict_self(&cli, &partial);
if (code != 0) return code;
if (partial) {
  /* Older ABI: some handled accesses are not governed (e.g. truncate
   * before ABI 3). Still confined for everything the kernel supports —
   * report, do not refuse. */
  fprintf(stderr, "landlock-run: partial enforcement (older Landlock ABI)\n");
}
```

`docs/support-matrix.md` 把这套判据总结成了一句话,同时强调"探测结果本身才是权威,内核版本号不是"：

```text
// native/landlock-run/docs/support-matrix.md:9
Enforcement additionally requires a kernel with Landlock enabled (5.13+). The
negotiated ABI level decides the probe verdict: every access this build knows
governed → `full`; an older ABI governing a subset → `partial` (still
confined for everything it supports); Landlock absent or disabled →
`unusable`, and the launcher refuses to run commands at all. The probe — not
the kernel version — is the authority: a kernel built without Landlock, or
with the LSM disabled, probes `unusable` regardless of its version.
```

### 白名单模型与 `execve` 继承

`docs/cli-contract.md` 最后一段直接点明了这个沙箱的两个安全支柱：

```text
// native/landlock-run/docs/cli-contract.md:32-34
## Confinement semantics

The launcher sets `no_new_privs`, installs the ruleset on itself, and `exec`s
the command; the ruleset is inherited across `execve`, so every descendant
process is equally confined. The ruleset governs the filesystem accesses of
the kernel's negotiated Landlock ABI (up to ABI 5); accesses newer than the
running ABI are not governed and are the difference between `full` and
`partial`.
```

- **白名单式授权**：Landlock 规则集本质上是允许列表,`--ro`/`--rw` 授予的路径之外一切被拒绝——这与传统的"黑名单拦截危险操作"完全相反,任何没有被显式授权的路径,不管是不是"看起来无害",都会被拒。
- **规则随 `execve` 继承**：`landlock_restrict_self` 施加在调用进程自身之后,只要接下来走 `execvp`,新进程映像继承同一份限制,而且这份限制**无法被子进程自己撤销**——`test/launcher.test.js` 里专门有一个"嵌套子进程也被限制"的用例验证这一点：

```js
// native/landlock-run/test/launcher.test.js:117-122
// The ruleset is inherited across execve: a CHILD of the wrapped command
// is confined too, not just the direct exec target.
const nested = path.join(work, 'nested.txt');
const nestedRun = run([...grantArgs({ readOnly: ['/'] }), '--', '/bin/sh', '-c', `/bin/sh -c 'echo x > ${nested}'; true`]);
assert.equal(nestedRun.status, 0, nestedRun.stderr);
assert.ok(!fs.existsSync(nested), 'a denied write from a nested child must not land either');
```

外层 shell 是被 `landlock-run` 直接 `execvp` 出来的进程,内层再 `fork`+`exec` 出的第二层 shell 依然在同一份规则集的约束下——`echo x > nested` 这次写入被拒绝,`nested.txt` 始终不存在,尽管命令本身的 exit code 是 0(内层子命令的失败被 shell 的 `; true` 吞掉了,重点是文件确实没被创建)。

### 消费方:`sandbox-local` 里三种沙箱后端的并列关系

`packages/sandbox/sandbox-local/src/profiles.ts` 里,`landlockProfileArgs` 只负责把 dsh 内部统一的 `SandboxPolicy` 翻译成 landlock-run 的授权参数：

```ts
// packages/sandbox/sandbox-local/src/profiles.ts:25-36
export function landlockProfileArgs(policy: SandboxPolicy): string[] {
  const readWrite = ['/dev/null']
  if (policy.mode === 'workspace-write') {
    readWrite.push('/tmp', policy.workspaceRoot)
  }
  return landlockGrantArgs({ readOnly: ['/'], readWrite })
}
```

同一个文件里,`bwrapProfileArgs` 和 `seatbeltProfileArgs`(macOS 的 Seatbelt 沙箱)与它并列存在——三种后端消费的是同一份 `SandboxPolicy` 抽象,只是各自翻译成自己认识的命令行参数。真正决定"这台机器该用哪个后端"的是 `index.ts` 里的平台选择链：

```ts
// packages/sandbox/sandbox-local/src/index.ts:159-166
const PLATFORM_CHAINS: Record<string, readonly SelectedRunner['runner'][]> = {
  linux: ['bwrap', 'landlock'],
  darwin: ['seatbelt'],
  win32: ['windows-acl'],
}
```

Linux 上 `bwrap` 排在 `landlock` 之前——只有 `bwrap` 探测不可用(权限不足、二进制不存在)时,才会降级尝试 `landlock`。真正拼出 argv 的地方,Landlock 分支就是本篇反复出现的 `[launcherPath(), ...grantArgs(...)]` 模式：

```ts
// packages/sandbox/sandbox-local/src/index.ts:336-344(节选)
private runnerArgv(runner: SelectedRunner['runner'], policy: SandboxPolicy): string[] {
  switch (runner) {
    case 'bwrap': return ['bwrap', ...bwrapProfileArgs(policy)]
    case 'landlock': return [this.landlockLauncher(), ...landlockProfileArgs(policy)]
    case 'seatbelt': return [this.seatbeltExec(), ...seatbeltProfileArgs(policy)]
    case 'windows-acl': return this.windowsAclRunnerArgv(policy)
    default: return assertNever(runner)
  }
}
```

选择 `landlock` 分支前,会先跑一次探测,复用的正是本篇讲过的 `probe()`：

```ts
// packages/sandbox/sandbox-local/src/index.ts:524-527(节选)
case 'landlock': {
  const probe = this.internals.probeLandlock ?? (launcher => defaultProbeLandlock(launcher, { timeoutMs: this.probeTimeoutMs }))
  return probe(this.landlockLauncher())
}
```

`enforcement` 字段(`full`/`partial`/`unusable`)会一路带到最终返回给调用方的 `ConfinedArgv` 结果里,让上层知道"这次沙箱到底是被完整强制,还是只有部分强制"——这也是为什么 `--probe` 的报告行不是调试信息,而是协议的一部分:它直接决定了 dsh 敢不敢把某个高风险操作交给这条沙箱路径去跑。

## 常见问题/易踩坑

- **"这是不是 Rust/Zig 写的?"** 不是。整个沙箱内核只有 `main.c` 一个 C11 源文件,没有 Rust/Zig 工具链参与,`docs/architecture.md` 和 `AGENTS.md` 都反复强调"审计面 = 这一个文件 + 内核稳定契约"这一设计目标,任何额外的语言/运行时都会扩大审计面。
- **"这是不是 N-API 绑定?"** 不是。包名前缀 "node-addon-" 只是沿用了 esbuild 式分发模型的命名习惯,`launcherPath()` 解析出来的是一个文件路径,消费方永远是 `spawn`/`spawnSync`,从未被 `require`/`import` 进 Node 进程。
- **为什么不直接检查 `uname -r` 或者 Landlock 相关的 `/proc` 项?** 因为内核版本号或者某个 feature flag 存在,不代表 Landlock 真的能在这台机器上被启用和强制——`--probe` 选择"真的施加一次规则集"作为唯一诚实的信号来源。
- **规则集施加之后能不能撤销或放宽?** 不能。Landlock 的语义就是"只能收紧,不能放宽",这也是为什么它天然适合"自我限制后再 exec 不可信命令"这种一次性、单向的场景。
- **partial enforcement 是不是意味着不安全?** 不是"不安全",而是"没那么全面"——旧内核 ABI 下没被治理的访问类型(比如 truncate)确实不受这次沙箱限制,但已经协商到的部分依然严格强制;调用方需要根据自己的风险承受度,决定要不要接受 `partial` 结果。

## 小结

`landlock-run` 用不到 300 行手写 C 代码,证明了一个"轻量级、无需特殊权限、可审计"的沙箱后端是可以脱离容器化基础设施独立存在的。它的核心设计哲学可以归纳为三条：**审计面最小化**(纯 C11 直连内核 UAPI,没有中间层)、**fail-closed**(任何不确定的情况都拒绝执行,而不是"降级到不设防")、**诚实的能力声明**(`--probe` 真的测一遍,`full`/`partial`/`unusable` 三态而不是简单的能用/不能用)。在跨语言边界这个主题下,它也是一个很好的反面教材式案例——一个包名可能会误导你以为它是"绑定进宿主语言运行时的原生模块",但真正的边界划分方式,可以简单到只是"启动一个独立可执行文件,靠退出码和 stderr 前缀通信"。
