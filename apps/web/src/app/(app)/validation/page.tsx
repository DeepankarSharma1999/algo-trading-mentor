import Link from "next/link";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { ts } from "@/lib/format";
import { startValidation } from "./actions";
import { STAGE_COUNT } from "./report";

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
      {error && <div className="notice notice--blocked" role="alert">{error}</div>}

      <div className="section">
        <span className="label">Validation jobs</span>
        {jobs.length === 0 ? (
          <p className="muted">No validation jobs yet. Queue one from the strategies below, or from the Builder.</p>
        ) : (
          <div className="table-scroll">
            <table className="ledger-table">
              <thead>
                <tr><th>Strategy</th><th>Status</th><th className="num">Stage</th><th>Created</th><th>Finished</th><th></th></tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td>{j.strategyId}</td>
                    <td><span className={`status ${j.status === "done" ? "status--eligible" : j.status === "failed" ? "status--blocked" : ""}`}>{j.status}</span></td>
                    <td className="num">{j.currentStage}/{STAGE_COUNT}</td>
                    <td>{ts(j.createdAt)}</td>
                    <td>{j.finishedAt ? ts(j.finishedAt) : "–"}</td>
                    <td><Link href={`/validation/${j.id}`}>Open</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="section">
        <span className="label">Queue a run</span>
        {strategies.length === 0 ? (
          <p className="muted">You have no strategies yet. Clone a template in the Library or write one in the Builder; validation runs against your own versions only.</p>
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
        <p className="muted" style={{ marginTop: 10 }}>A run works through eight stages in order and stops at the first hard failure. Stages 6 and 8 are informational.</p>
      </div>
    </>
  );
}
