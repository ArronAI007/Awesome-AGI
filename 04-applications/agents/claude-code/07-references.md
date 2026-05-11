# 七、参考资源

---

## 7.1 官方文档

| 资源 | 链接 | 说明 |
|------|------|------|
| **官方文档首页** | https://code.claude.com/docs | Claude Code 完整文档 |
| **LLMs 文档索引** | https://code.claude.com/docs/llms.txt | 所有文档页面的索引 |
| **快速开始** | https://code.claude.com/docs/en/quickstart | 首次使用指南 |
| **概述** | https://code.claude.com/docs/en/overview | Claude Code 概述 |
| **工作原理** | https://code.claude.com/docs/en/how-claude-code-works | 架构和基本原理 |

---

## 7.2 安装与配置

| 资源 | 链接 | 说明 |
|------|------|------|
| **安装指南** | https://code.claude.com/docs/en/setup | 详细安装说明 |
| **系统要求** | https://code.claude.com/docs/en/setup#system-requirements | 硬件和软件要求 |
| **网络配置** | https://code.claude.com/docs/en/network-config | 代理、CA、mTLS |
| **设置配置** | https://code.claude.com/docs/en/settings | settings.json 配置 |
| **权限配置** | https://code.claude.com/docs/en/permissions | 权限规则和模式 |
| **模型配置** | https://code.claude.com/docs/en/model-config | 模型选择和别名 |
| **故障排除** | https://code.claude.com/docs/en/troubleshoot-install | 安装问题排查 |

---

## 7.3 功能扩展

| 资源 | 链接 | 说明 |
|------|------|------|
| **Skills（技能）** | https://code.claude.com/docs/en/skills | 创建和管理技能 |
| **MCP 集成** | https://code.claude.com/docs/en/mcp | 连接外部工具和服务 |
| **Hooks（钩子）** | https://code.claude.com/docs/en/hooks | 自动化工作流 |
| **Subagents** | https://code.claude.com/docs/en/sub-agents | 子智能体配置 |
| **Agent Teams** | https://code.claude.com/docs/en/agent-teams | 多智能体协作 |
| **Memory（记忆）** | https://code.claude.com/docs/en/memory | CLAUDE.md 和 Auto Memory |

---

## 7.4 工具与命令参考

| 资源 | 链接 | 说明 |
|------|------|------|
| **CLI 参考** | https://code.claude.com/docs/en/cli-reference | 命令行接口完整参考 |
| **命令列表** | https://code.claude.com/docs/en/commands | 会话内 `/` 命令 |
| **工具参考** | https://code.claude.com/docs/en/tools-reference | 内置工具详细说明 |
| **Hooks 参考** | https://code.claude.com/docs/en/hooks | 钩子事件和配置 |

---

## 7.5 平台特定指南

| 资源 | 链接 | 说明 |
|------|------|------|
| **VS Code 扩展** | https://code.claude.com/docs/en/vs-code | VS Code 中使用 Claude Code |
| **JetBrains IDE** | https://code.claude.com/docs/en/jetbrains | IntelliJ、PyCharm 等 |
| **桌面应用** | https://code.claude.com/docs/en/desktop | 桌面应用使用指南 |
| **Chrome 扩展** | https://code.claude.com/docs/en/chrome | Claude in Chrome |
| **Slack 集成** | https://code.claude.com/docs/en/slack | Slack 中使用 |

---

## 7.6 工作流指南

| 资源 | 链接 | 说明 |
|------|------|------|
| **常见工作流** | https://code.claude.com/docs/en/common-workflows | 探索、调试、重构等 |
| **最佳实践** | https://code.claude.com/docs/en/best-practices | 高效使用建议 |
| **Git 工作流** | https://code.claude.com/docs/en/git-workflow | 与 Git 协作 |
| **Worktrees** | https://code.claude.com/docs/en/worktrees | 并行会话 |
| **计划模式** | https://code.claude.com/docs/en/permission-modes | Plan Mode 详解 |

---

## 7.7 企业部署

| 资源 | 链接 | 说明 |
|------|------|------|
| **Managed Settings** | https://code.claude.com/docs/en/server-managed-settings | 企业级配置管理 |
| **数据使用** | https://code.claude.com/docs/en/data-usage | 隐私和遥测 |
| **第三方集成** | https://code.claude.com/docs/en/third-party-integrations | Bedrock、Vertex 等 |
| **GitHub Actions** | https://code.claude.com/docs/en/github-actions | CI/CD 集成 |
| **GitLab CI/CD** | https://code.claude.com/docs/en/gitlab-ci-cd | GitLab 集成 |

---

## 7.8 下载与更新

| 资源 | 链接 | 说明 |
|------|------|------|
| **桌面应用下载** | https://claude.com/download | macOS / Windows 桌面版 |
| **VS Code 扩展** | vscode:extension/anthropic.claude-code | VS Code 市场 |
| **Open VSX** | https://open-vsx.org/extension/Anthropic/claude-code | 开源 VS Code 注册表 |
| **定价页面** | https://claude.com/pricing | Claude 订阅方案 |
| **Anthropic Console** | https://console.anthropic.com | API 管理和计费 |

---

## 7.9 社区与支持

| 资源 | 链接 | 说明 |
|------|------|------|
| **Anthropic 支持国家** | https://www.anthropic.com/supported-countries | 服务可用地区 |
| **API IP 地址** | https://platform.claude.com/docs/en/api/ip-addresses | 防火墙配置参考 |
| **Agent Skills 标准** | https://agentskills.io | 跨工具的 Skill 标准 |

---

## 7.10 速查卡

### 安装速查

```bash
# macOS / Linux / WSL
curl -fsSL https://claude.ai/install.sh | bash

# Windows PowerShell
irm https://claude.ai/install.ps1 | iex

# Homebrew
brew install --cask claude-code

# WinGet
winget install Anthropic.ClaudeCode
```

### 启动速查

```bash
claude                          # 启动会话
claude "prompt"                 # 带提示启动
claude -p "prompt"              # SDK 模式
claude -c                       # 继续会话
claude --model opus             # 指定模型
claude --worktree               # 隔离工作树
```

### 认证速查

```bash
claude auth login               # 登录
claude auth login --console     # API 模式
claude auth logout              # 登出
claude auth status              # 查看状态
```

### 常用会话命令

```
/help          # 查看命令
/clear         # 清空上下文
/compact       # 压缩历史
/context       # 查看上下文使用
/model         # 切换模型
/plan          # 计划模式
/diff          # 查看更改
/init          # 生成 CLAUDE.md
/mcp           # 管理 MCP
/agents        # 管理子智能体
```

---

> 📝 **笔记日期**：2026-05-11
> 📌 **版本**：基于 Claude Code 最新官方文档整理
> 🔄 **维护建议**：定期查看官方文档更新，特别是 [LLMs 文档索引](https://code.claude.com/docs/llms.txt) 获取新页面
