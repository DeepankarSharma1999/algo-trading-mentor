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
