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
  idempotent: templates are upserted, the demo user is created once (with a validated ICICIBANK two-legged pullback
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

`make` needs GNU make (Linux, macOS, WSL, or `choco install make` on Windows). Without it, run the
steps directly:

```bash
pnpm -r lint && pnpm -r typecheck && pnpm -r test
cd services/engine && python -m ruff check . && python -m pytest -q
pnpm --filter web exec playwright install chromium && pnpm --filter web e2e
```

Test counts at phase-1 completion: engine 231 (pytest), schema 18 and web 41 (vitest), Playwright 2.
CI (`.github/workflows/ci.yml`) runs the same, plus the compose stack and Playwright.

## Paper trader

`paper` is a compose service. It advances the simulated clock only while `sim_clock.running` is true
(Settings → Simulated clock → Pause/Resume). Every state change is logged as one line
(`<sim ts> <strategy> <symbol>: FROM -> TO (reason)`) and written to `signals`. A watcher needs a
`validated` strategy with `automation_permission = paper_only`; create one from the Builder's "Watch"
action. Signals, open positions and closed trades appear on the Desk and in the Journal.

## What "validated" means on synthetic data

Nothing. The synthetic feed has no exploitable structure, so every template fails at stage 2 or later
after costs. That is the gatekeeper working. The seeded strategy is marked `validated` as a fixture so
the Desk has a watcher on first launch; the seed also queues a real validation job whose honest
verdict (`untested`) lands a few seconds later and is visible on the Validation screen.

## Security prerequisites before any public deployment

- The engine trusts the `X-User-Id` header. It must stay unreachable from outside the compose network,
  or gain its own auth. `infra/docker-compose.prod.yml` enforces this by not publishing the engine's,
  Postgres's or Redis's ports — only the web app is reachable from outside the VM.
- Set a real `SESSION_SECRET` (the deploy script below generates one). Cookies are only marked
  `secure` when `NODE_ENV=production` **and** `COOKIE_SECURE` isn't `"false"` — the prod overlay sets
  it to `"false"` because the base setup below has no TLS; see "Add HTTPS" if you want a real
  certificate.

## Deploy to a free VM (Oracle Cloud Always Free)

Runs the exact stack above, unmodified, on a VM that's free forever (not a trial). Two parts: you
create the account and VM in Oracle's console (identity/payment verification is Oracle's requirement,
not something that can be scripted), then the deploy script below does everything else.

### 1. Create the VM (you do this, in the browser)

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (needs ID verification and a card for
   verification only — the shapes below are billed $0 forever).
2. **Compute → Instances → Create instance.**
   - Image: **Canonical Ubuntu 22.04** (aarch64/ARM build).
   - Shape: **VM.Standard.A1.Flex** (Ampere/ARM) — under "Always Free eligible", set 4 OCPUs / 24 GB
     memory (the maximum free allowance). If A1 capacity is unavailable in your region, retry later
     or fall back to the free `VM.Standard.E2.1.Micro` (1 GB RAM — tight for this stack, but works
     for a light demo).
   - Add your SSH public key (or let Oracle generate a key pair and download the private key).
   - Create.
3. **Networking → Virtual Cloud Networks → your VCN → Security Lists → Default Security List →
   Add Ingress Rules**: allow TCP port **3000** from `0.0.0.0/0` (this is the actual firewall; the
   VM's own `ufw`/`iptables` is a second, separate gate — Ubuntu images from Oracle usually ship with
   `iptables` already open for the default ports, but if the site doesn't load after deploying, also
   run `sudo iptables -I INPUT -p tcp --dport 3000 -j ACCEPT` on the VM).
4. Note the instance's **public IP**.

### 2. Push this repo somewhere the VM can pull it from

```bash
gh repo create algo-trading-mentor --private --source=. --remote=origin --push
```

(or push to any git remote you already use).

### 3. Deploy

```bash
ssh ubuntu@<public-ip>
curl -fsSL https://raw.githubusercontent.com/DeepankarSharma1999/algo-trading-mentor/main/infra/deploy.sh -o deploy.sh
REPO_URL=https://github.com/DeepankarSharma1999/algo-trading-mentor.git bash deploy.sh
```

The first run installs Docker and exits asking you to reconnect (group membership needs a fresh
session); run the same command again and it clones the repo, generates `infra/.env` with a random
`SESSION_SECRET`, and runs
`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`. It waits for
`/api/health` and prints the public URL. To redeploy after a change, just re-run the script — it
pulls and rebuilds.

### Add HTTPS (optional)

The setup above serves plain HTTP on port 3000. For a real certificate, point a free subdomain (e.g.
[duckdns.org](https://www.duckdns.org)) at the VM's IP, install [Caddy](https://caddyserver.com)
(`sudo apt install caddy`; it gets a Let's Encrypt certificate automatically), and give it a
Caddyfile that reverse-proxies `yourname.duckdns.org` to `localhost:3000`. Once TLS is real, drop the
`COOKIE_SECURE: "false"` line from `docker-compose.prod.yml` and redeploy.

## Stubs (see also docs/DECISIONS.md)

- `VendorProvider`: interface only, raises `NotImplementedError`.
- Validation stage 8 (paper agreement) reports `skip` until ≥ 30 closed paper trades exist for the strategy.
- Redis: provisioned in compose, unused.
- No email verification or password reset.
- Backtester closes the whole position at the first target (multiple targets are recorded but not scaled out).
- Option chain: Black-Scholes on the synthetic underlying with flat IV; no template uses it.
