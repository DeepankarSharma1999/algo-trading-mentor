import Link from "next/link";
import { StateChip } from "@/components/Chip";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { rupees, simTs } from "@/lib/format";
import { PROFILES, PROFILE_ORDER, isTightening, oneR } from "@/lib/risk";
import type { BehaviourState, RiskProfile } from "@/lib/types";
import { saveBuckets, saveCostOverrides, saveRiskProfile, saveTheme, setSimClock } from "./actions";
import { COST_KEYS, COST_META, readOverrides } from "./costs";
import { ThemeSetter } from "./ThemeSetter";

export const dynamic = "force-dynamic";

const SPEEDS = [1, 2, 5, 10, 30, 60];
const THEMES: { value: "system" | "light" | "dark"; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

/** Every setting as a ledger row. Reads Postgres only; each control's action tells the engine and fails soft. */
export default async function SettingsPage({ searchParams }: { searchParams: Promise<{ notice?: string; tone?: string }> }) {
  const user = await requireUser();
  const { notice, tone } = await searchParams;
  const [profile, clock] = await Promise.all([db.profile.findUnique({ where: { userId: user.id } }), db.simClock.findFirst()]);
  if (!profile) return null;
  const rp = profile.riskProfile as RiskProfile;
  const state = profile.behaviourState as BehaviourState;
  const research = state === "RESEARCH";
  const trading = Number(profile.tradingBucket);
  const r1 = oneR(trading, rp);
  const overrides = readOverrides(profile.costOverrides);
  const toneCls = tone === "blocked" ? "notice--blocked" : tone === "watch" ? "notice--watch" : "notice--eligible";
  const provider = process.env.DATA_PROVIDER ?? "synthetic";

  return (
    <>
      <ThemeSetter theme={profile.theme} />
      <div className="page-head">
        <h1 className="h-display">Settings</h1>
        <span className="cluster"><span className="mono muted">{user.email}</span><StateChip state={state} title={profile.stateReason} /></span>
      </div>
      <p className="page-intro">
        Everything the app knows about you, one row each. Each section saves on its own button; a sentence at the top of the page confirms what changed. Your behavioural state is shown at the right because it decides which changes are open right now. <Link href="/help">States and terms are explained in Help.</Link>
      </p>
      {notice && <div className={`notice ${toneCls}`} role="status" data-testid="settings-notice">{notice}</div>}

      {/* (a) Capital buckets */}
      <div className="section">
        <span className="label">Capital buckets</span>
        <p className="help help--tight">Whole rupees. Only the trading bucket ever sizes a paper position; 1R below follows from it and your profile. Safety and long-term money are recorded so the firewall is explicit, and never touched.</p>
        <form action={saveBuckets} className="ledger" data-testid="buckets">
          <BucketRow id="safety" label="Safety" help="Emergency money. Never touched by the app." value={Number(profile.safetyBucket)} />
          <BucketRow id="long_term" label="Long term" help="Investments you do not trade. Never touched by the app." value={Number(profile.longTermBucket)} />
          <BucketRow id="trading" label="Trading" help="The only bucket that sizes a paper position." value={trading} />
          <div className="row">
            <span className="label">1R</span>
            <span className="h-display" style={{ fontSize: "var(--fs-4)" }} data-testid="one-r-sentence">For you, 1R = {rupees(r1)}: {PROFILES[rp].perTradePct}% of the trading bucket under the {PROFILES[rp].label} profile.</span>
            <button className="btn btn--sm">Save buckets</button>
          </div>
        </form>
      </div>

      {/* (b) Risk profile */}
      <div className="section">
        <span className="label">Risk profile</span>
        <p className="help help--tight">Three fixed profiles. Each caps risk per trade, per day, per week and open at once, all in R. Tightening applies now and is journaled; loosening only opens in RESEARCH state, after the session closes. Your current profile is {PROFILES[rp].label}.</p>
        <form action={saveRiskProfile} className="ledger" data-testid="risk-profile">
          {PROFILE_ORDER.map((k) => {
            const q = PROFILES[k];
            const current = k === rp;
            const loosens = !isTightening(rp, k);
            const blocked = loosens && !research;
            const change = current ? "current profile" : !loosens ? "tightens; applies now" : research ? "loosens; open now, in RESEARCH" : "loosens, opens in RESEARCH";
            return (
              <label key={k} className="row" style={{ cursor: blocked ? "not-allowed" : "pointer" }}>
                <span className="cluster"><input type="radio" name="profile" value={k} defaultChecked={current} disabled={blocked} /> <span className="mono">{q.label}</span></span>
                <span className="muted">{q.perTradePct}% per trade · {q.dailyR}R a day · {q.weeklyR}R a week · {q.concurrentR}R open at once</span>
                <span className={`mono ${blocked ? "faint" : "muted"}`} data-testid={`profile-change-${k}`}>{change}</span>
              </label>
            );
          })}
          <div className="row row--wide">
            <span className="label">Change</span>
            <span className="cluster">
              <button className="btn btn--sm">Save profile</button>
              <span className="muted">{research ? "Tightening and loosening are both open now; the change is journaled." : "Tightening applies now and is journaled. Loosening opens in RESEARCH state, after the session closes."}</span>
            </span>
          </div>
        </form>
      </div>

      {/* (c) Cost model */}
      <div className="section">
        <span className="label">Cost model overrides</span>
        <p className="help help--tight">The per-trade cost assumptions that backtests and validation charge against every fill. Leave a field blank to keep the engine default; a number replaces it from the next run onward.</p>
        <form action={saveCostOverrides} className="ledger" data-testid="cost-overrides">
          {COST_KEYS.map((k) => {
            const m = COST_META[k];
            return (
              <div key={k} className="row">
                <label className="label" htmlFor={`cost-${k}`}>{m.label}</label>
                <span className="muted">{m.help} <span className="mono">{k}</span>; blank uses the engine default of <span className="mono">{m.fallback}</span>.</span>
                <span className="cluster" style={{ gap: 6 }}>
                  <input id={`cost-${k}`} name={k} className="input input--inline" inputMode="decimal" style={{ width: 96 }} defaultValue={overrides[k] ?? ""} placeholder={m.fallback} />
                  <span className="mono faint">{m.unit}</span>
                </span>
              </div>
            );
          })}
          <div className="row row--wide">
            <span className="label">Apply</span>
            <span className="cluster"><button className="btn btn--sm">Save overrides</button><span className="muted">Used by the next backtest and validation run; nothing already reported is recomputed.</span></span>
          </div>
        </form>
      </div>

      {/* (d) Data source */}
      <div className="section">
        <span className="label">Data source</span>
        <p className="help help--tight">Where the prices come from. This is set in the environment, not here; it is shown so you always know what you are looking at.</p>
        <div className="ledger" data-testid="data-source">
          <div className="row">
            <span className="label">Provider</span>
            <span className="muted">{provider === "synthetic" ? "Every price in this app is synthetic; nothing here is a market quote." : "Prices come from files you supplied; the engine never fetches from a vendor on your behalf."} To use your own one-minute CSVs, set <span className="mono">DATA_PROVIDER=csv</span> in the environment and restart the engine and paper worker, as described in the RUNBOOK. There is no key or credential field in this app.</span>
            <span className="fig">{provider}</span>
          </div>
        </div>
      </div>

      {/* (e) Simulated clock */}
      <div className="section">
        <span className="label">Simulated clock</span>
        <p className="help help--tight">Prices are synthetic, so time is simulated too. The paper trader only moves while this clock is running; paused, nothing opens or closes. Speed is how many one-minute bars pass per real second: at 1 a session takes as long as a real one, at 60 a full trading day of 375 bars passes in about six seconds.</p>
        <div className="ledger" data-testid="sim-clock">
          {!clock ? (
            <div className="row row--wide"><span className="label">None</span><span className="muted">There is no simulated clock row yet; run the seed to create one.</span></div>
          ) : (
            <>
              <div className="row"><span className="label">Sim time</span><span className="muted">IST wall time on synthetic trading days</span><span className="fig">{simTs(clock.now)}</span></div>
              <div className="row">
                <span className="label">Running</span>
                <span className="cluster">
                  <form action={setSimClock}><input type="hidden" name="op" value="pause" /><button className="btn btn--sm" disabled={!clock.running}>Pause</button></form>
                  <form action={setSimClock}><input type="hidden" name="op" value="resume" /><button className="btn btn--sm" disabled={clock.running}>Resume</button></form>
                  <span className="muted">Pausing stops the paper worker at the current bar; nothing is closed or opened.</span>
                </span>
                <span className={`status ${clock.running ? "status--eligible" : "status--watch"}`}>{clock.running ? "running" : "paused"}</span>
              </div>
              {!clock.running && clock.now >= new Date("2025-12-31T15:30:00Z") && (
                <div className="notice notice--watch" role="status">The synthetic feed ends at 2025-12-31 15:30 and the clock stopped there rather than looping. Jump it to an earlier date below to keep paper trading.</div>
              )}
              <form action={setSimClock} className="row">
                <label className="label" htmlFor="jump_day">Jump to</label>
                <span className="cluster">
                  <input type="hidden" name="op" value="jump" />
                  <input id="jump_day" name="jump_day" type="date" className="input input--inline" min="2025-01-01" max="2025-12-31" defaultValue="2025-06-12" />
                  <button className="btn btn--sm">Jump and run</button>
                  <span className="muted">Moves the clock to 09:15 on that synthetic day and starts it. Replaying a period paper-trades it again.</span>
                </span>
                <span className="fig">{simTs(clock.now).slice(0, 10)}</span>
              </form>
              <form action={setSimClock} className="row">
                <label className="label" htmlFor="speed">Speed</label>
                <span className="cluster">
                  <input type="hidden" name="op" value="speed" />
                  <select id="speed" name="speed" className="input input--inline" defaultValue={String(clock.speed)}>
                    {(SPEEDS.includes(clock.speed) ? SPEEDS : [...SPEEDS, clock.speed].sort((a, b) => a - b)).map((s) => <option key={s} value={s}>{s} bars / s</option>)}
                  </select>
                  <button className="btn btn--sm">Set speed</button>
                  <span className="muted">One-minute bars advanced per real second during session hours.</span>
                </span>
                <span className="fig">{clock.speed} bars/s</span>
              </form>
            </>
          )}
        </div>
      </div>

      {/* (f) Theme */}
      <div className="section">
        <span className="label">Theme</span>
        <p className="help help--tight">Saved on your account, so it follows you to any browser you sign in from. System follows the device setting and changes with it; Light and Dark stay fixed.</p>
        <form action={saveTheme} className="ledger" data-testid="theme">
          <div className="row">
            <span className="label">Appearance</span>
            <span className="cluster" style={{ gap: 18 }}>
              {THEMES.map((t) => (
                <label key={t.value} className="cluster" style={{ gap: 6, cursor: "pointer" }}><input type="radio" name="theme" value={t.value} defaultChecked={profile.theme === t.value} /> <span>{t.label}</span></label>
              ))}
            </span>
            <button className="btn btn--sm">Save theme</button>
          </div>
        </form>
      </div>

      {/* (g) Session */}
      <div className="section">
        <span className="label">Session</span>
        <p className="help help--tight">Who is signed in and which behavioural state the account is in. The state is set by the engine, not here.</p>
        <div className="ledger">
          <div className="row row--wide">
            <span className="label">Signed in as</span>
            <span className="mono">{user.email}</span>
          </div>
          <div className="row row--wide">
            <span className="label">State</span>
            <span className="muted">{profile.stateReason} <span className="mono faint">since {simTs(profile.stateChangedAt)}</span>. Parameter edits live in the <Link href="/research">Research</Link> section and the Builder.</span>
          </div>
        </div>
      </div>

      {/* (h) Sign out, alone at the bottom */}
      <div className="section">
        <span className="label">Sign out</span>
        <p className="help help--tight">Ends this session on this device only. Your buckets, strategies, jobs and journal stay on file for the next sign-in.</p>
        <form action="/api/logout" method="post" style={{ marginTop: 12 }}>
          <button className="btn btn--danger">Sign out</button>
        </form>
      </div>
    </>
  );
}

function BucketRow({ id, label, help, value }: { id: string; label: string; help: string; value: number }) {
  return (
    <div className="row">
      <label className="label" htmlFor={id}>{label}</label>
      <span className="help">{help}</span>
      <span className="cluster" style={{ gap: 6 }}><span className="mono faint">₹</span><input id={id} name={id} className="input input--inline" inputMode="numeric" style={{ width: 140 }} defaultValue={value} required /></span>
    </div>
  );
}
