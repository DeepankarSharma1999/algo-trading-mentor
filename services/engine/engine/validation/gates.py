"""Acceptance gates for the validation pipeline. One dataclass so a test or an admin can loosen them."""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_MIN_TRADES: dict[str, int] = {
    "1m": 300,
    "3m": 250,
    "5m": 200,
    "15m": 120,
    "30m": 90,
    "1h": 60,
    "1D": 60,
}


@dataclass
class AcceptanceGates:
    min_expectancy_r: float = 0.0  # OOS, walk-forward and cost-stressed expectancy must exceed this
    max_largest_trade_share: float = 0.30
    oos_fraction: float = 0.30
    wf_train_months: int = 6
    wf_test_months: int = 2
    wf_min_windows: int = 4
    cost_multipliers: tuple[float, ...] = (1.5, 2.0)  # first is hard, the rest are "watch"
    sensitivity_deltas: tuple[float, ...] = (-0.2, -0.1, 0.1, 0.2)
    sensitivity_plateau_share: float = 0.60  # share of neighbours that must keep expectancy > 0
    sensitivity_max_deviation_mult: float = 3.0  # |neighbour - base| <= mult * |base|
    sensitivity_base_floor_r: float = 0.05  # |base| is floored here so a near-zero base is not a trap
    mc_resamples: int = 1000
    mc_seed: int = 7
    mc_histogram_bins: int = 20
    paper_min_trades: int = 30
    paper_rel_tolerance: float = 0.50
    paper_abs_tolerance: float = 0.20
    min_trades_by_timeframe: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_MIN_TRADES))

    def min_trades(self, timeframe: str) -> int:
        return self.min_trades_by_timeframe.get(str(timeframe), 60)
