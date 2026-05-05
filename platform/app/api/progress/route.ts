import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { z } from "zod"

const progressSchema = z.object({
  chapterId: z.string(),
  completed: z.boolean().optional(),
  position: z.number().optional(),
})

export async function POST(req: Request) {
  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ error: "请先登录" }, { status: 401 })
  }

  const body = await req.json()
  const parsed = progressSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  const { chapterId, completed, position } = parsed.data

  try {
    const progress = await prisma.learningProgress.upsert({
      where: {
        userId_chapterId: {
          userId: session.user.id,
          chapterId,
        },
      },
      create: {
        userId: session.user.id,
        chapterId,
        completed: completed ?? false,
        position,
      },
      update: {
        completed: completed !== undefined ? completed : undefined,
        position: position !== undefined ? position : undefined,
      },
    })

    return NextResponse.json({ progress })
  } catch (error) {
    console.error("Save progress error:", error)
    return NextResponse.json({ error: "保存失败" }, { status: 500 })
  }
}

export async function GET(req: Request) {
  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ error: "请先登录" }, { status: 401 })
  }

  const { searchParams } = new URL(req.url)
  const courseSlug = searchParams.get("courseSlug")

  try {
    if (courseSlug) {
      const course = await prisma.course.findUnique({
        where: { slug: courseSlug },
        include: { chapters: true },
      })
      if (!course) {
        return NextResponse.json({ error: "课程不存在" }, { status: 404 })
      }

      const chapterIds = course.chapters.map((c) => c.id)
      const progress = await prisma.learningProgress.findMany({
        where: {
          userId: session.user.id,
          chapterId: { in: chapterIds },
        },
      })

      const completedCount = progress.filter((p) => p.completed).length
      const totalChapters = chapterIds.length
      const percent = totalChapters > 0 ? Math.round((completedCount / totalChapters) * 100) : 0

      return NextResponse.json({
        progress,
        completedCount,
        totalChapters,
        percent,
      })
    }

    const progress = await prisma.learningProgress.findMany({
      where: { userId: session.user.id },
    })
    return NextResponse.json({ progress })
  } catch {
    return NextResponse.json({ error: "查询失败" }, { status: 500 })
  }
}
