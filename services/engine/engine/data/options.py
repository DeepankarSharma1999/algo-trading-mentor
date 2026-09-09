"""Black-Scholes pricing and the synthetic option chain layout.

Used by SyntheticProvider.get_option_chain. Flat implied vol per underlying, continuous risk-free
rate, no dividends, no skew: enough for the interface to carry real numbers that satisfy put-call
parity, nothing more.
"""

from __future__ import annotations

import math
from datetime import date, datetime

import numpy as np
import pandas as pd

RISK_FREE_RATE = 0.065
CHAIN_STEPS = 10  # strikes on each side of ATM
CHAIN_COLUMNS = ["strike", "call_price", "put_price", "call_iv", "put_iv", "call_oi", "put_oi"]

# Flat implied vol by underlying; anything not listed is treated as a stock.
FLAT_IV: dict[str, float] = {"NIFTY": 0.14, "BANKNIFTY": 0.18}
STOCK_IV = 0.28

INDEX_STRIKE_STEP: dict[str, float] = {"NIFTY": 50.0, "BANKNIFTY": 100.0}
STOCK_STEP_PCT = 0.025  # stock strikes: 2.5 % of spot, rounded to a multiple of 5

MIN_YEARS = 1.0 / (365.0 * 24 * 60)  # never price with T = 0
OPTION_TICK = 0.05


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def bs_price(spot: float, strike: np.ndarray, t_years: float, iv: float, r: float = RISK_FREE_RATE):
    """European call and put prices for an array of strikes. Returns (call, put)."""
    k = np.asarray(strike, dtype=float)
    t = max(float(t_years), MIN_YEARS)
    sqrt_t = math.sqrt(t)
    d1 = (np.log(spot / k) + (r + 0.5 * iv * iv) * t) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t
    disc = math.exp(-r * t)
    call = spot * _norm_cdf(d1) - k * disc * _norm_cdf(d2)
    put = k * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
    return call, put


def implied_vol(underlying: str) -> float:
    return FLAT_IV.get(underlying, STOCK_IV)


def strike_step(underlying: str, spot: float) -> float:
    if underlying in INDEX_STRIKE_STEP:
        return INDEX_STRIKE_STEP[underlying]
    return max(5.0, 5.0 * round(spot * STOCK_STEP_PCT / 5.0))


def years_to_expiry(expiry: date, asof: datetime) -> float:
    """Time to the 15:30 close on the expiry date, in years (floored at one minute)."""
    close = datetime.combine(expiry, datetime.min.time()).replace(hour=15, minute=30)
    seconds = (close - asof).total_seconds()
    return max(seconds / (365.0 * 24 * 3600), MIN_YEARS)


def build_chain(underlying: str, spot: float, expiry: date, asof: datetime) -> pd.DataFrame:
    """Strikes ATM +/- CHAIN_STEPS steps, BS prices at a flat IV, and fake OI peaking at the money."""
    step = strike_step(underlying, spot)
    atm = round(spot / step) * step
    offsets = np.arange(-CHAIN_STEPS, CHAIN_STEPS + 1)
    strikes = atm + offsets * step
    iv = implied_vol(underlying)
    t = years_to_expiry(expiry, asof)
    call, put = bs_price(spot, strikes, t, iv)

    base_oi = 2_000_000 if underlying in INDEX_STRIKE_STEP else 250_000
    shape = np.exp(-np.abs(offsets) / 3.5)
    call_oi = (base_oi * shape * np.where(offsets >= 0, 1.0, 0.7)).astype("int64")
    put_oi = (base_oi * shape * np.where(offsets <= 0, 1.0, 0.7)).astype("int64")

    def quote(x: np.ndarray) -> np.ndarray:  # options tick at 0.05; nothing quotes below one tick
        return np.maximum(np.round(x / OPTION_TICK) * OPTION_TICK, OPTION_TICK)

    return pd.DataFrame(
        {
            "strike": strikes.astype(float),
            "call_price": quote(call),
            "put_price": quote(put),
            "call_iv": np.full(len(strikes), iv),
            "put_iv": np.full(len(strikes), iv),
            "call_oi": call_oi,
            "put_oi": put_oi,
        },
        columns=CHAIN_COLUMNS,
    )
