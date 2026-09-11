"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { JobStatus } from "@/lib/types";
import { STAGE_CHECKS, STAGE_COUNT, gateClass, headline, isActive, keyMetrics, openByDefault, stagesOf, statusWord } from "../report";
import { StageDetail } from "./StageDetail";

const POLL_MS = 1500;

/**
 * The eight stages as a vertical, numbered checklist. Polls /api/jobs/[id] every 1.5s while the job
 * is queued or running; unrun stages carry data-state="pending" so they fade in (120ms, primitives.css)
 * as the engine writes them. The weakest stage and the running stage open by default.
 */
export function Checklist({ initial }: { initial: JobStatus }) {
  const [job, setJob] = useState<JobStatus>(initial);
  const [source, setSource] = useState<"engine" | "db" | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [toggled, setToggled] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (!isActive(job)) return;
    let stop = false;
    const tick = async () => {
      try {
        const res = await fetch(`/api/jobs/${job.id}`, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const next = (await res.json()) as JobStatus & { source?: "engine" | "db" };
        if (stop) return;
        setJob({ id: next.id, status: next.status, current_stage: next.current_stage, report: next.report, error: next.error });
        setSource(next.source ?? null);
        setPollError(null);
      } catch (e) {
        if (!stop) setPollError(e instanceof Error ? e.message : "poll failed");
      }
    };
    const h = setInterval(tick, POLL_MS);
    return () => { stop = true; clearInterval(h); };
  }, [job.id, job.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const stages = stagesOf(job.report);
  const head = headline(job);
  const defaults = openByDefault(job);
  const isOpen = (n: number) => toggled[n] ?? defaults.has(n);

  return (
    <>
      {head.mono ? (
        <p className="mono" data-testid="headline" style={{ margin: "0 0 6px" }}>{head.text}</p>
      ) : (
        <>
          <p className="h-display" data-testid="headline" style={{ fontSize: "var(--fs-4)", margin: "0 0 6px", maxWidth: 760 }}>{head.text}</p>
          <p className="help" style={{ margin: "0 0 6px" }}>
            The sentence names the stage with the least margin, even on a run that passed. <Link href="/help">The eight stages are listed in Help.</Link>
          </p>
        </>
      )}
      {isActive(job) && (
        <p className="help" style={{ margin: 0 }} role="status">
          {source === "db" ? "The engine is not answering; showing the last stage it wrote to the database. " : ""}
          {pollError ? `Polling paused: ${pollError}. ` : ""}
          This page updates on its own. Stages fill in as they finish; nothing to refresh.
        </p>
      )}
      {job.status === "failed" && job.error && <div className="notice notice--blocked" role="alert">{job.error}</div>}

      <div className="section">
        <span className="label">Stages · {job.status === "done" ? (job.report?.passed ? "validated" : "not validated") : job.status === "running" ? `running stage ${Math.max(1, Math.min(STAGE_COUNT, job.current_stage || 1))} of ${STAGE_COUNT}` : job.status}</span>
        <div className="ledger" data-testid="stages">
          {stages.map((s) => {
            const sw = statusWord(s.status);
            const running = job.status === "running" && job.current_stage === s.stage;
            const open = isOpen(s.stage);
            return (
              <div key={s.stage} className="stage" data-state={s.status === "pending" && !running ? "pending" : undefined} data-stage={s.stage}>
                <span className="stage__num">{s.stage}</span>
                <div style={{ minWidth: 0 }}>
                  <div className="cluster" style={{ gap: 10 }}>
                    <span>{s.name}</span>
                    <span className={sw.cls} data-testid={`status-${s.stage}`}>
                      <span className={gateClass(s.status, running)} aria-hidden="true" />
                      {running ? "RUNNING" : sw.word}
                    </span>
                  </div>
                  <div className="help" style={{ marginTop: 2 }}>{STAGE_CHECKS[s.stage]}</div>
                  {s.summary && <div className="muted" style={{ marginTop: 5 }}>{s.summary}</div>}
                  {s.status === "pending" && !s.summary && (
                    <div className="faint" style={{ marginTop: 5 }}>{running ? "Running now." : job.status === "failed" ? "Not reached." : job.status === "done" ? "Not reached; an earlier stage failed." : "Waiting for the earlier stages."}</div>
                  )}
                  {keyMetrics(s).length > 0 && (
                    <div className="cluster mono" style={{ gap: 14, marginTop: 5, fontSize: "var(--fs-1)" }}>
                      {keyMetrics(s).map(([k, v]) => (
                        <span key={k}><span className="faint">{k}:</span> {v}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  {s.status !== "pending" && (
                    <button type="button" className="btn btn--sm" aria-expanded={open} onClick={() => setToggled((t) => ({ ...t, [s.stage]: !open }))}>
                      {open ? "Hide detail" : "Show detail"}
                    </button>
                  )}
                </div>
                {open && s.status !== "pending" && (
                  <div className="stage__detail"><StageDetail stage={s} /></div>
                )}
              </div>
            );
          })}
        </div>
        <p className="help" style={{ marginTop: 8 }}>
          <span className="mono">{STAGE_COUNT} stages · job {job.id}</span> · Stages 1 to 5 and 7 are hard gates: a FAIL there stops the run. Stages 6 and 8 report but never fail. SKIP means the stage did not have enough data yet.
        </p>
      </div>
    </>
  );
}
