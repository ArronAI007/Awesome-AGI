# Awesome-AGI 学习平台

基于 Next.js + Prisma + Auth.js 构建的在线学习平台，支持文档阅读、视频播放、Notebook 在线运行、课程购买和会员订阅。

## 功能特性

- **内容学习**：支持 Markdown 文档、Jupyter Notebook 在线运行、视频播放
- **用户系统**：邮箱注册登录、微信 OAuth 登录（可选）
- **付费体系**：单课购买 + 会员订阅（月度/年度）
- **支付集成**：微信支付 + 支付宝（支持沙箱测试模式）
- **学习进度**：章节完成标记、进度百分比展示
- **管理后台**：课程/订单/用户/会员计划管理

## 技术栈

- **框架**：Next.js 16 (App Router)
- **语言**：TypeScript
- **样式**：Tailwind CSS + shadcn/ui
- **数据库**：SQLite (开发) / PostgreSQL (生产)
- **ORM**：Prisma
- **认证**：Auth.js v5
- **存储**：Cloudflare R2 (视频/图片)
- **Notebook**：JupyterLite (Pyodide WASM)

## 本地开发

### 1. 安装依赖

```bash
npm install
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少配置以下项：

```
DATABASE_URL="file:./dev.db"
NEXTAUTH_URL="http://localhost:3000"
NEXTAUTH_SECRET="your-random-secret-at-least-32-characters-long"
NEXT_PUBLIC_APP_URL="http://localhost:3000"
```

### 3. 初始化数据库

```bash
npx prisma migrate dev --name init
npm run seed
```

### 4. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000

## 生产部署 (Vercel)

### 1. 数据库准备

注册 [Neon](https://neon.tech) 免费 PostgreSQL 数据库，获取连接字符串。

### 2. 配置环境变量

在 Vercel Dashboard 中设置以下环境变量：

```
DATABASE_URL=postgresql://user:password@ep-xxx.neon.tech/dbname?sslmode=require
NEXTAUTH_URL=https://your-domain.vercel.app
NEXTAUTH_SECRET=your-random-secret-at-least-32-characters-long
NEXT_PUBLIC_APP_URL=https://your-domain.vercel.app
```

可选（按需配置）：

```
# Cloudflare R2 视频存储
R2_ENDPOINT=https://xxx.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=xxx
R2_SECRET_ACCESS_KEY=xxx
R2_BUCKET_NAME=awesome-agi
R2_PUBLIC_URL=https://pub-xxx.r2.dev

# 微信登录
WECHAT_APP_ID=xxx
WECHAT_APP_SECRET=xxx

# 真实支付（不配置则使用模拟支付）
WECHAT_MCH_ID=xxx
WECHAT_API_KEY=xxx
ALIPAY_APP_ID=xxx
ALIPAY_PRIVATE_KEY=xxx
ALIPAY_PUBLIC_KEY=xxx
```

### 3. 部署命令

Vercel 的 Build Command 设置为：

```bash
npm run build:prod
```

或手动：

```bash
npm run build:prod
vercel --prod
```

### 4. 数据库迁移

首次部署后，在本地运行生产数据库迁移：

```bash
# 使用生产 DATABASE_URL
npx prisma migrate deploy
```

### 5. 初始化数据

```bash
# 使用生产 DATABASE_URL
npm run seed
```

## 内容更新流程

课程内容（Markdown / Notebook / 视频）通过 Git 管理：

1. 将内容文件放入 `content/courses/[course-slug]/chapters/[chapter-id]/`
2. 提交并推送代码
3. Vercel 自动部署更新

课程元数据（价格、章节顺序、权限）通过管理后台或数据库管理。

## 支付测试

在未配置真实支付密钥时，系统自动使用**模拟支付**模式：

1. 用户点击购买 -> 创建订单
2. 选择支付方式（微信/支付宝）
3. 点击"模拟支付成功" -> 自动完成订单并开通权限

## 管理员

默认管理员判定：邮箱后缀为 `@admin.com`。

访问 `/admin` 进入管理后台。

## 目录结构

```
app/
  (marketing)/        # 公开页面（首页、课程列表、课程详情）
  (learning)/         # 学习页面（章节阅读）
  api/                # API 路由（支付、进度、订单）
  admin/              # 管理后台
  membership/         # 会员订阅页面
components/
  ui/                 # shadcn/ui 基础组件
  course/             # 课程相关组件
  video/              # 视频播放器
  notebook/           # JupyterLite 嵌入
  payment/            # 支付弹窗
lib/
  auth.ts             # Auth.js 配置
  prisma.ts           # Prisma 客户端
  course.ts           # 课程数据获取
  access.ts           # 权限校验
  r2.ts               # Cloudflare R2 客户端
prisma/
  schema.prisma       # 开发版 Schema (SQLite)
  schema.prod.prisma  # 生产版 Schema (PostgreSQL)
  seed.ts             # 种子数据
content/
  courses/            # Git 管理的课程内容
```

## License

MIT
