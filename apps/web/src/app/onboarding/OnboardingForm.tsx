"use client";
import Link from "next/link";
import { useActionState, useState } from "react";
import { completeOnboarding, type OnboardingState } from "./actions";
import { rupees } from "@/lib/format";
import { PROFILES, PROFILE_ORDER, oneR } from "@/lib/risk";
import type { RiskProfile } from "@/lib/types";

const TRADING_ZERO = "The trading bucket must be more than zero. It is the only bucket that ever sizes a paper position, so 1R would be ₹0.";

export function OnboardingForm({ initial }: { initial: { safety: number; longTerm: number; trading: number; profile: RiskProfile } }) {
  const [state, action, pending] = useActionState<OnboardingState, FormData>(completeOnboarding, {});
  const [trading, setTrading] = useState(initial.trading);
  const [tradingTouched, setTradingTouched] = useState(false);
  const [profile, setProfile] = useState<RiskProfile>(initial.profile);
  const p = PROFILES[profile];
  const r = oneR(trading, profile);
  const tradingError = tradingTouched && trading <= 0 ? TRADING_ZERO : undefined;
  return (
    <form action={action}>
      <div className="section">
        <span className="label">Capital buckets</span>
        <p className="help help--tight">All three are required, in whole rupees. Enter 0 for a bucket you do not keep; the trading bucket must be more than 0.</p>
        <div className="ledger">
          <Row id="safety" label="Safety" hint="Emergency money. Never touched by this tool." defaultValue={initial.safety} />
          <Row id="long_term" label="Long-term" hint="Investments you do not trade. Never touched." defaultValue={initial.longTerm} />
          <Row id="trading" label="Trading" hint="The only bucket that ever sizes a paper position." defaultValue={initial.trading} onChange={setTrading} onBlur={() => setTradingTouched(true)} error={tradingError} />
        </div>
      </div>

      <fieldset className="section" style={{ border: 0, padding: 0, margin: "32px 0 0", minWidth: 0 }}>
        <legend className="label" style={{ width: "100%", padding: 0 }}>Risk profile <span aria-hidden="true">*</span></legend>
        <p className="help help--tight">One of three fixed profiles. Each caps how much of the trading bucket one trade may risk, and how many R may be lost in a day, in a week, and held open at once.</p>
        <div className="ledger">
          {PROFILE_ORDER.map((k) => {
            const q = PROFILES[k];
            return (
              <label key={k} className="row" style={{ cursor: "pointer" }}>
                <span className="cluster"><input type="radio" name="profile" value={k} checked={profile === k} onChange={() => setProfile(k)} required /> <span className="mono">{q.label}</span></span>
                <span className="muted">{q.perTradePct}% per trade · {q.dailyR}R daily · {q.weeklyR}R weekly · {q.concurrentR}R concurrent</span>
                <span />
              </label>
            );
          })}
        </div>
        <p className="help" style={{ marginTop: 10 }}>You can tighten this profile at any time. Loosening it is only possible in RESEARCH state, when the market is closed, and is written to your journal.</p>
      </fieldset>

      <div className="section">
        <p className="h-display h-display--xl" data-testid="one-r-sentence" aria-live="polite">
          For you, 1R = <span className="mono" style={{ fontSize: "0.85em" }}>{rupees(r)}</span>
        </p>
        <p className="muted">{p.perTradePct}% of {rupees(trading)}. Daily brake {rupees(r * p.dailyR)}, weekly brake {rupees(r * p.weeklyR)}.</p>
        <p className="help">1R is one unit of risk: the rupees you lose if a single trade hits its stop. Every figure on the Desk and in the Journal is counted in R, so trades of different sizes compare fairly. <Link href="/help">More terms in Help.</Link></p>
      </div>

      {state.error && <div className="notice notice--blocked" role="alert">{state.error}</div>}
      <div className="cluster" style={{ marginTop: 20 }}>
        <button className="btn btn--primary" disabled={pending}>Sign the firewall and open the desk</button>
        <span className="help">Saves the three buckets and the profile. Nothing is traded; the desk is paper only.</span>
      </div>
    </form>
  );
}

function Row({ id, label, hint, defaultValue, onChange, onBlur, error }: {
  id: string; label: string; hint: string; defaultValue: number; onChange?: (n: number) => void; onBlur?: () => void; error?: string;
}) {
  const errId = `${id}-error`, hintId = `${id}-hint`;
  return (
    <div className="row">
      <label className="label" htmlFor={id}>{label} <span aria-hidden="true">*</span></label>
      <span id={hintId} className="help">{hint}</span>
      <span className="cluster" style={{ gap: 6 }}>
        <span className="fig">₹</span>
        <input
          id={id} name={id} className="input input--inline right" style={{ width: 150 }} inputMode="numeric" defaultValue={defaultValue || ""} placeholder="0" required
          aria-required="true" aria-invalid={error ? true : undefined} aria-describedby={error ? `${hintId} ${errId}` : hintId}
          onChange={(e) => onChange?.(Number(e.target.value.replace(/[^\d.]/g, "")) || 0)} onBlur={onBlur}
        />
      </span>
      {error && <span id={errId} className="field-error" role="alert" style={{ gridColumn: "1 / -1" }}>{error}</span>}
    </div>
  );
}
