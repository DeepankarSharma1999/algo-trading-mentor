"""The 8-stage validation pipeline (ARCHITECTURE.md section 4 for the detail payload shapes).

Stages 1-5 and 7 are hard gates: the first failure stops the run and later stages stay `pending`.
Stage 6 is informational, stage 8 is skipped until enough paper trades exist. The weakest stage is
the failed one, or else the run stage with the smallest normalised margin.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from engine import indicators as ind
from engine.backtest import BacktestResult, Stats, run_backtest_multi
from engine.costs import CostParams
from engine.regime import classify
from engine.rules.engine import as_strategy
from engine.rules.operands import Computed
from engine.schema.strategy import Strategy
from engine.validation.gates import AcceptanceGates

STAGE_NAMES: dict[int, str] = {
    1: "In-sample coherence",
    2: "Out-of-sample",
    3: "Walk-forward",
    4: "Cost stress",
    5: "Parameter sensitivity",
    6: "Regime breakdown",
    7: "Monte Carlo",
    8: "Paper agreement",
}
HARD_STAGES: frozenset[int] = frozenset({1, 2, 3, 4, 5, 7})
Status = Literal["pass", "fail", "skip", "pending"]


class StageResult(BaseModel):
    stage: int
    name: str
    status: Status = "pending"
    summary: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)
    detail: Any = None


class ValidationReport(BaseModel):
    strategy_id: str
    started_at: str
    finished_at: str | None = None
    stages: list[StageResult]
    weakest_stage: int | None = None
    weakest_sentence: str = ""
    passed: bool = False


@dataclass
class _Ctx:
    spec: Strategy
    spec_dict: dict
    bars: dict[str, pd.DataFrame]
    gates: AcceptanceGates
    one_r: float
    max_dd_pct: float
    cost_params: CostParams
    run_kw: dict[str, Any]
    inputs: dict[str, Computed] = field(default_factory=dict)
    regimes: dict[str, pd.Series] = field(default_factory=dict)
    base: BacktestResult | None = None
    t0: pd.Timestamp = field(default_factory=lambda: pd.Timestamp(0))
    t1: pd.Timestamp = field(default_factory=lambda: pd.Timestamp(0))

    def run(
        self,
        spec: Strategy | dict | None = None,
        start: Any = None,
        end: Any = None,
        cost_multiplier: float = 1.0,
    ) -> BacktestResult:
        base_spec = spec is None
        return run_backtest_multi(
            self.spec if base_spec else spec,
            self.bars,
            inputs_by_symbol=self.inputs if base_spec else None,
            regime_by_symbol=self.regimes,
            cost_params=self.cost_params,
            cost_multiplier=cost_multiplier,
            one_r_rupees=self.one_r,
            start=start,
            end=end,
            **self.run_kw,
        )


def _fmt_ts(t: pd.Timestamp) -> str:
    return pd.Timestamp(t).isoformat()


def _stats(s: Stats) -> dict[str, Any]:
    return s.model_dump()


def _verdict(fail: bool) -> str:
    return "so this version is not validated" if fail else "so it is validated but keep an eye there"


# --- stages ---------------------------------------------------------------------------------------


def _stage1(ctx: _Ctx) -> StageResult:
    res = ctx.base = ctx.run()
    tf = str(ctx.spec.timeframe)
    min_trades = ctx.gates.min_trades(tf)
    problems: list[str] = []
    nan_after, warmup = 0, 0
    for sym, computed in ctx.inputs.items():
        for name, obj in computed.items():
            if name.startswith("__"):
                continue
            frame = obj.to_frame() if isinstance(obj, pd.Series) else obj
            for col in frame.columns:
                s = frame[col]
                fv = s.first_valid_index()
                if fv is None:
                    problems.append(f"input {name}.{col} on {sym} never has a value")
                    continue
                start_pos = int(s.index.get_loc(fv))
                warmup = max(warmup, start_pos)
                nan_after += int(s.iloc[start_pos:].isna().sum())
    if nan_after:
        problems.append(f"{nan_after} NaN values in inputs after warm-up")
    stop_err = sum(
        1 for t in res.trades if (t.side == "long" and t.stop >= t.entry) or (t.side == "short" and t.stop <= t.entry)
    )
    tgt_err = sum(
        1
        for t in res.trades
        if t.target is not None and ((t.side == "long" and t.target <= t.entry) or (t.side == "short" and t.target >= t.entry))
    )
    if stop_err:
        problems.append(f"{stop_err} trades have the stop on the wrong side")
    if tgt_err:
        problems.append(f"{tgt_err} trades have a target on the wrong side")
    if res.stats.trades < min_trades:
        problems.append(f"{res.stats.trades} trades, the {tf} minimum is {min_trades}")
    fail = bool(problems)
    margin = res.stats.trades / min_trades - 1 if min_trades else 1.0
    if nan_after or stop_err or tgt_err:
        margin = min(margin, -1.0)
    summary = (
        "; ".join(problems)
        if problems
        else f"{res.stats.trades} trades (min {min_trades}), inputs clean after {warmup} warm-up bars, "
        f"stops and targets on the right side, expectancy {res.stats.expectancy_r:+.2f}R"
    )
    return StageResult(
        stage=1,
        name=STAGE_NAMES[1],
        status="fail" if fail else "pass",
        summary=summary,
        metrics={
            "trades": res.stats.trades,
            "min_trades": min_trades,
            "expectancy_r": res.stats.expectancy_r,
            "nan_after_warmup": nan_after,
            "warmup_bars": warmup,
            "stop_side_errors": stop_err,
            "target_side_errors": tgt_err,
            "margin": margin,
        },
        detail={"stats": _stats(res.stats), "warmup_bars": warmup, "problems": problems},
    )


def _stage2(ctx: _Ctx) -> StageResult:
    g = ctx.gates
    split = ctx.t0 + (ctx.t1 - ctx.t0) * (1 - g.oos_fraction)
    ins, oos = ctx.run(end=split), ctx.run(start=split)
    e = oos.stats.expectancy_r
    fail = oos.stats.trades == 0 or e <= g.min_expectancy_r
    pct = int(round(g.oos_fraction * 100))
    summary = (
        f"OOS (last {pct}%, from {split.date()}): {oos.stats.trades} trades, expectancy {e:+.2f}R after costs "
        f"vs in-sample {ins.stats.expectancy_r:+.2f}R"
    )
    if oos.stats.trades == 0:
        summary = f"no trades in the last {pct}% of data (from {split.date()})"
    return StageResult(
        stage=2,
        name=STAGE_NAMES[2],
        status="fail" if fail else "pass",
        summary=summary,
        metrics={
            "in_sample_expectancy_r": ins.stats.expectancy_r,
            "oos_expectancy_r": e,
            "oos_trades": oos.stats.trades,
            "oos_fraction": g.oos_fraction,
            "margin": e - g.min_expectancy_r if oos.stats.trades else -1.0,
        },
        detail={"in_sample": _stats(ins.stats), "oos": _stats(oos.stats), "equity": oos.equity},
    )


def _wf_windows(ctx: _Ctx) -> tuple[list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]], bool]:
    g = ctx.gates
    train, test = pd.DateOffset(months=g.wf_train_months), pd.DateOffset(months=g.wf_test_months)
    windows = []
    s = ctx.t0
    while s + train + test <= ctx.t1 + pd.Timedelta(days=1):
        windows.append((s, s + train, s + train + test))
        s = s + test
    if len(windows) >= g.wf_min_windows:
        return windows, False
    k = g.wf_min_windows
    ratio = g.wf_train_months / g.wf_test_months
    test_len = (ctx.t1 - ctx.t0) / (ratio + k)
    train_len = test_len * ratio
    windows = []
    for j in range(k):
        a = ctx.t0 + test_len * j
        windows.append((a, a + train_len, a + train_len + test_len))
    windows[-1] = (windows[-1][0], windows[-1][1], ctx.t1 + pd.Timedelta(seconds=1))
    return windows, True


def _stage3(ctx: _Ctx) -> StageResult:
    g = ctx.gates
    windows, proportional = _wf_windows(ctx)
    rows, pooled_r = [], []
    for a, b, c in windows:
        tr, te = ctx.run(start=a, end=b), ctx.run(start=b, end=c)
        pooled_r.extend(t.r_multiple for t in te.trades)
        rows.append(
            {
                "train": {"start": _fmt_ts(a), "end": _fmt_ts(b), "trades": tr.stats.trades, "expectancy_r": tr.stats.expectancy_r},
                "test": {"start": _fmt_ts(b), "end": _fmt_ts(c), "trades": te.stats.trades, "expectancy_r": te.stats.expectancy_r},
                "stats": _stats(te.stats),
            }
        )
    pooled = float(np.mean(pooled_r)) if pooled_r else float("nan")
    fail = len(windows) < g.wf_min_windows or not pooled_r or pooled <= g.min_expectancy_r
    how = (
        f"proportional windows (data shorter than {g.wf_min_windows} x {g.wf_train_months}+{g.wf_test_months} months)"
        if proportional
        else f"rolling {g.wf_train_months}-month train / {g.wf_test_months}-month test"
    )
    summary = f"{len(windows)} {how}: pooled test expectancy {pooled:+.2f}R over {len(pooled_r)} trades"
    if not pooled_r:
        summary = f"{len(windows)} {how}: no test trades"
    return StageResult(
        stage=3,
        name=STAGE_NAMES[3],
        status="fail" if fail else "pass",
        summary=summary,
        metrics={
            "windows": len(windows),
            "pooled_test_expectancy_r": pooled if pooled_r else 0.0,
            "pooled_test_trades": len(pooled_r),
            "proportional": float(proportional),
            "margin": (pooled - g.min_expectancy_r) if pooled_r else -1.0,
        },
        detail={"windows": rows},
    )


def _stage4(ctx: _Ctx) -> StageResult:
    g = ctx.gates
    assert ctx.base is not None
    mults = {"1.0": ctx.base}
    for m in g.cost_multipliers:
        mults[f"{m:.1f}"] = ctx.run(cost_multiplier=m)
    hard_key = f"{g.cost_multipliers[0]:.1f}"
    e_hard = mults[hard_key].stats.expectancy_r
    fail = e_hard <= g.min_expectancy_r
    metrics = {f"expectancy_x{k.replace('.', '_')}": r.stats.expectancy_r for k, r in mults.items()}
    watch = [k for k in mults if k not in ("1.0", hard_key) and mults[k].stats.expectancy_r <= g.min_expectancy_r]
    metrics["watch"] = float(len(watch))
    metrics["margin"] = e_hard - g.min_expectancy_r
    parts = [f"x{k}: {r.stats.expectancy_r:+.2f}R" for k, r in mults.items()]
    summary = "expectancy at cost multipliers " + ", ".join(parts)
    if watch:
        summary += f"; watch: negative at x{', x'.join(watch)}"
    return StageResult(
        stage=4,
        name=STAGE_NAMES[4],
        status="fail" if fail else "pass",
        summary=summary,
        metrics=metrics,
        detail={"multipliers": {k: _stats(r.stats) for k, r in mults.items()}},
    )


def numeric_params(spec: dict) -> list[tuple[str, float]]:
    """Every tunable number: inputs.<name>.<param>, stop.<param>, targets[i].value, trailing.<param>."""
    out: list[tuple[str, float]] = []

    def is_num(v: Any) -> bool:
        return isinstance(v, int | float) and not isinstance(v, bool)

    for name, inp in spec.get("inputs", {}).items():
        for k, v in inp.get("params", {}).items():
            if is_num(v):
                out.append((f"inputs.{name}.{k}", v))
    for k, v in (spec.get("stop") or {}).get("params", {}).items():
        if is_num(v):
            out.append((f"stop.{k}", v))
    for i, t in enumerate(spec.get("targets", [])):
        if is_num(t.get("value")):
            out.append((f"targets[{i}].value", t["value"]))
    for k, v in spec.get("trailing", {}).get("params", {}).items():
        if is_num(v):
            out.append((f"trailing.{k}", v))
    return out


def perturbed_spec(spec: dict, path: str, base: float, delta: float) -> dict:
    """Copy of spec with `path` set to base * (1 + delta); ints stay ints (rounded, >= 1)."""
    v = base * (1 + delta)
    v = max(1, int(round(v))) if isinstance(base, int) else float(v)
    new = copy.deepcopy(spec)
    head, _, key = path.rpartition(".")
    if head.startswith("inputs."):
        new["inputs"][head.split(".", 1)[1]]["params"][key] = v
    elif head == "stop":
        new["stop"]["params"][key] = v
    elif head == "trailing":
        new["trailing"]["params"][key] = v
    elif head.startswith("targets["):
        new["targets"][int(head[8:-1])]["value"] = v
    else:
        raise ValueError(f"unknown param path {path!r}")
    return new


def _stage5(ctx: _Ctx) -> StageResult:
    g = ctx.gates
    assert ctx.base is not None
    base_e = ctx.base.stats.expectancy_r
    floor = max(abs(base_e), g.sensitivity_base_floor_r)
    params, neighbours = [], []
    for path, base in numeric_params(ctx.spec_dict):
        grid = []
        for d in g.sensitivity_deltas:
            try:
                e = ctx.run(perturbed_spec(ctx.spec_dict, path, base, d)).stats.expectancy_r
            except Exception:
                e = float("nan")
            grid.append({"delta": d, "expectancy": e})
            neighbours.append(e)
        params.append({"name": path, "base": base, "grid": grid})
    vals = np.array([v for v in neighbours if not math.isnan(v)]) if neighbours else np.array([])
    share = float((vals > g.min_expectancy_r).mean()) if len(vals) else 1.0
    max_dev = float(np.abs(vals - base_e).max()) if len(vals) else 0.0
    limit = g.sensitivity_max_deviation_mult * floor
    fail = share < g.sensitivity_plateau_share or max_dev > limit
    summary = (
        f"{len(params)} params x {len(g.sensitivity_deltas)} deltas: {share:.0%} of neighbours keep expectancy > 0 "
        f"(need {g.sensitivity_plateau_share:.0%}), max deviation {max_dev:.2f}R (limit {limit:.2f}R), base {base_e:+.2f}R"
    )
    return StageResult(
        stage=5,
        name=STAGE_NAMES[5],
        status="fail" if fail else "pass",
        summary=summary,
        metrics={
            "params": len(params),
            "neighbours": len(vals),
            "plateau_share": share,
            "max_deviation_r": max_dev,
            "deviation_limit_r": limit,
            "base_expectancy_r": base_e,
            "margin": min(share - g.sensitivity_plateau_share, 1 - max_dev / limit if limit else 1.0),
        },
        detail={"params": params},
    )


def _stage6(ctx: _Ctx) -> StageResult:
    assert ctx.base is not None
    regimes = ctx.base.by_regime
    metrics: dict[str, float] = {}
    for k, s in regimes.items():
        metrics[f"expectancy_{k}"] = s.expectancy_r
        metrics[f"trades_{k}"] = s.trades
    weakest = min(regimes.items(), key=lambda kv: kv[1].expectancy_r) if regimes else None
    metrics["min_regime_expectancy_r"] = weakest[1].expectancy_r if weakest else 0.0
    metrics["margin"] = weakest[1].expectancy_r if weakest else 0.0
    parts = [f"{k}: {s.expectancy_r:+.2f}R over {s.trades}" for k, s in regimes.items()]
    return StageResult(
        stage=6,
        name=STAGE_NAMES[6],
        status="pass",
        summary="expectancy by regime: " + (", ".join(parts) if parts else "no trades"),
        metrics=metrics,
        detail={"regimes": {k: _stats(s) for k, s in regimes.items()}, "weakest": weakest[0] if weakest else None},
    )


def _stage7(ctx: _Ctx) -> StageResult:
    g = ctx.gates
    assert ctx.base is not None
    start_eq = ctx.base.start_equity or 100 * ctx.one_r
    pnl = np.array([t.net_pnl for t in ctx.base.trades])
    rng = np.random.default_rng(g.mc_seed)
    dds = np.zeros(g.mc_resamples)
    for k in range(g.mc_resamples):
        eq = start_eq + np.cumsum(rng.permutation(pnl)) if len(pnl) else np.array([start_eq])
        peak = np.maximum.accumulate(np.concatenate([[start_eq], eq]))
        dds[k] = ((peak[1:] - eq) / start_eq * 100).max()
    p5, p50, p95 = (float(x) for x in np.percentile(dds, [5, 50, 95]))
    counts, edges = np.histogram(dds, bins=g.mc_histogram_bins)
    hist = [[float(edges[i]), int(counts[i])] for i in range(len(counts))]
    fail = p95 > ctx.max_dd_pct
    summary = (
        f"{g.mc_resamples} shuffles of {len(pnl)} trades: max drawdown p5 {p5:.1f}%, p50 {p50:.1f}%, "
        f"p95 {p95:.1f}% of starting equity (limit {ctx.max_dd_pct:.0f}%, gated on the worst 5% = p95)"
    )
    return StageResult(
        stage=7,
        name=STAGE_NAMES[7],
        status="fail" if fail else "pass",
        summary=summary,
        metrics={
            "dd_p5": p5,
            "dd_p50": p50,
            "dd_p95": p95,
            "max_dd_pct": ctx.max_dd_pct,
            "margin": (ctx.max_dd_pct - p95) / ctx.max_dd_pct if ctx.max_dd_pct else 0.0,
        },
        detail={"dd_p5": p5, "dd_p50": p50, "dd_p95": p95, "histogram": hist},
    )


def _agree(a: float, b: float, rel: float, abs_: float) -> bool:
    return abs(a - b) <= abs_ or abs(a - b) <= rel * max(abs(a), abs(b))


def _stage8(ctx: _Ctx, paper_stats: dict[str, Any] | None) -> StageResult:
    g = ctx.gates
    assert ctx.base is not None
    bt = ctx.base.stats
    n = int((paper_stats or {}).get("trades", 0) or 0)
    if not paper_stats or n < g.paper_min_trades:
        return StageResult(
            stage=8,
            name=STAGE_NAMES[8],
            status="skip",
            summary=f"{n} paper trades; needs {g.paper_min_trades} closed paper trades to compare",
            metrics={"paper_trades": n, "min_paper_trades": g.paper_min_trades, "backtest_expectancy_r": bt.expectancy_r},
            detail={"paper": None, "backtest": _stats(bt), "agreement": None},
        )
    pe, pw = float(paper_stats.get("expectancy_r", 0.0)), float(paper_stats.get("win_rate", 0.0))
    e_ok = _agree(pe, bt.expectancy_r, g.paper_rel_tolerance, g.paper_abs_tolerance)
    w_ok = _agree(pw, bt.win_rate, g.paper_rel_tolerance, g.paper_abs_tolerance)
    agreement = e_ok and w_ok
    summary = (
        f"paper {n} trades: expectancy {pe:+.2f}R vs backtest {bt.expectancy_r:+.2f}R, "
        f"win rate {pw:.0%} vs {bt.win_rate:.0%}: {'agree' if agreement else 'disagree'}"
    )
    gap = abs(pe - bt.expectancy_r)
    tol = max(g.paper_abs_tolerance, g.paper_rel_tolerance * max(abs(pe), abs(bt.expectancy_r)))
    return StageResult(
        stage=8,
        name=STAGE_NAMES[8],
        status="pass" if agreement else "fail",
        summary=summary,
        metrics={
            "paper_trades": n,
            "paper_expectancy_r": pe,
            "backtest_expectancy_r": bt.expectancy_r,
            "paper_win_rate": pw,
            "backtest_win_rate": bt.win_rate,
            "agreement": float(agreement),
            "margin": (tol - gap) / tol if tol else 0.0,
        },
        detail={"paper": dict(paper_stats), "backtest": _stats(bt), "agreement": agreement},
    )


# --- the weakest sentence -------------------------------------------------------------------------


def weakest_sentence(stage: StageResult) -> str:
    """One plain sentence naming the stage and the number that makes it the weakest."""
    m, fail = stage.metrics, stage.status == "fail"
    v = _verdict(fail)
    if stage.stage == 1:
        extra = f", with {stage.summary}" if fail and m.get("trades", 0) >= m.get("min_trades", 0) else ""
        return (
            f"In-sample coherence is your weakest gate: {m.get('trades', 0):.0f} trades against a minimum of "
            f"{m.get('min_trades', 0):.0f}{extra}, {v}."
        )
    if stage.stage == 2:
        e = m.get("oos_expectancy_r", 0.0)
        pct = int(round(m.get("oos_fraction", 0.3) * 100))
        verb = "fell to" if e <= 0 else "held at only"
        return f"Out-of-sample is your weakest gate: expectancy {verb} {e:+.2f}R after costs on the last {pct}% of data, {v}."
    if stage.stage == 3:
        return (
            f"Walk-forward is your weakest gate: pooled test expectancy across {m.get('windows', 0):.0f} windows was "
            f"{m.get('pooled_test_expectancy_r', 0.0):+.2f}R over {m.get('pooled_test_trades', 0):.0f} trades, {v}."
        )
    if stage.stage == 4:
        e = m.get("expectancy_x1_5", 0.0)
        return f"Cost stress is your weakest gate: at 1.5x costs expectancy {'fell to' if e <= 0 else 'thinned to'} {e:+.2f}R, {v}."
    if stage.stage == 5:
        return (
            f"Parameter sensitivity is your weakest gate: {m.get('plateau_share', 0.0):.0%} of the +/-10% and +/-20% "
            f"neighbours keep a positive expectancy and the widest swing is {m.get('max_deviation_r', 0.0):.2f}R from "
            f"the base {m.get('base_expectancy_r', 0.0):+.2f}R, {v}."
        )
    if stage.stage == 6:
        weakest = (stage.detail or {}).get("weakest") if isinstance(stage.detail, dict) else None
        e = m.get("min_regime_expectancy_r", 0.0)
        return (
            f"Regime breakdown is your weakest area: expectancy is {e:+.2f}R in {weakest or 'no'} bars, "
            "so this version earns unevenly across regimes."
        )
    if stage.stage == 7:
        return (
            f"Monte Carlo is your weakest gate: the worst 5% of shuffled trade orders reach a {m.get('dd_p95', 0.0):.1f}% "
            f"drawdown against your {m.get('max_dd_pct', 0.0):.0f}% limit, {v}."
        )
    return (
        f"Paper agreement is your weakest gate: paper expectancy {m.get('paper_expectancy_r', 0.0):+.2f}R against "
        f"backtest {m.get('backtest_expectancy_r', 0.0):+.2f}R, {v}."
    )


def pick_weakest(stages: list[StageResult]) -> StageResult | None:
    failed = [s for s in stages if s.status == "fail"]
    if failed:
        return failed[0]
    scored = [s for s in stages if s.status == "pass" and "margin" in s.metrics]
    return min(scored, key=lambda s: s.metrics["margin"]) if scored else None


# --- driver ---------------------------------------------------------------------------------------


def run_pipeline(
    spec: Strategy | dict,
    bars_by_symbol: dict[str, pd.DataFrame],
    *,
    one_r: float,
    max_dd_pct: float = 20.0,
    cost_params: CostParams = CostParams(),
    paper_stats: dict[str, Any] | None = None,
    on_stage: Callable[[StageResult], None] | None = None,
    gates: AcceptanceGates | None = None,
    lot_size: int = 1,
    segment: str | None = None,
) -> ValidationReport:
    strategy = as_strategy(spec)
    spec_dict = strategy.model_dump(mode="json")
    started = datetime.now(UTC)
    stages = [StageResult(stage=i, name=STAGE_NAMES[i]) for i in range(1, 9)]
    report = ValidationReport(strategy_id=strategy.strategy_id, started_at=started.isoformat(), stages=stages)
    bars = {k: v.reset_index(drop=True) for k, v in bars_by_symbol.items() if len(v)}
    if not bars:
        stages[0].status, stages[0].summary = "fail", "no bars supplied"
        stages[0].metrics = {"trades": 0, "min_trades": 1, "margin": -1.0}
        report.weakest_stage, report.weakest_sentence = 1, weakest_sentence(stages[0])
        report.finished_at = datetime.now(UTC).isoformat()
        if on_stage:
            on_stage(stages[0])
        return report
    ctx = _Ctx(
        spec=strategy,
        spec_dict=spec_dict,
        bars=bars,
        gates=gates or AcceptanceGates(),
        one_r=one_r,
        max_dd_pct=max_dd_pct,
        cost_params=cost_params,
        run_kw={"lot_size": lot_size, "segment": segment},
    )
    for sym, b in bars.items():
        ctx.inputs[sym] = ind.compute_inputs(b, strategy.inputs)
        ctx.regimes[sym] = classify(b)
    ctx.t0 = min(b["ts"].iloc[0] for b in bars.values())
    ctx.t1 = max(b["ts"].iloc[-1] for b in bars.values())

    runners: dict[int, Callable[[], StageResult]] = {
        1: lambda: _stage1(ctx),
        2: lambda: _stage2(ctx),
        3: lambda: _stage3(ctx),
        4: lambda: _stage4(ctx),
        5: lambda: _stage5(ctx),
        6: lambda: _stage6(ctx),
        7: lambda: _stage7(ctx),
        8: lambda: _stage8(ctx, paper_stats),
    }
    for i in range(1, 9):
        result = runners[i]()
        stages[i - 1] = result
        if on_stage:
            on_stage(result)
        if result.status == "fail" and i in HARD_STAGES:
            break
    report.stages = stages
    weakest = pick_weakest(stages)
    report.weakest_stage = weakest.stage if weakest else None
    report.weakest_sentence = weakest_sentence(weakest) if weakest else ""
    report.passed = all(s.status in ("pass", "skip") for s in stages)
    report.finished_at = datetime.now(UTC).isoformat()
    return report


__all__ = [
    "HARD_STAGES",
    "STAGE_NAMES",
    "StageResult",
    "ValidationReport",
    "numeric_params",
    "perturbed_spec",
    "pick_weakest",
    "run_pipeline",
    "weakest_sentence",
]
