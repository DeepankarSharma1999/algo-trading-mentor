"""Event-ordered backtester on closed bars.

Semantics (phase 1):
- A setup on closed bar t is acted on at bar t+1 per trigger type (`bar_close` is the one
  idealised exception: it fills at bar t's close and is only for users who explicitly pick it).
- Slippage (bps x stress x cost_multiplier) is embedded in every fill price; `costs` on a trade are
  brokerage + statutory charges only, so gross_pnl already carries the slippage.
- Exits are checked in bar order: stop (gap-through fills at the open), then the FIRST target
  (which closes the whole position — scaling out is phase 2), then the trailing stop is updated
  for the next bar, then time exits (max_bars, at_time, flat_at_close, end of data). When a bar
  touches both stop and target the stop wins (conservative).
- Sizing: qty = floor(one_r / rupee risk per unit), rounded down to whole lots when lot_size > 1.
  The stop is never widened to fit a size; trades that size below one lot are skipped and counted.
- risk.min_rr_after_costs is enforced on the first target using the all-in cost estimate
  (conservative: entry slippage is counted twice). risk.max_trades_per_day is enforced per symbol.
- regime_affinity is NOT enforced by default (so the regime breakdown stage sees every regime);
  pass enforce_regime_affinity=True to trade only inside the affinity list.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from engine import indicators as ind
from engine.costs import CostParams, round_trip_cost
from engine.rules.engine import (
    as_strategy,
    evaluate,
    render_condition,
    stop_price,
    target_prices,
    trailing_stop,
)
from engine.rules.operands import Computed
from engine.schema.strategy import Strategy

TF_MINUTES: dict[str, int] = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "1D": 375}
SESSION_OPEN = pd.Timedelta(hours=9, minutes=15)
BAR_COLUMNS = ["ts", "open", "high", "low", "close", "volume"]


class BacktestTrade(BaseModel):
    signal_ts: str
    entry_ts: str
    exit_ts: str
    side: str
    symbol: str
    qty: int
    entry: float
    exit: float
    stop: float
    target: float | None
    gross_pnl: float
    costs: float
    net_pnl: float
    r_multiple: float
    mfe_r: float
    mae_r: float
    exit_reason: str
    regime: str
    bars_held: int


class Stats(BaseModel):
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    expectancy_r: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    profit_factor: float = 0.0  # 99.0 caps the no-loss case so the value stays JSON-safe
    net_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_r: float = 0.0
    largest_trade_share: float = 0.0
    sharpe_ish: float = 0.0  # mean R / stdev R over trades (not annualised)
    gross_expectancy_r: float = 0.0  # before brokerage, taxes and fees (slippage is in the fill price)
    cost_per_trade_r: float = 0.0  # gross - net, per trade, in R
    skipped_for_size: int = 0
    skipped_invalid_stop: int = 0
    skipped_for_rr: int = 0
    skipped_day_limit: int = 0
    cancelled_orders: int = 0


class ConditionStat(BaseModel):
    side: str  # long|short
    true_pct: float  # share of evaluable bars on which the condition held, 0..100
    true_bars: int


class BacktestResult(BaseModel):
    trades: list[BacktestTrade] = Field(default_factory=list)
    equity: list[tuple[str, float]] = Field(default_factory=list)
    stats: Stats = Field(default_factory=Stats)
    by_regime: dict[str, Stats] = Field(default_factory=dict)
    start_equity: float = 0.0
    condition_stats: dict[str, ConditionStat] = Field(default_factory=dict)  # rendered condition -> how often it held
    setup_bars: dict[str, int] = Field(default_factory=dict)  # {long, short, bars}: bars on which every entry condition held


# --- helpers --------------------------------------------------------------------------------------


def _condition_stats(spec: Strategy, ev: pd.DataFrame) -> tuple[dict[str, ConditionStat], dict[str, int]]:
    """How often each entry condition held, and how often every condition of a side held together."""
    out: dict[str, ConditionStat] = {}
    for side, conds in (("long", spec.entry_long or []), ("short", spec.entry_short or [])):
        for c in conds:
            name = render_condition(c)
            if name not in ev.columns:
                continue
            col = ev[name]
            valid = col.notna()
            held = int((col[valid].astype(bool)).sum())
            out[name] = ConditionStat(side=side, true_pct=round(100.0 * held / int(valid.sum()), 2) if int(valid.sum()) else 0.0, true_bars=held)
    setups = {
        "long": int(np.asarray(ev["long_setup"].to_numpy(), dtype=bool).sum()),
        "short": int(np.asarray(ev["short_setup"].to_numpy(), dtype=bool).sum()),
        "bars": int(len(ev)),
    }
    return out, setups


def _hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def auto_segment(spec: Strategy) -> str:
    """NSE_EQ intraday timeframes -> eq_intraday, NSE_EQ daily -> eq_delivery, NSE_FO -> fo_futures
    (options need a chain; no phase-1 template trades premiums)."""
    if str(spec.market) == "NSE_FO":
        return "fo_futures"
    return "eq_delivery" if str(spec.timeframe) == "1D" else "eq_intraday"


# Canonical resampler lives in engine.data.resample; re-exported here for callers and tests.
from engine.data.resample import resample_bars  # noqa: E402


def compute_stats(trades: list[BacktestTrade], start_equity: float) -> Stats:
    if not trades:
        return Stats()
    r = np.array([t.r_multiple for t in trades])
    net = np.array([t.net_pnl for t in trades])
    wins, losses = r[r > 0], r[r <= 0]
    gross_profit, gross_loss = net[net > 0].sum(), -net[net < 0].sum()
    eq = start_equity + np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate([[start_equity], eq]))
    dd_pct = ((peak[1:] - eq) / start_equity * 100).max() if start_equity > 0 else 0.0
    cum_r = np.cumsum(r)
    dd_r = (np.maximum.accumulate(np.concatenate([[0.0], cum_r]))[1:] - cum_r).max()
    if gross_loss > 0:
        pf = float(gross_profit / gross_loss)
    else:
        pf = 99.0 if gross_profit > 0 else 0.0
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    risk_rs = np.array([abs(t.entry - t.stop) * t.qty for t in trades])
    gross_r = np.where(risk_rs > 0, np.array([t.gross_pnl for t in trades]) / np.where(risk_rs > 0, risk_rs, 1.0), 0.0)
    return Stats(
        trades=len(r),
        wins=int(len(wins)),
        losses=int(len(losses)),
        win_rate=float(len(wins) / len(r)),
        expectancy_r=float(r.mean()),
        avg_win_r=float(wins.mean()) if len(wins) else 0.0,
        avg_loss_r=float(losses.mean()) if len(losses) else 0.0,
        profit_factor=pf,
        net_pnl=float(net.sum()),
        max_drawdown_pct=float(max(dd_pct, 0.0)),
        max_drawdown_r=float(max(dd_r, 0.0)),
        largest_trade_share=float(net[net > 0].max() / gross_profit) if gross_profit > 0 else 0.0,
        sharpe_ish=float(r.mean() / sd) if sd > 0 else 0.0,
        gross_expectancy_r=float(gross_r.mean()),
        cost_per_trade_r=float(gross_r.mean() - r.mean()),
    )


def build_equity(trades: list[BacktestTrade], start_equity: float, first_ts: str | None) -> list[tuple[str, float]]:
    eq = start_equity
    out: list[tuple[str, float]] = [(first_ts, eq)] if first_ts else []
    for t in trades:
        eq += t.net_pnl
        out.append((t.exit_ts, eq))
    return out


def stats_by_regime(trades: list[BacktestTrade], start_equity: float) -> dict[str, Stats]:
    groups: dict[str, list[BacktestTrade]] = defaultdict(list)
    for t in trades:
        groups[t.regime].append(t)
    return {k: compute_stats(v, start_equity) for k, v in sorted(groups.items())}


def _iso(ts: Any) -> str:
    return pd.Timestamp(ts).isoformat()


# --- the engine -----------------------------------------------------------------------------------


def run_backtest(
    spec: Strategy | dict,
    bars: pd.DataFrame,
    cost_params: CostParams = CostParams(),
    cost_multiplier: float = 1.0,
    one_r_rupees: float = 10_000.0,
    lot_size: int = 1,
    segment: str | None = None,
    *,
    start: Any = None,
    end: Any = None,
    inputs: Computed | None = None,
    regime: pd.Series | None = None,
    enforce_regime_affinity: bool = False,
    symbol: str | None = None,
) -> BacktestResult:
    """Single-instrument run. `start`/`end` restrict signal bars to [start, end) while indicators
    still warm up on the full history; an open position is closed at the range's last bar."""
    spec = as_strategy(spec)
    if spec.stop is None:
        raise ValueError("strategy has no stop rule")
    bars = bars.reset_index(drop=True)
    n = len(bars)
    symbol = symbol or (spec.instruments[0].root if spec.instruments else "?")
    segment = segment or auto_segment(spec)
    params = cost_params.scaled(cost_multiplier)
    slip = params.slippage_bps / 10_000 * params.stress_multiplier
    start_equity = 100 * one_r_rupees
    computed: Computed = dict(inputs) if inputs is not None else ind.compute_inputs(bars, spec.inputs)
    ev = evaluate(spec, bars, computed, regime)
    long_setup, short_setup = ev["long_setup"].to_numpy(), ev["short_setup"].to_numpy()
    condition_stats, setup_bars = _condition_stats(spec, ev)
    regime_ok = np.asarray(ev["regime_ok"].to_numpy(), dtype=bool)
    regimes = ev["regime"].to_numpy()
    if not enforce_regime_affinity:
        regime_ok = np.ones(n, dtype=bool)

    o, h, lo, c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    ts = bars["ts"]
    dates = ts.dt.normalize().to_numpy()
    mod = (ts.dt.hour * 60 + ts.dt.minute).to_numpy()
    daily = str(spec.timeframe) == "1D"
    tf_min = TF_MINUTES[str(spec.timeframe)]
    start_min, end_min = _hhmm(spec.session.start), _hhmm(spec.session.end)
    at_min = _hhmm(spec.time_exit.at_time) if spec.time_exit.at_time else None
    max_bars = spec.time_exit.max_bars
    last_of_day = np.ones(n, dtype=bool)
    last_of_day[:-1] = dates[1:] != dates[:-1]
    in_range = np.ones(n, dtype=bool)
    if start is not None:
        in_range &= (ts >= pd.Timestamp(start)).to_numpy()
    if end is not None:
        in_range &= (ts < pd.Timestamp(end)).to_numpy()
    idx_in = np.flatnonzero(in_range)
    if len(idx_in) == 0:
        return BacktestResult(start_equity=start_equity)
    range_last = int(idx_in[-1])
    trigger, offset = str(spec.trigger.type), (spec.trigger.offset_pct or 0.0) / 100
    trailing = str(spec.trailing.type) != "none"
    min_rr = spec.risk.min_rr_after_costs
    max_per_day = spec.risk.max_trades_per_day
    stats = Stats()
    trades: list[BacktestTrade] = []
    entries_on_day: dict[Any, int] = defaultdict(int)
    order: dict[str, Any] | None = None
    pos: dict[str, Any] | None = None

    def entry_ok(t: int) -> bool:
        if t + 1 >= n or not in_range[t] or not in_range[t + 1]:
            return False
        if daily:
            return True
        if dates[t + 1] != dates[t] or mod[t] < start_min:
            return False
        if at_min is not None and mod[t + 1] + tf_min > at_min:
            return False  # a time exit at at_time means flat by then; do not enter into it
        return mod[t + 1] >= start_min and mod[t + 1] + 2 * tf_min <= end_min

    def try_fill(od: dict[str, Any], i: int) -> float | None:
        long = od["side"] == "long"
        if trigger == "next_bar_open":
            return o[i]
        if trigger == "break_of_signal_bar":
            lvl = od["sig_high"] * (1 + offset) if long else od["sig_low"] * (1 - offset)
            if long and h[i] >= lvl:
                return max(o[i], lvl)
            if not long and lo[i] <= lvl:
                return min(o[i], lvl)
            return None
        if trigger == "limit":
            lvl = od["sig_close"] * (1 - offset) if long else od["sig_close"] * (1 + offset)
            if long and lo[i] <= lvl:
                return min(o[i], lvl)
            if not long and h[i] >= lvl:
                return max(o[i], lvl)
            return None
        raise ValueError(f"unknown trigger {trigger!r}")

    def open_position(od: dict[str, Any], raw: float, i: int) -> dict[str, Any] | None:
        long, stop = od["side"] == "long", od["stop"]
        entry = raw * (1 + slip) if long else raw * (1 - slip)
        if (long and entry <= stop) or (not long and entry >= stop):
            stats.skipped_invalid_stop += 1
            return None
        risk_unit = abs(entry - stop)
        qty = math.floor(one_r_rupees / risk_unit)
        if lot_size > 1:
            qty = (qty // lot_size) * lot_size
        if qty < max(1, lot_size):
            stats.skipped_for_size += 1
            return None
        targets = target_prices(spec, entry, stop, od["side"], computed, od["signal_i"], bars)
        if targets and min_rr > 0:
            est = round_trip_cost(entry, targets[0], qty, segment, params).total
            rr = (abs(targets[0] - entry) * qty - est) / (risk_unit * qty)
            if rr < min_rr:
                stats.skipped_for_rr += 1
                return None
        entries_on_day[dates[i]] += 1
        return {
            "side": od["side"],
            "entry": entry,
            "stop": stop,
            "initial_stop": stop,
            "risk_unit": risk_unit,
            "qty": qty,
            "targets": targets,
            "entry_i": i,
            "signal_i": od["signal_i"],
            "regime": od["regime"],
            "bars_held": 0,
            "max_h": entry,
            "min_l": entry,
        }

    def check_exit(p: dict[str, Any], i: int) -> tuple[float, str] | None:
        long, stop = p["side"] == "long", p["stop"]
        p["bars_held"] += 1
        p["max_h"], p["min_l"] = max(p["max_h"], h[i]), min(p["min_l"], lo[i])
        reason = "stop" if stop == p["initial_stop"] else "trailing_stop"
        if long and lo[i] <= stop:
            return (o[i] if o[i] <= stop else stop), reason
        if not long and h[i] >= stop:
            return (o[i] if o[i] >= stop else stop), reason
        if p["targets"]:
            tgt = p["targets"][0]
            if long and h[i] >= tgt:
                return (o[i] if o[i] >= tgt else tgt), "target"
            if not long and lo[i] <= tgt:
                return (o[i] if o[i] <= tgt else tgt), "target"
        if trailing:
            p["stop"] = trailing_stop(spec, bars, i, p["side"], p["entry"], stop, p["risk_unit"], computed)
        if max_bars and p["bars_held"] >= max_bars:
            return c[i], "max_bars"
        if at_min is not None and not daily and mod[i] >= at_min:
            return c[i], "time_exit"
        if spec.session.flat_at_close and not daily and last_of_day[i]:
            return c[i], "flat_at_close"
        if i >= range_last or i == n - 1:
            return c[i], "end_of_data"
        return None

    def close_position(p: dict[str, Any], raw: float, reason: str, i: int) -> None:
        long, qty = p["side"] == "long", p["qty"]
        exit_ = raw * (1 - slip) if long else raw * (1 + slip)
        gross = (exit_ - p["entry"]) * qty if long else (p["entry"] - exit_) * qty
        buy, sell = (p["entry"], exit_) if long else (exit_, p["entry"])
        costs = round_trip_cost(buy, sell, qty, segment, params).statutory_total
        net = gross - costs
        risk_rupees = p["risk_unit"] * qty
        mfe = (p["max_h"] - p["entry"]) if long else (p["entry"] - p["min_l"])
        mae = (p["entry"] - p["min_l"]) if long else (p["max_h"] - p["entry"])
        trades.append(
            BacktestTrade(
                signal_ts=_iso(ts.iloc[p["signal_i"]]),
                entry_ts=_iso(ts.iloc[p["entry_i"]]),
                exit_ts=_iso(ts.iloc[i]),
                side=p["side"],
                symbol=symbol,
                qty=int(qty),
                entry=float(p["entry"]),
                exit=float(exit_),
                stop=float(p["initial_stop"]),
                target=float(p["targets"][0]) if p["targets"] else None,
                gross_pnl=float(gross),
                costs=float(costs),
                net_pnl=float(net),
                r_multiple=float(net / risk_rupees),
                mfe_r=float(max(mfe, 0.0) / p["risk_unit"]),
                mae_r=float(max(mae, 0.0) / p["risk_unit"]),
                exit_reason=reason,
                regime=str(p["regime"]),
                bars_held=int(p["bars_held"]),
            )
        )

    for i in range(n):
        if order is not None:
            raw = try_fill(order, i)
            if raw is None:
                stats.cancelled_orders += 1
            else:
                pos = open_position(order, raw, i)
            order = None
        if pos is not None:
            hit = check_exit(pos, i)
            if hit is not None:
                close_position(pos, hit[0], hit[1], i)
                pos = None
        if pos is None and order is None and in_range[i]:
            side = None
            if long_setup[i] and regime_ok[i]:
                side = "long"
            elif short_setup[i] and regime_ok[i]:
                side = "short"
            if side is None or not entry_ok(i):
                continue
            if entries_on_day[dates[i]] >= max_per_day:
                stats.skipped_day_limit += 1
                continue
            stop = stop_price(spec, bars, i, side, computed)
            if stop is None:
                stats.skipped_invalid_stop += 1
                continue
            od = {
                "side": side,
                "signal_i": i,
                "stop": stop,
                "sig_high": h[i],
                "sig_low": lo[i],
                "sig_close": c[i],
                "regime": regimes[i],
            }
            if trigger == "bar_close":
                pos = open_position(od, c[i], i)
            else:
                order = od

    result = BacktestResult(
        trades=trades,
        equity=build_equity(trades, start_equity, _iso(ts.iloc[idx_in[0]])),
        stats=compute_stats(trades, start_equity),
        by_regime=stats_by_regime(trades, start_equity),
        start_equity=start_equity,
    )
    for k in ("skipped_for_size", "skipped_invalid_stop", "skipped_for_rr", "skipped_day_limit", "cancelled_orders"):
        setattr(result.stats, k, getattr(stats, k))
    result.condition_stats, result.setup_bars = condition_stats, setup_bars
    return result


def run_backtest_multi(
    spec: Strategy | dict,
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    inputs_by_symbol: dict[str, Computed] | None = None,
    regime_by_symbol: dict[str, pd.Series] | None = None,
    **kw: Any,
) -> BacktestResult:
    """Runs each symbol independently (each sized at one_r), then merges trades chronologically
    and rebuilds the equity curve and stats on the merged sequence."""
    spec = as_strategy(spec)
    results: list[BacktestResult] = []
    for sym, bars in bars_by_symbol.items():
        results.append(
            run_backtest(
                spec,
                bars,
                symbol=sym,
                inputs=(inputs_by_symbol or {}).get(sym),
                regime=(regime_by_symbol or {}).get(sym),
                **kw,
            )
        )
    if not results:
        return BacktestResult()
    trades = sorted((t for r in results for t in r.trades), key=lambda t: (t.entry_ts, t.symbol))
    start_equity = results[0].start_equity
    first_ts = min((r.equity[0][0] for r in results if r.equity), default=None)
    merged = BacktestResult(
        trades=trades,
        equity=build_equity(trades, start_equity, first_ts),
        stats=compute_stats(trades, start_equity),
        by_regime=stats_by_regime(trades, start_equity),
        start_equity=start_equity,
    )
    # Condition hit rates weighted by bars; setup counts summed.
    total_bars = sum(int(r.setup_bars.get("bars", 0)) for r in results) or 1
    names = {k for r in results for k in r.condition_stats}
    for name in names:
        parts = [(r.condition_stats[name], int(r.setup_bars.get("bars", 0))) for r in results if name in r.condition_stats]
        held = sum(cs.true_bars for cs, _ in parts)
        merged.condition_stats[name] = ConditionStat(
            side=parts[0][0].side, true_pct=round(100.0 * held / total_bars, 2), true_bars=held
        )
    merged.setup_bars = {k: sum(int(r.setup_bars.get(k, 0)) for r in results) for k in ("long", "short", "bars")}
    for k in ("skipped_for_size", "skipped_invalid_stop", "skipped_for_rr", "skipped_day_limit", "cancelled_orders"):
        setattr(merged.stats, k, sum(getattr(r.stats, k) for r in results))
    return merged


__all__ = [
    "TF_MINUTES",
    "BacktestResult",
    "BacktestTrade",
    "Stats",
    "auto_segment",
    "build_equity",
    "compute_stats",
    "resample_bars",
    "run_backtest",
    "run_backtest_multi",
    "stats_by_regime",
]
