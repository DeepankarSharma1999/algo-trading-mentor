import { currentUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { engine } from "@/lib/engine";
import type { JobStatus, ValidationReport } from "@/lib/types";

/**
 * Client polling target for the validation checklist. Proxies engine GET /jobs/{id}; when the
 * engine is unreachable the reply comes from the `validation_jobs` row instead (the engine writes
 * that row after every stage), so polling never breaks the page. Only the job's owner may read it.
 */
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const user = await currentUser();
  if (!user) return Response.json({ error: "Sign in to read validation jobs." }, { status: 401 });
  const { id } = await ctx.params;
  const row = await db.validationJob.findFirst({ where: { id, userId: user.id } });
  if (!row) return Response.json({ error: "No such validation job." }, { status: 404 });
  const fromRow: JobStatus = {
    id: row.id,
    status: row.status as JobStatus["status"],
    current_stage: row.currentStage,
    report: row.report as unknown as ValidationReport | null,
    error: row.error,
  };
  try {
    const live = await engine<JobStatus>(`/jobs/${id}`, { userId: user.id });
    return Response.json({ ...fromRow, ...live, source: "engine" }, { headers: { "cache-control": "no-store" } });
  } catch {
    return Response.json({ ...fromRow, source: "db" }, { headers: { "cache-control": "no-store" } });
  }
}
