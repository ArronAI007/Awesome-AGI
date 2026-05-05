import Link from "next/link"
import { BookOpen } from "lucide-react"
import { getAllCoursesFromDB } from "@/lib/course"
import { Navbar } from "@/components/navbar"

export default async function CoursesPage() {
  const courses = await getAllCoursesFromDB()

  return (
    <>
      <Navbar />
      <main className="flex-1 px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <h1 className="text-3xl font-bold tracking-tight text-white">
            全部课程
          </h1>
          <p className="mt-2 text-zinc-400">
            选择适合你的学习路径，从基础到进阶系统掌握大模型技术
          </p>

          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {courses.map((course) => (
              <Link key={course.slug} href={`/course/${course.slug}`}>
                <div className="group rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 transition-colors hover:border-zinc-700 hover:bg-zinc-900">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-semibold text-white group-hover:text-emerald-400 transition-colors">
                      {course.title}
                    </h3>
                    {course.isFree ? (
                      <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-400">
                        免费
                      </span>
                    ) : (
                      <span className="rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs font-medium text-zinc-400">
                        ¥{(course.price / 100).toFixed(0)}
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-sm text-zinc-400 line-clamp-2">{course.description}</p>
                  <div className="mt-4 flex items-center text-sm text-zinc-500">
                    <BookOpen className="mr-1.5 h-4 w-4" />
                    {course.chapters.length} 个章节
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </main>
    </>
  )
}
