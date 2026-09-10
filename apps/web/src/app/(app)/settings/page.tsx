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
      {notice && <div className={`notice ${toneCls}`} role="status" data-testid="settings-notice">{notice}</div>}

      {/* (a) Capital buckets */}
      <div className="section">
        <span className="label">Capital buckets</span>
        <form action={saveBuckets} className="ledger" data-testid="buckets">
          <BucketRow id="safety" label="Safety" help="Never touched by the app." value={Number(profile.safetyBucket)} />
          <BucketRow id="long_term" label="Long term" help="Never touched by the app." value={Number(profile.longTermBucket)} />
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
        <form action={saveRiskProfile} className="ledger" data-testid="risk-profile">
          {PROFILE_ORDER.map((k) => {
            const q = PROFILES[k];
            const loosens = !isTightening(rp, k);
            const blocked = loosens && !research;
            return (
              <label key={k} className="row" style={{ cursor: blocked ? "not-allowed" : "pointer" }}>
                <span className="cluster"><input type="radio" name="profile" value={k} defaultChecked={rp === k} disabled={blocked} /> <span className="mono">{q.label}</span></span>
                <span className="muted">{q.perTradePct}% per trade · {q.dailyR}R a day · {q.weeklyR}R a week · {q.concurrentR}R open at once{k === rp ? " · current" : ""}</span>
                <span className="mono faint">{blocked ? "loosens: RESEARCH only" : loosens ? "loosens" : k === rp ? "" : "tightens"}</span>
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
                <span className="fig">{clock.speed}x</span>
              </form>
            </>
          )}
        </div>
      </div>

      {/* (f) Theme */}
      <div className="section">
        <span className="label">Theme</span>
        <form action={saveTheme} className="ledger" data-testid="theme">
          <div className="row">
            <span className="label">Appearance</span>
            <span className="cluster" style={{ gap: 18 }}>
              {(["system", "light", "dark"] as const).map((t) => (
                <label key={t} className="cluster" style={{ gap: 6, cursor: "pointer" }}><input type="radio" name="theme" value={t} defaultChecked={profile.theme === t} /> <span className="mono">{t}</span></label>
              ))}
            </span>
            <button className="btn btn--sm">Save theme</button>
          </div>
        </form>
      </div>

      {/* (g) Sign out */}
      <div className="section">
        <span className="label">Session</span>
        <div className="ledger">
          <div className="row">
            <span className="label">Signed in as</span>
            <span className="mono">{user.email}</span>
            <form action="/api/logout" method="post"><button className="btn btn--sm">Sign out</button></form>
          </div>
          <div className="row row--wide">
            <span className="label">State</span>
            <span className="muted">{profile.stateReason} <span className="mono faint">since {simTs(profile.stateChangedAt)}</span>. Parameter edits live in the <Link href="/research">Research</Link> section and the Builder.</span>
          </div>
        </div>
      </div>
    </>
  );
}

function BucketRow({ id, label, help, value }: { id: string; label: string; help: string; value: number }) {
  return (
    <div className="row">
      <label className="label" htmlFor={id}>{label}</label>
      <span className="muted">{help}</span>
      <span className="cluster" style={{ gap: 6 }}><span className="mono faint">₹</span><input id={id} name={id} className="input input--inline" inputMode="numeric" style={{ width: 140 }} defaultValue={value} required /></span>
    </div>
  );
}
