import { NextResponse } from "next/server"
import { prisma } from "@/lib/prisma"
import { verifyWechatNotify } from "@/lib/payment/wechat"

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const result = verifyWechatNotify(body)

    if (!result.valid || !result.outTradeNo) {
      return NextResponse.json({ code: "FAIL", message: "Invalid signature" })
    }

    const order = await prisma.order.findUnique({
      where: { tradeNo: result.outTradeNo },
    })

    if (!order || order.status === "paid") {
      return NextResponse.json({ code: "SUCCESS" })
    }

    await prisma.$transaction(async (tx) => {
      await tx.order.update({
        where: { id: order.id },
        data: { status: "paid", paidAt: new Date() },
      })

      if (order.type === "course") {
        await tx.userCourseAccess.create({
          data: {
            userId: order.userId,
            courseId: order.targetId,
          },
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

    return NextResponse.json({ code: "SUCCESS" })
  } catch (error) {
    console.error("Wechat notify error:", error)
    return NextResponse.json({ code: "FAIL", message: "System error" })
  }
}
