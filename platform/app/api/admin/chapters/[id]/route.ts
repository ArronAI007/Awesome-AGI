import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { checkAdmin } from "@/lib/access"
import { z } from "zod"

const updateChapterSchema = z.object({
  title: z.string().min(1).optional(),
  type: z.enum(["doc", "notebook", "video"]).optional(),
  sortOrder: z.number().optional(),
  isPreview: z.boolean().optional(),
  description: z.string().optional(),
  content: z.string().optional(),
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
  const parsed = updateChapterSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  try {
    const chapter = await prisma.chapter.update({
      where: { id },
      data: parsed.data,
    })
    return NextResponse.json({ chapter })
  } catch (error) {
    console.error("Update chapter error:", error)
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
    await prisma.chapter.delete({ where: { id } })
    return NextResponse.json({ success: true })
  } catch (error) {
    console.error("Delete chapter error:", error)
    return NextResponse.json({ error: "删除失败" }, { status: 500 })
  }
}
