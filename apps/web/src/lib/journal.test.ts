import { describe, expect, it } from "vitest";
import { byRegime, chronological, netRupees, outcomeStrip, processScore, streaks, totals, type TradeLike } from "./journal";

const t = (outcomeR: number | null, regime = "trend", day = 1, followed = 5, total = 5): TradeLike => ({
  outcomeR, regime, rulesFollowed: followed, rulesTotal: total, closedAt: new Date(Date.UTC(2025, 5, day, 10)),
});

describe("journal aggregates", () => {
  it("handles an empty journal", () => {
    expect(totals([])).toEqual({ trades: 0, wins: 0, winRate: 0, netR: 0, avgR: 0, processPct: 0 });
    expect(byRegime([])).toEqual([]);
    expect(streaks([])).toEqual({ current: 0, longestWin: 0, longestLoss: 0 });
    expect(outcomeStrip([])).toBe("");
    expect(netRupees([])).toBeNull();
  });

  it("computes totals in R and the process score from rules followed", () => {
    const rows = [t(1.5, "trend", 1, 5, 5), t(-1, "range", 2, 4, 5), t(2, "trend", 3, 5, 5), t(-0.5, "range", 4, 3, 5)];
    const s = totals(rows);
    expect(s.trades).toBe(4);
    expect(s.wins).toBe(2);
    expect(s.winRate).toBe(50);
    expect(s.netR).toBeCloseTo(2);
    expect(s.avgR).toBeCloseTo(0.5);
    expect(s.processPct).toBeCloseTo(85);
    expect(processScore(rows)).toBeCloseTo(85);
  });

  it("groups by regime in the canonical order", () => {
    const rows = [t(1, "range", 1), t(-1, "trend", 2, 4), t(0.5, "event", 3), t(2, "trend", 4)];
    const g = byRegime(rows);
    expect(g.map((x) => x.regime)).toEqual(["trend", "range", "event"]);
    expect(g[0]).toMatchObject({ trades: 2, netR: 1, avgR: 0.5, processPct: 90 });
    expect(g[1]).toMatchObject({ trades: 1, netR: 1, avgR: 1, processPct: 100 });
  });

  it("puts unknown regimes after the known ones, alphabetically", () => {
    const g = byRegime([t(1, "zeta", 1), t(1, "alpha", 2), t(1, "compression", 3)]);
    expect(g.map((x) => x.regime)).toEqual(["compression", "alpha", "zeta"]);
  });

  it("finds streaks in chronological order regardless of input order", () => {
    // chronological outcomes: + + − − − + + + +  → current +4, longest win 4, longest loss 3
    const rows = [t(1, "t", 8), t(1, "t", 1), t(-1, "t", 3), t(1, "t", 2), t(-1, "t", 4), t(-1, "t", 5), t(1, "t", 6), t(1, "t", 7), t(1, "t", 9)];
    expect(streaks(rows)).toEqual({ current: 4, longestWin: 4, longestLoss: 3 });
    expect(streaks([t(-1, "t", 1), t(-1, "t", 2)])).toEqual({ current: -2, longestWin: 0, longestLoss: 2 });
    expect(chronological(rows).map((x) => (x.closedAt as Date).getUTCDate())).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });

  it("treats a flat trade as a streak break", () => {
    expect(streaks([t(1, "t", 1), t(0, "t", 2), t(1, "t", 3)])).toEqual({ current: 1, longestWin: 1, longestLoss: 0 });
    expect(streaks([t(1, "t", 1), t(null, "t", 2)]).current).toBe(0);
  });

  it("renders the outcome strip newest-last and capped at n", () => {
    const rows = Array.from({ length: 40 }, (_, i) => t(i % 3 === 0 ? -1 : 1, "t", i + 1));
    const strip = outcomeStrip(rows);
    expect(strip).toHaveLength(30);
    expect(strip.at(-1)).toBe(rows[39].outcomeR! > 0 ? "+" : "−");
    expect(outcomeStrip([t(1, "t", 1), t(-1, "t", 2), t(0, "t", 3)])).toBe("+−·");
  });

  it("nets rupees from actual fills, on both sides, minus costs", () => {
    const rows: TradeLike[] = [
      { ...t(1), side: "long", qty: 10, costs: 5, actual: { entry: 100, exit: 110 } },
      { ...t(-1), side: "short", qty: 10, costs: 5, actual: { entry: 100, exit: 105 } },
      { ...t(null), side: "long", qty: 10, costs: 5, actual: { entry: 100, exit: null } },
    ];
    expect(netRupees(rows)).toBeCloseTo(100 - 5 + (-50 - 5));
  });
});
