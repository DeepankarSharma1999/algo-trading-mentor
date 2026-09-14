import json

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


# ---------------------------------------------------------------- suggest

REPORT_FAIL = {
    "passed": False, "weakest_stage": 1, "weakest_sentence": "In-sample coherence is your weakest gate.",
    "stages": [{"stage": 1, "name": "In-sample coherence", "status": "fail", "summary": "11 trades", "metrics": {"trades": 11, "min_trades": 120}}],
    "diagnosis": [
        {"stage": 1, "kind": "bottleneck_condition", "title": "One entry condition is the bottleneck", "detail": "'vr > 1.5' held on 2.1% of bars.",
         "numbers": {"true_pct": 2.1, "trades": 11, "min_trades": 120}, "levers": [{"label": "Condition vr > 1.5", "section": "entry", "path": "/entry_long/1"}]},
        {"stage": 1, "kind": "sized_to_zero", "title": "Setups sized to zero", "detail": "570 setups skipped.", "numbers": {"skipped_for_size": 570, "one_r": 2000, "lot_size": 25},
         "levers": [{"label": "Stop rule", "section": "exits", "path": "/stop"}]},
    ],
}
SPEC = {"strategy_id": "x_v1", "instruments": ["NIFTY"], "timeframe": "5m", "entry_long": [{"lhs": "close", "op": ">", "rhs": "ema20"}, {"lhs": "vr", "op": ">", "rhs": 1.5}],
        "stop": {"type": "atr", "params": {"length": 14, "mult": 2.0}}, "targets": [{"type": "rr", "value": 2}], "risk": {"max_trades_per_day": 2, "min_rr_after_costs": 1.5, "max_equity_risk_pct": 0.5}}


def test_template_suggest_turns_findings_into_patches():
    out = templates.suggest(SPEC, REPORT_FAIL)
    assert out["source"] == "template" and out["verdict"] == "fixable"
    ids = {s["id"]: s for s in out["suggestions"]}
    assert ids["bottleneck"]["patch"] == [{"path": "/entry_long/1/rhs", "from": 1.5, "to": 1.125}]
    assert ids["size"]["patch"] == [{"path": "/stop/params/mult", "from": 2.0, "to": 1.5}]
    for s in out["suggestions"]:
        assert service.patch_ok(s["patch"]) and guardrail(s["title"] + " " + s["reason"], {"NIFTY"}).ok


def test_template_suggest_no_edge_prefers_simplify_and_says_so():
    rep = {**REPORT_FAIL, "diagnosis": [{"stage": 2, "kind": "no_edge", "title": "No edge", "detail": "x", "numbers": {}, "levers": []}]}
    out = templates.suggest(SPEC, rep)
    assert out["verdict"] == "no_edge" and "fitting" in out["prose"]
    kinds = {s["kind"] for s in out["suggestions"]}
    assert "simplify" in kinds and "stop" in kinds and "tune" not in kinds


def test_patch_ok_rejects_instruments_and_identity():
    assert service.patch_ok([{"path": "/risk/max_trades_per_day", "from": 2, "to": 3}])
    assert not service.patch_ok([{"path": "/instruments/0", "from": "NIFTY", "to": "RELIANCE"}])
    assert not service.patch_ok([{"path": "/automation_permission", "to": "paper_only"}])
    assert not service.patch_ok([{"path": "/name", "to": "x"}])
    assert not service.patch_ok([{"path": "risk/x", "to": 1}])  # not a pointer
    assert not service.patch_ok([{"path": "/risk/x"}])  # no value


def test_provider_selection_prefers_gemini(monkeypatch):
    monkeypatch.setattr(service.config, "GEMINI_API_KEY", "g")
    monkeypatch.setattr(service.config, "ANTHROPIC_API_KEY", "a")
    assert service.llm_provider() == "gemini"
    monkeypatch.setattr(service.config, "GEMINI_API_KEY", "")
    assert service.llm_provider() == "anthropic"
    monkeypatch.setattr(service.config, "ANTHROPIC_API_KEY", "")
    assert service.llm_provider() is None and service.suggest(SPEC, REPORT_FAIL, {"NIFTY"})["source"] == "template"


def test_suggest_drops_forbidden_patches_and_keeps_source(monkeypatch):
    monkeypatch.setattr(service.config, "GEMINI_API_KEY", "g")
    reply = {"prose": "Two edits to your own rules.", "verdict": "fixable", "suggestions": [
        {"title": "Switch instrument", "reason": "Trade RELIANCE instead.", "kind": "tune", "patch": [{"path": "/instruments/0", "from": "NIFTY", "to": "RELIANCE"}]},
        {"title": "Relax the volume filter", "reason": "vr > 1.5 held on 2% of bars.", "kind": "tune", "patch": [{"path": "/entry_long/1/rhs", "from": 1.5, "to": 1.2}]},
    ]}
    monkeypatch.setattr(service, "_ask", lambda *_a, **_k: json.dumps(reply))
    out = service.suggest(SPEC, REPORT_FAIL, {"NIFTY"})
    # The instrument-swapping suggestion is dropped (forbidden root); the rule edit survives.
    assert out["source"] == "gemini" and len(out["suggestions"]) == 1
    assert out["suggestions"][0]["patch"] == [{"path": "/entry_long/1/rhs", "from": 1.5, "to": 1.2}]


def test_suggest_rejects_buy_sell_prose(monkeypatch):
    monkeypatch.setattr(service.config, "GEMINI_API_KEY", "g")
    seen = []
    service.set_rejection_sink(lambda ep, reason, raw: seen.append(ep))
    monkeypatch.setattr(service, "_ask", lambda *_a, **_k: json.dumps({"prose": "You should buy on the next signal.", "verdict": "fixable", "suggestions": []}))
    out = service.suggest(SPEC, REPORT_FAIL, {"NIFTY"})
    assert out["source"] == "template" and "suggest" in seen
    service.set_rejection_sink(lambda *_: None)
