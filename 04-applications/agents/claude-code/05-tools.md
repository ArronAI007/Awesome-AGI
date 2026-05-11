# 五、核心工具详解

---

## 5.1 工具概述

Claude Code 的强大能力来源于其丰富的内置工具集。这些工具让 Claude 从"只能说话"的聊天机器人转变为"能够动手"的编程助手。每个工具都有特定的用途，Claude 会根据任务需求自动选择最合适的工具组合。

**工具使用原则：**
- 只读工具无需用户批准，直接执行
- 修改类工具需要用户授权
- 工具调用结果会反馈到 Agentic Loop 中，影响下一步决策
- 工具可以组合使用，形成复杂的操作链

---

## 5.2 文件操作类工具

### 5.2.1 Read（读取文件）

**功能**：读取指定文件的内容

**权限要求**：无需批准

**使用场景**：
- 查看代码文件内容
- 阅读配置文件
- 查看日志输出
- 理解项目结构

**示例**：
```
Read("src/app.ts")
Read("package.json")
Read("README.md")
```

**特点**：
- 支持读取文本文件
- 可以指定读取的行范围
- 自动检测文件编码

---

### 5.2.2 Edit（编辑文件）

**功能**：对文件进行精确的、有针对性的编辑

**权限要求**：需要用户批准

**使用场景**：
- 修改代码逻辑
- 修复 bug
- 添加新功能
- 重构代码

**示例**：
```
Edit("src/app.ts", 15, "import { newFeature } from './features';")
```

**特点**：
- 精确到行级别的编辑
- 支持多行修改
- 编辑后会显示 diff 供用户确认
- 支持批量编辑

**"Yes, don't ask again"行为**：
- 文件编辑权限在当前会话内记住
- 会话结束后需要重新授权

---

### 5.2.3 Write（创建文件）

**功能**：创建新文件

**权限要求**：需要用户批准

**使用场景**：
- 创建新模块
- 添加配置文件
- 生成测试文件
- 创建文档

**示例**：
```
Write("src/new-module.ts", "export function hello() { return 'world'; }")
```

---

### 5.2.4 Glob（文件查找）

**功能**：按 glob 模式查找文件

**权限要求**：无需批准

**使用场景**：
- 查找特定类型的文件
- 批量定位文件
- 探索项目结构

**示例**：
```
Glob("src/**/*.ts")
Glob("**/*.test.js")
Glob("*.config.*")
```

**特点**：
- 支持标准 glob 语法
- 可递归搜索
- 支持排除模式

---

### 5.2.5 Grep（内容搜索）

**功能**：在文件内容中搜索正则表达式

**权限要求**：无需批准

**使用场景**：
- 查找特定函数或变量
- 定位代码引用
- 搜索错误信息
- 发现重复代码

**示例**：
```
Grep("class UserController", "src/")
Grep("TODO|FIXME|HACK", "src/")
Grep("async function", "src/services/")
```

**特点**：
- 支持正则表达式
- 可限制搜索目录
- 返回匹配的文件和行号

---

## 5.3 执行类工具

### 5.3.1 Bash（Shell 命令）

**功能**：执行 shell 命令

**权限要求**：需要用户批准

**使用场景**：
- 运行测试套件
- 编译代码
- 执行 Git 操作
- 启动开发服务器
- 安装依赖
- 运行脚本

**示例**：
```
Bash("npm test")
Bash("git status")
Bash("python manage.py migrate")
Bash("docker compose up")
```

**Bash 工具行为详解：**

| 特性 | 说明 |
|------|------|
| 默认 Shell | Bash（Linux/macOS），PowerShell（Windows 可选） |
| 长时间运行 | 支持，适用于服务器启动等 |
| 交互式命令 | 通过 PTY 支持 |
| 环境继承 | 继承 Claude Code 启动时的环境变量 |
| 沙盒支持 | WSL 2 支持沙盒执行 |
| 输出反馈 | 命令输出返回给 Claude，影响下一步决策 |

**权限记忆机制：**

| 操作 | 记忆范围 |
|------|---------|
| "Yes" | 该命令在当前会话中记住 |
| "Yes, don't ask again" | 该命令前缀在当前项目目录永久记住 |
| "No" | 拒绝执行 |

---

### 5.3.2 CronCreate / CronDelete / CronList（定时任务）

**功能**：管理会话内的定时任务

**权限要求**：无需批准

**使用场景**：
- 定期执行检查
- 定时提醒
- 后台监控

**示例**：
```
CronCreate("每30分钟检查测试状态", "*/30 * * * *", "run tests")
CronList()
CronDelete("task-id")
```

**特点**：
- 任务是会话范围的
- 使用 cron 表达式
- `--resume` 或 `--continue` 时恢复未过期的任务

---

## 5.4 Web 类工具

### 5.4.1 WebSearch（网页搜索）

**功能**：搜索网络获取信息

**权限要求**：无需批准

**使用场景**：
- 查找最新文档
- 搜索错误解决方案
- 了解第三方库用法
- 获取最新技术信息

**示例**：
```
WebSearch("React 19 new features")
WebSearch("TypeScript strict mode migration guide")
```

**特点**：
- 使用搜索引擎获取结果
- 返回摘要和相关链接
- 适合快速查找信息

---

### 5.4.2 WebFetch（网页获取）

**功能**：获取特定网页的完整内容

**权限要求**：无需批准

**使用场景**：
- 阅读技术文档
- 查看 API 参考
- 获取错误详情页面

**示例**：
```
WebFetch("https://docs.example.com/api")
```

**特点**：
- 获取网页的完整文本内容
- 调用前会进行域名安全检查
- 可通过 `skipWebFetchPreflight: true` 跳过安全检查

---

## 5.5 代码智能类工具

### 5.5.1 LSP（Language Server Protocol）

**功能**：通过语言服务器提供代码智能

**权限要求**：无需批准

**子功能**：

| 子功能 | 说明 |
|--------|------|
| Go to Definition | 跳转到符号定义 |
| Find References | 查找所有引用 |
| Type Errors | 类型错误和警告报告 |
| Hover Info | 符号信息和文档 |

**使用场景**：
- 精确导航大型代码库
- 理解类型系统
- 查找符号使用位置
- 检查代码问题

**示例**：
```
LSP("definition", "src/app.ts", 42, 15)
LSP("references", "src/user.ts", "UserService")
LSP("diagnostics", "src/auth.ts")
```

**前提条件**：
- 需要安装对应语言的 code intelligence plugin
- 语言服务器需要在项目中可用

---

## 5.6 编排与交互类工具

### 5.6.1 Agent（子智能体）

**功能**：生成子智能体处理特定任务

**权限要求**：无需批准

**使用场景**：
- 委派复杂子任务
- 保持主会话上下文干净
- 并行处理多个任务
- 使用专门的提示和工具限制

**示例**：
```
Agent("explore", "Find all API endpoints in this project")
Agent("review", "Review the auth module for security issues")
```

**内置子智能体：**

| 子智能体 | 模型 | 工具限制 | 用途 |
|---------|------|---------|------|
| Explore | Haiku | 只读 | 代码库搜索和探索 |
| Plan | 继承主会话 | 只读 | 计划模式下的研究 |
| General-purpose | 继承主会话 | 全部 | 复杂多步骤任务 |

**特点**：
- 每个子智能体有自己的上下文窗口
- 可以配置自定义系统提示
- 可以限制可用工具
- 子智能体不能嵌套（不能创建子智能体的子智能体）

---

### 5.6.2 AskUserQuestion（询问用户）

**功能**：向用户询问多选题或需要澄清的问题

**权限要求**：无需批准

**使用场景**：
- 遇到歧义时澄清需求
- 让用户选择实现方案
- 确认关键决策

**示例**：
```
AskUserQuestion("Which approach do you prefer?", [
  "A. Use async/await",
  "B. Use Promise chains",
  "C. Use RxJS observables"
])
```

---

### 5.6.3 EnterPlanMode / ExitPlanMode（计划模式）

**功能**：进入/退出计划模式

**权限要求**：
- EnterPlanMode：无需批准
- ExitPlanMode：需要批准

**使用场景**：
- 复杂任务前先制定计划
- 审查修改方案
- 避免盲目执行

**工作流程**：
1. `EnterPlanMode()` —— 进入计划模式
2. Claude 使用只读工具探索代码库
3. 制定详细的执行计划
4. `ExitPlanMode()` —— 展示计划，请求用户批准
5. 用户批准后开始执行

---

### 5.6.4 EnterWorktree / ExitWorktree（Git Worktree）

**功能**：创建/进入或退出 Git worktree

**权限要求**：无需批准

**使用场景**：
- 在隔离环境中工作
- 并行开发多个功能
- 避免污染主工作目录

**示例**：
```
EnterWorktree()  // 创建并进入新的 worktree
ExitWorktree()   // 退出 worktree，返回原目录
```

---

## 5.7 工具权限总结

| 工具 | 类别 | 需权限 | 记忆行为 |
|------|------|--------|---------|
| Read | 文件操作 | 否 | — |
| Edit | 文件操作 | 是 | 会话内 |
| Write | 文件操作 | 是 | 会话内 |
| Glob | 搜索 | 否 | — |
| Grep | 搜索 | 否 | — |
| Bash | 执行 | 是 | 永久（按项目+命令前缀） |
| CronCreate | 定时任务 | 否 | — |
| WebSearch | Web | 否 | — |
| WebFetch | Web | 否 | — |
| LSP | 代码智能 | 否 | — |
| Agent | 编排 | 否 | — |
| AskUserQuestion | 交互 | 否 | — |
| EnterPlanMode | 编排 | 否 | — |
| ExitPlanMode | 编排 | 是 | — |
| EnterWorktree | Git | 否 | — |
| ExitWorktree | Git | 否 | — |

---

## 5.8 工具调用链示例

**场景**：添加一个新功能并验证

```
1. Glob("src/features/**/*.ts")           → 查找现有功能模块
2. Read("src/features/user/user.service.ts") → 阅读参考实现
3. Bash("npm run generate:module auth")   → 生成新模块骨架
4. Write("src/features/auth/auth.service.ts", "...") → 创建服务文件
5. Write("src/features/auth/auth.controller.ts", "...") → 创建控制器
6. Edit("src/app.module.ts", 12, "import { AuthModule }") → 注册模块
7. Bash("npm test -- --grep auth")        → 运行测试
8. LSP("diagnostics", "src/features/auth/") → 检查类型错误
```

这个工具调用链展示了 Claude 如何组合使用多种工具完成复杂任务。
