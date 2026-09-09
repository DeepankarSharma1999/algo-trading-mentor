"""SQLAlchemy mirror of apps/web/prisma/schema.prisma. Prisma owns migrations; keep column names identical."""

from __future__ import annotations

import secrets
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def cuid() -> str:
    return "c" + secrets.token_hex(12)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    safety_bucket: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    long_term_bucket: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    trading_bucket: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    risk_profile: Mapped[str] = mapped_column(String, default="conservative")
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    behaviour_state: Mapped[str] = mapped_column(String, default="RESEARCH")
    state_reason: Mapped[str] = mapped_column(String, default="Market closed.")
    state_changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    cost_overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    data_source: Mapped[str] = mapped_column(String, default="synthetic")
    theme: Mapped[str] = mapped_column(String, default="system")


class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="draft")
    spec: Mapped[dict] = mapped_column(JSON)
    plain_rules: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ValidationJob(Base):
    __tablename__ = "validation_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    user_id: Mapped[str] = mapped_column(String)
    strategy_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued")
    current_stage: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Watcher(Base):
    __tablename__ = "watchers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    user_id: Mapped[str] = mapped_column(String)
    strategy_id: Mapped[str] = mapped_column(String)
    exec_state: Mapped[str] = mapped_column(String, default="WATCHING")
    state_reason: Mapped[str] = mapped_column(String, default="")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    user_id: Mapped[str] = mapped_column(String)
    watcher_id: Mapped[str] = mapped_column(String)
    strategy_id: Mapped[str] = mapped_column(String)
    ts: Mapped[datetime] = mapped_column(DateTime)
    payload: Mapped[dict] = mapped_column(JSON)


class PaperTrade(Base):
    __tablename__ = "paper_trades"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    user_id: Mapped[str] = mapped_column(String)
    strategy_id: Mapped[str] = mapped_column(String)
    watcher_id: Mapped[str | None] = mapped_column(String, nullable=True)
    symbol: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String)
    qty: Mapped[int] = mapped_column(Integer)
    planned: Mapped[dict] = mapped_column(JSON)
    actual: Mapped[dict] = mapped_column(JSON)
    slippage: Mapped[float] = mapped_column(Float, default=0)
    costs: Mapped[float] = mapped_column(Float, default=0)
    mfe_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    mae_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    regime: Mapped[str] = mapped_column(String, default="range")
    outcome_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    rules_followed: Mapped[int] = mapped_column(Integer, default=0)
    rules_total: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="open")
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class JournalNote(Base):
    __tablename__ = "journal_notes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    user_id: Mapped[str] = mapped_column(String)
    trade_id: Mapped[str | None] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StateEvent(Base):
    __tablename__ = "state_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    user_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="behaviour")
    from_state: Mapped[str] = mapped_column(String)
    to_state: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OverrideAttempt(Base):
    __tablename__ = "override_attempts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    user_id: Mapped[str] = mapped_column(String)
    what: Mapped[str] = mapped_column(String)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GuardrailLog(Base):
    __tablename__ = "guardrail_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    endpoint: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    raw: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SimClock(Base):
    __tablename__ = "sim_clock"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    now: Mapped[datetime] = mapped_column(DateTime)
    speed: Mapped[int] = mapped_column(Integer, default=2)
    running: Mapped[bool] = mapped_column(Boolean, default=True)


class EventCalendar(Base):
    __tablename__ = "event_calendar"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=cuid)
    date: Mapped[date] = mapped_column(Date)
    label: Mapped[str] = mapped_column(String)
