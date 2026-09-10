"use server";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { checkTestable, type Strategy } from "@atm/schema";
import { requireUser } from "@/lib/auth";
import { engine } from "@/lib/engine";
import { createDraft, getStrategy, saveSpec } from "@/lib/strategies";
import { validateBlockedReason, watchBlockedReason } from "@/lib/strategies.pure";

const ENGINE_DOWN = "The engine is not reachable right now, so nothing was started. Your strategy is unchanged; try again when the engine is up.";

function back(form: FormData, fallback = "/builder") {
  const b = String(form.get("back") ?? "");
  return b.startsWith("/") ? b : fallback;
}
const withNotice = (path: string, notice: string) => `${path}${path.includes("?") ? "&" : "?"}notice=${encodeURIComponent(notice)}`;

/** "New strategy": an empty draft, opened in the editor. */
export async function createDraftAction() {
  const user = await requireUser();
  const id = await createDraft(user.id);
  redirect(`/builder/${id}`);
}

/** Ask the engine to validate a strategy. Returns a job id or a plain sentence saying why not. */
export async function requestValidation(strategyId: string): Promise<{ jobId?: string; error?: string }> {
  const user = await requireUser();
  const s = await getStrategy(strategyId, user.id);
  if (!s) return { error: "That strategy does not exist." };
  const blocked = validateBlockedReason(s.status);
  if (blocked) return { error: blocked };
  const check = checkTestable(s.spec);
  if (!check.testable) return { error: `Not testable yet: ${check.missing.join(" ")}` };
  try {
    const r = await engine<{ job_id: string }>("/validate", { body: { strategy_id: strategyId }, userId: user.id });
    return { jobId: r.job_id };
  } catch {
    return { error: ENGINE_DOWN };
  }
}

/** Form version of requestValidation for the Builder index. */
export async function validateForm(form: FormData) {
  const r = await requestValidation(String(form.get("strategy_id") ?? ""));
  if (r.jobId) redirect(`/validation/${r.jobId}`);
  redirect(withNotice(back(form), r.error ?? "Validation could not start."));
}

/** Watch a validated paper_only strategy on the Desk. The engine owns watchers; without it nothing starts. */
export async function watchForm(form: FormData) {
  const user = await requireUser();
  const strategyId = String(form.get("strategy_id") ?? "");
  const s = await getStrategy(strategyId, user.id);
  if (!s) redirect(withNotice(back(form), "That strategy does not exist."));
  const blocked = watchBlockedReason(s.status, s.spec.automation_permission);
  if (blocked) redirect(withNotice(back(form), blocked));
  let ok = false;
  try { await engine("/watchers", { body: { strategy_id: strategyId }, userId: user.id }); ok = true; } catch { ok = false; }
  if (!ok) redirect(withNotice(back(form), ENGINE_DOWN));
  revalidatePath("/desk");
  redirect("/desk");
}

/** Save from the editor. A validated strategy becomes a new untested version; the reply carries the id to open. */
export async function saveSpecAction(id: string, spec: Strategy): Promise<{ id?: string; created?: boolean; status?: string; error?: string }> {
  const user = await requireUser();
  try {
    const r = await saveSpec(user.id, id, spec);
    revalidatePath("/builder");
    revalidatePath(`/builder/${r.id}`);
    return r;
  } catch (e) {
    return { error: e instanceof Error ? e.message : "The strategy could not be saved." };
  }
}

/** Turn free text into a draft spec through the mentor. Fails soft. */
export async function formaliseAction(text: string): Promise<{ draft?: Strategy; ambiguity_flags?: string[]; prose?: string; error?: string }> {
  const user = await requireUser();
  const t = text.trim();
  if (!t) return { error: "Write the rules first, then formalise." };
  try {
    return await engine<{ draft: Strategy; ambiguity_flags: string[]; prose: string }>("/mentor/formalise", { body: { text: t }, userId: user.id });
  } catch {
    return { error: "Mentor unavailable. The engine is not reachable; your text is still in the box." };
  }
}
