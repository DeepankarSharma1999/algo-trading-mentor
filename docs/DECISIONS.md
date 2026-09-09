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

## Stubs

- `VendorProvider` (`engine/data/provider.py`): interface documented, raises `NotImplementedError`.
- Stage 8 (paper agreement) reports `skip` until ≥ 30 closed paper trades exist for the strategy.
- Redis: provisioned, unused.
- Email verification / password reset: none. Email + password only.
