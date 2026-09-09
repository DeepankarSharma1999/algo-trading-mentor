"""Tests for the market-data layer: generator, calendar, resampling, providers, option chain."""

import importlib.util
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from engine import config
from engine.data import (
    BAR_COLUMNS,
    CHAIN_COLUMNS,
    HOLIDAYS,
    CsvProvider,
    SyntheticProvider,
    VendorProvider,
    get_provider,
    is_market_open,
    lot_size,
    resample_bars,
    trading_days,
)
from engine.data.options import RISK_FREE_RATE, years_to_expiry


def _load_generator():
    spec = importlib.util.spec_from_file_location("synthetic_generate", config.REPO / "data" / "generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()

# 2024-01-22 (Mon) and 2024-01-26 (Fri) are holidays: 2024-01-22..2024-01-26 has three sessions.
SMALL_START, SMALL_END = "2024-01-22", "2024-01-26"


@pytest.fixture(scope="module")
def small_nifty() -> pd.DataFrame:
    return gen.generate_symbol("NIFTY", SMALL_START, SMALL_END, seed=1)


# --- generator ---------------------------------------------------------------------------------


def test_generator_is_deterministic(small_nifty):
    again = gen.generate_symbol("NIFTY", SMALL_START, SMALL_END, seed=1)
    pd.testing.assert_frame_equal(small_nifty.head(100), again.head(100))
    other_seed = gen.generate_symbol("NIFTY", SMALL_START, SMALL_END, seed=2)
    assert not small_nifty.head(100).equals(other_seed.head(100))


def test_generator_columns_and_dtypes(small_nifty):
    assert list(small_nifty.columns) == BAR_COLUMNS
    assert small_nifty["ts"].dtype == "datetime64[ns]"
    assert small_nifty["ts"].dt.tz is None
    for c in ("open", "high", "low", "close"):
        assert small_nifty[c].dtype == np.float32
    assert small_nifty["volume"].dtype == np.int32


def test_ohlc_consistent_and_tick_rounded(small_nifty):
    df = small_nifty
    assert (df["high"] >= np.maximum(df["open"], df["close"])).all()
    assert (df["low"] <= np.minimum(df["open"], df["close"])).all()
    assert (df["low"] > 0).all()
    assert (df["volume"] >= 1).all()
    ticks = df["close"].astype("float64") / 0.05
    assert np.allclose(ticks, np.round(ticks), atol=1e-2)


def test_session_bars_only_375_per_day(small_nifty):
    t = small_nifty["ts"]
    assert ((t.dt.hour * 60 + t.dt.minute) >= 9 * 60 + 15).all()
    assert ((t.dt.hour * 60 + t.dt.minute) <= 15 * 60 + 29).all()
    per_day = small_nifty.groupby(t.dt.normalize()).size()
    assert (per_day == 375).all()
    assert t.is_monotonic_increasing and t.is_unique


def test_holidays_and_weekends_excluded(small_nifty):
    days = set(small_nifty["ts"].dt.date.unique())
    assert days == {date(2024, 1, 23), date(2024, 1, 24), date(2024, 1, 25)}
    assert date(2024, 1, 26) in HOLIDAYS and date(2024, 1, 22) in HOLIDAYS
    assert date(2024, 3, 29) not in trading_days("2024-03-25", "2024-04-01")  # Good Friday
    assert not any(d.weekday() >= 5 for d in trading_days("2024-01-01", "2024-12-31"))


def test_stocks_correlate_with_nifty():
    factor = gen.common_factor("2024-01-01", "2024-06-30", seed=3)
    nifty = gen.generate_symbol("NIFTY", "2024-01-01", "2024-06-30", seed=3, factor=factor)
    sbin = gen.generate_symbol("SBIN", "2024-01-01", "2024-06-30", seed=3, factor=factor)
    rn = np.log(nifty.groupby(nifty["ts"].dt.normalize())["close"].last().astype(float)).diff().dropna()
    rs = np.log(sbin.groupby(sbin["ts"].dt.normalize())["close"].last().astype(float)).diff().dropna()
    assert np.corrcoef(rn, rs)[0, 1] > 0.3


# --- resampling ----------------------------------------------------------------------------------


def test_resample_5m_alignment(small_nifty):
    five = resample_bars(small_nifty, "5m")
    first = five.iloc[0]
    src = small_nifty.iloc[0:5]
    assert first["ts"] == pd.Timestamp("2024-01-23 09:15")
    assert src["ts"].iloc[-1] == pd.Timestamp("2024-01-23 09:19")
    assert first["open"] == src["open"].iloc[0]
    assert first["close"] == src["close"].iloc[-1]
    assert first["high"] == src["high"].max()
    assert first["low"] == src["low"].min()
    assert first["volume"] == src["volume"].sum()
    assert (five["ts"].dt.minute % 5 == 0).all()
    assert len(five) == 3 * 75
    assert five["volume"].sum() == small_nifty["volume"].sum()


def test_resample_1h_and_30m_align_to_session_open(small_nifty):
    hour = resample_bars(small_nifty, "1h")
    times = sorted(set(hour["ts"].dt.strftime("%H:%M")))
    assert times == ["09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15"]
    half = resample_bars(small_nifty, "30m")
    assert half["ts"].iloc[0] == pd.Timestamp("2024-01-23 09:15")
    assert half["ts"].iloc[1] == pd.Timestamp("2024-01-23 09:45")
    assert len(half) == 3 * 13  # last 30m bucket (15:15-15:29) is a stub


def test_resample_1d(small_nifty):
    day = resample_bars(small_nifty, "1D")
    assert len(day) == 3
    d0 = small_nifty[small_nifty["ts"].dt.date == date(2024, 1, 23)]
    assert day["ts"].iloc[0] == pd.Timestamp("2024-01-23 09:15")
    assert day["open"].iloc[0] == d0["open"].iloc[0]
    assert day["close"].iloc[0] == d0["close"].iloc[-1]
    assert day["high"].iloc[0] == d0["high"].max()
    assert day["low"].iloc[0] == d0["low"].min()
    assert day["volume"].iloc[0] == d0["volume"].sum()


def test_resample_rejects_unknown_timeframe(small_nifty):
    with pytest.raises(ValueError):
        resample_bars(small_nifty, "2h")


# --- providers -----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic() -> SyntheticProvider:
    p = SyntheticProvider(config.DATA_DIR)
    assert (config.DATA_DIR / "SYNTHETIC_NIFTY_1m.parquet").exists(), "run python data/generate.py"
    return p


def test_synthetic_provider_reads_committed_file(synthetic):
    assert synthetic.name == "synthetic"
    assert "NIFTY" in synthetic.symbols() and len(synthetic.symbols()) == 12
    bars = synthetic.get_bars("NIFTY", "1m", "2024-03-01", "2024-03-05")
    assert list(bars.columns) == BAR_COLUMNS
    assert bars["ts"].dtype == "datetime64[ns]" and bars["ts"].dt.tz is None
    for c in ("open", "high", "low", "close"):
        assert bars[c].dtype == np.float32
    assert bars["volume"].dtype == np.int64
    assert bars["ts"].is_monotonic_increasing
    # 2024-03-01 (Fri), 03-04 (Mon), 03-05 (Tue): date-only end includes the whole last day.
    assert len(bars) == 3 * 375
    assert bars["ts"].iloc[-1] == pd.Timestamp("2024-03-05 15:29")
    assert bars["ts"].iloc[0] == pd.Timestamp("2024-03-01 09:15")


def test_synthetic_provider_timeframes_and_cache(synthetic):
    d = synthetic.get_bars("RELIANCE", "1D", "2024-06-01", "2024-06-30")
    assert len(d) == len(trading_days("2024-06-01", "2024-06-30"))
    m15 = synthetic.get_bars("RELIANCE", "15m", datetime(2024, 6, 3, 9, 15), datetime(2024, 6, 3, 10, 14))
    assert len(m15) == 4
    assert synthetic._load.cache_info().hits >= 1
    with pytest.raises(FileNotFoundError):
        synthetic.get_bars("NOPE", "1m")


def test_csv_provider(tmp_path, small_nifty):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    small_nifty.sample(frac=1.0, random_state=0).to_csv(csv_dir / "NIFTY_1m.csv", index=False)
    p = CsvProvider(csv_dir)
    assert p.symbols() == ["NIFTY"]
    bars = p.get_bars("NIFTY", "5m")
    pd.testing.assert_frame_equal(bars, resample_bars(small_nifty, "5m"))


def test_get_provider_and_vendor_stub(tmp_path):
    assert isinstance(get_provider("synthetic"), SyntheticProvider)
    assert isinstance(get_provider("csv", tmp_path), CsvProvider)
    with pytest.raises(NotImplementedError):
        get_provider("vendor")
    with pytest.raises(NotImplementedError):
        VendorProvider()
    with pytest.raises(ValueError):
        get_provider("bloomberg")


def test_lot_sizes():
    assert lot_size("NIFTY", "NSE_FO") == 25
    assert lot_size("BANKNIFTY", "NSE_FO") == 15
    assert lot_size("RELIANCE", "NSE_EQ") == 1


def test_market_open_clock():
    assert is_market_open("2024-03-04 09:15")
    assert is_market_open("2024-03-04 15:29:59")
    assert not is_market_open("2024-03-04 15:30")
    assert not is_market_open("2024-03-03 10:00")  # Sunday
    assert not is_market_open("2024-03-29 10:00")  # Good Friday


# --- option chain --------------------------------------------------------------------------------


@pytest.mark.parametrize("underlying,step", [("NIFTY", 50.0), ("BANKNIFTY", 100.0), ("RELIANCE", None)])
def test_option_chain_parity(synthetic, underlying, step):
    asof = datetime(2024, 3, 4, 13, 0)
    expiry = date(2024, 3, 28)
    chain = synthetic.get_option_chain(underlying, expiry, asof)
    assert list(chain.columns) == CHAIN_COLUMNS
    assert len(chain) == 21
    assert chain["strike"].is_monotonic_increasing
    diffs = chain["strike"].diff().dropna().unique()
    assert len(diffs) == 1
    if step is not None:
        assert diffs[0] == step
    else:
        assert diffs[0] % 5 == 0 and diffs[0] >= 5
    spot = float(synthetic.get_bars(underlying, "1m", end=asof)["close"].iloc[-1])
    t = years_to_expiry(expiry, asof)
    atm = chain.iloc[(chain["strike"] - spot).abs().argmin()]
    parity = spot - atm["strike"] * np.exp(-RISK_FREE_RATE * t)
    # prices are quoted on the 0.05 tick, so C - P can be off by at most one tick
    assert abs((atm["call_price"] - atm["put_price"]) - parity) <= 0.06
    assert (chain["call_price"] > 0).all() and (chain["put_price"] > 0).all()
    assert chain["call_oi"].idxmax() == 10 and chain["put_oi"].idxmax() == 10
    assert chain["call_oi"].iloc[0] < chain["call_oi"].iloc[10]
