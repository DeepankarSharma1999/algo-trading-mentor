import { notFound } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import type { JobStatus, ValidationReport } from "@/lib/types";
import { Checklist } from "./Checklist";
import { HeaderActions } from "./HeaderActions";

export const dynamic = "force-dynamic";

/** One validation job: the verdict sentence, then the eight stages as a numbered checklist. Renders from Postgres alone. */
export default async function ValidationJobPage({ params }: { params: Promise<{ jobId: string }> }) {
  const user = await requireUser();
  const { jobId } = await params;
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
      <Checklist initial={job} />
    </>
  );
}
