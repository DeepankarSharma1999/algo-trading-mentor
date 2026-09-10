"""Journal rows (paper_trades -> PaperTrade dicts) and the aggregates the Journal screen shows."""

from __future__ import annotations

from sqlalchemy.orm import Session

from engine.db import models as m
from engine.services.common import iso


def trade_dict(t: m.PaperTrade) -> dict:
    return {
        "id": t.id,
        "strategy_id": t.strategy_id,
        "symbol": t.symbol,
        "side": t.side,
        "qty": int(t.qty),
        "planned": dict(t.planned or {}),
        "actual": dict(t.actual or {}),
        "slippage": float(t.slippage or 0.0),
        "costs": float(t.costs or 0.0),
        "mfe_r": t.mfe_r,
        "mae_r": t.mae_r,
        "exit_reason": t.exit_reason,
        "regime": t.regime,
        "outcome_r": t.outcome_r,
        "rules_followed": int(t.rules_followed or 0),
        "rules_total": int(t.rules_total or 0),
        "status": t.status,
        "opened_at": iso(t.opened_at),
        "closed_at": iso(t.closed_at),
    }


def trades(session: Session, user_id: str) -> list[dict]:
    rows = (
        session.query(m.PaperTrade)
        .filter(m.PaperTrade.user_id == user_id)
        .order_by(m.PaperTrade.opened_at.desc())
        .all()
    )
    return [trade_dict(t) for t in rows]


def _process(rows: list[dict]) -> float:
    """Share of rules followed across trades, 0..1."""
    tot = sum(r["rules_total"] for r in rows)
    return round(sum(r["rules_followed"] for r in rows) / tot, 4) if tot else 0.0


def aggregates(trade_rows: list[dict]) -> dict:
    closed = [t for t in trade_rows if t["status"] == "closed" and t.get("outcome_r") is not None]
    by_regime: dict[str, dict] = {}
    for reg in sorted({t["regime"] for t in closed}):
        rows = [t for t in closed if t["regime"] == reg]
        by_regime[reg] = {
            "trades": len(rows),
            "process_score": _process(rows),
            "net_r": round(sum(t["outcome_r"] for t in rows), 4),
        }
    ordered = sorted(closed, key=lambda t: (t.get("closed_at") or "", t["id"]))
    current = longest_win = longest_loss = 0
    run = 0
    for t in ordered:
        win = t["outcome_r"] > 0
        if run > 0 and win:
            run += 1
        elif run < 0 and not win:
            run -= 1
        else:
            run = 1 if win else -1
        longest_win = max(longest_win, run)
        longest_loss = max(longest_loss, -run)
    current = run
    wins = sum(1 for t in closed if t["outcome_r"] > 0)
    return {
        "by_regime": by_regime,
        "streaks": {"current": current, "longest_win": longest_win, "longest_loss": longest_loss},
        "totals": {
            "trades": len(closed),
            "net_r": round(sum(t["outcome_r"] for t in closed), 4),
            "process_score": _process(closed),
            "win_rate": round(wins / len(closed), 4) if closed else 0.0,
        },
    }
