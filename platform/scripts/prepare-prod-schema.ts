import fs from "fs"
import path from "path"

const schemaDir = path.join(process.cwd(), "prisma")
const devSchema = path.join(schemaDir, "schema.prisma")
const prodSchema = path.join(schemaDir, "schema.prod.prisma")
const backupSchema = path.join(schemaDir, "schema.dev.prisma")

if (!fs.existsSync(prodSchema)) {
  console.error("Production schema not found:", prodSchema)
  process.exit(1)
}

// Backup dev schema
fs.copyFileSync(devSchema, backupSchema)
// Copy prod schema to schema.prisma
fs.copyFileSync(prodSchema, devSchema)

console.log("Switched to production PostgreSQL schema.")
