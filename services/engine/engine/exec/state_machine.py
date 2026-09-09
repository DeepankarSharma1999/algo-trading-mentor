"""Execution state machine for one position / watcher cycle.

WATCHING -> SETUP_FOUND -> ARMED -> ORDER_PENDING -> OPEN -> EXIT_PENDING -> CLOSED, with early
returns to WATCHING when a setup evaporates or an order is cancelled, and BLOCKED reachable from
every non-terminal state. CLOSED and BLOCKED are terminal: a new cycle is a new Position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ExecState(StrEnum):
    WATCHING = "WATCHING"
    SETUP_FOUND = "SETUP_FOUND"
    ARMED = "ARMED"
    ORDER_PENDING = "ORDER_PENDING"
    OPEN = "OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"


TERMINAL: frozenset[ExecState] = frozenset({ExecState.CLOSED, ExecState.BLOCKED})

TRANSITIONS: dict[ExecState, set[ExecState]] = {
    ExecState.WATCHING: {ExecState.SETUP_FOUND},
    ExecState.SETUP_FOUND: {ExecState.ARMED, ExecState.WATCHING},
    ExecState.ARMED: {ExecState.ORDER_PENDING, ExecState.WATCHING},
    ExecState.ORDER_PENDING: {ExecState.OPEN, ExecState.WATCHING},
    ExecState.OPEN: {ExecState.EXIT_PENDING, ExecState.CLOSED},
    ExecState.EXIT_PENDING: {ExecState.CLOSED},
    ExecState.CLOSED: set(),
    ExecState.BLOCKED: set(),
}
for _s in ExecState:
    if _s not in TERMINAL:
        TRANSITIONS[_s].add(ExecState.BLOCKED)


class IllegalTransition(Exception):
    def __init__(self, from_state: ExecState, to_state: ExecState) -> None:
        super().__init__(f"illegal transition {from_state} -> {to_state}")
        self.from_state, self.to_state = from_state, to_state


@dataclass(frozen=True)
class Transition:
    from_state: ExecState
    to_state: ExecState
    ts: datetime
    reason: str
    conditions: dict[str, Any]


@dataclass
class Position:
    strategy_id: str
    symbol: str
    side: str | None = None  # "long" | "short" | None before a setup
    qty: int = 0
    entry: float | None = None
    stop: float | None = None
    targets: list[float] = field(default_factory=list)
    opened_at: datetime | None = None
    state: ExecState = ExecState.WATCHING
    history: list[Transition] = field(default_factory=list)


def can_transition(from_state: ExecState, to_state: ExecState) -> bool:
    return to_state in TRANSITIONS[from_state]


def transition(
    pos: Position,
    to: ExecState | str,
    reason: str,
    conditions: dict[str, Any] | None = None,
    ts: datetime | None = None,
) -> Transition:
    """Move pos to `to`, journaling the step. Raises IllegalTransition on a disallowed move."""
    to = ExecState(to)
    if not can_transition(pos.state, to):
        raise IllegalTransition(pos.state, to)
    tr = Transition(pos.state, to, ts or datetime.now(UTC), reason, dict(conditions or {}))
    pos.history.append(tr)
    pos.state = to
    if to is ExecState.OPEN and pos.opened_at is None:
        pos.opened_at = tr.ts
    return tr
