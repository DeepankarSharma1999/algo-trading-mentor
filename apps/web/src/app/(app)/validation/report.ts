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
