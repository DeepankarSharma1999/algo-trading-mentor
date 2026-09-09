"use client";
import { useActionState, useState } from "react";
import { completeOnboarding, type OnboardingState } from "./actions";
import { rupees } from "@/lib/format";
import { PROFILES, PROFILE_ORDER, oneR } from "@/lib/risk";
import type { RiskProfile } from "@/lib/types";

export function OnboardingForm({ initial }: { initial: { safety: number; longTerm: number; trading: number; profile: RiskProfile } }) {
  const [state, action, pending] = useActionState<OnboardingState, FormData>(completeOnboarding, {});
  const [trading, setTrading] = useState(initial.trading);
  const [profile, setProfile] = useState<RiskProfile>(initial.profile);
  const p = PROFILES[profile];
  const r = oneR(trading, profile);
  return (
    <form action={action}>
      <div className="section">
        <span className="label">Capital buckets</span>
        <div className="ledger">
          <Row id="safety" label="Safety" hint="Emergency money. Never touched by this tool." defaultValue={initial.safety} />
          <Row id="long_term" label="Long-term" hint="Investments you do not trade. Never touched." defaultValue={initial.longTerm} />
          <Row id="trading" label="Trading" hint="The only bucket that ever sizes a paper position." defaultValue={initial.trading} onChange={setTrading} />
        </div>
      </div>

      <div className="section">
        <span className="label">Risk profile</span>
        <div className="ledger">
          {PROFILE_ORDER.map((k) => {
            const q = PROFILES[k];
            return (
              <label key={k} className="row" style={{ cursor: "pointer" }}>
                <span className="cluster"><input type="radio" name="profile" value={k} checked={profile === k} onChange={() => setProfile(k)} /> <span className="mono">{q.label}</span></span>
                <span className="muted">{q.perTradePct}% per trade · {q.dailyR}R daily · {q.weeklyR}R weekly · {q.concurrentR}R concurrent</span>
                <span />
              </label>
            );
          })}
        </div>
        <p className="muted" style={{ marginTop: 10 }}>You can tighten this profile at any time. Loosening it is only possible in RESEARCH state and is written to your journal.</p>
      </div>

      <div className="section">
        <p className="h-display h-display--xl" data-testid="one-r-sentence">
          For you, 1R = <span className="mono" style={{ fontSize: "0.85em" }}>{rupees(r)}</span>
        </p>
        <p className="muted">{p.perTradePct}% of {rupees(trading)}. Daily brake {rupees(r * p.dailyR)}, weekly brake {rupees(r * p.weeklyR)}.</p>
      </div>

      {state.error && <div className="notice notice--blocked" role="alert">{state.error}</div>}
      <div className="cluster" style={{ marginTop: 20 }}>
        <button className="btn btn--primary" disabled={pending}>Sign the firewall and open the desk</button>
      </div>
    </form>
  );
}

function Row({ id, label, hint, defaultValue, onChange }: { id: string; label: string; hint: string; defaultValue: number; onChange?: (n: number) => void }) {
  return (
    <div className="row">
      <label className="label" htmlFor={id}>{label}</label>
      <span className="muted">{hint}</span>
      <span className="cluster" style={{ gap: 6 }}>
        <span className="fig">₹</span>
        <input id={id} name={id} className="input input--inline right" style={{ width: 150 }} inputMode="numeric" defaultValue={defaultValue || ""} placeholder="0" onChange={(e) => onChange?.(Number(e.target.value.replace(/[^\d.]/g, "")) || 0)} required />
      </span>
    </div>
  );
}
