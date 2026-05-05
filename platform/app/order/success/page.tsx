import { Suspense } from "react"
import { Loader2 } from "lucide-react"
import { OrderSuccessContent } from "./order-success-content"

export default function OrderSuccessPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-400" />
        </div>
      }
    >
      <OrderSuccessContent />
    </Suspense>
  )
}
