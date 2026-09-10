"""Shared test plumbing for the service layer: an in-memory SQLite database that replaces the engine's
session factory, a fake market data provider serving conftest.make_bars, and seed rows."""

from __future__ import annotations

import copy
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from engine import db
from engine.data.provider import MarketDataProvider, slice_bars
from engine.data.resample import resample_bars
from engine.db import models as m
from engine.services import market
from tests.conftest import ema_cross_spec, make_bars

USER_ID = "user_test_1"
STRATEGY_ID = "ema_cross_v1"


class FakeProvider(MarketDataProvider):
    name = "synthetic"

    def __init__(self, bars_1m: pd.DataFrame, symbols: tuple[str, ...] = ("RELIANCE", "NIFTY")):
        self._bars = bars_1m.reset_index(drop=True)
        self._symbols = sorted(symbols)
        self.calls = 0

    def symbols(self) -> list[str]:
        return list(self._symbols)

    def get_bars(self, symbol: str, timeframe: str = "1m", start=None, end=None) -> pd.DataFrame:
        if symbol not in self._symbols:
            raise FileNotFoundError(f"no data for {symbol}")
        self.calls += 1
        return resample_bars(slice_bars(self._bars, start, end), timeframe)

    def get_option_chain(self, underlying, expiry, asof):
        raise NotImplementedError


def one_minute_bars(days: int = 12, start: str = "2025-06-02 09:15", seed: int = 3) -> pd.DataFrame:
    """Random-walk 1-minute bars with a slow wave so an EMA cross has trends to catch."""
    return make_bars(375 * days, seed=seed, start=start, freq="1min", vol=0.0006, wave_period=900, wave_amp=0.02)


def install_db(monkeypatch) -> sessionmaker:
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    m.Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, expire_on_commit=False)
    monkeypatch.setattr(db, "engine", eng)
    monkeypatch.setattr(db, "SessionLocal", factory)
    return factory


def install_provider(monkeypatch, bars_1m: pd.DataFrame | None = None) -> FakeProvider:
    prov = FakeProvider(bars_1m if bars_1m is not None else one_minute_bars())
    market.set_provider(prov)
    monkeypatch.setattr(market, "_provider", prov)
    return prov


def seed(
    factory: sessionmaker,
    *,
    sim_now: datetime = datetime(2025, 6, 12, 10, 35),
    behaviour_state: str = "CALM",
    risk_profile: str = "standard",
    strategy_status: str = "validated",
    spec: dict | None = None,
    watcher: bool = False,
) -> dict:
    spec = copy.deepcopy(spec or ema_cross_spec(instruments=["RELIANCE"], market="NSE_EQ"))
    with factory() as s:
        s.add(m.User(id=USER_ID, email="t@atm.local", password_hash="x"))
        s.add(
            m.Profile(
                user_id=USER_ID,
                safety_bucket=500000,
                long_term_bucket=1500000,
                trading_bucket=400000,
                risk_profile=risk_profile,
                onboarded_at=datetime(2025, 1, 1),
                behaviour_state=behaviour_state,
                state_reason="Session open. No brakes reached." if behaviour_state == "CALM" else "seeded",
                state_changed_at=sim_now,
            )
        )
        s.add(
            m.Strategy(
                id=spec["strategy_id"],
                user_id=USER_ID,
                name=spec["name"],
                slug=spec["strategy_id"].rsplit("_v", 1)[0],
                version=1,
                status=strategy_status,
                spec=spec,
            )
        )
        s.add(m.SimClock(id=1, now=sim_now, speed=2, running=True))
        out = {"user_id": USER_ID, "strategy_id": spec["strategy_id"]}
        if watcher:
            w = m.Watcher(user_id=USER_ID, strategy_id=spec["strategy_id"], exec_state="WATCHING", state_reason="", context={}, updated_at=sim_now)
            s.add(w)
            s.flush()
            out["watcher_id"] = w.id
        s.commit()
    return out
