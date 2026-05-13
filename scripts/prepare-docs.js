const fs = require('fs')
const path = require('path')

const rootDir = path.resolve(__dirname, '..')
const docsDir = path.resolve(rootDir, 'docs')

const contentDirs = [
  '01-fundamentals',
  '02-models',
  '03-infrastructure',
  '04-applications',
  '05-frameworks',
  '06-datasets'
]

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }
}

function copyMdFiles(srcDir, destDir) {
  ensureDir(destDir)
  const entries = fs.readdirSync(srcDir, { withFileTypes: true })

  for (const entry of entries) {
    const srcPath = path.join(srcDir, entry.name)
    const destPath = path.join(destDir, entry.name)

    if (entry.isDirectory()) {
      // Skip node_modules, .git, and hidden dirs
      if (entry.name.startsWith('.') || entry.name === 'node_modules') continue
      copyMdFiles(srcPath, destPath)
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      // Rename README.md to index.md so VitePress treats it as directory index
      const destFileName = entry.name === 'README.md' ? 'index.md' : entry.name
      const finalDestPath = path.join(destDir, destFileName)
      fs.copyFileSync(srcPath, finalDestPath)
    }
  }
}

function cleanContentDirs() {
  const entries = fs.readdirSync(docsDir, { withFileTypes: true })
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const name = entry.name
    // Only remove directories that match our content dirs
    if (contentDirs.includes(name)) {
      const targetPath = path.join(docsDir, name)
      fs.rmSync(targetPath, { recursive: true, force: true })
    }
  }

  // Remove generated overview if exists
  const overviewPath = path.join(docsDir, 'overview.md')
  if (fs.existsSync(overviewPath)) {
    fs.unlinkSync(overviewPath)
  }
}

function main() {
  console.log('Preparing docs content...')

  cleanContentDirs()

  for (const dir of contentDirs) {
    const src = path.join(rootDir, dir)
    const dest = path.join(docsDir, dir)
    if (fs.existsSync(src)) {
      copyMdFiles(src, dest)
      console.log(`Copied ${dir}`)
    } else {
      console.warn(`Source directory not found: ${src}`)
    }
  }

  // Copy root README as overview with frontmatter for better title
  const readmePath = path.join(rootDir, 'README.md')
  if (fs.existsSync(readmePath)) {
    const readmeContent = fs.readFileSync(readmePath, 'utf-8')
    const overviewContent = `---\ntitle: 课程总览\ndescription: Awesome-AGI 大模型全栈指南完整目录\n---\n\n${readmeContent}`
    fs.writeFileSync(path.join(docsDir, 'overview.md'), overviewContent)
    console.log('Copied README.md -> overview.md')
  }

  console.log('Docs content prepared.')
}

main()
