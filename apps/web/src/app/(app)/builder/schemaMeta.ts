// Editor metadata that the JSON schema does not carry: parameter keys per indicator, output fields of
// multi-output indicators, and parameter keys per stop/trailing type. Mirrors services/engine/engine/indicators.py.
import type { Input } from "@atm/schema";

export type Indicator = Input["indicator"];

export const PARAM_KEYS: Record<Indicator, Record<string, number>> = {
  sma: { length: 20 }, ema: { length: 20 }, rsi: { length: 14 }, macd: { fast: 12, slow: 26, signal: 9 },
  bbands: { length: 20, mult: 2, pct_window: 120 }, atr: { length: 14 }, supertrend: { length: 10, mult: 3 },
  donchian: { length: 20 }, vwap: {}, williams_r: { length: 14 }, psar: { step: 0.02, max_step: 0.2 },
  ichimoku: { tenkan: 9, kijun: 26, senkou_b: 52, displacement: 26 }, pivots: {}, cpr: {}, swing: { lookback: 5 },
  volume_ratio: { window: 20 }, adx: { length: 14 }, heikin_ashi: {},
};

/** Output fields of multi-output indicators; single-output indicators are addressed by input name alone. */
export const OUTPUT_FIELDS: Partial<Record<Indicator, string[]>> = {
  macd: ["macd", "signal", "hist"], bbands: ["upper", "mid", "lower", "bandwidth", "bw_pct"], supertrend: ["line", "direction"],
  donchian: ["upper", "lower", "mid"], vwap: ["vwap", "upper1", "lower1", "upper2", "lower2"],
  ichimoku: ["tenkan", "kijun", "senkou_a", "senkou_b", "chikou"], pivots: ["pp", "r1", "r2", "r3", "s1", "s2", "s3"],
  cpr: ["pivot", "bc", "tc", "width"], swing: ["high", "low"], adx: ["adx", "plus_di", "minus_di"], heikin_ashi: ["open", "high", "low", "close"],
};

export const BAR_FIELDS = ["open", "high", "low", "close", "volume"] as const;

export const STOP_TYPES = ["signal_bar", "swing", "atr", "indicator", "fixed_pct"] as const;
export const STOP_PARAM_KEYS: Record<(typeof STOP_TYPES)[number], Record<string, number | string>> = {
  signal_bar: {}, swing: { lookback: 5 }, atr: { length: 14, mult: 2 }, indicator: { ref: "" }, fixed_pct: { pct: 1 },
};
export const TRAILING_TYPES = ["none", "indicator", "atr", "breakeven_after_r"] as const;
export const TRAILING_PARAM_KEYS: Record<(typeof TRAILING_TYPES)[number], Record<string, number | string>> = {
  none: {}, indicator: { ref: "" }, atr: { length: 14, mult: 3 }, breakeven_after_r: { r: 1 },
};
export const TRIGGER_TYPES = ["next_bar_open", "break_of_signal_bar", "bar_close", "limit"] as const;
export const TARGET_TYPES = ["rr", "indicator", "fixed_pct"] as const;
export const MARKETS = ["NSE_EQ", "NSE_FO"] as const;

export const INSTRUMENT_RE = /^[A-Z0-9&-]{1,20}$/;
export const INPUT_NAME_RE = /^[a-z][a-z0-9_]*$/;
export const TIME_RE = /^[0-2][0-9]:[0-5][0-9]$/;

/** Every operand a condition may name: bar fields, input names, and input.field for multi-output indicators. */
export function operandsFor(inputs: Record<string, Input>): string[] {
  const out: string[] = [...BAR_FIELDS];
  for (const [name, inp] of Object.entries(inputs)) {
    const fields = OUTPUT_FIELDS[inp.indicator];
    if (fields) fields.forEach((f) => out.push(`${name}.${f}`)); else out.push(name);
  }
  return out;
}

// ---- Helper text shown next to the editor's controls. Plain words; the mono field names are computed per input. ----

/** What each indicator measures, for the line under an input row. Output field names are appended by `indicatorHelp`. */
export const INDICATOR_HELP: Record<Indicator, string> = {
  sma: "Simple moving average of close over length bars.",
  ema: "Exponential moving average of close over length bars; reacts faster than sma.",
  rsi: "Relative strength index, 0 to 100, over length bars; below 30 is oversold, above 70 overbought by convention.",
  macd: "Moving-average convergence: the fast minus slow EMA (macd), its signal EMA, and their difference (hist).",
  bbands: "Bollinger bands: a length-bar average with bands mult standard deviations away; bw_pct is the bandwidth percentile over pct_window bars.",
  atr: "Average true range over length bars, in price units; a measure of how far bars move.",
  supertrend: "A trailing line mult ATRs from price; direction is 1 when price is above it and -1 below.",
  donchian: "Highest high and lowest low of the last length bars, and their midpoint.",
  vwap: "Volume-weighted average price for the day, with 1- and 2-sigma bands.",
  williams_r: "Williams %R, -100 to 0, over length bars; near 0 is overbought, near -100 oversold.",
  psar: "Parabolic SAR: a stop-and-reverse level that accelerates by step up to max_step.",
  ichimoku: "Ichimoku lines: tenkan, kijun, the two senkou cloud edges and the lagging chikou.",
  pivots: "Classic daily pivots from the previous session: the pivot pp, resistances r1 to r3, supports s1 to s3.",
  cpr: "Central pivot range from the previous session: pivot, bottom central (bc), top central (tc) and its width.",
  swing: "The most recent swing high and swing low, each confirmed by lookback bars on both sides.",
  volume_ratio: "This bar's volume divided by the average volume of the last window bars; 1.5 means one and a half times normal.",
  adx: "Average directional index over length bars: adx measures trend strength; plus_di and minus_di its direction.",
  heikin_ashi: "Smoothed candles built from the ordinary bars; each field is the smoothed open, high, low or close.",
};

/** The full helper line for one input: what it measures and exactly which operand names it creates. */
export function indicatorHelp(name: string, indicator: Indicator): string {
  const fields = OUTPUT_FIELDS[indicator];
  const operands = fields ? fields.map((f) => `${name}.${f}`).join(", ") : name;
  return `${INDICATOR_HELP[indicator]} Use in a condition as: ${operands}.`;
}

export const OPS_HELP = "Each condition compares a left value with a right value on the closed bar. >, <, >=, <= and == compare their current values; crosses_above and crosses_below hold only on the bar where the left value crosses the right one; rising and falling hold when the left value has risen or fallen over the last lookback bars.";
export const OPERAND_HELP = "Pick an input name, input.field, a bar field (open/high/low/close/volume), or a number.";

export const TRIGGER_HELP: Record<(typeof TRIGGER_TYPES)[number], string> = {
  next_bar_open: "Enter at the open of the bar after the signal bar. Offset is ignored.",
  break_of_signal_bar: "Enter when price breaks the signal bar's high (long) or low (short); offset_pct adds a margin beyond it.",
  bar_close: "Enter at the close of the signal bar itself.",
  limit: "Rest a limit order offset_pct away from the signal close and enter only if price comes to it.",
};

export const STOP_HELP: Record<(typeof STOP_TYPES)[number], string> = {
  signal_bar: "Just beyond the low of the signal bar for a long, or its high for a short. No parameters.",
  swing: "Beyond the most recent swing low (long) or swing high (short), found with lookback bars on each side.",
  atr: "mult times ATR(length) away from the entry price.",
  indicator: "At the current level of an input; ref is the operand name, e.g. st.line or bb.lower.",
  fixed_pct: "pct percent away from the entry price.",
};

export const TRAILING_HELP: Record<(typeof TRAILING_TYPES)[number], string> = {
  none: "The stop stays where it was placed.",
  indicator: "Each bar, move the stop to the level of ref (an operand name) if that is closer to price.",
  atr: "Each bar, keep the stop mult times ATR(length) behind the best price seen.",
  breakeven_after_r: "Once the trade is r R in profit, move the stop to the entry price.",
};

export const TARGET_HELP: Record<(typeof TARGET_TYPES)[number], string> = {
  rr: "A multiple of the initial risk: 2 means take profit at twice the distance to the stop.",
  indicator: "Take profit at the level of an input named in ref; value is kept for the record.",
  fixed_pct: "Take profit a fixed percent away from entry.",
};

export const RISK_HELP = {
  min_rr_after_costs: "Reward divided by risk once brokerage, taxes and slippage are taken off. A signal whose ratio falls below this is skipped, not taken.",
  max_equity_risk_pct: "The most one trade may lose at its stop, as a percent of your trading bucket. 0.5 means half a percent; this feeds position size.",
  max_trades_per_day: "A hard cap. After this many entries in a session the strategy stops signalling for the day.",
};

export const PERMISSION_HELP: Record<"paper_only" | "mentor_only" | "blocked", string> = {
  paper_only: "After validation the strategy can be watched on the Desk, where it replays on paper and logs signals. The only value that can be watched.",
  mentor_only: "The mentor explains and validates it; it never runs on the Desk.",
  blocked: "Kept as a record only: no validation output is acted on and it cannot be watched.",
};
