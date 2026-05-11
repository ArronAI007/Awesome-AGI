import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { checkAdmin } from "@/lib/access"
import { z } from "zod"

const createCourseSchema = z.object({
  slug: z.string().min(1),
  title: z.string().min(1),
  description: z.string().optional(),
  price: z.number().min(0),
  isFree: z.boolean().default(false),
  isPublished: z.boolean().default(false),
})

export async function POST(req: Request) {
  const session = await auth()
  if (!session?.user?.id || !(await checkAdmin(session.user.id))) {
    return NextResponse.json({ error: "无权访问" }, { status: 403 })
  }

  const body = await req.json()
  const parsed = createCourseSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  const { slug, title, description, price, isFree, isPublished } = parsed.data

  const existing = await prisma.course.findUnique({ where: { slug } })
  if (existing) {
    return NextResponse.json({ error: "课程标识已存在" }, { status: 409 })
  }

  try {
    const course = await prisma.course.create({
      data: {
        slug,
        title,
        description,
        price,
        isFree,
        isPublished,
      },
    })
    return NextResponse.json({ course })
  } catch (error) {
    console.error("Create course error:", error)
    return NextResponse.json({ error: "创建失败" }, { status: 500 })
  }
}
