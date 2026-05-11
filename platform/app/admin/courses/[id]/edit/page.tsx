import { notFound, redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { prisma } from "@/lib/prisma"
import { checkAdmin } from "@/lib/access"
import { Navbar } from "@/components/navbar"
import { CourseForm } from "../../course-form"
import { ChapterManager } from "../../../chapter-manager"

interface EditCoursePageProps {
  params: Promise<{ id: string }>
}

export default async function EditCoursePage({ params }: EditCoursePageProps) {
  const session = await auth()
  if (!session?.user?.id || !(await checkAdmin(session.user.id))) {
    redirect("/")
  }

  const { id } = await params
  const course = await prisma.course.findUnique({
    where: { id },
    include: { chapters: { orderBy: { sortOrder: "asc" } } },
  })

  if (!course) {
    notFound()
  }

  return (
    <>
      <Navbar />
      <main className="flex-1 px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl">
          <h1 className="text-2xl font-bold text-white">编辑课程</h1>
          <div className="mt-6">
            <CourseForm course={course} />
          </div>
          <div className="mt-10">
            <h2 className="text-xl font-semibold text-white mb-4">章节管理</h2>
            <ChapterManager courseId={course.id} chapters={course.chapters} />
          </div>
        </div>
      </main>
    </>
  )
}
