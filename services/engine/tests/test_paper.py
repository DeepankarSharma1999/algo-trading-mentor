"""Paper trader on the in-memory database: an EMA-cross watcher replayed over synthetic 1-minute bars."""

from __future__ import annotations

from datetime import datetime

import pytest

from engine import db
from engine.db import models as m
from engine.exec import TERMINAL, TRANSITIONS, ExecState
from engine.mentor.guardrail import guardrail
from engine.paper import simulator
from engine.services import clock
from tests import harness
from tests.conftest import ema_cross_spec

SPEC = ema_cross_spec(instruments=["RELIANCE"], market="NSE_EQ")


@pytest.fixture(autouse=True)
def strict(monkeypatch):
    monkeypatch.setattr(simulator, "STRICT", True)
    yield
    harness.market.set_provider(None)


def _run(monkeypatch, *, sim_now: datetime, steps: int, **seed_kw) -> dict:
    factory = harness.install_db(monkeypatch)
    harness.install_provider(monkeypatch, harness.make_bars(375 * 12, seed=5, start="2025-06-02 09:15", freq="1min", vol=0.0012, wave_period=500, wave_amp=0.02))
    info = harness.seed(factory, sim_now=sim_now, spec=SPEC, watcher=True, **seed_kw)
    with db.session() as s:
        res = simulator.step(s, steps)
    return info | {"result": res}


def _signals(watcher_id: str) -> list[dict]:
    with db.session() as s:
        rows = s.query(m.Signal).filter(m.Signal.watcher_id == watcher_id).order_by(m.Signal.ts, m.Signal.id).all()
        return [dict(r.payload) | {"_ts": r.ts} for r in rows]


def _assert_legal(seq: list[str]) -> None:
    prev = ExecState.WATCHING
    for raw in seq:
        cur = ExecState(raw)
        if prev in TERMINAL:
            assert cur is ExecState.WATCHING or cur in TRANSITIONS[ExecState.WATCHING], f"{prev} -> {cur} after a terminal state"
        else:
            assert cur in TRANSITIONS[prev], f"illegal {prev} -> {cur}"
        prev = cur


def test_simulator_trades_the_watcher_and_journals_everything(monkeypatch):
    info = _run(monkeypatch, sim_now=datetime(2025, 6, 9, 9, 14), steps=376 * 4)  # four sessions, each 09:15 .. 15:30
    assert info["result"]["sim_now"] == "2025-06-12T15:30:00"
    sigs = _signals(info["watcher_id"])
    assert len(sigs) >= 1
    states = [s["exec_state"] for s in sigs]
    _assert_legal(states)
    assert "OPEN" in states and "CLOSED" in states
    keys = {"id", "strategy_id", "version", "timestamp", "symbol", "regime", "side", "conditions_passed", "conditions_failed", "trigger", "stop",
            "targets", "quantity", "rupee_risk", "portfolio_risk_pct", "estimated_costs", "post_cost_rr", "automation_permission",
            "ambiguity_flags", "gates", "exec_state", "verdict", "sentence"}
    for s in sigs:
        assert set(s) - {"_ts"} == keys, set(s) ^ keys
        assert s["id"] and guardrail(s["sentence"], {"RELIANCE"}).ok, s["sentence"]
        assert [g["name"] for g in s["gates"]][:4] == ["All entry conditions", "Regime matches affinity", "Post-cost R:R >= 0", "Session window"]
        assert all(("reason" in g) == (not g["pass"]) for g in s["gates"])
    with db.session() as s:
        trades = s.query(m.PaperTrade).filter(m.PaperTrade.status == "closed").all()
        assert trades, "expected at least one closed paper trade"
        for t in trades:
            assert t.outcome_r is not None and t.costs > 0 and t.slippage > 0
            assert t.actual["entry"] and t.actual["exit"] and t.actual["entry_ts"] < t.actual["exit_ts"]
            assert t.planned["stop"] and t.planned["targets"] and t.planned["risk_r"] <= 1.0001
            assert t.mfe_r is not None and t.mae_r is not None and t.exit_reason in ("stop", "trailing_stop", "target", "flat_at_close", "max_bars", "time_exit")
            assert t.rules_followed == t.rules_total == 4  # one entry condition + stop, target, session
            assert t.regime in ("trend", "range", "compression", "high_vol", "event")
        assert s.query(m.PaperTrade).filter(m.PaperTrade.status == "open").count() == 0  # flat_at_close each day
        w = s.get(m.Watcher, info["watcher_id"])
        assert w.exec_state in [x.value for x in ExecState] and w.context.get("last_evaluated_ts")
        assert clock.now(s) == datetime(2025, 6, 12, 15, 30)
        # behaviour: RESEARCH at every close, CALM at every open
        ev = [(e.from_state, e.to_state, e.ts.time().strftime("%H:%M")) for e in s.query(m.StateEvent).order_by(m.StateEvent.ts).all()]
        assert ("CALM", "RESEARCH", "15:30") in ev and ("RESEARCH", "CALM", "09:15") in ev
    # a watcher is evaluated once per closed bar of its timeframe: no two signals share a bar and a state
    seen = {(s["timestamp"], s["exec_state"]) for s in sigs}
    assert len(seen) == len(sigs)


def test_no_entry_while_cooldown_and_cooldown_clears_at_next_open(monkeypatch):
    factory = harness.install_db(monkeypatch)
    harness.install_provider(monkeypatch, harness.make_bars(375 * 12, seed=5, start="2025-06-02 09:15", freq="1min", vol=0.0012, wave_period=500, wave_amp=0.02))
    info = harness.seed(factory, sim_now=datetime(2025, 6, 9, 9, 14), spec=SPEC, watcher=True, behaviour_state="RESEARCH")
    with db.session() as s:  # a cooldown set on the previous trading day (Friday 6 June) carries into Monday
        s.add(m.StateEvent(user_id=harness.USER_ID, kind="behaviour", from_state="CALM", to_state="COOLDOWN", reason="Daily loss brake reached.", ts=datetime(2025, 6, 6, 14, 0)))
    with db.session() as s:
        simulator.step(s, 376)  # Monday 09:15 .. 15:30
        assert s.get(m.Profile, harness.USER_ID).behaviour_state == "RESEARCH"
        opened = s.query(m.StateEvent).filter(m.StateEvent.to_state == "COOLDOWN", m.StateEvent.ts == datetime(2025, 6, 9, 9, 15)).one()
        assert opened.reason.startswith("Cooldown carried")
    sigs = _signals(info["watcher_id"])
    monday = [s for s in sigs if s["_ts"].date() == datetime(2025, 6, 9).date()]
    assert monday, "expected setups on Monday"
    assert all(s["exec_state"] not in ("ARMED", "ORDER_PENDING", "OPEN") for s in monday)
    blocked = [s for s in monday if s["exec_state"] == "BLOCKED"]
    assert blocked and all(not next(g for g in s["gates"] if g["name"] == "Behavioural state allows entries")["pass"] for s in blocked)
    with db.session() as s:
        assert s.query(m.PaperTrade).count() == 0
        simulator.step(s, 1)  # Tuesday 09:15: cooldown served, CALM again
        assert s.get(m.Profile, harness.USER_ID).behaviour_state == "CALM"
        simulator.step(s, 375)
        assert s.query(m.Signal).filter(m.Signal.payload["exec_state"].as_string() == "OPEN").count() >= 1


def test_daily_brake_blocks_entries_and_moves_to_cooldown(monkeypatch):
    factory = harness.install_db(monkeypatch)
    harness.install_provider(monkeypatch, harness.make_bars(375 * 12, seed=5, start="2025-06-02 09:15", freq="1min", vol=0.0012, wave_period=500, wave_amp=0.02))
    info = harness.seed(factory, sim_now=datetime(2025, 6, 9, 9, 14), spec=SPEC, watcher=True, risk_profile="conservative")
    with db.session() as s:  # 2R lost already today against the conservative 1.5R daily limit
        for k, r in enumerate([-1.2, -0.8]):
            s.add(
                m.PaperTrade(
                    user_id=harness.USER_ID, strategy_id=harness.STRATEGY_ID, symbol="RELIANCE", side="long", qty=10,
                    planned={"entry": 100, "stop": 99, "targets": [102], "risk_r": 1}, actual={"entry": 100, "exit": 99, "entry_ts": None, "exit_ts": None},
                    exit_reason="stop", regime="trend", outcome_r=r, rules_followed=4, rules_total=4, status="closed",
                    opened_at=datetime(2025, 6, 9, 9, 15 + k), closed_at=datetime(2025, 6, 9, 9, 16 + k),
                )
            )
    with db.session() as s:
        simulator.step(s, 376)
    sigs = [x for x in _signals(info["watcher_id"]) if x["_ts"].date() == datetime(2025, 6, 9).date()]
    assert sigs and all(x["exec_state"] not in ("ARMED", "ORDER_PENDING", "OPEN") for x in sigs)
    blocked = [x for x in sigs if x["exec_state"] == "BLOCKED"]
    assert blocked
    for x in blocked:
        daily = next(g for g in x["gates"] if g["name"] == "Daily risk brake")
        assert daily["pass"] is False and "brake" in daily["reason"]
        assert x["verdict"] == "blocked" and x["sentence"].startswith("Setup matches, but this trade is blocked:")
    with db.session() as s:
        assert s.query(m.PaperTrade).filter(m.PaperTrade.opened_at > datetime(2025, 6, 9, 9, 20)).count() == 0


def test_daily_brake_after_a_losing_paper_trade_triggers_cooldown(monkeypatch):
    """A tiny trading bucket makes every trade risk ~1R against a 1.5R daily limit, so the second loss
    on a day must trip the brake and move the user to COOLDOWN for the rest of that session."""
    factory = harness.install_db(monkeypatch)
    harness.install_provider(monkeypatch, harness.make_bars(375 * 12, seed=5, start="2025-06-02 09:15", freq="1min", vol=0.0012, wave_period=500, wave_amp=0.02))
    info = harness.seed(factory, sim_now=datetime(2025, 6, 9, 9, 14), spec=SPEC, watcher=True, risk_profile="conservative")
    with db.session() as s:
        simulator.step(s, 376 * 4)
        trades = s.query(m.PaperTrade).order_by(m.PaperTrade.closed_at).all()
        assert trades
        events = s.query(m.StateEvent).filter(m.StateEvent.to_state == "COOLDOWN").all()
        by_day: dict = {}
        for t in trades:
            by_day.setdefault(t.closed_at.date(), []).append(t)
        tripped = [d for d, rows in by_day.items() if sum(max(0.0, -(t.outcome_r or 0)) for t in rows) >= 1.5]
        assert {e.ts.date() for e in events} >= set(tripped)
        for d in tripped:
            brake_ts = min(t.closed_at for t in by_day[d] if sum(max(0.0, -(x.outcome_r or 0)) for x in by_day[d] if x.closed_at <= t.closed_at) >= 1.5)
            assert not [t for t in by_day[d] if t.opened_at > brake_ts], "no entry after the brake tripped"
    sigs = _signals(info["watcher_id"])
    _assert_legal([s["exec_state"] for s in sigs])
