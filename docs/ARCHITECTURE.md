# ARCHITECTURE.md

This file is the contract between `apps/web` and `services/engine`. Both sides build to it. Change it
first, then the code.

## 0. The governing rule (spec §0)

Nothing security-specific originates from the platform. Enforced in code:

- `engine/mentor/guardrail.py::guardrail(text, allowed_symbols) -> GuardrailResult` rejects any mentor
  output that names a symbol outside the user's strategy/portfolio context or uses imperative
  buy/sell phrasing. Rejections are written to `guardrail_log`.
- `automation_permission ∈ {paper_only, mentor_only, blocked}` — the schema enum has exactly three values.
- No broker client, no order types, no API-key input exists anywhere.
- Library copy: "Templates to learn the schema". No performance numbers on template cards.
- No screener.

## 1. Services

| Service | Tech | Port | Role |
|---|---|---|---|
| `web` | Next.js 15 App Router, Prisma | 3000 | Auth, all screens, CRUD on strategies/journal/settings, proxies compute calls to engine |
| `engine` | FastAPI | 8000 | Indicators, rule engine, backtester, validation jobs, risk, behaviour, mentor |
| `paper` | same image, `python -m engine.paper.worker` | – | Replays the synthetic feed on a simulated clock; produces signals, fills, state transitions |
| `postgres` | 16 | 5432 | Single DB, Prisma owns the schema (`apps/web/prisma/schema.prisma`) |
| `redis` | 7 | 6379 | Provisioned; phase 1 stores job state in Postgres (see DECISIONS) |

Web → engine calls are server-side only (`apps/web/src/lib/engine.ts`), on the compose network, with
header `X-User-Id: <user id>`. Engine trusts that header (internal network). Never expose engine
publicly without adding auth.

## 2. Database (Prisma is the source of truth)

All tables snake_case via `@@map`. Engine mirrors them in `engine/db/models.py` (SQLAlchemy). JSON
columns hold schema-typed documents:

| Table | Purpose | JSON columns |
|---|---|---|
| `users` | email, argon2 hash | |
| `sessions` | cookie session id → user, expiry | |
| `profiles` | capital buckets, risk profile, behavioural state, cost overrides, data source, onboarding | `cost_overrides` |
| `strategies` | one row per version; `id` = `strategy_id` (`slug_vN`); `user_id NULL` ⇒ template | `spec` (Strategy) |
| `validation_jobs` | queued/running/done/failed, `current_stage` 1-8, report | `report` (ValidationReport) |
| `watchers` | a `paper_only` strategy being replayed for a user; execution state machine state | `context` |
| `signals` | one per evaluated bar with a setup or a state change; rendered as the rule trace | `payload` (Signal) |
| `paper_trades` | open and closed paper positions; journal rows | `planned`, `actual` |
| `journal_notes` | free text, optional trade link, lexicon hits | `flags` |
| `state_events` | every behavioural transition with reason | |
| `override_attempts` | user tried to act outside rules/brakes | |
| `guardrail_log` | rejected mentor outputs | |
| `sim_clock` | single row: simulated `now`, speed, running | |
| `event_calendar` | dated events (RBI policy etc.) for the `event` regime | |

Risk usage (daily/weekly R used) is computed from `paper_trades`, not stored.

## 3. Strategy schema

`packages/schema/strategy.schema.json` is the source. Generated: `packages/schema/src/types.ts`,
`services/engine/engine/schema/strategy.py` (pydantic v2). `pnpm gen` regenerates both.

Testable rules live once in `packages/schema/testable.rules.json` and are interpreted by
`packages/schema/src/testable.ts` and `engine/schema/testable.py` (each ~25 lines). Both run the same
fixtures in `packages/schema/fixtures/testable.cases.json`.

Condition grammar: `{ lhs, op, rhs, lookback? }` where `lhs`/`rhs` are either an input name
(`"rsi14"`), a dotted input field (`"bb.upper"`, `"macd.hist"`), a bar field (`"close"`, `"open"`,
`"high"`, `"low"`, `"volume"`), or a number. `op ∈ {>, <, >=, <=, ==, crosses_above,
crosses_below, rising, falling}`. `lookback` applies to `rising`/`falling` (n bars) and to cross ops
(within n bars, default 1). All evaluated on closed bars only.

## 4. Engine HTTP API

All bodies/replies JSON. Errors: `{ "error": "<plain sentence>" }` with 4xx.

| Method & path | Body → Reply |
|---|---|
| `GET /health` | `{ ok, provider, sim_now }` |
| `POST /strategies/check` | `{ spec }` → `{ testable, missing: [string], ambiguity_flags }` (shared validator + engine-side consistency checks) |
| `POST /backtest` | `{ spec, start?, end?, cost_multiplier? }` → `BacktestResult` (synchronous; used by builder preview) |
| `POST /validate` | `{ strategy_id }` → `{ job_id }` (creates `validation_jobs` row, runs in a background thread) |
| `GET /jobs/{job_id}` | → `{ id, status, current_stage, report, error }` |
| `GET /desk/{user_id}` | → `DeskSummary` (top strip + watchers + latest signals) |
| `POST /watchers` | `{ strategy_id }` → watcher; requires `automation_permission == paper_only` and strategy status `validated` |
| `DELETE /watchers/{id}` | |
| `GET /journal/{user_id}` | → `{ trades: [PaperTrade], aggregates: JournalAggregates }` |
| `POST /journal/notes` | `{ trade_id?, text }` → `{ note, state }` (runs lexicon, may transition state) |
| `POST /behaviour/override` | `{ what }` → `{ state, reason }` (logs attempt; repeated ⇒ ELEVATED) |
| `POST /risk/profile` | `{ profile }` → `{ ok }` or 409 `{ error }` (loosening only in RESEARCH; journaled) |
| `GET /risk/{user_id}` | → `RiskStatus` |
| `POST /mentor/formalise` | `{ text }` → `{ draft: Strategy, ambiguity_flags, prose }` |
| `POST /mentor/explain` | `{ signal_id }` → `{ prose }` |
| `POST /mentor/review` | `{ job_id }` → `{ prose, weakest_stage, next_step }` |
| `POST /mentor/coach` | `{ note_id }` or `{ text }` → `{ prose }` |
| `GET /sim/clock`, `POST /sim/clock` | `{ speed?, running?, jump_to? }` — sim clock control (settings, tests) |
| `POST /paper/step` | `{ bars: n }` → advances the paper trader synchronously by n base bars (tests/e2e) |

### Types (mirrored in `apps/web/src/lib/types.ts`)

```ts
type Regime = "trend" | "range" | "compression" | "high_vol" | "event";
type ExecState = "WATCHING"|"SETUP_FOUND"|"ARMED"|"ORDER_PENDING"|"OPEN"|"EXIT_PENDING"|"CLOSED"|"BLOCKED";
type BehaviourState = "CALM"|"ELEVATED"|"COOLDOWN"|"RESEARCH";

interface Gate { name: string; pass: boolean; reason?: string }   // reason set when !pass
interface Signal {
  id: string; strategy_id: string; version: number; timestamp: string; symbol: string; regime: Regime;
  side: "long"|"short"|null;
  conditions_passed: string[]; conditions_failed: string[];   // rendered rule expressions
  trigger: { type: string; price: number|null; description: string };
  stop: number|null; targets: number[]; quantity: number;
  rupee_risk: number; portfolio_risk_pct: number;
  estimated_costs: number; post_cost_rr: number|null;
  automation_permission: "paper_only"|"mentor_only"|"blocked";
  ambiguity_flags: string[];
  gates: Gate[];                       // every gate green/red with reason
  exec_state: ExecState; verdict: "eligible"|"watch"|"blocked"; sentence: string;
}
interface RiskStatus {
  trading_bucket: number; one_r: number; profile: "conservative"|"standard"|"hard_ceiling";
  daily_used_r: number; daily_limit_r: number; weekly_used_r: number; weekly_limit_r: number;
  concurrent_used_r: number; concurrent_limit_r: number; brakes: { daily: boolean; weekly: boolean; concurrent: boolean };
}
interface DeskSummary {
  risk: RiskStatus; behaviour: { state: BehaviourState; reason: string; since: string };
  market: { open: boolean; sim_now: string; session: string };
  watchers: { id: string; strategy_id: string; name: string; exec_state: ExecState; state_reason: string; latest_signal: Signal|null }[];
  provider: "synthetic"|"csv";
}
interface StageResult { stage: number; name: string; status: "pass"|"fail"|"skip"|"pending"; summary: string; metrics: Record<string, number>; detail: any }
interface ValidationReport {
  strategy_id: string; started_at: string; finished_at: string|null;
  stages: StageResult[]; weakest_stage: number|null; weakest_sentence: string; passed: boolean;
}
interface PaperTrade {
  id: string; strategy_id: string; symbol: string; side: "long"|"short"; qty: number;
  planned: { entry: number; stop: number; targets: number[]; risk_r: number };
  actual: { entry: number|null; exit: number|null; entry_ts: string|null; exit_ts: string|null };
  slippage: number; costs: number; mfe_r: number|null; mae_r: number|null;
  exit_reason: string|null; regime: Regime; outcome_r: number|null;
  rules_followed: number; rules_total: number; status: "open"|"closed";
}
```

`BacktestResult`: `{ trades: BacktestTrade[], equity: [ts, equity][], stats: {...}, by_regime: {...} }`.
Stage `detail` payloads: 2 `{ in_sample: stats, oos: stats, equity }`, 3 `{ windows: [{train, test, stats}] }`,
4 `{ multipliers: { "1.0": stats, "1.5": stats, "2.0": stats } }`, 5 `{ params: [{name, base, grid: [{delta, expectancy}]}] }`,
6 `{ regimes: { [regime]: stats } }`, 7 `{ dd_p5, dd_p50, dd_p95, histogram: [[bin, count]] }`, 8 `{ paper: stats|null, backtest: stats, agreement }`.

## 5. Jobs

Validation runs inside the engine process in a thread (`ThreadPoolExecutor(max_workers=2)`), writing
`current_stage` and the growing `report` to `validation_jobs` after each stage. Web polls
`GET /jobs/{id}` every 1.5s via TanStack Query. Jobs survive a page reload; they do not survive an
engine restart (status stays `running`; the runbook says how to reset).

## 6. Simulated clock and paper trader

Data is synthetic, so the app runs on a simulated clock (`sim_clock` row). The `paper` worker
advances it `PAPER_SPEED` 1-minute bars per real second during session hours and jumps to the next
session open when the day ends. Market open ⇔ sim time in 09:15–15:30 IST on a weekday not in the
holiday list. Every tick: for each watcher, evaluate the strategy on closed bars up to `sim_now`,
run the execution state machine, apply the cost model to fills, enforce risk brakes and behavioural
state, write `signals`, `paper_trades`, `state_events`.

Execution state machine (`engine/exec/state_machine.py`):
`WATCHING → SETUP_FOUND → ARMED → ORDER_PENDING → OPEN → EXIT_PENDING → CLOSED`, any hard failure `→ BLOCKED`.
Each transition writes a `signals` row carrying the exact conditions and gate results.

## 7. Risk engine

Buckets `safety`, `long_term`, `trading`. Only `trading` sizes positions. `1R = trading × per_trade_pct`.

| Profile | per trade | daily | weekly | concurrent |
|---|---|---|---|---|
| conservative | 0.25% | 1.5R | 4R | 1R |
| standard | 0.50% | 2R | 5R | 2R |
| hard_ceiling | 1.00% | 3R | 7R | 3R |

Brakes are evaluated in the engine before any paper fill. Tightening allowed any time; loosening only
in `RESEARCH`, and both are journaled to `state_events` with `kind = "profile_change"`.

## 8. Behavioural state machine

`CALM | ELEVATED | COOLDOWN | RESEARCH`. RESEARCH whenever market closed (worker sets it at close and
restores CALM at open unless COOLDOWN carried over). ELEVATED after ≥ 2 override attempts within a
session or when a journal note hits the lexicon (`engine/behaviour/lexicon.txt`). COOLDOWN on rule
breach or daily brake; journal-only until next session open. Parameters editable only in RESEARCH
(web checks state before rendering the Research editor; engine rejects writes outside RESEARCH).

## 9. Mentor

`engine/mentor/service.py`. If `ANTHROPIC_API_KEY` is set, calls the Messages API with the system
prompt in `engine/mentor/prompt.md`; otherwise `engine/mentor/templates.py` produces deterministic
prose from the same inputs. Both paths go through `guardrail()`; on rejection the reply is the
template fallback and the rejection is logged.

## 10. Data providers

`engine/data/provider.py`: `MarketDataProvider.get_bars(symbol, timeframe, start, end) -> DataFrame[ts, open, high, low, close, volume]`
and `get_option_chain(underlying, expiry, asof)`. `SyntheticProvider` reads `/data/*.parquet` (committed,
generated by `data/generate.py`, filenames prefixed `SYNTHETIC_`). `CsvProvider` reads `/data/csv/<SYMBOL>_<tf>.csv`.
`VendorProvider` is a documented stub raising `NotImplementedError`. Selected by `DATA_PROVIDER`.
