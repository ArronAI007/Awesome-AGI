# 四、基本原理

---

## 4.1 智能体循环的工作原理

### 4.1.1 核心机制

Claude Code 的核心工作原理是一个**持续迭代的思想-行动-观察**循环：

```
用户输入
   │
   ▼
┌─────────────────────────────┐
│  Claude 推理（Thought）      │
│  - 理解用户意图              │
│  - 评估当前状态              │
│  - 决定下一步行动            │
└─────────────────────────────┘
   │
   ▼
┌─────────────────────────────┐
│  工具调用（Action）           │
│  - 选择合适工具              │
│  - 构建工具参数              │
│  - 执行工具                  │
└─────────────────────────────┘
   │
   ▼
┌─────────────────────────────┐
│  观察结果（Observation）      │
│  - 获取工具输出              │
│  - 分析执行结果              │
│  - 判断任务进度              │
└─────────────────────────────┘
   │
   ▼
  任务完成？──否──→ 继续循环
     │
    是
     ▼
  返回结果给用户
```

### 4.1.2 循环执行示例：修复 Bug

**场景**：用户说 "修复用户登录失败的问题"

```
【第 1 轮】
Thought: 用户报告登录失败，我需要先了解问题
Action: Bash("npm test -- --grep login")
Observation: 测试输出显示 3 个测试失败，错误信息：
             "TypeError: Cannot read property 'hash' of undefined"

【第 2 轮】
Thought: 错误指向 password.hash 为 undefined，可能是用户对象缺少 password 字段
Action: Grep("password\\.hash", "src/")
Observation: 找到 5 个匹配文件，其中 auth.service.ts 第 42 行使用 user.password.hash

【第 3 轮】
Thought: 需要查看 auth.service.ts 的完整上下文
Action: Read("src/auth/auth.service.ts")
Observation: 文件内容显示... 第 42 行直接访问 user.password.hash，
             但 User 类型定义中 password 是可选字段

【第 4 轮】
Thought: 需要检查 User 模型和登录流程
Action: Read("src/user/user.entity.ts")
Observation: password 字段标记为 optional (?)

【第 5 轮】
Thought: 应该在访问 password.hash 前做空值检查
Action: Edit("src/auth/auth.service.ts", 42, 
             "if (!user.password) throw new UnauthorizedException();")
Observation: 编辑成功，文件已更新

【第 6 轮】
Thought: 修改后需要验证修复
Action: Bash("npm test -- --grep login")
Observation: 所有登录测试通过 ✓

【第 7 轮】
Thought: 修复完成，可以告知用户
→ 返回结果：已修复登录失败问题...
```

### 4.1.3 循环的决策逻辑

Claude 在每次循环中基于以下因素做决策：

1. **用户原始请求** —— 最终目标是什么
2. **已收集的信息** —— 目前知道了什么
3. **前一步的结果** —— 上一步成功还是失败
4. **上下文窗口状态** —— 还有多少空间
5. **工具可用性** —— 哪些工具可以调用

---

## 4.2 上下文管理

### 4.2.1 上下文窗口机制

Claude Code 使用 Claude 模型的**上下文窗口**来维护对话状态：

- 标准上下文窗口：约 200K tokens
- 扩展上下文窗口（`[1m]` 模型）：1M tokens
- 上下文窗口包含：系统提示、CLAUDE.md、对话历史、工具调用记录

### 4.2.2 上下文加载策略

```
会话启动时的上下文加载顺序：

1. 系统提示（固定）
2. 管理策略 CLAUDE.md（如存在）
3. 用户级 CLAUDE.md（~/.claude/CLAUDE.md）
4. 项目级 CLAUDE.md（./CLAUDE.md）
5. Auto Memory（前 200 行或 25KB）
6. 本地 CLAUDE.local.md（如存在）
7. 用户输入的历史消息
8. 当前对话消息
```

### 4.2.3 按需加载机制

为了避免上下文窗口被撑满，Claude Code 采用**按需加载**：

- **启动时加载**：项目根目录的 CLAUDE.md、用户级 CLAUDE.md
- **按需加载**：子目录中的 CLAUDE.md 和规则文件，在 Claude 读取该目录文件时加载
- **惰性加载**：工具调用结果、文件内容按需读入上下文

### 4.2.4 上下文压缩

当上下文接近上限时：

- `/compact` 命令可以总结历史对话，释放空间
- 旧的工具调用结果可能被摘要替代
- 用户可以手动 `/clear` 开始新任务

---

## 4.3 模型选择原理

### 4.3.1 模型别名解析

Claude Code 使用**模型别名**简化模型选择：

| 别名 | API 解析 | 第三方解析 |
|------|---------|-----------|
| `sonnet` | Sonnet 4.6 | Sonnet 4.5 |
| `opus` | Opus 4.7 | Opus 4.6 |
| `haiku` | 最新 Haiku | 最新 Haiku |

别名会随着新模型发布而自动更新。要固定到特定版本，使用完整模型名称（如 `claude-opus-4-7`）或设置环境变量。

### 4.3.2 opusplan 模式

`opusplan` 是一个特殊的模型配置：

- **计划阶段**：使用 `opus` 进行深度分析和计划制定
- **执行阶段**：自动切换到 `sonnet` 执行具体修改

这种模式平衡了计划质量和执行效率。

### 4.3.3 模型选择优先级

```
1. 会话中 /model 命令（最高优先级，保存到本地设置）
2. 启动参数 --model
3. 环境变量 ANTHROPIC_MODEL
4. 本地设置 .claude/settings.local.json
5. 项目设置 .claude/settings.json
6. 用户设置 ~/.claude/settings.json
7. 系统默认值
```

### 4.3.4 企业模型控制

企业管理员可以通过 `availableModels` 限制用户可选模型：

```json
{
  "availableModels": ["sonnet", "haiku"]
}
```

即使设置了 `availableModels: []`，用户仍可使用 Default 模型。

---

## 4.4 权限系统原理

### 4.4.1 权限层级

Claude Code 使用**三层权限系统**：

| 层级 | 行为 | 示例 |
|------|------|------|
| **只读（Read-only）** | 无需批准，直接执行 | Read、Glob、Grep、WebSearch |
| **询问（Ask）** | 首次使用时询问，可记住选择 | Bash、Edit |
| **拒绝（Deny）** | 完全禁止 | 在 settings.json 中配置的禁止项 |

### 4.4.2 权限模式

Claude Code 支持多种权限模式：

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `default` | 标准行为：首次使用工具时提示 | 日常使用 |
| `acceptEdits` | 自动接受文件编辑和常见文件系统命令 | 快速开发 |
| `plan` | 计划模式：只读探索，不修改源文件 | 审查和规划 |
| `auto` | 自动批准工具调用（带后台安全检查） | 研究预览 |
| `dontAsk` | 除非预先批准，否则拒绝工具 | 严格限制 |
| `bypassPermissions` | 跳过所有权限提示（危险！） | 隔离环境（容器/VM） |

### 4.4.3 权限规则语法

权限规则使用 `Tool` 或 `Tool(specifier)` 格式：

```json
{
  "permissions": {
    "allow": [
      "Bash(npm run *)",
      "Bash(git commit *)",
      "Read(./.env)"
    ],
    "deny": [
      "Bash(git push *)",
      "Bash(rm -rf *)"
    ],
    "ask": [
      "Bash(docker *)"
    ]
  }
}
```

**规则匹配优先级**：`deny` → `ask` → `allow`，第一个匹配的规则生效。

**通配符规则：**
- `Bash(npm run *)` —— 匹配所有以 `npm run ` 开头的命令
- `Bash(* --version)` —— 匹配所有以 ` --version` 结尾的命令
- `Bash(git * main)` —— 匹配 `git checkout main`、`git log main` 等

### 4.4.4 Bash 权限的特殊行为

| 行为 | 说明 |
|------|------|
| "Yes, don't ask again" | 对同一命令前缀永久记住（按项目目录） |
| 编辑权限 | 仅在当前会话内记住 |
| 首次执行 | 总是询问确认 |

---

## 4.5 记忆系统原理

### 4.5.1 双记忆系统

Claude Code 有两种互补的记忆机制：

| | CLAUDE.md | Auto Memory |
|--|-----------|-------------|
| **作者** | 用户 | Claude |
| **内容** | 指令和规则 | 学习到的模式 |
| **范围** | 项目/用户/组织 | 每个工作树 |
| **加载量** | 完整加载 | 前 200 行或 25KB |
| **用途** | 指导行为 | 自动优化 |

### 4.5.2 CLAUDE.md 编写原则

**应该写入的内容：**
- 构建和测试命令
- 编码标准和约定
- 项目架构决策
- 命名规范
- 常见工作流
- "总是做 X" 的规则

**不应该写入的内容：**
- 多步骤流程（应使用 Skill）
- 仅适用于代码库某部分的规则（应使用 path-scoped rules）
- 临时的、一次性的指令

### 4.5.3 Auto Memory 工作原理

Auto Memory 让 Claude 自动记录学习到的内容：

- Claude 根据你的纠正和偏好自动写笔记
- 存储在工作树的 `.claude/` 目录中
- 每次会话加载前 200 行或 25KB
- 子智能体也可以有自己的 Auto Memory

---

## 4.6 与用户的协作模式

### 4.6.1 自主执行

Claude 可以独立完成任务的大部分步骤：
- 自主搜索和阅读文件
- 自主编辑代码
- 自主运行测试和命令
- 自主决策下一步行动

### 4.6.2 用户介入点

用户可以在以下时刻介入：

| 时机 | 方式 |
|------|------|
| 权限请求 | 批准或拒绝工具调用 |
| 计划审查 | `/plan` 模式下审查计划 |
| 中途纠正 | 随时输入新指令 |
| 结果验证 | 检查修改后的代码 |
| 多选提问 | `AskUserQuestion` 工具 |

### 4.6.3 计划模式

对于复杂任务，可以先进入计划模式：

1. 用户输入 `/plan` 或 Claude 自动进入
2. Claude 只使用只读工具探索代码库
3. 制定详细的执行计划
4. 用户审查并批准计划
5. 退出计划模式，按计划执行

---

## 4.7 Git 集成原理

### 4.7.1 自动感知的 Git 状态

Claude Code 启动时自动获取：
- 当前分支
- 未提交的更改（staged/unstaged）
- 近期提交历史
- 远程仓库信息

### 4.7.2 Git 工作树隔离

使用 `--worktree` 参数可以创建隔离的 git worktree：

```bash
claude --worktree
```

这会在独立的 worktree 中运行 Claude，避免与主工作目录冲突，支持并行开发。

### 4.7.3 会话与 PR 关联

使用 `gh pr create` 创建 PR 时，会话自动链接到该 PR。后续可以通过 `--from-pr` 恢复。

---

## 4.8 代码智能原理

### 4.8.1 LSP 集成

Claude Code 通过 Language Server Protocol (LSP) 获得代码智能能力：

- **定义跳转**：快速定位符号定义
- **引用查找**：查找所有引用位置
- **类型检查**：实时类型错误和警告
- **符号信息**：获取符号的文档和类型

### 4.8.2 代码探索策略

Claude 使用多种策略理解代码库：

1. **目录结构分析** —— 了解项目组织
2. **关键文件识别** —— 找到入口点、配置文件
3. **依赖关系追踪** —— 通过 import/require 追踪模块关系
4. **类型定义阅读** —— 理解数据模型
5. **测试文件分析** —— 通过测试了解预期行为
