import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { z } from "zod"
import { createWechatOrder } from "@/lib/payment/wechat"
import { createAlipayOrder } from "@/lib/payment/alipay"

const createOrderSchema = z.object({
  type: z.enum(["course", "subscription"]),
  targetId: z.string(),
  channel: z.enum(["wechat", "alipay"]),
})

export async function POST(req: Request) {
  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ error: "请先登录" }, { status: 401 })
  }

  const body = await req.json()
  const parsed = createOrderSchema.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  const { type, targetId, channel } = parsed.data
  const userId = session.user.id

  try {
    let amount = 0
    let title = ""

    if (type === "course") {
      const course = await prisma.course.findUnique({
        where: { id: targetId },
      })
      if (!course) {
        return NextResponse.json({ error: "课程不存在" }, { status: 404 })
      }
      if (course.isFree) {
        return NextResponse.json({ error: "免费课程无需购买" }, { status: 400 })
      }
      amount = course.price
      title = course.title

      // Check if already purchased
      const existing = await prisma.order.findFirst({
        where: {
          userId,
          type: "course",
          targetId,
          status: "paid",
        },
      })
      if (existing) {
        return NextResponse.json({ error: "已购买该课程" }, { status: 409 })
      }
    } else {
      const plan = await prisma.subscriptionPlan.findUnique({
        where: { id: targetId },
      })
      if (!plan) {
        return NextResponse.json({ error: "会员计划不存在" }, { status: 404 })
      }
      amount = plan.price
      title = plan.name
    }

    const tradeNo = `ORD${Date.now()}${Math.floor(Math.random() * 1000)}`

    const order = await prisma.order.create({
      data: {
        userId,
        type,
        targetId,
        amount,
        status: "pending",
        channel,
        tradeNo,
      },
    })

    // Generate payment params
    let payParams = null
    const host = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"

    if (channel === "wechat") {
      payParams = await createWechatOrder({
        outTradeNo: tradeNo,
        totalFee: amount,
        body: title,
        notifyUrl: `${host}/api/payment/wechat`,
      })
    } else {
      payParams = await createAlipayOrder({
        outTradeNo: tradeNo,
        totalAmount: amount / 100,
        subject: title,
        notifyUrl: `${host}/api/payment/alipay`,
        returnUrl: `${host}/order/success?tradeNo=${tradeNo}`,
      })
    }

    return NextResponse.json({ order, payParams })
  } catch (error) {
    console.error("Create order error:", error)
    return NextResponse.json({ error: "创建订单失败" }, { status: 500 })
  }
}

export async function GET(req: Request) {
  const session = await auth()
  if (!session?.user?.id) {
    return NextResponse.json({ error: "请先登录" }, { status: 401 })
  }

  const { searchParams } = new URL(req.url)
  const tradeNo = searchParams.get("tradeNo")

  try {
    if (tradeNo) {
      const order = await prisma.order.findUnique({
        where: { tradeNo },
      })
      return NextResponse.json({ order })
    }

    const orders = await prisma.order.findMany({
      where: { userId: session.user.id },
      orderBy: { createdAt: "desc" },
    })
    return NextResponse.json({ orders })
  } catch {
    return NextResponse.json({ error: "查询失败" }, { status: 500 })
  }
}
