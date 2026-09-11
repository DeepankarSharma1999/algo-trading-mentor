import { requireUser } from "@/lib/auth";
import { OnboardingForm } from "./OnboardingForm";
import type { RiskProfile } from "@/lib/types";

export const dynamic = "force-dynamic";

/** The capital firewall. No chart is shown before this completes. */
export default async function OnboardingPage() {
  const user = await requireUser({ allowUnboarded: true });
  const p = user.profile;
  return (
    <main className="content" style={{ maxWidth: 760, paddingTop: 56 }}>
      <div className="label">Before the desk</div>
      <h1 className="h-display h-display--xl" style={{ marginTop: 8 }}>The capital firewall</h1>
      <p className="muted" style={{ marginTop: 12, maxWidth: 560 }}>
        Split your capital into three buckets. Only the trading bucket ever sizes a paper position, and only through the profile you pick here. Nothing on this page is advice; it is arithmetic on numbers you enter.
      </p>
      <p className="help" style={{ marginTop: 8, maxWidth: 560 }}>
        After this page the flow is three steps: clone a template in the Library, validate it, then watch it paper-trade on the Desk. You can change these figures later in Settings.
      </p>
      <OnboardingForm initial={{ safety: Number(p?.safetyBucket ?? 0), longTerm: Number(p?.longTermBucket ?? 0), trading: Number(p?.tradingBucket ?? 0), profile: (p?.riskProfile ?? "conservative") as RiskProfile }} />
      <p className="footer-note" style={{ padding: "36px 0 0", border: 0 }}>Educational tool. Not SEBI-registered. No recommendations.</p>
    </main>
  );
}
