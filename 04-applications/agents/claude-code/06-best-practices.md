# 六、最佳实践

---

## 6.1 高效使用建议

### 6.1.1 提示词（Prompt）技巧

**清晰具体的描述**

❌ 不好的示例：
```
fix the bug
```

✅ 好的示例：
```
When I submit the login form with an empty password, the app crashes with 
"TypeError: Cannot read property 'hash' of undefined". Fix this in the 
auth service and add proper validation.
```

**提供上下文**

告诉 Claude 相关的背景信息：
- 使用的技术栈和版本
- 相关的文件或模块
- 期望的行为
- 已尝试的解决方案

**分解复杂任务**

对于大型任务，分解为多个步骤：
```
Step 1: Find all places where the old API is used
Step 2: Create a wrapper function for the new API
Step 3: Replace all usages
Step 4: Run tests to verify
```

---

### 6.1.2 充分利用 CLAUDE.md

**应该放入 CLAUDE.md 的内容：**

```markdown
# 项目规范

## 技术栈
- Node.js 20 + TypeScript 5
- Express.js 后端
- React 18 前端
- PostgreSQL 数据库

## 构建命令
```bash
npm run build      # 编译 TypeScript
npm run test       # 运行测试
npm run test:watch # 监听模式测试
npm run lint       # ESLint 检查
```

## 代码规范
- 使用单引号
- 缩进 2 空格
- 函数使用 camelCase
- 类使用 PascalCase
- 接口前缀 I（如 IUser）

## 项目结构
- `src/controllers/` - HTTP 控制器
- `src/services/` - 业务逻辑
- `src/models/` - 数据模型
- `src/middleware/` - Express 中间件
- `src/utils/` - 工具函数

## 测试规范
- 所有服务必须有单元测试
- 使用 Jest + Supertest
- 测试文件命名：`*.spec.ts`
```

**CLAUDE.md 的加载层次：**

| 层级 | 路径 | 用途 |
|------|------|------|
| 组织级 | `/Library/Application Support/ClaudeCode/CLAUDE.md` | 公司编码标准、安全策略 |
| 项目级 | `./CLAUDE.md` | 项目架构、团队约定 |
| 用户级 | `~/.claude/CLAUDE.md` | 个人偏好 |
| 本地级 | `./CLAUDE.local.md` | 个人项目偏好（.gitignore） |

**使用 `/init` 自动生成：**

```bash
# 自动分析代码库并生成 CLAUDE.md
/init
```

Claude 会分析项目结构、构建命令、测试指令等，自动生成初始的 CLAUDE.md。

---

### 6.1.3 善用计划模式

对于复杂修改，先使用 `/plan` 模式：

1. **进入计划模式**：
   ```
   /plan refactor the authentication system to use JWT
   ```

2. **Claude 会**：
   - 只读探索代码库
   - 分析当前实现
   - 制定详细计划
   - 展示修改步骤

3. **审查计划**：
   - 检查修改范围
   - 确认不会破坏现有功能
   - 评估风险

4. **执行**：
   - 批准计划
   - Claude 按计划执行

---

### 6.1.4 管道输入快速处理

利用 Unix 管道快速处理文件：

```bash
# 快速分析日志
cat error.log | claude -p "summarize the errors and suggest fixes"

# 代码审查
cat src/app.ts | claude -p "review this code for security issues"

# 格式化输出
claude -p "generate a markdown table from this data" < data.json
```

**SDK 模式（`-p`）特点：**
- 执行完即退出
- 适合脚本化
- 可处理管道输入
- 无交互式对话

---

### 6.1.5 保持会话连续性

```bash
# 继续最近的工作
claude -c

# 或
claude --continue

# 从特定会话恢复
claude -r "feature-auth" "implement the login endpoint"
```

**会话管理技巧：**
- 给会话起有意义的名字（如 `auth-refactor`、`api-migration`）
- 定期使用 `/compact` 压缩历史
- 使用 `/clear` 开始新任务（保留项目记忆）

---

### 6.1.6 使用子智能体保持上下文干净

当需要大量探索性工作时，让子智能体处理：

```
Explore the entire codebase and find all places where 
User.findById is called, then return a summary.
```

Claude 会自动使用 Explore 子智能体：
- 在独立的上下文窗口中工作
- 只返回摘要，不污染主会话
- 使用 Haiku 模型，快速高效

---

### 6.1.7 模型选择策略

| 场景 | 推荐模型 | 原因 |
|------|---------|------|
| 日常编码 | `sonnet` | 平衡性能和速度 |
| 复杂架构 | `opus` | 最强推理能力 |
| 简单任务 | `haiku` | 快速、低成本 |
| 大型重构 | `opusplan` | 深度计划 + 高效执行 |
| 超长代码分析 | `sonnet[1m]` / `opus[1m]` | 1M 上下文窗口 |

---

## 6.2 典型工作流

### 6.2.1 理解新代码库

```bash
# 1. 进入项目目录
cd /path/to/new-project

# 2. 启动 Claude Code
claude

# 3. 获取代码库概览
> "give me an overview of this codebase"

# 4. 深入了解架构
> "explain the main architecture patterns used here"
> "what are the key data models?"
> "how is authentication handled?"

# 5. 探索特定功能
> "find the files that handle user authentication"
> "trace the login process from front-end to database"
```

**技巧：**
- 从宽泛的问题开始，逐步深入
- 询问项目特定的术语和约定
- 使用代码智能插件获得精确的导航

---

### 6.2.2 修复 Bug

```bash
# 1. 描述问题
> "I'm seeing an error when I run npm test"

# 2. 提供复现步骤（如果 Claude 没有自动运行测试）
> "run the tests and show me the failures"

# 3. 分析错误
> "explain what this error means"

# 4. 定位问题
> "find the source of the TypeError in auth.ts"

# 5. 修复
> "fix the null pointer exception in the login function"

# 6. 验证
> "run the tests again to confirm the fix"
```

**技巧：**
- 提供完整的错误信息（堆栈跟踪）
- 说明复现步骤
- 告诉 Claude 错误是间歇性还是持续的

---

### 6.2.3 代码重构

```bash
# 1. 识别需要重构的代码
> "find deprecated API usage in our codebase"

# 2. 获取建议
> "suggest how to refactor utils.js to use modern JavaScript features"

# 3. 进入计划模式（复杂重构）
> "/plan refactor the data layer to use Repository pattern"

# 4. 执行重构
> "refactor utils.js to use ES2024 features while maintaining the same behavior"

# 5. 验证
> "run tests for the refactored code"
> "check for any TypeScript errors"
```

**技巧：**
- 小步快跑，逐步重构
- 每次修改后运行测试
- 要求保持向后兼容（如需要）

---

### 6.2.4 编写测试

```bash
# 1. 识别未测试的代码
> "find functions in NotificationsService that are not covered by tests"

# 2. 生成测试骨架
> "add tests for the notification service"

# 3. 添加边界条件
> "add test cases for edge conditions in the notification service"

# 4. 运行并修复
> "run the new tests and fix any failures"
```

**技巧：**
- Claude 会匹配现有测试风格
- 明确说明要测试的行为
- 让 Claude 识别容易遗漏的边界条件

---

### 6.2.5 创建 Pull Request

```bash
# 1. 总结更改
> "summarize the changes I've made to the authentication module"

# 2. 创建 PR
> "create a pr"

# 3. 增强描述
> "enhance the PR description with more context about the security improvements"
```

**技巧：**
- 审查 Claude 生成的 PR 描述
- 让 Claude 指出潜在风险
- 使用 `gh pr create` 自动链接会话

---

### 6.2.6 批量代码修改

对于大规模修改，使用 `/batch` 命令：

```
/batch migrate src/ from Solid to React
```

工作流程：
1. Claude 研究代码库
2. 将工作分解为 5-30 个独立单元
3. 展示计划供你批准
4. 批准后，每个单元在隔离的 git worktree 中并行执行
5. 每个子智能体实现其单元、运行测试、打开 PR

---

### 6.2.7 完整的日常开发流程

```bash
# 1. 进入项目，继续之前的工作
claude -c

# 2. 查看当前状态
> "what's the current status of the project?"
> "show me my uncommitted changes"

# 3. 开始新任务
> "implement the password reset feature"
# Claude 会：
# - 探索相关代码
# - 提出实现方案
# - 请求确认后开始编码

# 4. 审查修改
> "/diff"
# 查看所有更改

# 5. 运行测试
> "run all tests"

# 6. 提交更改
> "commit my changes with a descriptive message"

# 7. 创建 PR
> "create a pull request"
```

---

## 6.3 常见陷阱与避免方法

| 陷阱 | 避免方法 |
|------|---------|
| 上下文溢出 | 定期使用 `/compact`，大任务用子智能体 |
| 权限频繁询问 | 配置 `permissions.allow` 规则 |
| Claude 理解偏差 | 提供具体示例和明确的验收标准 |
| 修改范围过大 | 使用 `/plan` 模式，小步迭代 |
| 测试遗漏 | 明确要求 "run tests after changes" |
| 过度依赖 | 始终审查 Claude 的修改，理解其逻辑 |

---

## 6.4 扩展工作流

### 6.4.1 使用 Skills

创建可复用的工作流：

```bash
# 创建技能目录
mkdir -p ~/.claude/skills/code-review

# 编写 SKILL.md
cat > ~/.claude/skills/code-review/SKILL.md << 'EOF'
---
description: Reviews code for quality issues. Use when the user asks for code review.
---

## Instructions

1. Check for common issues:
   - Missing error handling
   - Hardcoded values
   - Security vulnerabilities
   - Performance bottlenecks
   - Type safety issues

2. For each issue found:
   - Explain the problem
   - Show the current code
   - Suggest an improved version

3. Provide an overall quality score (1-10)
EOF
```

使用：`/code-review` 或让 Claude 自动触发

### 6.4.2 使用 MCP 连接外部服务

```bash
# 添加 MCP 服务器
claude mcp add postgres --transport stdio -- npx -y @modelcontextprotocol/server-postgres

# 在会话中使用
> "query the database for all active users"
```

### 6.4.3 使用 Hooks 自动化

配置钩子自动执行检查：

```json
{
  "hooks": [
    {
      "event": "PreToolUse",
      "matcher": "Edit",
      "command": "./scripts/pre-commit-check.sh"
    }
  ]
}
```
