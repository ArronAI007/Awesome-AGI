"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Loader2, Play } from "lucide-react"

interface JupyterLiteProps {
  notebookContent?: string
}

export function JupyterLite({ notebookContent }: JupyterLiteProps) {
  const [isLoading, setIsLoading] = useState(true)

  // JupyterLite 部署地址，可以替换为你自己部署的实例
  const jupyterLiteUrl = "https://jupyterlite.github.io/demo/repl/index.html?kernel=python&toolbar=1"

  // 如果有 notebook 内容，可以尝试通过 URL 参数传递（有长度限制）
  // 或者后续通过 postMessage 注入

  return (
    <div className="rounded-lg border border-zinc-800 overflow-hidden bg-zinc-950">
      <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900/50 px-4 py-2">
        <div className="flex items-center gap-2">
          <Play className="h-4 w-4 text-emerald-400" />
          <span className="text-sm font-medium text-zinc-300">交互式 Notebook</span>
        </div>
        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中...
          </div>
        )}
      </div>
      <div className="relative" style={{ height: "600px" }}>
        <iframe
          src={jupyterLiteUrl}
          className="absolute inset-0 h-full w-full"
          onLoad={() => setIsLoading(false)}
          allow="clipboard-read; clipboard-write"
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-modals allow-downloads"
        />
      </div>
    </div>
  )
}
