"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { PaymentModal } from "@/components/payment/payment-modal"

interface MembershipActionsProps {
  planId: string
  planName: string
  price: number
}

export function MembershipActions({ planId, planName, price }: MembershipActionsProps) {
  const [showPayment, setShowPayment] = useState(false)

  return (
    <>
      <Button
        onClick={() => setShowPayment(true)}
        className="mt-6 w-full bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
      >
        立即开通
      </Button>

      {showPayment && (
        <PaymentModal
          targetId={planId}
          title={planName}
          price={price}
          type="subscription"
          onClose={() => setShowPayment(false)}
          onSuccess={() => {
            setShowPayment(false)
            window.location.reload()
          }}
        />
      )}
    </>
  )
}
