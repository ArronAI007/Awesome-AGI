import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"

export async function POST(req: Request) {
  const session = await auth()
  if (!session?.user?.email?.endsWith("@admin.com")) {
    return NextResponse.json({ error: "无权访问" }, { status: 403 })
  }

  const { chapterId, videoUrl } = await req.json()

  if (!chapterId || !videoUrl) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  try {
    await prisma.chapter.update({
      where: { id: chapterId },
      data: { content: videoUrl },
    })
    return NextResponse.json({ success: true })
  } catch (error) {
    console.error("Save video URL error:", error)
    return NextResponse.json({ error: "保存失败" }, { status: 500 })
  }
}
