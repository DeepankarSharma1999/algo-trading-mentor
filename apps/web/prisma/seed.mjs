// Idempotent seed: demo user, capital firewall, sim clock, event calendar, 20 templates,
// one validated strategy in paper mode with a watcher + rule trace, and a journal of closed paper trades.
// Runs on every container start; exits early when the demo user already exists.
import { PrismaClient } from "@prisma/client";
import { hash } from "@node-rs/argon2";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const db = new PrismaClient();
const DEMO = { email: "demo@atm.local", password: "papertrade" };
// Sim clock starts mid-session on a synthetic trading day; the paper worker replays from here.
const SIM_START = new Date("2025-06-12T10:35:00Z"); // UTC-naive column holding IST wall time

const EVENTS = [
  ["2024-02-08", "RBI MPC"], ["2024-04-05", "RBI MPC"], ["2024-06-07", "RBI MPC"], ["2024-07-23", "Union Budget"], ["2024-08-08", "RBI MPC"],
  ["2024-10-09", "RBI MPC"], ["2024-12-06", "RBI MPC"], ["2025-02-01", "Union Budget"], ["2025-02-07", "RBI MPC"], ["2025-04-09", "RBI MPC"],
  ["2025-06-06", "RBI MPC"], ["2025-08-06", "RBI MPC"], ["2025-10-01", "RBI MPC"], ["2025-12-05", "RBI MPC"],
];

function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32); }

async function seedTemplates() {
  const file = join(here, "templates.json");
  if (!existsSync(file)) { console.log("seed: templates.json missing, skipping templates"); return []; }
  const templates = JSON.parse(readFileSync(file, "utf8"));
  for (const t of templates) {
    await db.strategy.upsert({
      where: { id: t.id },
      create: { id: t.id, userId: null, name: t.name, slug: t.id.replace(/_v\d+$/, ""), version: 1, parentId: null, status: "testable", spec: t.spec, plainRules: JSON.stringify({ rules: t.plain_rules, ambiguity_notes: t.ambiguity_notes, regime: t.regime }) },
      update: { name: t.name, spec: t.spec, plainRules: JSON.stringify({ rules: t.plain_rules, ambiguity_notes: t.ambiguity_notes, regime: t.regime }) },
    });
  }
  console.log(`seed: ${templates.length} templates`);
  return templates;
}

async function main() {
  await db.simClock.upsert({ where: { id: 1 }, create: { id: 1, now: SIM_START, speed: Number(process.env.PAPER_SPEED ?? 2), running: true }, update: {} });
  if ((await db.eventCalendar.count()) === 0) await db.eventCalendar.createMany({ data: EVENTS.map(([d, label]) => ({ date: new Date(d), label })) });
  const templates = await seedTemplates();

  const existing = await db.user.findUnique({ where: { email: DEMO.email } });
  if (existing && (await db.strategy.count({ where: { userId: existing.id } })) > 0) { console.log("seed: demo user exists, done"); return; }
  const user = existing ?? await db.user.create({ data: { email: DEMO.email, passwordHash: await hash(DEMO.password), profile: { create: {
    safetyBucket: 500000, longTermBucket: 1500000, tradingBucket: 400000, riskProfile: "standard", onboardedAt: new Date(),
    behaviourState: "CALM", stateReason: "Session open. No brakes reached.", stateChangedAt: SIM_START,
  } } } });
  const oneR = 400000 * 0.005; // ₹2,000

  // A cloned template, validated, in paper mode.
  const base = templates.find((t) => t.id === "two_legged_pullback_v1") ?? templates[0];
  const spec = base ? { ...base.spec, strategy_id: "icici_pullback_v1", name: "ICICIBANK two-legged pullback (mine)", parent_id: base.id, instruments: ["ICICIBANK"], market: "NSE_EQ", automation_permission: "paper_only", version_locked: true } : null;
  if (!spec) { console.log("seed: no templates, skipping strategy"); return; }
  const strat = await db.strategy.create({ data: { id: "icici_pullback_v1", userId: user.id, name: spec.name, slug: "icici_pullback", version: 1, parentId: base.id, status: "validated", spec, plainRules: base.plain_rules } });
  const watcher = await db.watcher.create({ data: { userId: user.id, strategyId: strat.id, execState: "SETUP_FOUND", stateReason: "Trend regime; higher low above the rising 21 EMA on the last closed bar.", updatedAt: SIM_START } });

  const signal = {
    id: "seed_signal", strategy_id: strat.id, version: 1, timestamp: SIM_START.toISOString().replace("Z", ""), symbol: "ICICIBANK", regime: "trend", side: "long",
    conditions_passed: ["ema21 rising ema21 (within 10 bars)", "adx.adx > 20", "low[-1] < low[-3]", "low > low[-1]"],
    conditions_failed: ["close > ema21"],
    trigger: { type: "next_bar_open", price: 1012.4, description: "Fill at the open of the next 15m bar, inside a 3 bps slippage band." },
    stop: 1004.1, targets: [1029.0], quantity: 240, rupee_risk: 1992.0, portfolio_risk_pct: 0.5,
    estimated_costs: 118.6, post_cost_rr: 1.88, automation_permission: "paper_only", ambiguity_flags: [],
    gates: [
      { name: "All entry conditions", pass: false, reason: "Close is 1011.9, below the 21 EMA at 1012.6." },
      { name: "Regime matches affinity", pass: true }, { name: "Post-cost R:R >= 1.5", pass: true },
      { name: "Daily risk brake", pass: true }, { name: "Weekly risk brake", pass: true }, { name: "Concurrent risk", pass: true },
      { name: "Max trades today", pass: true }, { name: "Behavioural state allows entries", pass: true }, { name: "Session window", pass: true },
    ],
    exec_state: "SETUP_FOUND", verdict: "watch",
    sentence: "Strategy icici_pullback_v1 matched a trend regime. The 21 EMA has risen for 10 bars, ADX is above 20 and the bar made a higher low after a two-legged dip, but the close is under the 21 EMA, so this bar is not a full setup. Watching for the next closed bar.",
  };
  await db.signal.create({ data: { userId: user.id, watcherId: watcher.id, strategyId: strat.id, ts: SIM_START, payload: signal } });

  // Journal: 36 closed paper trades over the previous 8 weeks, deterministic.
  const r = rng(42);
  const regimes = ["trend", "trend", "range", "high_vol", "trend", "compression"];
  const reasons = ["target", "stop", "trailing", "time_exit", "flat_at_close"];
  const trades = [];
  let t = new Date(SIM_START); t.setUTCDate(t.getUTCDate() - 80);
  for (let i = 0; i < 36; i++) {
    t = new Date(t); t.setUTCDate(t.getUTCDate() + 1 + (r() < 0.3 ? 1 : 0)); if (t.getUTCDay() === 6) t.setUTCDate(t.getUTCDate() + 2); if (t.getUTCDay() === 0) t.setUTCDate(t.getUTCDate() + 1);
    if (t.toISOString().slice(0, 10) >= SIM_START.toISOString().slice(0, 10)) break; // never journal the future
    const opened = new Date(t); opened.setUTCHours(9 + Math.floor(r() * 5), [0, 15, 30, 45][Math.floor(r() * 4)]);
    const held = 15 * (2 + Math.floor(r() * 12)); const closed = new Date(opened.getTime() + held * 60000);
    const side = r() < 0.7 ? "long" : "short"; const entry = 940 + r() * 120; const risk = 5 + r() * 6;
    const win = r() < 0.47; const outcome = win ? +(0.8 + r() * 1.8).toFixed(2) : -+(0.6 + r() * 0.5).toFixed(2);
    const stop = side === "long" ? entry - risk : entry + risk; const target = side === "long" ? entry + 2 * risk : entry - 2 * risk;
    const slip = +(entry * 0.0003 * (0.5 + r())).toFixed(2); const actualEntry = side === "long" ? entry + slip : entry - slip;
    const exit = side === "long" ? actualEntry + outcome * risk : actualEntry - outcome * risk;
    const followed = r() < 0.8 ? 5 : 4;
    trades.push({
      userId: user.id, strategyId: strat.id, watcherId: watcher.id, symbol: "ICICIBANK", side, qty: 240,
      planned: { entry: +entry.toFixed(2), stop: +stop.toFixed(2), targets: [+target.toFixed(2)], risk_r: 1 },
      actual: { entry: +actualEntry.toFixed(2), exit: +exit.toFixed(2), entry_ts: opened.toISOString().replace("Z", ""), exit_ts: closed.toISOString().replace("Z", "") },
      slippage: slip, costs: +(70 + r() * 40).toFixed(2), mfeR: +(Math.max(outcome, 0) + r() * 0.6).toFixed(2), maeR: -+(Math.max(-outcome, 0) + r() * 0.4).toFixed(2),
      exitReason: win ? (r() < 0.7 ? "target" : "trailing") : reasons[1 + Math.floor(r() * 4)], regime: regimes[Math.floor(r() * regimes.length)],
      outcomeR: outcome, rulesFollowed: followed, rulesTotal: 5, status: "closed", openedAt: opened, closedAt: closed,
    });
  }
  await db.paperTrade.createMany({ data: trades });
  const first = await db.paperTrade.findFirst({ where: { userId: user.id }, orderBy: { closedAt: "desc" } });
  await db.journalNote.createMany({ data: [
    { userId: user.id, tradeId: first?.id ?? null, text: "Took the fill at the open as planned. Stop was at the signal bar low; did not move it.", flags: [] },
    { userId: user.id, tradeId: null, text: "Skipped the second setup of the day because daily trades were at the limit. Felt the pull to size up on the next one.", flags: [] },
  ] });
  await db.stateEvent.createMany({ data: [
    { userId: user.id, kind: "behaviour", fromState: "RESEARCH", toState: "CALM", reason: "Market open.", ts: new Date(SIM_START.getTime() - 80 * 60000) },
  ] });
  console.log(`seed: demo user ${DEMO.email} / ${DEMO.password}, strategy ${strat.id}, ${trades.length} paper trades, 1R = ₹${oneR}`);

  // Ask the engine for a real validation report so the Validation screen is populated.
  const engineUrl = process.env.ENGINE_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${engineUrl}/validate`, { method: "POST", headers: { "content-type": "application/json", "x-user-id": user.id }, body: JSON.stringify({ strategy_id: strat.id }) });
    console.log(`seed: validation job ${res.ok ? "queued" : "not queued (" + res.status + ")"}`);
  } catch { console.log("seed: engine not reachable, validation not queued"); }
}

main().catch((e) => { console.error(e); process.exit(1); }).finally(() => db.$disconnect());
