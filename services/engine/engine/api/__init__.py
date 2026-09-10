"""HTTP routers (ARCHITECTURE section 4). Each module exposes a `router`."""

from engine.api import behaviour, desk, journal, mentor, risk, sim, strategies

ROUTERS = [strategies.router, desk.router, journal.router, behaviour.router, risk.router, mentor.router, sim.router]

__all__ = ["ROUTERS"]
