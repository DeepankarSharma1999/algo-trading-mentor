"""The simulated clock (ARCHITECTURE section 6). One `sim_clock` row; time is tz-naive IST wall time.

`advance` only ever lands on session moments: 09:15 .. 15:30 on a trading day. 15:30 is the moment
the last bar closes (the market is closed at that instant); the next step jumps to the following
trading day's 09:15. Past the end of the synthetic data the clock wraps to 2025-01-01 09:15.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from engine.data.calendar import DATA_END, SESSION_CLOSE, SESSION_OPEN, is_market_open, is_trading_day
from engine.db import models as m

DEFAULT_START = datetime(2025, 6, 12, 10, 35)
WRAP_TO = datetime(2025, 1, 1, 9, 15)


def _next_trading_day(d: date) -> date:
    d = d + timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def previous_trading_day(d: date) -> date:
    d = d - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def session_open(d: date) -> datetime:
    return datetime.combine(d, SESSION_OPEN)


def session_close(d: date) -> datetime:
    return datetime.combine(d, SESSION_CLOSE)


def next_open_after(ts: datetime) -> datetime:
    nxt = _next_trading_day(ts.date())
    if nxt > DATA_END:
        return WRAP_TO
    return session_open(nxt)


def step_one(ts: datetime) -> datetime:
    """The next session moment strictly after `ts`."""
    ts = ts.replace(second=0, microsecond=0)
    if is_trading_day(ts.date()):
        if ts < session_open(ts.date()):
            return session_open(ts.date())
        if ts < session_close(ts.date()):
            return ts + timedelta(minutes=1)
    return next_open_after(ts)


def market_open(ts: datetime | str) -> bool:
    return is_market_open(ts)


def get(session: Session) -> m.SimClock:
    row = session.get(m.SimClock, 1)
    if row is None:
        row = m.SimClock(id=1, now=DEFAULT_START, speed=2, running=True)
        session.add(row)
        session.flush()
    return row


def now(session: Session) -> datetime:
    return get(session).now


def to_dict(row: m.SimClock) -> dict[str, Any]:
    return {
        "now": pd.Timestamp(row.now).isoformat(),
        "speed": int(row.speed),
        "running": bool(row.running),
        "market_open": market_open(row.now),
    }


def set(session: Session, speed: int | None = None, running: bool | None = None, jump_to: Any = None) -> dict:  # noqa: A001
    row = get(session)
    if speed is not None:
        row.speed = max(1, min(int(speed), 375))
    if running is not None:
        row.running = bool(running)
    if jump_to is not None:
        ts = pd.Timestamp(jump_to)
        if ts.tzinfo is not None:
            ts = ts.tz_convert(None)
        row.now = ts.to_pydatetime().replace(second=0, microsecond=0)
    session.flush()
    return to_dict(row)


def advance(session: Session, minutes: int = 1) -> datetime:
    row = get(session)
    ts = row.now
    for _ in range(max(0, int(minutes))):
        ts = step_one(ts)
    row.now = ts
    session.flush()
    return ts
