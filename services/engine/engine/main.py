"""FastAPI entrypoint (ARCHITECTURE section 4). Errors are `{"error": "<plain sentence>"}` with a 4xx."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from engine import config, db
from engine.api import ROUTERS
from engine.db import models as m
from engine.mentor import service as mentor
from engine.services import clock, market
from engine.services.common import ApiError, iso

log = logging.getLogger("engine")


def _guardrail_sink(endpoint: str, reason: str, raw: str) -> None:
    try:
        with db.session() as s:
            s.add(m.GuardrailLog(endpoint=endpoint, reason=reason, raw=raw[:4000]))
    except Exception:  # never let logging break a mentor reply
        log.exception("could not write guardrail_log")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    mentor.set_rejection_sink(_guardrail_sink)
    yield


app = FastAPI(title="Algo Trading Mentor engine", version="0.2.0", lifespan=lifespan)
for r in ROUTERS:
    app.include_router(r)


@app.exception_handler(ApiError)
async def api_error(_req: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status)


@app.exception_handler(HTTPException)
async def http_error(_req: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "The request could not be handled."
    return JSONResponse({"error": detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_req: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", ()) if x != "body")
    msg = first.get("msg", "invalid request")
    return JSONResponse({"error": f"Request field {loc or 'body'}: {msg}."}, status_code=422)


@app.get("/health")
def health() -> dict:
    sim_now = None
    try:
        with db.session() as s:
            sim_now = iso(clock.now(s))
    except Exception as e:
        log.warning("health: database unavailable: %s", e)
    try:
        provider = market.provider().name
    except Exception:
        provider = config.DATA_PROVIDER
    return {"ok": True, "provider": provider, "sim_now": sim_now}
