"""Per-bar market regime from closed bars only.

Priority when several match: event > high_vol > compression > trend > range. `range` is also the
fallback for bars that match nothing (including the warm-up period).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from engine import indicators as ind
from engine.data.calendar import EVENT_DAYS

# RBI MPC decision days 2024-2025 plus the two Union Budget days.
DEFAULT_EVENT_DATES: frozenset[date] = frozenset(EVENT_DAYS)  # RBI MPC + Union Budget, from engine.data.calendar

REGIMES: tuple[str, ...] = ("trend", "range", "compression", "high_vol", "event")


@dataclass
class RegimeConfig:
    adx_length: int = 14
    adx_trend: float = 25.0
    adx_range: float = 20.0
    ema_length: int = 20
    slope_bars: int = 5
    slope_atr_threshold: float = 1.0  # |EMA20[t] - EMA20[t-5]| / ATR14
    bb_length: int = 20
    bb_mult: float = 2.0
    bb_pct_window: int = 120
    bb_stability_window: int = 20
    bb_stability_max: float = 0.25  # rolling std / rolling mean of bandwidth
    compression_bw_pct: float = 20.0
    compression_volume_ratio: float = 0.8
    volume_window: int = 20
    rv_window: int = 20
    rv_pct_window: int = 250
    rv_pct_threshold: float = 85.0
    event_dates: set[date] = field(default_factory=lambda: set(DEFAULT_EVENT_DATES))


def classify(bars: pd.DataFrame, cfg: RegimeConfig | None = None) -> pd.Series:
    cfg = cfg or RegimeConfig()
    a = ind.adx(bars, cfg.adx_length)["adx"]
    atr = ind.atr(bars, cfg.adx_length)
    ema = ind.ema(bars, cfg.ema_length)
    slope = (ema - ema.shift(cfg.slope_bars)).abs() / atr.replace(0, np.nan)
    bb = ind.bbands(bars, cfg.bb_length, cfg.bb_mult, cfg.bb_pct_window)
    bw_roll = bb["bandwidth"].rolling(cfg.bb_stability_window)
    bw_stability = bw_roll.std(ddof=0) / bw_roll.mean().replace(0, np.nan)
    vr = ind.volume_ratio(bars, cfg.volume_window)
    rv = np.log(bars["close"]).diff().rolling(cfg.rv_window).std()
    rv_pct = rv.rolling(cfg.rv_pct_window, min_periods=max(2, cfg.rv_pct_window // 4)).rank(pct=True) * 100

    trend = (a > cfg.adx_trend) | (slope > cfg.slope_atr_threshold)
    rng = (a < cfg.adx_range) & (bw_stability < cfg.bb_stability_max)
    compression = (bb["bw_pct"] < cfg.compression_bw_pct) & (vr < cfg.compression_volume_ratio)
    high_vol = rv_pct > cfg.rv_pct_threshold
    event = bars["ts"].dt.date.isin(cfg.event_dates) if cfg.event_dates else pd.Series(False, index=bars.index)

    out = pd.Series("range", index=bars.index, dtype=object)
    out[rng.fillna(False)] = "range"
    out[trend.fillna(False)] = "trend"
    out[compression.fillna(False)] = "compression"
    out[high_vol.fillna(False)] = "high_vol"
    out[event.to_numpy()] = "event"
    return out.rename("regime")
