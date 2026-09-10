import { describe, expect, it } from "vitest";
import type { Strategy } from "@atm/schema";
import { cloneSpec, deriveIdFromName, emptyDraft, newDraftId, nextFreeVersionId, parseTemplateRules, planSave, statusFor, uniqueSlug, validateBlockedReason, watchBlockedReason } from "./strategies.pure";

const complete: Strategy = {
  ...emptyDraft("fixture_v1", "Fixture"),
  instruments: ["RELIANCE"], regime_affinity: ["trend"],
  inputs: { ema20: { indicator: "ema", params: { length: 20 } } },
  entry_long: [{ lhs: "close", op: "crosses_above", rhs: "ema20" }],
  stop: { type: "atr", params: { length: 14, mult: 2 } },
  targets: [{ type: "rr", value: 2 }],
};

describe("uniqueSlug / deriveIdFromName", () => {
  it("slugifies and returns the root when free", () => {
    expect(uniqueSlug("NIFTY Squeeze (mine)", [])).toBe("nifty_squeeze_mine");
    expect(deriveIdFromName("EMA cross", [])).toBe("ema_cross_v1");
  });
  it("suffixes _2, _3 when the slug is taken", () => {
    expect(uniqueSlug("EMA cross", ["ema_cross"])).toBe("ema_cross_2");
    expect(uniqueSlug("EMA cross", ["ema_cross", "ema_cross_2"])).toBe("ema_cross_3");
    expect(deriveIdFromName("EMA cross", ["ema_cross"])).toBe("ema_cross_2_v1");
  });
  it("keeps suffixed slugs within 40 characters", () => {
    const long = "a".repeat(60);
    const s = uniqueSlug(long, ["a".repeat(40)]);
    expect(s.length).toBeLessThanOrEqual(40);
    expect(s.endsWith("_2")).toBe(true);
  });
});

describe("statusFor", () => {
  it("is testable for a complete spec and draft otherwise", () => {
    expect(statusFor(complete)).toBe("testable");
    expect(statusFor({ ...complete, stop: null })).toBe("draft");
    expect(statusFor(emptyDraft("new_strategy_v1"))).toBe("draft");
  });
});

describe("version ids", () => {
  it("bumps to the next free version", () => {
    expect(nextFreeVersionId("nifty_squeeze_v1", ["nifty_squeeze_v1"])).toBe("nifty_squeeze_v2");
    expect(nextFreeVersionId("nifty_squeeze_v1", ["nifty_squeeze_v1", "nifty_squeeze_v2"])).toBe("nifty_squeeze_v3");
  });
  it("numbers new drafts above the highest existing new_strategy version", () => {
    expect(newDraftId([])).toBe("new_strategy_v1");
    expect(newDraftId(["new_strategy_v1", "other_v4", "new_strategy_v3"])).toBe("new_strategy_v4");
  });
});

describe("planSave", () => {
  const row = { id: "nifty_squeeze_v1", status: "validated", version: 1, parentId: "tmpl_v1", spec: { ...complete, version_locked: true } };
  it("creates an untested new version when the current row is validated", () => {
    const p = planSave(row, { ...complete, name: "Changed" }, ["nifty_squeeze_v1"]);
    expect(p.mode).toBe("bump");
    if (p.mode !== "bump") return;
    expect(p.id).toBe("nifty_squeeze_v2");
    expect(p.previousId).toBe("nifty_squeeze_v1");
    expect(p.status).toBe("untested");
    expect(p.spec.strategy_id).toBe("nifty_squeeze_v2");
    expect(p.spec.version).toBe(2);
    expect(p.spec.parent_id).toBe("nifty_squeeze_v1");
    expect(p.spec.version_locked).toBe(false);
  });
  it("also bumps when only version_locked is set", () => {
    const p = planSave({ ...row, status: "testable" }, complete, ["nifty_squeeze_v1"]);
    expect(p.mode).toBe("bump");
  });
  it("updates in place and recomputes status for drafts and testable rows", () => {
    const draft = { id: "ema_cross_v1", status: "draft", version: 1, parentId: null, spec: emptyDraft("ema_cross_v1") };
    const p = planSave(draft, { ...complete, strategy_id: "wrong_v9", version: 9 }, ["ema_cross_v1"]);
    expect(p.mode).toBe("update");
    expect(p.status).toBe("testable");
    expect(p.spec.strategy_id).toBe("ema_cross_v1");
    expect(p.spec.version).toBe(1);
    const p2 = planSave(draft, { ...complete, entry_long: [], entry_short: null }, []);
    expect(p2.status).toBe("draft");
  });
  it("updates an untested (already bumped) row in place", () => {
    const p = planSave({ id: "nifty_squeeze_v2", status: "untested", version: 2, parentId: "nifty_squeeze_v1", spec: complete }, complete, []);
    expect(p.mode).toBe("update");
  });
});

describe("cloneSpec / parseTemplateRules", () => {
  it("copies instruments and sets lineage", () => {
    const c = cloneSpec({ ...complete, version_locked: true }, "ema_cross_v1", "EMA cross", "tmpl_ema_v1");
    expect(c.parent_id).toBe("tmpl_ema_v1");
    expect(c.instruments).toEqual(["RELIANCE"]);
    expect(c.instruments).not.toBe(complete.instruments);
    expect(c.version_locked).toBe(false);
    expect(c.version).toBe(1);
  });
  it("parses JSON, plain text and garbage", () => {
    expect(parseTemplateRules(JSON.stringify({ rules: "r", ambiguity_notes: ["a"], regime: "trend" }))).toEqual({ rules: "r", ambiguity_notes: ["a"], regime: "trend" });
    expect(parseTemplateRules("plain words", "range")).toEqual({ rules: "plain words", ambiguity_notes: [], regime: "range" });
    expect(parseTemplateRules("", "range").regime).toBe("range");
  });
});

describe("blocked reasons", () => {
  it("explains why validate or watch is unavailable", () => {
    expect(validateBlockedReason("draft")).toMatch(/Not testable/);
    expect(validateBlockedReason("testable")).toBeNull();
    expect(watchBlockedReason("testable", "paper_only")).toMatch(/Validate/);
    expect(watchBlockedReason("validated", "mentor_only")).toMatch(/mentor_only/);
    expect(watchBlockedReason("validated", "paper_only")).toBeNull();
  });
});
