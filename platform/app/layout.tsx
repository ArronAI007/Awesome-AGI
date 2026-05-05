import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Awesome-AGI 学习平台",
  description: "从 LLM 基础到 Agent 实战的完整学习路径",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-zinc-950 text-zinc-100 font-sans">
        {children}
      </body>
    </html>
  );
}
