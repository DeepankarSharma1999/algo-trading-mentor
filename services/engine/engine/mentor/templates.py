"""Deterministic mentor responses. Used when ANTHROPIC_API_KEY is absent and as the fallback when the
LLM reply fails the guardrail. Same inputs, same outputs, always in the spec's voice."""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------- formalise


_TF = [(r"\b1\s*-?\s*min|\b1m\b", "1m"), (r"\b3\s*-?\s*min|\b3m\b", "3m"), (r"\b5\s*-?\s*min|\b5m\b", "5m"),
       (r"\b15\s*-?\s*min|\b15m\b", "15m"), (r"\b30\s*-?\s*min|\b30m\b", "30m"), (r"\b(?:1\s*-?\s*)?hour(?:ly)?\b|\b1h\b|\b60\s*-?\s*min", "1h"),
       (r"\bdaily\b|\b1d\b|\bday\s+chart|\beod\b|\bpositional\b|\bswing\b", "1D")]
_NUM = r"(\d+(?:\.\d+)?)"


def _find(pattern: str, text: str, group: int = 1, default: str | None = None) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(group) if m else default


def formalise(text: str, symbols_in_text: list[str] | None = None) -> dict[str, Any]:
    """Keyword formaliser. Produces a draft in the schema plus one ambiguity flag per unstated choice."""
    t = text.lower()
    flags: list[str] = []
    inputs: dict[str, dict] = {}
    entry: list[dict] = []
    short: list[dict] | None = None

    timeframe = next((tf for pat, tf in _TF if re.search(pat, t)), None)
    if not timeframe:
        flags.append("Timeframe not stated. Which bar size do the rules read: 1m, 5m, 15m, 1h or 1D?")
        timeframe = "15m"

    # Indicators
    if m := re.search(r"ema\s*" + _NUM + r"(?:\s*(?:/|and|,)\s*" + _NUM + ")?", t):
        a, b = int(float(m.group(1))), (int(float(m.group(2))) if m.group(2) else None)
        inputs[f"ema{a}"] = {"indicator": "ema", "params": {"length": a}}
        if b:
            inputs[f"ema{b}"] = {"indicator": "ema", "params": {"length": b}}
            entry.append({"lhs": f"ema{a}", "op": "crosses_above", "rhs": f"ema{b}"})
            short = [{"lhs": f"ema{a}", "op": "crosses_below", "rhs": f"ema{b}"}]
        else:
            entry.append({"lhs": "close", "op": "crosses_above", "rhs": f"ema{a}"})
            flags.append(f"Entry reads 'close crosses above EMA {a}'. Is a close above enough, or must the whole bar be above?")
    if m := re.search(r"sma\s*" + _NUM + r"|" + _NUM + r"\s*(?:-|\s)?(?:day|period)?\s*(?:sma|moving average)", t):
        n = int(float(m.group(1) or m.group(2)))
        inputs[f"sma{n}"] = {"indicator": "sma", "params": {"length": n}}
        entry.append({"lhs": "close", "op": ">", "rhs": f"sma{n}"})
    if "rsi" in t:
        n = int(float(_find(r"rsi\s*\(?\s*" + _NUM, t, default="14")))
        inputs[f"rsi{n}"] = {"indicator": "rsi", "params": {"length": n}}
        lvl = _find(r"rsi[^.\d]{0,20}?(?:below|under|<)\s*" + _NUM, t)
        hi = _find(r"rsi[^.\d]{0,20}?(?:above|over|>)\s*" + _NUM, t)
        if lvl:
            entry.append({"lhs": f"rsi{n}", "op": "<", "rhs": float(lvl)})
        elif hi:
            entry.append({"lhs": f"rsi{n}", "op": ">", "rhs": float(hi)})
        else:
            flags.append(f"RSI {n} is mentioned without a level. Below what value is 'oversold' for you, above what is 'overbought'?")
    if "bollinger" in t or "squeeze" in t or re.search(r"\bbb\b", t):
        inputs["bb"] = {"indicator": "bbands", "params": {"length": 20, "mult": 2.0, "pct_window": 120}}
        if "squeeze" in t:
            entry.append({"lhs": "bb.bw_pct", "op": "<", "rhs": 20})
            flags.append("'Squeeze' is drafted as bandwidth percentile below 20 over 120 bars. Is that your threshold?")
        entry.append({"lhs": "close", "op": ">", "rhs": "bb.upper"})
        short = short or [{"lhs": "close", "op": "<", "rhs": "bb.lower"}]
    if "vwap" in t:
        inputs["vw"] = {"indicator": "vwap", "params": {}}
        entry.append({"lhs": "close", "op": "<", "rhs": "vw.lower2"})
        flags.append("VWAP reversion is drafted at the second sigma band. Is your entry at 1σ, 2σ, or a fixed distance?")
    if "supertrend" in t:
        inputs["st"] = {"indicator": "supertrend", "params": {"length": 10, "mult": 3.0}}
        entry.append({"lhs": "st.direction", "op": "==", "rhs": 1})
    if "donchian" in t or "channel" in t:
        inputs["dc"] = {"indicator": "donchian", "params": {"length": 20}}
        entry.append({"lhs": "close", "op": ">", "rhs": "dc.upper[-1]"})
    if "macd" in t:
        inputs["macd"] = {"indicator": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}
        entry.append({"lhs": "macd.hist", "op": "crosses_above", "rhs": 0})
    if "volume" in t:
        inputs["vr"] = {"indicator": "volume_ratio", "params": {"window": 20}}
        mult = _find(r"volume[^.\d]{0,30}?" + _NUM + r"\s*(?:x|times)", t)
        entry.append({"lhs": "vr", "op": ">", "rhs": float(mult) if mult else 1.5})
        if not mult:
            flags.append("'High volume' is drafted as 1.5× the 20-bar median. What multiple do you mean?")
    if not entry:
        flags.append("No entry condition could be read from the text. State the indicator, the level, and the comparison.")

    # Stop
    stop: dict | None
    if m := re.search(r"atr[^.\d]{0,20}?" + _NUM + r"\s*(?:x|times)?|" + _NUM + r"\s*(?:x|times)?\s*atr", t):
        mult = float(m.group(1) or m.group(2))
        inputs.setdefault("atr14", {"indicator": "atr", "params": {"length": 14}})
        stop = {"type": "atr", "params": {"length": 14, "mult": mult}}
    elif "swing" in t and "stop" in t:
        stop = {"type": "swing", "params": {"lookback": 5}}
        flags.append("Swing stop is drafted with a 5-bar confirmation. A 3-bar swing is a different stop.")
    elif m := re.search(r"stop[^.\d]{0,25}?" + _NUM + r"\s*%", t):
        stop = {"type": "fixed_pct", "params": {"pct": float(m.group(1))}}
    elif "signal bar" in t or "candle low" in t or "bar low" in t:
        stop = {"type": "signal_bar", "params": {"buffer_pct": 0.0}}
    elif "stop" in t:
        stop = {"type": "signal_bar", "params": {"buffer_pct": 0.0}}
        flags.append("Your stop rule reads two ways: below the signal bar or below the last swing. I can backtest both, but I will not mark this strategy testable until you pick one.")
    else:
        stop = None
        flags.append("No stop rule stated. A strategy without a stop is not testable.")

    # Targets / exits
    targets: list[dict] = []
    if m := re.search(r"(\d+(?:\.\d+)?)\s*r\b|1\s*:\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*(?:x|times)\s*(?:the\s+)?risk", t):
        targets.append({"type": "rr", "value": float(m.group(1) or m.group(2) or m.group(3))})
    elif m := re.search(r"target[^.\d]{0,25}?" + _NUM + r"\s*%", t):
        targets.append({"type": "fixed_pct", "value": float(m.group(1))})
    trailing = {"type": "none", "params": {}}
    if "trail" in t:
        trailing = {"type": "atr", "params": {"length": 14, "mult": 2.0}}
        inputs.setdefault("atr14", {"indicator": "atr", "params": {"length": 14}})
        flags.append("Trailing is drafted as 2× ATR(14). State the trail distance if it differs.")
    time_exit: dict = {}
    if m := re.search(r"(?:exit|close|flat)[^.\d]{0,20}?(\d{1,2}):(\d{2})", t):
        time_exit["at_time"] = f"{int(m.group(1)):02d}:{m.group(2)}"
    if not targets and trailing["type"] == "none" and not time_exit:
        flags.append("No exit stated: give a target (in R or %), a trailing rule, or a time exit.")

    intraday = timeframe != "1D"
    symbols = [s.upper() for s in (symbols_in_text or [])]
    if not symbols:
        flags.append("No instrument named. Add the symbols you want to test; the mentor never picks them.")
    market = "NSE_FO" if any(s in ("NIFTY", "BANKNIFTY", "FINNIFTY") for s in symbols) else "NSE_EQ"
    draft = {
        "strategy_id": "draft_v1", "name": _name_from(text), "version": 1, "parent_id": None, "market": market,
        "instruments": symbols, "timeframe": timeframe,
        "session": {"start": "09:15", "end": "15:30", "flat_at_close": intraday},
        "regime_affinity": _regimes(t), "inputs": inputs, "entry_long": entry, "entry_short": short,
        "trigger": {"type": "next_bar_open"}, "stop": stop, "targets": targets, "trailing": trailing, "time_exit": time_exit,
        "risk": {"min_rr_after_costs": 1.5, "max_equity_risk_pct": 0.5, "max_trades_per_day": 3},
        "automation_permission": "paper_only", "ambiguity_flags": flags, "version_locked": False,
    }
    prose = (
        f"I read {len(entry)} entry condition{'s' if len(entry) != 1 else ''}, "
        f"{'a ' + stop['type'].replace('_', ' ') + ' stop' if stop else 'no stop'}, and "
        f"{'a target' if targets else ('a trailing rule' if trailing['type'] != 'none' else ('a time exit' if time_exit else 'no exit'))} on the {timeframe} timeframe. "
        + (f"{len(flags)} ambiguit{'y' if len(flags) == 1 else 'ies'} block 'testable' until you resolve them in the Builder." if flags else "Nothing is ambiguous; the draft is testable once you save it.")
    )
    return {"draft": draft, "ambiguity_flags": flags, "prose": prose}


def _name_from(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)[:6]
    return (" ".join(words) or "Draft strategy")[:80]


def _regimes(t: str) -> list[str]:
    out = []
    if any(k in t for k in ("trend", "breakout", "momentum", "cross")):
        out.append("trend")
    if any(k in t for k in ("range", "reversion", "revert", "mean", "bounce")):
        out.append("range")
    if any(k in t for k in ("squeeze", "compression", "consolidat")):
        out.append("compression")
    if any(k in t for k in ("volatil", "high vol", "vix")):
        out.append("high_vol")
    return out or ["trend"]


# ---------------------------------------------------------------- explain


def explain(signal: dict) -> str:
    sid = signal.get("strategy_id", "your strategy")
    parts = [f"Strategy {sid} evaluated the last closed {signal.get('symbol', '')} bar in a {signal.get('regime', 'unknown').replace('_', ' ')} regime."]
    if signal.get("conditions_passed"):
        parts.append("Passed: " + "; ".join(signal["conditions_passed"]) + ".")
    if signal.get("conditions_failed"):
        parts.append("Failed: " + "; ".join(signal["conditions_failed"]) + ".")
    trig = signal.get("trigger") or {}
    if trig.get("description"):
        parts.append(f"Trigger: {trig['description']}")
    if signal.get("stop") is not None:
        tg = ", ".join(f"{x:.2f}" for x in signal.get("targets") or []) or "none"
        parts.append(f"Stop {signal['stop']:.2f}, targets {tg}, quantity {signal.get('quantity', 0)}, rupee risk {signal.get('rupee_risk', 0):.0f} ({signal.get('portfolio_risk_pct', 0):.2f}% of your trading bucket).")
    if signal.get("post_cost_rr") is not None:
        parts.append(f"Estimated costs {signal.get('estimated_costs', 0):.0f}, post-cost R:R {signal['post_cost_rr']:.2f}.")
    red = [g for g in signal.get("gates", []) if not g.get("pass")]
    if red:
        parts.append("Blocked gates: " + " ".join(f"{g['name']}: {g.get('reason', 'failed')}" for g in red))
    else:
        parts.append("Every gate passes.")
    v = signal.get("verdict", "watch")
    parts.append({"eligible": "Eligible under your rules if the next executable price stays inside your slippage band.",
                  "blocked": "Blocked under your rules. We can log it in paper mode and journal what would have happened.",
                  "watch": "Not a full setup yet. Watching for the next closed bar."}[v])
    return " ".join(parts)


# ---------------------------------------------------------------- review


def review(report: dict) -> dict:
    stages = report.get("stages", [])
    weakest = report.get("weakest_stage")
    sentence = report.get("weakest_sentence") or "No stage has run yet."
    st = next((s for s in stages if s.get("stage") == weakest), None)
    detail = ""
    next_step = "Run the validation to see where your rules stand."
    if st:
        m = st.get("metrics", {})
        detail = st.get("summary", "")
        step_by_stage = {
            1: "Loosen nothing; first check the rules produce trades at all on your instruments and timeframe. Fix the rule that never fires.",
            2: "Do not tune parameters to the out-of-sample window. Revisit the idea in Research: is the edge regime-specific? Check stage 6.",
            3: "The edge did not hold across rolling windows. Simplify the rule set before touching parameters.",
            4: "Costs eat the edge. Fewer trades, a wider stop-to-target ratio, or a slower timeframe are changes inside your rules.",
            5: "Neighbouring parameters lose money: the base case sits on a spike. Prefer a parameter region that is broadly flat.",
            6: "Expectancy differs by regime. Consider restricting regime_affinity to where the rules actually work.",
            7: "The 5th-percentile drawdown breaches your profile. Reduce risk per trade or tighten the profile; do not widen stops.",
            8: "Paper results disagree with the backtest. Keep paper trading; compare slippage and fills before changing rules.",
        }
        next_step = step_by_stage.get(weakest or 0, next_step)
        if m:
            detail += " Key figures: " + ", ".join(f"{k} {v:.2f}" if isinstance(v, float) else f"{k} {v}" for k, v in list(m.items())[:4]) + "."
    passed = report.get("passed")
    prose = f"{sentence} {detail}".strip()
    if passed:
        prose += " Every hard gate passed; this version can be watched in paper mode."
    return {"prose": prose, "weakest_stage": weakest, "next_step": next_step}


# ---------------------------------------------------------------- coach


def coach(text: str, hits: list[str], trade: dict | None = None) -> str:
    parts = []
    if trade:
        rf, rt = trade.get("rules_followed", 0), trade.get("rules_total", 0) or 1
        parts.append(f"Process on this trade: {rf} of {rt} rules followed.")
        if rf < rt:
            parts.append("A rule you skipped is the only thing under your control here; the outcome is not.")
        else:
            parts.append("You followed every rule. Whatever the outcome, that is the trade to repeat.")
    if hits:
        parts.append(f"Your note uses language from the revenge/FOMO lexicon ({', '.join(hits[:3])}). That is the signal, not the market. Before the next session: read the rule that would have stopped this, and write one sentence on what you will do when the feeling returns.")
    else:
        parts.append("The note reads as process, not emotion. Keep writing the plan before the fill and the deviation, if any, after.")
    parts.append("The mentor does not comment on P&L as skill; it comments on whether your rules were followed.")
    return " ".join(parts)
