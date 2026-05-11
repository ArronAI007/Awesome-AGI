import Link from "next/link"
import { BookOpen, LogOut, User, GraduationCap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { auth, signOut } from "@/lib/auth"

export async function Navbar() {
  const session = await auth()

  return (
    <header className="sticky top-0 z-50 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight">
          <BookOpen className="h-6 w-6 text-emerald-400" />
          <span>Awesome-AGI</span>
        </Link>
        <nav className="flex items-center gap-6">
          <Link href="/courses" className="text-sm font-medium text-zinc-400 hover:text-zinc-100 transition-colors flex items-center gap-1.5">
            <GraduationCap className="h-4 w-4" />
            全部课程
          </Link>
          {session?.user ? (
            <form
              action={async () => {
                "use server"
                await signOut({ redirectTo: "/" })
              }}
            >
              <Button type="submit" variant="ghost" size="sm" className="text-zinc-400 hover:text-zinc-100">
                <LogOut className="mr-2 h-4 w-4" />
                退出
              </Button>
            </form>
          ) : (
            <Link href="/login">
              <Button variant="ghost" size="sm" className="text-zinc-400 hover:text-zinc-100">
                <User className="mr-2 h-4 w-4" />
                登录
              </Button>
            </Link>
          )}
        </nav>
      </div>
    </header>
  )
}
