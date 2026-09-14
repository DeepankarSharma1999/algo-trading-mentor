"""Findings are deterministic arithmetic on the user's own backtest (ARCHITECTURE section 4b)."""

from engine.backtest import run_backtest
from engine.validation.pipeline import run_pipeline
from tests.conftest import ema_cross_spec, make_bars


def _spec_with_rare_condition():
    spec = ema_cross_spec()
    spec["inputs"]["vr"] = {"indicator": "volume_ratio", "params": {"window": 20}}
    spec["entry_long"] = spec["entry_long"] + [{"lhs": "vr", "op": ">", "rhs": 50}]  # almost never true
    spec["entry_short"] = None
    return spec


def test_backtest_reports_condition_hit_rates_and_gross_expectancy():
    bars = make_bars(375 * 30, seed=4, freq="5min")
    r = run_backtest(_spec_with_rare_condition(), bars, one_r_rupees=2000)
    assert "vr > 50" in r.condition_stats
    assert r.condition_stats["vr > 50"].true_pct < 1.0
    assert r.setup_bars["bars"] == len(bars) and r.setup_bars["long"] <= r.condition_stats["vr > 50"].true_bars
    base = run_backtest(ema_cross_spec(), bars, one_r_rupees=2000)
    assert base.stats.trades > 0
    assert base.stats.cost_per_trade_r > 0  # brokerage, taxes and fees always cost something
    assert abs(base.stats.gross_expectancy_r - base.stats.cost_per_trade_r - base.stats.expectancy_r) < 1e-9


def test_bottleneck_condition_finding_points_at_the_rare_rule():
    bars = {"RELIANCE": make_bars(375 * 60, seed=5, freq="5min")}
    report = run_pipeline(_spec_with_rare_condition(), bars, one_r=2000)
    assert not report.passed and report.weakest_stage == 1
    kinds = [f.kind for f in report.diagnosis]
    assert "bottleneck_condition" in kinds
    f = next(f for f in report.diagnosis if f.kind == "bottleneck_condition")
    assert "vr > 50" in f.detail and f.numbers["min_trades"] > f.numbers["trades"]
    assert f.levers[0].section == "entry" and f.levers[0].path == "/entry_long/1"
    # Stage 1 detail carries the raw numbers the web renders.
    d = report.stages[0].detail
    assert "vr > 50" in d["condition_stats"] and "skips" in d and d["setup_bars"]["bars"] > 0


def test_sized_to_zero_finding_when_one_lot_exceeds_one_r():
    b = make_bars(375 * 60, seed=6, freq="5min")
    for col in ("open", "high", "low", "close"):
        b[col] = b[col] * 24.0  # an index-sized price: one lot of 25 with an ATR stop costs far more than 1R = 500
    bars = {"NIFTY": b}
    report = run_pipeline(ema_cross_spec(), bars, one_r=500, lot_size=25)
    kinds = [f.kind for f in report.diagnosis]
    assert "sized_to_zero" in kinds
    f = next(f for f in report.diagnosis if f.kind == "sized_to_zero")
    assert f.numbers["lot_size"] == 25 and f.numbers["one_r"] == 500
    assert {lv.section for lv in f.levers} == {"exits", "risk"}


def test_passed_or_edge_findings_never_offer_gates_or_instruments():
    bars = {"RELIANCE": make_bars(375 * 120, seed=7, freq="5min")}
    report = run_pipeline(ema_cross_spec(), bars, one_r=2000)
    for f in report.diagnosis:
        for lv in f.levers:
            assert lv.section in {"identity", "timeframe", "inputs", "entry", "exits", "risk"}
            assert not (lv.path or "").startswith("/instruments")
    if report.passed:
        assert report.diagnosis == []
    else:
        assert report.diagnosis, "a failed report must explain itself"
