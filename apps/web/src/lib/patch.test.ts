import { describe, expect, it } from "vitest";
import { emptyDraft } from "./strategies.pure";
import { PROTECTED_ROOTS, applyPatch, parsePointer, sectionForPath } from "./patch";

const spec = () => ({
  ...emptyDraft("fixture_v1", "Fixture"),
  instruments: ["RELIANCE"], regime_affinity: ["trend" as const],
  inputs: { ema20: { indicator: "ema" as const, params: { length: 20 } }, rsi14: { indicator: "rsi" as const, params: { length: 14 } } },
  entry_long: [{ lhs: "close", op: ">" as const, rhs: "ema20" }, { lhs: "rsi14", op: "<" as const, rhs: 35 }],
  stop: { type: "atr" as const, params: { length: 14, mult: 2 } },
  targets: [{ type: "rr" as const, value: 2 }],
});

describe("parsePointer", () => {
  it("splits and unescapes", () => {
    expect(parsePointer("/risk/min_rr_after_costs")).toEqual(["risk", "min_rr_after_costs"]);
    expect(parsePointer("/inputs/a~1b/x~0y")).toEqual(["inputs", "a/b", "x~y"]);
    expect(parsePointer("/")).toEqual([""]);
  });
  it("rejects non-pointers", () => {
    expect(() => parsePointer("risk/x")).toThrow(/JSON pointer/);
    expect(() => parsePointer("")).toThrow();
  });
});

describe("applyPatch", () => {
  it("sets a nested value and leaves the input untouched", () => {
    const s = spec();
    const out = applyPatch(s, [{ path: "/risk/min_rr_after_costs", from: 1.5, to: 1.2 }]);
    expect(out.risk.min_rr_after_costs).toBe(1.2);
    expect(s.risk.min_rr_after_costs).toBe(1.5);
    expect(out).not.toBe(s);
  });
  it("applies patches in order and supports array indices", () => {
    const out = applyPatch(spec(), [
      { path: "/entry_long/1/rhs", from: 35, to: 40 },
      { path: "/entry_long/1/rhs", from: 40, to: 45 },
      { path: "/targets/0/value", to: 3 },
    ]);
    expect(out.entry_long[1].rhs).toBe(45);
    expect(out.targets[0].value).toBe(3);
  });
  it("appends with /- and at index == length", () => {
    const out = applyPatch(spec(), [
      { path: "/regime_affinity/-", to: "compression" },
      { path: "/targets/1", to: { type: "rr", value: 4 } },
    ]);
    expect(out.regime_affinity).toEqual(["trend", "compression"]);
    expect(out.targets).toHaveLength(2);
  });
  it("creates intermediate objects and arrays", () => {
    const out = applyPatch({ ...spec(), stop: null, entry_short: null, time_exit: {} }, [
      { path: "/stop/type", to: "atr" },
      { path: "/stop/params/mult", to: 1.5 },
      { path: "/entry_short/0/lhs", to: "close" },
      { path: "/time_exit/max_bars", to: 12 },
      { path: "/inputs/atr14", to: { indicator: "atr", params: { length: 14 } } },
    ]);
    expect(out.stop).toEqual({ type: "atr", params: { mult: 1.5 } });
    expect(out.entry_short).toEqual([{ lhs: "close" }]);
    expect(out.time_exit.max_bars).toBe(12);
    expect(out.inputs.atr14.indicator).toBe("atr");
  });
  it("replaces a whole subtree", () => {
    const out = applyPatch(spec(), [{ path: "/entry_long", to: [{ lhs: "close", op: ">", rhs: "ema20" }] }]);
    expect(out.entry_long).toHaveLength(1);
    expect(applyPatch(spec(), [{ path: "/timeframe", to: "1h" }]).timeframe).toBe("1h");
  });
  it("rejects every protected root and the empty path", () => {
    for (const root of PROTECTED_ROOTS) expect(() => applyPatch(spec(), [{ path: `/${root}`, to: "x" }])).toThrow(new RegExp(root));
    expect(() => applyPatch(spec(), [{ path: "/instruments/0", to: "INFY" }])).toThrow(/instruments/);
    expect(() => applyPatch(spec(), [{ path: "/name", to: "Renamed" }])).toThrow(/name/);
    expect(() => applyPatch(spec(), [{ path: "/", to: {} }])).toThrow(/whole spec/);
    expect(() => applyPatch(spec(), [{ path: "risk", to: {} }])).toThrow(/JSON pointer/);
  });
  it("rejects an index past the end of an array and descending into a primitive", () => {
    expect(() => applyPatch(spec(), [{ path: "/targets/5/value", to: 1 }])).toThrow(/array position/);
    expect(() => applyPatch(spec(), [{ path: "/targets/x", to: 1 }])).toThrow(/array position/);
    expect(() => applyPatch(spec(), [{ path: "/timeframe/x", to: 1 }])).toThrow(/not an object/);
  });
  it("applies nothing when a later patch is rejected", () => {
    const s = spec();
    expect(() => applyPatch(s, [{ path: "/timeframe", to: "1h" }, { path: "/name", to: "x" }])).toThrow();
    expect(s.timeframe).toBe("15m");
  });
});

describe("sectionForPath", () => {
  it("maps every allowed root to its Builder section", () => {
    expect(sectionForPath("/inputs/ema20/params/length")).toBe("inputs");
    expect(sectionForPath("/entry_long/1/rhs")).toBe("entry");
    expect(sectionForPath("/entry_short")).toBe("entry");
    expect(sectionForPath("/timeframe")).toBe("timeframe");
    expect(sectionForPath("/session/end")).toBe("timeframe");
    for (const root of ["stop", "targets", "trailing", "time_exit", "trigger"]) expect(sectionForPath(`/${root}/x`)).toBe("exits");
    expect(sectionForPath("/risk/max_trades_per_day")).toBe("risk");
    expect(sectionForPath("/regime_affinity/-")).toBe("risk");
    expect(sectionForPath("/nonsense")).toBe("entry");
  });
});
