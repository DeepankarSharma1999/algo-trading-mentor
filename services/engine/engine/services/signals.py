"""Build the Signal payload (ARCHITECTURE section 4) for one closed bar of one strategy.

Everything the desk shows about a bar comes from here: rendered conditions, trigger, stop/targets,
size via the risk engine, cost estimate, every gate with its reason, the verdict and the one-sentence
rule trace in the spec's voice. The sentence is checked against the section 0 guardrail before it is
returned; a failing sentence (which would be a bug) is replaced by a neutral fallback.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from engine import indicators as ind
from engine.backtest import TF_MINUTES, auto_segment
from engine.costs import CostParams, per_unit_cost_estimate
from engine.mentor.guardrail import guardrail
from engine.risk.engine import RiskStatus, gate_new_exposure, position_size
from engine.rules.engine import (
    as_strategy,
    conditions_trace,
    describe_trigger,
    render_condition,
    stop_price,
    target_prices,
)
from engine.rules.operands import Computed, render_operand, resolve_operand
from engine.schema.strategy import Condition, Strategy

GATE_ENTRY = "All entry conditions"
GATE_REGIME = "Regime matches affinity"
GATE_SESSION = "Session window"


def _hhmm(s: str) -> int:
    h, mm = s.split(":")
    return int(h) * 60 + int(mm)


def _as_status(rs: RiskStatus | dict) -> RiskStatus:
    if isinstance(rs, RiskStatus):
        return rs
    fields = {k: v for k, v in rs.items() if k in RiskStatus.__dataclass_fields__}
    return RiskStatus(**fields)


def _value_at(operand: Any, bars: pd.DataFrame, inputs: Computed, i: int) -> float | None:
    try:
        v = resolve_operand(operand, bars, inputs)
    except Exception:
        return None
    if isinstance(v, float):
        return v
    x = v.iloc[i]
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def describe_failure(cond: Condition, bars: pd.DataFrame, inputs: Computed, i: int) -> str:
    """One plain sentence with the figures behind a failed condition on bar i."""
    op = str(cond.op)
    lhs_name = render_operand(cond.lhs)
    lv = _value_at(cond.lhs, bars, inputs, i)
    if op in ("rising", "falling"):
        return f"{lhs_name} is not {op} over the required bars."
    rhs_name = render_operand(cond.rhs)
    rv = _value_at(cond.rhs, bars, inputs, i)
    if op in ("crosses_above", "crosses_below"):
        return f"{lhs_name} did not cross {'above' if op == 'crosses_above' else 'below'} {rhs_name} on this bar."
    lv_s = "unavailable" if lv is None else f"{lv:.2f}"
    rv_s = rhs_name if rv is None else (f"{rv:.2f}" if not rhs_name.replace(".", "").isdigit() else f"{rv:g}")
    return f"{lhs_name} is {lv_s}, rule needs {op} {rv_s}."


def session_window_gate(spec: Strategy, bar_ts: pd.Timestamp) -> dict:
    """Mirror of the backtester's entry_ok: the signal bar must sit inside the session and the next bar
    (the fill bar) must leave room for a full bar before the session end / time exit."""
    tf = TF_MINUTES[str(spec.timeframe)]
    if str(spec.timeframe) == "1D":
        return {"name": GATE_SESSION, "pass": True}
    mod = bar_ts.hour * 60 + bar_ts.minute
    start_min, end_min = _hhmm(spec.session.start), _hhmm(spec.session.end)
    nxt = mod + tf
    ok = mod >= start_min and nxt >= start_min and nxt + 2 * tf <= end_min
    if spec.time_exit.at_time and nxt + tf > _hhmm(spec.time_exit.at_time):
        ok = False
    if ok:
        return {"name": GATE_SESSION, "pass": True}
    return {
        "name": GATE_SESSION,
        "pass": False,
        "reason": f"Bar at {bar_ts.strftime('%H:%M')} leaves no room for a fill inside your {spec.session.start}-{spec.session.end} window.",
    }


def build_signal(
    spec: Strategy | dict,
    bars: pd.DataFrame,
    i: int,
    regime_row: pd.Series,
    risk_status: RiskStatus | dict,
    behaviour_state: str,
    trades_today: int,
    one_r: float,
    cost_params: CostParams = CostParams(),
    lot: int = 1,
    *,
    inputs: Computed | None = None,
    exec_state: str = "WATCHING",
    signal_id: str = "",
    timestamp: Any = None,
    symbol: str | None = None,
) -> dict:
    spec = as_strategy(spec)
    inputs = inputs if inputs is not None else ind.compute_inputs(bars, spec.inputs)
    rs = _as_status(risk_status)
    row = regime_row
    bar_ts = pd.Timestamp(bars["ts"].iloc[i])
    regime = str(row.get("regime", "range"))
    long_setup, short_setup = bool(row.get("long_setup", False)), bool(row.get("short_setup", False))
    regime_ok = bool(row.get("regime_ok", True))
    symbol = symbol or (spec.instruments[0].root if spec.instruments else "?")

    # Side: the one with a full setup, else the one with the most passed conditions (long on ties).
    long_p, long_f = conditions_trace(spec, row, "long")
    short_p, short_f = conditions_trace(spec, row, "short") if spec.entry_short else ([], [])
    if long_setup or (not short_setup and (len(long_p) >= len(short_p) or not spec.entry_short)):
        side: str | None = "long" if spec.entry_long else None
        passed, failed = long_p, long_f
        conds = spec.entry_long
    else:
        side, passed, failed, conds = "short", short_p, short_f, spec.entry_short or []
    setup = (long_setup and side == "long") or (short_setup and side == "short")
    if side is None:
        setup = False

    close = float(bars["close"].iloc[i])
    stop = stop_price(spec, bars, i, side, inputs) if side else None
    per_unit = abs(close - stop) if stop is not None else 0.0
    one_r_eff = min(one_r, rs.trading_bucket * spec.risk.max_equity_risk_pct / 100.0) if rs.trading_bucket > 0 else one_r
    qty = position_size(one_r_eff, per_unit, lot) if stop is not None else 0
    targets = target_prices(spec, close, stop, side, inputs, i, bars) if (stop is not None and side) else []
    rupee_risk = round(qty * per_unit, 2)
    portfolio_risk_pct = round(rupee_risk / rs.trading_bucket * 100.0, 2) if rs.trading_bucket > 0 else 0.0
    segment = auto_segment(spec)
    est = round(per_unit_cost_estimate(close, qty, segment, cost_params) * qty, 2) if qty > 0 else 0.0
    post_cost_rr: float | None = None
    if targets and qty > 0 and per_unit > 0:
        post_cost_rr = round((abs(targets[0] - close) * qty - est) / (per_unit * qty), 2)
    planned_risk_r = round(rupee_risk / one_r, 4) if one_r > 0 and qty > 0 else 1.0

    # Trigger
    ttype, off = str(spec.trigger.type), (spec.trigger.offset_pct or 0.0) / 100
    if ttype == "break_of_signal_bar":
        price = float(bars["high"].iloc[i]) * (1 + off) if side == "long" else float(bars["low"].iloc[i]) * (1 - off)
    elif ttype == "limit":
        price = close * (1 - off) if side == "long" else close * (1 + off)
    else:
        price = close
    trigger = {
        "type": ttype,
        "price": round(price, 2) if side else None,
        "description": describe_trigger(spec)[0].upper()
        + describe_trigger(spec)[1:]
        + f", inside a {cost_params.slippage_bps:g} bps slippage band.",
    }

    # Gates, in display order.
    gates: list[dict] = []
    if setup:
        gates.append({"name": GATE_ENTRY, "pass": True})
    else:
        first = next((c for c in conds if render_condition(c) in failed), None)
        reason = describe_failure(first, bars, inputs, i) if first is not None else "No entry rule is defined for this side."
        gates.append({"name": GATE_ENTRY, "pass": False, "reason": reason})
    if regime_ok:
        gates.append({"name": GATE_REGIME, "pass": True})
    else:
        aff = ", ".join(str(r).replace("_", " ") for r in spec.regime_affinity)
        gates.append({"name": GATE_REGIME, "pass": False, "reason": f"Regime is {regime.replace('_', ' ')}; your rules want {aff}."})
    min_rr = spec.risk.min_rr_after_costs
    rr_name = f"Post-cost R:R >= {min_rr:g}"
    if side and stop is None:
        gates.append({"name": rr_name, "pass": False, "reason": "The stop rule gives no valid level on this bar, so risk cannot be measured."})
    elif side and qty <= 0 and stop is not None:
        gates.append({"name": rr_name, "pass": False, "reason": f"Rupee risk per unit {per_unit:.2f} sizes below one lot of {lot} at 1R = {one_r_eff:.0f}."})
    elif post_cost_rr is not None and post_cost_rr < min_rr:
        gates.append({"name": rr_name, "pass": False, "reason": f"Post-cost R:R is {post_cost_rr:.2f}, your rule needs at least {min_rr:g}."})
    else:
        gates.append({"name": rr_name, "pass": True})
    gates.append(session_window_gate(spec, bar_ts))
    gates.extend(gate_new_exposure(rs, planned_risk_r, behaviour_state, trades_today, spec.risk.max_trades_per_day))

    red = [g for g in gates if not g["pass"]]
    if not setup:
        verdict = "watch"
    elif red:
        verdict = "blocked"
    else:
        verdict = "eligible"

    regime_words = regime.replace("_", " ")
    if verdict == "eligible":
        rr_text = f"post-cost R:R {post_cost_rr:.2f}" if post_cost_rr is not None else "post-cost R:R not measured (no fixed target)"
        sentence = (
            f"Strategy {spec.strategy_id} matched a {regime_words} regime. {'; '.join(passed)}. "
            f"Risk {portfolio_risk_pct:.2f}% of equity, {rr_text}, all data gates pass. "
            "Eligible if the next executable price stays inside your slippage band."
        )
    elif verdict == "blocked":
        sentence = (
            f"Setup matches, but this trade is blocked: {red[0].get('reason', red[0]['name'] + ' failed.')} "
            "We can log it in paper mode and journal what would have happened."
        )
    else:
        if passed:
            sentence = f"{'; '.join(passed)}, but {'; '.join(failed) or 'no setup'}, so this bar is not a full setup. Watching for the next closed bar."
        else:
            sentence = f"No entry condition is met on this bar ({'; '.join(failed) or 'no entry rule'}), so this bar is not a full setup. Watching for the next closed bar."
    if not guardrail(sentence, {x.root for x in spec.instruments}).ok:
        sentence = f"Strategy {spec.strategy_id} evaluated the last closed bar: verdict {verdict}. Watching for the next closed bar."

    return {
        "id": signal_id,
        "strategy_id": spec.strategy_id,
        "version": int(spec.version),
        "timestamp": pd.Timestamp(timestamp if timestamp is not None else bar_ts).isoformat(),
        "symbol": symbol,
        "regime": regime,
        "side": side,
        "conditions_passed": passed,
        "conditions_failed": failed,
        "trigger": trigger,
        "stop": round(stop, 2) if stop is not None else None,
        "targets": [round(t, 2) for t in targets],
        "quantity": int(qty),
        "rupee_risk": rupee_risk,
        "portfolio_risk_pct": portfolio_risk_pct,
        "estimated_costs": est,
        "post_cost_rr": post_cost_rr,
        "automation_permission": str(spec.automation_permission),
        "ambiguity_flags": list(spec.ambiguity_flags),
        "gates": gates,
        "exec_state": exec_state,
        "verdict": verdict,
        "sentence": sentence,
    }


__all__ = ["GATE_ENTRY", "GATE_REGIME", "GATE_SESSION", "build_signal", "describe_failure", "session_window_gate"]
