"use server";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { EngineError, engine } from "@/lib/engine";
import { applyPatch, sectionForPath } from "@/lib/patch";
import { getStrategy, saveSpec } from "@/lib/strategies";
import type { JobStatus, SpecPatch, SuggestReply, Suggestion, ValidationReport } from "@/lib/types";
import { findingsOf, firstLeverSection } from "./report";

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

// ---- §4b fix-it flow -------------------------------------------------------------------------------------

export type SuggestState = { reply?: SuggestReply; error?: string };
const PANEL_STANDS = "The panel above still stands.";

const asJob = (row: { status: string; report: unknown }) => ({ status: row.status as JobStatus["status"], report: row.report as unknown as ValidationReport | null });

/**
 * "Edit and re-test": copies the tested version's rules into the next version (always a bump, so this report
 * stays attached to the version it tested) and opens the Builder at the first lever's section.
 */
export async function editAndRetest(jobId: string): Promise<void> {
  const user = await requireUser();
  const job = await db.validationJob.findFirst({ where: { id: jobId, userId: user.id } });
  if (!job) redirect(`/validation?error=${encodeURIComponent("No such validation job.")}`);
  const section = firstLeverSection(findingsOf(asJob(job)));
  let next: string;
  try {
    const s = await getStrategy(job.strategyId, user.id);
    if (!s) throw new Error(`Strategy ${job.strategyId} no longer exists, so there is nothing to edit.`);
    next = (await saveSpec(user.id, s.id, s.spec, { newVersion: true })).id;
  } catch (e) {
    redirect(`/validation/${jobId}?error=${encodeURIComponent(e instanceof Error ? e.message : "The next version could not be created.")}`);
  }
  revalidatePath("/builder");
  redirect(`/builder/${next}?section=${section}`);
}

const isPatch = (p: unknown): p is SpecPatch => !!p && typeof p === "object" && typeof (p as SpecPatch).path === "string";
const isSuggestion = (s: unknown): s is Suggestion => !!s && typeof s === "object" && typeof (s as Suggestion).title === "string" && Array.isArray((s as Suggestion).patch);

/** Asks the engine for mentor suggestions (`POST /mentor/suggest`). Fails soft: a sentence, never a thrown error. */
export async function suggestChanges(jobId: string): Promise<SuggestState> {
  const user = await requireUser();
  const job = await db.validationJob.findFirst({ where: { id: jobId, userId: user.id } });
  if (!job) return { error: "No such validation job." };
  if (!job.report) return { error: "There is no report to work from yet. Suggestions need a finished run." };
  try {
    const r = await engine<Partial<SuggestReply>>("/mentor/suggest", { body: { job_id: jobId }, userId: user.id });
    const suggestions = (Array.isArray(r.suggestions) ? r.suggestions : []).filter(isSuggestion).map((s, i) => ({
      id: typeof s.id === "string" && s.id ? s.id : `s${i + 1}`, title: s.title, reason: typeof s.reason === "string" ? s.reason : "",
      kind: s.kind === "fix" || s.kind === "tune" || s.kind === "simplify" || s.kind === "stop" ? s.kind : "tune", patch: s.patch.filter(isPatch),
    }));
    return { reply: {
      prose: typeof r.prose === "string" ? r.prose : "",
      verdict: r.verdict === "no_edge" || r.verdict === "passed" ? r.verdict : "fixable",
      source: r.source === "gemini" || r.source === "anthropic" ? r.source : "template",
      suggestions,
    } };
  } catch (e) {
    if (e instanceof EngineError && e.status === 404) return { error: `This engine does not offer suggestions yet (POST /mentor/suggest is not implemented). ${PANEL_STANDS}` };
    if (e instanceof Error && e.message && !/fetch failed|ECONNREFUSED/i.test(e.message)) return { error: `The mentor did not answer: ${e.message}. ${PANEL_STANDS}` };
    return { error: `The mentor did not answer because the engine is unreachable. ${PANEL_STANDS}` };
  }
}

/**
 * Applies one suggestion's patches (or every suggestion's, in order, for "Apply all") to the tested strategy,
 * saves the result as the next version and opens the Builder at the section the first patch touches.
 * Protected roots are rejected before anything is written.
 */
export async function applyPatches(jobId: string, patches: SpecPatch[]): Promise<{ error?: string }> {
  const user = await requireUser();
  const job = await db.validationJob.findFirst({ where: { id: jobId, userId: user.id } });
  if (!job) return { error: "No such validation job." };
  const list = Array.isArray(patches) ? patches.filter(isPatch) : [];
  if (list.length === 0) return { error: "This suggestion carries no patch to apply; it is advice only." };
  let next: string;
  try {
    const s = await getStrategy(job.strategyId, user.id);
    if (!s) return { error: `Strategy ${job.strategyId} no longer exists, so there is nothing to patch.` };
    next = (await saveSpec(user.id, s.id, applyPatch(s.spec, list), { newVersion: true })).id;
  } catch (e) {
    return { error: e instanceof Error ? e.message : "The patch could not be applied." };
  }
  revalidatePath("/builder");
  redirect(`/builder/${next}?section=${sectionForPath(list[0].path)}`);
}
