import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"
import { auth } from "@/lib/auth"

export const config = {
  matcher: ["/learn/:path*", "/admin/:path*", "/api/admin/:path*"],
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Admin route protection
  if (pathname.startsWith("/admin") || pathname.startsWith("/api/admin")) {
    const session = await auth()
    if (!session?.user?.id || session.user.role !== "admin") {
      if (pathname.startsWith("/api/")) {
        return NextResponse.json({ error: "Forbidden" }, { status: 403 })
      }
      return NextResponse.redirect(new URL("/", request.url))
    }
    return NextResponse.next()
  }

  // Only intercept /learn/[courseSlug]/[chapterId] paths
  const match = pathname.match(/^\/learn\/([^\/]+)\/([^\/]+)$/)
  if (!match) {
    return NextResponse.next()
  }

  // Allow access to preview chapters without auth check in middleware
  // Detailed access check is done in the page component
  return NextResponse.next()
}
