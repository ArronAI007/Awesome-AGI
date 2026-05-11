"use client"

import Link from "next/link"
import { Pencil, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"

export function CourseRowActions({ courseId }: { courseId: string }) {
  async function handleDelete() {
    if (!confirm("确定要删除该课程吗？此操作不可撤销。")) return
    const res = await fetch(`/api/admin/courses/${courseId}`, { method: "DELETE" })
    if (res.ok) {
      window.location.reload()
    } else {
      alert("删除失败")
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Link href={`/admin/courses/${courseId}/edit`}>
        <Button size="sm" variant="ghost" className="text-zinc-400 hover:text-white">
          <Pencil className="h-4 w-4" />
        </Button>
      </Link>
      <Button size="sm" variant="ghost" className="text-red-400 hover:text-red-300 hover:bg-red-500/10" onClick={handleDelete}>
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  )
}
