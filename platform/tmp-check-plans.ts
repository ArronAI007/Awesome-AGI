import { PrismaClient } from "@prisma/client"

const p = new PrismaClient()
async function main() {
  const plans = await p.subscriptionPlan.findMany()
  console.log(JSON.stringify(plans, null, 2))
  await p.$disconnect()
}
main()
