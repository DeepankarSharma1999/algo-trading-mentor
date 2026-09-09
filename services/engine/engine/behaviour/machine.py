"""Behavioural state machine (ARCHITECTURE §8). Pure transitions here; persistence lives in the service layer.

States: CALM | ELEVATED | COOLDOWN | RESEARCH.
- RESEARCH whenever the market is closed. At open: CALM, unless COOLDOWN was set during the previous
  session (it clears only at the NEXT session open, so a cooldown set at 14:00 ends at the next day's open).
- ELEVATED on >= 2 override attempts within a session, or when journal text hits the lexicon.
- COOLDOWN on a rule breach or a daily brake -> journal-only until the next session open.
Parameters are editable only in RESEARCH."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

STATES = ("CALM", "ELEVATED", "COOLDOWN", "RESEARCH")
OVERRIDES_TO_ELEVATE = 2


@lru_cache(maxsize=1)
def lexicon() -> list[str]:
    lines = (Path(__file__).with_name("lexicon.txt")).read_text(encoding="utf-8").splitlines()
    return [ln.strip().lower() for ln in lines if ln.strip() and not ln.startswith("#")]


def lexicon_hits(text: str) -> list[str]:
    t = re.sub(r"\s+", " ", text.lower())
    return [p for p in lexicon() if p in t]


@dataclass
class Decision:
    to: str
    reason: str
    changed: bool


def _same(state: str, reason: str) -> Decision:
    return Decision(state, reason, False)


def on_market_close(state: str) -> Decision:
    if state == "RESEARCH":
        return _same(state, "Market closed.")
    return Decision("RESEARCH", "Market closed. Parameters may change in Research.", True)


def on_market_open(state: str, cooldown_pending: bool) -> Decision:
    """`cooldown_pending` is true when a COOLDOWN was set during the previous session and has not yet been
    served through a full session; in that case the new session starts in COOLDOWN and clears at the following open."""
    if cooldown_pending:
        return Decision("COOLDOWN", "Cooldown carried into this session. Journal only until the next open.", state != "COOLDOWN")
    return Decision("CALM", "Session open. No brakes reached.", state != "CALM")


def on_override_attempt(state: str, attempts_this_session: int) -> Decision:
    if state in ("COOLDOWN", "RESEARCH"):
        return _same(state, f"Override logged ({attempts_this_session}); state unchanged.")
    if attempts_this_session >= OVERRIDES_TO_ELEVATE and state == "CALM":
        return Decision("ELEVATED", f"{attempts_this_session} override attempts this session.", True)
    return _same(state, f"Override logged ({attempts_this_session}).")


def on_journal_text(state: str, text: str) -> tuple[Decision, list[str]]:
    hits = lexicon_hits(text)
    if hits and state == "CALM":
        return Decision("ELEVATED", f"Journal text matched the lexicon: {', '.join(hits[:3])}.", True), hits
    return _same(state, "Note journaled." if not hits else f"Lexicon hit ({', '.join(hits[:3])}); state unchanged."), hits


def on_rule_breach(state: str, what: str) -> Decision:
    if state == "RESEARCH":
        return _same(state, f"{what} recorded; market closed.")
    return Decision("COOLDOWN", f"{what}. Journal only until the next session open.", state != "COOLDOWN")


def on_daily_brake(state: str) -> Decision:
    return on_rule_breach(state, "Daily loss brake reached")


def can_edit_parameters(state: str) -> bool:
    return state == "RESEARCH"


def can_open_positions(state: str) -> bool:
    return state in ("CALM", "ELEVATED")


def session_key(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d")
