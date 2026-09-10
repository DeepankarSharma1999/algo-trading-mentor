import Link from "next/link";
import { PlainChip } from "@/components/Chip";
import { requireUser } from "@/lib/auth";
import { listMine } from "@/lib/strategies";
import { validateBlockedReason, watchBlockedReason } from "@/lib/strategies.pure";
import { createDraftAction, validateForm, watchForm } from "./actions";

export const dynamic = "force-dynamic";

/** The user's strategies as a ledger. Every disabled control says why. */
export default async function BuilderIndex({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireUser();
  const sp = await searchParams;
  const notice = Array.isArray(sp.notice) ? sp.notice[0] : sp.notice;
  const mine = await listMine(user.id);
  return (
    <>
      <div className="page-head">
        <h1 className="h-display">Builder</h1>
        <form action={createDraftAction}><button className="btn btn--primary">New strategy</button></form>
      </div>
      {notice && <p className="notice notice--watch" role="status">{notice}</p>}

      <div className="section">
        <span className="label">Your strategies</span>
        <div className="ledger" data-testid="strategies">
          {mine.length === 0 && (
            <div className="row row--wide">
              <span className="label">None</span>
              <span>You have no strategies yet. Start from an empty draft with New strategy, or clone a template in the <Link href="/library">Library</Link>.</span>
            </div>
          )}
          {mine.map((s) => {
            const vReason = validateBlockedReason(s.status);
            const wReason = watchBlockedReason(s.status, s.spec.automation_permission);
            return (
              <div className="row" key={s.id} data-testid="strategy-row">
                <span className="label" style={{ textTransform: "none", letterSpacing: 0 }}><Link href={`/builder/${s.id}`}>{s.id}</Link></span>
                <span>
                  <span>{s.name}</span>
                  <span className="mono muted" style={{ display: "block", fontSize: "var(--fs-1)", marginTop: 2 }}>
                    v{s.version} · {s.spec.timeframe || "no timeframe"} · {s.spec.automation_permission}{s.parentId ? ` · from ${s.parentId}` : ""}
                  </span>
                  {(vReason || wReason) && (
                    <span className="muted" style={{ display: "block", fontSize: "var(--fs-1)", marginTop: 4 }}>
                      {vReason ? `Validate: ${vReason}` : ""}{vReason && wReason ? " " : ""}{wReason ? `Watch: ${wReason}` : ""}
                    </span>
                  )}
                </span>
                <span className="cluster" style={{ gap: 8 }}>
                  <PlainChip>{s.status}</PlainChip>
                  <Link className="btn btn--sm" href={`/builder/${s.id}`}>Open</Link>
                  <form action={validateForm}>
                    <input type="hidden" name="strategy_id" value={s.id} /><input type="hidden" name="back" value="/builder" />
                    <button className="btn btn--sm" disabled={!!vReason} title={vReason ?? "Start the validation pipeline"}>Validate</button>
                  </form>
                  <form action={watchForm}>
                    <input type="hidden" name="strategy_id" value={s.id} /><input type="hidden" name="back" value="/builder" />
                    <button className="btn btn--sm" disabled={!!wReason} title={wReason ?? "Replay this strategy on the Desk in paper mode"}>Watch</button>
                  </form>
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
