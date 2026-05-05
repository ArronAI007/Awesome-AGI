"use client"

import { useEffect, useState } from "react"
import { CheckCircle2, Circle } from "lucide-react"
import { Button } from "@/components/ui/button"

interface ProgressTrackerProps {
  chapterId: string
}

export function ProgressTracker({ chapterId }: ProgressTrackerProps) {
  const [completed, setCompleted] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch(`/api/progress?chapterId=${chapterId}`)
      .then((res) => res.json())
      .then((data) => {
        const p = data.progress?.find((p: { chapterId: string }) => p.chapterId === chapterId)
        if (p) setCompleted(p.completed)
      })
      .catch(() => {})
  }, [chapterId])

  async function markComplete() {
    setSaving(true)
    try {
      const res = await fetch("/api/progress", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chapterId, completed: true }),
      })
      if (res.ok) setCompleted(true)
    } catch {
      // ignore
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mt-8 pt-6 border-t border-zinc-800">
      {completed ? (
        <div className="flex items-center gap-2 text-emerald-400">
          <CheckCircle2 className="h-5 w-5" />
          <span className="font-medium">已完成本章学习</span>
        </div>
      ) : (
        <Button
          onClick={markComplete}
          disabled={saving}
          className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold"
        >
          <Circle className="mr-2 h-4 w-4" />
          {saving ? "保存中..." : "标记为已完成"}
        </Button>
      )}
    </div>
  )
}
