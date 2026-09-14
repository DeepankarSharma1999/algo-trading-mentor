import Link from "next/link";
import type { Finding } from "@/lib/types";
import { editAndRetest } from "../actions";
import { asSection, findingLabel, formatFindingNumber } from "../report";
import { Suggestions } from "./Suggestions";

/**
 * "What you can change": the engine's deterministic diagnosis of a failed run, one ledger row per finding,
 * each lever a button into the Builder section that drives it. Below it the two ways forward: "Edit and
 * re-test" (always the next version, so this report stays attached to the version it tested) and the
 * mentor's suggestions. Server-rendered from the stored report; renders nothing without findings.
 */
export function FixIt({ jobId, strategyId, findings }: { jobId: string; strategyId: string; findings: Finding[] }) {
  if (findings.length === 0) return null;
  return (
    <div className="section" data-testid="fix-it">
      <span className="label">What you can change</span>
      <p className="help" style={{ margin: "8px 0 0", maxWidth: "64ch" }}>
        Each finding is arithmetic on the run above, anchored in your own rules; no threshold of the pipeline is offered as a lever.
        A button opens the Builder section that drives the finding. Nothing changes until you save there.
      </p>
      <div className="ledger" style={{ marginTop: 6 }}>
        {findings.map((f, i) => {
          const numbers = Object.entries(f.numbers ?? {}).filter(([, v]) => typeof v === "number");
          const levers = Array.isArray(f.levers) ? f.levers : [];
          return (
            <div key={i} className="row row--wide" data-testid="finding" data-kind={f.kind}>
              <span className="label">{findingLabel(f)}</span>
              <div className="value">
                <div style={{ fontSize: "var(--fs-3)" }}>{f.title}</div>
                <div className="muted" style={{ marginTop: 4, maxWidth: "70ch" }}>{f.detail}</div>
                {numbers.length > 0 && (
                  <div className="cluster mono" style={{ gap: 14, marginTop: 6, fontSize: "var(--fs-1)" }}>
                    {numbers.map(([k, v]) => <span key={k}><span className="faint">{k}:</span> {formatFindingNumber(k, v)}</span>)}
                  </div>
                )}
                {levers.length > 0 && (
                  <div className="cluster" style={{ marginTop: 10 }}>
                    {levers.map((l, j) => (
                      <Link key={j} className="btn btn--sm" href={`/builder/${strategyId}?section=${asSection(l.section)}`} title={l.path ? `Spec path ${l.path}` : undefined}>
                        Open {l.label}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="cluster" style={{ marginTop: 16, alignItems: "flex-start" }}>
        <form action={editAndRetest.bind(null, jobId)} style={{ maxWidth: 360 }}>
          <button className="btn btn--primary">Edit and re-test</button>
          <p className="help help--tight" style={{ margin: "6px 0 0" }}>
            Copies the rules of <span className="mono">{strategyId}</span> into the next version and opens it in the Builder at the first lever.
            This report stays attached to the version it tested.
          </p>
        </form>
      </div>

      <div style={{ marginTop: 22 }}>
        <Suggestions jobId={jobId} />
      </div>
    </div>
  );
}
