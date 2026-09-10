"""GET/POST /sim/clock and POST /paper/step."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.api.deps import db_session, user_id
from engine.paper import simulator
from engine.services import clock

router = APIRouter()


class ClockBody(BaseModel):
    speed: int | None = Field(default=None, ge=1, le=375)
    running: bool | None = None
    jump_to: str | None = None


class StepBody(BaseModel):
    bars: int = Field(default=1, ge=1, le=5000)


@router.get("/sim/clock")
def get_clock(s: Session = Depends(db_session)) -> dict:
    return clock.to_dict(clock.get(s))


@router.post("/sim/clock")
def set_clock(body: ClockBody, _uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    return clock.set(s, speed=body.speed, running=body.running, jump_to=body.jump_to)


@router.post("/paper/step")
def paper_step(body: StepBody, _uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    return simulator.step(s, body.bars)
