from datetime import date

from engine.regime import DEFAULT_EVENT_DATES, REGIMES, RegimeConfig, classify
from tests.conftest import make_bars

BIG = 1e9


def test_values_and_alignment(bars):
    r = classify(bars)
    assert len(r) == len(bars) and r.index.equals(bars.index)
    assert set(r.unique()) <= set(REGIMES)


def test_event_dates_default_list_and_override():
    assert date(2024, 2, 8) in DEFAULT_EVENT_DATES and date(2025, 2, 1) in DEFAULT_EVENT_DATES
    b = make_bars(150, seed=1, start="2024-02-08 09:15")  # RBI day then 2024-02-09
    r = classify(b)
    assert (r.iloc[:75] == "event").all()
    assert (r.iloc[75:] != "event").all()
    r2 = classify(b, RegimeConfig(event_dates={date(2024, 2, 9)}))
    assert (r2.iloc[:75] != "event").all() and (r2.iloc[75:] == "event").all()


def test_priority_order(bars):
    everything_trend = dict(adx_trend=-1)
    no_high_vol, no_compression = dict(rv_pct_threshold=101), dict(compression_bw_pct=-1)
    # trend beats range
    r = classify(bars, RegimeConfig(**everything_trend, **no_high_vol, **no_compression, adx_range=BIG, bb_stability_max=BIG))
    assert (r.iloc[50:] == "trend").all()
    # compression beats trend
    r = classify(
        bars, RegimeConfig(**everything_trend, **no_high_vol, compression_bw_pct=101, compression_volume_ratio=BIG)
    )
    assert (r.iloc[150:] == "compression").all()
    # high_vol beats compression
    r = classify(
        bars,
        RegimeConfig(**everything_trend, compression_bw_pct=101, compression_volume_ratio=BIG, rv_pct_threshold=-1),
    )
    assert (r.iloc[150:] == "high_vol").all()
    # event beats high_vol
    r = classify(
        bars,
        RegimeConfig(rv_pct_threshold=-1, event_dates={d for d in bars["ts"].dt.date.unique()}),
    )
    assert (r == "event").all()


def test_range_is_fallback_and_needs_low_adx(bars):
    r = classify(bars, RegimeConfig(adx_trend=BIG, slope_atr_threshold=BIG, rv_pct_threshold=101, compression_bw_pct=-1))
    assert (r == "range").all()
