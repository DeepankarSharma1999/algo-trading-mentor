"""Indicators against hand-computed loops and no-look-ahead checks."""

import math

import numpy as np
import pandas as pd
import pytest

from engine import indicators as ind
from tests.conftest import make_bars, session_timestamps

CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
]  # fmt: skip


def frame(closes, highs=None, lows=None, volume=None, start="2024-01-01 09:15"):
    n = len(closes)
    close = np.array(closes, dtype=float)
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.array(highs, dtype=float) if highs is not None else np.maximum(open_, close) + 0.5
    low = np.array(lows, dtype=float) if lows is not None else np.minimum(open_, close) - 0.5
    vol = np.array(volume, dtype=float) if volume is not None else np.full(n, 100.0)
    return pd.DataFrame(
        {"ts": session_timestamps(n, start), "open": open_, "high": high, "low": low, "close": close, "volume": vol}
    )


def test_sma_matches_loop():
    b = frame(CLOSES)
    out = ind.sma(b, 5)
    for i in range(len(CLOSES)):
        if i < 4:
            assert math.isnan(out.iloc[i])
        else:
            assert out.iloc[i] == pytest.approx(sum(CLOSES[i - 4 : i + 1]) / 5)


def test_ema_matches_loop():
    b = frame(CLOSES)
    out = ind.ema(b, 5)
    alpha, e = 2 / 6, CLOSES[0]
    assert out.iloc[0] == pytest.approx(e)
    for i in range(1, len(CLOSES)):
        e = alpha * CLOSES[i] + (1 - alpha) * e
        assert out.iloc[i] == pytest.approx(e)


def test_rsi_wilder_matches_loop():
    n = 14
    b = frame(CLOSES)
    out = ind.rsi(b, n)
    gains, losses = [], []
    for i in range(1, len(CLOSES)):
        d = CLOSES[i] - CLOSES[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    expected = {n: 100 - 100 / (1 + ag / al)}
    for i in range(n + 1, len(CLOSES)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        expected[i] = 100 - 100 / (1 + ag / al)
    assert out.iloc[:n].isna().all()
    for i, v in expected.items():
        assert out.iloc[i] == pytest.approx(v)
    assert 60 < out.iloc[14] < 80  # the classic worked example lands around 70


def test_atr_wilder_matches_loop():
    n = 5
    b = frame(CLOSES)
    out = ind.atr(b, n)
    h, lo, c = b["high"].tolist(), b["low"].tolist(), b["close"].tolist()
    tr = [h[0] - lo[0]] + [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, len(c))]
    a = sum(tr[:n]) / n
    assert out.iloc[n - 1] == pytest.approx(a)
    for i in range(n, len(c)):
        a = (a * (n - 1) + tr[i]) / n
        assert out.iloc[i] == pytest.approx(a)


def test_bbands_population_std_and_bandwidth():
    b = frame(CLOSES)
    out = ind.bbands(b, 5, 2.0, pct_window=8)
    i = 10
    window = CLOSES[i - 4 : i + 1]
    mid = sum(window) / 5
    sd = math.sqrt(sum((x - mid) ** 2 for x in window) / 5)
    assert out["mid"].iloc[i] == pytest.approx(mid)
    assert out["upper"].iloc[i] == pytest.approx(mid + 2 * sd)
    assert out["lower"].iloc[i] == pytest.approx(mid - 2 * sd)
    assert out["bandwidth"].iloc[i] == pytest.approx(4 * sd / mid)
    assert out["bw_pct"].dropna().between(0, 100).all()


def test_donchian_and_williams():
    b = frame(CLOSES)
    d = ind.donchian(b, 4)
    i = 7
    hh, ll = b["high"].iloc[i - 3 : i + 1].max(), b["low"].iloc[i - 3 : i + 1].min()
    assert d["upper"].iloc[i] == hh and d["lower"].iloc[i] == ll and d["mid"].iloc[i] == (hh + ll) / 2
    w = ind.williams_r(b, 4)
    assert w.iloc[i] == pytest.approx(-100 * (hh - CLOSES[i]) / (hh - ll))
    assert w.dropna().between(-100, 0).all()


def test_macd_is_ema_difference():
    b = frame(CLOSES)
    m = ind.macd(b, 3, 6, 2)
    diff = ind.ema(b, 3) - ind.ema(b, 6)
    assert np.allclose(m["macd"], diff)
    assert np.allclose(m["hist"], m["macd"] - m["signal"])


def test_vwap_resets_each_session():
    # 75 bars per 5m day: day 1 is rows 0..74, day 2 starts at row 75
    b = make_bars(150, seed=2)
    v = ind.vwap(b)
    tp = (b["high"] + b["low"] + b["close"]) / 3
    assert v["vwap"].iloc[75] == pytest.approx(tp.iloc[75])
    # hand cumulative for row 77 (third bar of day 2)
    rows = slice(75, 78)
    w = b["volume"].iloc[rows]
    expected = (tp.iloc[rows] * w).sum() / w.sum()
    assert v["vwap"].iloc[77] == pytest.approx(expected)
    var = (tp.iloc[rows] ** 2 * w).sum() / w.sum() - expected**2
    assert v["upper1"].iloc[77] == pytest.approx(expected + math.sqrt(max(var, 0)))
    assert v["lower2"].iloc[77] == pytest.approx(expected - 2 * math.sqrt(max(var, 0)))
    assert v["vwap"].iloc[74] != pytest.approx(v["vwap"].iloc[75])


def test_swing_confirms_only_after_lookback_bars():
    highs = [10, 11, 12, 13, 20, 13, 12, 11, 10, 11, 12, 11, 10, 9, 8, 9, 10, 11, 12, 13]
    lows = [h - 2 for h in highs]
    b = frame([h - 1 for h in highs], highs=highs, lows=lows)
    sw = ind.swing(b, 3)
    # the peak at index 4 (20) is a swing high; it becomes known only at index 7
    assert sw["high"].iloc[:7].isna().all()
    assert sw["high"].iloc[7] == 20
    assert sw["high"].iloc[8] == 20  # forward-filled
    # the trough at index 14 (low 6) is confirmed at 17
    assert sw["low"].iloc[17] == 6
    assert sw["low"].iloc[16] != 6 or math.isnan(sw["low"].iloc[16])


def test_ichimoku_is_displaced_forward_not_backward():
    b = make_bars(200, seed=5)
    ich = ind.ichimoku(b)
    tenkan = (b["high"].rolling(9).max() + b["low"].rolling(9).min()) / 2
    kijun = (b["high"].rolling(26).max() + b["low"].rolling(26).min()) / 2
    raw_a = (tenkan + kijun) / 2
    t = 150
    assert ich["senkou_a"].iloc[t] == pytest.approx(raw_a.iloc[t - 26])
    assert ich["chikou"].iloc[t] == pytest.approx(b["close"].iloc[t - 26])
    assert ich["senkou_b"].iloc[:77].isna().all()


def test_pivots_and_cpr_use_prior_day():
    b = make_bars(150, seed=6)
    day1 = b.iloc[:75]
    hi, lo, cl = day1["high"].max(), day1["low"].min(), day1["close"].iloc[-1]
    pp = (hi + lo + cl) / 3
    p = ind.pivots(b)
    assert p["pp"].iloc[:75].isna().all()
    assert p["pp"].iloc[75] == pytest.approx(pp)
    assert p["r1"].iloc[100] == pytest.approx(2 * pp - lo)
    assert p["s2"].iloc[100] == pytest.approx(pp - (hi - lo))
    assert p["r3"].iloc[100] == pytest.approx(hi + 2 * (pp - lo))
    c = ind.cpr(b)
    bc = (hi + lo) / 2
    assert c["bc"].iloc[80] == pytest.approx(bc)
    assert c["tc"].iloc[80] == pytest.approx(2 * pp - bc)
    assert c["width"].iloc[80] == pytest.approx(abs(2 * pp - 2 * bc))


def test_heikin_ashi_recursion():
    b = frame(CLOSES)
    ha = ind.heikin_ashi(b)
    ha_close = (b["open"] + b["high"] + b["low"] + b["close"]) / 4
    assert np.allclose(ha["close"], ha_close)
    assert ha["open"].iloc[0] == pytest.approx((b["open"].iloc[0] + b["close"].iloc[0]) / 2)
    for i in range(1, 6):
        assert ha["open"].iloc[i] == pytest.approx((ha["open"].iloc[i - 1] + ha_close.iloc[i - 1]) / 2)
    assert (ha["high"] >= ha[["open", "close"]].max(axis=1)).all()


def test_adx_di_bounds_and_volume_ratio():
    b = make_bars(300, seed=7)
    a = ind.adx(b, 14)
    assert a.dropna().apply(lambda col: col.between(0, 100).all()).all()
    vr = ind.volume_ratio(b, 20)
    med = b["volume"].iloc[80:100].median()
    assert vr.iloc[99] == pytest.approx(b["volume"].iloc[99] / med)


def test_supertrend_and_psar_flip_direction():
    b = make_bars(400, seed=8, wave_period=100, wave_amp=0.05)
    st = ind.supertrend(b, 10, 3)
    assert set(st["direction"].dropna().unique()) == {1.0, -1.0}
    up = st["direction"] == 1
    assert (st["line"][up] <= b["close"][up]).all()
    assert (st["line"][~up & st["line"].notna()] >= b["close"][~up & st["line"].notna()]).all()
    ps = ind.psar(b)
    assert ps.iloc[1:].notna().all()
    assert ((ps < b["low"]) | (ps > b["high"])).iloc[5:].mean() > 0.9


def test_registry_and_compute_inputs():
    assert set(ind.INDICATORS) == {
        "sma", "ema", "rsi", "macd", "bbands", "atr", "supertrend", "donchian", "vwap", "williams_r",
        "psar", "ichimoku", "pivots", "cpr", "swing", "volume_ratio", "adx", "heikin_ashi",
    }  # fmt: skip
    b = make_bars(100, seed=1)
    out = ind.compute_inputs(b, {"e": {"indicator": "ema", "params": {"length": 5}}, "bb": {"indicator": "bbands", "params": {}}})
    assert isinstance(out["e"], pd.Series) and list(out["bb"].columns) == ["upper", "mid", "lower", "bandwidth", "bw_pct"]
    with pytest.raises(KeyError):
        ind.compute_inputs(b, {"x": {"indicator": "nope", "params": {}}})


@pytest.mark.parametrize("name", sorted(ind.INDICATORS))
def test_no_look_ahead(name):
    """Truncating the future must not change any value already computed."""
    b = make_bars(400, seed=9)
    k = 300
    full, part = ind.INDICATORS[name](b), ind.INDICATORS[name](b.iloc[:k].reset_index(drop=True))
    full_df = full.to_frame() if isinstance(full, pd.Series) else full
    part_df = part.to_frame() if isinstance(part, pd.Series) else part
    pd.testing.assert_frame_equal(full_df.iloc[:k].reset_index(drop=True), part_df.reset_index(drop=True))
