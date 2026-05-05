"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { BookOpen } from "lucide-react"

export default function RegisterPage() {
  const router = useRouter()
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      })

      const data = await res.json()

      if (res.ok) {
        router.push("/login?registered=true")
      } else {
        setError(data.error || "注册失败")
      }
    } catch {
      setError("注册失败，请重试")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-full flex-col justify-center px-4 py-12 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-sm">
        <div className="text-center">
          <Link href="/" className="inline-flex items-center gap-2 text-xl font-bold">
            <BookOpen className="h-6 w-6 text-emerald-400" />
            <span>Awesome-AGI</span>
          </Link>
          <h2 className="mt-6 text-2xl font-bold tracking-tight text-white">
            创建账户
          </h2>
        </div>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          <div className="space-y-4">
            <div>
              <Label htmlFor="name" className="text-zinc-300">昵称</Label>
              <Input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 bg-zinc-900 border-zinc-800 text-white placeholder:text-zinc-600"
                placeholder="你的昵称"
              />
            </div>
            <div>
              <Label htmlFor="email" className="text-zinc-300">邮箱</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 bg-zinc-900 border-zinc-800 text-white placeholder:text-zinc-600"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <Label htmlFor="password" className="text-zinc-300">密码</Label>
              <Input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 bg-zinc-900 border-zinc-800 text-white placeholder:text-zinc-600"
                placeholder="至少6位字符"
              />
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-400">{error}</p>
          )}

          <Button
            type="submit"
            className="w-full bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
            disabled={loading}
          >
            {loading ? "注册中..." : "注册"}
          </Button>

          <p className="text-center text-sm text-zinc-500">
            已有账户？{" "}
            <Link href="/login" className="text-emerald-400 hover:text-emerald-300">
              直接登录
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
