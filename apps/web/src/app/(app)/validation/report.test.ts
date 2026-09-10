import { describe, expect, it } from "vitest";
import type { JobStatus } from "@/lib/types";
import { completeReport, runningReport } from "./report.fixture";
import { STAGE_NAMES, formatMetric, headline, isActive, keyMetrics, openByDefault, stagesOf, statusWord } from "./report";

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
  it("knows which jobs still need polling", () => {
    expect(isActive(queued)).toBe(true);
    expect(isActive(running)).toBe(true);
    expect(isActive(done)).toBe(false);
    expect(isActive(failed)).toBe(false);
  });
});
