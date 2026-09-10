"""POST /risk/profile, GET /risk/{user_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.api.deps import db_session, user_id
from engine.services import risk as risk_svc
from engine.services.common import ApiError

router = APIRouter()


class ProfileBody(BaseModel):
    profile: str


@router.post("/risk/profile")
def set_profile(body: ProfileBody, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    return risk_svc.set_profile(s, uid, body.profile)


@router.get("/risk/{user}")
def get_risk(user: str, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    if user != uid:
        raise ApiError(403, "You can only read your own risk status.")
    return risk_svc.status(s, uid)
