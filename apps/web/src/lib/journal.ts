// Journal aggregates: pure functions over closed paper-trade rows, so the page renders from
// Postgres alone and the numbers are unit-tested. Everything here is in R and process terms;
// the single rupee figure is `netRupees`, shown once in the totals ledger.

export interface TradeLike {
  outcomeR: number | null;
  regime: string;
  rulesFollowed: number;
  rulesTotal: number;
  closedAt: Date | string | null;
  side?: string;
  qty?: number;
  costs?: number;
  actual?: { entry: number | null; exit: number | null } | null;
}

export const REGIME_ORDER = ["trend", "range", "compression", "high_vol", "event"];

const r = (t: TradeLike) => t.outcomeR ?? 0;
const time = (t: TradeLike) => (t.closedAt ? new Date(t.closedAt).getTime() : 0);

/** Oldest first. Rows without a close time sort first so they never count as "latest". */
export function chronological<T extends TradeLike>(trades: T[]): T[] {
  return [...trades].sort((a, b) => time(a) - time(b));
}

/** Rules followed as a percentage of rules total across the rows; 0 when nothing to score. */
export function processScore(trades: TradeLike[]): number {
  const total = trades.reduce((a, t) => a + t.rulesTotal, 0);
  if (!total) return 0;
  return (trades.reduce((a, t) => a + t.rulesFollowed, 0) / total) * 100;
}

export interface RegimeRow { regime: string; trades: number; processPct: number; netR: number; avgR: number }

/** One row per regime that has trades, in REGIME_ORDER then alphabetical for unknown regimes. */
export function byRegime(trades: TradeLike[]): RegimeRow[] {
  const groups = new Map<string, TradeLike[]>();
  for (const t of trades) groups.set(t.regime, [...(groups.get(t.regime) ?? []), t]);
  const rank = (k: string) => { const i = REGIME_ORDER.indexOf(k); return i === -1 ? REGIME_ORDER.length : i; };
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([regime, rows]) => {
      const netR = rows.reduce((a, t) => a + r(t), 0);
      return { regime, trades: rows.length, processPct: processScore(rows), netR, avgR: rows.length ? netR / rows.length : 0 };
    });
}

export interface Totals { trades: number; wins: number; winRate: number; netR: number; avgR: number; processPct: number }

export function totals(trades: TradeLike[]): Totals {
  const n = trades.length;
  const wins = trades.filter((t) => r(t) > 0).length;
  const netR = trades.reduce((a, t) => a + r(t), 0);
  return { trades: n, wins, winRate: n ? (wins / n) * 100 : 0, netR, avgR: n ? netR / n : 0, processPct: processScore(trades) };
}

/** Realised rupee P&L from actual fills, net of costs. Null when no row carries fills. */
export function netRupees(trades: TradeLike[]): number | null {
  let any = false, sum = 0;
  for (const t of trades) {
    const e = t.actual?.entry, x = t.actual?.exit;
    if (e === null || e === undefined || x === null || x === undefined || !t.qty) continue;
    any = true;
    const gross = (t.side === "short" ? e - x : x - e) * t.qty;
    sum += gross - (t.costs ?? 0);
  }
  return any ? sum : null;
}

export interface Streaks { current: number; longestWin: number; longestLoss: number }

/** `current` is signed: +3 means three wins in a row ending at the latest trade, −2 two losses. Flat trades break streaks. */
export function streaks(trades: TradeLike[]): Streaks {
  let current = 0, longestWin = 0, longestLoss = 0;
  for (const t of chronological(trades)) {
    const v = r(t);
    if (v > 0) current = current > 0 ? current + 1 : 1;
    else if (v < 0) current = current < 0 ? current - 1 : -1;
    else current = 0;
    longestWin = Math.max(longestWin, current);
    longestLoss = Math.max(longestLoss, -current);
  }
  return { current, longestWin, longestLoss };
}

/** The last `n` outcomes, oldest to newest, as a compact mono strip: `+` win, `−` loss, `·` flat. */
export function outcomeStrip(trades: TradeLike[], n = 30): string {
  return chronological(trades)
    .slice(-n)
    .map((t) => (r(t) > 0 ? "+" : r(t) < 0 ? "−" : "·"))
    .join("");
}
