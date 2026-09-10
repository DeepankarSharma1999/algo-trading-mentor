"""POST /behaviour/override."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.api.deps import db_session, user_id
from engine.services import behaviour as behaviour_svc

router = APIRouter()


class OverrideBody(BaseModel):
    what: str


@router.post("/behaviour/override")
def override(body: OverrideBody, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    return behaviour_svc.on_override(s, uid, body.what)
