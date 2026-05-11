import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { checkAdmin } from "@/lib/access"
import { prisma } from "@/lib/prisma"
import { z } from "zod"

const planSchema = z.object({
  name: z.string().min(1).optional(),
  price: z.number().min(0).optional(),
  duration: z.number().int().min(1).optional(),
  description: z.string().optional(),
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
  const parsed = planSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  try {
    const plan = await prisma.subscriptionPlan.update({
      where: { id },
      data: parsed.data,
    })
    return NextResponse.json({ plan })
  } catch (error) {
    console.error("Update plan error:", error)
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
    await prisma.subscriptionPlan.delete({ where: { id } })
    return NextResponse.json({ success: true })
  } catch (error) {
    console.error("Delete plan error:", error)
    return NextResponse.json({ error: "删除失败" }, { status: 500 })
  }
}
