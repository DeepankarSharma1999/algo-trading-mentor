// Complete ValidationReports in the exact shapes engine/validation/pipeline.py writes, for tests and for
// populating a job row while the engine is down. Deterministic: no randomness. `completeReport` (alias
// `passedReport`) passed with an empty diagnosis; `failedReport` failed at stage 2 and carries the §4b
// diagnosis plus the stage-1 condition statistics, so the fix-it flow renders end to end without the engine.
import type { Stats, SuggestReply, ValidationReport } from "@/lib/types";

const stats = (o: Partial<Stats>): Stats => ({
  trades: 0, wins: 0, losses: 0, win_rate: 0, expectancy_r: 0, gross_expectancy_r: 0, cost_per_trade_r: 0, avg_win_r: 0, avg_loss_r: 0, profit_factor: 0, net_pnl: 0,
  max_drawdown_pct: 0, max_drawdown_r: 0, largest_trade_share: 0, sharpe_ish: 0, skipped_for_size: 0, skipped_invalid_stop: 0,
  skipped_for_rr: 0, skipped_day_limit: 0, cancelled_orders: 0, ...o,
});

const base = stats({ trades: 142, wins: 64, losses: 78, win_rate: 0.451, expectancy_r: 0.21, gross_expectancy_r: 0.33, cost_per_trade_r: 0.12, avg_win_r: 1.62, avg_loss_r: -0.93, profit_factor: 1.43, net_pnl: 59640, max_drawdown_pct: 7.8, max_drawdown_r: 15.6, largest_trade_share: 0.061, sharpe_ish: 0.17 });
const ins = stats({ trades: 104, wins: 48, losses: 56, win_rate: 0.462, expectancy_r: 0.24, gross_expectancy_r: 0.36, cost_per_trade_r: 0.12, avg_win_r: 1.6, avg_loss_r: -0.92, profit_factor: 1.49, net_pnl: 49920, max_drawdown_pct: 6.9, max_drawdown_r: 13.8, largest_trade_share: 0.07, sharpe_ish: 0.19 });
const oos = stats({ trades: 38, wins: 16, losses: 22, win_rate: 0.421, expectancy_r: 0.12, gross_expectancy_r: 0.24, cost_per_trade_r: 0.12, avg_win_r: 1.66, avg_loss_r: -0.95, profit_factor: 1.27, net_pnl: 9120, max_drawdown_pct: 5.4, max_drawdown_r: 10.8, largest_trade_share: 0.12, sharpe_ish: 0.1 });

function equity(n: number, start: number, step: number): [string, number][] {
  const out: [string, number][] = [];
  let e = start;
  for (let i = 0; i < n; i++) {
    e += step * (i % 7 === 3 ? -2.2 : i % 5 === 0 ? 1.8 : 0.6);
    const d = new Date(Date.UTC(2025, 2, 3 + i));
    out.push([d.toISOString().slice(0, 19), Math.round(e)]);
  }
  return out;
}

const window = (i: number) => {
  const a = new Date(Date.UTC(2024, 3 + i * 2, 1)), b = new Date(Date.UTC(2024, 9 + i * 2, 1)), c = new Date(Date.UTC(2024, 11 + i * 2, 1));
  const e = [0.19, 0.08, 0.27, 0.14][i];
  return {
    train: { start: a.toISOString().slice(0, 19), end: b.toISOString().slice(0, 19), trades: 58 + i * 3, expectancy_r: 0.22 + i * 0.01 },
    test: { start: b.toISOString().slice(0, 19), end: c.toISOString().slice(0, 19), trades: 17 + i, expectancy_r: e },
    stats: stats({ trades: 17 + i, wins: 7 + i, losses: 10, win_rate: (7 + i) / (17 + i), expectancy_r: e, net_pnl: Math.round(e * (17 + i) * 2000), max_drawdown_pct: 3.1 + i }),
  };
};

const hist: [number, number][] = [[2, 6], [3.2, 41], [4.4, 138], [5.6, 221], [6.8, 246], [8, 172], [9.2, 98], [10.4, 47], [11.6, 22], [12.8, 9]];

export const completeReport: ValidationReport = {
  strategy_id: "nifty_squeeze_v1",
  started_at: "2025-06-12T10:36:02",
  finished_at: "2025-06-12T10:37:48",
  passed: true,
  weakest_stage: 2,
  weakest_sentence: "Out-of-sample is the weakest stage: expectancy fell to +0.12R after costs over 38 trades, against +0.24R in-sample, so it is validated but keep an eye there.",
  diagnosis: [],
  stages: [
    { stage: 1, name: "In-sample coherence", status: "pass", summary: "142 trades (min 60), inputs clean after 34 warm-up bars, stops and targets on the right side, expectancy +0.21R", metrics: { trades: 142, min_trades: 60, expectancy_r: 0.21, nan_after_warmup: 0, warmup_bars: 34, stop_side_errors: 0, target_side_errors: 0, margin: 1.37 }, detail: { stats: base, warmup_bars: 34, problems: [] } },
    { stage: 2, name: "Out-of-sample", status: "pass", summary: "OOS (last 30%, from 2025-03-03): 38 trades, expectancy +0.12R after costs vs in-sample +0.24R", metrics: { in_sample_expectancy_r: 0.24, oos_expectancy_r: 0.12, oos_trades: 38, oos_fraction: 0.3, margin: 0.12 }, detail: { in_sample: ins, oos, equity: equity(60, 200000, 900) } },
    { stage: 3, name: "Walk-forward", status: "pass", summary: "4 rolling 6-month train / 2-month test: pooled test expectancy +0.17R over 74 trades", metrics: { windows: 4, pooled_test_expectancy_r: 0.17, pooled_test_trades: 74, proportional: 0, margin: 0.17 }, detail: { windows: [0, 1, 2, 3].map(window) } },
    { stage: 4, name: "Cost stress", status: "pass", summary: "expectancy at cost multipliers x1.0: +0.21R, x1.5: +0.14R, x2.0: +0.07R", metrics: { expectancy_x1_0: 0.21, expectancy_x1_5: 0.14, expectancy_x2_0: 0.07, watch: 0, margin: 0.07 }, detail: { multipliers: { "1.0": base, "1.5": stats({ ...base, expectancy_r: 0.14, cost_per_trade_r: 0.19, net_pnl: 39760, profit_factor: 1.28 }), "2.0": stats({ ...base, expectancy_r: 0.07, cost_per_trade_r: 0.26, net_pnl: 19880, profit_factor: 1.13 }) } } },
    { stage: 5, name: "Parameter sensitivity", status: "pass", summary: "3 params x 4 deltas: 92% of neighbours keep expectancy > 0 (need 75%), max deviation 0.11R (limit 0.42R), base +0.21R", metrics: { params: 3, neighbours: 12, plateau_share: 0.92, max_deviation_r: 0.11, deviation_limit_r: 0.42, base_expectancy_r: 0.21, margin: 0.17 }, detail: { params: [
      { name: "inputs.bb.period", base: 20, grid: [{ delta: -20, expectancy: 0.14 }, { delta: -10, expectancy: 0.19 }, { delta: 0, expectancy: 0.21 }, { delta: 10, expectancy: 0.18 }, { delta: 20, expectancy: 0.1 }] },
      { name: "inputs.bb.std", base: 2, grid: [{ delta: -20, expectancy: 0.16 }, { delta: -10, expectancy: 0.2 }, { delta: 0, expectancy: 0.21 }, { delta: 10, expectancy: 0.17 }, { delta: 20, expectancy: -0.02 }] },
      { name: "stop.atr_mult", base: 1.5, grid: [{ delta: -20, expectancy: 0.12 }, { delta: -10, expectancy: 0.19 }, { delta: 0, expectancy: 0.21 }, { delta: 10, expectancy: 0.22 }, { delta: 20, expectancy: 0.15 }] },
    ] } },
    { stage: 6, name: "Regime breakdown", status: "pass", summary: "expectancy by regime: compression: +0.31R over 61, trend: +0.18R over 44, range: +0.05R over 29, high_vol: −0.12R over 8", metrics: { expectancy_compression: 0.31, trades_compression: 61, expectancy_trend: 0.18, trades_trend: 44, expectancy_range: 0.05, trades_range: 29, expectancy_high_vol: -0.12, trades_high_vol: 8, min_regime_expectancy_r: -0.12, margin: -0.12 }, detail: { regimes: {
      compression: stats({ trades: 61, wins: 31, losses: 30, win_rate: 0.508, expectancy_r: 0.31, net_pnl: 37820, max_drawdown_pct: 4.1 }),
      trend: stats({ trades: 44, wins: 20, losses: 24, win_rate: 0.455, expectancy_r: 0.18, net_pnl: 15840, max_drawdown_pct: 5.2 }),
      range: stats({ trades: 29, wins: 11, losses: 18, win_rate: 0.379, expectancy_r: 0.05, net_pnl: 2900, max_drawdown_pct: 6.3 }),
      high_vol: stats({ trades: 8, wins: 2, losses: 6, win_rate: 0.25, expectancy_r: -0.12, net_pnl: -1920, max_drawdown_pct: 3.9 }),
    }, weakest: "high_vol" } },
    { stage: 7, name: "Monte Carlo", status: "pass", summary: "1000 shuffles of 142 trades: max drawdown p5 3.6%, p50 6.9%, p95 11.2% of starting equity (limit 15%, gated on the worst 5% = p95)", metrics: { dd_p5: 3.6, dd_p50: 6.9, dd_p95: 11.2, max_dd_pct: 15, margin: 0.25 }, detail: { dd_p5: 3.6, dd_p50: 6.9, dd_p95: 11.2, histogram: hist } },
    { stage: 8, name: "Paper agreement", status: "skip", summary: "36 paper trades; needs 40 closed paper trades to compare", metrics: { paper_trades: 36, min_paper_trades: 40, backtest_expectancy_r: 0.21 }, detail: { paper: null, backtest: base, agreement: null } },
  ],
};

/** A passed run carries an empty diagnosis; nothing to fix. */
export const passedReport: ValidationReport = completeReport;

/** The same run stopped at stage 2, as the engine writes it while stages are still running. */
export const runningReport: ValidationReport = {
  ...completeReport,
  finished_at: null,
  passed: false,
  weakest_stage: null,
  weakest_sentence: "",
  diagnosis: [],
  stages: completeReport.stages.slice(0, 1).concat(completeReport.stages.slice(1).map((s) => ({ ...s, status: "pending", summary: "", metrics: {}, detail: null }))),
};

// ---- a failed run with a diagnosis (§4b) ---------------------------------------------------------------
// The rules: close > ema20, rsi14 < 35, volume_ratio20 > 1.5 on 15m bars; the RSI condition is the bottleneck.
const s1 = stats({ trades: 71, wins: 29, losses: 42, win_rate: 0.408, expectancy_r: -0.04, gross_expectancy_r: 0.09, cost_per_trade_r: 0.13, avg_win_r: 1.31, avg_loss_r: -0.97, profit_factor: 0.93, net_pnl: -5680, max_drawdown_pct: 9.4, max_drawdown_r: 18.8, largest_trade_share: 0.14, sharpe_ish: -0.03, skipped_for_size: 23, skipped_for_rr: 11, skipped_day_limit: 4, skipped_invalid_stop: 0, cancelled_orders: 6 });
const f_ins = stats({ trades: 50, wins: 21, losses: 29, win_rate: 0.42, expectancy_r: -0.03, gross_expectancy_r: 0.1, cost_per_trade_r: 0.13, avg_win_r: 1.33, avg_loss_r: -0.96, profit_factor: 0.96, net_pnl: -3000, max_drawdown_pct: 7.1, max_drawdown_r: 14.2, largest_trade_share: 0.16, sharpe_ish: -0.02 });
const f_oos = stats({ trades: 21, wins: 8, losses: 13, win_rate: 0.381, expectancy_r: -0.07, gross_expectancy_r: 0.06, cost_per_trade_r: 0.13, avg_win_r: 1.27, avg_loss_r: -0.98, profit_factor: 0.86, net_pnl: -2940, max_drawdown_pct: 5.9, max_drawdown_r: 11.8, largest_trade_share: 0.21, sharpe_ish: -0.05 });

export const failedReport: ValidationReport = {
  strategy_id: "nifty_squeeze_v1",
  started_at: "2025-06-14T09:02:11",
  finished_at: "2025-06-14T09:02:58",
  passed: false,
  weakest_stage: 2,
  weakest_sentence: "Out-of-sample failed: expectancy is −0.07R after costs over 21 trades, against −0.03R in-sample; the rules did not carry an edge into data they had never seen.",
  stages: [
    { stage: 1, name: "In-sample coherence", status: "pass", summary: "71 trades (min 60), inputs clean after 34 warm-up bars, stops and targets on the right side, expectancy −0.04R", metrics: { trades: 71, min_trades: 60, expectancy_r: -0.04, nan_after_warmup: 0, warmup_bars: 34, stop_side_errors: 0, target_side_errors: 0, margin: 0.18 }, detail: {
      stats: s1, warmup_bars: 34, problems: [],
      condition_stats: {
        "close > ema20": { side: "long", true_pct: 54.2, true_bars: 9871 },
        "rsi14 < 35": { side: "long", true_pct: 6.1, true_bars: 1112 },
        "volume_ratio20 > 1.5": { side: "long", true_pct: 18.7, true_bars: 3406 },
      },
      setup_bars: { long: 115, short: 0, bars: 18210 },
    } },
    { stage: 2, name: "Out-of-sample", status: "fail", summary: "OOS (last 30%, from 2025-03-03): 21 trades, expectancy −0.07R after costs vs in-sample −0.03R", metrics: { in_sample_expectancy_r: -0.03, oos_expectancy_r: -0.07, oos_trades: 21, oos_fraction: 0.3, margin: -0.07 }, detail: { in_sample: f_ins, oos: f_oos, equity: equity(21, 200000, -300) } },
    ...completeReport.stages.slice(2).map((s) => ({ ...s, status: "pending" as const, summary: "", metrics: {}, detail: null })),
  ],
  diagnosis: [
    {
      stage: 1, kind: "bottleneck_condition", title: "One entry condition is the bottleneck",
      detail: "'rsi14 < 35' held on 6.1% of bars (1112 of 18210). All conditions held together on 115 bars, which became 71 trades against a minimum of 60 for 15m.",
      numbers: { true_pct: 6.1, true_bars: 1112, setups: 115, trades: 71, min_trades: 60 },
      levers: [{ label: "Condition rsi14 < 35", section: "entry", path: "/entry_long/1" }],
    },
    {
      stage: 1, kind: "sized_to_zero", title: "Setups sized to zero",
      detail: "23 setups were skipped because one lot (1 unit) risked more than your 1R of 2,000 rupees from entry to stop. The stop is never widened to fit.",
      numbers: { skipped_for_size: 23, one_r: 2000, lot_size: 1 },
      levers: [
        { label: "Stop rule (a tighter stop type or multiple)", section: "exits", path: "/stop" },
        { label: "Risk per trade", section: "risk", path: "/risk/max_equity_risk_pct" },
      ],
    },
    {
      stage: 2, kind: "costs", title: "Costs exceed the gross edge",
      detail: "Out of sample the rules made +0.06R per trade before brokerage, taxes and fees and −0.07R after; costs take 0.13R per trade. Fewer, larger trades keep more of the edge.",
      numbers: { gross_expectancy_r: 0.06, expectancy_r: -0.07, cost_per_trade_r: 0.13, oos_trades: 21 },
      levers: [{ label: "Timeframe (slower bars, larger moves)", section: "timeframe", path: "/timeframe" }],
    },
  ],
};

/** What the engine's template path answers for `failedReport` (no API key set). */
export const templateSuggestions: SuggestReply = {
  prose: "The RSI threshold is the bottleneck and costs eat the small edge that remains. Loosen the bottleneck a little, move to slower bars so each trade is worth more than its costs, and re-test; do not add conditions.",
  verdict: "fixable",
  source: "template",
  suggestions: [
    { id: "s1", kind: "tune", title: "Loosen the RSI threshold", reason: "rsi14 < 35 held on 6.1% of bars; at 40 it holds more often without changing what the rule means.", patch: [{ path: "/entry_long/1/rhs", from: 35, to: 40 }] },
    { id: "s2", kind: "fix", title: "Slower bars", reason: "Costs take 0.13R per trade against +0.06R gross; on 1h bars each trade covers a larger move.", patch: [{ path: "/timeframe", from: "15m", to: "1h" }] },
    { id: "s3", kind: "simplify", title: "Drop the volume filter", reason: "It removes setups without changing expectancy in-sample.", patch: [{ path: "/entry_long", from: [{ lhs: "close", op: ">", rhs: "ema20" }, { lhs: "rsi14", op: "<", rhs: 35 }, { lhs: "volume_ratio20", op: ">", rhs: 1.5 }], to: [{ lhs: "close", op: ">", rhs: "ema20" }, { lhs: "rsi14", op: "<", rhs: 35 }] }] },
  ],
};
