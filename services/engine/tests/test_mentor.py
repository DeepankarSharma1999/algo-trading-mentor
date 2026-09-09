from engine.mentor import service, templates
from engine.mentor.guardrail import guardrail
from engine.schema.testable import check_testable


def test_formalise_reads_a_complete_hypothesis():
    r = templates.formalise("On the 15 min chart go with an EMA 9 / 21 cross, stop 2x ATR, target 2R, on NIFTY", ["NIFTY"])
    d = r["draft"]
    assert d["timeframe"] == "15m" and d["instruments"] == ["NIFTY"] and d["market"] == "NSE_FO"
    assert d["stop"] == {"type": "atr", "params": {"length": 14, "mult": 2.0}}
    assert d["targets"] == [{"type": "rr", "value": 2.0}]
    assert d["entry_long"][0]["op"] == "crosses_above"
    assert check_testable(d)["testable"], r["ambiguity_flags"]


def test_formalise_flags_ambiguity_and_blocks_testable():
    r = templates.formalise("Buy when RSI is oversold and put a stop somewhere sensible", [])
    flags = r["ambiguity_flags"]
    assert any("RSI" in f for f in flags)
    assert any("stop rule reads two ways" in f for f in flags)
    assert any("No instrument" in f for f in flags)
    assert not check_testable(r["draft"])["testable"]


def test_formalise_never_invents_symbols():
    r = templates.formalise("EMA 20 cross on the daily with 3% stop and 1:2 target", [])
    assert r["draft"]["instruments"] == []
    assert guardrail(r["prose"], set()).ok


def test_explain_and_review_and_coach_pass_guardrail():
    sig = {"strategy_id": "s_v1", "symbol": "NIFTY", "regime": "compression", "conditions_passed": ["close > bb.upper"],
           "conditions_failed": [], "trigger": {"description": "Fill at next bar open."}, "stop": 100.0, "targets": [110.0],
           "quantity": 25, "rupee_risk": 2000, "portfolio_risk_pct": 0.5, "estimated_costs": 90, "post_cost_rr": 1.8,
           "gates": [{"name": "Daily risk brake", "pass": False, "reason": "Daily loss brake reached."}], "verdict": "blocked"}
    e = templates.explain(sig)
    assert "Blocked gates" in e and guardrail(e, {"NIFTY"}).ok
    rep = {"stages": [{"stage": 2, "name": "Out-of-sample", "summary": "OOS expectancy -0.08R.", "metrics": {"expectancy_r": -0.08}}],
           "weakest_stage": 2, "weakest_sentence": "Out-of-sample is your weakest gate.", "passed": False}
    rv = templates.review(rep)
    assert rv["weakest_stage"] == 2 and "Research" in rv["next_step"] and guardrail(rv["prose"], set()).ok
    c = templates.coach("Need to get it back tomorrow", ["get it back"], {"rules_followed": 4, "rules_total": 5})
    assert "lexicon" in c and guardrail(c, set()).ok


def test_service_falls_back_without_key(monkeypatch):
    monkeypatch.setattr(service.config, "ANTHROPIC_API_KEY", "")
    out = service.explain({"strategy_id": "x_v1", "symbol": "NIFTY", "gates": [], "verdict": "watch"}, {"NIFTY"})
    assert "x_v1" in out


def test_service_rejects_bad_llm_output_and_logs(monkeypatch):
    seen = []
    service.set_rejection_sink(lambda ep, reason, raw: seen.append((ep, reason)))
    monkeypatch.setattr(service, "_ask", lambda *_a, **_k: "You should buy RELIANCE now.")
    out = service.coach("fine", [], None, {"NIFTY"})
    assert "RELIANCE" not in out and seen and seen[0][0] == "coach"
    service.set_rejection_sink(lambda *_: None)
