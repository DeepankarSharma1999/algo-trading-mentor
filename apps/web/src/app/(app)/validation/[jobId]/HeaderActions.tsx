"use client";
import { useActionState } from "react";
import { mentorReview, rerunValidation, type ActionState, type ReviewState } from "../actions";

/**
 * The two controls in the page head. "Re-run validation" queues a fresh job for the same strategy and
 * opens it; "Ask the mentor to review" prints prose and a next step under the head. Both fail soft
 * with a plain sentence when the engine is down; the report on the page is untouched either way.
 */
export function HeaderActions({ jobId, strategyId, hasReport }: { jobId: string; strategyId: string; hasReport: boolean }) {
  const [rerun, rerunAction, rerunPending] = useActionState<ActionState, FormData>(rerunValidation, {});
  const [review, reviewAction, reviewPending] = useActionState<ReviewState, FormData>(mentorReview, {});
  return (
    <div className="stack" style={{ textAlign: "right" }}>
      <div className="cluster" style={{ justifyContent: "flex-end", alignItems: "flex-start" }}>
        <form action={rerunAction} style={{ maxWidth: 220 }}>
          <input type="hidden" name="strategy_id" value={strategyId} />
          <button className="btn btn--sm" disabled={rerunPending} aria-describedby="rerun-help">
            {rerunPending ? "Queueing…" : "Re-run validation"}
          </button>
          <p id="rerun-help" className="help help--tight" style={{ margin: "4px 0 0" }}>Queues a fresh run of all eight stages for this version and opens it. This report stays in the list.</p>
        </form>
        <form action={reviewAction} style={{ maxWidth: 220 }}>
          <input type="hidden" name="job_id" value={jobId} />
          <button className="btn btn--sm" disabled={reviewPending || !hasReport} aria-describedby="review-help">
            {reviewPending ? "Asking…" : "Ask the mentor to review"}
          </button>
          <p id="review-help" className="help help--tight" style={{ margin: "4px 0 0" }}>{hasReport ? "The mentor reads this report and names the weakest stage and one next step inside your rules. It never names an instrument." : "Available once the run has produced at least one stage."}</p>
        </form>
      </div>
      {rerun.error && <p className="notice notice--watch" role="status" style={{ textAlign: "left", margin: 0 }}>{rerun.error}</p>}
      {review.error && <p className="notice notice--watch" role="status" style={{ textAlign: "left", margin: 0 }} data-testid="review-error">{review.error}</p>}
      {review.prose && (
        <div className="notice" style={{ textAlign: "left", margin: 0, maxWidth: 520 }} data-testid="review-prose">
          <p style={{ margin: 0 }}>{review.prose}</p>
          {review.next_step && <p style={{ margin: "8px 0 0" }}><span className="label">Next step</span> {review.next_step}</p>}
          {typeof review.weakest_stage === "number" && <p className="mono faint" style={{ margin: "6px 0 0", fontSize: "var(--fs-1)" }}>weakest stage: {review.weakest_stage}</p>}
        </div>
      )}
    </div>
  );
}
