import { defineConfig } from 'vitepress'
import fs from 'fs'
import path from 'path'

const docsDir = path.resolve(__dirname, '..')

const dirNameMap: Record<string, string> = {
  '01-fundamentals': '基础理论',
  '02-models': '模型与 API',
  '03-infrastructure': '工程与部署',
  '04-applications': '应用实践',
  '05-frameworks': '开发框架',
  '06-datasets': '数据集',
  'fine-tuning': '微调',
  'prompt-engineering': '提示工程',
  'evaluation': '评估',
  'deployment': '部署框架',
  'agents': 'Agent 实战',
  'rag': 'RAG 实战',
  'nl2sql': 'NL2SQL',
  'mcp': 'MCP',
  'langchain': 'LangChain',
  'llama-index': 'LlamaIndex',
  'llm': '语言大模型',
  'mllm': '多模态大模型',
  'openai': 'OpenAI',
  'claude-code': 'Claude Code',
  'tutorials': '实战教程',
  'examples': '示例',
  'context-management': '上下文管理',
}

function getDisplayName(name: string): string {
  if (dirNameMap[name]) return dirNameMap[name]
  // Convert kebab-case or snake_case to readable text
  return name
    .replace(/[-_]/g, ' ')
    .replace(/^\w/, c => c.toUpperCase())
}

function generateSidebarItems(dirPath: string, baseLink: string): any[] {
  const entries = fs.readdirSync(dirPath, { withFileTypes: true })
  const items: any[] = []
  const dirs: any[] = []
  const files: any[] = []

  for (const entry of entries) {
    const name = entry.name
    if (name.startsWith('.')) continue

    const fullPath = path.join(dirPath, name)
    const linkPath = baseLink + '/' + name.replace(/\.md$/, '')

    if (entry.isDirectory()) {
      const subItems = generateSidebarItems(fullPath, linkPath)
      const indexFile = ['README.md', 'index.md'].find(f => fs.existsSync(path.join(fullPath, f)))
      dirs.push({
        text: getDisplayName(name),
        link: indexFile ? linkPath + '/' : undefined,
        items: subItems.length > 0 ? subItems : undefined,
        collapsed: true,
      })
    } else if (entry.isFile() && name.endsWith('.md')) {
      if (name === 'README.md' || name === 'index.md') continue // Handled by parent dir
      files.push({
        text: getDisplayName(name.replace(/\.md$/, '')),
        link: linkPath,
      })
    }
  }

  // Sort: directories first, then files; alphabetically within each group
  dirs.sort((a, b) => a.text.localeCompare(b.text, 'zh-CN'))
  files.sort((a, b) => a.text.localeCompare(b.text, 'zh-CN'))

  return [...dirs, ...files]
}

function generateSidebar(): any[] {
  const contentDirs = [
    '01-fundamentals',
    '02-models',
    '03-infrastructure',
    '04-applications',
    '05-frameworks',
    '06-datasets',
  ]

  const sidebar: any[] = []

  for (const dir of contentDirs) {
    const dirPath = path.join(docsDir, dir)
    if (!fs.existsSync(dirPath)) continue

    const indexFile = ['README.md', 'index.md'].find(f => fs.existsSync(path.join(dirPath, f)))
    const items = generateSidebarItems(dirPath, '/' + dir)

    sidebar.push({
      text: getDisplayName(dir),
      link: indexFile ? '/' + dir + '/' : undefined,
      items,
      collapsed: false,
    })
  }

  return sidebar
}

export default defineConfig({
  title: 'Awesome-AGI',
  titleTemplate: ':title | Awesome-AGI 大模型全栈指南',
  description: '从 LLM 基础理论到 Agent 实战的完整学习路径，涵盖微调、RAG、多 Agent 系统等核心技术。',
  lang: 'zh-CN',
  base: '/Awesome-AGI/',
  lastUpdated: true,
  cleanUrls: true,
  metaChunk: true,
  ignoreDeadLinks: true,

  markdown: {
    lineNumbers: true,
    config: (md) => {
      // Add any markdown-it plugins here if needed
    },
  },

  themeConfig: {
    logo: '/logo.svg',

    nav: [
      { text: '首页', link: '/' },
      { text: '课程总览', link: '/overview' },
      { text: '基础理论', link: '/01-fundamentals/' },
      { text: '应用实践', link: '/04-applications/' },
      {
        text: '更多',
        items: [
          { text: '模型与 API', link: '/02-models/' },
          { text: '工程与部署', link: '/03-infrastructure/' },
          { text: '开发框架', link: '/05-frameworks/' },
          { text: '数据集', link: '/06-datasets/' },
        ],
      },
    ],

    sidebar: generateSidebar(),

    socialLinks: [
      { icon: 'github', link: 'https://github.com/ArronAI007/Awesome-AGI' },
    ],

    footer: {
      message: '基于 MIT 协议开源',
      copyright: 'Copyright © 2024-present ArronAI',
    },

    search: {
      provider: 'local',
      options: {
        translations: {
          button: {
            buttonText: '搜索',
            buttonAriaLabel: '搜索文档',
          },
          modal: {
            noResultsText: '未找到相关结果',
            resetButtonTitle: '清除查询',
            footer: {
              selectText: '选择',
              navigateText: '切换',
              closeText: '关闭',
            },
          },
        },
      },
    },

    docFooter: {
      prev: '上一页',
      next: '下一页',
    },

    outline: {
      label: '页面导航',
      level: [2, 3],
    },

    lastUpdated: {
      text: '最后更新于',
      formatOptions: {
        dateStyle: 'short',
        timeStyle: 'medium',
      },
    },

    langMenuLabel: '多语言',
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '菜单',
    darkModeSwitchLabel: '主题',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',
  },

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/Awesome-AGI/logo.svg' }],
    ['meta', { name: 'theme-color', content: '#3b82f6' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:title', content: 'Awesome-AGI 大模型全栈指南' }],
    ['meta', { property: 'og:description', content: '从 LLM 基础理论到 Agent 实战的完整学习路径' }],
  ],
})
