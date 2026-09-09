"""Deterministic synthetic NSE-like 1-minute OHLCV generator.

EVERY PRICE PRODUCED HERE IS SYNTHETIC. The tickers are familiar names used only so the app reads
naturally; no bar in this folder ever traded anywhere. See data/README.md for the model.

Run:  python data/generate.py            (writes data/SYNTHETIC_<SYMBOL>_1m.parquet)
      python data/generate.py --seed 7   (a different universe)

The calendar (holidays, event days, session times) is shared with the engine and lives in
services/engine/engine/data/calendar.py.
"""

from __future__ import annotations

import argparse
import sys
import zlib
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "engine"))

from engine.data.calendar import (  # noqa: E402
    BARS_PER_DAY,
    DATA_END,
    DATA_START,
    EVENT_DAYS,
    session_index,
    trading_days,
)

OUT_DIR = Path(__file__).resolve().parent
DEFAULT_SEED = 20240101
TICK = 0.05

# Starting level and "personality": beta to the common market factor, idiosyncratic daily vol in
# the normal regime, and base 1-minute volume. Index "volume" stands in for futures volume.
SYMBOLS: dict[str, dict[str, float]] = {
    "NIFTY": {"start": 21500.0, "beta": 1.00, "idio_vol": 0.0015, "volume": 4000},
    "BANKNIFTY": {"start": 46000.0, "beta": 1.15, "idio_vol": 0.0050, "volume": 2500},
    "RELIANCE": {"start": 2600.0, "beta": 0.95, "idio_vol": 0.0105, "volume": 9000},
    "HDFCBANK": {"start": 1650.0, "beta": 1.05, "idio_vol": 0.0110, "volume": 14000},
    "ICICIBANK": {"start": 1000.0, "beta": 1.10, "idio_vol": 0.0105, "volume": 16000},
    "INFY": {"start": 1550.0, "beta": 0.75, "idio_vol": 0.0120, "volume": 8000},
    "TCS": {"start": 3800.0, "beta": 0.70, "idio_vol": 0.0100, "volume": 3500},
    "SBIN": {"start": 620.0, "beta": 1.15, "idio_vol": 0.0135, "volume": 30000},
    "ITC": {"start": 440.0, "beta": 0.60, "idio_vol": 0.0095, "volume": 25000},
    "LT": {"start": 3400.0, "beta": 1.00, "idio_vol": 0.0120, "volume": 4000},
    "AXISBANK": {"start": 1050.0, "beta": 1.15, "idio_vol": 0.0130, "volume": 15000},
    "KOTAKBANK": {"start": 1800.0, "beta": 0.95, "idio_vol": 0.0115, "volume": 6000},
}

# Three-state volatility regime: quiet / normal / high-vol. Rows sum to 1; diagonals set persistence
# (mean durations ~20, ~17 and ~8 trading days).
REGIME_VOL_MULT = np.array([0.55, 1.0, 2.1])
REGIME_TRANSITION = np.array(
    [
        [0.950, 0.050, 0.000],
        [0.030, 0.940, 0.030],
        [0.000, 0.125, 0.875],
    ]
)
FACTOR_VOL = 0.0085  # common factor daily vol in the normal regime (NIFTY ~ 13.5 % annualised)
EVENT_VOL_MULT = 2.0
EVENT_VOLUME_MULT = 1.6
GAP_VAR_SHARE = 0.30  # share of daily variance realised in the overnight gap
DRIFT_PHI = 0.985  # AR(1) persistence of the daily drift (trends last weeks)
DRIFT_STD = 0.0012  # stationary std of the daily drift
DRIFT_MEAN = 0.0003  # ~ +7.5 %/year long-run

_minute = np.arange(BARS_PER_DAY)
# Intraday vol profile: heavy first half hour, lighter middle, pick-up into the close.
VOL_PROFILE = 1.0 + 1.6 * np.exp(-_minute / 25.0) + 0.5 * np.exp(-(BARS_PER_DAY - 1 - _minute) / 30.0)
VOL_PROFILE /= np.sqrt(np.mean(VOL_PROFILE**2))  # unit RMS so daily vol is preserved
# Intraday volume profile: opening spike, lunch lull, closing ramp.
VOLUME_PROFILE = (
    1.0
    + 3.0 * np.exp(-_minute / 20.0)
    + 1.2 * np.exp(-(BARS_PER_DAY - 1 - _minute) / 25.0)
    - 0.35 * np.exp(-(((_minute - 180) / 60.0) ** 2))
)

_DTYPES = {
    "ts": "datetime64[ns]",
    "open": "float32",
    "high": "float32",
    "low": "float32",
    "close": "float32",
    "volume": "int32",
}


def _rng(seed: int, *tags: str) -> np.random.Generator:
    """Independent stream per (seed, tag...) so each symbol and sub-process is reproducible."""
    return np.random.default_rng([seed, *(zlib.crc32(t.encode()) for t in tags)])


def _regimes(rng: np.random.Generator, n_days: int) -> np.ndarray:
    """Sample a path of the 3-state Markov chain, starting from the normal regime."""
    states = np.empty(n_days, dtype=np.int64)
    s = 1
    u = rng.random(n_days)
    cum = np.cumsum(REGIME_TRANSITION, axis=1)
    for i in range(n_days):
        s = min(int(np.searchsorted(cum[s], u[i])), 2)
        states[i] = s
    return states


def _drift(rng: np.random.Generator, n_days: int) -> np.ndarray:
    innov = rng.standard_normal(n_days) * DRIFT_STD * np.sqrt(1.0 - DRIFT_PHI**2)
    mu = np.empty(n_days)
    x = 0.0
    for i in range(n_days):
        x = DRIFT_PHI * x + innov[i]
        mu[i] = x
    return mu + DRIFT_MEAN


def _returns(seed: int, tag: str, days: list[date], base_vol: float, drift_mean_scale: float = 1.0):
    """Daily gap log-returns (n_days,), minute log-returns (n_days, 375), regimes, minute vol."""
    n = len(days)
    regimes = _regimes(_rng(seed, tag, "regime"), n)
    drift = _drift(_rng(seed, tag, "drift"), n) * drift_mean_scale
    event = np.array([EVENT_VOL_MULT if d in EVENT_DAYS else 1.0 for d in days])
    day_vol = base_vol * REGIME_VOL_MULT[regimes] * event
    gap = _rng(seed, tag, "gap").standard_normal(n) * day_vol * np.sqrt(GAP_VAR_SHARE)
    z = _rng(seed, tag, "noise").standard_normal((n, BARS_PER_DAY))
    minute_vol = day_vol[:, None] * np.sqrt(1.0 - GAP_VAR_SHARE) / np.sqrt(BARS_PER_DAY) * VOL_PROFILE[None, :]
    minute = z * minute_vol + drift[:, None] / BARS_PER_DAY
    return gap, minute, regimes, minute_vol


def common_factor(start: date | str, end: date | str, seed: int = DEFAULT_SEED) -> dict[str, np.ndarray]:
    """The market-wide factor every symbol loads on. Depends only on (start, end, seed)."""
    days = trading_days(start, end)
    gap, minute, regimes, minute_vol = _returns(seed, "FACTOR", days, FACTOR_VOL)
    return {"days": np.array(days), "gap": gap, "minute": minute, "regimes": regimes, "minute_vol": minute_vol}


def generate_symbol(
    symbol: str,
    start: date | str = DATA_START,
    end: date | str = DATA_END,
    seed: int = DEFAULT_SEED,
    factor: dict[str, np.ndarray] | None = None,
) -> pd.DataFrame:
    """1-minute OHLCV bars for `symbol` over [start, end]. Same arguments => identical output.

    Returns columns ts (datetime64[ns], tz-naive IST), open/high/low/close (float32, tick 0.05),
    volume (int32); 375 rows per trading day. `factor` is the output of `common_factor` for the
    same range and seed (computed on demand when omitted).
    """
    if symbol not in SYMBOLS:
        raise KeyError(f"unknown synthetic symbol {symbol!r}; known: {sorted(SYMBOLS)}")
    spec = SYMBOLS[symbol]
    days = trading_days(start, end)
    n = len(days)
    if n == 0:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in _DTYPES.items()})
    if factor is None or len(factor["days"]) != n or factor["days"][0] != days[0]:
        factor = common_factor(start, end, seed)

    beta = spec["beta"]
    gap_e, minute_e, regimes, minute_vol_e = _returns(seed, symbol, days, spec["idio_vol"], drift_mean_scale=0.0)
    gap = beta * factor["gap"] + gap_e
    minute = beta * factor["minute"] + minute_e

    # Log price path: day open = previous close * exp(gap); bar close = bar open * exp(r).
    day_ret = gap + minute.sum(axis=1)
    prev_close = np.log(spec["start"]) + np.concatenate([[0.0], np.cumsum(day_ret)[:-1]])
    log_open0 = prev_close + gap
    log_close = log_open0[:, None] + np.cumsum(minute, axis=1)
    log_open = np.concatenate([log_open0[:, None], log_close[:, :-1]], axis=1)
    open_ = np.exp(log_open)
    close = np.exp(log_close)

    # Intrabar range: wick beyond the body proportional to the local minute vol.
    rr = _rng(seed, symbol, "range")
    local_vol = np.sqrt((beta * factor["minute_vol"]) ** 2 + minute_vol_e**2)
    body_hi = np.maximum(open_, close)
    body_lo = np.minimum(open_, close)
    high = body_hi * (1.0 + np.abs(rr.standard_normal((n, BARS_PER_DAY))) * 0.6 * local_vol)
    low = body_lo * (1.0 - np.abs(rr.standard_normal((n, BARS_PER_DAY))) * 0.6 * local_vol)

    # Volume: U-shape x regime x event x |return| shock x lognormal noise.
    vr = _rng(seed, symbol, "volume")
    event = np.array([EVENT_VOLUME_MULT if d in EVENT_DAYS else 1.0 for d in days])
    shock = 1.0 + 1.5 * np.abs(minute) / np.maximum(local_vol, 1e-9)
    vol_mult = (0.7 + 0.6 * REGIME_VOL_MULT[regimes]) * event
    noise = np.exp(0.45 * vr.standard_normal((n, BARS_PER_DAY)))
    volume = spec["volume"] * VOLUME_PROFILE[None, :] * vol_mult[:, None] * shock * noise

    def tick(x: np.ndarray) -> np.ndarray:
        return np.round(x / TICK) * TICK

    o, c = tick(open_), tick(close)
    h = np.maximum(tick(high), np.maximum(o, c))
    lo = np.minimum(tick(low), np.minimum(o, c))

    ts = pd.DatetimeIndex(np.concatenate([session_index(d).values for d in days]))
    return pd.DataFrame(
        {
            "ts": ts.astype("datetime64[ns]"),
            "open": o.ravel().astype("float32"),
            "high": h.ravel().astype("float32"),
            "low": lo.ravel().astype("float32"),
            "close": c.ravel().astype("float32"),
            "volume": np.clip(np.rint(volume.ravel()), 1, np.iinfo(np.int32).max).astype("int32"),
        }
    )


def write_all(out_dir: Path = OUT_DIR, seed: int = DEFAULT_SEED, start=DATA_START, end=DATA_END) -> list[Path]:
    """Generate every symbol and write the parquet files. Returns the written paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    factor = common_factor(start, end, seed)
    written: list[Path] = []
    for symbol in SYMBOLS:
        df = generate_symbol(symbol, start, end, seed, factor)
        path = out_dir / f"SYNTHETIC_{symbol}_1m.parquet"
        df.to_parquet(path, engine="pyarrow", compression="zstd", index=False)
        written.append(path)
        size = path.stat().st_size / 1e6
        print(f"{path.name}: {len(df):,} rows, {size:.1f} MB, last close {df['close'].iloc[-1]:.2f}")
    total = sum(p.stat().st_size for p in written) / 1e6
    print(f"total {total:.1f} MB in {out_dir}")
    return written


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    write_all(args.out, args.seed)


if __name__ == "__main__":
    main()
