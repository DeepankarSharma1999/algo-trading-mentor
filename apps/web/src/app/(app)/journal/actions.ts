"use server";
import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { engine } from "@/lib/engine";
import type { BehaviourState } from "@/lib/types";

export type NoteState = {
  ok?: boolean;
  error?: string;
  flags?: string[];
  state?: BehaviourState | null;
  /** Set when the row was saved but the engine could not run the lexicon over it. */
  engineNotice?: string;
};

const MAX_LEN = 2000;

/**
 * Adds a journal note, optionally against one closed paper trade. The row is written through Prisma
 * first so the note survives an engine outage; then the engine runs its lexicon over the text and
 * may move the behavioural state. Whatever the engine says is shown back; when it is down the note
 * still stands and the page says so.
 */
export async function addNote(_: NoteState, form: FormData): Promise<NoteState> {
  const user = await requireUser();
  const text = String(form.get("text") ?? "").trim().slice(0, MAX_LEN);
  const tradeIdRaw = String(form.get("trade_id") ?? "").trim();
  if (!text) return { error: "Write something first; an empty note is not saved." };
  let tradeId: string | null = null;
  if (tradeIdRaw) {
    const trade = await db.paperTrade.findFirst({ where: { id: tradeIdRaw, userId: user.id }, select: { id: true } });
    if (!trade) return { error: "That trade is not in your journal." };
    tradeId = trade.id;
  }
  const row = await db.journalNote.create({ data: { userId: user.id, tradeId, text, flags: [] } });

  let flags: string[] = [];
  let state: BehaviourState | null = null;
  let engineNotice: string | undefined;
  try {
    const res = await engine<{ note?: { id?: string; flags?: string[] }; state?: BehaviourState | { state?: BehaviourState } }>("/journal/notes", {
      body: { trade_id: tradeId, text, note_id: row.id },
      userId: user.id,
    });
    flags = Array.isArray(res.note?.flags) ? res.note!.flags!.map(String) : [];
    state = typeof res.state === "string" ? res.state : (res.state?.state ?? null);
    if (flags.length) await db.journalNote.update({ where: { id: row.id }, data: { flags } });
  } catch {
    engineNotice = "Saved. The engine did not answer, so the lexicon has not read this note yet; it will when the engine is back.";
  }
  revalidatePath("/journal");
  return { ok: true, flags, state, engineNotice };
}
