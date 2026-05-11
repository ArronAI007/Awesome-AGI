# 二、常用命令

---

## 2.1 基础命令

### 2.1.1 启动会话

| 命令 | 说明 | 示例 |
|------|------|------|
| `claude` | 启动交互式会话 | `claude` |
| `claude "query"` | 带初始提示启动会话 | `claude "explain this project"` |
| `claude -p "query"` | SDK 模式：执行查询后退出 | `claude -p "explain this function"` |
| `cat file \| claude -p "query"` | 管道输入处理 | `cat logs.txt \| claude -p "explain errors"` |

**SDK 模式（`-p`）的特点：**
- 执行完查询后自动退出
- 适合脚本化和自动化场景
- 不支持交互式对话
- 可以处理管道输入

### 2.1.2 启动时指定模型

```bash
# 使用指定模型启动
claude --model opus
claude --model sonnet
claude --model haiku

# 使用 1M 上下文窗口
claude --model sonnet[1m]
claude --model opus[1m]

# 使用 opusplan（计划模式用 opus，执行用 sonnet）
claude --model opusplan
```

### 2.1.3 添加工作目录

```bash
# 添加额外的工作目录（当前会话有效）
claude --add-dir /path/to/another/project
```

> ⚠️ 添加的目录中的 `.claude/` 配置**不会被自动发现**。

---

## 2.2 会话管理

### 2.2.1 继续会话

| 命令 | 说明 | 示例 |
|------|------|------|
| `claude -c` | 继续当前目录最近的对话 | `claude -c` |
| `claude -c -p "query"` | 继续会话并以 SDK 模式执行 | `claude -c -p "Check for type errors"` |
| `claude --continue` | 同 `-c` | `claude --continue` |
| `claude --resume` | 同 `-c` | `claude --resume` |

### 2.2.2 恢复指定会话

```bash
# 按会话 ID 或名称恢复
claude -r "auth-refactor" "Finish this PR"
claude --resume "session-id" "Continue the task"
```

### 2.2.3 从 PR 恢复会话

```bash
# 从 GitHub PR 恢复会话
claude --from-pr 123
claude --from-pr https://github.com/user/repo/pull/123
```

使用 `gh pr create` 创建 PR 时，会话会自动链接到该 PR。

---

## 2.3 版本与安装管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `claude update` | 更新到最新版本 | `claude update` |
| `claude install [version]` | 安装/重装指定版本 | `claude install stable` |
| `claude --version` | 查看当前版本 | `claude --version` |
| `claude --help` | 查看帮助信息 | `claude --help` |

### 安装版本选项

```bash
# 安装稳定版
claude install stable

# 安装最新版
claude install latest

# 安装指定版本
claude install 2.1.118

# 重新安装当前版本
claude install
```

---

## 2.4 认证管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `claude auth login` | 登录 Anthropic 账号 | `claude auth login` |
| `claude auth logout` | 登出 | `claude auth logout` |
| `claude auth status` | 查看认证状态（JSON） | `claude auth status` |

### 登录选项

```bash
# 预填邮箱地址
claude auth login --email your@email.com

# 强制 SSO 认证
claude auth login --sso

# 使用 Anthropic Console（API 计费）
claude auth login --console
```

---

## 2.5 会话内命令（以 `/` 开头）

在 Claude Code 交互式会话中，可以使用 `/` 开头的命令控制会话行为。

### 2.5.1 会话生命周期命令

| 命令 | 说明 |
|------|------|
| `/clear` | 清空当前会话上下文，开始新任务（保留项目记忆） |
| `/compact` | 压缩会话历史，总结关键信息以节省上下文窗口 |
| `/context` | 显示当前上下文窗口使用情况 |
| `/resume` | 恢复之前的会话 |
| `/branch` | 从当前会话创建分支（分叉对话） |
| `/rewind` | 回滚到指定的检查点 |

### 2.5.2 模型与配置命令

| 命令 | 说明 |
|------|------|
| `/model [name]` | 切换模型，不带参数打开选择器 |
| `/effort` | 调整推理强度 |
| `/config` | 打开设置界面 |
| `/permissions` | 管理权限规则 |
| `/settings` | 查看/编辑设置 |

### 2.5.3 项目与代码命令

| 命令 | 说明 |
|------|------|
| `/init` | 自动生成 CLAUDE.md |
| `/memory` | 查看/编辑记忆 |
| `/diff` | 查看未提交的更改 |
| `/simplify` | 审查近期文件并应用质量和效率优化 |
| `/review` | 对代码进行深度只读审查 |
| `/security-review` | 安全审查 |
| `/plan` | 进入计划模式 |

### 2.5.4 扩展与集成命令

| 命令 | 说明 |
|------|------|
| `/mcp` | 管理 MCP 服务器 |
| `/agents` | 管理子智能体配置 |
| `/skills` | 管理技能 |
| `/hooks` | 管理钩子 |

### 2.5.5 实用工具命令

| 命令 | 说明 |
|------|------|
| `/help` | 查看可用命令 |
| `/doctor` | 诊断安装和运行时问题 |
| `/debug` | 调试模式 |
| `/feedback` | 提交反馈（附带会话上下文） |
| `/btw` | 快速旁注（不膨胀历史记录） |
| `/statusline` | 配置状态行 |
| `/release-notes` | 查看发布说明 |

### 2.5.6 批量与自动化命令

| 命令 | 说明 |
|------|------|
| `/batch <instruction>` | 大规模批量修改代码库（Skill） |
| `/loop <instruction>` | 循环执行直到完成（Skill） |
| `/autofix-pr [prompt]` | 自动修复 PR 中的 CI 失败和审查意见 |

### 2.5.7 特殊模式命令

```bash
# 仅初始化（用于 CI 或脚本）
claude --init-only

# 初始化并进入维护模式
claude --init
claude --maintenance

# 创建隔离的 git worktree
claude --worktree
```

---

## 2.6 环境变量

### 2.6.1 常用环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | `sk-ant-...` |
| `ANTHROPIC_MODEL` | 默认模型 | `sonnet` / `opus` |
| `ANTHROPIC_BASE_URL` | API 基础 URL（用于 LLM 网关） | `https://gateway.example.com` |
| `HTTPS_PROXY` | HTTPS 代理 | `https://proxy:8080` |
| `HTTP_PROXY` | HTTP 代理 | `http://proxy:8080` |
| `NO_PROXY` | 绕过代理的地址 | `localhost,192.168.1.1` |
| `CLAUDE_CODE_CERT_STORE` | 证书存储源 | `bundled,system` |
| `CLAUDE_CODE_CLIENT_CERT` | mTLS 客户端证书 | `/path/to/cert.pem` |
| `CLAUDE_CODE_CLIENT_KEY` | mTLS 客户端私钥 | `/path/to/key.pem` |

### 2.6.2 模型相关环境变量

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Sonnet 别名解析到的具体模型 |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | Opus 别名解析到的具体模型 |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | Haiku 别名解析到的具体模型 |

---

## 2.7 命令速查表

### 启动与会话

```bash
claude                          # 启动交互式会话
claude "prompt"                 # 带初始提示启动
claude -p "prompt"              # SDK 模式
claude -c                       # 继续最近会话
claude -r "name" "prompt"       # 恢复指定会话
claude --from-pr 123            # 从 PR 恢复
claude --model opus             # 指定模型启动
claude --add-dir /path          # 添加工作目录
```

### 认证

```bash
claude auth login               # 登录
claude auth login --console     # Console 登录
claude auth logout              # 登出
claude auth status              # 查看状态
```

### 版本管理

```bash
claude update                   # 更新
claude install stable           # 安装稳定版
claude install latest           # 安装最新版
claude install 2.1.118          # 安装指定版本
claude --version                # 查看版本
```
