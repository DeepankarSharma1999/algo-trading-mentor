"""DeskSummary (ARCHITECTURE section 4): top strip, watchers and their latest signal."""

from __future__ import annotations

from sqlalchemy.orm import Session

from engine.db import models as m
from engine.services import behaviour, clock, market, risk
from engine.services.common import get_profile, iso

SESSION_LABEL = "09:15–15:30 IST"


def watcher_dict(session: Session, w: m.Watcher, strategy: m.Strategy | None = None) -> dict:
    strategy = strategy or session.get(m.Strategy, w.strategy_id)
    latest = (
        session.query(m.Signal)
        .filter(m.Signal.watcher_id == w.id)
        .order_by(m.Signal.ts.desc(), m.Signal.id.desc())
        .first()
    )
    return {
        "id": w.id,
        "strategy_id": w.strategy_id,
        "name": strategy.name if strategy else w.strategy_id,
        "exec_state": w.exec_state,
        "state_reason": w.state_reason,
        "latest_signal": dict(latest.payload) if latest else None,
        "updated_at": iso(w.updated_at),
    }


def summary(session: Session, user_id: str) -> dict:
    p = get_profile(session, user_id)
    now = clock.now(session)
    watchers = session.query(m.Watcher).filter(m.Watcher.user_id == user_id).order_by(m.Watcher.updated_at).all()
    return {
        "risk": risk.status(session, user_id, now),
        "behaviour": behaviour.state_dict(p),
        "market": {"open": clock.market_open(now), "sim_now": iso(now), "session": SESSION_LABEL},
        "watchers": [watcher_dict(session, w) for w in watchers],
        "provider": market.provider().name,
    }
