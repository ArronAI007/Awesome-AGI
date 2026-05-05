"use client"

import { useState } from "react"
import { X, CreditCard, Smartphone, CheckCircle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"

interface PaymentModalProps {
  targetId: string
  title: string
  price: number
  type: "course" | "subscription"
  onClose: () => void
  onSuccess: () => void
}

export function PaymentModal({ targetId, title, price, type, onClose, onSuccess }: PaymentModalProps) {
  const [channel, setChannel] = useState<"wechat" | "alipay">("wechat")
  const [loading, setLoading] = useState(false)
  const [orderCreated, setOrderCreated] = useState(false)
  const [tradeNo, setTradeNo] = useState<string | null>(null)

  async function createOrder() {
    setLoading(true)
    try {
      const res = await fetch("/api/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, targetId, channel }),
      })
      const data = await res.json()
      if (res.ok) {
        setTradeNo(data.order.tradeNo)
        setOrderCreated(true)
      } else {
        alert(data.error || "创建订单失败")
      }
    } catch {
      alert("创建订单失败")
    } finally {
      setLoading(false)
    }
  }

  async function simulatePay() {
    if (!tradeNo) return
    setLoading(true)
    try {
      const res = await fetch("/api/payment/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tradeNo }),
      })
      const data = await res.json()
      if (res.ok) {
        onSuccess()
      } else {
        alert(data.error || "支付失败")
      }
    } catch {
      alert("支付失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="relative w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-900 p-6">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-zinc-500 hover:text-zinc-300"
        >
          <X className="h-5 w-5" />
        </button>

        {!orderCreated ? (
          <>
            <h3 className="text-xl font-bold text-white">{type === "course" ? "购买课程" : "购买会员"}</h3>
            <p className="mt-1 text-zinc-400">{title}</p>
            <p className="mt-4 text-3xl font-bold text-emerald-400">
              ¥{(price / 100).toFixed(0)}
            </p>

            <div className="mt-6 space-y-3">
              <button
                onClick={() => setChannel("wechat")}
                className={`flex w-full items-center gap-3 rounded-lg border px-4 py-3 transition-colors ${
                  channel === "wechat"
                    ? "border-emerald-500/50 bg-emerald-500/10"
                    : "border-zinc-800 bg-zinc-950 hover:border-zinc-700"
                }`}
              >
                <Smartphone className="h-5 w-5 text-emerald-400" />
                <span className="text-sm font-medium text-zinc-200">微信支付</span>
                {channel === "wechat" && (
                  <CheckCircle className="ml-auto h-4 w-4 text-emerald-400" />
                )}
              </button>

              <button
                onClick={() => setChannel("alipay")}
                className={`flex w-full items-center gap-3 rounded-lg border px-4 py-3 transition-colors ${
                  channel === "alipay"
                    ? "border-emerald-500/50 bg-emerald-500/10"
                    : "border-zinc-800 bg-zinc-950 hover:border-zinc-700"
                }`}
              >
                <CreditCard className="h-5 w-5 text-blue-400" />
                <span className="text-sm font-medium text-zinc-200">支付宝</span>
                {channel === "alipay" && (
                  <CheckCircle className="ml-auto h-4 w-4 text-emerald-400" />
                )}
              </button>
            </div>

            <Button
              onClick={createOrder}
              disabled={loading}
              className="mt-6 w-full bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
            >
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              确认支付
            </Button>
          </>
        ) : (
          <>
            <h3 className="text-xl font-bold text-white">模拟支付</h3>
            <p className="mt-1 text-zinc-400">当前为测试环境，点击下方按钮模拟支付成功</p>
            <p className="mt-2 text-sm text-zinc-500">订单号：{tradeNo}</p>

            <Button
              onClick={simulatePay}
              disabled={loading}
              className="mt-6 w-full bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
            >
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              模拟支付成功
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
