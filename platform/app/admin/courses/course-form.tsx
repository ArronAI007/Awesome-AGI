"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Loader2 } from "lucide-react"

interface CourseFormProps {
  course?: {
    id: string
    slug: string
    title: string
    description?: string | null
    price: number
    isFree: boolean
    isPublished: boolean
  }
}

export function CourseForm({ course }: CourseFormProps) {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [slug, setSlug] = useState(course?.slug || "")
  const [title, setTitle] = useState(course?.title || "")
  const [description, setDescription] = useState(course?.description || "")
  const [price, setPrice] = useState(course?.price ? (course.price / 100).toFixed(0) : "0")
  const [isFree, setIsFree] = useState(course?.isFree ?? false)
  const [isPublished, setIsPublished] = useState(course?.isPublished ?? false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)

    const payload = {
      slug,
      title,
      description: description || undefined,
      price: isFree ? 0 : Number(price) * 100,
      isFree,
      isPublished,
    }

    try {
      const url = course ? `/api/admin/courses/${course.id}` : "/api/admin/courses"
      const method = course ? "PUT" : "POST"
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        router.push("/admin")
      } else {
        const data = await res.json()
        alert(data.error || "操作失败")
      }
    } catch {
      alert("网络错误")
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6 rounded-lg border border-zinc-800 bg-zinc-900/50 p-6">
      <div>
        <Label htmlFor="slug" className="text-zinc-300">课程标识 (URL 用)</Label>
        <Input
          id="slug"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          required
          className="mt-1 bg-zinc-950 border-zinc-800 text-white"
          placeholder="awesome-agi"
        />
        <p className="mt-1 text-xs text-zinc-500">仅支持英文、数字和连字符</p>
      </div>

      <div>
        <Label htmlFor="title" className="text-zinc-300">课程标题</Label>
        <Input
          id="title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          className="mt-1 bg-zinc-950 border-zinc-800 text-white"
          placeholder="课程标题"
        />
      </div>

      <div>
        <Label htmlFor="description" className="text-zinc-300">课程描述</Label>
        <Input
          id="description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="mt-1 bg-zinc-950 border-zinc-800 text-white"
          placeholder="简短描述"
        />
      </div>

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={isFree}
            onChange={(e) => setIsFree(e.target.checked)}
            className="rounded border-zinc-700 bg-zinc-950 text-emerald-500"
          />
          免费课程
        </label>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={isPublished}
            onChange={(e) => setIsPublished(e.target.checked)}
            className="rounded border-zinc-700 bg-zinc-950 text-emerald-500"
          />
          立即发布
        </label>
      </div>

      {!isFree && (
        <div>
          <Label htmlFor="price" className="text-zinc-300">价格 (元)</Label>
          <Input
            id="price"
            type="number"
            min={0}
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            required={!isFree}
            className="mt-1 bg-zinc-950 border-zinc-800 text-white"
            placeholder="299"
          />
        </div>
      )}

      <div className="flex gap-3">
        <Button
          type="submit"
          disabled={loading}
          className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
        >
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {course ? "保存修改" : "创建课程"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => router.push("/admin")}
          className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        >
          取消
        </Button>
      </div>
    </form>
  )
}
