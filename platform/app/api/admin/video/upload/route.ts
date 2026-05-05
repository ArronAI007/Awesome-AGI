import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { r2Client, R2_BUCKET_NAME, getR2PublicUrl } from "@/lib/r2"
import { PutObjectCommand } from "@aws-sdk/client-s3"
import { getSignedUrl } from "@aws-sdk/s3-request-presigner"
import { prisma } from "@/lib/prisma"

export async function POST(req: Request) {
  const session = await auth()
  if (!session?.user?.email?.endsWith("@admin.com")) {
    return NextResponse.json({ error: "无权访问" }, { status: 403 })
  }

  const { chapterId, filename, contentType } = await req.json()

  if (!chapterId || !filename || !contentType) {
    return NextResponse.json({ error: "参数错误" }, { status: 400 })
  }

  const chapter = await prisma.chapter.findUnique({
    where: { id: chapterId },
  })

  if (!chapter) {
    return NextResponse.json({ error: "章节不存在" }, { status: 404 })
  }

  const key = `videos/${chapter.courseId}/${chapterId}/${Date.now()}-${filename}`

  try {
    const command = new PutObjectCommand({
      Bucket: R2_BUCKET_NAME,
      Key: key,
      ContentType: contentType,
    })

    const presignedUrl = await getSignedUrl(r2Client, command, { expiresIn: 600 })
    const publicUrl = getR2PublicUrl(key)

    return NextResponse.json({ presignedUrl, publicUrl, key })
  } catch (error) {
    console.error("Generate presigned URL error:", error)
    return NextResponse.json({ error: "生成上传链接失败" }, { status: 500 })
  }
}
