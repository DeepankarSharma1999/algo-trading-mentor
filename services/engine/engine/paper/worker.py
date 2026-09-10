"""`python -m engine.paper.worker`: advance the sim clock `speed` bars every real second while it is running."""

from __future__ import annotations

import logging
import time

from engine import config, db
from engine.paper import simulator
from engine.services import clock, market

log = logging.getLogger("paper.worker")


def tick() -> dict | None:
    with db.session() as s:
        c = clock.get(s)
        if not c.running:
            return None
        return simulator.step(s, max(1, int(c.speed)))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        log.info("paper worker: provider %s, symbols %s", market.provider().name, ",".join(market.provider().symbols()))
    except Exception as e:
        log.warning("paper worker: provider not ready: %s", e)
    log.info("paper worker: database %s, PAPER_SPEED %s", config.DATABASE_URL.split("@")[-1], config.PAPER_SPEED)
    while True:
        t0 = time.monotonic()
        try:
            res = tick()
            if res:
                for e in res["events"]:
                    if e["kind"] == "exec":
                        log.info("%s %s %s: %s -> %s (%s)", e["ts"], e["strategy_id"], e["symbol"], e["from"], e["to"], e["reason"])
                    elif e["kind"] == "behaviour":
                        log.info("%s behaviour %s -> %s (%s)", e["ts"], e["user_id"], e["to"], e["reason"])
                    else:
                        log.warning("%s %s", e["ts"], e)
        except Exception:
            log.exception("paper step failed; retrying next second")
        time.sleep(max(0.0, 1.0 - (time.monotonic() - t0)))


if __name__ == "__main__":
    main()
