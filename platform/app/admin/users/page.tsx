import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { checkAdmin } from "@/lib/access"
import { Navbar } from "@/components/navbar"
import { Users, CreditCard, BookOpen, Shield } from "lucide-react"

export default async function AdminUsersPage() {
  const session = await auth()
  if (!session?.user?.id || !(await checkAdmin(session.user.id))) {
    redirect("/")
  }

  const users = await prisma.user.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      _count: {
        select: { orders: true, subscriptions: true, access: true },
      },
    },
  })

  const stats = {
    totalUsers: users.length,
    totalSubscriptions: await prisma.userSubscription.count(),
    totalAccess: await prisma.userCourseAccess.count(),
  }

  return (
    <>
      <Navbar />
      <main className="flex-1 px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <h1 className="text-3xl font-bold text-white">用户管理</h1>

          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <StatCard icon={<Users className="h-5 w-5" />} label="总用户数" value={stats.totalUsers} />
            <StatCard icon={<CreditCard className="h-5 w-5" />} label="订阅数" value={stats.totalSubscriptions} />
            <StatCard icon={<BookOpen className="h-5 w-5" />} label="课程开通数" value={stats.totalAccess} />
          </div>

          <div className="mt-10">
            <h2 className="text-xl font-semibold text-white mb-4">用户列表</h2>
            <div className="rounded-lg border border-zinc-800 overflow-hidden">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900 text-zinc-400">
                  <tr>
                    <th className="px-4 py-3">邮箱</th>
                    <th className="px-4 py-3">名称</th>
                    <th className="px-4 py-3">角色</th>
                    <th className="px-4 py-3">订单</th>
                    <th className="px-4 py-3">订阅</th>
                    <th className="px-4 py-3">课程</th>
                    <th className="px-4 py-3">注册时间</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {users.map((user) => (
                    <tr key={user.id} className="bg-zinc-950 hover:bg-zinc-900">
                      <td className="px-4 py-3 text-zinc-200">{user.email}</td>
                      <td className="px-4 py-3 text-zinc-200">{user.name || "—"}</td>
                      <td className="px-4 py-3">
                        {user.role === "admin" && (
                          <span title="管理权限">
                            <Shield className="h-4 w-4 text-purple-400" />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-zinc-400">{user._count.orders}</td>
                      <td className="px-4 py-3 text-zinc-400">{user._count.subscriptions}</td>
                      <td className="px-4 py-3 text-zinc-400">{user._count.access}</td>
                      <td className="px-4 py-3 text-zinc-500">{user.createdAt.toLocaleDateString("zh-CN")}</td>
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
