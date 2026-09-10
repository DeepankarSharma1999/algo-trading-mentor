/**
 * Cost-model overrides live in profile.cost_overrides as JSON. The engine reads these keys and falls
 * back to its defaults for any that are absent; every figure is what the user pays, never a price.
 */
export const COST_KEYS = ["brokerage_per_order", "slippage_bps", "slippage_stress"] as const;
export type CostKey = (typeof COST_KEYS)[number];

export const COST_META: Record<CostKey, { label: string; unit: string; help: string; fallback: string }> = {
  brokerage_per_order: { label: "Brokerage per order", unit: "₹ / order", help: "Flat rupee charge per order, applied to the entry and the exit.", fallback: "20" },
  slippage_bps: { label: "Slippage", unit: "bps / side", help: "Adverse fill in basis points on each side of the trade.", fallback: "3" },
  slippage_stress: { label: "Slippage stress", unit: "x", help: "Multiplier on slippage in the cost-stress stage of validation.", fallback: "1" },
};

/** The overrides as stored, restricted to known keys with finite numbers. */
export function readOverrides(raw: unknown): Partial<Record<CostKey, number>> {
  const out: Partial<Record<CostKey, number>> = {};
  if (!raw || typeof raw !== "object") return out;
  for (const k of COST_KEYS) {
    const v = (raw as Record<string, unknown>)[k];
    if (typeof v === "number" && Number.isFinite(v)) out[k] = v;
  }
  return out;
}
