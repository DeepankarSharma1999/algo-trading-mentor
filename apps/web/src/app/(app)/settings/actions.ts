"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { EngineError, engine } from "@/lib/engine";
import { PROFILES, isTightening, oneR } from "@/lib/risk";
import type { RiskProfile } from "@/lib/types";
import { COST_KEYS } from "./costs";

/** Every action lands back on /settings with one sentence; `tone` picks the notice tint. */
type Tone = "eligible" | "watch" | "blocked";
function back(notice: string, tone: Tone = "eligible"): never {
  revalidatePath("/settings");
  redirect(`/settings?notice=${encodeURIComponent(notice)}&tone=${tone}`);
}

const ENGINE_DOWN = "The engine did not answer, so it will read this change from the database when it is back.";

const rupeeField = (form: FormData, key: string): number | null => {
  const raw = String(form.get(key) ?? "").replace(/[₹,\s]/g, "");
  if (raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? Math.round(n) : null;
};

/** (a) Capital buckets. Three rupee figures; 1R follows from the trading bucket and the profile. */
export async function saveBuckets(form: FormData): Promise<void> {
  const user = await requireUser();
  const safety = rupeeField(form, "safety"), longTerm = rupeeField(form, "long_term"), trading = rupeeField(form, "trading");
  if (safety === null || longTerm === null || trading === null) back("Each bucket needs a whole rupee figure of zero or more. Nothing was changed.", "blocked");
  const profile = await db.profile.update({ where: { userId: user.id }, data: { safetyBucket: safety, longTermBucket: longTerm, tradingBucket: trading } });
  const r1 = oneR(trading, profile.riskProfile as RiskProfile);
  back(`Buckets saved. For you, 1R is now ₹${r1.toLocaleString("en-IN")}.`);
}

/**
 * (b) Risk profile. Tightening is always allowed; loosening only in RESEARCH state, which the engine
 * also enforces. Every change is journaled as a state_events row of kind "profile_change".
 */
export async function saveRiskProfile(form: FormData): Promise<void> {
  const user = await requireUser();
  const to = String(form.get("profile") ?? "") as RiskProfile;
  if (!to) back("Pick a profile first. Nothing was changed.", "blocked");
  if (!(to in PROFILES)) back("That profile is not one of the three on file. Nothing was changed.", "blocked");
  const profile = await db.profile.findUnique({ where: { userId: user.id } });
  if (!profile) redirect("/onboarding");
  const from = profile.riskProfile as RiskProfile;
  if (from === to) back(`Your profile is already ${PROFILES[to].label}.`, "watch");
  if (!isTightening(from, to) && profile.behaviourState !== "RESEARCH") {
    back("Loosening opens in RESEARCH state, after the session closes. Tightening is open now.", "blocked");
  }
  await db.$transaction([
    db.profile.update({ where: { userId: user.id }, data: { riskProfile: to } }),
    db.stateEvent.create({ data: { userId: user.id, kind: "profile_change", fromState: from, toState: to, reason: isTightening(from, to) ? "Tightened from Settings." : "Loosened from Settings in RESEARCH state." } }),
  ]);
  let tail = "";
  try {
    await engine("/risk/profile", { body: { profile: to }, userId: user.id });
  } catch (e) {
    // A 409 means the engine refused the loosening; put the row back so the two never disagree.
    if (e instanceof EngineError && e.status === 409) {
      await db.profile.update({ where: { userId: user.id }, data: { riskProfile: from } });
      back(e.message || "The engine refused the change.", "blocked");
    }
    tail = e instanceof EngineError ? ` The engine answered: ${e.message}` : ` ${ENGINE_DOWN}`;
  }
  const r1 = oneR(Number(profile.tradingBucket), to);
  back(`Profile is now ${PROFILES[to].label}: ${PROFILES[to].perTradePct}% per trade, ${PROFILES[to].dailyR}R a day, ${PROFILES[to].weeklyR}R a week. 1R is ₹${r1.toLocaleString("en-IN")}.${tail}`);
}

/** (c) Cost-model overrides, stored as JSON on the profile (keys documented in ./costs.ts). A blank field removes the override. */
export async function saveCostOverrides(form: FormData): Promise<void> {
  const user = await requireUser();
  const out: Record<string, number> = {};
  for (const k of COST_KEYS) {
    const raw = String(form.get(k) ?? "").trim();
    if (raw === "") continue;
    const n = Number(raw);
    if (!Number.isFinite(n) || n < 0) back(`${k} needs a number of zero or more. Nothing was changed.`, "blocked");
    out[k] = n;
  }
  await db.profile.update({ where: { userId: user.id }, data: { costOverrides: out } });
  const set = Object.keys(out);
  back(set.length ? `Cost overrides saved: ${set.join(", ")}. The next backtest and validation run use them.` : "Cost overrides cleared; the engine's defaults apply.");
}

/** (e) Simulated clock. Pause, resume or set the speed; the row is written here and the engine told. */
export async function setSimClock(form: FormData): Promise<void> {
  await requireUser();
  const op = String(form.get("op") ?? "");
  const data: { running?: boolean; speed?: number } = {};
  if (op === "pause") data.running = false;
  else if (op === "resume") data.running = true;
  else if (op === "speed") {
    const s = Number(form.get("speed"));
    if (!Number.isInteger(s) || s < 1 || s > 600) back("Speed is whole one-minute bars per real second, from 1 to 600. Nothing was changed.", "blocked");
    data.speed = s;
  } else back("Unknown clock control.", "blocked");
  const row = await db.simClock.findFirst();
  if (!row) back("There is no simulated clock row yet; run the seed first.", "blocked");
  await db.simClock.update({ where: { id: row.id }, data });
  let tail = "";
  try { await engine("/sim/clock", { body: data }); } catch { tail = ` ${ENGINE_DOWN}`; }
  back(op === "pause" ? `Clock paused.${tail}` : op === "resume" ? `Clock running.${tail}` : `Clock speed is ${data.speed} bars per second.${tail}`);
}

/** (f) Theme, kept on the profile so it follows the account; the ThemeSetter applies it in the browser. */
export async function saveTheme(form: FormData): Promise<void> {
  const user = await requireUser();
  const theme = String(form.get("theme") ?? "system");
  if (!["system", "light", "dark"].includes(theme)) back("Theme is system, light or dark.", "blocked");
  await db.profile.update({ where: { userId: user.id }, data: { theme } });
  back(theme === "system" ? "Theme follows your system setting." : `Theme is ${theme}.`);
}
