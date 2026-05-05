import fs from "fs"
import path from "path"

const schemaDir = path.join(process.cwd(), "prisma")
const devSchema = path.join(schemaDir, "schema.prisma")
const backupSchema = path.join(schemaDir, "schema.dev.prisma")

if (fs.existsSync(backupSchema)) {
  fs.copyFileSync(backupSchema, devSchema)
  fs.unlinkSync(backupSchema)
  console.log("Restored development SQLite schema.")
} else {
  console.log("No backup schema found.")
}
