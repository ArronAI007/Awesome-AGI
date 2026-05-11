"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Pencil, Trash2, Plus, Loader2 } from "lucide-react"

interface SubscriptionPlan {
  id: string
  name: string
  price: number
  duration: number
  description: string | null
  createdAt: Date
}

interface PlanManagerProps {
  initialPlans: SubscriptionPlan[]
}

export function PlanManager({ initialPlans }: PlanManagerProps) {
  const [plans, setPlans] = useState(initialPlans)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [loading, setLoading] = useState(false)

  const [name, setName] = useState("")
  const [price, setPrice] = useState("")
  const [duration, setDuration] = useState("")
  const [description, setDescription] = useState("")

  function resetForm() {
    setName("")
    setPrice("")
    setDuration("")
    setDescription("")
    setEditingId(null)
  }

  function startEdit(plan: SubscriptionPlan) {
    setName(plan.name)
    setPrice((plan.price / 100).toFixed(0))
    setDuration(plan.duration.toString())
    setDescription(plan.description || "")
    setEditingId(plan.id)
    setCreating(false)
  }

  async function handleSave() {
    if (!name || !price || !duration) return
    setLoading(true)

    const payload = {
      name,
      price: Number(price) * 100,
      duration: Number(duration),
      description: description || undefined,
    }

    try {
      const url = editingId ? `/api/admin/subscription-plans/${editingId}` : "/api/admin/subscription-plans"
      const method = editingId ? "PUT" : "POST"
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        const data = await res.json()
        if (editingId) {
          setPlans((prev) => prev.map((p) => (p.id === editingId ? data.plan : p)).sort((a, b) => a.price - b.price))
        } else {
          setPlans((prev) => [...prev, data.plan].sort((a, b) => a.price - b.price))
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
    if (!confirm("确定删除该会员计划？")) return
    const res = await fetch(`/api/admin/subscription-plans/${id}`, { method: "DELETE" })
    if (res.ok) {
      setPlans((prev) => prev.filter((p) => p.id !== id))
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
              <th className="px-4 py-3">名称</th>
              <th className="px-4 py-3">价格</th>
              <th className="px-4 py-3">时长(天)</th>
              <th className="px-4 py-3">描述</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {plans.map((plan) => (
              <tr key={plan.id} className="bg-zinc-950 hover:bg-zinc-900">
                <td className="px-4 py-3 text-zinc-200">{plan.name}</td>
                <td className="px-4 py-3 text-zinc-400">¥{(plan.price / 100).toFixed(0)}</td>
                <td className="px-4 py-3 text-zinc-400">{plan.duration}</td>
                <td className="px-4 py-3 text-zinc-400">{plan.description}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="ghost" className="text-zinc-400 hover:text-white" onClick={() => startEdit(plan)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button size="sm" variant="ghost" className="text-red-400 hover:text-red-300 hover:bg-red-500/10" onClick={() => handleDelete(plan.id)}>
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
          <h3 className="font-semibold text-white">{editingId ? "编辑会员计划" : "添加会员计划"}</h3>
          <div>
            <Label className="text-zinc-300">名称</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 bg-zinc-950 border-zinc-800 text-white" required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-zinc-300">价格 (元)</Label>
              <Input type="number" min={0} value={price} onChange={(e) => setPrice(e.target.value)} className="mt-1 bg-zinc-950 border-zinc-800 text-white" required />
            </div>
            <div>
              <Label className="text-zinc-300">时长 (天)</Label>
              <Input type="number" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} className="mt-1 bg-zinc-950 border-zinc-800 text-white" required />
            </div>
          </div>
          <div>
            <Label className="text-zinc-300">描述</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1 bg-zinc-950 border-zinc-800 text-white" />
          </div>
          <div className="flex gap-3">
            <Button onClick={handleSave} disabled={loading} className="bg-emerald-500 hover:bg-emerald-600 text-zinc-950 font-semibold">
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              保存
            </Button>
            <Button variant="outline" onClick={() => { resetForm(); setCreating(false); }} className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
              取消
            </Button>
          </div>
        </div>
      )}

      {!creating && !editingId && (
        <Button onClick={() => { resetForm(); setCreating(true); }} variant="outline" className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
          <Plus className="mr-1.5 h-4 w-4" />
          添加会员计划
        </Button>
      )}
    </div>
  )
}
