import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"

export async function POST(req: Request) {
  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ error: "请先登录" }, { status: 401 })
  }

  const { tradeNo } = await req.json()

  if (!tradeNo) {
    return NextResponse.json({ error: "订单号不能为空" }, { status: 400 })
  }

  const order = await prisma.order.findUnique({
    where: { tradeNo },
  })

  if (!order) {
    return NextResponse.json({ error: "订单不存在" }, { status: 404 })
  }

  if (order.userId !== session.user.id) {
    return NextResponse.json({ error: "无权操作" }, { status: 403 })
  }

  if (order.status === "paid") {
    return NextResponse.json({ error: "订单已支付" }, { status: 409 })
  }

  await prisma.$transaction(async (tx) => {
    await tx.order.update({
      where: { id: order.id },
      data: { status: "paid", paidAt: new Date() },
    })

    if (order.type === "course") {
      await tx.userCourseAccess.upsert({
        where: {
          userId_courseId: {
            userId: order.userId,
            courseId: order.targetId,
          },
        },
        create: {
          userId: order.userId,
          courseId: order.targetId,
        },
        update: {},
      })
    } else if (order.type === "subscription") {
      const plan = await tx.subscriptionPlan.findUnique({
        where: { id: order.targetId },
      })
      if (plan) {
        const startsAt = new Date()
        const endsAt = new Date(startsAt.getTime() + plan.duration * 24 * 60 * 60 * 1000)
        await tx.userSubscription.create({
          data: {
            userId: order.userId,
            planId: order.targetId,
            startsAt,
            endsAt,
            status: "active",
          },
        })
      }
    }
  })

  return NextResponse.json({ success: true, tradeNo })
}
