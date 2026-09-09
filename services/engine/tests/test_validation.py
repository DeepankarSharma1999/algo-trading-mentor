import pytest

from engine.validation import HARD_STAGES, STAGE_NAMES, AcceptanceGates, ValidationReport, run_pipeline
from engine.validation.pipeline import numeric_params, perturbed_spec, weakest_sentence
from tests.conftest import ema_cross_spec, make_bars

LOW_GATES = AcceptanceGates(min_trades_by_timeframe={"5m": 20})


@pytest.fixture(scope="module")
def trending_bars_module():
    return make_bars(3000, seed=3, vol=0.0008, wave_period=300, wave_amp=0.03)


@pytest.fixture(scope="module")
def run(trending_bars_module) -> dict:
    seen: list[int] = []
    rep = run_pipeline(
        ema_cross_spec(),
        {"NIFTY": trending_bars_module},
        one_r=10_000,
        max_dd_pct=20,
        gates=LOW_GATES,
        on_stage=lambda s: seen.append(s.stage),
    )
    return {"report": rep, "seen": seen}


@pytest.fixture(scope="module")
def report(run) -> ValidationReport:
    return run["report"]


def test_all_eight_stages_present_and_run(run, report):
    assert isinstance(report, ValidationReport)
    assert [s.stage for s in report.stages] == list(range(1, 9))
    assert [s.name for s in report.stages] == [STAGE_NAMES[i] for i in range(1, 9)]
    assert run["seen"] == list(range(1, 9))
    assert all(s.status in ("pass", "fail", "skip") for s in report.stages)
    assert report.stages[7].status == "skip"  # no paper stats
    assert report.finished_at and report.strategy_id == "ema_cross_v1"
    assert report.weakest_stage in range(1, 9) and report.weakest_sentence.endswith(".")
    assert report.passed == all(s.status in ("pass", "skip") for s in report.stages)


def test_detail_shapes_follow_architecture(report):
    d = {s.stage: s.detail for s in report.stages}
    assert set(d[2]) == {"in_sample", "oos", "equity"} and "expectancy_r" in d[2]["oos"]
    assert set(d[3]) == {"windows"} and set(d[3]["windows"][0]) == {"train", "test", "stats"}
    assert len(d[3]["windows"]) >= 4
    assert set(d[4]["multipliers"]) == {"1.0", "1.5", "2.0"}
    assert set(d[5]["params"][0]) == {"name", "base", "grid"} and set(d[5]["params"][0]["grid"][0]) == {"delta", "expectancy"}
    assert len(d[5]["params"]) == 5  # fast, slow, atr length, atr mult, target rr
    assert "regimes" in d[6]
    assert set(d[7]) >= {"dd_p5", "dd_p50", "dd_p95", "histogram"} and len(d[7]["histogram"]) == 20
    assert d[8] == {"paper": None, "backtest": d[8]["backtest"], "agreement": None}
    m = {s.stage: s.metrics for s in report.stages}
    assert m[7]["dd_p5"] <= m[7]["dd_p50"] <= m[7]["dd_p95"]
    assert "proportional" in report.stages[2].summary  # 3000 five-minute bars is far short of 4 x 8 months


def test_stops_at_first_hard_fail(trending_bars_module):
    seen = []
    rep = run_pipeline(
        ema_cross_spec(),
        {"NIFTY": trending_bars_module},
        one_r=10_000,
        gates=AcceptanceGates(min_trades_by_timeframe={"5m": 10_000}),
        on_stage=lambda s: seen.append(s.stage),
    )
    assert seen == [1]
    assert rep.stages[0].status == "fail" and 1 in HARD_STAGES
    assert [s.status for s in rep.stages[1:]] == ["pending"] * 7
    assert rep.weakest_stage == 1 and not rep.passed
    assert "In-sample coherence" in rep.weakest_sentence and "not validated" in rep.weakest_sentence


def test_monte_carlo_gate_uses_max_dd(trending_bars_module):
    rep = run_pipeline(ema_cross_spec(), {"NIFTY": trending_bars_module}, one_r=10_000, max_dd_pct=0.01, gates=LOW_GATES)
    assert rep.stages[6].status == "fail" and rep.stages[7].status == "pending"
    assert rep.weakest_stage == 7 and "Monte Carlo" in rep.weakest_sentence


def test_paper_agreement(trending_bars_module, report):
    bt = report.stages[0].metrics["expectancy_r"]
    agree = {"trades": 40, "expectancy_r": bt, "win_rate": 0.5}
    rep = run_pipeline(ema_cross_spec(), {"NIFTY": trending_bars_module}, one_r=10_000, gates=LOW_GATES, paper_stats=agree)
    assert rep.stages[7].status == "pass" and rep.stages[7].detail["agreement"] is True
    disagree = {"trades": 40, "expectancy_r": bt - 5, "win_rate": 0.5}
    rep = run_pipeline(ema_cross_spec(), {"NIFTY": trending_bars_module}, one_r=10_000, gates=LOW_GATES, paper_stats=disagree)
    assert rep.stages[7].status == "fail" and not rep.passed
    few = run_pipeline(ema_cross_spec(), {"NIFTY": trending_bars_module}, one_r=10_000, gates=LOW_GATES, paper_stats={"trades": 5})
    assert few.stages[7].status == "skip"


def test_numeric_params_and_perturbation():
    spec = ema_cross_spec(trailing={"type": "atr", "params": {"length": 14, "mult": 2.5}})
    names = [n for n, _ in numeric_params(spec)]
    assert names == ["inputs.fast.length", "inputs.slow.length", "stop.length", "stop.mult", "targets[0].value", "trailing.length", "trailing.mult"]
    p = perturbed_spec(spec, "inputs.fast.length", 8, -0.2)
    assert p["inputs"]["fast"]["params"]["length"] == 6 and isinstance(p["inputs"]["fast"]["params"]["length"], int)
    assert perturbed_spec(spec, "inputs.fast.length", 1, -0.2)["inputs"]["fast"]["params"]["length"] == 1
    assert perturbed_spec(spec, "trailing.mult", 2.5, 0.1)["trailing"]["params"]["mult"] == pytest.approx(2.75)
    assert perturbed_spec(spec, "targets[0].value", 2, 0.1)["targets"][0]["value"] == 2
    assert spec["inputs"]["fast"]["params"]["length"] == 8  # untouched


def test_weakest_sentence_for_every_stage(report):
    for s in report.stages:
        sentence = weakest_sentence(s)
        assert sentence and sentence.count(".") >= 1 and STAGE_NAMES[s.stage].split()[0] in sentence


def test_empty_bars_fail_fast():
    rep = run_pipeline(ema_cross_spec(), {}, one_r=10_000)
    assert rep.stages[0].status == "fail" and rep.weakest_stage == 1 and rep.weakest_sentence
