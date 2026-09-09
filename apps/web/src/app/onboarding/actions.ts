"use server";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { PROFILES } from "@/lib/risk";
import type { RiskProfile } from "@/lib/types";

export type OnboardingState = { error?: string };

export async function completeOnboarding(_: OnboardingState, form: FormData): Promise<OnboardingState> {
  const user = await requireUser({ allowUnboarded: true });
  const n = (k: string) => Number(String(form.get(k) ?? "").replace(/[^\d.]/g, ""));
  const safety = n("safety"), longTerm = n("long_term"), trading = n("trading");
  const profile = String(form.get("profile") ?? "") as RiskProfile;
  if (![safety, longTerm, trading].every((x) => Number.isFinite(x) && x >= 0)) return { error: "Buckets must be rupee amounts of zero or more." };
  if (trading <= 0) return { error: "The trading bucket must be greater than zero. It is the only bucket that ever sizes a position." };
  if (!(profile in PROFILES)) return { error: "Choose a risk profile." };
  await db.profile.upsert({
    where: { userId: user.id },
    create: { userId: user.id, safetyBucket: safety, longTermBucket: longTerm, tradingBucket: trading, riskProfile: profile, onboardedAt: new Date() },
    update: { safetyBucket: safety, longTermBucket: longTerm, tradingBucket: trading, riskProfile: profile, onboardedAt: new Date() },
  });
  redirect("/desk");
}
