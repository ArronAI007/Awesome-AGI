import Link from "next/link"
import { ArrowRight, BookOpen, Code2, Play, Shield } from "lucide-react"
import { Button } from "@/components/ui/button"
import { getAllCoursesFromDB } from "@/lib/course"
import { Navbar } from "@/components/navbar"

export default async function HomePage() {
  const courses = await getAllCoursesFromDB()

  return (
    <>
      <Navbar />
      <main className="flex-1">
        {/* Hero */}
        <section className="relative overflow-hidden border-b border-zinc-800 bg-zinc-950 px-4 py-24 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-4xl text-center">
            <h1 className="text-4xl font-extrabold tracking-tight text-white sm:text-6xl">
              掌握大模型技术
              <br />
              <span className="text-emerald-400">从理论到实战</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-zinc-400">
              系统化的 AGI 学习平台，涵盖 LLM 微调、RAG、Agent 构建、多模态等前沿技术。
              在线运行 Notebook，边看边练。
            </p>
            <div className="mt-10 flex justify-center gap-4">
              <Link href="/courses">
                <Button size="lg" className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold">
                  浏览课程
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="border-b border-zinc-800 bg-zinc-900/50 px-4 py-16 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
              <FeatureCard
                icon={<BookOpen className="h-6 w-6" />}
                title="系统化课程"
                description="从基础理论到工程实践，覆盖 LLM 全生命周期"
              />
              <FeatureCard
                icon={<Code2 className="h-6 w-6" />}
                title="在线 Notebook"
                description="浏览器内直接运行和修改代码，无需本地环境"
              />
              <FeatureCard
                icon={<Play className="h-6 w-6" />}
                title="视频教程"
                description="录屏讲解复杂概念，配合文档深入理解"
              />
              <FeatureCard
                icon={<Shield className="h-6 w-6" />}
                title="持续更新"
                description="紧跟技术前沿，课程内容和案例定期迭代"
              />
            </div>
          </div>
        </section>

        {/* Courses Preview */}
        <section className="px-4 py-16 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <h2 className="text-2xl font-bold tracking-tight text-white">热门课程</h2>
            <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
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
        </section>
      </main>

      <footer className="border-t border-zinc-800 bg-zinc-950 px-4 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl text-center text-sm text-zinc-500">
          Awesome-AGI 学习平台 · 持续更新中
        </div>
      </footer>
    </>
  )
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
      <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400">
        {icon}
      </div>
      <h3 className="mt-4 text-base font-semibold text-white">{title}</h3>
      <p className="mt-2 text-sm text-zinc-400">{description}</p>
    </div>
  )
}
