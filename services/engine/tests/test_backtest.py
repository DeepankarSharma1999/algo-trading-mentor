import math

import pandas as pd
import pytest

from engine import indicators as ind
from engine.backtest import BacktestResult, resample_bars, run_backtest, run_backtest_multi
from engine.costs import CostParams
from engine.rules import evaluate, stop_price
from tests.conftest import ema_cross_spec, make_bars

SLIP = CostParams().slippage_bps / 10_000


def perturb_after(bars, k, factor=1.05):
    b = bars.copy()
    for col in ("open", "high", "low", "close"):
        b.loc[b.index > k, col] *= factor
    return b


def test_no_look_ahead_in_signals_and_entries():
    bars = make_bars(900, seed=11, wave_period=200, wave_amp=0.02)
    spec = ema_cross_spec()
    k = 600
    a, b = run_backtest(spec, bars), run_backtest(spec, perturb_after(bars, k))
    cutoff = bars["ts"].iloc[k].isoformat()
    key = lambda t: (t.signal_ts, t.entry_ts, t.side, t.entry, t.stop, t.qty, t.target)  # noqa: E731
    ea = [key(t) for t in a.trades if t.entry_ts <= cutoff]
    eb = [key(t) for t in b.trades if t.entry_ts <= cutoff]
    assert ea and ea == eb
    # and the evaluated setups themselves
    pd.testing.assert_frame_equal(evaluate(spec, bars).iloc[: k + 1], evaluate(spec, perturb_after(bars, k)).iloc[: k + 1])
    # fully-closed trades before k are byte-identical too
    ca = [t for t in a.trades if t.exit_ts < cutoff]
    cb = [t for t in b.trades if t.exit_ts < cutoff]
    assert ca == cb


def test_next_bar_open_fill_with_slippage(bars):
    res = run_backtest(ema_cross_spec(), bars)
    assert res.trades
    for t in res.trades:
        sig = bars.index[bars["ts"] == pd.Timestamp(t.signal_ts)][0]
        assert pd.Timestamp(t.entry_ts) == bars["ts"].iloc[sig + 1]
        raw = bars["open"].iloc[sig + 1]
        assert t.entry == pytest.approx(raw * (1 + SLIP) if t.side == "long" else raw * (1 - SLIP))
        assert t.regime in {"trend", "range", "compression", "high_vol", "event"}


def test_flat_at_close_and_session_enforcement():
    bars = make_bars(900, seed=12)
    spec = ema_cross_spec(session={"start": "10:00", "end": "13:00", "flat_at_close": True})
    res = run_backtest(spec, bars)
    assert res.trades
    for t in res.trades:
        e, x = pd.Timestamp(t.entry_ts), pd.Timestamp(t.exit_ts)
        assert e.date() == x.date()
        assert e.time() >= pd.Timestamp("10:05").time()  # signal bar itself is inside the session
        assert e.time() <= pd.Timestamp("12:50").time()  # fill bar is never the session's last bar
    # the day's last in-range bar closes the position at its close
    closes = [t for t in res.trades if t.exit_reason == "flat_at_close"]
    assert closes
    for t in closes:
        assert pd.Timestamp(t.exit_ts).time() == pd.Timestamp("15:25").time()
    # without flat_at_close (and no target) trades can span days
    spec2 = ema_cross_spec(
        session={"start": "09:15", "end": "15:30", "flat_at_close": False},
        stop={"type": "fixed_pct", "params": {"pct": 5}},
        targets=[],
    )
    res2 = run_backtest(spec2, bars)
    assert any(pd.Timestamp(t.entry_ts).date() != pd.Timestamp(t.exit_ts).date() for t in res2.trades)


def test_time_exits():
    bars = make_bars(900, seed=13)
    res = run_backtest(ema_cross_spec(time_exit={"max_bars": 4}, targets=[]), bars)
    assert res.trades and max(t.bars_held for t in res.trades) <= 4
    assert any(t.exit_reason == "max_bars" for t in res.trades)
    res = run_backtest(ema_cross_spec(time_exit={"at_time": "13:00"}, targets=[]), bars)
    assert all(pd.Timestamp(t.exit_ts).time() <= pd.Timestamp("13:00").time() for t in res.trades)
    assert any(t.exit_reason == "time_exit" for t in res.trades)


def test_sizing_never_widens_stop_and_uses_rule_stop(bars):
    one_r = 10_000.0
    spec = ema_cross_spec()
    computed = ind.compute_inputs(bars, spec["inputs"])
    res = run_backtest(spec, bars, one_r_rupees=one_r)
    for t in res.trades:
        sig = bars.index[bars["ts"] == pd.Timestamp(t.signal_ts)][0]
        assert t.stop == pytest.approx(stop_price(spec, bars, sig, t.side, computed))
        risk = abs(t.entry - t.stop)
        assert t.qty == math.floor(one_r / risk)
        assert t.qty * risk <= one_r
        assert (t.stop < t.entry) if t.side == "long" else (t.stop > t.entry)
        assert t.r_multiple == pytest.approx(t.net_pnl / (risk * t.qty))
        assert t.mfe_r >= 0 and t.mae_r >= 0
        if t.exit_reason == "stop":
            assert t.mae_r >= 1.0


def test_lot_capping_and_skip_for_size(bars):
    spec = ema_cross_spec(market="NSE_FO")
    res = run_backtest(spec, bars, lot_size=25)
    assert res.trades and all(t.qty % 25 == 0 and t.qty >= 25 for t in res.trades)
    tiny = run_backtest(spec, bars, lot_size=25, one_r_rupees=50.0)
    assert tiny.trades == [] and tiny.stats.skipped_for_size > 0
    # the stop is the rule's stop, not widened to make a lot fit
    plain = run_backtest(spec, bars, lot_size=1)
    by_sig = {t.signal_ts: t.stop for t in plain.trades}
    for t in res.trades:
        assert t.stop == pytest.approx(by_sig[t.signal_ts])


def test_max_trades_per_day():
    bars = make_bars(900, seed=14)
    res = run_backtest(ema_cross_spec(risk={"min_rr_after_costs": 0, "max_equity_risk_pct": 0.5, "max_trades_per_day": 1}), bars)
    per_day = pd.Series([pd.Timestamp(t.entry_ts).date() for t in res.trades]).value_counts()
    assert per_day.max() == 1 and res.stats.skipped_day_limit > 0


def test_min_rr_after_costs_skips():
    bars = make_bars(600, seed=15)
    strict = run_backtest(ema_cross_spec(risk={"min_rr_after_costs": 10, "max_equity_risk_pct": 0.5, "max_trades_per_day": 5}), bars)
    assert strict.trades == [] and strict.stats.skipped_for_rr > 0


def test_other_triggers(bars):
    spec = ema_cross_spec(trigger={"type": "bar_close"})
    res = run_backtest(spec, bars)
    for t in res.trades:
        assert t.entry_ts == t.signal_ts
        raw = float(bars.loc[bars["ts"] == pd.Timestamp(t.signal_ts), "close"].iloc[0])
        assert t.entry == pytest.approx(raw * (1 + SLIP) if t.side == "long" else raw * (1 - SLIP))
    res = run_backtest(ema_cross_spec(trigger={"type": "break_of_signal_bar", "offset_pct": 0.05}), bars)
    for t in res.trades:
        row = bars.loc[bars["ts"] == pd.Timestamp(t.signal_ts)].iloc[0]
        if t.side == "long":
            assert t.entry / (1 + SLIP) >= row["high"] * 1.0005 - 1e-9
        else:
            assert t.entry / (1 - SLIP) <= row["low"] * 0.9995 + 1e-9
    assert res.stats.cancelled_orders > 0
    res = run_backtest(ema_cross_spec(trigger={"type": "limit", "offset_pct": 0.05}), bars)
    for t in res.trades:
        row = bars.loc[bars["ts"] == pd.Timestamp(t.signal_ts)].iloc[0]
        if t.side == "long":
            assert t.entry / (1 + SLIP) <= row["close"] * 0.9995 + 1e-9


def test_costs_and_multiplier(bars):
    spec = ema_cross_spec()
    a, b = run_backtest(spec, bars), run_backtest(spec, bars, cost_multiplier=2.0)
    assert a.stats.trades > 0 and a.stats.wins + a.stats.losses == a.stats.trades
    assert all(t.costs > 0 and t.net_pnl == pytest.approx(t.gross_pnl - t.costs) for t in a.trades)
    assert b.stats.expectancy_r < a.stats.expectancy_r
    assert 0 <= a.stats.largest_trade_share <= 1
    assert len(a.equity) == a.stats.trades + 1
    assert a.equity[-1][1] == pytest.approx(a.start_equity + a.stats.net_pnl)
    assert set(a.by_regime) <= {"trend", "range", "compression", "high_vol", "event"}
    assert sum(s.trades for s in a.by_regime.values()) == a.stats.trades


def test_start_end_range(bars):
    spec = ema_cross_spec()
    mid = bars["ts"].iloc[300]
    left, right = run_backtest(spec, bars, end=mid), run_backtest(spec, bars, start=mid)
    assert all(pd.Timestamp(t.signal_ts) < mid for t in left.trades)
    assert all(pd.Timestamp(t.signal_ts) >= mid for t in right.trades)
    assert all(pd.Timestamp(t.exit_ts) < mid for t in left.trades)


def test_multi_instrument_merges_chronologically(bars):
    other = make_bars(600, seed=21)
    res = run_backtest_multi(ema_cross_spec(), {"A": bars, "B": other})
    assert isinstance(res, BacktestResult)
    assert {t.symbol for t in res.trades} == {"A", "B"}
    ts = [t.entry_ts for t in res.trades]
    assert ts == sorted(ts)
    assert len(res.equity) == len(res.trades) + 1
    assert res.stats.trades == len(res.trades)


def test_resample_bars_indian_convention():
    m1 = make_bars(375 * 2, seed=1, freq="1min")
    r5 = resample_bars(m1, "5m")
    assert r5["ts"].iloc[0] == pd.Timestamp("2024-01-01 09:15")
    first = m1.iloc[:5]
    # provider output is float32 (documented in DECISIONS.md), so compare with a tolerance
    assert r5["open"].iloc[0] == pytest.approx(first["open"].iloc[0], rel=1e-6)
    assert r5["close"].iloc[0] == pytest.approx(first["close"].iloc[-1], rel=1e-6)
    assert r5["high"].iloc[0] == pytest.approx(first["high"].max(), rel=1e-6) and r5["volume"].iloc[0] == first["volume"].sum()
    assert len(r5) == 150 and (r5["ts"].dt.minute % 5 == 0).all()
    r1h = resample_bars(m1, "1h")
    assert sorted(r1h["ts"].dt.strftime("%H:%M").unique()) == ["09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15"]
    r1d = resample_bars(m1, "1D")
    assert len(r1d) == 2 and r1d["close"].iloc[0] == pytest.approx(m1["close"].iloc[374], rel=1e-6)
    with pytest.raises(ValueError):
        resample_bars(m1, "2m")


def test_daily_timeframe_runs():
    daily = resample_bars(make_bars(375 * 120, seed=2, freq="1min", vol=0.0004), "1D")
    spec = ema_cross_spec(timeframe="1D", inputs={"fast": {"indicator": "ema", "params": {"length": 3}}, "slow": {"indicator": "ema", "params": {"length": 8}}})
    res = run_backtest(spec, daily)
    assert res.stats.trades > 0
    for t in res.trades:
        assert pd.Timestamp(t.entry_ts).date() > pd.Timestamp(t.signal_ts).date()
