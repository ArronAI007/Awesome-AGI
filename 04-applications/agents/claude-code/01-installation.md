# 一、安装

---

## 1.1 Claude Code 简介

**Claude Code** 是 Anthropic 推出的智能体（Agentic）编程工具，直接在终端运行，能够读取代码库、编辑文件、执行命令，并与开发工具深度集成。它基于 Claude 大语言模型，通过内置的工具链和智能体循环（Agentic Loop）将自然语言指令转化为实际的代码操作。

Claude Code 不仅限于终端 CLI，还支持多种运行环境：

| 运行环境 | 特点 |
|---------|------|
| **终端 CLI** | 功能最完整，直接集成到开发工作流 |
| **VS Code 扩展** | 提供内联 diff、@-提及、计划审查和会话历史 |
| **JetBrains IDE** | 在 IntelliJ、PyCharm 等 IDE 中使用 |
| **桌面应用** | 无需终端即可使用的图形界面 |
| **浏览器** | 通过 claude.ai/code 访问 |
| **Slack** | 在 Slack 中集成 Claude Code |
| **CI/CD** | GitHub Actions、GitLab CI/CD 集成 |

---

## 1.2 系统要求

### 1.2.1 基础要求

| 项目 | 要求 |
|------|------|
| **操作系统** | macOS 13.0+ / Windows 10 1809+ / Windows Server 2019+ / Ubuntu 20.04+ / Debian 10+ / Alpine Linux 3.19+ |
| **硬件** | 4 GB+ RAM，x64 或 ARM64 处理器 |
| **网络** | 需要互联网连接 |
| **Shell** | Bash、Zsh、PowerShell 或 CMD |
| **额外依赖** | ripgrep（通常已内置） |

### 1.2.2 网络访问要求

Claude Code 需要访问以下域名：

| URL | 用途 |
|-----|------|
| `api.anthropic.com` | Claude API 请求 |
| `claude.ai` | 账号认证 |
| `platform.claude.com` | Anthropic Console 账号认证 |
| `downloads.claude.ai` | 插件下载、原生安装和自动更新 |
| `storage.googleapis.com` | 旧版本（<2.1.116）的安装包下载 |
| `bridge.claudeusercontent.com` | Claude in Chrome 扩展 WebSocket |
| `raw.githubusercontent.com` | 发布说明和更新日志 |

如果使用第三方提供商（Bedrock、Vertex、Foundry），模型流量会路由到对应提供商而非 `api.anthropic.com`。

### 1.2.3 企业网络配置

**代理服务器配置：**
```bash
# HTTPS 代理（推荐）
export HTTPS_PROXY=https://proxy.example.com:8080

# HTTP 代理
export HTTP_PROXY=http://proxy.example.com:8080

# 绕过代理
export NO_PROXY="localhost,192.168.1.1,example.com"
```

> ⚠️ 不支持 SOCKS 代理。

**自定义 CA 证书：**
```bash
export NODE_EXTRA_CA_CERTS=/path/to/ca-cert.pem
```

**mTLS 认证：**
```bash
export CLAUDE_CODE_CLIENT_CERT=/path/to/client-cert.pem
export CLAUDE_CODE_CLIENT_KEY=/path/to/client-key.pem
export CLAUDE_CODE_CLIENT_KEY_PASSPHRASE="your-passphrase"
```

---

## 1.3 安装方式

### 1.3.1 方式一：原生安装（推荐）

原生安装支持**后台自动更新**，始终保持最新版本。

**macOS / Linux / WSL：**
```bash
curl -fsSL https://claude.ai/install.sh | bash
```

**Windows PowerShell：**
```powershell
irm https://claude.ai/install.ps1 | iex
```

**Windows CMD：**
```batch
curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd && del install.cmd
```

> 💡 **提示**：如果看到 `The token '&&' is not a valid statement separator`，说明你在 PowerShell 中而非 CMD。如果看到 `'irm' is not recognized`，说明你在 CMD 中而非 PowerShell。PowerShell 提示符显示 `PS C:\`，CMD 不显示 `PS`。

**特点：**
- ✅ 后台自动更新
- ✅ 无需手动维护版本
- ✅ 最新功能和安全补丁即时可用

---

### 1.3.2 方式二：Homebrew（macOS）

```bash
# 稳定版（约晚一周，跳过有严重回归的版本）
brew install --cask claude-code

# 最新版（即时获取新版本）
brew install --cask claude-code@latest
```

**特点：**
- ❌ 不会自动更新
- 需手动运行 `brew upgrade claude-code` 或 `brew upgrade claude-code@latest`

---

### 1.3.3 方式三：WinGet（Windows）

```powershell
winget install Anthropic.ClaudeCode
```

**特点：**
- ❌ 不会自动更新
- 需手动运行 `winget upgrade Anthropic.ClaudeCode`

---

### 1.3.4 方式四：Linux 包管理器

```bash
# Debian/Ubuntu
sudo apt install claude-code

# Fedora/RHEL
sudo dnf install claude-code

# Alpine Linux（需 libgcc、libstdc++、ripgrep）
sudo apk add claude-code
```

---

### 1.3.5 安装特定版本

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

## 1.4 启动与登录

### 1.4.1 启动交互式会话

```bash
# 进入项目目录并启动
cd your-project
claude

# 首次使用会提示登录
```

### 1.4.2 账号类型

Claude Code 支持以下账号类型：

| 账号类型 | 说明 |
|---------|------|
| **Claude Pro / Max / Team / Enterprise** | 推荐，通过 Claude 订阅使用 |
| **Anthropic Console** | API 访问，预付费积分。首次登录自动创建 "Claude Code" 工作区用于成本追踪 |
| **第三方提供商** | Amazon Bedrock、Google Vertex AI、Microsoft Foundry |

### 1.4.3 认证命令

```bash
# 登录
claude auth login

# 使用邮箱预填
claude auth login --email your@email.com

# 强制 SSO 认证
claude auth login --sso

# 使用 Anthropic Console（API 计费）
claude auth login --console

# 登出
claude auth logout

# 查看认证状态（JSON 格式）
claude auth status
```

登录后，凭证会存储在系统中，无需重复登录。切换账号使用 `/login` 命令。

---

## 1.5 Windows 特殊配置

### 1.5.1 运行选项对比

| 选项 | 要求 | 沙盒支持 | 适用场景 |
|------|------|---------|---------|
| **原生 Windows** | 推荐安装 Git for Windows | ❌ 不支持 | Windows 原生项目和工具 |
| **WSL 2** | 启用 WSL 2 | ✅ 支持 | Linux 工具链或沙盒命令执行 |
| **WSL 1** | 启用 WSL 1 | ❌ 不支持 | WSL 2 不可用时的备选 |

### 1.5.2 Git for Windows 配置

Git for Windows 推荐安装，Claude Code 内部使用 Bash 工具执行命令。

```bash
# 在 settings.json 中指定 Git Bash 路径
{
  "env": {
    "CLAUDE_CODE_GIT_BASH_PATH": "C:\\Program Files\\Git\\bin\\bash.exe"
  }
}
```

**PowerShell 工具选择：**
```bash
# 启用 PowerShell 工具（渐进推出中）
export CLAUDE_CODE_USE_POWERSHELL_TOOL=1

# 禁用 PowerShell 工具
export CLAUDE_CODE_USE_POWERSHELL_TOOL=0
```

### 1.5.3 Alpine Linux 特殊依赖

Alpine 和其他 musl/uClibc 发行版需要：
```bash
# 安装必要依赖
apk add libgcc libstdc++ ripgrep
```

---

## 1.6 版本管理

### 1.6.1 更新命令

```bash
# 更新到最新版本
claude update

# 查看当前版本
claude --version

# 安装特定版本
claude install <version>
```

### 1.6.2 更新渠道

| 渠道 | 说明 | 获取方式 |
|------|------|---------|
| **Stable（稳定版）** | 约晚一周，跳过有严重回归的版本 | `claude install stable` / Homebrew `claude-code` |
| **Latest（最新版）** | 即时获取所有新版本 | `claude install latest` / Homebrew `claude-code@latest` |

---

## 1.7 卸载

```bash
# macOS / Linux
rm -rf ~/.claude
rm $(which claude)

# 或使用安装器的卸载功能
# 具体命令参考官方文档
```

---

## 1.8 安装故障排除

### 常见问题

| 问题 | 解决方案 |
|------|---------|
| 安装脚本执行失败 | 检查网络连接，确认 `curl` 可用 |
| Windows 上 `&&` 错误 | 确认在正确的 shell 中运行对应命令 |
| 认证失败 | 检查网络防火墙，确认 `claude.ai` 和 `api.anthropic.com` 可访问 |
| 搜索失败 | 确认 `ripgrep` 已安装 |
| 权限不足 | 原生安装不需要管理员权限 |

更多故障排除信息请参考官方文档的 [Troubleshoot installation and login](https://code.claude.com/docs/en/troubleshoot-install)。
