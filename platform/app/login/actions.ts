"use server"

import { signIn } from "@/lib/auth"
import { AuthError } from "next-auth"
import { redirect } from "next/navigation"

export async function loginAction(formData: FormData) {
  const email = formData.get("email") as string
  const password = formData.get("password") as string

  try {
    await signIn("credentials", {
      email,
      password,
      redirectTo: "/courses",
    })
  } catch (error) {
    if (error instanceof AuthError) {
      redirect("/login?error=invalid_credentials")
    }
    throw error
  }
}
