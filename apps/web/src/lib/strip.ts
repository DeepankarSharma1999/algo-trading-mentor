// Data for the persistent top strip, computed from Postgres so the strip works even when the engine is down.
import { db } from "./db";
import { PROFILES, oneR } from "./risk";
import type { BehaviourState, RiskProfile } from "./types";

export interface StripData {
  tradingBucket: number; oneR: number; profile: RiskProfile;
  dailyUsedR: number; dailyLimitR: number; weeklyUsedR: number; weeklyLimitR: number;
  brakes: { daily: boolean; weekly: boolean };
  state: BehaviourState; stateReason: string;
  marketOpen: boolean; simNow: Date | null;
  provider: string;
}

export const IST_SESSION = { start: "09:15", end: "15:30" };

export function isMarketOpen(simNow: Date | null): boolean {
  if (!simNow) return false;
  const dow = simNow.getUTCDay();
  if (dow === 0 || dow === 6) return false;
  const m = simNow.getUTCHours() * 60 + simNow.getUTCMinutes();
  return m >= 9 * 60 + 15 && m < 15 * 60 + 30;
}

function startOfDay(d: Date) { return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())); }
function startOfWeek(d: Date) { const s = startOfDay(d); s.setUTCDate(s.getUTCDate() - ((s.getUTCDay() + 6) % 7)); return s; }

export async function stripData(userId: string): Promise<StripData> {
  const [profile, clockRow] = await Promise.all([
    db.profile.findUnique({ where: { userId } }),
    db.simClock.findFirst(),
  ]);
  const rp = (profile?.riskProfile ?? "conservative") as RiskProfile;
  const trading = Number(profile?.tradingBucket ?? 0);
  const simNow = clockRow?.now ?? null;
  const dayStart = simNow ? startOfDay(simNow) : new Date(0);
  const weekStart = simNow ? startOfWeek(simNow) : new Date(0);
  const closed = await db.paperTrade.findMany({ where: { userId, status: "closed", closedAt: { gte: weekStart } }, select: { outcomeR: true, closedAt: true } });
  const loss = (rows: typeof closed) => rows.reduce((a, t) => a + Math.max(0, -(t.outcomeR ?? 0)), 0);
  const dailyUsed = loss(closed.filter((t) => t.closedAt && t.closedAt >= dayStart));
  const weeklyUsed = loss(closed);
  const p = PROFILES[rp];
  return {
    tradingBucket: trading, oneR: oneR(trading, rp), profile: rp,
    dailyUsedR: dailyUsed, dailyLimitR: p.dailyR, weeklyUsedR: weeklyUsed, weeklyLimitR: p.weeklyR,
    brakes: { daily: dailyUsed >= p.dailyR, weekly: weeklyUsed >= p.weeklyR },
    state: (profile?.behaviourState ?? "RESEARCH") as BehaviourState, stateReason: profile?.stateReason ?? "",
    marketOpen: isMarketOpen(simNow), simNow,
    provider: process.env.DATA_PROVIDER ?? "synthetic",
  };
}
