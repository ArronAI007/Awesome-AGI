"use client"

import { useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import Link from "next/link"
import { CheckCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"

export function OrderSuccessContent() {
  const searchParams = useSearchParams()
  const tradeNo = searchParams.get("tradeNo")
  const [order, setOrder] = useState<{ tradeNo: string; status: string; amount: number } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!tradeNo) {
      setLoading(false)
      return
    }
    fetch(`/api/order?tradeNo=${tradeNo}`)
      .then((res) => res.json())
      .then((data) => {
        setOrder(data.order)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [tradeNo])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
      </div>
    )
  }

  if (!order) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="text-center">
          <p className="text-zinc-400">未找到订单信息</p>
          <Link href="/courses">
            <Button variant="link" className="mt-4 text-emerald-400">
              返回课程列表
            </Button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="mx-auto max-w-sm text-center">
        <CheckCircle className="mx-auto h-16 w-16 text-emerald-400" />
        <h1 className="mt-6 text-2xl font-bold text-white">支付成功</h1>
        <p className="mt-2 text-zinc-400">订单号：{order.tradeNo}</p>
        <p className="mt-1 text-zinc-400">支付金额：¥{(order.amount / 100).toFixed(2)}</p>
        <div className="mt-8 flex flex-col gap-3">
          <Link href="/courses">
            <Button className="w-full bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold">
              去学习
            </Button>
          </Link>
          <Link href="/courses">
            <Button variant="outline" className="w-full border-zinc-700 text-zinc-300 hover:bg-zinc-800">
              返回课程列表
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}
