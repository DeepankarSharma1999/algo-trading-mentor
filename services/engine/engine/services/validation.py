"""Validation jobs (ARCHITECTURE section 5): a `validation_jobs` row plus a background thread that runs
the eight-stage pipeline and writes stage progress to the row after every stage."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from engine import db
from engine.backtest import auto_segment
from engine.costs import CostParams
from engine.data import lot_size
from engine.db import models as m
from engine.risk.engine import PROFILES
from engine.risk.engine import one_r as risk_one_r
from engine.rules.engine import as_strategy
from engine.services import market
from engine.services.common import ApiError, get_strategy, iso, num
from engine.validation.pipeline import STAGE_NAMES, StageResult, ValidationReport, run_pipeline

log = logging.getLogger("validation")
MAX_DD_PCT = {"conservative": 10.0, "standard": 15.0, "hard_ceiling": 20.0}
FALLBACK_ONE_R = 2000.0
PAPER_MIN_TRADES = 30

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="validate")
_inflight: set[str] = set()
_lock = threading.Lock()


def job_dict(j: m.ValidationJob) -> dict:
    return {
        "id": j.id,
        "status": j.status,
        "current_stage": int(j.current_stage or 0),
        "report": j.report,
        "error": j.error,
        "strategy_id": j.strategy_id,
        "created_at": iso(j.created_at),
        "finished_at": iso(j.finished_at),
    }


def get_job(session: Session, job_id: str) -> dict:
    j = session.get(m.ValidationJob, job_id)
    if j is None:
        raise ApiError(404, f"Validation job {job_id} was not found.")
    return job_dict(j)


def cost_params_for(profile: m.Profile | None) -> CostParams:
    ov = dict((profile.cost_overrides or {}) if profile else {})
    fields = {k: float(v) for k, v in ov.items() if k in CostParams.__dataclass_fields__ and isinstance(v, int | float)}
    return CostParams(**fields) if fields else CostParams()


def paper_stats_for(session: Session, strategy_id: str, user_id: str) -> dict[str, Any] | None:
    rows = (
        session.query(m.PaperTrade)
        .filter(
            m.PaperTrade.strategy_id == strategy_id,
            m.PaperTrade.user_id == user_id,
            m.PaperTrade.status == "closed",
            m.PaperTrade.outcome_r.isnot(None),
        )
        .all()
    )
    if len(rows) < PAPER_MIN_TRADES:
        return {"trades": len(rows)} if rows else None
    r = np.array([t.outcome_r for t in rows], dtype=float)
    return {"trades": int(len(r)), "expectancy_r": float(r.mean()), "win_rate": float((r > 0).mean())}


def start_job(user_id: str, strategy_id: str) -> str:
    with db.session() as s:
        strat = get_strategy(s, strategy_id, user_id)
        try:
            as_strategy(strat.spec)
        except Exception as e:
            raise ApiError(400, f"Strategy {strategy_id} does not validate against the schema: {e}") from e
        job = m.ValidationJob(user_id=user_id, strategy_id=strategy_id, status="queued", current_stage=0)
        s.add(job)
        s.flush()
        job_id = job.id
    with _lock:
        _inflight.add(job_id)
    _executor.submit(_run_job, job_id)
    return job_id


def run_job_sync(job_id: str) -> None:
    """Runs the job on the calling thread (tests, CLI)."""
    _run_job(job_id)


def _write(job_id: str, **fields: Any) -> None:
    with db.session() as s:
        j = s.get(m.ValidationJob, job_id)
        if j is None:
            return
        for k, v in fields.items():
            setattr(j, k, v)


def _run_job(job_id: str) -> None:
    try:
        _write(job_id, status="running")
        with db.session() as s:
            j = s.get(m.ValidationJob, job_id)
            assert j is not None
            strat = s.get(m.Strategy, j.strategy_id)
            if strat is None:
                raise ApiError(404, f"Strategy {j.strategy_id} was not found.")
            spec = as_strategy(strat.spec)
            profile = s.get(m.Profile, j.user_id)
            user_id, strategy_id = j.user_id, j.strategy_id
            paper = paper_stats_for(s, strategy_id, user_id)
            one_r = FALLBACK_ONE_R
            max_dd = MAX_DD_PCT["hard_ceiling"]
            if profile is not None and profile.risk_profile in PROFILES and num(profile.trading_bucket) > 0:
                one_r = risk_one_r(num(profile.trading_bucket), profile.risk_profile)
                max_dd = MAX_DD_PCT[profile.risk_profile]
            cost_params = cost_params_for(profile)
        prov = market.provider()
        tf = str(spec.timeframe)
        bars = {inst.root: prov.get_bars(inst.root, tf) for inst in spec.instruments}
        stages = [StageResult(stage=i, name=STAGE_NAMES[i]) for i in range(1, 9)]
        started = datetime.now(UTC).isoformat()

        def on_stage(res: StageResult) -> None:
            stages[res.stage - 1] = res
            partial = ValidationReport(strategy_id=spec.strategy_id, started_at=started, stages=stages)
            _write(job_id, current_stage=res.stage, report=partial.model_dump(mode="json"))

        report = run_pipeline(
            spec,
            bars,
            one_r=one_r,
            max_dd_pct=max_dd,
            cost_params=cost_params,
            paper_stats=paper,
            on_stage=on_stage,
            lot_size=lot_size(spec.instruments[0].root, str(spec.market)) if spec.instruments else 1,
            segment=auto_segment(spec),
        )
        with db.session() as s:
            j = s.get(m.ValidationJob, job_id)
            if j is not None:
                j.status = "done"
                j.report = report.model_dump(mode="json")
                j.current_stage = max((st.stage for st in report.stages if st.status != "pending"), default=0)
                j.finished_at = datetime.utcnow()
            strat = s.get(m.Strategy, strategy_id)
            if strat is not None:
                strat.status = "validated" if report.passed else "untested"
    except Exception as e:
        log.exception("validation job %s failed", job_id)
        try:
            _write(job_id, status="failed", error=f"{type(e).__name__}: {e}"[:1000], finished_at=datetime.utcnow())
        except Exception:
            log.exception("could not record failure for job %s", job_id)
    finally:
        with _lock:
            _inflight.discard(job_id)


def default_range(prov: Any, symbol: str, months: int = 6) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[end - months, end] where end is the last bar the provider has for `symbol`."""
    tail = prov.get_bars(symbol, "1D")
    end = pd.Timestamp(tail["ts"].iloc[-1]).normalize() + pd.Timedelta(days=1)
    return end - pd.DateOffset(months=months), end
