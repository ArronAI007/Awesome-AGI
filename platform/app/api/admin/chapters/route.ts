import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { checkAdmin } from "@/lib/access"
import { z } from "zod"

const createChapterSchema = z.object({
  courseId: z.string().min(1),
  title: z.string().min(1),
  type: z.enum(["doc", "notebook", "video"]),
  sortOrder: z.number().default(0),
  isPreview: z.boolean().default(false),
  description: z.string().optional(),
  content: z.string().optional(),
})

export async function POST(req: Request) {
  const session = await auth()
  if (!session?.user?.id || !(await checkAdmin(session.user.id))) {
    return NextResponse.json({ error: "无权访问" }, { status: 403 })
  }

  const body = await req.json()
  const parsed = createChapterSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  const { courseId, title, type, sortOrder, isPreview, description, content } = parsed.data

  try {
    const chapter = await prisma.chapter.create({
      data: {
        courseId,
        title,
        type,
        sortOrder,
        isPreview,
        description,
        content,
      },
    })
    return NextResponse.json({ chapter })
  } catch (error) {
    console.error("Create chapter error:", error)
    return NextResponse.json({ error: "创建失败" }, { status: 500 })
  }
}
