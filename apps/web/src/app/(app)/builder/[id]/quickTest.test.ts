import { describe, expect, it } from "vitest";
import type { BacktestResult, Stats } from "@/lib/types";
import { conditionRows, equityPoints, isoDay, skipRows, windowSentence } from "./quickTest.pure";

const stats = (o: Partial<Stats>): Stats => ({
  trades: 0, wins: 0, losses: 0, win_rate: 0, expectancy_r: 0, gross_expectancy_r: 0, cost_per_trade_r: 0, avg_win_r: 0, avg_loss_r: 0, profit_factor: 0, net_pnl: 0,
  max_drawdown_pct: 0, max_drawdown_r: 0, largest_trade_share: 0, ...o,
});

/** The engine's reply to `POST /backtest { spec, window: "in_sample" }`, in the shape services/engine/engine/services/strategies.py writes. */
export const quickTestReply: BacktestResult = {
  trades: [],
  equity: [["2024-01-02T09:15:00", 200000], ["2024-03-11T10:30:00", 201800], ["2024-06-20T14:00:00", 199600], ["2025-05-23T15:15:00", 204100]],
  stats: stats({ trades: 48, wins: 21, losses: 27, win_rate: 0.4375, expectancy_r: 0.09, gross_expectancy_r: 0.22, cost_per_trade_r: 0.13, avg_win_r: 1.4, avg_loss_r: -0.93, profit_factor: 1.18, net_pnl: 4100, max_drawdown_pct: 4.2, max_drawdown_r: 8.4, largest_trade_share: 0.11, skipped_for_size: 570, skipped_for_rr: 0, skipped_day_limit: 3, cancelled_orders: 0 }),
  by_regime: {},
  start_equity: 200000,
  condition_stats: {
    "close > ema20": { side: "long", true_pct: 54.2, true_bars: 9871 },
    "rsi14 < 35": { side: "long", true_pct: 6.1, true_bars: 1112 },
  },
  setup_bars: { long: 115, short: 0, bars: 18210 },
  window: { kind: "in_sample", start: "2024-01-01T00:00:00", end: "2025-05-26T00:00:00", oos_from: "2025-05-26T00:00:00", in_sample_pct: 70, note: "First 70% of the data." },
};

describe("quick test helpers", () => {
  it("builds the window sentence from the engine's dates and says so when there is none", () => {
    expect(windowSentence(quickTestReply.window)).toBe("First 70% of the data (2024-01-01 → 2025-05-26). The last 30% stays locked until you Validate, so this cannot be tuned to the test window.");
    expect(windowSentence(undefined)).toMatch(/did not say which window/);
    expect(isoDay("2024-01-01T09:15:00")).toBe("2024-01-01");
    expect(isoDay(undefined)).toBe("–");
  });
  it("lists only the non-zero skip counters in plain words", () => {
    expect(skipRows(quickTestReply.stats)).toEqual([["skipped: sized to zero", 570], ["skipped: over the day limit", 3]]);
    expect(skipRows(stats({}))).toEqual([]);
    expect(skipRows(null)).toEqual([]);
  });
  it("sorts entry conditions so the bottleneck comes first", () => {
    const rows = conditionRows(quickTestReply.condition_stats);
    expect(rows.map((x) => x.name)).toEqual(["rsi14 < 35", "close > ema20"]);
    expect(rows[0].truePct).toBe(6.1);
    expect(conditionRows(undefined)).toEqual([]);
  });
  it("turns the equity series into chart points with day labels", () => {
    const e = equityPoints(quickTestReply.equity);
    expect(e.pts).toEqual([[0, 200000], [1, 201800], [2, 199600], [3, 204100]]);
    expect(e.labels).toEqual(["2024-01-02", "2025-05-23"]);
    expect(equityPoints(undefined).pts).toEqual([]);
  });
});
