"use client";
import { useState, useTransition } from "react";
import { explainTrace, markEligibleAnyway } from "./actions";

/** Buttons under a rule trace. "Mark eligible anyway" only ever logs; "Explain this trace" asks the mentor. */
export function SignalActions({ signalId, dbSignalId, verdict, strategyId }: { signalId: string; dbSignalId: string; verdict: string; strategyId: string }) {
  const [pending, start] = useTransition();
  const [overrideNote, setOverrideNote] = useState<string | null>(null);
  const [explain, setExplain] = useState<{ prose?: string; error?: string } | null>(null);
  return (
    <div style={{ marginTop: 18 }}>
      <div className="cluster">
        {verdict !== "eligible" && (
          <button className="btn" disabled={pending} onClick={() => start(async () => { const r = await markEligibleAnyway(`mark eligible anyway: ${strategyId} signal ${signalId}`); setOverrideNote(r.sentence); })}>
            Mark eligible anyway
          </button>
        )}
        <button className="btn" disabled={pending} onClick={() => start(async () => setExplain(await explainTrace(dbSignalId)))}>
          Explain this trace
        </button>
      </div>
      {overrideNote && <p className="notice" role="status" data-testid="override-note">{overrideNote}</p>}
      {explain?.prose && <p className="notice" data-testid="explain-prose">{explain.prose}</p>}
      {explain?.error && <p className="notice notice--watch" data-testid="explain-error">{explain.error}</p>}
    </div>
  );
}
