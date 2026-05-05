"use client"

import Link from "next/link"
import { useState } from "react"
import { CheckCircle2, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { PaymentModal } from "@/components/payment/payment-modal"

interface CourseActionsProps {
  courseSlug: string
  courseTitle: string
  price: number
  isFree: boolean
  hasAccess: boolean
  previewChapterId?: string
}

export function CourseActions({
  courseSlug,
  courseTitle,
  price,
  isFree,
  hasAccess,
  previewChapterId,
}: CourseActionsProps) {
  const [showPayment, setShowPayment] = useState(false)
  const [purchased, setPurchased] = useState(hasAccess)

  if (isFree) {
    return (
      <div className="mt-6">
        <Link href={`/learn/${courseSlug}/${previewChapterId || ""}`}>
          <Button
            size="lg"
            className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
          >
            <Play className="mr-2 h-4 w-4" />
            开始学习
          </Button>
        </Link>
      </div>
    )
  }

  if (purchased) {
    return (
      <div className="mt-6 flex items-center gap-2 text-emerald-400">
        <CheckCircle2 className="h-5 w-5" />
        <span className="font-medium">已购买</span>
        <Link href={`/learn/${courseSlug}/${previewChapterId || ""}`} className="ml-4">
          <Button
            size="lg"
            className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
          >
            <Play className="mr-2 h-4 w-4" />
            开始学习
          </Button>
        </Link>
      </div>
    )
  }

  return (
    <>
      <div className="mt-6 flex gap-4">
        <Button
          size="lg"
          className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
          onClick={() => setShowPayment(true)}
        >
          立即购买
        </Button>
        {previewChapterId && (
          <Link href={`/learn/${courseSlug}/${previewChapterId}`}>
            <Button
              size="lg"
              variant="outline"
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800 hover:text-white"
            >
              <Play className="mr-2 h-4 w-4" />
              免费试学
            </Button>
          </Link>
        )}
      </div>

      {showPayment && (
        <PaymentModal
          targetId={courseSlug}
          title={courseTitle}
          price={price}
          type="course"
          onClose={() => setShowPayment(false)}
          onSuccess={() => {
            setShowPayment(false)
            setPurchased(true)
          }}
        />
      )}
    </>
  )
}
