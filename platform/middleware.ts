import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"
import { auth } from "@/lib/auth"

export const config = {
  matcher: ["/learn/:path*"],
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Only intercept /learn/[courseSlug]/[chapterId] paths
  const match = pathname.match(/^\/learn\/([^\/]+)\/([^\/]+)$/)
  if (!match) {
    return NextResponse.next()
  }

  const [, courseSlug, chapterId] = match

  // Allow access to preview chapters without auth check in middleware
  // Detailed access check is done in the page component
  // Middleware here only ensures session is available for paid content

  const session = await auth()

  if (!session?.user?.id) {
    // Check if this is a preview chapter by looking at query params or cookies
    // For simplicity, let the page handle the detailed check
    // Just pass through and let the page redirect if needed
    return NextResponse.next()
  }

  return NextResponse.next()
}
