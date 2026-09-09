"use server";
import { redirect } from "next/navigation";
import { createSession, destroySession, hashPassword, verifyPassword } from "@/lib/auth";
import { db } from "@/lib/db";

export type AuthState = { error?: string };

const email = (f: FormData) => String(f.get("email") ?? "").trim().toLowerCase();
const password = (f: FormData) => String(f.get("password") ?? "");

export async function register(_: AuthState, form: FormData): Promise<AuthState> {
  const e = email(form), p = password(form);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e)) return { error: "Enter a valid email address." };
  if (p.length < 8) return { error: "Use at least 8 characters." };
  if (await db.user.findUnique({ where: { email: e } })) return { error: "That email already has an account. Sign in instead." };
  const u = await db.user.create({ data: { email: e, passwordHash: await hashPassword(p), profile: { create: {} } } });
  await createSession(u.id);
  redirect("/onboarding");
}

export async function login(_: AuthState, form: FormData): Promise<AuthState> {
  const u = await db.user.findUnique({ where: { email: email(form) } });
  if (!u || !(await verifyPassword(u.passwordHash, password(form)))) return { error: "Email or password does not match." };
  await createSession(u.id);
  redirect("/desk");
}

export async function logout() {
  await destroySession();
  redirect("/login");
}
