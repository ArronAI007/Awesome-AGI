import { NextResponse } from "next/server"
import { prisma } from "@/lib/prisma"
import { verifyAlipayNotify } from "@/lib/payment/alipay"

export async function POST(req: Request) {
  try {
    const formData = await req.formData()
    const params: Record<string, string> = {}
    formData.forEach((value, key) => {
      params[key] = value.toString()
    })

    const result = verifyAlipayNotify(params)

    if (!result.valid || !result.outTradeNo) {
      return NextResponse.json("fail")
    }

    if (result.tradeStatus !== "TRADE_SUCCESS" && result.tradeStatus !== "TRADE_FINISHED") {
      return NextResponse.json("success")
    }

    const order = await prisma.order.findUnique({
      where: { tradeNo: result.outTradeNo },
    })

    if (!order || order.status === "paid") {
      return NextResponse.json("success")
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

    return NextResponse.json("success")
  } catch (error) {
    console.error("Alipay notify error:", error)
    return NextResponse.json("fail")
  }
}
