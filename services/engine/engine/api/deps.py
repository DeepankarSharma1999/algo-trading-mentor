"""FastAPI dependencies: the caller's user id (X-User-Id) and a DB session per request."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Header
from sqlalchemy.orm import Session

from engine import db
from engine.services.common import ApiError


def user_id(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> str:
    if not x_user_id or not x_user_id.strip():
        raise ApiError(401, "The X-User-Id header is missing.")
    return x_user_id.strip()


def db_session() -> Iterator[Session]:
    with db.session() as s:
        yield s
