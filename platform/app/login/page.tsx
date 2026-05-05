import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { BookOpen } from "lucide-react"
import { loginAction } from "./actions"
import { WeChatLoginButton } from "./wechat-button"

export default function LoginPage() {
  const wechatEnabled =
    !!process.env.WECHAT_APP_ID && !!process.env.WECHAT_APP_SECRET

  return (
    <div className="flex min-h-full flex-col justify-center px-4 py-12 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-sm">
        <div className="text-center">
          <Link href="/" className="inline-flex items-center gap-2 text-xl font-bold">
            <BookOpen className="h-6 w-6 text-emerald-400" />
            <span>Awesome-AGI</span>
          </Link>
          <h2 className="mt-6 text-2xl font-bold tracking-tight text-white">
            登录学习平台
          </h2>
        </div>

        <form action={loginAction} className="mt-8 space-y-6">
          <div className="space-y-4">
            <div>
              <Label htmlFor="email" className="text-zinc-300">邮箱</Label>
              <Input
                id="email"
                name="email"
                type="email"
                required
                className="mt-1 bg-zinc-900 border-zinc-800 text-white placeholder:text-zinc-600"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <Label htmlFor="password" className="text-zinc-300">密码</Label>
              <Input
                id="password"
                name="password"
                type="password"
                required
                className="mt-1 bg-zinc-900 border-zinc-800 text-white placeholder:text-zinc-600"
                placeholder="******"
              />
            </div>
          </div>

          <Button
            type="submit"
            className="w-full bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
          >
            登录
          </Button>

          {wechatEnabled && (
            <>
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-zinc-800" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-zinc-950 px-2 text-zinc-500">或</span>
                </div>
              </div>
              <WeChatLoginButton />
            </>
          )}

          <p className="text-center text-sm text-zinc-500">
            还没有账户？{" "}
            <Link href="/register" className="text-emerald-400 hover:text-emerald-300">
              立即注册
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}
