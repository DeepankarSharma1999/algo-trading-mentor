"use client";
import { useActionState, useEffect, useId, useRef } from "react";
import { addNote, type NoteState } from "./actions";

export const LEXICON_SENTENCE = "This note matched the revenge/FOMO lexicon; your state may have moved to ELEVATED.";

/** One textarea and a button. With `tradeId` the note attaches to that trade; without, it is a free note. */
export function NoteForm({ tradeId, label = "Add note" }: { tradeId?: string; label?: string }) {
  const [st, action, pending] = useActionState<NoteState, FormData>(addNote, {});
  const ref = useRef<HTMLFormElement>(null);
  const helpId = useId();
  useEffect(() => { if (st.ok) ref.current?.reset(); }, [st]);
  return (
    <form ref={ref} action={action} className="stack" data-testid={tradeId ? "trade-note-form" : "note-form"}>
      {tradeId && <input type="hidden" name="trade_id" value={tradeId} />}
      <div>
        <label className="label" htmlFor={`${helpId}-text`} style={{ display: "block", marginBottom: 4 }}>{tradeId ? "Note on this trade" : "New note"}</label>
        <textarea id={`${helpId}-text`} className="input" name="text" aria-describedby={helpId} placeholder={tradeId ? "What happened on this trade, in your own words." : "Anything about the session."} maxLength={2000} required />
        <p id={helpId} className="help help--tight" style={{ margin: "4px 0 0" }}>Free text, up to 2000 characters. Words from the revenge/FOMO list move your state to ELEVATED; that is a feature, not a fault. Nothing here is sent anywhere else.</p>
      </div>
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
