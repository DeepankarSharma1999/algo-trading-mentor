"""Vectorised indicators on a bars DataFrame (columns ts, open, high, low, close, volume).

Every function returns a Series or DataFrame aligned to the bars index and uses only closed bars:
a value at row t depends on rows <= t. Recursive indicators (Wilder smoothing, supertrend, PSAR)
are seeded the way the original authors did so the first values match reference implementations.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

__all__ = ["INDICATORS", "compute_inputs"]


def _wilder(x: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing: SMA of the first n valid values as seed, then y = y_prev + (x - y_prev) / n."""
    arr = x.to_numpy(dtype=float)
    out = np.full(len(arr), np.nan)
    valid = np.flatnonzero(~np.isnan(arr))
    if len(valid) < n:
        return pd.Series(out, index=x.index)
    first = valid[0]
    k = first + n - 1
    y = arr.copy()
    y[:k] = np.nan
    y[k] = np.nanmean(arr[first : first + n])
    return pd.Series(y, index=x.index).ewm(alpha=1.0 / n, adjust=False).mean()


def _true_range(bars: pd.DataFrame) -> pd.Series:
    prev_close = bars["close"].shift(1).fillna(bars["close"])  # TR[0] = high - low
    return pd.concat(
        [bars["high"] - bars["low"], (bars["high"] - prev_close).abs(), (bars["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1, skipna=False)


def _day(bars: pd.DataFrame) -> pd.Series:
    return bars["ts"].dt.normalize()


def sma(bars: pd.DataFrame, length: int = 20, source: str = "close") -> pd.Series:
    return bars[source].rolling(int(length)).mean().rename("sma")


def ema(bars: pd.DataFrame, length: int = 20, source: str = "close") -> pd.Series:
    return bars[source].ewm(span=int(length), adjust=False).mean().rename("ema")


def rsi(bars: pd.DataFrame, length: int = 14, source: str = "close") -> pd.Series:
    delta = bars[source].diff()
    avg_gain = _wilder(delta.clip(lower=0), int(length))
    avg_loss = _wilder(-delta.clip(upper=0), int(length))
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.where(avg_loss != 0, 100.0).where(avg_gain.notna())
    return out.rename("rsi")


def macd(bars: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(bars, fast) - ema(bars, slow)
    sig = line.ewm(span=int(signal), adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bbands(bars: pd.DataFrame, length: int = 20, mult: float = 2.0, pct_window: int = 120) -> pd.DataFrame:
    """Population stdev (ddof=0, TradingView convention). bandwidth = (upper - lower) / mid;
    bw_pct is bandwidth's percentile rank (0-100) within the trailing pct_window bars."""
    mid = bars["close"].rolling(int(length)).mean()
    sd = bars["close"].rolling(int(length)).std(ddof=0)
    upper, lower = mid + mult * sd, mid - mult * sd
    bw = (upper - lower) / mid
    bw_pct = bw.rolling(int(pct_window), min_periods=max(2, int(pct_window) // 4)).rank(pct=True) * 100
    return pd.DataFrame({"upper": upper, "mid": mid, "lower": lower, "bandwidth": bw, "bw_pct": bw_pct})


def atr(bars: pd.DataFrame, length: int = 14) -> pd.Series:
    return _wilder(_true_range(bars), int(length)).rename("atr")


def supertrend(bars: pd.DataFrame, length: int = 10, mult: float = 3.0) -> pd.DataFrame:
    hl2 = (bars["high"] + bars["low"]) / 2
    a = atr(bars, length).to_numpy()
    up, lo = (hl2 + mult * a).to_numpy(), (hl2 - mult * a).to_numpy()
    close = bars["close"].to_numpy(dtype=float)
    n = len(close)
    line, direction = np.full(n, np.nan), np.zeros(n)
    fu, fl = np.full(n, np.nan), np.full(n, np.nan)
    started = False
    for i in range(n):
        if np.isnan(a[i]):
            continue
        if not started:
            fu[i], fl[i], direction[i], started = up[i], lo[i], 1, True
            line[i] = fl[i]
            continue
        fu[i] = up[i] if (up[i] < fu[i - 1] or close[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lo[i] if (lo[i] > fl[i - 1] or close[i - 1] < fl[i - 1]) else fl[i - 1]
        if direction[i - 1] == -1:
            direction[i] = 1 if close[i] > fu[i] else -1
        else:
            direction[i] = -1 if close[i] < fl[i] else 1
        line[i] = fl[i] if direction[i] == 1 else fu[i]
    direction[np.isnan(line)] = np.nan
    return pd.DataFrame({"line": line, "direction": direction}, index=bars.index)


def donchian(bars: pd.DataFrame, length: int = 20) -> pd.DataFrame:
    upper = bars["high"].rolling(int(length)).max()
    lower = bars["low"].rolling(int(length)).min()
    return pd.DataFrame({"upper": upper, "lower": lower, "mid": (upper + lower) / 2})


def vwap(bars: pd.DataFrame, sigma: tuple[float, ...] | list[float] = (1, 2)) -> pd.DataFrame:
    """Session VWAP resetting each calendar day, with bands at k * sqrt(session variance of
    typical price weighted by volume): var = cum(tp^2 v) / cum(v) - vwap^2."""
    day = _day(bars)
    tp = (bars["high"] + bars["low"] + bars["close"]) / 3
    vol = bars["volume"].astype(float)
    cum_v = vol.groupby(day).cumsum()
    cum_pv = (tp * vol).groupby(day).cumsum()
    cum_p2v = (tp * tp * vol).groupby(day).cumsum()
    vw = cum_pv / cum_v
    sd = np.sqrt((cum_p2v / cum_v - vw * vw).clip(lower=0))
    out = {"vwap": vw}
    for k in sigma:
        k = float(k)
        tag = f"{k:g}".replace(".", "_")
        out[f"upper{tag}"], out[f"lower{tag}"] = vw + k * sd, vw - k * sd
    return pd.DataFrame(out)


def williams_r(bars: pd.DataFrame, length: int = 14) -> pd.Series:
    hh = bars["high"].rolling(int(length)).max()
    ll = bars["low"].rolling(int(length)).min()
    return (-100 * (hh - bars["close"]) / (hh - ll).replace(0, np.nan)).rename("williams_r")


def psar(bars: pd.DataFrame, step: float = 0.02, max_step: float = 0.2) -> pd.Series:
    """Wilder's parabolic SAR. Starts long on bar 1 with SAR at bar 0's low."""
    h, lo = bars["high"].to_numpy(dtype=float), bars["low"].to_numpy(dtype=float)
    n = len(h)
    out = np.full(n, np.nan)
    if n < 2:
        return pd.Series(out, index=bars.index, name="psar")
    long, af, sar, ep = True, step, lo[0], h[0]
    for i in range(1, n):
        prev_sar = sar
        sar = prev_sar + af * (ep - prev_sar)
        if long:
            sar = min(sar, lo[i - 1], lo[i - 2] if i >= 2 else lo[i - 1])
            if lo[i] < sar:  # reverse to short
                long, sar, ep, af = False, ep, lo[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, max_step)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > sar:  # reverse to long
                long, sar, ep, af = True, ep, h[i], step
            elif lo[i] < ep:
                ep, af = lo[i], min(af + step, max_step)
        out[i] = sar
    return pd.Series(out, index=bars.index, name="psar")


def ichimoku(
    bars: pd.DataFrame, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, displacement: int = 26
) -> pd.DataFrame:
    """Senkou lines are shifted FORWARD by `displacement`, so the cloud read at bar t is the one
    computed `displacement` bars earlier. chikou is the close from `displacement` bars ago, so
    `close > ich.chikou` is the classic chikou confirmation without look-ahead."""

    def mid(n: int) -> pd.Series:
        return (bars["high"].rolling(n).max() + bars["low"].rolling(n).min()) / 2

    t, k = mid(int(tenkan)), mid(int(kijun))
    return pd.DataFrame(
        {
            "tenkan": t,
            "kijun": k,
            "senkou_a": ((t + k) / 2).shift(int(displacement)),
            "senkou_b": mid(int(senkou_b)).shift(int(displacement)),
            "chikou": bars["close"].shift(int(displacement)),
        }
    )


def _prior_day_ohlc(bars: pd.DataFrame) -> pd.DataFrame:
    day = _day(bars)
    daily = bars.groupby(day).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    prior = daily.shift(1)
    return prior.reindex(day.to_numpy()).set_index(bars.index)


def pivots(bars: pd.DataFrame) -> pd.DataFrame:
    p = _prior_day_ohlc(bars)
    pp = (p["high"] + p["low"] + p["close"]) / 3
    rng = p["high"] - p["low"]
    return pd.DataFrame(
        {
            "pp": pp,
            "r1": 2 * pp - p["low"],
            "r2": pp + rng,
            "r3": p["high"] + 2 * (pp - p["low"]),
            "s1": 2 * pp - p["high"],
            "s2": pp - rng,
            "s3": p["low"] - 2 * (p["high"] - pp),
        }
    )


def cpr(bars: pd.DataFrame) -> pd.DataFrame:
    p = _prior_day_ohlc(bars)
    pivot = (p["high"] + p["low"] + p["close"]) / 3
    bc = (p["high"] + p["low"]) / 2
    tc = 2 * pivot - bc
    return pd.DataFrame({"pivot": pivot, "bc": bc, "tc": tc, "width": (tc - bc).abs()})


def swing(bars: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """Most recent CONFIRMED swing high/low. Bar i is a swing high when high[i] is the max of
    high[i-lookback .. i+lookback]; that is only known at bar i+lookback, so the value appears
    there and is forward-filled until the next confirmed swing."""
    lb = int(lookback)
    w = 2 * lb + 1
    hi, lo = bars["high"], bars["low"]
    is_high = hi == hi.rolling(w, center=True).max()
    is_low = lo == lo.rolling(w, center=True).min()
    return pd.DataFrame(
        {"high": hi.where(is_high).shift(lb).ffill(), "low": lo.where(is_low).shift(lb).ffill()}
    )


def volume_ratio(bars: pd.DataFrame, window: int = 20) -> pd.Series:
    med = bars["volume"].astype(float).rolling(int(window)).median()
    return (bars["volume"] / med.replace(0, np.nan)).rename("volume_ratio")


def adx(bars: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    n = int(length)
    up, down = bars["high"].diff(), -bars["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0).where(up.notna())
    minus_dm = down.where((down > up) & (down > 0), 0.0).where(down.notna())
    tr_s = _wilder(_true_range(bars), n)
    plus_di = 100 * _wilder(plus_dm, n) / tr_s
    minus_di = 100 * _wilder(minus_dm, n) / tr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"adx": _wilder(dx, n), "plus_di": plus_di, "minus_di": minus_di})


def heikin_ashi(bars: pd.DataFrame) -> pd.DataFrame:
    """ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2 is an EWM (alpha 0.5) of the lagged ha_close."""
    ha_close = (bars["open"] + bars["high"] + bars["low"] + bars["close"]) / 4
    seed = ha_close.shift(1)
    seed.iloc[0] = (bars["open"].iloc[0] + bars["close"].iloc[0]) / 2
    ha_open = seed.ewm(alpha=0.5, adjust=False).mean()
    return pd.DataFrame(
        {
            "open": ha_open,
            "high": pd.concat([bars["high"], ha_open, ha_close], axis=1).max(axis=1),
            "low": pd.concat([bars["low"], ha_open, ha_close], axis=1).min(axis=1),
            "close": ha_close,
        }
    )


INDICATORS: dict[str, Callable[..., pd.Series | pd.DataFrame]] = {
    "sma": sma,
    "ema": ema,
    "rsi": rsi,
    "macd": macd,
    "bbands": bbands,
    "atr": atr,
    "supertrend": supertrend,
    "donchian": donchian,
    "vwap": vwap,
    "williams_r": williams_r,
    "psar": psar,
    "ichimoku": ichimoku,
    "pivots": pivots,
    "cpr": cpr,
    "swing": swing,
    "volume_ratio": volume_ratio,
    "adx": adx,
    "heikin_ashi": heikin_ashi,
}


def compute_inputs(bars: pd.DataFrame, inputs: dict) -> dict[str, pd.Series | pd.DataFrame]:
    """inputs: {name: {"indicator": str, "params": {...}}} (dicts or schema Input models)."""
    out: dict[str, pd.Series | pd.DataFrame] = {}
    for name, inp in inputs.items():
        ind = inp["indicator"] if isinstance(inp, dict) else inp.indicator
        params = inp["params"] if isinstance(inp, dict) else inp.params
        fn = INDICATORS.get(str(ind))
        if fn is None:
            raise KeyError(f"unknown indicator {ind!r} for input {name!r}")
        out[name] = fn(bars, **params)
    return out
