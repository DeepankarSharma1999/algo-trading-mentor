"""NSE session calendar shared by the synthetic generator, the data providers and the paper clock.

Everything here is deliberately small and hardcoded: the synthetic universe covers 2024-01-01 to
2025-12-31 and the app runs on a simulated clock, so a real exchange-calendar dependency buys
nothing. Timestamps throughout the engine are tz-naive Asia/Kolkata wall time.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd

SESSION_OPEN = time(9, 15)
SESSION_LAST_BAR = time(15, 29)  # open time of the last 1-minute bar
SESSION_CLOSE = time(15, 30)
BARS_PER_DAY = 375

DATA_START = date(2024, 1, 1)
DATA_END = date(2025, 12, 31)

# NSE trading holidays that fall on weekdays. Weekend holidays are omitted (they are closed anyway).
# The list follows the published NSE calendars closely enough for a synthetic feed; it is not
# authoritative and must never be used to decide anything about a real market.
HOLIDAYS: dict[date, str] = {
    # 2024
    date(2024, 1, 22): "Special holiday (Ram Mandir)",
    date(2024, 1, 26): "Republic Day",
    date(2024, 3, 8): "Mahashivratri",
    date(2024, 3, 25): "Holi",
    date(2024, 3, 29): "Good Friday",
    date(2024, 4, 11): "Id-Ul-Fitr",
    date(2024, 4, 17): "Ram Navami",
    date(2024, 5, 1): "Maharashtra Day",
    date(2024, 5, 20): "General election (Mumbai)",
    date(2024, 6, 17): "Bakri Id",
    date(2024, 7, 17): "Muharram",
    date(2024, 8, 15): "Independence Day",
    date(2024, 10, 2): "Gandhi Jayanti",
    date(2024, 11, 1): "Diwali Laxmi Pujan",
    date(2024, 11, 15): "Guru Nanak Jayanti",
    date(2024, 11, 20): "Maharashtra assembly election",
    date(2024, 12, 25): "Christmas",
    # 2025
    date(2025, 2, 26): "Mahashivratri",
    date(2025, 3, 14): "Holi",
    date(2025, 3, 31): "Id-Ul-Fitr",
    date(2025, 4, 10): "Mahavir Jayanti",
    date(2025, 4, 14): "Dr Ambedkar Jayanti",
    date(2025, 4, 18): "Good Friday",
    date(2025, 5, 1): "Maharashtra Day",
    date(2025, 8, 15): "Independence Day",
    date(2025, 8, 27): "Ganesh Chaturthi",
    date(2025, 10, 2): "Gandhi Jayanti / Dussehra",
    date(2025, 10, 21): "Diwali Laxmi Pujan",
    date(2025, 10, 22): "Diwali Balipratipada",
    date(2025, 11, 5): "Guru Nanak Jayanti",
    date(2025, 12, 25): "Christmas",
}

# Scheduled macro events. The generator doubles volatility on these days; the engine's `event`
# regime and the `event_calendar` table can be seeded from the same dict.
EVENT_DAYS: dict[date, str] = {
    date(2024, 2, 8): "RBI MPC",
    date(2024, 4, 5): "RBI MPC",
    date(2024, 6, 7): "RBI MPC",
    date(2024, 7, 23): "Union Budget",
    date(2024, 8, 8): "RBI MPC",
    date(2024, 10, 9): "RBI MPC",
    date(2024, 12, 6): "RBI MPC",
    date(2025, 2, 1): "Union Budget",
    date(2025, 2, 7): "RBI MPC",
    date(2025, 4, 9): "RBI MPC",
    date(2025, 6, 6): "RBI MPC",
    date(2025, 8, 6): "RBI MPC",
    date(2025, 10, 1): "RBI MPC",
    date(2025, 12, 5): "RBI MPC",
}


def as_date(d: date | datetime | str) -> date:
    """Coerce a date, datetime or ISO string to a plain date."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return pd.Timestamp(d).date()


def is_trading_day(d: date | datetime | str) -> bool:
    d = as_date(d)
    return d.weekday() < 5 and d not in HOLIDAYS


def trading_days(start: date | datetime | str, end: date | datetime | str) -> list[date]:
    """All NSE trading days in [start, end] inclusive."""
    s, e = as_date(start), as_date(end)
    out: list[date] = []
    d = s
    while d <= e:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def session_index(day: date | datetime | str) -> pd.DatetimeIndex:
    """The 375 one-minute bar open times of one session: 09:15 .. 15:29 inclusive, tz-naive."""
    d = as_date(day)
    return pd.date_range(datetime.combine(d, SESSION_OPEN), periods=BARS_PER_DAY, freq="1min")


def is_market_open(ts: datetime | str) -> bool:
    """True when `ts` (tz-naive IST) falls inside a live session: 09:15 <= t < 15:30 on a trading day."""
    t = pd.Timestamp(ts)
    if not is_trading_day(t.date()):
        return False
    return SESSION_OPEN <= t.time() < SESSION_CLOSE
