// Pure helpers that turn a validation job row into what the checklist renders. Unit-tested with a
// queued job (report null) and a complete report, so the page is known to render both.
import type { JobStatus, StageResult, ValidationReport } from "@/lib/types";

/** Mirrors engine/validation/pipeline.py STAGE_NAMES. Order matters here; stages are numbered on screen. */
export const STAGE_NAMES: Record<number, string> = {
  1: "In-sample coherence",
  2: "Out-of-sample",
  3: "Walk-forward",
  4: "Cost stress",
  5: "Parameter sensitivity",
  6: "Regime breakdown",
  7: "Monte Carlo",
  8: "Paper agreement",
};
export const STAGE_COUNT = 8;

/** One sentence per stage saying what it checks; printed under the stage name so the list explains itself. */
export const STAGE_CHECKS: Record<number, string> = {
  1: "Checks that the rules produce enough trades and place every stop on the right side of the entry.",
  2: "Runs the rules on the last 30% of the data, which was never seen while building.",
  3: "Rolling train/test windows: fit on one stretch, test on the next, repeat.",
  4: "Reruns with costs at 1.5x and 2x to see whether the edge survives worse fills.",
  5: "The neighbours of every numeric parameter must also work; a single lucky value fails.",
  6: "Expectancy per market regime, so you know where the rules earn and where they lose.",
  7: "1000 shuffles of the trade order to size the drawdown you should expect, not the one you got.",
  8: "Paper trades against the backtest once 30 closed paper trades exist; skipped until then.",
};

export type StageStatus = StageResult["status"];

export const isActive = (job: Pick<JobStatus, "status">) => job.status === "queued" || job.status === "running";

/** Always eight stages in order; missing ones (report null, or a run that stopped early) are pending. */
export function stagesOf(report: ValidationReport | null | undefined): StageResult[] {
  const byNum = new Map<number, StageResult>();
  for (const s of report?.stages ?? []) byNum.set(s.stage, s);
  return Array.from({ length: STAGE_COUNT }, (_, i) => {
    const n = i + 1;
    return byNum.get(n) ?? { stage: n, name: STAGE_NAMES[n], status: "pending", summary: "", metrics: {}, detail: null };
  });
}

/** The status word shown in `.status`, and the class that tints it. */
export function statusWord(s: StageStatus): { word: string; cls: string } {
  switch (s) {
    case "pass": return { word: "PASS", cls: "status status--eligible" };
    case "fail": return { word: "FAIL", cls: "status status--blocked" };
    case "skip": return { word: "SKIP", cls: "status muted" };
    default: return { word: "PENDING", cls: "status faint" };
  }
}

/**
 * The line under the page head. Serif (`h-display`) for the weakest-stage sentence once the run
 * has finished; mono while it is still running, so the only serif line is the verdict.
 */
export function headline(job: JobStatus): { text: string; mono: boolean } {
  if (job.status === "queued") return { text: "Queued. Waiting for the engine to pick this job up.", mono: true };
  if (job.status === "running") return { text: `Running stage ${Math.max(1, Math.min(STAGE_COUNT, job.current_stage || 1))} of ${STAGE_COUNT}.`, mono: true };
  if (job.status === "failed") return { text: job.error ? `The run stopped: ${job.error}` : "The run stopped before a verdict.", mono: true };
  const sentence = job.report?.weakest_sentence?.trim();
  if (sentence) return { text: sentence, mono: false };
  return { text: job.report?.passed ? "Every stage passed." : "The run finished without a verdict sentence.", mono: false };
}

/** The glyph next to a status word, so state is carried by shape as well as colour. */
export function gateClass(s: StageStatus, running = false): string {
  if (running) return "gate gate--pending";
  switch (s) {
    case "pass": return "gate gate--pass";
    case "fail": return "gate gate--fail";
    case "skip": return "gate";
    default: return "gate gate--pending";
  }
}

/** The job's state in plain words for the index ledger: "Queued", "Running stage 3 of 8", "Failed at stage 2", "Passed". */
export function plainStatus(job: Pick<JobStatus, "status" | "current_stage" | "report" | "error">): { text: string; cls: string } {
  const stage = Math.max(1, Math.min(STAGE_COUNT, job.current_stage || 1));
  if (job.status === "queued") return { text: "Queued", cls: "muted" };
  if (job.status === "running") return { text: `Running stage ${stage} of ${STAGE_COUNT}`, cls: "" };
  if (job.status === "failed") return { text: `Stopped at stage ${stage}${job.error ? ": " + job.error : ""}`, cls: "status--blocked" };
  if (job.report?.passed) return { text: "Passed", cls: "status--eligible" };
  const failed = job.report?.stages?.find((s) => s.status === "fail")?.stage ?? job.report?.weakest_stage ?? stage;
  return { text: `Failed at stage ${failed}`, cls: "status--blocked" };
}

/** Stages whose detail panel opens by default: the weakest one and the one running now. */
export function openByDefault(job: JobStatus): Set<number> {
  const open = new Set<number>();
  if (job.status === "running" && job.current_stage >= 1) open.add(job.current_stage);
  const w = job.report?.weakest_stage;
  if (w && w >= 1 && w <= STAGE_COUNT) open.add(w);
  return open;
}

/** Small mono `label: value` pairs under each stage. `margin` is internal to the engine and hidden. */
export function keyMetrics(s: StageResult, max = 5): [string, string][] {
  return Object.entries(s.metrics ?? {})
    .filter(([k]) => k !== "margin")
    .slice(0, max)
    .map(([k, v]) => [k, formatMetric(k, v)]);
}

export function formatMetric(key: string, v: number): string {
  if (!Number.isFinite(v)) return "–";
  if (/(^|_)(trades|windows|params|neighbours|bars|errors|min_trades|paper_trades|watch)$/.test(key) || /^(nan_after_warmup|proportional|agreement)$/.test(key)) return String(Math.round(v));
  if (/_r$/.test(key) || /expectancy/.test(key)) return `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}R`;
  if (/(share|rate|fraction)$/.test(key)) return `${(v * 100).toFixed(0)}%`;
  if (/(pct|dd_p\d+)$/.test(key)) return `${v.toFixed(1)}%`;
  return v.toFixed(2);
}
