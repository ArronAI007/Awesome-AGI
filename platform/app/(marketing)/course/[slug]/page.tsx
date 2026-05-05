import Link from "next/link"
import { notFound } from "next/navigation"
import { BookOpen, CheckCircle2, Lock, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { getCourseBySlugFromDB } from "@/lib/course"
import { auth } from "@/lib/auth"
import { checkCourseAccess } from "@/lib/access"
import { prisma } from "@/lib/prisma"
import { Navbar } from "@/components/navbar"
import { CourseActions } from "./course-actions"

interface CoursePageProps {
  params: Promise<{ slug: string }>
}

export default async function CoursePage({ params }: CoursePageProps) {
  const { slug } = await params
  const course = await getCourseBySlugFromDB(slug)
  const session = await auth()

  if (!course || !course.isPublished) {
    notFound()
  }

  let hasAccess = course.isFree
  let progressList: { chapterId: string; completed: boolean }[] = []

  if (session?.user?.id) {
    const accessPromise = course.isFree
      ? Promise.resolve(true)
      : checkCourseAccess(session.user.id, course.slug)
    const progressPromise = prisma.learningProgress.findMany({
      where: {
        userId: session.user.id,
        chapterId: { in: course.chapters.map((c) => c.id) },
      },
      select: { chapterId: true, completed: true },
    })
    const [accessResult, progressResult] = await Promise.all([
      accessPromise,
      progressPromise,
    ])
    hasAccess = accessResult
    progressList = progressResult
  }

  const completedChapterIds = new Set(
    progressList.filter((p) => p.completed).map((p) => p.chapterId)
  )
  const progressPercent =
    course.chapters.length > 0
      ? Math.round((completedChapterIds.size / course.chapters.length) * 100)
      : 0

  const previewChapters = course.chapters.filter((c) => c.isPreview)

  return (
    <>
      <Navbar />
      <main className="flex-1 px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-5xl">
          {/* Course Header */}
          <div className="border-b border-zinc-800 pb-8">
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold tracking-tight text-white">
                {course.title}
              </h1>
              {course.isFree ? (
                <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-sm font-medium text-emerald-400">
                  免费
                </span>
              ) : (
                <span className="rounded-full bg-zinc-800 px-3 py-1 text-sm font-medium text-zinc-300">
                  ¥{(course.price / 100).toFixed(0)}
                </span>
              )}
            </div>
            <p className="mt-4 text-lg text-zinc-400 max-w-3xl">
              {course.description}
            </p>

            <CourseActions
              courseSlug={course.slug}
              courseTitle={course.title}
              price={course.price}
              isFree={course.isFree}
              hasAccess={hasAccess}
              previewChapterId={previewChapters[0]?.id}
            />
          </div>

          {/* Progress */}
          {session?.user?.id && course.chapters.length > 0 && (
            <div className="mt-6 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-zinc-300">
                  学习进度
                </span>
                <span className="text-sm font-medium text-emerald-400">
                  {progressPercent}%
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-zinc-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-emerald-500 transition-all"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-zinc-500">
                已完成 {completedChapterIds.size} / {course.chapters.length} 章
              </p>
            </div>
          )}

          {/* Chapter List */}
          <div className="mt-8">
            <h2 className="text-xl font-semibold text-white mb-4">
              课程目录
            </h2>
            <div className="space-y-3">
              {course.chapters.map((chapter, index) => (
                <div
                  key={chapter.id}
                  className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/50 px-5 py-4"
                >
                  <div className="flex items-center gap-4">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-sm font-medium text-zinc-400">
                      {completedChapterIds.has(chapter.id) ? (
                        <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                      ) : (
                        index + 1
                      )}
                    </span>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-medium text-zinc-200">
                          {chapter.title}
                        </h3>
                        {chapter.isPreview && (
                          <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-xs text-emerald-400">
                            试看
                          </span>
                        )}
                      </div>
                      {chapter.description && (
                        <p className="mt-0.5 text-sm text-zinc-500">
                          {chapter.description}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {chapter.type === "video" && (
                      <Play className="h-4 w-4 text-zinc-500" />
                    )}
                    {chapter.type === "doc" && (
                      <BookOpen className="h-4 w-4 text-zinc-500" />
                    )}
                    {chapter.isPreview || course.isFree || hasAccess ? (
                      <Link
                        href={`/learn/${course.slug}/${chapter.id}`}
                      >
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
                        >
                          <CheckCircle2 className="mr-1.5 h-4 w-4" />
                          学习
                        </Button>
                      </Link>
                    ) : (
                      <Lock className="h-4 w-4 text-zinc-600" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </>
  )
}
