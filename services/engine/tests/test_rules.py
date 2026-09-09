import numpy as np
import pandas as pd
import pytest

from engine import indicators as ind
from engine.rules import (
    condition_series,
    conditions_trace,
    evaluate,
    parse_operand,
    render_condition,
    resolve_operand,
    stop_price,
    target_prices,
    trailing_stop,
)
from engine.rules.operands import ParsedOperand
from engine.schema.strategy import Condition
from tests.conftest import base_spec, ema_cross_spec, make_bars, session_timestamps


def frame(closes):
    n = len(closes)
    c = np.array(closes, dtype=float)
    return pd.DataFrame(
        {"ts": session_timestamps(n), "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": np.full(n, 100.0)}
    )


def cond(lhs, op, rhs=0, lookback=None):
    return Condition.model_validate({"lhs": lhs, "op": op, "rhs": rhs, "lookback": lookback})


def series(b, computed, *args, **kw):
    return condition_series(cond(*args, **kw), b, computed).tolist()


def test_parse_operand_grammar():
    assert parse_operand("close") == ParsedOperand("close", None, 0)
    assert parse_operand("bb.upper[-3]") == ParsedOperand("bb", "upper", 3)
    assert parse_operand(2.5) == 2.5
    assert parse_operand("ema20[-50]").lag == 50
    with pytest.raises(ValueError):
        parse_operand("ema20[-51]")
    with pytest.raises(ValueError):
        parse_operand("ema20[1]")
    with pytest.raises(ValueError):
        parse_operand("Bad-Name")


def test_resolve_operand_fields_and_lag():
    b = frame([1, 2, 3, 4])
    computed = {"e": pd.Series([1.0, 1.5, 2.0, 2.5]), "bb": pd.DataFrame({"upper": [5.0, 6.0, 7.0, 8.0]})}
    assert resolve_operand("close[-1]", b, computed).tolist()[1:] == [1, 2, 3]
    assert resolve_operand("bb.upper", b, computed).tolist() == [5, 6, 7, 8]
    assert resolve_operand(3, b, computed) == 3.0
    with pytest.raises(ValueError):
        resolve_operand("bb", b, computed)
    with pytest.raises(ValueError):
        resolve_operand("e.x", b, computed)
    with pytest.raises(KeyError):
        resolve_operand("nope", b, computed)


def test_comparison_ops():
    b = frame([1, 2, 3, 2, 3])
    assert series(b, {}, "close", ">", 2) == [False, False, True, False, True]
    assert series(b, {}, "close", "<", 2) == [True, False, False, False, False]
    assert series(b, {}, "close", ">=", 2) == [False, True, True, True, True]
    assert series(b, {}, "close", "<=", 2) == [True, True, False, True, False]
    assert series(b, {}, "close", "==", 2) == [False, True, False, True, False]
    assert series(b, {}, "close", ">", "close[-1]") == [False, True, True, False, True]


def test_crosses_default_lookback_is_one_bar():
    b = frame([1, 2, 3, 2, 3])
    assert series(b, {}, "close", "crosses_above", 2.5) == [False, False, True, False, True]
    assert series(b, {}, "close", "crosses_below", 2.5) == [False, False, False, True, False]
    # touching then leaving counts: <= at t-1, > at t
    b2 = frame([2.5, 3])
    assert series(b2, {}, "close", "crosses_above", 2.5) == [False, True]


def test_crosses_with_lookback_window():
    b = frame([1, 3, 3, 3, 3])
    assert series(b, {}, "close", "crosses_above", 2) == [False, True, False, False, False]
    assert series(b, {}, "close", "crosses_above", 2, lookback=3) == [False, True, True, True, False]


def test_rising_and_falling_strict():
    b = frame([1, 2, 3, 4, 3, 3, 2, 1])
    assert series(b, {}, "close", "rising") == [False, False, False, True, False, False, False, False]
    assert series(b, {}, "close", "rising", lookback=2) == [False, False, True, True, False, False, False, False]
    assert series(b, {}, "close", "falling", lookback=2) == [False] * 7 + [True]


def test_nan_inputs_evaluate_false():
    b = frame([1, 2, 3, 4, 5, 6])
    computed = {"s": ind.sma(b, 3)}
    assert series(b, computed, "close", ">", "s") == [False, False, True, True, True, True]


def test_render_condition_and_trace():
    assert render_condition(cond("close", "crosses_above", "ema20")) == "close crosses_above ema20"
    assert render_condition(cond("close", "crosses_above", "ema20", lookback=3)) == "close crosses_above ema20 within 3"
    assert render_condition(cond("bb.upper[-1]", ">", 100.5)) == "bb.upper[-1] > 100.5"
    assert render_condition(cond("ema20", "rising")) == "ema20 rising over 3"
    spec = base_spec(entry_long=[{"lhs": "close", "op": ">", "rhs": "ema20"}, {"lhs": "close", "op": "rising", "rhs": 0}])
    ev = evaluate(spec, make_bars(80, seed=1))
    row = ev.iloc[-1]
    passed, failed = conditions_trace(spec, row)
    assert set(passed) | set(failed) == {"close > ema20", "close rising over 3"}
    assert all(row[p] for p in passed) and not any(row[f] for f in failed)


def test_evaluate_shape_and_closed_bar_semantics():
    b = make_bars(400, seed=2)
    spec = ema_cross_spec()
    ev = evaluate(spec, b)
    assert list(ev.columns[:5]) == ["ts", "long_setup", "short_setup", "regime", "regime_ok"]
    assert "fast crosses_above slow" in ev.columns and "fast crosses_below slow" in ev.columns
    assert ev["long_setup"].sum() > 0 and not (ev["long_setup"] & ev["short_setup"]).any()
    k = 250
    b2 = b.copy()
    for col in ("open", "high", "low", "close"):
        b2.loc[b2.index > k, col] *= 1.05
    ev2 = evaluate(spec, b2)
    pd.testing.assert_frame_equal(ev.iloc[: k + 1], ev2.iloc[: k + 1])


def test_regime_ok_follows_affinity():
    b = make_bars(300, seed=2)
    ev = evaluate(ema_cross_spec(regime_affinity=["event"]), b)
    assert not ev["regime_ok"].any()
    ev = evaluate(ema_cross_spec(regime_affinity=[]), b)
    assert ev["regime_ok"].all()


def test_stop_price_every_type():
    b = make_bars(200, seed=4)
    computed = ind.compute_inputs(b, ema_cross_spec()["inputs"])
    i = 150
    close, low, high = (float(b[c].iloc[i]) for c in ("close", "low", "high"))
    s = stop_price(ema_cross_spec(stop={"type": "signal_bar", "params": {"buffer_pct": 1}}), b, i, "long", computed)
    assert s == pytest.approx(low * 0.99)
    s = stop_price(ema_cross_spec(stop={"type": "signal_bar", "params": {}}), b, i, "short", computed)
    assert s == pytest.approx(high)
    s = stop_price(ema_cross_spec(stop={"type": "fixed_pct", "params": {"pct": 2}}), b, i, "long", computed)
    assert s == pytest.approx(close * 0.98)
    a = float(ind.atr(b, 14).iloc[i])
    s = stop_price(ema_cross_spec(stop={"type": "atr", "params": {"length": 14, "mult": 1.5}}), b, i, "short", computed)
    assert s == pytest.approx(close + 1.5 * a)
    sw = ind.swing(b, 5)
    s = stop_price(ema_cross_spec(stop={"type": "swing", "params": {"lookback": 5}}), b, i, "long", computed)
    assert s is None or s == pytest.approx(float(sw["low"].iloc[i]))
    s = stop_price(ema_cross_spec(stop={"type": "indicator", "params": {"ref": "slow"}}), b, i, "long", computed)
    slow = float(computed["slow"].iloc[i])
    assert s == (pytest.approx(slow) if slow < close else None)
    # wrong side is refused
    s = stop_price(ema_cross_spec(stop={"type": "indicator", "params": {"ref": "high"}}), b, i, "long", computed)
    assert s is None
    assert stop_price(ema_cross_spec(stop=None), b, i, "long", computed) is None


def test_target_prices_and_trailing():
    b = make_bars(100, seed=4)
    computed = ind.compute_inputs(b, ema_cross_spec()["inputs"])
    spec = ema_cross_spec(
        targets=[{"type": "rr", "value": 2}, {"type": "fixed_pct", "value": 1}, {"type": "indicator", "value": 0, "ref": "slow"}]
    )
    t = target_prices(spec, 100.0, 98.0, "long", computed, 50, b)
    assert t[:2] == [pytest.approx(104.0), pytest.approx(101.0)]
    slow = float(computed["slow"].iloc[50])
    assert (slow in t) == (slow > 100.0)
    t = target_prices(spec, 100.0, 102.0, "short", computed, 50, b)
    assert t[:2] == [pytest.approx(96.0), pytest.approx(99.0)]
    # trailing never loosens
    be = ema_cross_spec(trailing={"type": "breakeven_after_r", "params": {"r": 1}})
    i = 60
    close = float(b["close"].iloc[i])
    assert trailing_stop(be, b, i, "long", close - 5, close - 10, 5.0, computed) == pytest.approx(close - 5)
    assert trailing_stop(be, b, i, "long", close + 5, close - 10, 5.0, computed) == close - 10
    at = ema_cross_spec(trailing={"type": "atr", "params": {"length": 14, "mult": 1}})
    a = float(ind.atr(b, 14).iloc[i])
    assert trailing_stop(at, b, i, "long", close - 50, close - 100, 50.0, computed) == pytest.approx(close - a)
    assert trailing_stop(at, b, i, "long", close - 50, close, 50.0, computed) == close
    assert trailing_stop(ema_cross_spec(), b, i, "long", 1.0, 0.5, 0.5, computed) == 0.5
