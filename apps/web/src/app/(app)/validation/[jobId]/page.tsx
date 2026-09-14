import { notFound } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import type { JobStatus, ValidationReport } from "@/lib/types";
import { findingsOf } from "../report";
import { Checklist } from "./Checklist";
import { FixIt } from "./FixIt";
import { HeaderActions } from "./HeaderActions";

export const dynamic = "force-dynamic";

/**
 * One validation job: the verdict sentence, the eight stages as a numbered checklist, and, on a failed run
 * with a diagnosis, "What you can change". Renders from Postgres alone; `?error=` carries a fix-it action's failure.
 */
export default async function ValidationJobPage({ params, searchParams }: { params: Promise<{ jobId: string }>; searchParams: Promise<{ error?: string | string[] }> }) {
  const user = await requireUser();
  const [{ jobId }, sp] = await Promise.all([params, searchParams]);
  const error = Array.isArray(sp.error) ? sp.error[0] : sp.error;
  const row = await db.validationJob.findFirst({ where: { id: jobId, userId: user.id } });
  if (!row) notFound();
  const job: JobStatus = {
    id: row.id,
    status: row.status as JobStatus["status"],
    current_stage: row.currentStage,
    report: row.report as unknown as ValidationReport | null,
    error: row.error,
  };
  return (
    <>
      <div className="page-head">
        <h1 className="h-display">Validation · <span className="mono" style={{ fontSize: "0.8em" }}>{row.strategyId}</span></h1>
        <HeaderActions jobId={row.id} strategyId={row.strategyId} hasReport={!!row.report} />
      </div>
      {error && <div className="notice notice--blocked" role="alert" data-testid="fixit-error">{error}</div>}
      <Checklist initial={job} />
      <FixIt jobId={row.id} strategyId={row.strategyId} findings={findingsOf(job)} />
    </>
  );
}
