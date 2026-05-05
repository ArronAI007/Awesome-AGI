import { notFound, redirect } from "next/navigation"
import Link from "next/link"
import { ArrowLeft, ArrowRight, BookOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { auth } from "@/lib/auth"
import { getCourseBySlugFromDB, getChapterContent } from "@/lib/course"
import { checkCourseAccess } from "@/lib/access"
import { MDXContent } from "@/components/mdx-content"
import { JupyterLite } from "@/components/notebook/jupyter-lite"
import { VideoPlayer } from "@/components/video/video-player"
import { ProgressTracker } from "@/components/course/progress-tracker"
import { Navbar } from "@/components/navbar"

interface LearnPageProps {
  params: Promise<{ courseSlug: string; chapterId: string }>
}

export default async function LearnPage({ params }: LearnPageProps) {
  const { courseSlug, chapterId } = await params
  const session = await auth()

  const course = await getCourseBySlugFromDB(courseSlug)
  if (!course || !course.isPublished) {
    notFound()
  }

  const chapterIndex = course.chapters.findIndex((c) => c.id === chapterId)
  if (chapterIndex === -1) {
    notFound()
  }

  const chapter = course.chapters[chapterIndex]

  // Check access for paid chapters
  if (!chapter.isPreview && !course.isFree) {
    if (!session?.user?.id) {
      redirect("/login")
    }

    const hasAccess = await checkCourseAccess(session.user.id, courseSlug)
    if (!hasAccess) {
      redirect(`/course/${courseSlug}`)
    }
  }

  const content = getChapterContent(courseSlug, chapterId)
  const prevChapter = chapterIndex > 0 ? course.chapters[chapterIndex - 1] : null
  const nextChapter = chapterIndex < course.chapters.length - 1 ? course.chapters[chapterIndex + 1] : null

  return (
    <>
      <Navbar />
      <main className="flex-1">
        {/* Chapter Header */}
        <div className="border-b border-zinc-800 bg-zinc-900/30 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-5xl">
            <Link
              href={`/course/${courseSlug}`}
              className="inline-flex items-center text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              <ArrowLeft className="mr-1.5 h-4 w-4" />
              {course.title}
            </Link>
            <h1 className="mt-2 text-2xl font-bold text-white">
              {chapter.title}
            </h1>
          </div>
        </div>

        {/* Content */}
        <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
          {chapter.type === "doc" && content && (
            <div className="prose prose-invert prose-zinc max-w-none">
              <MDXContent source={content.content} />
            </div>
          )}

          {chapter.type === "notebook" && content && (
            <div className="space-y-6">
              <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
                <p className="text-sm text-zinc-400">
                  <BookOpen className="mr-1.5 inline h-4 w-4" />
                  下方为交互式 Notebook，你可以直接运行和修改代码。
                </p>
              </div>
              <JupyterLite notebookContent={content.content} />
            </div>
          )}

          {chapter.type === "video" && chapter.content && (
            <div className="space-y-6">
              <VideoPlayer src={chapter.content} />
            </div>
          )}

          {chapter.type === "video" && !chapter.content && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-12 text-center text-zinc-500">
              视频暂未上传
            </div>
          )}

          {!content && chapter.type !== "video" && (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-12 text-center text-zinc-500">
              该章节暂无内容
            </div>
          )}

          {session?.user?.id && (
            <ProgressTracker chapterId={chapter.id} />
          )}
        </div>

        {/* Navigation */}
        <div className="border-t border-zinc-800 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-5xl justify-between">
            {prevChapter ? (
              <Link href={`/learn/${courseSlug}/${prevChapter.id}`}>
                <Button variant="ghost" className="text-zinc-400 hover:text-white">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  {prevChapter.title}
                </Button>
              </Link>
            ) : (
              <div />
            )}
            {nextChapter ? (
              <Link href={`/learn/${courseSlug}/${nextChapter.id}`}>
                <Button variant="ghost" className="text-zinc-400 hover:text-white">
                  {nextChapter.title}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            ) : (
              <div />
            )}
          </div>
        </div>
      </main>
    </>
  )
}
