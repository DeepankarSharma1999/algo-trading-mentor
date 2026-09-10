"""GET /journal/{user_id}, POST /journal/notes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.api.deps import db_session, user_id
from engine.services import behaviour as behaviour_svc
from engine.services import journal as journal_svc
from engine.services.common import ApiError

router = APIRouter()


class NoteBody(BaseModel):
    text: str
    trade_id: str | None = None


@router.get("/journal/{user}")
def journal(user: str, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    if user != uid:
        raise ApiError(403, "You can only read your own journal.")
    rows = journal_svc.trades(s, uid)
    return {"trades": rows, "aggregates": journal_svc.aggregates(rows)}


@router.post("/journal/notes")
def add_note(body: NoteBody, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    return behaviour_svc.on_note(s, uid, body.text, body.trade_id)
