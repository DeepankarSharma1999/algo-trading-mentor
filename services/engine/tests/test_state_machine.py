from itertools import product

import pytest

from engine.exec import (
    TERMINAL,
    TRANSITIONS,
    ExecState,
    IllegalTransition,
    Position,
    can_transition,
    transition,
)

ALLOWED = {
    (ExecState.WATCHING, ExecState.SETUP_FOUND),
    (ExecState.SETUP_FOUND, ExecState.ARMED),
    (ExecState.SETUP_FOUND, ExecState.WATCHING),
    (ExecState.ARMED, ExecState.ORDER_PENDING),
    (ExecState.ARMED, ExecState.WATCHING),
    (ExecState.ORDER_PENDING, ExecState.OPEN),
    (ExecState.ORDER_PENDING, ExecState.WATCHING),
    (ExecState.OPEN, ExecState.EXIT_PENDING),
    (ExecState.OPEN, ExecState.CLOSED),
    (ExecState.EXIT_PENDING, ExecState.CLOSED),
} | {(s, ExecState.BLOCKED) for s in ExecState if s not in TERMINAL}


def test_table_matches_expected_exactly():
    assert {(a, b) for a, targets in TRANSITIONS.items() for b in targets} == ALLOWED
    assert set(TRANSITIONS) == set(ExecState)


@pytest.mark.parametrize("pair", list(product(ExecState, ExecState)), ids=lambda p: f"{p[0]}->{p[1]}")
def test_every_pair(pair):
    a, b = pair
    pos = Position("s_v1", "RELIANCE", state=a)
    if (a, b) in ALLOWED:
        assert can_transition(a, b)
        tr = transition(pos, b, "because", {"close > ema20": True})
        assert pos.state == b and pos.history == [tr]
        assert (tr.from_state, tr.to_state, tr.reason) == (a, b, "because")
        assert tr.conditions == {"close > ema20": True}
    else:
        assert not can_transition(a, b)
        with pytest.raises(IllegalTransition):
            transition(pos, b, "nope")
        assert pos.state == a and pos.history == []


def test_blocked_reachable_from_every_non_terminal_only():
    for s in ExecState:
        assert can_transition(s, ExecState.BLOCKED) == (s not in TERMINAL)
    assert TRANSITIONS[ExecState.CLOSED] == set() and TRANSITIONS[ExecState.BLOCKED] == set()


def test_happy_path_journal_and_opened_at():
    pos = Position("s_v1", "RELIANCE")
    path = ["SETUP_FOUND", "ARMED", "ORDER_PENDING", "OPEN", "EXIT_PENDING", "CLOSED"]
    for step in path:
        transition(pos, step, step.lower())
    assert [t.to_state for t in pos.history] == [ExecState(s) for s in path]
    assert pos.opened_at == pos.history[3].ts
    assert pos.state is ExecState.CLOSED
