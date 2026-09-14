"use client";
import { useState, useTransition } from "react";
import { PlainChip } from "@/components/Chip";
import type { SpecPatch, SuggestReply, Suggestion } from "@/lib/types";
import { applyPatches, suggestChanges, type SuggestState } from "../actions";

const SOURCE: Record<SuggestReply["source"], string> = {
  gemini: "via gemini",
  anthropic: "via anthropic",
  template: "template suggestions — set GEMINI_API_KEY for AI suggestions",
};

/** A patch value on one mono line. Strings print bare; anything else as compact JSON. */
const show = (v: unknown): string => (v === undefined ? "–" : typeof v === "string" ? v : JSON.stringify(v));

/**
 * "Ask the mentor for changes": `POST /mentor/suggest` through a server action, then the prose and a ledger
 * of suggestions, each with its patch as `path: from → to` lines and an Apply button. Apply (and Apply all)
 * writes the patched spec as the next version and opens the Builder there. Fails soft in one sentence.
 */
export function Suggestions({ jobId }: { jobId: string }) {
  const [state, setState] = useState<SuggestState>({});
  const [applyError, setApplyError] = useState<string | null>(null);
  const [asking, startAsk] = useTransition();
  const [applying, startApply] = useTransition();

  const ask = () => startAsk(async () => { setApplyError(null); setState(await suggestChanges(jobId)); });
  const apply = (patches: SpecPatch[]) => startApply(async () => {
    setApplyError(null);
    const r = await applyPatches(jobId, patches);
    if (r?.error) setApplyError(r.error);
  });

  const reply = state.reply;
  const withPatch = reply?.suggestions.filter((s) => s.patch.length > 0) ?? [];
  const noEdge = reply?.verdict === "no_edge";

  return (
    <div data-testid="suggestions">
      <span className="label">{noEdge ? "The mentor thinks these rules have no edge" : "Ask the mentor for changes"}</span>
      <div className="cluster" style={{ marginTop: 8, alignItems: "flex-start" }}>
        <button type="button" className="btn" disabled={asking} onClick={ask} aria-describedby="suggest-help">
          {asking ? "Asking the mentor…" : reply ? "Ask again" : "Ask the mentor for changes"}
        </button>
        <p id="suggest-help" className="help" style={{ margin: 0, maxWidth: "52ch" }}>
          The mentor reads this report and proposes edits to your own rules as patches. Nothing is applied until you press Apply, and every Apply becomes the next version.
        </p>
      </div>
      {asking && <p className="mono muted" role="status" style={{ margin: "8px 0 0", fontSize: "var(--fs-1)" }}>Asking the mentor…</p>}
      {state.error && !asking && <p className="notice notice--watch" role="status" data-testid="suggest-error">{state.error}</p>}
      {applyError && <p className="notice notice--blocked" role="alert" data-testid="apply-error">{applyError}</p>}

      {reply && !asking && (
        <div style={{ marginTop: 10 }} data-testid="suggest-reply" data-verdict={reply.verdict}>
          <p className="mono faint" style={{ margin: "0 0 6px", fontSize: "var(--fs-1)" }}>{SOURCE[reply.source]}</p>
          {reply.verdict === "passed" ? (
            <p className="muted" style={{ margin: 0 }}>{reply.prose || "This run passed; the mentor has nothing to change."}</p>
          ) : noEdge ? (
            <div className="notice notice--watch" style={{ margin: 0 }}>{reply.prose || "The mentor found no edge to keep in these rules."}</div>
          ) : (
            reply.prose && <p style={{ margin: 0, maxWidth: "70ch" }}>{reply.prose}</p>
          )}

          {reply.suggestions.length > 0 && (
            <div className="ledger" style={{ marginTop: 10 }}>
              {reply.suggestions.map((s) => (
                <SuggestionRow key={s.id} s={s} busy={applying} onApply={() => apply(s.patch)} />
              ))}
            </div>
          )}
          {reply.suggestions.length === 0 && reply.verdict !== "passed" && <p className="muted" style={{ margin: "8px 0 0" }}>The mentor made no concrete suggestion for this run.</p>}
          {withPatch.length > 1 && (
            <div className="cluster" style={{ marginTop: 12, alignItems: "flex-start" }}>
              <button type="button" className="btn" disabled={applying} onClick={() => apply(withPatch.flatMap((s) => s.patch))}>
                {applying ? "Applying…" : `Apply all (${withPatch.length})`}
              </button>
              <span className="help" style={{ maxWidth: "48ch" }}>Every patch above, in order, into one new version.</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SuggestionRow({ s, busy, onApply }: { s: Suggestion; busy: boolean; onApply: () => void }) {
  const applicable = s.patch.length > 0;
  return (
    <div className="row" data-testid="suggestion" data-kind={s.kind}>
      <span><PlainChip>{s.kind}</PlainChip></span>
      <div className="value">
        <div>{s.title}</div>
        {s.reason && <div className="muted" style={{ marginTop: 3, maxWidth: "70ch" }}>{s.reason}</div>}
        {applicable ? (
          <div className="mono" style={{ marginTop: 6, fontSize: "var(--fs-1)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {s.patch.map((p, i) => <div key={i}>{p.path}: {show(p.from)} → {show(p.to)}</div>)}
          </div>
        ) : (
          <div className="faint mono" style={{ marginTop: 6, fontSize: "var(--fs-1)" }}>no patch: advice only</div>
        )}
      </div>
      <button type="button" className="btn btn--sm" disabled={busy || !applicable} onClick={onApply} title={applicable ? "Save as the next version and open it" : "Nothing to apply"}>
        {busy ? "Applying…" : "Apply"}
      </button>
    </div>
  );
}
