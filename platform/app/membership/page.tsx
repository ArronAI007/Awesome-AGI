import Link from "next/link"
import { redirect } from "next/navigation"
import { Check, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { Navbar } from "@/components/navbar"
import { MembershipActions } from "./membership-actions"

export default async function MembershipPage() {
  const session = await auth()
  if (!session?.user?.id) {
    redirect("/login")
  }

  const plans = await prisma.subscriptionPlan.findMany({
    orderBy: { price: "asc" },
  })

  const activeSubscription = await prisma.userSubscription.findFirst({
    where: {
      userId: session.user.id,
      status: "active",
      endsAt: { gt: new Date() },
    },
    include: { plan: true },
    orderBy: { endsAt: "desc" },
  })

  return (
    <>
      <Navbar />
      <main className="flex-1 px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-5xl">
          <div className="text-center mb-12">
            <h1 className="text-3xl font-bold tracking-tight text-white">
              会员计划
            </h1>
            <p className="mt-4 text-lg text-zinc-400 max-w-2xl mx-auto">
              成为会员，解锁全部付费课程，畅享无限学习
            </p>
          </div>

          {activeSubscription && (
            <div className="mb-10 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-6 text-center">
              <div className="flex items-center justify-center gap-2 text-emerald-400 font-medium">
                <Sparkles className="h-5 w-5" />
                你当前是 {activeSubscription.plan.name}
              </div>
              <p className="mt-1 text-sm text-zinc-400">
                有效期至 {activeSubscription.endsAt.toLocaleDateString("zh-CN")}
              </p>
            </div>
          )}

          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {plans.map((plan) => (
              <div
                key={plan.id}
                className="relative rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 flex flex-col"
              >
                <h3 className="text-xl font-semibold text-white">
                  {plan.name}
                </h3>
                <p className="mt-2 text-sm text-zinc-400">
                  {plan.description}
                </p>
                <div className="mt-4 flex items-baseline gap-1">
                  <span className="text-3xl font-bold text-white">
                    ¥{(plan.price / 100).toFixed(0)}
                  </span>
                  <span className="text-sm text-zinc-500">
                    / {plan.duration}天
                  </span>
                </div>

                <ul className="mt-6 space-y-3 text-sm text-zinc-300 flex-1">
                  <li className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-emerald-400" />
                    解锁全部付费课程
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-emerald-400" />
                    无限次学习
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-emerald-400" />
                    在线运行 Notebook
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-emerald-400" />
                    学习进度追踪
                  </li>
                </ul>

                <MembershipActions planId={plan.id} planName={plan.name} price={plan.price} />
              </div>
            ))}
          </div>

          <div className="mt-12 text-center">
            <Link href="/courses">
              <Button variant="ghost" className="text-zinc-400 hover:text-zinc-200">
                返回课程列表
              </Button>
            </Link>
          </div>
        </div>
      </main>
    </>
  )
}
