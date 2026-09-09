"""Risk engine (ARCHITECTURE §7). Pure functions; the service layer supplies trade rows and the profile.

Only the `trading` bucket ever sizes a position. 1R = trading × per_trade_pct."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

PROFILES: dict[str, dict[str, float]] = {
    "conservative": {"per_trade_pct": 0.25, "daily_r": 1.5, "weekly_r": 4.0, "concurrent_r": 1.0},
    "standard": {"per_trade_pct": 0.50, "daily_r": 2.0, "weekly_r": 5.0, "concurrent_r": 2.0},
    "hard_ceiling": {"per_trade_pct": 1.00, "daily_r": 3.0, "weekly_r": 7.0, "concurrent_r": 3.0},
}
ORDER = ["conservative", "standard", "hard_ceiling"]


def one_r(trading_bucket: float, profile: str) -> float:
    return round(float(trading_bucket) * PROFILES[profile]["per_trade_pct"] / 100.0, 2)


def is_tightening(from_profile: str, to_profile: str) -> bool:
    return ORDER.index(to_profile) <= ORDER.index(from_profile)


@dataclass
class TradeRow:
    outcome_r: float | None
    closed_at: datetime | None
    status: str  # open|closed
    planned_risk_r: float = 1.0


@dataclass
class RiskStatus:
    trading_bucket: float
    one_r: float
    profile: str
    daily_used_r: float
    daily_limit_r: float
    weekly_used_r: float
    weekly_limit_r: float
    concurrent_used_r: float
    concurrent_limit_r: float

    @property
    def brakes(self) -> dict[str, bool]:
        return {
            "daily": self.daily_used_r >= self.daily_limit_r,
            "weekly": self.weekly_used_r >= self.weekly_limit_r,
            "concurrent": self.concurrent_used_r >= self.concurrent_limit_r,
        }

    def to_dict(self) -> dict:
        d = self.__dict__ | {"brakes": self.brakes}
        return d


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def risk_status(trading_bucket: float, profile: str, trades: list[TradeRow], now: datetime) -> RiskStatus:
    p = PROFILES[profile]
    today = now.date()
    wk = _week_start(today)
    daily = sum(max(0.0, -(t.outcome_r or 0.0)) for t in trades if t.status == "closed" and t.closed_at and t.closed_at.date() == today)
    weekly = sum(max(0.0, -(t.outcome_r or 0.0)) for t in trades if t.status == "closed" and t.closed_at and t.closed_at.date() >= wk)
    concurrent = sum(t.planned_risk_r for t in trades if t.status == "open")
    return RiskStatus(
        float(trading_bucket), one_r(trading_bucket, profile), profile,
        round(daily, 4), p["daily_r"], round(weekly, 4), p["weekly_r"], round(concurrent, 4), p["concurrent_r"],
    )


def position_size(one_r_rupees: float, rupee_risk_per_unit: float, lot_size: int = 1, max_units: int | None = None) -> int:
    """floor(allowed_rupee_risk / rupee_risk_per_unit), capped to whole lots. Never widens a stop."""
    if rupee_risk_per_unit <= 0 or one_r_rupees <= 0:
        return 0
    units = math.floor(one_r_rupees / rupee_risk_per_unit)
    if max_units is not None:
        units = min(units, max_units)
    lots = units // lot_size
    return int(lots * lot_size)


def gate_new_exposure(status: RiskStatus, planned_risk_r: float, behaviour_state: str, trades_today: int, max_trades_per_day: int) -> list[dict]:
    """Every risk/behaviour gate with pass/reason, in display order."""
    gates = [
        {"name": "Daily risk brake", "pass": not status.brakes["daily"], "reason": f"Daily loss brake reached ({status.daily_used_r:.2f}R of {status.daily_limit_r}R). No new exposure today."},
        {"name": "Weekly risk brake", "pass": not status.brakes["weekly"], "reason": f"Weekly brake reached ({status.weekly_used_r:.2f}R of {status.weekly_limit_r}R). No new exposure this week."},
        {"name": "Concurrent risk", "pass": status.concurrent_used_r + planned_risk_r <= status.concurrent_limit_r, "reason": f"Open risk {status.concurrent_used_r:.2f}R plus {planned_risk_r:.2f}R exceeds the {status.concurrent_limit_r}R concurrent limit."},
        {"name": "Max trades today", "pass": trades_today < max_trades_per_day, "reason": f"{trades_today} of {max_trades_per_day} trades already taken today."},
        {"name": "Behavioural state allows entries", "pass": behaviour_state in ("CALM", "ELEVATED"), "reason": f"State is {behaviour_state}: journal only until the next session open." if behaviour_state == "COOLDOWN" else f"State is {behaviour_state}: market closed."},
    ]
    for g in gates:
        if g["pass"]:
            g.pop("reason")
    return gates
