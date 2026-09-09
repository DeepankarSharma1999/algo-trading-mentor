"""Mentor service: Anthropic Messages API when a key is configured, deterministic templates otherwise.
Every output passes `guardrail()`; a rejected LLM reply falls back to the template and is logged."""

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


def llm_available() -> bool:
    return bool(config.ANTHROPIC_API_KEY)


def _ask(user_content: str, max_tokens: int = 1200) -> str | None:
    if not llm_available():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=config.ANTHROPIC_MODEL, max_tokens=max_tokens, system=SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    except Exception as e:  # network, auth, quota: fall back silently, the app must keep working
        log.warning("LLM call failed: %s", e)
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
    raw = _ask(f"formalise\n\nHypothesis:\n{text}\n\nSymbols the user named: {symbols or 'none'}\n\nSchema example:\n{json.dumps(base['draft'])}")
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
