import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { checkAdmin } from "@/lib/access"
import { Navbar } from "@/components/navbar"
import { CourseForm } from "../course-form"

export default async function NewCoursePage() {
  const session = await auth()
  if (!session?.user?.id || !(await checkAdmin(session.user.id))) {
    redirect("/")
  }

  return (
    <>
      <Navbar />
      <main className="flex-1 px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl">
          <h1 className="text-2xl font-bold text-white">添加课程</h1>
          <div className="mt-6">
            <CourseForm />
          </div>
        </div>
      </main>
    </>
  )
}
