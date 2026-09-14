"""POST /strategies/check, POST /backtest, POST /validate, GET /jobs/{id}."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.api.deps import db_session, user_id
from engine.db import models as m
from engine.risk.engine import PROFILES
from engine.risk.engine import one_r as risk_one_r
from engine.services import strategies as strategies_svc
from engine.services import validation as validation_svc
from engine.services.common import num

router = APIRouter()


class CheckBody(BaseModel):
    spec: dict[str, Any]


class BacktestBody(BaseModel):
    spec: dict[str, Any]
    start: str | None = None
    end: str | None = None
    cost_multiplier: float = Field(default=1.0, ge=0.0, le=10.0)
    window: str | None = None  # "in_sample": first 70% of the feed only; the OOS window stays locked


class ValidateBody(BaseModel):
    strategy_id: str


@router.post("/strategies/check")
def strategies_check(body: CheckBody, _uid: str = Depends(user_id)) -> dict:
    return strategies_svc.check(body.spec)


@router.post("/backtest")
def backtest(body: BacktestBody, uid: str = Depends(user_id), s: Session = Depends(db_session)) -> dict:
    one_r = validation_svc.FALLBACK_ONE_R
    p = s.get(m.Profile, uid)
    if p is not None and p.risk_profile in PROFILES and num(p.trading_bucket) > 0:
        one_r = risk_one_r(num(p.trading_bucket), p.risk_profile)
    return strategies_svc.backtest(
        body.spec, body.start, body.end, body.cost_multiplier, one_r=one_r, cost_params=validation_svc.cost_params_for(p),
        window=body.window,
    )


@router.post("/validate")
def validate(body: ValidateBody, uid: str = Depends(user_id)) -> dict:
    return {"job_id": validation_svc.start_job(uid, body.strategy_id)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, s: Session = Depends(db_session)) -> dict:
    return validation_svc.get_job(s, job_id)
