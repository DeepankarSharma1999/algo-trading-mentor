"""The §0 guardrail. Every mentor output passes through `guardrail()` before it reaches the user.

Rejects (1) any instrument symbol that is not in the caller's allowed set (the user's own strategy /
portfolio context) and (2) imperative buy/sell phrasing. Rejections are logged by the caller."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Symbols the platform knows about (synthetic universe + common NSE names). A word in this set that is
# not in `allowed` is a violation. Uppercase tokens of 3-12 letters not in the English allow-list are
# also treated as tickers, so unknown symbols cannot slip through.
KNOWN_SYMBOLS = {
    "NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX", "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "ITC",
    "LT", "AXISBANK", "KOTAKBANK", "TATAMOTORS", "TATASTEEL", "WIPRO", "HCLTECH", "BAJFINANCE", "MARUTI",
    "SUNPHARMA", "ONGC", "NTPC", "ADANIENT", "ADANIPORTS", "HINDUNILVR", "BHARTIARTL", "TITAN", "ASIANPAINT",
    "ULTRACEMCO", "POWERGRID", "COALINDIA", "JSWSTEEL", "TECHM", "NESTLEIND", "DRREDDY", "CIPLA", "BPCL",
    "GRASIM", "EICHERMOT", "HEROMOTOCO", "DIVISLAB", "BRITANNIA", "APOLLOHOSP", "INDUSINDBK", "HDFCLIFE",
    "SBILIFE", "BAJAJFINSV", "TATACONSUM", "HINDALCO", "UPL", "M&M", "VEDL", "ZOMATO", "PAYTM", "DLF", "IRCTC",
}
# Uppercase words that are legitimately uppercase in mentor prose and are not tickers.
UPPER_ALLOW = {
    "R", "RR", "ATR", "EMA", "SMA", "RSI", "MACD", "VWAP", "ADX", "BB", "CPR", "SAR", "MTF", "OOS", "WF", "MC",
    "NSE", "SEBI", "RBI", "GST", "STT", "MFE", "MAE", "OHLC", "OHLCV", "CALM", "ELEVATED", "COOLDOWN",
    "RESEARCH", "WATCHING", "SETUP_FOUND", "ARMED", "ORDER_PENDING", "OPEN", "EXIT_PENDING", "CLOSED",
    "BLOCKED", "NSE_EQ", "NSE_FO", "PASS", "FAIL", "SKIP", "IST", "P", "L", "PNL", "OK", "NA", "ID", "HH", "MM",
    "AND", "OR", "NOT", "IF", "THE", "A", "I", "FOMO", "API", "LLM", "SYNTHETIC", "TEMPLATE", "TEMPLATES", "VCP",
    "HA", "PSAR", "DC", "ST", "BW", "PCT", "TP", "SL", "NAN", "MAX", "MIN", "TL", "DR",
}

# "buy X" / "sell X" / "go long" / "short it now" / "you should buy" ... Advice-shaped imperatives.
_IMPERATIVE = re.compile(
    r"\b(?:you\s+(?:should|must|need\s+to|ought\s+to|can)\s+)?"
    r"(?:buy|sell|purchase|short|go\s+long|go\s+short|enter\s+long|enter\s+short|accumulate|dump|exit\s+now|"
    r"take\s+(?:a\s+)?(?:long|short)|load\s+up|book\s+profits?)\b"
    r"(?!\s+(?:side|orders?|rule|rules|leg|legs|condition|conditions|signal|signals|price|prices|stop|"
    r"stops|trigger|entry|entries|phrasing|permission|is|are|was|were|would|means|refers))",
    re.IGNORECASE,
)
# Phrases that explicitly describe the user's own rule rather than advise, e.g. "your entry_long rule".
_RULE_CONTEXT = re.compile(r"\b(?:your|the)\s+(?:entry|exit|stop|target|trailing|short|long)[_ ]?(?:long|short)?[_ ]?(?:rule|rules|condition|conditions|leg)\b", re.IGNORECASE)
_TICKER = re.compile(r"(?<![A-Za-z0-9_])([A-Z][A-Z0-9&]{2,11})(?![A-Za-z0-9_])")


@dataclass
class GuardrailResult:
    ok: bool
    text: str
    reasons: list[str] = field(default_factory=list)


def guardrail(text: str, allowed_symbols: set[str] | list[str] | None = None) -> GuardrailResult:
    """Return ok=False with reasons if `text` names a symbol outside `allowed_symbols` or advises a trade."""
    allowed = {s.upper() for s in (allowed_symbols or [])}
    reasons: list[str] = []
    for m in _TICKER.finditer(text):
        tok = m.group(1)
        if tok in allowed or tok in UPPER_ALLOW:
            continue
        if tok in KNOWN_SYMBOLS or (tok.isalpha() and len(tok) >= 4):
            reasons.append(f"names instrument outside your context: {tok}")
    for m in _IMPERATIVE.finditer(text):
        window = text[max(0, m.start() - 40) : m.end() + 20]
        if _RULE_CONTEXT.search(window):
            continue
        reasons.append(f"imperative trade phrasing: '{m.group(0).strip()}'")
    return GuardrailResult(ok=not reasons, text=text, reasons=sorted(set(reasons)))
