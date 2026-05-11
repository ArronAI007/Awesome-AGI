import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { checkAdmin } from "@/lib/access"
import { prisma } from "@/lib/prisma"
import { z } from "zod"

const planSchema = z.object({
  name: z.string().min(1),
  price: z.number().min(0),
  duration: z.number().int().min(1),
  description: z.string().optional(),
})

export async function POST(req: Request) {
  const session = await auth()
  if (!session?.user?.id || !(await checkAdmin(session.user.id))) {
    return NextResponse.json({ error: "无权访问" }, { status: 403 })
  }

  const body = await req.json()
  const parsed = planSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  try {
    const plan = await prisma.subscriptionPlan.create({ data: parsed.data })
    return NextResponse.json({ plan })
  } catch (error) {
    console.error("Create plan error:", error)
    return NextResponse.json({ error: "创建失败" }, { status: 500 })
  }
}
