"""Behavioural state persistence (ARCHITECTURE section 8). Decisions come from engine.behaviour.machine."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from engine.behaviour import machine
from engine.db import models as m
from engine.services import clock
from engine.services.common import ApiError, get_profile, iso


def state_dict(p: m.Profile) -> dict:
    return {"state": p.behaviour_state, "reason": p.state_reason, "since": iso(p.state_changed_at)}


def transition(
    session: Session, user_id: str, decision: machine.Decision, kind: str = "behaviour", now: datetime | None = None
) -> m.Profile:
    p = get_profile(session, user_id)
    if decision.changed and decision.to != p.behaviour_state:
        ts = now or clock.now(session)
        session.add(
            m.StateEvent(
                user_id=user_id, kind=kind, from_state=p.behaviour_state, to_state=decision.to, reason=decision.reason, ts=ts
            )
        )
        p.behaviour_state = decision.to
        p.state_reason = decision.reason
        p.state_changed_at = ts
    elif decision.reason:
        p.state_reason = decision.reason
    session.flush()
    return p


def on_override(session: Session, user_id: str, what: str) -> dict:
    p = get_profile(session, user_id)
    now = clock.now(session)
    session.add(m.OverrideAttempt(user_id=user_id, what=what, ts=now))
    session.flush()
    since = clock.session_open(now.date())
    n = (
        session.query(m.OverrideAttempt)
        .filter(m.OverrideAttempt.user_id == user_id, m.OverrideAttempt.ts >= since, m.OverrideAttempt.ts <= now)
        .count()
    )
    d = machine.on_override_attempt(p.behaviour_state, n)
    p = transition(session, user_id, d, now=now)
    return {"state": p.behaviour_state, "reason": d.reason, "attempts_this_session": n}


def on_note(session: Session, user_id: str, text: str, trade_id: str | None = None) -> dict:
    if not text or not text.strip():
        raise ApiError(400, "The note is empty.")
    p = get_profile(session, user_id)
    now = clock.now(session)
    if trade_id is not None:
        t = session.get(m.PaperTrade, trade_id)
        if t is None or t.user_id != user_id:
            raise ApiError(404, f"Paper trade {trade_id} was not found.")
    d, hits = machine.on_journal_text(p.behaviour_state, text)
    note = m.JournalNote(user_id=user_id, trade_id=trade_id, text=text.strip(), flags=list(hits), created_at=now)
    session.add(note)
    p = transition(session, user_id, d, now=now)
    session.flush()
    return {
        "note": {
            "id": note.id,
            "trade_id": note.trade_id,
            "text": note.text,
            "flags": list(hits),
            "created_at": iso(note.created_at),
        },
        "state": state_dict(p) | {"reason": d.reason},
    }


def on_daily_brake(session: Session, user_id: str, now: datetime | None = None) -> m.Profile:
    p = get_profile(session, user_id)
    return transition(session, user_id, machine.on_daily_brake(p.behaviour_state), now=now)


def on_rule_breach(session: Session, user_id: str, what: str, now: datetime | None = None) -> m.Profile:
    p = get_profile(session, user_id)
    return transition(session, user_id, machine.on_rule_breach(p.behaviour_state, what), now=now)


def on_close(session: Session, user_id: str, now: datetime) -> m.Profile:
    p = get_profile(session, user_id)
    return transition(session, user_id, machine.on_market_close(p.behaviour_state), now=now)


def cooldown_pending(session: Session, user_id: str, now: datetime) -> bool:
    """True when the most recent behavioural move into COOLDOWN happened on the previous trading day
    (and was not itself a carry-over), so the new session must start in COOLDOWN."""
    ev = (
        session.query(m.StateEvent)
        .filter(
            m.StateEvent.user_id == user_id,
            m.StateEvent.kind == "behaviour",
            m.StateEvent.to_state == "COOLDOWN",
            m.StateEvent.ts < now,
        )
        .order_by(m.StateEvent.ts.desc())
        .first()
    )
    if ev is None or ev.reason.startswith("Cooldown carried"):
        return False
    return ev.ts.date() == clock.previous_trading_day(now.date())


def on_open(session: Session, user_id: str, now: datetime) -> m.Profile:
    p = get_profile(session, user_id)
    pending = cooldown_pending(session, user_id, now)
    return transition(session, user_id, machine.on_market_open(p.behaviour_state, pending), now=now)


def onboarded_user_ids(session: Session) -> list[str]:
    return [p.user_id for p in session.query(m.Profile).filter(m.Profile.onboarded_at.isnot(None)).all()]
