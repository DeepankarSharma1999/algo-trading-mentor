"""HTTP API tests on an in-memory SQLite database with a fake provider (no Postgres needed)."""

from __future__ import annotations

import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from engine import db
from engine.db import models as m
from engine.mentor.guardrail import guardrail
from engine.validation.pipeline import STAGE_NAMES
from tests import harness
from tests.conftest import base_spec, ema_cross_spec

H = {"X-User-Id": harness.USER_ID}


@pytest.fixture
def api(monkeypatch):
    factory = harness.install_db(monkeypatch)
    harness.install_provider(monkeypatch)
    harness.seed(factory, sim_now=datetime(2025, 6, 12, 10, 35), strategy_status="validated")
    from engine.main import app

    with TestClient(app) as client:
        yield client
    harness.market.set_provider(None)


def _profile_state(state: str) -> None:
    with db.session() as s:
        p = s.get(m.Profile, harness.USER_ID)
        p.behaviour_state = state


# --- health / auth ---------------------------------------------------------------------------------


def test_health_reports_provider_and_sim_now(api):
    r = api.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "provider": "synthetic", "sim_now": "2025-06-12T10:35:00"}


def test_missing_user_header_is_401_with_plain_error(api):
    r = api.get(f"/risk/{harness.USER_ID}")
    assert r.status_code == 401 and set(r.json()) == {"error"} and r.json()["error"].endswith(".")
    assert api.get("/jobs/nope").status_code == 404  # jobs need no header
    assert api.get("/jobs/nope").json()["error"].startswith("Validation job")


def test_validation_errors_use_the_error_shape(api):
    r = api.post("/journal/notes", json={"nope": 1}, headers=H)
    assert r.status_code == 422 and set(r.json()) == {"error"}


# --- strategies ------------------------------------------------------------------------------------


def test_strategies_check_testable_and_not(api):
    ok = api.post("/strategies/check", json={"spec": ema_cross_spec()}, headers=H).json()
    assert ok == {"testable": True, "missing": [], "ambiguity_flags": []}
    bad = api.post("/strategies/check", json={"spec": base_spec(stop=None, ambiguity_flags=["Which stop?"])}, headers=H).json()
    assert bad["testable"] is False and any("stop" in x.lower() for x in bad["missing"]) and bad["ambiguity_flags"] == ["Which stop?"]
    broken = api.post("/strategies/check", json={"spec": ema_cross_spec(entry_long=[{"lhs": "ghost", "op": ">", "rhs": 1}])}, headers=H).json()
    assert broken["testable"] is False and any("ghost" in x for x in broken["missing"])


def test_backtest_is_synchronous_and_returns_result_shape(api):
    r = api.post("/backtest", json={"spec": ema_cross_spec(instruments=["RELIANCE"], market="NSE_EQ")}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"trades", "equity", "stats", "by_regime"}
    assert body["stats"]["trades"] >= 1 and all(t["costs"] > 0 for t in body["trades"])
    r2 = api.post("/backtest", json={"spec": ema_cross_spec(stop=None)}, headers=H)
    assert r2.status_code == 400 and "stop" in r2.json()["error"]


def test_backtest_in_sample_window_never_touches_the_oos_window(api):
    spec = ema_cross_spec(instruments=["RELIANCE"], market="NSE_EQ")
    r = api.post("/backtest", json={"spec": spec, "window": "in_sample"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    win = body["window"]
    assert win["kind"] == "in_sample" and win["end"] == win["oos_from"] and win["in_sample_pct"] == 70
    assert "locked" in win["note"]
    assert all(t["entry_ts"] < win["oos_from"] for t in body["trades"]), "a trade entered inside the locked window"
    assert set(body) >= {"condition_stats", "setup_bars", "stats"} and body["setup_bars"]["bars"] > 0
    assert api.post("/backtest", json={"spec": spec, "window": "bogus"}, headers=H).status_code == 400


def _run_validation(api, strategy_id):
    job_id = api.post("/validate", json={"strategy_id": strategy_id}, headers=H).json()["job_id"]
    deadline = time.time() + 120
    while time.time() < deadline:
        j = api.get(f"/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_repeated_validations_count_attempts_and_warn_from_the_third(api):
    first = _run_validation(api, harness.STRATEGY_ID)["report"]
    n0 = first["attempt"]
    second = _run_validation(api, harness.STRATEGY_ID)["report"]
    third = _run_validation(api, harness.STRATEGY_ID)["report"]
    assert (second["attempt"], third["attempt"]) == (n0 + 1, n0 + 2)
    assert third["attempt"] >= 3 and third["attempt_notice"].startswith(f"Attempt {third['attempt']} on the same test window")
    assert guardrail(third["attempt_notice"], {"RELIANCE"}).ok
    if n0 == 1:
        assert first["attempt_notice"] == "" and second["attempt_notice"] == ""


# --- risk ------------------------------------------------------------------------------------------


def test_risk_status_shape(api):
    r = api.get(f"/risk/{harness.USER_ID}", headers=H).json()
    assert r["profile"] == "standard" and r["one_r"] == 2000 and r["trading_bucket"] == 400000
    assert set(r["brakes"]) == {"daily", "weekly", "concurrent"} and r["daily_limit_r"] == 2.0


def test_risk_profile_tighten_any_time_loosen_only_in_research(api):
    assert api.post("/risk/profile", json={"profile": "conservative"}, headers=H).json() == {"ok": True}
    r = api.post("/risk/profile", json={"profile": "standard"}, headers=H)
    assert r.status_code == 409 and "RESEARCH" in r.json()["error"]
    _profile_state("RESEARCH")
    assert api.post("/risk/profile", json={"profile": "hard_ceiling"}, headers=H).json() == {"ok": True}
    assert api.get(f"/risk/{harness.USER_ID}", headers=H).json()["profile"] == "hard_ceiling"
    with db.session() as s:
        ev = s.query(m.StateEvent).filter(m.StateEvent.kind == "profile_change").order_by(m.StateEvent.ts).all()
        assert [(e.from_state, e.to_state) for e in ev] == [("standard", "conservative"), ("conservative", "hard_ceiling")]
        assert ev[0].ts == datetime(2025, 6, 12, 10, 35)
    assert api.post("/risk/profile", json={"profile": "wild"}, headers=H).status_code == 400


# --- behaviour / journal ---------------------------------------------------------------------------


def test_two_overrides_in_a_session_elevate(api):
    a = api.post("/behaviour/override", json={"what": "Mark eligible anyway"}, headers=H).json()
    assert a["state"] == "CALM"
    b = api.post("/behaviour/override", json={"what": "Skip cooldown"}, headers=H).json()
    assert b["state"] == "ELEVATED" and "2 override attempts" in b["reason"]
    with db.session() as s:
        assert s.query(m.OverrideAttempt).count() == 2
        assert s.query(m.StateEvent).filter(m.StateEvent.to_state == "ELEVATED").count() == 1


def test_journal_note_with_lexicon_flags_and_elevates(api):
    r = api.post("/journal/notes", json={"text": "Lost twice, need to get it back tomorrow with bigger size."}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"note", "state"}
    assert set(body["note"]["flags"]) >= {"get it back", "bigger size"} and body["note"]["id"]
    assert body["state"]["state"] == "ELEVATED"
    calm = api.post("/journal/notes", json={"text": "Took the fill as planned."}, headers=H).json()
    assert calm["note"]["flags"] == [] and calm["state"]["state"] == "ELEVATED"


def test_journal_shape(api):
    with db.session() as s:
        for k, (r, reg) in enumerate([(1.5, "trend"), (-1.0, "range"), (0.8, "trend")]):
            s.add(
                m.PaperTrade(
                    user_id=harness.USER_ID, strategy_id=harness.STRATEGY_ID, symbol="RELIANCE", side="long", qty=10,
                    planned={"entry": 100, "stop": 99, "targets": [102], "risk_r": 1},
                    actual={"entry": 100, "exit": 100 + r, "entry_ts": "2025-06-11T10:00:00", "exit_ts": "2025-06-11T11:00:00"},
                    slippage=0.03, costs=45.0, mfe_r=1.0, mae_r=0.2, exit_reason="target", regime=reg, outcome_r=r,
                    rules_followed=4, rules_total=4, status="closed",
                    opened_at=datetime(2025, 6, 11, 10, k), closed_at=datetime(2025, 6, 11, 11, k),
                )
            )
    body = api.get(f"/journal/{harness.USER_ID}", headers=H).json()
    assert set(body) == {"trades", "aggregates"} and len(body["trades"]) == 3
    t = body["trades"][0]
    assert set(t) >= {"id", "strategy_id", "symbol", "side", "qty", "planned", "actual", "slippage", "costs", "mfe_r", "mae_r", "exit_reason", "regime", "outcome_r", "rules_followed", "rules_total", "status"}
    agg = body["aggregates"]
    assert set(agg) == {"by_regime", "streaks", "totals"}
    assert agg["totals"] == {"trades": 3, "net_r": 1.3, "process_score": 1.0, "win_rate": pytest.approx(0.6667, abs=1e-3)}
    assert agg["by_regime"]["trend"] == {"trades": 2, "process_score": 1.0, "net_r": 2.3}
    assert agg["streaks"] == {"current": 1, "longest_win": 1, "longest_loss": 1}
    assert api.get("/journal/somebody-else", headers=H).status_code == 403


# --- desk / watchers -------------------------------------------------------------------------------


def test_watchers_require_validated_paper_only(api):
    with db.session() as s:
        st = s.get(m.Strategy, harness.STRATEGY_ID)
        st.status = "testable"
    r = api.post("/watchers", json={"strategy_id": harness.STRATEGY_ID}, headers=H)
    assert r.status_code == 409 and "validated" in r.json()["error"]
    with db.session() as s:
        st = s.get(m.Strategy, harness.STRATEGY_ID)
        st.status = "validated"
        st.spec = dict(st.spec) | {"automation_permission": "mentor_only"}
    r = api.post("/watchers", json={"strategy_id": harness.STRATEGY_ID}, headers=H)
    assert r.status_code == 409 and "mentor_only" in r.json()["error"]
    with db.session() as s:
        st = s.get(m.Strategy, harness.STRATEGY_ID)
        st.spec = dict(st.spec) | {"automation_permission": "paper_only"}
    r = api.post("/watchers", json={"strategy_id": harness.STRATEGY_ID}, headers=H)
    assert r.status_code == 200, r.text
    w = r.json()
    assert w["exec_state"] == "WATCHING" and w["strategy_id"] == harness.STRATEGY_ID and w["latest_signal"] is None
    assert api.post("/watchers", json={"strategy_id": harness.STRATEGY_ID}, headers=H).json()["id"] == w["id"]
    desk = api.get(f"/desk/{harness.USER_ID}", headers=H).json()
    assert set(desk) == {"risk", "behaviour", "market", "watchers", "provider"}
    assert desk["market"] == {"open": True, "sim_now": "2025-06-12T10:35:00", "session": "09:15–15:30 IST"}
    assert desk["behaviour"]["state"] == "CALM" and desk["provider"] == "synthetic"
    assert [x["id"] for x in desk["watchers"]] == [w["id"]] and desk["watchers"][0]["name"] == "EMA cross"
    assert api.delete(f"/watchers/{w['id']}", headers=H).json() == {"ok": True}
    assert api.delete(f"/watchers/{w['id']}", headers=H).status_code == 404


# --- validation job --------------------------------------------------------------------------------


def test_validate_job_runs_in_background_and_reports_stages(api):
    r = api.post("/validate", json={"strategy_id": harness.STRATEGY_ID}, headers=H)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    deadline = time.time() + 120
    while time.time() < deadline:
        j = api.get(f"/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.2)
    assert j["status"] in ("done", "failed"), j
    assert set(j) >= {"id", "status", "current_stage", "report", "error"}
    assert j["status"] == "done", j["error"]
    rep = j["report"]
    assert set(rep) == {"strategy_id", "started_at", "finished_at", "stages", "weakest_stage", "weakest_sentence", "passed", "diagnosis",
                        "attempt", "attempt_notice"}
    assert rep["attempt"] >= 1 and isinstance(rep["attempt_notice"], str)
    assert [s["stage"] for s in rep["stages"]] == list(range(1, 9))
    assert [s["name"] for s in rep["stages"]] == [STAGE_NAMES[i] for i in range(1, 9)]
    assert all(set(s) == {"stage", "name", "status", "summary", "metrics", "detail"} for s in rep["stages"])
    assert rep["weakest_sentence"].endswith(".") and j["current_stage"] >= 1
    with db.session() as s:
        st = s.get(m.Strategy, harness.STRATEGY_ID)
        assert st.status == ("validated" if rep["passed"] else "untested")
    review = api.post("/mentor/review", json={"job_id": job_id}, headers=H).json()
    assert set(review) == {"prose", "weakest_stage", "next_step"} and guardrail(review["prose"], {"RELIANCE"}).ok
    assert api.post("/validate", json={"strategy_id": "missing_v1"}, headers=H).status_code == 404


# --- mentor ----------------------------------------------------------------------------------------


def test_mentor_formalise_never_adds_instruments_and_passes_guardrail(api):
    text = "On the 15 min chart, EMA 9 / 21 cross on RELIANCE and INFY, stop 2x ATR, target 2R"
    r = api.post("/mentor/formalise", json={"text": text}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"draft", "ambiguity_flags", "prose"}
    assert body["draft"]["instruments"] == ["RELIANCE"]  # INFY is not in the provider or the user's strategies
    assert guardrail(body["prose"] + " " + " ".join(body["ambiguity_flags"]), set(body["draft"]["instruments"])).ok
    none = api.post("/mentor/formalise", json={"text": "Buy the dip on TATAMOTORS with a 1% stop"}, headers=H).json()
    assert none["draft"]["instruments"] == [] and guardrail(none["prose"], set()).ok


def test_mentor_explain_and_coach(api):
    with db.session() as s:
        w = m.Watcher(user_id=harness.USER_ID, strategy_id=harness.STRATEGY_ID, updated_at=datetime(2025, 6, 12, 10, 35))
        s.add(w)
        s.flush()
        payload = {"id": "sig1", "strategy_id": harness.STRATEGY_ID, "symbol": "RELIANCE", "regime": "trend", "conditions_passed": ["fast crosses_above slow"],
                   "conditions_failed": [], "trigger": {"description": "Fill at the next bar's open."}, "stop": 990.0, "targets": [1010.0], "quantity": 200,
                   "rupee_risk": 2000, "portfolio_risk_pct": 0.5, "estimated_costs": 90, "post_cost_rr": 1.8,
                   "gates": [{"name": "Daily risk brake", "pass": True}], "verdict": "eligible", "exec_state": "ARMED"}
        s.add(m.Signal(id="sig1", user_id=harness.USER_ID, watcher_id=w.id, strategy_id=harness.STRATEGY_ID, ts=datetime(2025, 6, 12, 10, 30), payload=payload))
    r = api.post("/mentor/explain", json={"signal_id": "sig1"}, headers=H).json()
    assert "RELIANCE" in r["prose"] and guardrail(r["prose"], {"RELIANCE"}).ok
    assert api.post("/mentor/explain", json={"signal_id": "nope"}, headers=H).status_code == 404
    c = api.post("/mentor/coach", json={"text": "I want to double down and get it back"}, headers=H).json()
    assert "lexicon" in c["prose"] and guardrail(c["prose"], set()).ok
    note = api.post("/journal/notes", json={"text": "Followed the plan."}, headers=H).json()["note"]
    c2 = api.post("/mentor/coach", json={"note_id": note["id"]}, headers=H).json()
    assert c2["prose"] and guardrail(c2["prose"], set()).ok
    assert api.post("/mentor/coach", json={}, headers=H).status_code == 400


# --- sim clock / paper step ------------------------------------------------------------------------


def test_sim_clock_get_and_post(api):
    c = api.get("/sim/clock").json()
    assert c == {"now": "2025-06-12T10:35:00", "speed": 2, "running": True, "market_open": True, "at_end": False, "data_end": "2025-12-31"}
    c2 = api.post("/sim/clock", json={"speed": 5, "running": False, "jump_to": "2025-06-13T15:29:00"}, headers=H).json()
    assert c2 == {"now": "2025-06-13T15:29:00", "speed": 5, "running": False, "market_open": True, "at_end": False, "data_end": "2025-12-31"}
    assert api.get("/health").json()["sim_now"] == "2025-06-13T15:29:00"


def test_paper_step_advances_through_session_bars_only(api):
    r = api.post("/paper/step", json={"bars": 3}, headers=H).json()
    assert r["sim_now"] == "2025-06-12T10:38:00" and r["market_open"] is True
    api.post("/sim/clock", json={"jump_to": "2025-06-13T15:29:00"}, headers=H)  # Friday, last bar
    r = api.post("/paper/step", json={"bars": 1}, headers=H).json()
    assert r["sim_now"] == "2025-06-13T15:30:00" and r["market_open"] is False
    r = api.post("/paper/step", json={"bars": 1}, headers=H).json()
    assert r["sim_now"] == "2025-06-16T09:15:00" and r["market_open"] is True  # skips the weekend
    with db.session() as s:
        kinds = [(e.from_state, e.to_state) for e in s.query(m.StateEvent).order_by(m.StateEvent.ts).all()]
        assert ("CALM", "RESEARCH") in kinds and ("RESEARCH", "CALM") in kinds
        assert s.get(m.Profile, harness.USER_ID).behaviour_state == "CALM"  # a session opened last
    # End of the synthetic feed: the clock stops at the last close instead of looping.
    api.post("/sim/clock", json={"jump_to": "2025-12-31T15:29:00", "running": True}, headers=H)
    r = api.post("/paper/step", json={"bars": 3}, headers=H).json()
    assert r["sim_now"] == "2025-12-31T15:30:00"
    assert api.get("/sim/clock").json()["running"] is False


def test_mentor_suggest_after_validation(api):
    job_id = api.post("/validate", json={"strategy_id": harness.STRATEGY_ID}, headers=H).json()["job_id"]
    for _ in range(600):
        j = api.get(f"/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    r = api.post("/mentor/suggest", json={"job_id": job_id}, headers=H)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["source"] == "template" and out["verdict"] in ("fixable", "no_edge", "passed")
    assert isinstance(out["suggestions"], list) and out["prose"]
    for sg in out["suggestions"]:
        assert set(sg) >= {"id", "title", "reason", "kind", "patch"}
    assert api.post("/mentor/suggest", json={"job_id": "nope"}, headers=H).status_code == 404
