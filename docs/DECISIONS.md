# DECISIONS.md

Decisions made autonomously while building phase 1. Newest at the bottom of each section.

## Architecture

- **Jobs: engine endpoints + web polling, not BullMQ.** Web calls `POST /validate`, engine runs the
  pipeline in a thread and writes stage progress to Postgres; web polls `GET /jobs/{id}`. One fewer
  moving part than a Redis queue and the same UX. Redis stays in compose (spec asks for it) but is
  unused in phase 1; it is the obvious home for a multi-worker queue in phase 2.
- **Engine trusts `X-User-Id` from web.** Engine is only reachable on the compose network. Recorded
  as a hard prerequisite in RUNBOOK before any public deployment.
- **Simulated clock.** Data is synthetic, so "live" means replaying the feed on a simulated clock
  (`sim_clock` table) advanced by the paper worker. Market open/closed and RESEARCH state derive
  from sim time, not wall time. The clock is controllable from Settings and from tests.
- **Single DB, Prisma owns migrations.** Engine mirrors the tables with SQLAlchemy models by name;
  snake_case via `@@map`. Any schema change starts in `schema.prisma`.
- **Shared testable-validator = declarative rules + two tiny interpreters.** `testable.rules.json`
  is the single definition; TS and Python each interpret it in ~25 lines and run the same fixture
  file. This is the honest way to have one validator across two languages.
- **Auth: hand-rolled.** argon2id (`@node-rs/argon2`) + opaque session id in an HttpOnly cookie,
  sessions in Postgres. Auth.js adds a dependency tree for no phase-1 benefit.
- **Fonts via `<link>` to Google Fonts**, not `next/font`, so the docker build works offline.
  Fallback stacks are real (Georgia / Helvetica / Menlo).
- **Tailwind is installed but used only for spacing/flex/grid utilities.** Every colour, face and
  size comes from `packages/ui/tokens.css`; components use `primitives.css` classes. The design lint
  fails the build on banned utilities.
- **Instrument universe for synthetic data:** NIFTY, BANKNIFTY (index, lot sizes 25 / 15) and ten
  stocks: RELIANCE, HDFCBANK, ICICIBANK, INFY, TCS, SBIN, ITC, LT, AXISBANK, KOTAKBANK. Names are
  just familiar tickers for the generator; every price series is synthetic and labelled so.
- **Base data is 1-minute; higher timeframes are resampled** in the provider, so all timeframes are
  consistent and the parquet footprint stays small (1m × 2 years × 12 symbols ≈ 2.2M rows).
- **Model default `claude-sonnet-5`** for the mentor (override with `ANTHROPIC_MODEL`).
- **Postgres is published on host port 55432**, not 5432: many developer machines already run a local
  Postgres on 5432 (this one did), and a silent connection to the wrong server is worse than an odd port.
  Inside the compose network it is still `postgres:5432`.
- **ESLint uses `typescript-eslint` + `react-hooks` directly**, not `eslint-config-next`, which fails to
  load under current ESLint 9 (the rushstack patch error). Coverage is equivalent for this codebase.
- **Provider prices are float32** (parquet footprint); tests compare with a 1e-6 relative tolerance.
- **Regime affinity is not enforced in the backtester** (stage 6 must see every regime to report the
  breakdown); the paper trader enforces it through the "Regime matches affinity" gate.
- **Monte Carlo gate reads the bad tail**: the report shows p5/p50/p95 of max drawdown across 1000
  trade-order resamples and gates on the 95th percentile (the drawdown only 5% of orderings exceed),
  which is what "5th-percentile drawdown within the profile" means once drawdown is a positive number.
- **Seed never journals the future**: seeded paper trades stop the day before the sim clock's start, so
  the daily and weekly brakes on the strip reflect only what the simulated clock has already lived through.

## Product

- **Templates are seeded with `user_id = NULL`** and shown read-only; "Clone" copies the spec into
  the user's own strategies as `slug_v1` with `parent_id` set to the template id.
- **Strategy status** ∈ `draft | testable | validated | untested`. Any spec change on a `validated`
  strategy creates a new version row and marks it `untested` (spec §4.4).
- **Option chain**: `get_option_chain` on `SyntheticProvider` returns a Black-Scholes-priced chain
  from the synthetic underlying and a flat vol, enough for the interface to be real; no strategy
  template uses it in phase 1.
- **Override attempts**: in paper mode the only "override" the UI offers is "Mark eligible anyway" /
  "Skip cooldown" buttons that never do anything except log the attempt; two in one session moves
  the user to ELEVATED. This keeps the behavioural machine testable without a broker.

- **Index templates often size to zero at a ₹4 lakh trading bucket.** One NIFTY lot (25) with a
  15m ATR stop risks more than 1R at the Standard profile, and the sizing rule never widens a stop to
  fit, so the backtester skips the trade and counts it in `skipped_for_size`. This is correct behaviour
  and the Builder shows it; the seed therefore uses a stock (ICICIBANK, lot 1) so the demo report gets
  past stage 1.
- **On synthetic data every template fails validation.** The generator has no exploitable structure
  beyond volatility regimes, so out-of-sample expectancy is negative after costs. The seeded strategy
  is marked `validated` as a fixture so the Desk has a watcher; the real validation job queued by the
  seed writes its honest verdict (`untested`) a few seconds later. That contradiction is deliberate
  for the demo and disappears with real data.

- **Strategy ids are unique across the whole table**, templates included. `strategy_id` is the
  primary key and the spec fixes its shape to `slug_vN`, so cloning "Donchian Pullback" for the first
  time yields `donchian_pullback_2_v1` (the template holds `donchian_pullback_v1`). A per-user prefix
  would have changed the spec's id shape.

- **Type scale raised one notch and touch targets set to 40px** after the usability review; the
  ledger identity is unchanged. A Help page with a glossary and a "start here" checklist on an empty
  Desk replace the assumption that users know what 1R, brakes and gates mean.

- **The simulated clock stops at the end of the feed instead of looping.** The first version wrapped
  to 2025-01-01, which after a few loops left the Desk showing a December trace as "latest" and the
  brakes counting losses from "later this week" of a previous loop. Now `advance()` pauses at the last
  close, Settings offers a deliberate "Jump to", and every read of signals, trades and risk windows
  ignores rows dated after the simulated now.

## Stubs

- `VendorProvider` (`engine/data/provider.py`): interface documented, raises `NotImplementedError`.
- Stage 8 (paper agreement) reports `skip` until ≥ 30 closed paper trades exist for the strategy.
- Redis: provisioned, unused.
- Email verification / password reset: none. Email + password only.
