"""GET /desk/{user_id}, POST /watchers, DELETE /watchers/{id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.api.deps import db_session, user_id
from engine.db import models as m
from engine.services import clock
from engine.services import desk as desk_svc
from engine.services.common import ApiError, get_strategy

router = APIRouter()


class WatcherBody(BaseModel):
    strategy_id: str


@router.get("/desk/{user}")
def desk(user: str, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    if user != uid:
        raise ApiError(403, "You can only read your own desk.")
    return desk_svc.summary(s, uid)


@router.post("/watchers")
def create_watcher(body: WatcherBody, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    strat = get_strategy(s, body.strategy_id, uid)
    if strat.user_id != uid:
        raise ApiError(409, "Templates cannot be watched; clone the template into your own strategies first.")
    if strat.status != "validated":
        raise ApiError(409, f"Strategy {strat.id} is {strat.status}; only a validated strategy can be watched in paper mode.")
    if (strat.spec or {}).get("automation_permission") != "paper_only":
        raise ApiError(409, f"Strategy {strat.id} has automation permission {(strat.spec or {}).get('automation_permission')}; only paper_only strategies can be watched.")
    existing = s.query(m.Watcher).filter(m.Watcher.user_id == uid, m.Watcher.strategy_id == strat.id).first()
    if existing is not None:
        return desk_svc.watcher_dict(s, existing, strat)
    w = m.Watcher(user_id=uid, strategy_id=strat.id, exec_state="WATCHING", state_reason="Watching for the next closed bar.", context={}, updated_at=clock.now(s))
    s.add(w)
    s.flush()
    return desk_svc.watcher_dict(s, w, strat)


@router.delete("/watchers/{watcher_id}")
def delete_watcher(watcher_id: str, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    w = s.get(m.Watcher, watcher_id)
    if w is None or w.user_id != uid:
        raise ApiError(404, f"Watcher {watcher_id} was not found.")
    s.delete(w)
    s.flush()
    return {"ok": True}
