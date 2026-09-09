"""Rule evaluation on closed bars.

Every column produced here is a fact about bar t computed from bars <= t. Acting on it (a fill)
happens at bar t+1 or later; that is the backtester's and paper trader's job, not this module's.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from engine import indicators as ind
from engine.regime import classify
from engine.rules.operands import Computed, operand_value, render_operand, resolve_operand
from engine.schema.strategy import Condition, Strategy

COMPARISONS = {">", "<", ">=", "<=", "=="}
CROSSES = {"crosses_above", "crosses_below"}
MONOTONIC = {"rising", "falling"}
DEFAULT_CROSS_LOOKBACK = 1
DEFAULT_MONOTONIC_LOOKBACK = 3


def as_strategy(spec: Strategy | dict) -> Strategy:
    return spec if isinstance(spec, Strategy) else Strategy.model_validate(spec)


def _lookback(cond: Condition) -> int:
    if cond.lookback:
        return int(cond.lookback)
    return DEFAULT_MONOTONIC_LOOKBACK if cond.op in MONOTONIC else DEFAULT_CROSS_LOOKBACK


def render_condition(cond: Condition | dict) -> str:
    cond = cond if isinstance(cond, Condition) else Condition.model_validate(cond)
    lhs, op = render_operand(cond.lhs), str(cond.op)
    if op in MONOTONIC:
        return f"{lhs} {op} over {_lookback(cond)}"
    rhs = render_operand(cond.rhs)
    if op in CROSSES and _lookback(cond) > 1:
        return f"{lhs} {op} {rhs} within {_lookback(cond)}"
    return f"{lhs} {op} {rhs}"


def condition_series(cond: Condition, bars: pd.DataFrame, computed: Computed) -> pd.Series:
    """Boolean Series (NaN -> False) for one condition."""
    lhs = resolve_operand(cond.lhs, bars, computed)
    op, n = str(cond.op), _lookback(cond)
    if op in MONOTONIC:
        if isinstance(lhs, float):
            return pd.Series(False, index=bars.index)
        d = lhs.diff()
        step = (d > 0) if op == "rising" else (d < 0)
        out = step.astype(float).rolling(n).sum() == n
        return out.fillna(False).astype(bool)
    rhs = resolve_operand(cond.rhs, bars, computed)
    if isinstance(lhs, float) and isinstance(rhs, float):
        return pd.Series(_scalar_cmp(op, lhs, rhs), index=bars.index)
    if op == "==":
        out = pd.Series(np.isclose(lhs, rhs, rtol=1e-9, atol=1e-12), index=bars.index)
    elif op in COMPARISONS:
        out = {">": lhs > rhs, "<": lhs < rhs, ">=": lhs >= rhs, "<=": lhs <= rhs}[op]
    else:
        above_now = lhs > rhs if op == "crosses_above" else lhs < rhs
        below_before = lhs <= rhs if op == "crosses_above" else lhs >= rhs
        was_below = below_before.astype(float).rolling(n, min_periods=1).max().shift(1) > 0
        out = above_now & was_below
    if isinstance(out, np.ndarray | bool):
        out = pd.Series(out, index=bars.index)
    return out.fillna(False).astype(bool)


def _scalar_cmp(op: str, a: float, b: float) -> bool:
    return {">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b, "==": math.isclose(a, b)}[op]


def evaluate(
    spec: Strategy | dict,
    bars: pd.DataFrame,
    inputs: Computed | None = None,
    regime: pd.Series | None = None,
) -> pd.DataFrame:
    """One row per bar: ts, long_setup, short_setup, regime, regime_ok and one boolean column per
    condition (named by its rendered expression). Setups ignore regime_affinity; `regime_ok` says
    whether the bar's regime is in the affinity list (empty list = always ok)."""
    spec = as_strategy(spec)
    computed = inputs if inputs is not None else ind.compute_inputs(bars, spec.inputs)
    out = pd.DataFrame({"ts": bars["ts"]}, index=bars.index)
    cols: dict[str, pd.Series] = {}

    def all_of(conds: list[Condition] | None) -> pd.Series:
        if not conds:
            return pd.Series(False, index=bars.index)
        acc = pd.Series(True, index=bars.index)
        for c in conds:
            name = render_condition(c)
            if name not in cols:
                cols[name] = condition_series(c, bars, computed)
            acc &= cols[name]
        return acc

    long_setup = all_of(spec.entry_long)
    short_setup = all_of(spec.entry_short)
    reg = regime if regime is not None else classify(bars)
    affinity = {str(r) for r in spec.regime_affinity}
    out["long_setup"] = long_setup
    out["short_setup"] = short_setup
    out["regime"] = reg.to_numpy()
    out["regime_ok"] = reg.isin(affinity).to_numpy() if affinity else True
    for name, s in cols.items():
        out[name] = s.to_numpy()
    return out


def conditions_trace(spec: Strategy | dict, row: pd.Series, side: str = "long") -> tuple[list[str], list[str]]:
    spec = as_strategy(spec)
    conds = spec.entry_long if side == "long" else (spec.entry_short or [])
    passed, failed = [], []
    for c in conds:
        name = render_condition(c)
        (passed if bool(row.get(name, False)) else failed).append(name)
    return passed, failed


# --- price levels ----------------------------------------------------------------------------


def _at(x: pd.Series | float, i: int) -> float | None:
    v = x if isinstance(x, float) else x.iloc[i]
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def _ref_series(ref: str, bars: pd.DataFrame, inputs: Computed) -> pd.Series | float:
    return resolve_operand(ref, bars, inputs)


def stop_price(spec: Strategy | dict, bars: pd.DataFrame, i: int, side: str, inputs: Computed) -> float | None:
    """Initial stop for a signal on closed bar i. None when it cannot be placed (NaN inputs or the
    level lands on the wrong side of the signal close)."""
    spec = as_strategy(spec)
    if spec.stop is None:
        return None
    p: dict[str, Any] = spec.stop.params
    long = side == "long"
    close = float(bars["close"].iloc[i])
    kind = str(spec.stop.type)
    if kind == "signal_bar":
        buf = float(p.get("buffer_pct", 0.0)) / 100
        lvl = float(bars["low"].iloc[i]) * (1 - buf) if long else float(bars["high"].iloc[i]) * (1 + buf)
    elif kind == "swing":
        sw = _swing_cached(bars, int(p.get("lookback", 5)), inputs)
        lvl = _at(sw["low"] if long else sw["high"], i)
    elif kind == "atr":
        a = _at(_atr_cached(bars, int(p.get("length", 14)), inputs), i)
        mult = float(p.get("mult", 2.0))
        lvl = None if a is None else (close - mult * a if long else close + mult * a)
    elif kind == "indicator":
        lvl = _at(_ref_series(str(p["ref"]), bars, inputs), i)
    elif kind == "fixed_pct":
        pct = float(p.get("pct", 1.0)) / 100
        lvl = close * (1 - pct) if long else close * (1 + pct)
    else:
        raise ValueError(f"unknown stop type {kind!r}")
    if lvl is None or math.isnan(lvl):
        return None
    if (long and lvl >= close) or (not long and lvl <= close):
        return None
    return float(lvl)


def target_prices(
    spec: Strategy | dict,
    entry: float,
    stop: float,
    side: str,
    inputs: Computed,
    i: int,
    bars: pd.DataFrame | None = None,
) -> list[float]:
    """Targets beyond the entry, in spec order; unresolvable ones (NaN, wrong side) are dropped."""
    spec = as_strategy(spec)
    long, risk = side == "long", abs(entry - stop)
    out: list[float] = []
    for t in spec.targets:
        kind = str(t.type)
        if kind == "rr":
            lvl = entry + t.value * risk if long else entry - t.value * risk
        elif kind == "fixed_pct":
            lvl = entry * (1 + t.value / 100) if long else entry * (1 - t.value / 100)
        elif kind == "indicator":
            if not t.ref:
                continue
            lvl = _at(_ref_series(t.ref, bars if bars is not None else pd.DataFrame(), inputs), i)
        else:
            raise ValueError(f"unknown target type {kind!r}")
        if lvl is None or math.isnan(lvl):
            continue
        if (long and lvl > entry) or (not long and lvl < entry):
            out.append(float(lvl))
    return out


# Cached helper series live in the `inputs` dict under reserved keys so the backtester does not
# recompute them per bar.
def _swing_cached(bars: pd.DataFrame, lookback: int, inputs: Computed) -> pd.DataFrame:
    key = f"__swing_{lookback}"
    if key not in inputs:
        inputs[key] = ind.swing(bars, lookback)
    return inputs[key]  # type: ignore[return-value]


def _atr_cached(bars: pd.DataFrame, length: int, inputs: Computed) -> pd.Series:
    key = f"__atr_{length}"
    if key not in inputs:
        inputs[key] = ind.atr(bars, length)
    return inputs[key]  # type: ignore[return-value]


def trailing_stop(
    spec: Strategy | dict,
    bars: pd.DataFrame,
    i: int,
    side: str,
    entry: float,
    stop: float,
    initial_risk: float,
    inputs: Computed,
) -> float:
    """New stop after closed bar i; never loosens. Takes effect from bar i+1."""
    spec = as_strategy(spec)
    kind, p = str(spec.trailing.type), spec.trailing.params
    long = side == "long"
    cand: float | None = None
    if kind == "none":
        return stop
    if kind == "indicator":
        cand = _at(_ref_series(str(p["ref"]), bars, inputs), i)
    elif kind == "atr":
        a = _at(_atr_cached(bars, int(p.get("length", 14)), inputs), i)
        if a is not None:
            close = float(bars["close"].iloc[i])
            mult = float(p.get("mult", 2.0))
            cand = close - mult * a if long else close + mult * a
    elif kind == "breakeven_after_r":
        r = float(p.get("r", 1.0))
        close = float(bars["close"].iloc[i])
        if (long and close >= entry + r * initial_risk) or (not long and close <= entry - r * initial_risk):
            cand = entry
    else:
        raise ValueError(f"unknown trailing type {kind!r}")
    if cand is None or math.isnan(cand):
        return stop
    return max(stop, cand) if long else min(stop, cand)


def describe_trigger(spec: Strategy | dict) -> str:
    spec = as_strategy(spec)
    t, off = str(spec.trigger.type), spec.trigger.offset_pct or 0.0
    return {
        "next_bar_open": "fill at the next bar's open",
        "break_of_signal_bar": f"stop order beyond the signal bar's extreme (+{off:g}%), valid one bar",
        "bar_close": "idealised fill at the signal bar's close",
        "limit": f"limit at the signal close offset {off:g}%, valid one bar",
    }[t]


__all__ = [
    "as_strategy",
    "condition_series",
    "conditions_trace",
    "describe_trigger",
    "evaluate",
    "operand_value",
    "render_condition",
    "stop_price",
    "target_prices",
    "trailing_stop",
]
