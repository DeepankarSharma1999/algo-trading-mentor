"""Small shared helpers: the API error type, timestamp formatting, row lookups."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from engine.db import models as m


class ApiError(Exception):
    """Raised by services; the API layer renders it as {"error": sentence} with `status`."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def iso(ts: Any) -> str | None:
    if ts is None:
        return None
    return pd.Timestamp(ts).isoformat()


def as_dt(ts: Any) -> datetime:
    return pd.Timestamp(ts).to_pydatetime()


def num(v: Any) -> float:
    return float(v) if isinstance(v, Decimal | int | float) else 0.0


def get_profile(session: Session, user_id: str) -> m.Profile:
    p = session.get(m.Profile, user_id)
    if p is None:
        raise ApiError(404, f"No profile exists for user {user_id}.")
    return p


def get_strategy(session: Session, strategy_id: str, user_id: str | None = None) -> m.Strategy:
    s = session.get(m.Strategy, strategy_id)
    if s is None or (user_id is not None and s.user_id not in (None, user_id)):
        raise ApiError(404, f"Strategy {strategy_id} was not found.")
    return s


def user_instruments(session: Session, user_id: str) -> set[str]:
    out: set[str] = set()
    for s in session.query(m.Strategy).filter(m.Strategy.user_id == user_id).all():
        out.update(str(x).upper() for x in (s.spec or {}).get("instruments", []))
    return out
