import { hash, verify } from "@node-rs/argon2";
import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";
import { db } from "./db";

const COOKIE = "atm_session";
const TTL_MS = 1000 * 60 * 60 * 24 * 14;

export const hashPassword = (pw: string) => hash(pw, { memoryCost: 19456, timeCost: 2, parallelism: 1 });
export const verifyPassword = (h: string, pw: string) => verify(h, pw);

export async function createSession(userId: string) {
  const id = randomBytes(32).toString("base64url");
  const expiresAt = new Date(Date.now() + TTL_MS);
  await db.session.create({ data: { id, userId, expiresAt } });
  (await cookies()).set(COOKIE, id, { httpOnly: true, sameSite: "lax", path: "/", expires: expiresAt, secure: process.env.NODE_ENV === "production" && process.env.COOKIE_SECURE !== "false" });
}

export async function destroySession() {
  const jar = await cookies();
  const id = jar.get(COOKIE)?.value;
  if (id) await db.session.deleteMany({ where: { id } });
  jar.delete(COOKIE);
}

/** Current user or null. Cached per request. */
export const currentUser = cache(async () => {
  const id = (await cookies()).get(COOKIE)?.value;
  if (!id) return null;
  const s = await db.session.findUnique({ where: { id }, include: { user: { include: { profile: true } } } });
  if (!s || s.expiresAt < new Date()) return null;
  return s.user;
});

/** Redirects to /login when signed out, to /onboarding until the capital firewall is complete. */
export async function requireUser(opts: { allowUnboarded?: boolean } = {}) {
  const u = await currentUser();
  if (!u) redirect("/login");
  if (!opts.allowUnboarded && !u.profile?.onboardedAt) redirect("/onboarding");
  return u;
}
