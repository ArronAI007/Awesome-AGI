"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Pencil, Trash2, Plus, GripVertical } from "lucide-react"
import { Loader2 } from "lucide-react"

interface Chapter {
  id: string
  title: string
  type: string
  sortOrder: number
  isPreview: boolean
  description: string | null
  content: string | null
}

interface ChapterManagerProps {
  courseId: string
  chapters: Chapter[]
}

export function ChapterManager({ courseId, chapters: initialChapters }: ChapterManagerProps) {
  const [chapters, setChapters] = useState(initialChapters)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [loading, setLoading] = useState(false)

  const [title, setTitle] = useState("")
  const [type, setType] = useState<"doc" | "notebook" | "video">("doc")
  const [sortOrder, setSortOrder] = useState(0)
  const [isPreview, setIsPreview] = useState(false)
  const [description, setDescription] = useState("")
  const [content, setContent] = useState("")

  function resetForm() {
    setTitle("")
    setType("doc")
    setSortOrder(chapters.length)
    setIsPreview(false)
    setDescription("")
    setContent("")
    setEditingId(null)
  }

  function startEdit(chapter: Chapter) {
    setTitle(chapter.title)
    setType(chapter.type as "doc" | "notebook" | "video")
    setSortOrder(chapter.sortOrder)
    setIsPreview(chapter.isPreview)
    setDescription(chapter.description || "")
    setContent(chapter.content || "")
    setEditingId(chapter.id)
    setCreating(false)
  }

  async function handleSave() {
    if (!title) return
    setLoading(true)

    const payload = {
      courseId: editingId ? undefined : courseId,
      title,
      type,
      sortOrder,
      isPreview,
      description: description || undefined,
      content: content || undefined,
    }

    try {
      const url = editingId ? `/api/admin/chapters/${editingId}` : "/api/admin/chapters"
      const method = editingId ? "PUT" : "POST"
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        const data = await res.json()
        if (editingId) {
          setChapters((prev) => prev.map((c) => (c.id === editingId ? data.chapter : c)).sort((a, b) => a.sortOrder - b.sortOrder))
        } else {
          setChapters((prev) => [...prev, data.chapter].sort((a, b) => a.sortOrder - b.sortOrder))
        }
        resetForm()
        setCreating(false)
      } else {
        alert("保存失败")
      }
    } catch {
      alert("网络错误")
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("确定删除该章节？")) return
    const res = await fetch(`/api/admin/chapters/${id}`, { method: "DELETE" })
    if (res.ok) {
      setChapters((prev) => prev.filter((c) => c.id !== id))
    } else {
      alert("删除失败")
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm text-left">
          <thead className="bg-zinc-900 text-zinc-400">
            <tr>
              <th className="px-4 py-3 w-8"></th>
              <th className="px-4 py-3">标题</th>
              <th className="px-4 py-3">类型</th>
              <th className="px-4 py-3">排序</th>
              <th className="px-4 py-3">试看</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {chapters.map((chapter) => (
              <tr key={chapter.id} className="bg-zinc-950 hover:bg-zinc-900">
                <td className="px-4 py-3"><GripVertical className="h-4 w-4 text-zinc-600" /></td>
                <td className="px-4 py-3 text-zinc-200">{chapter.title}</td>
                <td className="px-4 py-3 text-zinc-400">
                  {chapter.type === "doc" ? "文档" : chapter.type === "notebook" ? "Notebook" : "视频"}
                </td>
                <td className="px-4 py-3 text-zinc-400">{chapter.sortOrder}</td>
                <td className="px-4 py-3">
                  {chapter.isPreview && (
                    <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-xs text-emerald-400">试看</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="ghost" className="text-zinc-400 hover:text-white" onClick={() => startEdit(chapter)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost" className="text-red-400 hover:text-red-300 hover:bg-red-500/10" onClick={() => handleDelete(chapter.id)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(creating || editingId) && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
          <h3 className="font-semibold text-white">{editingId ? "编辑章节" : "添加章节"}</h3>
          <div>
            <Label className="text-zinc-300">章节标题</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1 bg-zinc-950 border-zinc-800 text-white" required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-zinc-300">类型</Label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value as "doc" | "notebook" | "video")}
                className="mt-1 w-full rounded-md bg-zinc-950 border border-zinc-800 text-white px-3 py-2"
              >
                <option value="doc">文档</option>
                <option value="notebook">Notebook</option>
                <option value="video">视频</option>
              </select>
            </div>
            <div>
              <Label className="text-zinc-300">排序</Label>
              <Input type="number" value={sortOrder} onChange={(e) => setSortOrder(Number(e.target.value))} className="mt-1 bg-zinc-950 border-zinc-800 text-white" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-zinc-300">
              <input type="checkbox" checked={isPreview} onChange={(e) => setIsPreview(e.target.checked)} className="rounded border-zinc-700 bg-zinc-950 text-emerald-500" />
              允许试看
            </label>
          </div>
          <div>
            <Label className="text-zinc-300">描述</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1 bg-zinc-950 border-zinc-800 text-white" />
          </div>
          <div>
            <Label className="text-zinc-300">内容 / 视频URL</Label>
            <Input value={content} onChange={(e) => setContent(e.target.value)} className="mt-1 bg-zinc-950 border-zinc-800 text-white" placeholder={type === "video" ? "https://..." : "可选"} />
          </div>
          <div className="flex gap-3">
            <Button onClick={handleSave} disabled={loading} className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold">
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              保存
            </Button>
            <Button variant="outline" onClick={() => { resetForm(); setCreating(false); }} className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">取消</Button>
          </div>
        </div>
      )}

      {!creating && !editingId && (
        <Button
          onClick={() => { resetForm(); setSortOrder(chapters.length); setCreating(true); }}
          variant="outline"
          className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
        >
          <Plus className="mr-1.5 h-4 w-4" />
          添加章节
        </Button>
      )}
    </div>
  )
}
