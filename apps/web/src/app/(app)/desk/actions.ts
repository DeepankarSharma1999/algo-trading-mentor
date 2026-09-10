"use server";
import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { engine } from "@/lib/engine";

const OVERRIDE_SENTENCE ="Logged. The mentor does not override its own gates; the setup stays as it is.";

/** Stop a watcher. Engine first; if it is down, the row is removed directly so the desk stays honest. */
export async function stopWatching(form: FormData) {
  const user = await requireUser();
  const id = String(form.get("watcher_id") ?? "");
  if (!id) return;
  const own = await db.watcher.findFirst({ where: { id, userId: user.id } });
  if (!own) return;
  try { await engine(`/watchers/${id}`, { method: "DELETE", userId: user.id }); } catch { /* engine down: fall through to the row delete */ }
  await db.watcher.deleteMany({ where: { id, userId: user.id } });
  revalidatePath("/desk");
}

/**
 * The only "override" surface. It records the attempt (engine, or the table directly when the engine is
 * down) and changes nothing else. The sentence is fixed whatever the engine replies.
 */
export async function markEligibleAnyway(what: string): Promise<{ sentence: string }> {
  const user = await requireUser();
  const text = what.slice(0, 200) || "mark eligible anyway";
  try {
    await engine("/behaviour/override", { body: { what: text }, userId: user.id });
  } catch {
    await db.overrideAttempt.create({ data: { userId: user.id, what: text } });
  }
  revalidatePath("/desk");
  return { sentence: OVERRIDE_SENTENCE };
}

export async function explainTrace(signalId: string): Promise<{ prose?: string; error?: string }> {
  const user = await requireUser();
  try {
    const r = await engine<{ prose: string }>("/mentor/explain", { body: { signal_id: signalId }, userId: user.id });
    return { prose: r.prose };
  } catch {
    return { error: "Mentor unavailable." };
  }
}
