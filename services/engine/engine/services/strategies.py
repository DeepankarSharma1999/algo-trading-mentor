"""Strategy checks and synchronous backtests for the Builder preview."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pydantic import ValidationError

from engine import indicators as ind
from engine.backtest import (
    BacktestResult,
    ConditionStat,
    auto_segment,
    build_equity,
    compute_stats,
    run_backtest,
    stats_by_regime,
)
from engine.costs import CostParams
from engine.data import lot_size
from engine.rules.engine import as_strategy, render_condition
from engine.rules.operands import referenced_inputs, resolve_operand
from engine.schema.strategy import Strategy
from engine.schema.testable import check_testable
from engine.services import market
from engine.services.common import ApiError
from engine.services.validation import default_range


def _probe_bars(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    ts = pd.date_range("2024-01-01 09:15", periods=n, freq="5min")
    close = 1000 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    return pd.DataFrame(
        {
            "ts": ts,
            "open": close * (1 + rng.normal(0, 0.0002, n)),
            "high": close * (1 + abs(rng.normal(0, 0.0005, n))),
            "low": close * (1 - abs(rng.normal(0, 0.0005, n))),
            "close": close,
            "volume": rng.integers(500, 5000, n).astype(float),
        }
    )


def _pydantic_sentences(e: ValidationError) -> list[str]:
    out = []
    for err in e.errors()[:8]:
        loc = ".".join(str(x) for x in err.get("loc", ()))
        out.append(f"Field {loc or 'spec'}: {err.get('msg', 'invalid')}.")
    return out


def consistency_problems(spec: Strategy) -> list[str]:
    """Engine-side checks the shared validator cannot do: every operand resolves, every ref exists,
    the session is ordered, the stop/target/trailing references point at real inputs."""
    problems: list[str] = []
    bars = _probe_bars()
    try:
        inputs = ind.compute_inputs(bars, spec.inputs)
    except Exception as e:
        return [f"Inputs cannot be computed: {e}."]
    conds = list(spec.entry_long) + list(spec.entry_short or [])
    for c in conds:
        for operand in (c.lhs, c.rhs):
            try:
                resolve_operand(operand, bars, inputs)
            except Exception as e:
                problems.append(f"Condition '{render_condition(c)}': {e}.")
                break
    refs: list[tuple[str, str | None]] = []
    if spec.stop is not None and str(spec.stop.type) == "indicator":
        refs.append(("stop", spec.stop.params.get("ref")))
    if str(spec.trailing.type) == "indicator":
        refs.append(("trailing", spec.trailing.params.get("ref")))
    for i, t in enumerate(spec.targets):
        if str(t.type) == "indicator":
            refs.append((f"targets[{i}]", t.ref))
    for where, ref in refs:
        if not ref:
            problems.append(f"{where} uses an indicator level but names no ref.")
            continue
        try:
            if referenced_inputs(ref) not in spec.inputs and referenced_inputs(ref) is not None:
                raise KeyError(f"unknown input {referenced_inputs(ref)!r}")
            resolve_operand(ref, bars, inputs)
        except Exception as e:
            problems.append(f"{where} ref '{ref}': {e}.")
    if spec.session.start >= spec.session.end:
        problems.append(f"Session start {spec.session.start} is not before session end {spec.session.end}.")
    if spec.time_exit.at_time and not (spec.session.start <= spec.time_exit.at_time <= spec.session.end):
        problems.append(f"Time exit {spec.time_exit.at_time} falls outside the session.")
    return problems


def check(spec_dict: dict) -> dict:
    result = check_testable(spec_dict or {})
    missing = list(result["missing"])
    flags = list((spec_dict or {}).get("ambiguity_flags") or [])
    try:
        spec = Strategy.model_validate(spec_dict)
    except ValidationError as e:
        missing.extend(_pydantic_sentences(e))
        return {"testable": False, "missing": missing, "ambiguity_flags": flags}
    missing.extend(consistency_problems(spec))
    return {"testable": not missing, "missing": missing, "ambiguity_flags": flags}


def in_sample_window(prov: Any, symbols: list[str], oos_fraction: float | None = None) -> dict:
    """The pipeline's chronological split over the full feed: the first (1 - oos_fraction) of the data is the
    in-sample window; everything from `oos_from` on is the out-of-sample window stage 2 reads and stays locked."""
    from engine.validation.gates import AcceptanceGates

    frac = AcceptanceGates().oos_fraction if oos_fraction is None else oos_fraction
    t0s, t1s = [], []
    for sym in symbols:
        d = prov.get_bars(sym, "1D")
        t0s.append(pd.Timestamp(d["ts"].iloc[0]).normalize())
        t1s.append(pd.Timestamp(d["ts"].iloc[-1]).normalize() + pd.Timedelta(days=1))
    t0, t1 = min(t0s), max(t1s)
    split = (t0 + (t1 - t0) * (1 - frac)).normalize()
    pct = int(round((1 - frac) * 100))
    return {
        "kind": "in_sample", "start": t0.isoformat(), "end": split.isoformat(), "oos_from": split.isoformat(),
        "in_sample_pct": pct,
        "note": (f"First {pct}% of the data ({t0.date()} to {(split - pd.Timedelta(days=1)).date()}). The last {100 - pct}% "
                 "stays locked until you Validate, so a quick test cannot be tuned to the test window."),
    }


def backtest(
    spec_dict: dict,
    start: Any = None,
    end: Any = None,
    cost_multiplier: float = 1.0,
    one_r: float = 2000.0,
    cost_params: CostParams = CostParams(),
    window: str | None = None,
) -> dict:
    try:
        spec = as_strategy(spec_dict)
    except ValidationError as e:
        raise ApiError(400, "The strategy does not validate against the schema: " + " ".join(_pydantic_sentences(e))) from e
    if spec.stop is None:
        raise ApiError(400, "The strategy has no stop rule, so it cannot be backtested.")
    if not spec.instruments:
        raise ApiError(400, "The strategy names no instruments.")
    prov = market.provider()
    results: list[BacktestResult] = []
    tf = str(spec.timeframe)
    win: dict | None = None
    if window == "in_sample":
        try:
            win = in_sample_window(prov, [i.root for i in spec.instruments])
        except Exception as e:
            raise ApiError(404, f"No data for the strategy's instruments: {e}") from e
        start, end = win["start"], win["end"]
    elif window not in (None, "", "default"):
        raise ApiError(400, "window must be 'in_sample' or omitted.")
    for inst in spec.instruments:
        sym = inst.root
        try:
            s0, e0 = default_range(prov, sym)
        except Exception as e:
            raise ApiError(404, f"No data for {sym}: {e}") from e
        s = pd.Timestamp(start) if start else s0
        e = pd.Timestamp(end) if end else e0
        if e == e.normalize() and win is None:  # a date-only end covers that day; the in-sample split is exclusive
            e = e + pd.Timedelta(days=1)
        warm = s - pd.Timedelta(days=45 if tf != "1D" else 400)
        bars = prov.get_bars(sym, tf, warm, e)
        results.append(
            run_backtest(
                spec,
                bars,
                cost_params=cost_params,
                cost_multiplier=float(cost_multiplier or 1.0),
                one_r_rupees=one_r,
                lot_size=lot_size(sym, str(spec.market)),
                segment=auto_segment(spec),
                start=s,
                end=e,
                symbol=sym,
            )
        )
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
    for k in ("skipped_for_size", "skipped_invalid_stop", "skipped_for_rr", "skipped_day_limit", "cancelled_orders"):
        setattr(merged.stats, k, sum(getattr(r.stats, k) for r in results))
    # Condition hit rates and setup counts, merged across instruments the same way the pipeline does.
    total_bars = sum(int(r.setup_bars.get("bars", 0)) for r in results) or 1
    for name in {k for r in results for k in r.condition_stats}:
        parts = [r.condition_stats[name] for r in results if name in r.condition_stats]
        true_bars = sum(c.true_bars for c in parts)
        merged.condition_stats[name] = ConditionStat(true_bars=true_bars, true_pct=100.0 * true_bars / total_bars, side=parts[0].side)
    merged.setup_bars = {k: sum(int(r.setup_bars.get(k, 0)) for r in results) for k in ("long", "short", "bars")}
    out = merged.model_dump(mode="json")
    if win is not None:
        out["window"] = win
    return out
