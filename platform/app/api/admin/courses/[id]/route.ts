import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { checkAdmin } from "@/lib/access"
import { z } from "zod"

const updateCourseSchema = z.object({
  slug: z.string().min(1).optional(),
  title: z.string().min(1).optional(),
  description: z.string().optional(),
  price: z.number().min(0).optional(),
  isFree: z.boolean().optional(),
  isPublished: z.boolean().optional(),
})

export async function PUT(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await auth()
  if (!session?.user?.id || !(await checkAdmin(session.user.id))) {
    return NextResponse.json({ error: "无权访问" }, { status: 403 })
  }

  const { id } = await params
  const body = await req.json()
  const parsed = updateCourseSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  try {
    const course = await prisma.course.update({
      where: { id },
      data: parsed.data,
    })
    return NextResponse.json({ course })
  } catch (error) {
    console.error("Update course error:", error)
    return NextResponse.json({ error: "更新失败" }, { status: 500 })
  }
}

export async function DELETE(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await auth()
  if (!session?.user?.id || !(await checkAdmin(session.user.id))) {
    return NextResponse.json({ error: "无权访问" }, { status: 403 })
  }

  const { id } = await params

  try {
    await prisma.course.delete({ where: { id } })
    return NextResponse.json({ success: true })
  } catch (error) {
    console.error("Delete course error:", error)
    return NextResponse.json({ error: "删除失败" }, { status: 500 })
  }
}
