"""Operand grammar: `name`, `name.field`, `name[-k]`, `name.field[-k]`, a bar field, or a number.

`[-k]` reads the value k closed bars ago (k <= MAX_LAG). A positive index would be look-ahead and
is rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

BAR_FIELDS: frozenset[str] = frozenset({"open", "high", "low", "close", "volume"})
MAX_LAG = 50
_OPERAND = re.compile(r"^([a-z][a-z0-9_]*)(?:\.([a-z0-9_]+))?(?:\[(-?[0-9]+)\])?$")

Computed = dict[str, pd.Series | pd.DataFrame]


@dataclass(frozen=True)
class ParsedOperand:
    name: str
    field: str | None
    lag: int  # bars ago, >= 0

    def render(self) -> str:
        s = self.name if self.field is None else f"{self.name}.{self.field}"
        return f"{s}[-{self.lag}]" if self.lag else s


def operand_value(operand) -> str | float:
    """Unwrap the pydantic Operand root model (or pass through a raw str/number)."""
    while hasattr(operand, "root"):
        operand = operand.root
    return operand


def parse_operand(operand) -> ParsedOperand | float:
    raw = operand_value(operand)
    if isinstance(raw, bool):
        raise ValueError("boolean is not a valid operand")
    if isinstance(raw, int | float):
        return float(raw)
    m = _OPERAND.match(raw)
    if not m:
        raise ValueError(f"malformed operand {raw!r}")
    name, field, lag = m.group(1), m.group(2), int(m.group(3) or 0)
    if lag > 0:
        raise ValueError(f"operand {raw!r} indexes a future bar; only [-k] is allowed")
    if -lag > MAX_LAG:
        raise ValueError(f"operand {raw!r} looks back more than {MAX_LAG} bars")
    return ParsedOperand(name, field, -lag)


def render_operand(operand) -> str:
    p = parse_operand(operand)
    return f"{p:g}" if isinstance(p, float) else p.render()


def resolve_operand(operand, bars: pd.DataFrame, computed: Computed) -> pd.Series | float:
    """A float for numeric operands, else a float Series aligned to bars (lagged if requested)."""
    p = parse_operand(operand)
    if isinstance(p, float):
        return p
    if p.name in BAR_FIELDS and p.field is None:
        s = bars[p.name]
    elif p.name in computed:
        obj = computed[p.name]
        if isinstance(obj, pd.DataFrame):
            if p.field is None:
                raise ValueError(f"input {p.name!r} has fields {list(obj.columns)}; pick one with a dot")
            if p.field not in obj.columns:
                raise ValueError(f"input {p.name!r} has no field {p.field!r}")
            s = obj[p.field]
        else:
            if p.field is not None:
                raise ValueError(f"input {p.name!r} is single-valued; drop .{p.field}")
            s = obj
    else:
        raise KeyError(f"unknown operand {p.render()!r}")
    s = s.astype(float)
    return s.shift(p.lag) if p.lag else s


def referenced_inputs(operand) -> str | None:
    p = parse_operand(operand)
    if isinstance(p, float) or (p.name in BAR_FIELDS and p.field is None):
        return None
    return p.name
