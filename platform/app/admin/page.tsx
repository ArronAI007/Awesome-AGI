import Link from "next/link"
import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { Navbar } from "@/components/navbar"
import { BookOpen, ShoppingCart, Users, CreditCard } from "lucide-react"

export default async function AdminPage() {
  const session = await auth()
  if (!session?.user?.email?.endsWith("@admin.com")) {
    redirect("/")
  }

  const courses = await prisma.course.findMany({
    include: { _count: { select: { chapters: true } } },
    orderBy: { createdAt: "desc" },
  })

  const orders = await prisma.order.findMany({
    orderBy: { createdAt: "desc" },
    take: 10,
  })

  const plans = await prisma.subscriptionPlan.findMany({
    orderBy: { price: "asc" },
  })

  const stats = {
    totalCourses: courses.length,
    totalOrders: await prisma.order.count(),
    totalUsers: await prisma.user.count(),
    totalRevenue: await prisma.order
      .aggregate({ _sum: { amount: true }, where: { status: "paid" } })
      .then((r) => r._sum.amount || 0),
    totalSubscriptions: await prisma.userSubscription.count(),
  }

  return (
    <>
      <Navbar />
      <main className="flex-1 px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <h1 className="text-3xl font-bold text-white">管理后台</h1>

          {/* Stats */}
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <StatCard icon={<BookOpen className="h-5 w-5" />} label="课程数" value={stats.totalCourses} />
            <StatCard icon={<ShoppingCart className="h-5 w-5" />} label="订单数" value={stats.totalOrders} />
            <StatCard icon={<Users className="h-5 w-5" />} label="用户数" value={stats.totalUsers} />
            <StatCard icon={<CreditCard className="h-5 w-5" />} label="订阅数" value={stats.totalSubscriptions} />
            <StatCard icon={<ShoppingCart className="h-5 w-5" />} label="总收入" value={`¥${(stats.totalRevenue / 100).toFixed(0)}`} />
          </div>

          {/* Courses */}
          <div className="mt-10">
            <h2 className="text-xl font-semibold text-white mb-4">课程管理</h2>
            <div className="rounded-lg border border-zinc-800 overflow-hidden">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900 text-zinc-400">
                  <tr>
                    <th className="px-4 py-3">标题</th>
                    <th className="px-4 py-3">价格</th>
                    <th className="px-4 py-3">章节</th>
                    <th className="px-4 py-3">状态</th>
                    <th className="px-4 py-3">创建时间</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {courses.map((course) => (
                    <tr key={course.id} className="bg-zinc-950 hover:bg-zinc-900">
                      <td className="px-4 py-3 text-zinc-200">{course.title}</td>
                      <td className="px-4 py-3 text-zinc-400">
                        {course.isFree ? "免费" : `¥${(course.price / 100).toFixed(0)}`}
                      </td>
                      <td className="px-4 py-3 text-zinc-400">{course._count.chapters}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded px-2 py-0.5 text-xs ${course.isPublished ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-800 text-zinc-500"}`}>
                          {course.isPublished ? "已发布" : "未发布"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-zinc-500">{course.createdAt.toLocaleDateString("zh-CN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Subscription Plans */}
          <div className="mt-10">
            <h2 className="text-xl font-semibold text-white mb-4">会员计划</h2>
            <div className="rounded-lg border border-zinc-800 overflow-hidden">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900 text-zinc-400">
                  <tr>
                    <th className="px-4 py-3">名称</th>
                    <th className="px-4 py-3">价格</th>
                    <th className="px-4 py-3">时长(天)</th>
                    <th className="px-4 py-3">描述</th>
                    <th className="px-4 py-3">创建时间</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {plans.map((plan) => (
                    <tr key={plan.id} className="bg-zinc-950 hover:bg-zinc-900">
                      <td className="px-4 py-3 text-zinc-200">{plan.name}</td>
                      <td className="px-4 py-3 text-zinc-400">¥{(plan.price / 100).toFixed(0)}</td>
                      <td className="px-4 py-3 text-zinc-400">{plan.duration}</td>
                      <td className="px-4 py-3 text-zinc-400">{plan.description}</td>
                      <td className="px-4 py-3 text-zinc-500">{plan.createdAt.toLocaleDateString("zh-CN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Recent Orders */}
          <div className="mt-10">
            <h2 className="text-xl font-semibold text-white mb-4">最近订单</h2>
            <div className="rounded-lg border border-zinc-800 overflow-hidden">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900 text-zinc-400">
                  <tr>
                    <th className="px-4 py-3">订单号</th>
                    <th className="px-4 py-3">类型</th>
                    <th className="px-4 py-3">金额</th>
                    <th className="px-4 py-3">状态</th>
                    <th className="px-4 py-3">支付方式</th>
                    <th className="px-4 py-3">时间</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {orders.map((order) => (
                    <tr key={order.id} className="bg-zinc-950 hover:bg-zinc-900">
                      <td className="px-4 py-3 text-zinc-200 font-mono">{order.tradeNo}</td>
                      <td className="px-4 py-3 text-zinc-400">{order.type === "course" ? "课程" : "会员"}</td>
                      <td className="px-4 py-3 text-zinc-400">¥{(order.amount / 100).toFixed(2)}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded px-2 py-0.5 text-xs ${order.status === "paid" ? "bg-emerald-500/10 text-emerald-400" : order.status === "pending" ? "bg-yellow-500/10 text-yellow-400" : "bg-zinc-800 text-zinc-500"}`}>
                          {order.status === "paid" ? "已支付" : order.status === "pending" ? "待支付" : "已取消"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-zinc-400">{order.channel === "wechat" ? "微信" : "支付宝"}</td>
                      <td className="px-4 py-3 text-zinc-500">{order.createdAt.toLocaleDateString("zh-CN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
    </>
  )
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="flex items-center gap-2 text-zinc-400">
        {icon}
        <span className="text-sm">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-bold text-white">{value}</p>
    </div>
  )
}
