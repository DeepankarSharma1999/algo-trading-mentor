import { describe, expect, it } from "vitest";
import type { JobStatus } from "@/lib/types";
import { sectionForPath } from "@/lib/patch";
import { completeReport, failedReport, passedReport, runningReport, templateSuggestions } from "./report.fixture";
import { STAGE_CHECKS, STAGE_COUNT, STAGE_NAMES, asSection, costBreakdown, findingLabel, findingsOf, firstLeverSection, formatFindingNumber, formatMetric, gateClass, headline, isActive, keyMetrics, openByDefault, plainStatus, stagesOf, statusWord } from "./report";

const queued: JobStatus = { id: "j1", status: "queued", current_stage: 0, report: null, error: null };
const running: JobStatus = { id: "j2", status: "running", current_stage: 2, report: runningReport, error: null };
const done: JobStatus = { id: "j3", status: "done", current_stage: 8, report: completeReport, error: null };
const failed: JobStatus = { id: "j4", status: "failed", current_stage: 3, report: runningReport, error: "engine restarted" };

describe("stagesOf", () => {
  it("returns eight pending stages for a queued job with no report", () => {
    const s = stagesOf(null);
    expect(s).toHaveLength(8);
    expect(s.map((x) => x.stage)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(s.every((x) => x.status === "pending")).toBe(true);
    expect(s[0].name).toBe(STAGE_NAMES[1]);
    expect(s[7].name).toBe("Paper agreement");
  });
  it("keeps the engine's stages in order and fills nothing in for a complete report", () => {
    const s = stagesOf(completeReport);
    expect(s.map((x) => x.status)).toEqual(["pass", "pass", "pass", "pass", "pass", "pass", "pass", "skip"]);
  });
  it("marks unrun stages pending while running", () => {
    const s = stagesOf(runningReport);
    expect(s[0].status).toBe("pass");
    expect(s.slice(1).every((x) => x.status === "pending")).toBe(true);
  });
});

describe("headline", () => {
  it("is mono while queued or running, serif once done", () => {
    expect(headline(queued)).toEqual({ text: "Queued. Waiting for the engine to pick this job up.", mono: true });
    expect(headline(running)).toEqual({ text: "Running stage 2 of 8.", mono: true });
    const h = headline(done);
    expect(h.mono).toBe(false);
    expect(h.text).toBe(completeReport.weakest_sentence);
  });
  it("names the error when the run failed", () => {
    expect(headline(failed).text).toContain("engine restarted");
    expect(headline(failed).mono).toBe(true);
  });
  it("falls back to a plain sentence when the report has no verdict text", () => {
    expect(headline({ ...done, report: { ...completeReport, weakest_sentence: "" } }).text).toBe("Every stage passed.");
  });
});

describe("openByDefault", () => {
  it("opens the running stage and the weakest stage", () => {
    expect([...openByDefault(queued)]).toEqual([]);
    expect([...openByDefault(running)]).toEqual([2]);
    expect([...openByDefault(done)]).toEqual([2]);
  });
});

describe("metrics", () => {
  it("hides the internal margin and formats R, counts and shares", () => {
    const m = keyMetrics(stagesOf(completeReport)[1]);
    expect(m.map(([k]) => k)).not.toContain("margin");
    expect(Object.fromEntries(m)).toMatchObject({ in_sample_expectancy_r: "+0.24R", oos_expectancy_r: "+0.12R", oos_trades: "38", oos_fraction: "30%" });
    expect(formatMetric("expectancy_high_vol", -0.12)).toBe("−0.12R");
    expect(formatMetric("dd_p95", 11.2)).toBe("11.2%");
    expect(formatMetric("warmup_bars", 34)).toBe("34");
    expect(formatMetric("anything", NaN)).toBe("–");
  });
  it("maps statuses to status words", () => {
    expect(statusWord("pass")).toEqual({ word: "PASS", cls: "status status--eligible" });
    expect(statusWord("fail").cls).toContain("status--blocked");
    expect(statusWord("skip").word).toBe("SKIP");
    expect(statusWord("pending").cls).toContain("faint");
  });
  it("has one plain sentence for every stage", () => {
    for (let n = 1; n <= STAGE_COUNT; n++) expect(STAGE_CHECKS[n]).toMatch(/\.$/);
  });
  it("pairs every status with a square gate glyph", () => {
    expect(gateClass("pass")).toBe("gate gate--pass");
    expect(gateClass("fail")).toBe("gate gate--fail");
    expect(gateClass("pending")).toBe("gate gate--pending");
    expect(gateClass("pass", true)).toBe("gate gate--pending");
  });
  it("says the job state in plain words", () => {
    expect(plainStatus(queued).text).toBe("Queued");
    expect(plainStatus(running).text).toBe("Running stage 2 of 8");
    expect(plainStatus(done).text).toBe("Passed");
    expect(plainStatus(failed).text).toContain("Stopped at stage 3");
    const notPassed: JobStatus = { ...done, report: { ...completeReport, passed: false, stages: completeReport.stages.map((s) => (s.stage === 2 ? { ...s, status: "fail" } : s)) } };
    expect(plainStatus(notPassed).text).toBe("Failed at stage 2");
  });
  it("knows which jobs still need polling", () => {
    expect(isActive(queued)).toBe(true);
    expect(isActive(running)).toBe(true);
    expect(isActive(done)).toBe(false);
    expect(isActive(failed)).toBe(false);
  });
});

describe("fix-it flow (§4b)", () => {
  const failedJob: JobStatus = { id: "j5", status: "done", current_stage: 2, report: failedReport, error: null };
  it("shows findings only on a finished run that did not pass", () => {
    expect(findingsOf(failedJob)).toHaveLength(3);
    expect(findingsOf(done)).toEqual([]);
    expect(findingsOf({ status: "done", report: passedReport })).toEqual([]);
    expect(findingsOf({ status: "running", report: { ...failedReport } })).toEqual([]);
    expect(findingsOf({ status: "done", report: { ...failedReport, diagnosis: undefined } })).toEqual([]);
    expect(findingsOf(queued)).toEqual([]);
  });
  it("labels a finding by stage and kind in words", () => {
    expect(findingLabel({ stage: 1, kind: "bottleneck_condition" })).toBe("Stage 1 · bottleneck condition");
    expect(findingLabel({ stage: 2, kind: "costs" })).toBe("Stage 2 · costs");
    expect(findingLabel({ stage: 1, kind: "rr_filter" })).toBe("Stage 1 · R:R filter");
  });
  it("opens the Builder at the first lever, and at entry when there is none", () => {
    expect(firstLeverSection(findingsOf(failedJob))).toBe("entry");
    expect(firstLeverSection([{ ...failedReport.diagnosis![2] }])).toBe("timeframe");
    expect(firstLeverSection([])).toBe("entry");
    expect(asSection("risk")).toBe("risk");
    expect(asSection("nonsense")).toBe("entry");
  });
  it("formats finding numbers as rupees, counts or metrics", () => {
    expect(formatFindingNumber("one_r", 2000)).toMatch(/2,000/);
    expect(formatFindingNumber("skipped_for_size", 23)).toBe("23");
    expect(formatFindingNumber("lot_size", 1)).toBe("1");
    expect(formatFindingNumber("true_pct", 6.1)).toBe("6.1%");
    expect(formatFindingNumber("gross_expectancy_r", 0.06)).toBe("+0.06R");
    expect(formatFindingNumber("cost_per_trade_r", 0.13)).toBe("0.13R");
    expect(formatFindingNumber("min_trades", 60)).toBe("60");
    expect(formatFindingNumber("x", NaN)).toBe("–");
  });
  it("splits expectancy into gross, cost and net and names when costs exceed the edge", () => {
    const oos = (failedReport.stages[1].detail as { oos: import("@/lib/types").Stats }).oos;
    expect(costBreakdown(oos)).toEqual({ gross: 0.06, cost: 0.13, net: -0.07, exceeds: true });
    const base = (completeReport.stages[0].detail as { stats: import("@/lib/types").Stats }).stats;
    expect(costBreakdown(base)).toMatchObject({ gross: 0.33, cost: 0.12, net: 0.21, exceeds: false });
    expect(costBreakdown({ trades: 3, expectancy_r: 0.1 })).toBeNull();
    expect(costBreakdown(null)).toBeNull();
    expect(costBreakdown({ expectancy_r: 0.1, gross_expectancy_r: 0.3 })?.cost).toBeCloseTo(0.2);
  });
  it("keeps the fixtures coherent: a passed report has no findings, the failed one names allowed roots only", () => {
    expect(passedReport.passed).toBe(true);
    expect(passedReport.diagnosis).toEqual([]);
    expect(failedReport.passed).toBe(false);
    expect(plainStatus(failedJob).text).toBe("Failed at stage 2");
    expect(stagesOf(failedReport).map((s) => s.status)).toEqual(["pass", "fail", "pending", "pending", "pending", "pending", "pending", "pending"]);
    for (const s of templateSuggestions.suggestions) for (const p of s.patch) expect(["inputs", "entry", "timeframe", "exits", "risk"]).toContain(sectionForPath(p.path));
    expect(sectionForPath(templateSuggestions.suggestions[1].patch[0].path)).toBe("timeframe");
  });
});
