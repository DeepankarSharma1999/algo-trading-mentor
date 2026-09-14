"""Mentor service: Gemini when GEMINI_API_KEY is set, else Claude when ANTHROPIC_API_KEY is set, else
deterministic templates. Every output passes `guardrail()`; a rejected LLM reply falls back to the
template and is logged."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from engine import config
from engine.mentor import templates
from engine.mentor.guardrail import guardrail

log = logging.getLogger("mentor")
SYSTEM = (Path(__file__).with_name("prompt.md")).read_text(encoding="utf-8")

# Called with (endpoint, reason, raw_text); the API layer binds this to the guardrail_log table.
RejectionSink = Callable[[str, str, str], None]
_sink: RejectionSink | None = None


def set_rejection_sink(fn: RejectionSink) -> None:
    global _sink
    _sink = fn


def _log_rejection(endpoint: str, reasons: list[str], raw: str) -> None:
    log.warning("guardrail rejected %s: %s", endpoint, reasons)
    if _sink:
        _sink(endpoint, "; ".join(reasons), raw)


def llm_provider() -> str | None:
    """'gemini' | 'anthropic' | None, by which key is configured (Gemini wins when both are set)."""
    if config.GEMINI_API_KEY:
        return "gemini"
    if config.ANTHROPIC_API_KEY:
        return "anthropic"
    return None


def llm_available() -> bool:
    return llm_provider() is not None


def _ask(user_content: str, max_tokens: int = 1200, json_mode: bool = False) -> str | None:
    """`json_mode` asks the model for a bare JSON object. Gemini 2.5 spends "thinking" tokens from the same
    output budget, so thinking is switched off and the budget raised; otherwise a 1200-token cap truncates the JSON."""
    provider = llm_provider()
    if provider is None:
        return None
    try:
        if provider == "gemini":
            from google import genai
            from google.genai import types as gtypes

            client = genai.Client(api_key=config.GEMINI_API_KEY)
            gcfg = gtypes.GenerateContentConfig(
                system_instruction=SYSTEM,
                max_output_tokens=max(max_tokens, 4000) if json_mode else max_tokens,
                thinking_config=gtypes.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json" if json_mode else None,
            )
            resp = client.models.generate_content(model=config.GEMINI_MODEL, contents=user_content, config=gcfg)
            return resp.text or ""
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=config.ANTHROPIC_MODEL, max_tokens=max_tokens, system=SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception as e:  # network, auth, quota: fall back silently, the app must keep working
        log.warning("LLM call failed (%s): %s", provider, e)
        return None


def _guarded(endpoint: str, text: str | None, allowed: set[str], fallback: str) -> str:
    if text is None:
        return fallback
    r = guardrail(text, allowed)
    if r.ok:
        return text
    _log_rejection(endpoint, r.reasons, text)
    return fallback


def formalise(text: str, allowed_symbols: set[str] | None = None) -> dict[str, Any]:
    symbols = sorted({s for s in allowed_symbols or set() if s.upper() in text.upper()})
    base = templates.formalise(text, symbols)
    raw = _ask(f"formalise\n\nHypothesis:\n{text}\n\nSymbols the user named: {symbols or 'none'}\n\nSchema example:\n{json.dumps(base['draft'])}", 3000, json_mode=True)
    if raw is None:
        return base
    try:
        js = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
        draft, flags, prose = js["draft"], list(js.get("ambiguity_flags", [])), str(js.get("prose", ""))
        # §0: the LLM may not add instruments the user did not name.
        draft["instruments"] = symbols
        draft["automation_permission"] = "paper_only" if draft.get("automation_permission") not in ("paper_only", "mentor_only", "blocked") else draft["automation_permission"]
        draft["ambiguity_flags"] = flags
        check = guardrail(prose + " " + " ".join(flags), set(symbols))
        if not check.ok:
            _log_rejection("formalise", check.reasons, raw)
            return base
        return {"draft": draft, "ambiguity_flags": flags, "prose": prose}
    except Exception as e:
        _log_rejection("formalise", [f"unparseable reply: {e}"], raw)
        return base


def explain(signal: dict, allowed_symbols: set[str]) -> str:
    fallback = templates.explain(signal)
    raw = _ask(f"explain\n\nSignal JSON:\n{json.dumps(signal)}", 700)
    return _guarded("explain", raw, allowed_symbols, fallback)


def review(report: dict, allowed_symbols: set[str]) -> dict[str, Any]:
    base = templates.review(report)
    raw = _ask(f"review\n\nValidationReport JSON (stage details trimmed):\n{json.dumps({**report, 'stages': [{k: v for k, v in s.items() if k != 'detail'} for s in report.get('stages', [])]})}", 700)
    prose = _guarded("review", raw, allowed_symbols, base["prose"])
    return {**base, "prose": prose}


def coach(text: str, hits: list[str], trade: dict | None, allowed_symbols: set[str]) -> str:
    fallback = templates.coach(text, hits, trade)
    raw = _ask(f"coach\n\nJournal note:\n{text}\n\nLexicon hits: {hits}\n\nTrade: {json.dumps(trade) if trade else 'none'}", 500)
    return _guarded("coach", raw, allowed_symbols, fallback)


# ---------------------------------------------------------------- suggest (ARCHITECTURE section 4b)

ALLOWED_ROOTS = {"inputs", "entry_long", "entry_short", "timeframe", "session", "regime_affinity", "trigger", "stop",
                 "targets", "trailing", "time_exit", "risk"}
FORBIDDEN_ROOTS = {"instruments", "market", "automation_permission", "strategy_id", "version", "parent_id", "name",
                   "version_locked", "ambiguity_flags"}
KINDS = {"fix", "tune", "simplify", "stop"}
VERDICTS = {"fixable", "no_edge", "passed"}


def patch_ok(patch: Any) -> bool:
    """Every op is a JSON-pointer set whose root is an allowed spec section. Forbidden roots reject the whole patch."""
    if not isinstance(patch, list):
        return False
    for op in patch:
        if not isinstance(op, dict) or not isinstance(op.get("path"), str) or not op["path"].startswith("/") or "to" not in op:
            return False
        root = op["path"].split("/")[1] if len(op["path"]) > 1 else ""
        if root in FORBIDDEN_ROOTS or root not in ALLOWED_ROOTS:
            return False
    return True


def _clean_suggestions(raw: Any) -> list[dict]:
    out: list[dict] = []
    for i, sg in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(sg, dict) or not patch_ok(sg.get("patch", [])):
            continue
        title, reason = str(sg.get("title", "")).strip(), str(sg.get("reason", "")).strip()
        if not title or not reason:
            continue
        out.append({
            "id": str(sg.get("id") or f"s{i + 1}"), "title": title[:120], "reason": reason[:600],
            "kind": sg.get("kind") if sg.get("kind") in KINDS else "tune", "patch": sg["patch"],
        })
    return out[:6]


def suggest(spec: dict, report: dict, allowed_symbols: set[str] | None = None) -> dict[str, Any]:
    """Concrete edits to the user's own rules for a failed report. Never applied here; the web saves a new version."""
    allowed = set(allowed_symbols or [])
    base = templates.suggest(spec, report)
    provider = llm_provider()
    if provider is None:
        return base
    slim = {
        "weakest_sentence": report.get("weakest_sentence"),
        "passed": report.get("passed"),
        "stages": [{k: v for k, v in s.items() if k != "detail"} for s in report.get("stages", [])],
        "diagnosis": report.get("diagnosis", []),
    }
    raw = _ask(
        "suggest\n\nStrategy spec JSON:\n" + json.dumps(spec) + "\n\nValidation report (stage details trimmed):\n" + json.dumps(slim)
        + "\n\nAllowed patch roots: " + ", ".join(sorted(ALLOWED_ROOTS)) + ". Forbidden: " + ", ".join(sorted(FORBIDDEN_ROOTS))
        + '.\nReply with JSON only: {"prose": str, "verdict": "fixable"|"no_edge", "suggestions": [{"title": str, "reason": str, '
        + '"kind": "fix"|"tune"|"simplify"|"stop", "patch": [{"path": "/json/pointer", "from": current, "to": new}]}]} with at most 5 suggestions.',
        4000,
        json_mode=True,
    )
    if raw is None:
        return base
    try:
        js = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])
    except Exception as e:
        _log_rejection("suggest", [f"unparseable reply: {e}"], raw)
        return base
    suggestions = _clean_suggestions(js.get("suggestions"))
    prose = str(js.get("prose", "")).strip()
    check = guardrail(" ".join([prose] + [s["title"] + " " + s["reason"] for s in suggestions]), allowed)
    if not check.ok:
        _log_rejection("suggest", check.reasons, raw)
        return base
    verdict = js.get("verdict") if js.get("verdict") in VERDICTS else base["verdict"]
    if report.get("passed"):
        verdict = "passed"
    return {"prose": prose or base["prose"], "verdict": verdict, "suggestions": suggestions or base["suggestions"], "source": provider}
