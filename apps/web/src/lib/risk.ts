// Risk profile table (ARCHITECTURE §7). The engine enforces; this mirrors it for display and onboarding.
import type { RiskProfile } from "./types";

export const PROFILES: Record<RiskProfile, { label: string; perTradePct: number; dailyR: number; weeklyR: number; concurrentR: number }> = {
  conservative: { label: "Conservative", perTradePct: 0.25, dailyR: 1.5, weeklyR: 4, concurrentR: 1 },
  standard:     { label: "Standard",     perTradePct: 0.5,  dailyR: 2,   weeklyR: 5, concurrentR: 2 },
  hard_ceiling: { label: "Hard ceiling", perTradePct: 1.0,  dailyR: 3,   weeklyR: 7, concurrentR: 3 },
};
export const PROFILE_ORDER: RiskProfile[] = ["conservative", "standard", "hard_ceiling"];

export function oneR(tradingBucket: number, profile: RiskProfile): number {
  return Math.round((tradingBucket * PROFILES[profile].perTradePct) / 100);
}

/** true when `to` is at least as strict as `from`. Loosening is only allowed in RESEARCH. */
export function isTightening(from: RiskProfile, to: RiskProfile): boolean {
  return PROFILE_ORDER.indexOf(to) <= PROFILE_ORDER.indexOf(from);
}
