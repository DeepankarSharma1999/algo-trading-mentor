"""Indian equity / F&O transaction cost model (rates as of 2025, discount-broker style).

All rates are stored as fractions (0.00025 == 0.025%). Brokerage is a flat Rs 20 per executed
order on every segment (no delivery cap: the model is meant for a self-directed intraday /
positional trader, and Rs 20 per order is the common ceiling anyway).

Worked example, equity intraday, buy 100 @ 1000, sell 100 @ 1010 (turnover 100,000 + 101,000):

    brokerage       20 + 20                                  =  40.000000
    stt             0.025% of sell 101,000                   =  25.250000
    exchange        0.00297% of 201,000                      =   5.969700
    sebi            0.0001% of 201,000                       =   0.201000
    stamp           0.003% of buy 100,000                    =   3.000000
    gst             18% of (40 + 5.9697 + 0.201 = 46.1707)   =   8.310726
    statutory_total (everything above)                       =  82.731426
    slippage_rupees 3 bps of 100,000 + 3 bps of 101,000      =  60.300000
    total           statutory_total + slippage_rupees        = 143.031426

tests/test_costs.py asserts exactly these numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

Segment = Literal["eq_delivery", "eq_intraday", "fo_futures", "fo_options"]
SEGMENTS: tuple[str, ...] = ("eq_delivery", "eq_intraday", "fo_futures", "fo_options")


@dataclass(frozen=True)
class CostParams:
    brokerage_per_order: float = 20.0
    # STT (securities transaction tax)
    stt_delivery: float = 0.001  # 0.1% both sides
    stt_intraday_sell: float = 0.00025  # 0.025% sell side only
    stt_options_sell: float = 0.001  # 0.1% of sell-side premium
    stt_futures_sell: float = 0.0002  # 0.02% sell side
    # Exchange transaction charges (NSE)
    exch_equity: float = 0.0000297  # 0.00297% both sides
    exch_options: float = 0.0003503  # 0.03503% on premium
    exch_futures: float = 0.0000173  # 0.00173%
    sebi_fee: float = 0.000001  # Rs 10 per crore = 0.0001%
    # Stamp duty, buy side only
    stamp_delivery: float = 0.00015  # 0.015%
    stamp_intraday: float = 0.00003  # 0.003%
    stamp_options: float = 0.00003  # 0.003%
    stamp_futures: float = 0.00002  # 0.002%
    gst: float = 0.18  # on brokerage + exchange + SEBI
    slippage_bps: float = 3.0  # per side, of price
    stress_multiplier: float = 1.0  # scales slippage_bps

    def scaled(self, m: float) -> CostParams:
        """Every rupee-generating rate times m (used by the cost-stress stage). GST rate is untouched:
        it is a tax on the other lines, so it scales with them automatically."""
        if m == 1.0:
            return self
        fields = {k: v * m for k, v in self.__dict__.items() if k not in ("gst", "stress_multiplier")}
        return replace(self, **fields)


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: float
    stt: float
    exchange: float
    sebi: float
    stamp: float
    gst: float
    slippage_rupees: float
    total: float

    @property
    def statutory_total(self) -> float:
        """Everything except slippage (used when slippage is already embedded in the fill price)."""
        return self.total - self.slippage_rupees


def round_trip_cost(
    price_in: float, price_out: float, qty: float, segment: Segment, params: CostParams = CostParams()
) -> CostBreakdown:
    """Costs of buying qty at price_in and selling qty at price_out (or the reverse for a short —
    the sides are symmetric, buy-side charges apply to the buy leg wherever it sits)."""
    if segment not in SEGMENTS:
        raise ValueError(f"unknown segment {segment!r}")
    buy_turn, sell_turn = price_in * qty, price_out * qty
    both = buy_turn + sell_turn
    p = params
    brokerage = 2 * p.brokerage_per_order
    if segment == "eq_delivery":
        stt, exch, stamp = p.stt_delivery * both, p.exch_equity * both, p.stamp_delivery * buy_turn
    elif segment == "eq_intraday":
        stt, exch, stamp = p.stt_intraday_sell * sell_turn, p.exch_equity * both, p.stamp_intraday * buy_turn
    elif segment == "fo_futures":
        stt, exch, stamp = p.stt_futures_sell * sell_turn, p.exch_futures * both, p.stamp_futures * buy_turn
    else:
        stt, exch, stamp = p.stt_options_sell * sell_turn, p.exch_options * both, p.stamp_options * buy_turn
    sebi = p.sebi_fee * both
    gst = p.gst * (brokerage + exch + sebi)
    slippage = p.slippage_bps / 10_000 * p.stress_multiplier * both
    total = brokerage + stt + exch + sebi + stamp + gst + slippage
    return CostBreakdown(brokerage, stt, exch, sebi, stamp, gst, slippage, total)


def per_unit_cost_estimate(price: float, qty: float, segment: Segment, params: CostParams = CostParams()) -> float:
    """Pre-trade estimate of all-in round-trip cost per unit, assuming exit near entry price."""
    if qty <= 0:
        return 0.0
    return round_trip_cost(price, price, qty, segment, params).total / qty
