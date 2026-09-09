"""Resample 1-minute bars to the engine's higher timeframes.

Bars are labelled by their open time and aligned to the NSE session open, so the 09:15 5m bar
covers 09:15:00-09:19:59 and 1h bars sit at 09:15, 10:15, ..., 15:15 (the last one is a 15-minute
stub, exactly as on a real chart). Empty buckets (overnight, holidays) are dropped. The daily
timeframe produces one bar per session, labelled at 09:15 of that day.
"""

from __future__ import annotations

import pandas as pd

from engine.data.calendar import SESSION_OPEN

BAR_COLUMNS = ["ts", "open", "high", "low", "close", "volume"]

# timeframe -> pandas offset alias (None = one bar per session day)
TIMEFRAMES: dict[str, str | None] = {
    "1m": "1min",
    "3m": "3min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "60min",
    "1D": None,
}

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
_SESSION_OFFSET = pd.Timedelta(hours=SESSION_OPEN.hour, minutes=SESSION_OPEN.minute)


def normalize_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with the canonical column order, dtypes and ascending ts."""
    out = df.loc[:, BAR_COLUMNS].copy()
    out["ts"] = pd.to_datetime(out["ts"]).astype("datetime64[ns]")
    for c in ("open", "high", "low", "close"):
        out[c] = out[c].astype("float32")
    out["volume"] = out["volume"].astype("int64")
    return out.sort_values("ts", kind="stable").reset_index(drop=True)


def resample_bars(bars_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate 1-minute bars into `timeframe` (one of TIMEFRAMES).

    Input must have columns ts, open, high, low, close, volume with tz-naive ts. Output has the same
    columns, prices float32, volume int64, ts = bucket open time, sorted ascending.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown timeframe {timeframe!r}; expected one of {list(TIMEFRAMES)}")
    df = normalize_bars(bars_1m)
    if df.empty or timeframe == "1m":
        return df

    rule = TIMEFRAMES[timeframe]
    if rule is None:  # 1D
        day = df["ts"].dt.normalize()
        out = df.groupby(day, sort=True).agg(_AGG)
        out.index = out.index + _SESSION_OFFSET
    else:
        out = (
            df.set_index("ts")
            .resample(rule, label="left", closed="left", origin="start_day", offset=_SESSION_OFFSET)
            .agg(_AGG)
            .dropna(subset=["open"])
        )
    out.index.name = "ts"
    return normalize_bars(out.reset_index())
