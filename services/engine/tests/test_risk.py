from datetime import datetime

from engine.risk.engine import TradeRow, gate_new_exposure, is_tightening, one_r, position_size, risk_status

NOW = datetime(2025, 6, 12, 10, 35)


def test_one_r_by_profile():
    assert one_r(400_000, "conservative") == 1000
    assert one_r(400_000, "standard") == 2000
    assert one_r(400_000, "hard_ceiling") == 4000


def test_tightening_direction():
    assert is_tightening("standard", "conservative")
    assert is_tightening("standard", "standard")
    assert not is_tightening("conservative", "hard_ceiling")


def test_daily_and_weekly_usage_counts_losses_only():
    trades = [
        TradeRow(-1.0, datetime(2025, 6, 12, 9, 50), "closed"),
        TradeRow(+2.0, datetime(2025, 6, 12, 10, 10), "closed"),
        TradeRow(-0.8, datetime(2025, 6, 10, 14, 0), "closed"),  # same week (Tue)
        TradeRow(-3.0, datetime(2025, 6, 6, 14, 0), "closed"),  # previous week
        TradeRow(None, None, "open", planned_risk_r=1.0),
    ]
    s = risk_status(400_000, "standard", trades, NOW)
    assert s.daily_used_r == 1.0 and s.weekly_used_r == 1.8 and s.concurrent_used_r == 1.0
    assert s.brakes == {"daily": False, "weekly": False, "concurrent": False}
    s2 = risk_status(400_000, "conservative", trades, NOW)
    assert s2.brakes["concurrent"] is True  # 1R open vs 1R limit


def test_trades_dated_after_now_are_ignored():
    """A replayed loop of the feed leaves trades dated later in the same sim week; they must not spend the brakes."""
    trades = [
        TradeRow(-1.0, datetime(2025, 6, 12, 9, 50), "closed"),
        TradeRow(-3.0, datetime(2025, 6, 12, 14, 0), "closed"),  # later today, from a previous loop
        TradeRow(-3.0, datetime(2025, 6, 13, 10, 0), "closed"),  # later this week, from a previous loop
    ]
    s = risk_status(400_000, "standard", trades, NOW)
    assert s.daily_used_r == 1.0 and s.weekly_used_r == 1.0
    assert s.brakes == {"daily": False, "weekly": False, "concurrent": False}


def test_position_size_never_widens_stop():
    assert position_size(2000, 100) == 20
    assert position_size(2000, 100, lot_size=25) == 0  # less than one lot => skip, never widen
    assert position_size(5000, 100, lot_size=25) == 50
    assert position_size(2000, 0) == 0


def test_gates_explain_blocks():
    trades = [TradeRow(-2.0, datetime(2025, 6, 12, 9, 50), "closed")]
    s = risk_status(400_000, "standard", trades, NOW)
    gates = gate_new_exposure(s, 1.0, "CALM", 0, 3)
    daily = next(g for g in gates if g["name"] == "Daily risk brake")
    assert daily["pass"] is False and "brake" in daily["reason"]
    assert all("reason" not in g for g in gates if g["pass"])
    cool = next(g for g in gate_new_exposure(s, 1.0, "COOLDOWN", 0, 3) if g["name"].startswith("Behavioural"))
    assert cool["pass"] is False and "journal only" in cool["reason"].lower()
