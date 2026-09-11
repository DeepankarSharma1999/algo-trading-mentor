import Link from "next/link";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { ts } from "@/lib/format";
import type { ValidationReport } from "@/lib/types";
import { startValidation } from "./actions";
import { plainStatus } from "./report";

export const dynamic = "force-dynamic";

/** Ledger of the user's validation jobs, newest first, plus one row per strategy to queue a run. */
export default async function ValidationIndex({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const user = await requireUser();
  const { error } = await searchParams;
  const [jobs, strategies] = await Promise.all([
    db.validationJob.findMany({ where: { userId: user.id }, orderBy: { createdAt: "desc" }, take: 100 }),
    db.strategy.findMany({ where: { userId: user.id }, orderBy: [{ slug: "asc" }, { version: "desc" }] }),
  ]);
  return (
    <>
      <div className="page-head"><h1 className="h-display">Validation</h1></div>
      <p className="page-intro">
        Validation is an eight-stage test of one strategy version against the synthetic history. The stages run in order and the run stops at the first hard failure; when it finishes, the weakest stage is named in one sentence. Stages 6 and 8 inform but never fail a run. <Link href="/help">The eight stages are listed in Help.</Link>
      </p>
      {error && <div className="notice notice--blocked" role="alert">{error}</div>}

      <div className="section">
        <span className="label">Validation jobs</span>
        {jobs.length === 0 ? (
          <div className="empty" data-testid="jobs-empty">
            <p>No validation runs yet. A run starts from a strategy in the Builder, or from the list below once you have one.</p>
            <Link className="btn" href="/builder">Open the Builder</Link>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="ledger-table" data-testid="jobs">
              <thead>
                <tr><th>Strategy</th><th>Status</th><th>Created</th><th>Finished</th><th></th></tr>
              </thead>
              <tbody>
                {jobs.map((j) => {
                  const st = plainStatus({ status: j.status as "queued" | "running" | "done" | "failed", current_stage: j.currentStage, report: j.report as unknown as ValidationReport | null, error: j.error });
                  return (
                    <tr key={j.id}>
                      <td>{j.strategyId}</td>
                      <td className={st.cls} style={{ fontFamily: "var(--font-ui)" }}>{st.text}</td>
                      <td style={{ whiteSpace: "nowrap" }}>{ts(j.createdAt)}</td>
                      <td style={{ whiteSpace: "nowrap" }}>{j.finishedAt ? ts(j.finishedAt) : "–"}</td>
                      <td><Link href={`/validation/${j.id}`}>Open</Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="section">
        <span className="label">Queue a run</span>
        <p className="help help--tight">One row per version you own. A new run does not replace an old report; both stay in the list above.</p>
        {strategies.length === 0 ? (
          <div className="empty">
            <p>You have no strategies yet. Clone a template in the Library or write one in the Builder; validation runs against your own versions only.</p>
            <span className="cluster"><Link className="btn" href="/library">Open the Library</Link><Link className="btn" href="/builder">Open the Builder</Link></span>
          </div>
        ) : (
          <div className="ledger">
            {strategies.map((s) => (
              <form key={s.id} action={startValidation.bind(null, s.id)} className="row">
                <span className="mono">{s.id}</span>
                <span className="muted">{s.name} · <span className="mono">{s.status}</span></span>
                <button className="btn btn--sm">Run validation</button>
              </form>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
