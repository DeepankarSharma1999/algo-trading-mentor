import pytest

from engine.costs import CostParams, per_unit_cost_estimate, round_trip_cost


def test_worked_example_intraday_equity():
    c = round_trip_cost(1000, 1010, 100, "eq_intraday")
    assert c.brokerage == pytest.approx(40.0, abs=1e-9)
    assert c.stt == pytest.approx(25.25, abs=1e-9)
    assert c.exchange == pytest.approx(5.9697, abs=1e-9)
    assert c.sebi == pytest.approx(0.201, abs=1e-9)
    assert c.stamp == pytest.approx(3.0, abs=1e-9)
    assert c.gst == pytest.approx(8.310726, abs=1e-9)
    assert c.statutory_total == pytest.approx(82.731426, abs=1e-9)
    assert c.slippage_rupees == pytest.approx(60.3, abs=1e-9)
    assert c.total == pytest.approx(143.031426, abs=1e-9)


def test_delivery_stt_both_sides_and_stamp():
    c = round_trip_cost(1000, 1010, 100, "eq_delivery")
    assert c.stt == pytest.approx(0.001 * 201_000)
    assert c.stamp == pytest.approx(0.00015 * 100_000)


def test_futures_and_options_rates():
    f = round_trip_cost(20000, 20100, 25, "fo_futures")
    assert f.stt == pytest.approx(0.0002 * 20100 * 25)
    assert f.exchange == pytest.approx(0.0000173 * (20000 + 20100) * 25)
    assert f.stamp == pytest.approx(0.00002 * 20000 * 25)
    o = round_trip_cost(100, 120, 50, "fo_options")
    assert o.stt == pytest.approx(0.001 * 120 * 50)
    assert o.exchange == pytest.approx(0.0003503 * 220 * 50)
    assert o.stamp == pytest.approx(0.00003 * 100 * 50)


def test_scaled_multiplies_every_charge_but_gst_rate():
    base = round_trip_cost(1000, 1010, 100, "eq_intraday")
    p = CostParams().scaled(2.0)
    assert p.gst == 0.18 and p.stress_multiplier == 1.0
    c = round_trip_cost(1000, 1010, 100, "eq_intraday", p)
    assert c.total == pytest.approx(2 * base.total)
    assert CostParams().scaled(1.0) is not None


def test_stress_multiplier_only_scales_slippage():
    c = round_trip_cost(1000, 1010, 100, "eq_intraday", CostParams(stress_multiplier=2.0))
    assert c.slippage_rupees == pytest.approx(120.6)
    assert c.statutory_total == pytest.approx(82.731426)


def test_per_unit_estimate_and_bad_segment():
    est = per_unit_cost_estimate(1000, 100, "eq_intraday")
    assert est == pytest.approx(round_trip_cost(1000, 1000, 100, "eq_intraday").total / 100)
    assert per_unit_cost_estimate(1000, 0, "eq_intraday") == 0.0
    with pytest.raises(ValueError):
        round_trip_cost(1, 1, 1, "crypto")  # type: ignore[arg-type]
