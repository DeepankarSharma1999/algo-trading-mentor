"use client";
import { useActionState, useEffect, useRef } from "react";
import { addNote, type NoteState } from "./actions";

export const LEXICON_SENTENCE = "This note matched the revenge/FOMO lexicon; your state may have moved to ELEVATED.";

/** One textarea and a button. With `tradeId` the note attaches to that trade; without, it is a free note. */
export function NoteForm({ tradeId, label = "Add note" }: { tradeId?: string; label?: string }) {
  const [st, action, pending] = useActionState<NoteState, FormData>(addNote, {});
  const ref = useRef<HTMLFormElement>(null);
  useEffect(() => { if (st.ok) ref.current?.reset(); }, [st]);
  return (
    <form ref={ref} action={action} className="stack" data-testid={tradeId ? "trade-note-form" : "note-form"}>
      {tradeId && <input type="hidden" name="trade_id" value={tradeId} />}
      <textarea className="input" name="text" placeholder={tradeId ? "What happened on this trade, in your own words." : "Anything about the session. The lexicon reads it; nothing here is sent anywhere else."} maxLength={2000} required />
      <div className="cluster">
        <button className="btn btn--sm" disabled={pending}>{pending ? "Saving…" : label}</button>
        {st.ok && !st.engineNotice && <span className="muted">Saved.</span>}
      </div>
      {st.error && <p className="field-error" role="alert" style={{ margin: 0 }}>{st.error}</p>}
      {st.engineNotice && <p className="notice notice--watch" role="status" style={{ margin: 0 }}>{st.engineNotice}</p>}
      {st.ok && st.flags && st.flags.length > 0 && (
        <p className="notice notice--watch" role="status" style={{ margin: 0 }}>
          <span className="mono">{st.flags.join(", ")}</span> · {LEXICON_SENTENCE}
        </p>
      )}
      {st.ok && st.state && <p className="mono muted" style={{ margin: 0, fontSize: "var(--fs-1)" }}>state: {st.state}</p>}
    </form>
  );
}
