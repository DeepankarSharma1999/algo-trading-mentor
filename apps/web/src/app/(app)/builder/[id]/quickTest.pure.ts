// Pure helpers behind the Builder's quick-test panel. Kept out of the component so they can be unit-tested
// against the engine's reply shape without React.
import type { BacktestResult, BacktestWindow, ConditionStat, SkipCounter, Stats } from "@/lib/types";

/** "2024-01-01" from an ISO timestamp, without a timezone shift; anything else is echoed as given. */
export const isoDay = (s: string | null | undefined): string => (s && /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : s ?? "–");

/**
 * The one help line under the panel label. Built from the window the engine reports; when it did not report
 * one (an older engine, or a reply that ran on all the data) the sentence says so instead of guessing.
 */
export function windowSentence(w: BacktestWindow | null | undefined): string {
  if (!w || !Number.isFinite(Number(w.in_sample_pct))) return "The engine did not say which window it ran on, so this may have used all of the data, not just the first part.";
  const pct = Math.round(Number(w.in_sample_pct));
  return `First ${pct}% of the data (${isoDay(w.start)} → ${isoDay(w.end)}). The last ${100 - pct}% stays locked until you Validate, so this cannot be tuned to the test window.`;
}

/** Skip counters in plain words, in the order the backtester checks them. */
export const SKIP_WORDS: Record<SkipCounter, string> = {
  skipped_invalid_stop: "skipped: stop on the wrong side",
  skipped_for_size: "skipped: sized to zero",
  skipped_for_rr: "skipped: below your min R:R",
  skipped_day_limit: "skipped: over the day limit",
  cancelled_orders: "cancelled: order not filled next bar",
};

/** Only the non-zero counters, as `[plain words, count]` rows. Nothing when the payload has none. */
export function skipRows(s: Partial<Stats> | null | undefined): [string, number][] {
  if (!s) return [];
  return (Object.keys(SKIP_WORDS) as SkipCounter[])
    .map((k) => [SKIP_WORDS[k], Math.round(Number(s[k]))] as [string, number])
    .filter(([, v]) => Number.isFinite(v) && v > 0);
}

export interface ConditionRow { name: string; side: string; truePct: number; bars: number }
/** Entry conditions sorted ascending by how often they held; the first row is the bottleneck. */
export function conditionRows(stats: Record<string, ConditionStat> | null | undefined): ConditionRow[] {
  return Object.entries(stats ?? {})
    .map(([name, v]) => ({ name, side: typeof v?.side === "string" ? v.side : "–", truePct: Number(v?.true_pct), bars: Number(v?.true_bars) }))
    .filter((x) => Number.isFinite(x.truePct))
    .sort((a, b) => a.truePct - b.truePct);
}

/** Equity as chart points (index, rupees) plus first/last day labels. Bad rows are dropped. */
export function equityPoints(equity: BacktestResult["equity"] | null | undefined): { pts: [number, number][]; labels?: [string, string] } {
  if (!Array.isArray(equity)) return { pts: [] };
  const pts = equity.map((row, i) => [i, Number(row?.[1])] as [number, number]).filter((p) => Number.isFinite(p[1]));
  const first = equity[0]?.[0], last = equity[equity.length - 1]?.[0];
  const labels = typeof first === "string" && typeof last === "string" ? ([isoDay(first), isoDay(last)] as [string, string]) : undefined;
  return { pts, labels };
}
