"""The shared testable-validator, Python twin of packages/schema/src/testable.ts.

Rules come from packages/schema/testable.rules.json; this only interprets them."""

import json
from functools import lru_cache
from typing import Any

from engine import config


@lru_cache(maxsize=1)
def _rules() -> list[dict]:
    return json.loads((config.SCHEMA_DIR / "testable.rules.json").read_text())["rules"]


def _resolve(doc: Any, pointer: str) -> Any:
    cur = doc
    for seg in pointer.split("/")[1:]:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(seg)
    return cur


def _present(v: Any, not_: Any = None) -> bool:
    if v is None or v == "" or (isinstance(v, list) and not v):
        return False
    return not (not_ is not None and v == not_)


def check_testable(spec: dict) -> dict:
    """Returns {"testable": bool, "missing": [sentence], "missing_ids": [rule id]}."""
    missing, ids = [], []
    for rule in _rules():
        values = [_resolve(spec, p["path"]) for p in rule["paths"]]
        if rule["kind"] == "present_any":
            ok = any(_present(v, p.get("not")) for v, p in zip(values, rule["paths"], strict=True))
        else:
            ok = not _present(values[0])
        if not ok:
            vals = "; ".join(map(str, values[0])) if isinstance(values[0], list) else str(values[0] or "")
            missing.append(rule["missing"].replace("{values}", vals))
            ids.append(rule["id"])
    return {"testable": not missing, "missing": missing, "missing_ids": ids}
