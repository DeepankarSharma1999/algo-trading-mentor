"""Risk status from profile + paper trades, and profile changes (ARCHITECTURE section 7)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from engine.db import models as m
from engine.risk.engine import PROFILES, RiskStatus, TradeRow, is_tightening, risk_status
from engine.services import clock
from engine.services.common import ApiError, get_profile, num


def trade_rows(session: Session, user_id: str) -> list[TradeRow]:
    rows = session.query(m.PaperTrade).filter(m.PaperTrade.user_id == user_id).all()
    return [
        TradeRow(t.outcome_r, t.closed_at, t.status, float((t.planned or {}).get("risk_r", 1.0) or 1.0))
        for t in rows
    ]


def status_obj(session: Session, user_id: str, now: datetime | None = None) -> RiskStatus:
    p = get_profile(session, user_id)
    profile = p.risk_profile if p.risk_profile in PROFILES else "conservative"
    return risk_status(num(p.trading_bucket), profile, trade_rows(session, user_id), now or clock.now(session))


def status(session: Session, user_id: str, now: datetime | None = None) -> dict:
    return status_obj(session, user_id, now).to_dict()


def set_profile(session: Session, user_id: str, to: str) -> dict:
    if to not in PROFILES:
        raise ApiError(400, f"Unknown risk profile {to!r}; choose conservative, standard or hard_ceiling.")
    p = get_profile(session, user_id)
    frm = p.risk_profile
    if frm == to:
        return {"ok": True}
    if not is_tightening(frm, to) and p.behaviour_state != "RESEARCH":
        raise ApiError(
            409,
            f"Loosening from {frm} to {to} is only allowed in RESEARCH; you are in {p.behaviour_state}. "
            "Tightening is allowed at any time.",
        )
    ts = clock.now(session)
    p.risk_profile = to
    verb = "Tightened" if is_tightening(frm, to) else "Loosened in RESEARCH"
    session.add(
        m.StateEvent(
            user_id=user_id,
            kind="profile_change",
            from_state=frm,
            to_state=to,
            reason=f"{verb} risk profile from {frm} to {to}.",
            ts=ts,
        )
    )
    session.flush()
    return {"ok": True}
