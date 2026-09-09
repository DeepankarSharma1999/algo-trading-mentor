# RUNBOOK.md

## Run

```bash
cp infra/.env.example infra/.env   # optional; every value has a working default
docker compose -f infra/docker-compose.yml up --build
```

Then open http://localhost:3000. Sign in with the seeded demo account **demo@atm.local / papertrade**,
or register your own account (you will be taken through the capital firewall first).

Services: web :3000, engine :8000 (`/health`, `/docs` for the OpenAPI UI), postgres on host port
**55432** (5432 inside the network; the host port is unusual on purpose because many machines already
run a local Postgres on 5432), redis :6379 (provisioned, unused in phase 1), and the `paper` worker
(no port; it advances the simulated clock and paper-trades every watched strategy).

Local development without Docker for web and engine:

```bash
docker compose -f infra/docker-compose.yml up -d postgres redis
pnpm install && pnpm --filter web db:push && pnpm --filter web db:seed
pnpm --filter web dev                                   # :3000
cd services/engine && pip install -e ".[dev]" && uvicorn engine.main:app --reload   # :8000
python -m engine.paper.worker                            # paper trader, optional
```

`apps/web/.env` and `services/engine/engine/config.py` default to the local ports above.

## Seed and reset

- The web container runs `prisma db push` and `prisma/seed.mjs` on every start. The seed is
  idempotent: templates are upserted, the demo user is created once (with a validated NIFTY squeeze
  strategy in paper mode, a watcher with a rule trace, 36 closed paper trades and two journal notes),
  the sim clock is created once at 2025-06-12 10:35 IST.
- `make seed` re-runs the seed inside the running web container.
- `make reset` (`docker compose down -v`) drops the database volume. Next `up` recreates everything.
- To re-seed only the demo user: delete it (`DELETE FROM users WHERE email='demo@atm.local'`, cascades)
  and run `make seed`.
- A validation job that was `running` when the engine restarted stays `running` forever. Re-run it
  from the Validation screen ("Re-run validation") or `UPDATE validation_jobs SET status='failed'`.

## The simulated clock

Prices are synthetic, so the app runs on a simulated clock (`sim_clock` table). The paper worker
advances it `PAPER_SPEED` one-minute bars per real second during session hours (09:15–15:30 IST on
synthetic trading days) and jumps to the next session open at close. Market open/closed and the
RESEARCH state derive from this clock. Control it from Settings (pause, resume, speed) or
`POST /sim/clock {"running": false, "speed": 10, "jump_to": "2025-06-13T09:15:00"}`. Data runs
2024-01-01 → 2025-12-31; the clock wraps to 2025-01-01 when it runs off the end.

## Swap the data provider

`DATA_PROVIDER=synthetic` (default) reads `data/SYNTHETIC_<SYMBOL>_1m.parquet`. Regenerate with
`python data/generate.py` (deterministic; ~1 s).

`DATA_PROVIDER=csv` reads `data/csv/<SYMBOL>_1m.csv` with header `ts,open,high,low,close,volume`,
`ts` as `YYYY-MM-DD HH:MM:SS` in IST wall time, one-minute bars, session 09:15–15:29. Higher timeframes
are resampled from 1m. Put your files in `data/csv/` and restart engine and paper.

A real vendor: implement `MarketDataProvider` (`get_bars`, `get_option_chain`, `symbols`) in
`services/engine/engine/data/provider.py` next to `VendorProvider`, register it in `get_provider`, and
set `DATA_PROVIDER=<name>`. Never put vendor credentials in the UI; the engine reads them from the
environment. When the provider is not synthetic the footer drops the "Synthetic data." clause.

## Mentor LLM

Set `ANTHROPIC_API_KEY` (and optionally `ANTHROPIC_MODEL`, default `claude-sonnet-5`) in `infra/.env`.
Without a key every mentor endpoint returns deterministic template prose from
`services/engine/engine/mentor/templates.py`. With a key, replies still pass the guardrail; rejected
replies fall back to the template and are written to `guardrail_log`.

## Checks

```bash
make check          # design lint + eslint + tsc + vitest + ruff + pytest
make e2e            # Playwright happy path against a running stack (http://localhost:3000)
```

CI (`.github/workflows/ci.yml`) runs the same, plus the compose stack and Playwright.

## Security prerequisites before any public deployment

- The engine trusts the `X-User-Id` header. It must stay unreachable from outside the compose network,
  or gain its own auth.
- Set a real `SESSION_SECRET`, serve over HTTPS (cookies are `secure` in production).

## Stubs (see also docs/DECISIONS.md)

- `VendorProvider`: interface only, raises `NotImplementedError`.
- Validation stage 8 (paper agreement) reports `skip` until ≥ 30 closed paper trades exist for the strategy.
- Redis: provisioned in compose, unused.
- No email verification or password reset.
- Backtester closes the whole position at the first target (multiple targets are recorded but not scaled out).
- Option chain: Black-Scholes on the synthetic underlying with flat IV; no template uses it.
