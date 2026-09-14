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


# ---------------------------------------------------------------- suggest (deterministic, from report.diagnosis)

TF_ORDER = ["1m", "3m", "5m", "15m", "30m", "1h", "1D"]


def _get(spec: dict, pointer: str) -> Any:
    cur: Any = spec
    for seg in pointer.split("/")[1:]:
        if isinstance(cur, list):
            cur = cur[int(seg)] if seg.isdigit() and int(seg) < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
        if cur is None:
            return None
    return cur


def _slower_tf(tf: str) -> str | None:
    if tf in TF_ORDER and TF_ORDER.index(tf) < len(TF_ORDER) - 1:
        return TF_ORDER[TF_ORDER.index(tf) + 1]
    return None


def suggest(spec: dict, report: dict) -> dict:
    """One concrete edit per finding where a safe one exists. Never invents instruments; never touches gates."""
    findings = report.get("diagnosis") or []
    out: list[dict] = []
    seen: set[str] = set()

    def add(sid: str, title: str, reason: str, kind: str, patch: list[dict]) -> None:
        if sid in seen:
            return
        seen.add(sid)
        out.append({"id": sid, "title": title, "reason": reason, "kind": kind, "patch": patch})

    for f in findings:
        kind, levers = f.get("kind"), f.get("levers") or []
        nums = f.get("numbers") or {}
        if kind == "bottleneck_condition" and levers and levers[0].get("path"):
            path = levers[0]["path"]
            cond = _get(spec, path) or {}
            rhs, op = cond.get("rhs"), cond.get("op")
            if isinstance(rhs, (int, float)) and op in (">", ">=", "<", "<="):
                new = round(rhs * (0.75 if op in (">", ">=") else 1.25), 4)
                add("bottleneck", f"Relax the bottleneck threshold to {new:g}",
                    f"'{cond.get('lhs')} {op} {rhs:g}' held on {nums.get('true_pct', 0):.1f}% of bars. At {new:g} it fires more often; check that the extra setups still make money in sample before trusting them.",
                    "tune", [{"path": f"{path}/rhs", "from": rhs, "to": new}])
            else:
                key = path.split("/")[1]
                lst = list(spec.get(key) or [])
                idx = int(path.split("/")[2])
                if len(lst) > 1 and idx < len(lst):
                    trimmed = [c for i, c in enumerate(lst) if i != idx]
                    add("simplify", "Drop the condition that almost never holds",
                        "Fewer conditions is a simpler rule and more trades; if the results barely change, the condition was not adding anything.",
                        "simplify", [{"path": f"/{key}", "from": lst, "to": trimmed}])
        elif kind == "sized_to_zero":
            stop = spec.get("stop") or {}
            if stop.get("type") == "atr":
                mult = float((stop.get("params") or {}).get("mult", 2.0))
                add("size", f"Tighten the ATR stop from {mult:g}x to {round(mult * 0.75, 2):g}x",
                    f"{int(nums.get('skipped_for_size', 0))} setups risked more than 1R per lot; a nearer stop lowers the rupee risk per unit so a whole lot fits.",
                    "fix", [{"path": "/stop/params/mult", "from": mult, "to": round(mult * 0.75, 2)}])
            elif stop.get("type") == "fixed_pct":
                pct = float((stop.get("params") or {}).get("pct", 1.0))
                add("size", f"Tighten the fixed stop from {pct:g}% to {round(pct * 0.75, 3):g}%",
                    "A nearer stop lowers the rupee risk per unit so a whole lot fits inside 1R.",
                    "fix", [{"path": "/stop/params/pct", "from": pct, "to": round(pct * 0.75, 3)}])
            else:
                add("size", "Switch to a 1.5x ATR stop",
                    "The current stop type puts one lot's risk above 1R on most setups; an ATR stop scales with the bar size and can be tuned.",
                    "fix", [{"path": "/stop", "from": stop, "to": {"type": "atr", "params": {"length": 14, "mult": 1.5}}}])
        elif kind == "rr_filter":
            tg = spec.get("targets") or []
            if tg and tg[0].get("type") == "rr":
                v = float(tg[0].get("value", 2))
                add("rr", f"Move the target from {v:g}R to {v + 0.5:g}R",
                    "Costs are fixed per trade, so a further target raises the post-cost reward-to-risk; fewer setups will reach it.",
                    "tune", [{"path": "/targets/0/value", "from": v, "to": v + 0.5}])
        elif kind == "day_limit":
            n = int(spec.get("risk", {}).get("max_trades_per_day", 1))
            add("daylimit", f"Allow {n + 1} trades a day instead of {n}",
                "Setups arrived after the daily limit; one more trade a day adds sample size without changing the rules.",
                "tune", [{"path": "/risk/max_trades_per_day", "from": n, "to": n + 1}])
        elif kind == "costs":
            tf = spec.get("timeframe")
            nxt = _slower_tf(str(tf))
            if nxt:
                add("costs_tf", f"Move from {tf} to {nxt} bars",
                    f"You made {nums.get('gross_expectancy_r', 0):+.2f}R before costs and lost after; slower bars mean fewer trades and larger moves per unit of cost.",
                    "tune", [{"path": "/timeframe", "from": tf, "to": nxt}])
            tg = spec.get("targets") or []
            if tg and tg[0].get("type") == "rr":
                v = float(tg[0].get("value", 2))
                add("costs_target", f"Move the target from {v:g}R to {v + 0.5:g}R",
                    "A further target keeps more of each trade after fixed costs.",
                    "tune", [{"path": "/targets/0/value", "from": v, "to": v + 0.5}])
        elif kind == "no_edge":
            lst = list(spec.get("entry_long") or [])
            if len(lst) > 1:
                add("simplify_noedge", "Simplify: remove one entry condition",
                    "The rules lose before costs out of sample. Tuning a threshold to make that window pass would be fitting. Removing a condition tests whether the idea survives in a simpler form; if it does not, the hypothesis is the problem.",
                    "simplify", [{"path": "/entry_long", "from": lst, "to": lst[:-1]}])
            add("stop_noedge", "Consider a different hypothesis",
                "Expectancy is negative before costs out of sample. No parameter change should be expected to fix that.",
                "stop", [])
        elif kind == "drawdown":
            pct = float(spec.get("risk", {}).get("max_equity_risk_pct", 0.5))
            add("dd", f"Cut equity risk per trade from {pct:g}% to {round(pct * 0.75, 3):g}%",
                "The 5th-percentile drawdown breaches your profile; smaller positions shrink it in proportion without touching the entry rule.",
                "fix", [{"path": "/risk/max_equity_risk_pct", "from": pct, "to": round(pct * 0.75, 3)}])
    verdict = "passed" if report.get("passed") else ("no_edge" if any(f.get("kind") == "no_edge" for f in findings) else "fixable")
    if verdict == "passed":
        prose = "This version passed every hard gate. There is nothing to fix; watch it in paper mode and let the journal speak."
    elif verdict == "no_edge":
        prose = ("The rules lose out of sample even before costs. The suggestions below simplify rather than tune, because "
                 "making the test window pass by moving a threshold is fitting the past, not fixing the idea.")
    else:
        prose = (f"{len(out)} concrete change{'s' if len(out) != 1 else ''} to your own rules, each tied to a failed check. "
                 "Apply one at a time and re-test; every apply makes a new version so you can compare.")
    return {"prose": prose, "verdict": verdict, "suggestions": out, "source": "template"}
