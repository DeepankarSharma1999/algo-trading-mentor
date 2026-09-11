import Link from "next/link";
import { PlainChip } from "@/components/Chip";
import { requireUser } from "@/lib/auth";
import { listMine } from "@/lib/strategies";
import { validateBlockedReason, watchBlockedReason } from "@/lib/strategies.pure";
import { createDraftAction, validateForm, watchForm } from "./actions";

export const dynamic = "force-dynamic";

/** The user's strategies as a ledger. Every disabled control says why, in visible text. */
export default async function BuilderIndex({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireUser();
  const sp = await searchParams;
  const notice = Array.isArray(sp.notice) ? sp.notice[0] : sp.notice;
  const mine = await listMine(user.id);
  return (
    <>
      <div className="page-head">
        <h1 className="h-display">Builder</h1>
        {mine.length > 0 && <form action={createDraftAction}><button className="btn btn--primary">New strategy</button></form>}
      </div>
      <p className="page-intro">
        Your strategies live here. Each one is a spec you write yourself: which symbols, which indicators, when to enter, where the stop
        goes, how to exit and how much to risk. Open a strategy to edit it, Validate it to run the eight-stage pipeline on synthetic data,
        and Watch a validated paper-only strategy on the Desk. Nothing here trades live.
      </p>
      <p className="help" style={{ margin: "-10px 0 18px", maxWidth: "64ch" }}>
        Status: <span className="mono">draft</span> means pieces are still missing; <span className="mono">testable</span> means every
        required piece is present and Validate is available; <span className="mono">validated</span> means the pipeline ran and passed.
        Changing a validated strategy saves a new version marked <span className="mono">untested</span> until you validate it again.
      </p>
      {notice && <p className="notice notice--watch" role="status">{notice}</p>}

      <div className="section" style={{ marginTop: mine.length === 0 ? 8 : undefined }}>
        <span className="label">Your strategies</span>
        <div className="ledger" data-testid="strategies">
          {mine.length === 0 && (
            <div className="empty">
              <p>You have no strategies yet. Start from an empty draft, or clone one of the templates in the Library and change its symbols and rules.</p>
              <span className="cluster">
                <form action={createDraftAction}><button className="btn btn--primary">New strategy</button></form>
                <Link className="btn" href="/library">Clone a template</Link>
              </span>
            </div>
          )}
          {mine.map((s) => {
            const vReason = validateBlockedReason(s.status);
            const wReason = watchBlockedReason(s.status, s.spec.automation_permission);
            const vWhy = vReason ? "Validate needs a testable strategy: open it to see what is missing." : null;
            const wWhy = wReason
              ? s.status !== "validated"
                ? "Watch needs a validated, paper-only strategy: validate it first."
                : `Watch needs a validated, paper-only strategy: this one is ${s.spec.automation_permission}. Change the permission in the editor.`
              : null;
            return (
              <div className="row" key={s.id} data-testid="strategy-row">
                <span className="label" style={{ textTransform: "none", letterSpacing: 0 }}><Link href={`/builder/${s.id}`}>{s.id}</Link></span>
                <span>
                  <span style={{ fontSize: "var(--fs-3)" }}>{s.name}</span>
                  <span className="mono muted" style={{ display: "block", fontSize: "var(--fs-1)", marginTop: 2 }}>
                    v{s.version} · {s.spec.timeframe || "no timeframe"} · {s.spec.instruments.length ? s.spec.instruments.join(", ") : "no symbols yet"} · {s.spec.automation_permission}{s.parentId ? ` · from ${s.parentId}` : ""}
                  </span>
                </span>
                <span style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end", maxWidth: 360 }}>
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
                  {vWhy && <span className="help right">{vWhy}</span>}
                  {wWhy && <span className="help right">{wWhy}</span>}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
