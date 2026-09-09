"""Shared fixtures: in-memory bar generation (session bars only) and a base EMA-cross spec."""

from __future__ import annotations

import copy
import json

import numpy as np
import pandas as pd
import pytest

from engine import config

SESSION_START = 9 * 60 + 15
SESSION_END = 15 * 60 + 30


def session_timestamps(n: int, start: str = "2024-01-01 09:15", freq: str = "5min") -> pd.DatetimeIndex:
    """n tz-naive Asia/Kolkata wall-time stamps, weekdays only, 09:15 <= t < 15:30, bar-aligned."""
    step = pd.Timedelta(freq)
    step_min = int(step.total_seconds() // 60)
    day = pd.Timestamp(start).normalize()
    first_minute = pd.Timestamp(start).hour * 60 + pd.Timestamp(start).minute
    out: list[pd.Timestamp] = []
    minutes = list(range(SESSION_START, SESSION_END, step_min))
    while len(out) < n:
        if day.weekday() < 5:
            for m in minutes:
                if day == pd.Timestamp(start).normalize() and m < first_minute:
                    continue
                out.append(day + pd.Timedelta(minutes=m))
                if len(out) == n:
                    break
        day += pd.Timedelta(days=1)
    return pd.DatetimeIndex(out)


def make_bars(
    n: int,
    seed: int = 0,
    start: str = "2024-01-01 09:15",
    freq: str = "5min",
    base: float = 1000.0,
    vol: float = 0.0015,
    drift: float = 0.0,
    wave_period: int | None = None,
    wave_amp: float = 0.0,
) -> pd.DataFrame:
    """Random-walk OHLCV bars. wave_period/wave_amp add a slow sine so trend-followers have
    something to catch; drift is per-bar log drift."""
    rng = np.random.default_rng(seed)
    ts = session_timestamps(n, start, freq)
    i = np.arange(n)
    log_ret = rng.normal(drift, vol, n)
    close = base * np.exp(np.cumsum(log_ret))
    if wave_period:
        close = close * (1 + wave_amp * np.sin(2 * np.pi * i / wave_period))
    open_ = np.empty(n)
    open_[0] = base
    open_[1:] = close[:-1] * (1 + rng.normal(0, vol / 4, n - 1))
    hi = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    lo = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    volume = rng.integers(500, 5000, n).astype(float)
    return pd.DataFrame(
        {"ts": ts, "open": open_, "high": hi, "low": lo, "close": close, "volume": volume}
    )


FIXTURE_BASE = json.loads((config.SCHEMA_DIR / "fixtures" / "testable.cases.json").read_text())["base"]


def base_spec(**patch) -> dict:
    """The shared fixture strategy (15m EMA20 cross, ATR stop, 2R target) with overrides."""
    spec = copy.deepcopy(FIXTURE_BASE)
    spec.update(patch)
    return spec


def ema_cross_spec(**patch) -> dict:
    """Fast/slow EMA cross, long and short, 5m, ATR stop, 2R target, breakeven trailing."""
    spec = base_spec(
        strategy_id="ema_cross_v1",
        name="EMA cross",
        timeframe="5m",
        regime_affinity=["trend", "range"],
        inputs={
            "fast": {"indicator": "ema", "params": {"length": 8}},
            "slow": {"indicator": "ema", "params": {"length": 21}},
        },
        entry_long=[{"lhs": "fast", "op": "crosses_above", "rhs": "slow"}],
        entry_short=[{"lhs": "fast", "op": "crosses_below", "rhs": "slow"}],
        stop={"type": "atr", "params": {"length": 14, "mult": 2}},
        targets=[{"type": "rr", "value": 2}],
        trailing={"type": "none", "params": {}},
        risk={"min_rr_after_costs": 0, "max_equity_risk_pct": 0.5, "max_trades_per_day": 5},
    )
    spec.update(patch)
    return spec


@pytest.fixture
def bars() -> pd.DataFrame:
    return make_bars(600, seed=1)


@pytest.fixture
def trending_bars() -> pd.DataFrame:
    return make_bars(3000, seed=3, vol=0.0008, wave_period=300, wave_amp=0.03)
