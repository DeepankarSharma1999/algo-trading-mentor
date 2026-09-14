"""Turn a failed ValidationReport into findings anchored in the user's own rules (ARCHITECTURE section 4b).

Every finding is deterministic arithmetic on the backtest the pipeline already ran: which entry condition
is the bottleneck, how many setups sized to zero, gross vs net expectancy, and so on. Each carries the
levers (Builder sections and JSON pointers) that drive it. No instrument is ever named beyond the ones the
user chose, and the gate thresholds are never offered as levers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Section = Literal["identity", "timeframe", "inputs", "entry", "exits", "risk"]
Kind = Literal[
    "bottleneck_condition", "sized_to_zero", "rr_filter", "day_limit", "costs", "no_edge", "regime",
    "sensitivity", "drawdown", "other",
]


class Lever(BaseModel):
    label: str
    section: Section
    path: str | None = None


class Finding(BaseModel):
    stage: int
    kind: Kind
    title: str
    detail: str
    numbers: dict[str, float] = Field(default_factory=dict)
    levers: list[Lever] = Field(default_factory=list)


def _cond_path(spec: dict, rendered: str, side: str) -> str | None:
    """JSON pointer of the condition whose rendered text matches, e.g. /entry_long/2."""
    from engine.rules.engine import render_condition

    key = "entry_long" if side == "long" else "entry_short"
    for i, c in enumerate(spec.get(key) or []):
        if render_condition(c) == rendered:
            return f"/{key}/{i}"
    return None


def _stage(stages: list, n: int):
    return next((s for s in stages if s.stage == n), None)


def diagnose(spec: dict, stages: list, base: Any, one_r: float, lot_size: int, max_dd_pct: float) -> list[Finding]:
    """`base` is the stage-1 BacktestResult (or None). Returns [] when nothing failed."""
    out: list[Finding] = []
    s1, s2, s4, s5, s7 = (_stage(stages, n) for n in (1, 2, 4, 5, 7))
    tf = spec.get("timeframe", "")

    if s1 is not None and s1.status == "fail" and base is not None:
        st = base.stats
        min_trades = int(s1.metrics.get("min_trades", 0))
        setups = base.setup_bars or {}
        n_setups = int(setups.get("long", 0) + setups.get("short", 0))
        # Bottleneck condition: the entry condition that held least often.
        if base.condition_stats and st.trades < min_trades:
            name, cs = min(base.condition_stats.items(), key=lambda kv: kv[1].true_pct)
            out.append(Finding(
                stage=1, kind="bottleneck_condition", title="One entry condition is the bottleneck",
                detail=(f"'{name}' held on {cs.true_pct:.1f}% of bars ({cs.true_bars} of {setups.get('bars', 0)}). "
                        f"All conditions held together on {n_setups} bars, which became {st.trades} trades against a minimum of {min_trades} for {tf}."),
                numbers={"true_pct": cs.true_pct, "true_bars": cs.true_bars, "setups": n_setups, "trades": st.trades, "min_trades": min_trades},
                levers=[Lever(label=f"Condition {name}", section="entry", path=_cond_path(spec, name, cs.side)),
                        Lever(label="Timeframe (more bars, more setups)", section="timeframe", path="/timeframe")],
            ))
        if st.skipped_for_size:
            out.append(Finding(
                stage=1, kind="sized_to_zero", title="Setups sized to zero",
                detail=(f"{st.skipped_for_size} setups were skipped because one lot ({lot_size} unit{'s' if lot_size != 1 else ''}) "
                        f"risked more than your 1R of {one_r:,.0f} rupees from entry to stop. The stop is never widened to fit."),
                numbers={"skipped_for_size": st.skipped_for_size, "one_r": one_r, "lot_size": lot_size},
                levers=[Lever(label="Stop rule (a tighter stop type or multiple)", section="exits", path="/stop"),
                        Lever(label="Risk per trade (profile and trading bucket are in Settings)", section="risk", path="/risk/max_equity_risk_pct")],
            ))
        if st.skipped_for_rr:
            out.append(Finding(
                stage=1, kind="rr_filter", title="Setups failed your post-cost R:R minimum",
                detail=(f"{st.skipped_for_rr} setups had a post-cost reward-to-risk below your minimum of "
                        f"{spec.get('risk', {}).get('min_rr_after_costs', 0)}. Costs are fixed per trade, so a nearer target or a wider stop lowers the ratio."),
                numbers={"skipped_for_rr": st.skipped_for_rr, "min_rr": float(spec.get("risk", {}).get("min_rr_after_costs", 0) or 0)},
                levers=[Lever(label="Targets", section="exits", path="/targets"), Lever(label="Minimum R:R after costs", section="risk", path="/risk/min_rr_after_costs"),
                        Lever(label="Timeframe (larger moves per trade)", section="timeframe", path="/timeframe")],
            ))
        if st.skipped_day_limit:
            out.append(Finding(
                stage=1, kind="day_limit", title="Setups blocked by your daily trade limit",
                detail=f"{st.skipped_day_limit} setups arrived after {spec.get('risk', {}).get('max_trades_per_day', 0)} trades had already been taken that day.",
                numbers={"skipped_day_limit": st.skipped_day_limit},
                levers=[Lever(label="Max trades per day", section="risk", path="/risk/max_trades_per_day")],
            ))
        if st.cancelled_orders:
            out.append(Finding(
                stage=1, kind="other", title="Orders that never filled",
                detail=f"{st.cancelled_orders} break-of-bar or limit orders were not filled on the next bar and were cancelled.",
                numbers={"cancelled_orders": st.cancelled_orders},
                levers=[Lever(label="Trigger type", section="exits", path="/trigger")],
            ))
        for p in (s1.detail or {}).get("problems", []):
            if "wrong side" in p or "NaN" in p or "never has a value" in p:
                out.append(Finding(stage=1, kind="other", title="Rules are internally inconsistent", detail=p + ".",
                                   levers=[Lever(label="Stop and targets", section="exits", path="/stop"), Lever(label="Inputs", section="inputs", path="/inputs")]))

    # Costs and edge: read from whichever of stage 2 / stage 1 stats exist.
    stats_for_edge = None
    if s2 is not None and s2.status == "fail" and s2.detail:
        stats_for_edge = (s2.detail.get("oos") or {}), (s2.detail.get("in_sample") or {})
    if stats_for_edge:
        oos, ins = stats_for_edge
        g, n_, c = float(oos.get("gross_expectancy_r", 0.0)), float(oos.get("expectancy_r", 0.0)), float(oos.get("cost_per_trade_r", 0.0))
        if g > 0 >= n_:
            out.append(Finding(
                stage=2, kind="costs", title="Costs exceed the gross edge",
                detail=(f"Out of sample the rules made {g:+.2f}R per trade before brokerage, taxes and fees and {n_:+.2f}R after; "
                        f"costs take {c:.2f}R per trade. Fewer, larger trades keep more of the edge."),
                numbers={"gross_expectancy_r": g, "expectancy_r": n_, "cost_per_trade_r": c, "oos_trades": float(oos.get("trades", 0))},
                levers=[Lever(label="Timeframe (slower bars, larger moves)", section="timeframe", path="/timeframe"),
                        Lever(label="Targets (further target per unit of cost)", section="exits", path="/targets"),
                        Lever(label="Max trades per day", section="risk", path="/risk/max_trades_per_day")],
            ))
        else:
            out.append(Finding(
                stage=2, kind="no_edge", title="No edge out of sample, even before costs",
                detail=(f"On the last 30% of data the rules made {g:+.2f}R per trade before costs and {n_:+.2f}R after, "
                        f"against {float(ins.get('expectancy_r', 0.0)):+.2f}R in sample. Changing a threshold to make this window pass is fitting, not fixing; "
                        "the honest moves are to simplify the rules or to test a different hypothesis."),
                numbers={"gross_expectancy_r": g, "expectancy_r": n_, "in_sample_expectancy_r": float(ins.get("expectancy_r", 0.0)), "oos_trades": float(oos.get("trades", 0))},
                levers=[Lever(label="Entry conditions (remove one, do not add)", section="entry", path="/entry_long"),
                        Lever(label="Regime affinity (trade only where both windows were positive)", section="risk", path="/regime_affinity")],
            ))

    if s4 is not None and s4.status == "fail" and s4.detail:
        m = s4.detail.get("multipliers", {})
        e15 = float((m.get("1.5") or {}).get("expectancy_r", 0.0))
        e10 = float((m.get("1.0") or {}).get("expectancy_r", 0.0))
        out.append(Finding(
            stage=4, kind="costs", title="The edge does not survive higher costs",
            detail=f"Expectancy is {e10:+.2f}R at normal costs and {e15:+.2f}R at 1.5x. Real slippage is often worse than modelled, so this margin is too thin.",
            numbers={"expectancy_x1": e10, "expectancy_x15": e15},
            levers=[Lever(label="Timeframe", section="timeframe", path="/timeframe"), Lever(label="Targets", section="exits", path="/targets")],
        ))

    if s5 is not None and s5.status == "fail" and s5.detail:
        worst = None
        for prm in s5.detail.get("params", []):
            neg = [g for g in prm.get("grid", []) if float(g.get("expectancy", 0.0)) <= 0]
            if neg and (worst is None or len(neg) > worst[1]):
                worst = (prm, len(neg))
        if worst:
            prm, n_neg = worst
            out.append(Finding(
                stage=5, kind="sensitivity", title="The base value sits on a spike",
                detail=(f"Parameter {prm.get('name')} = {prm.get('base')} works, but {n_neg} of its {len(prm.get('grid', []))} neighbours "
                        "(±10% and ±20%) lose money. A robust rule is flat around its value."),
                numbers={"neighbours_negative": n_neg, "neighbours": len(prm.get("grid", []))},
                levers=[Lever(label=str(prm.get("name")), section=_section_for_path(str(prm.get("name", ""))), path=str(prm.get("name")))],
            ))

    if s7 is not None and s7.status == "fail":
        p95 = float(s7.metrics.get("dd_p95", 0.0))
        out.append(Finding(
            stage=7, kind="drawdown", title="Drawdown exceeds your profile",
            detail=f"In 5% of trade orderings the drawdown reaches {p95:.1f}% of equity; your profile allows {max_dd_pct:.0f}%. Risk per trade, not the entry rule, drives this.",
            numbers={"dd_p95": p95, "max_dd_pct": max_dd_pct},
            levers=[Lever(label="Max equity risk per trade", section="risk", path="/risk/max_equity_risk_pct"), Lever(label="Stop rule", section="exits", path="/stop")],
        ))
    return out


def _section_for_path(path: str) -> Section:
    seg = path.lstrip("/").split("/")[0]
    return {"inputs": "inputs", "entry_long": "entry", "entry_short": "entry", "timeframe": "timeframe", "session": "timeframe",
            "stop": "exits", "targets": "exits", "trailing": "exits", "time_exit": "exits", "trigger": "exits",
            "risk": "risk", "regime_affinity": "risk"}.get(seg, "entry")  # type: ignore[return-value]
