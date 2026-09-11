export * from "./types";
export { checkTestable, type TestableResult } from "./testable";

export const AUTOMATION_PERMISSIONS = ["paper_only", "mentor_only", "blocked"] as const;
export const REGIMES = ["trend", "range", "compression", "high_vol", "event"] as const;
export const TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "1D"] as const;
export const INDICATORS = ["sma", "ema", "rsi", "macd", "bbands", "atr", "supertrend", "donchian", "vwap", "williams_r", "psar", "ichimoku", "pivots", "cpr", "swing", "volume_ratio", "adx", "heikin_ashi"] as const;
export const OPS = [">", "<", ">=", "<=", "==", "crosses_above", "crosses_below", "rising", "falling"] as const;
export const STRATEGY_STATUSES = ["draft", "testable", "validated", "untested"] as const;
export type StrategyStatus = (typeof STRATEGY_STATUSES)[number];

export function parseStrategyId(id: string): { slug: string; version: number } {
  const m = /^([a-z0-9_]+)_v(\d+)$/.exec(id);
  if (!m) throw new Error(`Bad strategy_id: ${id}`);
  return { slug: m[1], version: Number(m[2]) };
}
export function bumpVersion(id: string): string {
  const { slug, version } = parseStrategyId(id);
  return `${slug}_v${version + 1}`;
}
export function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "strategy";
}

/** Render a condition as a rule expression for the UI and the journal. */
export function conditionText(c: { lhs: string | number; op: string; rhs: string | number; lookback?: number }): string {
  if (c.op === "rising" || c.op === "falling") return `${c.lhs} ${c.op} over ${c.lookback ?? 3} bars`;
  const lb = c.lookback ? ` (within ${c.lookback} bars)` : "";
  return `${c.lhs} ${c.op.replace(/_/g, " ")} ${c.rhs}${lb}`;
}
