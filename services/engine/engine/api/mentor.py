"""POST /mentor/formalise | explain | review | coach. Every reply passes the section 0 guardrail inside
engine.mentor.service; allowed symbols come from the user's own context only."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.api.deps import db_session, user_id
from engine.behaviour.machine import lexicon_hits
from engine.db import models as m
from engine.mentor import service as mentor
from engine.services import journal as journal_svc
from engine.services import market
from engine.services.common import ApiError, user_instruments

router = APIRouter()
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9&]{1,19}")


class FormaliseBody(BaseModel):
    text: str


class ExplainBody(BaseModel):
    signal_id: str


class ReviewBody(BaseModel):
    job_id: str


class CoachBody(BaseModel):
    note_id: str | None = None
    text: str | None = None


def _known_symbols(s: Session, uid: str) -> set[str]:
    known = user_instruments(s, uid)
    try:
        known |= {x.upper() for x in market.provider().symbols()}
    except Exception:
        pass
    return known


@router.post("/mentor/formalise")
def formalise(body: FormaliseBody, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    if not body.text.strip():
        raise ApiError(400, "Write the hypothesis first; the mentor formalises text, it does not invent rules.")
    known = _known_symbols(s, uid)
    mentioned = {w.upper() for w in _WORD.findall(body.text)}
    allowed = known & mentioned
    out = mentor.formalise(body.text, allowed)
    return {"draft": out["draft"], "ambiguity_flags": list(out["ambiguity_flags"]), "prose": out["prose"]}


@router.post("/mentor/explain")
def explain(body: ExplainBody, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    sig = s.get(m.Signal, body.signal_id)
    if sig is None or sig.user_id != uid:
        raise ApiError(404, f"Signal {body.signal_id} was not found.")
    strat = s.get(m.Strategy, sig.strategy_id)
    allowed = {str(x).upper() for x in ((strat.spec or {}).get("instruments", []) if strat else [])}
    allowed.add(str(sig.payload.get("symbol", "")).upper())
    return {"prose": mentor.explain(dict(sig.payload), allowed)}


@router.post("/mentor/review")
def review(body: ReviewBody, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    job = s.get(m.ValidationJob, body.job_id)
    if job is None or job.user_id != uid:
        raise ApiError(404, f"Validation job {body.job_id} was not found.")
    if not job.report:
        raise ApiError(409, f"Validation job {body.job_id} has no report yet; it is {job.status}.")
    strat = s.get(m.Strategy, job.strategy_id)
    allowed = {str(x).upper() for x in ((strat.spec or {}).get("instruments", []) if strat else [])}
    out = mentor.review(dict(job.report), allowed)
    return {"prose": out["prose"], "weakest_stage": out["weakest_stage"], "next_step": out["next_step"]}


@router.post("/mentor/coach")
def coach(body: CoachBody, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    allowed = user_instruments(s, uid)
    trade = None
    if body.note_id:
        note = s.get(m.JournalNote, body.note_id)
        if note is None or note.user_id != uid:
            raise ApiError(404, f"Journal note {body.note_id} was not found.")
        text, hits = note.text, list(note.flags or [])
        if note.trade_id:
            t = s.get(m.PaperTrade, note.trade_id)
            trade = journal_svc.trade_dict(t) if t else None
    elif body.text and body.text.strip():
        text, hits = body.text, lexicon_hits(body.text)
    else:
        raise ApiError(400, "Send a note_id or some text for the mentor to read.")
    return {"prose": mentor.coach(text, hits, trade, allowed)}
