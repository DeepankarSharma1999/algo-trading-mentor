"use server";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { engine } from "@/lib/engine";

export type ActionState = { error?: string };
export type ReviewState = { prose?: string; next_step?: string; weakest_stage?: number | null; error?: string };

const ENGINE_DOWN = "The engine did not answer, so nothing was queued. The report below is unchanged; try again once the engine is up.";

/** Queues a validation run for one of the user's strategies and opens the new job. */
export async function startValidation(strategyId: string): Promise<void> {
  const user = await requireUser();
  const strat = await db.strategy.findFirst({ where: { id: strategyId, userId: user.id } });
  if (!strat) redirect(`/validation?error=${encodeURIComponent("That strategy is not yours or does not exist.")}`);
  let jobId: string | null = null;
  try {
    const res = await engine<{ job_id: string }>("/validate", { body: { strategy_id: strategyId }, userId: user.id });
    jobId = res.job_id;
  } catch (e) {
    const msg = e instanceof Error && e.message && !/fetch failed|ECONNREFUSED/i.test(e.message) ? e.message : ENGINE_DOWN;
    redirect(`/validation?error=${encodeURIComponent(msg)}`);
  }
  redirect(`/validation/${jobId}`);
}

/** Header button on a job page. Same call, but the error stays on the page instead of a redirect. */
export async function rerunValidation(_: ActionState, form: FormData): Promise<ActionState> {
  const user = await requireUser();
  const strategyId = String(form.get("strategy_id") ?? "");
  const strat = await db.strategy.findFirst({ where: { id: strategyId, userId: user.id } });
  if (!strat) return { error: "That strategy is not yours or does not exist." };
  let jobId: string;
  try {
    jobId = (await engine<{ job_id: string }>("/validate", { body: { strategy_id: strategyId }, userId: user.id })).job_id;
  } catch (e) {
    return { error: e instanceof Error && e.message && !/fetch failed|ECONNREFUSED/i.test(e.message) ? e.message : ENGINE_DOWN };
  }
  redirect(`/validation/${jobId}`);
}

/** Asks the mentor for a review of the report. Prose only; the mentor never names an instrument or a direction. */
export async function mentorReview(_: ReviewState, form: FormData): Promise<ReviewState> {
  const user = await requireUser();
  const jobId = String(form.get("job_id") ?? "");
  const job = await db.validationJob.findFirst({ where: { id: jobId, userId: user.id } });
  if (!job) return { error: "No such validation job." };
  if (!job.report) return { error: "There is no report to review yet. The mentor can review once the run has produced stages." };
  try {
    const res = await engine<{ prose: string; weakest_stage: number | null; next_step: string }>("/mentor/review", { body: { job_id: jobId }, userId: user.id });
    return { prose: res.prose, next_step: res.next_step, weakest_stage: res.weakest_stage };
  } catch (e) {
    return { error: e instanceof Error && e.message && !/fetch failed|ECONNREFUSED/i.test(e.message) ? e.message : "The mentor did not answer because the engine is unreachable. The report itself is complete; read the weakest-stage sentence above." };
  }
}
