"""The paper trader (ARCHITECTURE section 6).

`step(session, n_bars)` advances the sim clock by n one-minute bars. At every session open/close the
behavioural machine runs for every onboarded user. Then every watcher whose strategy is `paper_only`
is evaluated on the CLOSED bars of its timeframe up to `sim_now`, once per closed bar, and the
execution state machine (engine.exec) is driven with the same fill/exit semantics as the backtester:

    WATCHING -> SETUP_FOUND -> ARMED -> ORDER_PENDING -> OPEN -> EXIT_PENDING -> CLOSED
                            \\-> BLOCKED (any red gate)        (new cycle from the next bar)

Every state change writes a `signals` row (the Signal payload with `exec_state` set) and updates the
watcher; fills and exits write/update `paper_trades`. The position lives in `watchers.context`.
"""

from __future__ import annotations

import copy
import itertools
import logging
import math
import secrets
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from engine import indicators as ind
from engine.backtest import TF_MINUTES, auto_segment
from engine.behaviour.machine import can_open_positions
from engine.costs import round_trip_cost
from engine.data import lot_size, resample_bars
from engine.data.calendar import SESSION_CLOSE
from engine.db import models as m
from engine.exec import TERMINAL, ExecState, IllegalTransition, can_transition
from engine.risk.engine import PROFILES, position_size
from engine.risk.engine import one_r as risk_one_r
from engine.rules.engine import as_strategy, evaluate, target_prices, trailing_stop
from engine.services import behaviour, clock, market, risk
from engine.services import validation as validation_svc
from engine.services.common import get_profile, iso, num
from engine.services.signals import build_signal

log = logging.getLogger("paper")
TAIL_BARS = 400
MIN_BARS = 30
STRICT = False  # tests set True so evaluation errors raise instead of being logged
_seq = itertools.count()
_CLOSE = pd.Timedelta(hours=SESSION_CLOSE.hour, minutes=SESSION_CLOSE.minute)


def signal_id() -> str:
    """cuid-shaped, lexicographically ordered within a process so same-tick rows keep their order."""
    return f"c{time.time_ns():016x}{next(_seq) % 0x10000:04x}{secrets.token_hex(2)}"


def _hhmm(s: str) -> int:
    h, mm = s.split(":")
    return int(h) * 60 + int(mm)


def _f(x: Any) -> float:
    return float(x)


# --- bars -----------------------------------------------------------------------------------------


def may_have_closed(now: datetime, tf_min: int) -> bool:
    """Cheap pre-check: a bar of this timeframe can only have closed at a bar boundary or at 15:30."""
    if tf_min <= 1:
        return True
    minutes = (now - clock.session_open(now.date())).total_seconds() / 60
    return minutes <= 0 or minutes >= 375 or minutes % tf_min == 0


def closed_bars(prov: Any, symbol: str, tf: str, now: datetime, tail: int = TAIL_BARS) -> pd.DataFrame:
    """The last `tail` CLOSED bars of `tf` at `now` (bar open + tf <= now, or the session has ended)."""
    tf_min = TF_MINUTES[tf]
    days = math.ceil(tail * tf_min / 375 * 1.6) + 5
    b1 = prov.get_bars(symbol, "1m", now - timedelta(days=days), now)
    if b1.empty:
        return b1
    b1 = b1[b1["ts"] + pd.Timedelta(minutes=1) <= pd.Timestamp(now)]
    bars = resample_bars(b1, tf) if tf != "1m" else b1.reset_index(drop=True)
    if bars.empty:
        return bars
    day_close = bars["ts"].dt.normalize() + _CLOSE
    closed = (bars["ts"] + pd.Timedelta(minutes=tf_min) <= pd.Timestamp(now)) | (day_close <= pd.Timestamp(now))
    return bars[closed].tail(tail).reset_index(drop=True)


# --- one watcher, one closed bar -----------------------------------------------------------------


class _Cycle:
    """Everything needed to evaluate one watcher on its latest closed bar."""

    def __init__(self, session: Session, w: m.Watcher, strat: m.Strategy, bars: pd.DataFrame, now: datetime, events: list[dict]):
        self.s, self.w, self.strat, self.bars, self.now, self.events = session, w, strat, bars, now, events
        self.spec = as_strategy(strat.spec)
        self.symbol = self.spec.instruments[0].root
        self.i = len(bars) - 1
        self.inputs = ind.compute_inputs(bars, self.spec.inputs)
        self.ev = evaluate(self.spec, bars, self.inputs)
        self.row = self.ev.iloc[self.i]
        self.profile = get_profile(session, w.user_id)
        rp = self.profile.risk_profile if self.profile.risk_profile in PROFILES else "conservative"
        self.one_r = risk_one_r(num(self.profile.trading_bucket), rp) or validation_svc.FALLBACK_ONE_R
        self.one_r_eff = min(self.one_r, num(self.profile.trading_bucket) * self.spec.risk.max_equity_risk_pct / 100.0) or self.one_r
        self.rs = risk.status_obj(session, w.user_id, now)
        self.lot = lot_size(self.symbol, str(self.spec.market))
        self.cost_params = validation_svc.cost_params_for(self.profile)
        self.slip = self.cost_params.slippage_bps / 10_000 * self.cost_params.stress_multiplier
        self.segment = auto_segment(self.spec)
        self.tf_min = TF_MINUTES[str(self.spec.timeframe)]
        self.daily = str(self.spec.timeframe) == "1D"
        self.rules_total = len(self.spec.entry_long or []) + 3
        self._base: dict | None = None
        self.ctx: dict = copy.deepcopy(w.context or {})

    # -- helpers --------------------------------------------------------------------------------
    @property
    def bar_ts(self) -> pd.Timestamp:
        return pd.Timestamp(self.bars["ts"].iloc[self.i])

    def trades_today(self) -> int:
        since = clock.session_open(self.now.date())
        return (
            self.s.query(m.PaperTrade)
            .filter(
                m.PaperTrade.user_id == self.w.user_id,
                m.PaperTrade.strategy_id == self.strat.id,
                m.PaperTrade.opened_at >= since,
                m.PaperTrade.opened_at <= self.now,
            )
            .count()
        )

    def base(self) -> dict:
        if self._base is None:
            self._base = build_signal(
                self.spec,
                self.bars,
                self.i,
                self.row,
                self.rs,
                self.profile.behaviour_state,
                self.trades_today(),
                self.one_r,
                self.cost_params,
                self.lot,
                inputs=self.inputs,
                exec_state=self.w.exec_state,
                timestamp=self.bar_ts,
                symbol=self.symbol,
            )
        return self._base

    def move(self, to: ExecState, reason: str, sentence: str | None = None) -> None:
        frm = ExecState(self.w.exec_state)
        if frm in TERMINAL and to is ExecState.WATCHING:
            pass  # a new cycle starts at WATCHING
        elif frm in TERMINAL and to in (ExecState.SETUP_FOUND,):
            pass  # new cycle: WATCHING -> SETUP_FOUND on the same bar
        elif not can_transition(frm, to):
            raise IllegalTransition(frm, to)
        payload = dict(self.base())
        payload["id"] = signal_id()
        payload["exec_state"] = to.value
        if sentence:
            payload["sentence"] = sentence
        self.s.add(
            m.Signal(
                id=payload["id"], user_id=self.w.user_id, watcher_id=self.w.id, strategy_id=self.strat.id, ts=self.now, payload=payload
            )
        )
        self.w.exec_state = to.value
        self.w.state_reason = reason
        self.w.updated_at = self.now
        self.events.append(
            {
                "kind": "exec",
                "ts": iso(self.now),
                "bar": iso(self.bar_ts),
                "watcher_id": self.w.id,
                "strategy_id": self.strat.id,
                "symbol": self.symbol,
                "from": frm.value,
                "to": to.value,
                "reason": reason,
            }
        )

    # -- fills and exits (same semantics as engine.backtest) ------------------------------------
    def try_fill(self, order: dict) -> float | None:
        i, b = self.i, self.bars
        o, h, lo = _f(b["open"].iloc[i]), _f(b["high"].iloc[i]), _f(b["low"].iloc[i])
        long = order["side"] == "long"
        trigger, offset = str(self.spec.trigger.type), (self.spec.trigger.offset_pct or 0.0) / 100
        if trigger in ("next_bar_open", "bar_close"):
            return o
        if trigger == "break_of_signal_bar":
            lvl = order["sig_high"] * (1 + offset) if long else order["sig_low"] * (1 - offset)
            if long and h >= lvl:
                return max(o, lvl)
            if not long and lo <= lvl:
                return min(o, lvl)
            return None
        if trigger == "limit":
            lvl = order["sig_close"] * (1 - offset) if long else order["sig_close"] * (1 + offset)
            if long and lo <= lvl:
                return min(o, lvl)
            if not long and h >= lvl:
                return max(o, lvl)
            return None
        raise ValueError(f"unknown trigger {trigger!r}")

    def open_position(self, order: dict, raw: float) -> tuple[dict | None, str]:
        long, stop = order["side"] == "long", float(order["stop"])
        entry = raw * (1 + self.slip) if long else raw * (1 - self.slip)
        if (long and entry <= stop) or (not long and entry >= stop):
            return None, f"Fill at {entry:.2f} would sit beyond the stop {stop:.2f}; order cancelled."
        risk_unit = abs(entry - stop)
        qty = position_size(self.one_r_eff, risk_unit, self.lot)
        if qty < max(1, self.lot):
            return None, f"Rupee risk per unit {risk_unit:.2f} at the fill sizes below one lot; order cancelled."
        sig_i = self._index_of(order.get("signal_ts"), default=max(0, self.i - 1))
        targets = target_prices(self.spec, entry, stop, order["side"], self.inputs, sig_i, self.bars)
        min_rr = self.spec.risk.min_rr_after_costs
        if targets and min_rr > 0:
            est = round_trip_cost(entry, targets[0], qty, self.segment, self.cost_params).total
            rr = (abs(targets[0] - entry) * qty - est) / (risk_unit * qty)
            if rr < min_rr:
                return None, f"Post-cost R:R at the fill is {rr:.2f}, below your minimum {min_rr:g}; order cancelled."
        pos = {
            "side": order["side"],
            "entry": entry,
            "raw_entry": raw,
            "planned_entry": float(order.get("planned_entry", raw)),
            "stop": stop,
            "initial_stop": stop,
            "risk_unit": risk_unit,
            "qty": int(qty),
            "targets": [float(t) for t in targets],
            "entry_ts": iso(self.bar_ts),
            "signal_ts": order.get("signal_ts"),
            "regime": str(order.get("regime", "range")),
            "bars_held": 0,
            "max_h": entry,
            "min_l": entry,
            "slippage": abs(entry - raw),
            "opened_at": iso(self.bar_ts),
        }
        trade = m.PaperTrade(
            user_id=self.w.user_id,
            strategy_id=self.strat.id,
            watcher_id=self.w.id,
            symbol=self.symbol,
            side=order["side"],
            qty=int(qty),
            planned={
                "entry": round(pos["planned_entry"], 2),
                "stop": round(stop, 2),
                "targets": [round(float(t), 2) for t in order.get("targets", targets)],
                "risk_r": round(qty * risk_unit / self.one_r, 4) if self.one_r else 1.0,
            },
            actual={"entry": round(entry, 2), "exit": None, "entry_ts": iso(self.bar_ts), "exit_ts": None},
            slippage=round(abs(entry - raw), 4),
            costs=0.0,
            regime=pos["regime"],
            rules_followed=self.rules_total,
            rules_total=self.rules_total,
            status="open",
            opened_at=self.bar_ts.to_pydatetime(),
        )
        self.s.add(trade)
        self.s.flush()
        pos["trade_id"] = trade.id
        return pos, ""

    def _index_of(self, ts_iso: str | None, default: int) -> int:
        if not ts_iso:
            return default
        hits = self.bars.index[self.bars["ts"] == pd.Timestamp(ts_iso)]
        return int(hits[0]) if len(hits) else default

    def _last_of_day(self) -> bool:
        return self.bar_ts + pd.Timedelta(minutes=self.tf_min) >= self.bar_ts.normalize() + _CLOSE

    def check_exit(self, p: dict) -> tuple[float, str] | None:
        i, b = self.i, self.bars
        o, h, lo, c = (_f(b[k].iloc[i]) for k in ("open", "high", "low", "close"))
        long, stop = p["side"] == "long", float(p["stop"])
        p["bars_held"] = int(p.get("bars_held", 0)) + 1
        p["max_h"], p["min_l"] = max(float(p["max_h"]), h), min(float(p["min_l"]), lo)
        reason = "stop" if stop == float(p["initial_stop"]) else "trailing_stop"
        if long and lo <= stop:
            return (o if o <= stop else stop), reason
        if not long and h >= stop:
            return (o if o >= stop else stop), reason
        if p["targets"]:
            tgt = float(p["targets"][0])
            if long and h >= tgt:
                return (o if o >= tgt else tgt), "target"
            if not long and lo <= tgt:
                return (o if o <= tgt else tgt), "target"
        if str(self.spec.trailing.type) != "none":
            p["stop"] = float(
                trailing_stop(self.spec, b, i, p["side"], float(p["entry"]), stop, float(p["risk_unit"]), self.inputs)
            )
        max_bars = self.spec.time_exit.max_bars
        if max_bars and p["bars_held"] >= max_bars:
            return c, "max_bars"
        mod = self.bar_ts.hour * 60 + self.bar_ts.minute
        if self.spec.time_exit.at_time and not self.daily and mod >= _hhmm(self.spec.time_exit.at_time):
            return c, "time_exit"
        if self.spec.session.flat_at_close and not self.daily and self._last_of_day():
            return c, "flat_at_close"
        return None

    def close_position(self, p: dict, raw: float, reason: str) -> dict:
        long, qty = p["side"] == "long", int(p["qty"])
        entry = float(p["entry"])
        exit_ = raw * (1 - self.slip) if long else raw * (1 + self.slip)
        gross = (exit_ - entry) * qty if long else (entry - exit_) * qty
        buy, sell = (entry, exit_) if long else (exit_, entry)
        costs = round_trip_cost(buy, sell, qty, self.segment, self.cost_params).statutory_total
        net = gross - costs
        risk_unit = float(p["risk_unit"])
        mfe = (float(p["max_h"]) - entry) if long else (entry - float(p["min_l"]))
        mae = (entry - float(p["min_l"])) if long else (float(p["max_h"]) - entry)
        outcome_r = net / (risk_unit * qty)
        trade = self.s.get(m.PaperTrade, p.get("trade_id"))
        if trade is not None:
            trade.actual = dict(trade.actual or {}) | {"exit": round(exit_, 2), "exit_ts": iso(self.bar_ts)}
            trade.slippage = round(float(p.get("slippage", 0.0)) + abs(exit_ - raw), 4)
            trade.costs = round(float(costs), 2)
            trade.mfe_r = round(max(mfe, 0.0) / risk_unit, 4)
            trade.mae_r = round(max(mae, 0.0) / risk_unit, 4)
            trade.exit_reason = reason
            trade.outcome_r = round(float(outcome_r), 4)
            trade.status = "closed"
            trade.closed_at = self.bar_ts.to_pydatetime()
        return {"exit": exit_, "outcome_r": outcome_r, "costs": costs, "net": net}

    # -- the bar --------------------------------------------------------------------------------
    def run(self) -> None:
        w, ctx = self.w, self.ctx
        state = ExecState(w.exec_state)
        fresh_cycle = state in TERMINAL
        if fresh_cycle:
            state = ExecState.WATCHING
        pos, order = ctx.get("position"), ctx.get("order")

        if state is ExecState.ORDER_PENDING:
            if not order:
                self.move(ExecState.WATCHING, "No order in the watcher context; watching again.")
                state = ExecState.WATCHING
            else:
                raw = self.try_fill(order)
                ctx["order"] = None
                if raw is None:
                    self.move(ExecState.WATCHING, "Order not filled within one bar; cancelled.")
                    state = ExecState.WATCHING
                else:
                    pos, why = self.open_position(order, raw)
                    if pos is None:
                        self.move(ExecState.WATCHING, why)
                        state = ExecState.WATCHING
                    else:
                        ctx["position"] = pos
                        self.move(ExecState.OPEN, f"Filled at {pos['entry']:.2f}; stop {pos['stop']:.2f}.", self._fill_sentence(pos))
                        state = ExecState.OPEN

        if state is ExecState.OPEN:
            if not pos:
                self.move(ExecState.BLOCKED, "Position context was lost; the cycle is closed without a fill.")
                state = ExecState.BLOCKED
            else:
                hit = self.check_exit(pos)
                if hit is None:
                    ctx["position"] = pos
                    w.state_reason = f"Open on the {pos['side']} side at {pos['entry']:.2f}; stop {pos['stop']:.2f}, {pos['bars_held']} bars held."
                    w.updated_at = self.now
                else:
                    raw, reason = hit
                    self.move(ExecState.EXIT_PENDING, f"Exit by {reason}.", f"Exit signalled by {reason.replace('_', ' ')} on the {self.bar_ts:%H:%M} bar.")
                    res = self.close_position(pos, raw, reason)
                    ctx["position"] = None
                    self.move(
                        ExecState.CLOSED,
                        f"Closed by {reason}: {res['outcome_r']:+.2f}R.",
                        f"Paper exit on the {pos['side']} side at {res['exit']:.2f} ({reason.replace('_', ' ')}): "
                        f"{res['outcome_r']:+.2f}R after costs of {res['costs']:.0f}.",
                    )
                    state = ExecState.CLOSED
                    rs = risk.status_obj(self.s, w.user_id, self.now)
                    if rs.brakes["daily"] and res["outcome_r"] < 0:
                        p = behaviour.on_daily_brake(self.s, w.user_id, self.now)
                        self.events.append({"kind": "behaviour", "ts": iso(self.now), "user_id": w.user_id, "to": p.behaviour_state, "reason": p.state_reason})

        if state in (ExecState.SETUP_FOUND, ExecState.ARMED):
            self.move(ExecState.WATCHING, "Setup from an earlier bar expired; watching again.")
            state = ExecState.WATCHING

        if state is ExecState.WATCHING:
            sig = self.base()
            side = sig["side"]
            if sig["verdict"] in ("eligible", "blocked") and side:
                self.move(ExecState.SETUP_FOUND, f"{side.capitalize()} setup on the {self.bar_ts:%H:%M} bar: {'; '.join(sig['conditions_passed'])}.")
                if sig["verdict"] == "eligible" and can_open_positions(self.profile.behaviour_state) and sig["stop"] is not None and sig["quantity"] > 0:
                    self.move(ExecState.ARMED, "Every gate passes.")
                    i, b = self.i, self.bars
                    order = {
                        "side": side,
                        "stop": float(sig["stop"]),
                        "targets": list(sig["targets"]),
                        "qty": int(sig["quantity"]),
                        "signal_ts": iso(self.bar_ts),
                        "sig_high": _f(b["high"].iloc[i]),
                        "sig_low": _f(b["low"].iloc[i]),
                        "sig_close": _f(b["close"].iloc[i]),
                        "planned_entry": float(sig["trigger"]["price"] or _f(b["close"].iloc[i])),
                        "regime": sig["regime"],
                    }
                    if str(self.spec.trigger.type) == "bar_close":
                        self.move(ExecState.ORDER_PENDING, "Idealised fill at the signal bar's close.", self._order_sentence(order))
                        pos, why = self.open_position(order, order["sig_close"])
                        if pos is None:
                            self.move(ExecState.WATCHING, why)
                        else:
                            ctx["position"] = pos
                            self.move(ExecState.OPEN, f"Filled at {pos['entry']:.2f}; stop {pos['stop']:.2f}.", self._fill_sentence(pos))
                    else:
                        ctx["order"] = order
                        self.move(ExecState.ORDER_PENDING, f"Order placed for the next bar: {sig['trigger']['description']}", self._order_sentence(order))
                else:
                    red = [g for g in sig["gates"] if not g["pass"]]
                    reason = red[0].get("reason", red[0]["name"] + " failed.") if red else "Behavioural state does not allow entries."
                    self.move(ExecState.BLOCKED, reason)
            else:
                if fresh_cycle:
                    self.move(ExecState.WATCHING, "Watching for the next closed bar.")
                else:
                    red = [g for g in sig["gates"] if not g["pass"]]
                    w.state_reason = "Watching: " + (red[0].get("reason", "no setup on the last closed bar.") if red else "no setup on the last closed bar.")
                    w.updated_at = self.now

        w.context = ctx
        flag_modified(w, "context")

    def _order_sentence(self, order: dict) -> str:
        return (
            f"Order placed on the {order['side']} side: {order['qty']} {self.symbol}, "
            f"{self.spec.trigger.type.value.replace('_', ' ')}, stop {order['stop']:.2f}."
        )

    def _fill_sentence(self, pos: dict) -> str:
        tg = ", ".join(f"{t:.2f}" for t in pos["targets"]) or "none"
        return (
            f"Paper fill on the {pos['side']} side: {pos['qty']} {self.symbol} at {pos['entry']:.2f} "
            f"(raw {pos['raw_entry']:.2f}, slippage {self.cost_params.slippage_bps:g} bps). Stop {pos['stop']:.2f}, targets {tg}."
        )


# --- the step -------------------------------------------------------------------------------------


def paper_watchers(session: Session) -> list[tuple[m.Watcher, m.Strategy]]:
    out = []
    for w in session.query(m.Watcher).order_by(m.Watcher.updated_at).all():
        strat = session.get(m.Strategy, w.strategy_id)
        if strat is None or (strat.spec or {}).get("automation_permission") != "paper_only":
            continue
        if not (strat.spec or {}).get("instruments"):
            continue
        out.append((w, strat))
    return out


def evaluate_watcher(session: Session, w: m.Watcher, strat: m.Strategy, now: datetime, events: list[dict]) -> bool:
    """Evaluate one watcher at `now`. Returns True when a new closed bar was processed."""
    tf = str((strat.spec or {}).get("timeframe", "5m"))
    tf_min = TF_MINUTES.get(tf, 5)
    ctx = w.context or {}
    if ctx.get("last_evaluated_ts") and not may_have_closed(now, tf_min):
        return False
    symbol = str(strat.spec["instruments"][0])
    bars = closed_bars(market.provider(), symbol, tf, now)
    if len(bars) < MIN_BARS:
        return False
    last_ts = iso(bars["ts"].iloc[-1])
    if ctx.get("last_evaluated_ts") == last_ts:
        return False
    cycle = _Cycle(session, w, strat, bars, now, events)
    cycle.ctx["last_evaluated_ts"] = last_ts
    cycle.run()
    return True


def step(session: Session, n_bars: int = 1) -> dict:
    events: list[dict] = []
    now = clock.now(session)
    for _ in range(max(1, int(n_bars))):
        prev, now = now, clock.advance(session, 1)
        was_open, is_open = clock.market_open(prev), clock.market_open(now)
        if is_open and not was_open:
            for uid in behaviour.onboarded_user_ids(session):
                p = behaviour.on_open(session, uid, now)
                events.append({"kind": "behaviour", "ts": iso(now), "user_id": uid, "to": p.behaviour_state, "reason": p.state_reason, "event": "session_open"})
        elif was_open and not is_open:
            for uid in behaviour.onboarded_user_ids(session):
                p = behaviour.on_close(session, uid, now)
                events.append({"kind": "behaviour", "ts": iso(now), "user_id": uid, "to": p.behaviour_state, "reason": p.state_reason, "event": "session_close"})
        for w, strat in paper_watchers(session):
            try:
                evaluate_watcher(session, w, strat, now, events)
            except Exception as e:
                if STRICT:
                    raise
                log.exception("watcher %s (%s) failed at %s", w.id, strat.id, now)
                events.append({"kind": "error", "ts": iso(now), "watcher_id": w.id, "strategy_id": strat.id, "error": f"{type(e).__name__}: {e}"})
        session.flush()
    return {"sim_now": iso(now), "market_open": clock.market_open(now), "events": events}


__all__ = ["closed_bars", "evaluate_watcher", "may_have_closed", "paper_watchers", "signal_id", "step"]
