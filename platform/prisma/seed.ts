import { PrismaClient } from "@prisma/client"

const prisma = new PrismaClient()

async function main() {
  // Clean existing data
  await prisma.learningProgress.deleteMany()
  await prisma.userSubscription.deleteMany()
  await prisma.subscriptionPlan.deleteMany()
  await prisma.userCourseAccess.deleteMany()
  await prisma.order.deleteMany()
  await prisma.chapter.deleteMany()
  await prisma.course.deleteMany()
  await prisma.user.deleteMany()

  // Create a sample course with fixed chapter IDs matching filesystem
  const course = await prisma.course.create({
    data: {
      slug: "awesome-agi",
      title: "Awesome-AGI 大模型全栈指南",
      description:
        "从 LLM 基础理论到 Agent 实战的完整学习路径，涵盖微调、RAG、多 Agent 系统等核心技术。",
      coverImage: "/images/agi-cover.png",
      price: 29900,
      isFree: false,
      isPublished: true,
      chapters: {
        create: [
          {
            id: "01-fundamentals",
            title: "大模型基础理论",
            sortOrder: 1,
            type: "doc",
            isPreview: true,
            description: "了解 LLM 的核心概念、微调方法和评估体系",
          },
          {
            id: "02-models",
            title: "主流模型与 API 实践",
            sortOrder: 2,
            type: "doc",
            isPreview: false,
            description: "掌握国内外主流大模型的 API 调用与私有化部署",
          },
        ],
      },
    },
  })

  // Create a free preview course
  const freeCourse = await prisma.course.create({
    data: {
      slug: "llm-quickstart",
      title: "大模型快速入门",
      description: "零基础了解大语言模型，30分钟建立整体认知。",
      price: 0,
      isFree: true,
      isPublished: true,
      chapters: {
        create: [
          {
            id: "01-intro",
            title: "什么是大语言模型",
            sortOrder: 1,
            type: "doc",
            isPreview: true,
            description: "LLM 的定义、发展历程和核心能力",
          },
          {
            id: "02-prompt",
            title: "提示工程基础",
            sortOrder: 2,
            type: "doc",
            isPreview: true,
            description: "如何与 AI 高效对话",
          },
        ],
      },
    },
  })

  // Seed subscription plans
  await prisma.subscriptionPlan.createMany({
    data: [
      {
        name: "月度会员",
        price: 4900,
        duration: 30,
        description: "解锁全部课程，畅享30天学习",
      },
      {
        name: "年度会员",
        price: 29900,
        duration: 365,
        description: "全年无限学习，立省50%",
      },
    ],
  })

  console.log("Seeded courses:", course.id, freeCourse.id)
}

main()
  .then(async () => {
    await prisma.$disconnect()
  })
  .catch(async (e) => {
    console.error(e)
    await prisma.$disconnect()
    process.exit(1)
  })
