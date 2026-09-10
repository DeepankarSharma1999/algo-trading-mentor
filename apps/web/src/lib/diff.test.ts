import { describe, expect, it } from "vitest";
import { diff, flatten, show } from "./diff";

describe("flatten", () => {
  it("flattens nested objects and arrays to dotted paths", () => {
    expect(flatten({ a: { b: [1, 2], c: "x" }, d: null })).toEqual({ "a.b[0]": 1, "a.b[1]": 2, "a.c": "x", d: null });
  });
  it("keeps markers for empty containers", () => {
    expect(flatten({ a: [], b: {} })).toEqual({ a: "[]", b: "{}" });
  });
  it("flattens a bare primitive to the empty path", () => {
    expect(flatten(3)).toEqual({ "": 3 });
  });
});

describe("diff", () => {
  it("reports nothing for identical documents", () => {
    const spec = { inputs: { rsi14: { period: 14 } }, targets: [{ value: 2 }] };
    expect(diff(spec, structuredClone(spec))).toEqual([]);
  });

  it("reports changes, additions and deletions with old and new values", () => {
    const a = { inputs: { rsi14: { period: 14 } }, stop: { atr_mult: 1.5 }, targets: [{ value: 2 }, { value: 3 }] };
    const b = { inputs: { rsi14: { period: 21 } }, stop: { atr_mult: 1.5, kind: "atr" }, targets: [{ value: 2 }] };
    expect(diff(a, b)).toEqual([
      { path: "inputs.rsi14.period", kind: "change", from: "14", to: "21" },
      { path: "targets[1].value", kind: "del", from: "3" },
      { path: "stop.kind", kind: "add", to: "atr" },
    ]);
  });

  it("distinguishes null from a missing key and 0 from false", () => {
    expect(diff({ a: null }, {})).toEqual([{ path: "a", kind: "del", from: "null" }]);
    expect(diff({ a: 0 }, { a: false })).toEqual([{ path: "a", kind: "change", from: "0", to: "false" }]);
  });

  it("orders lines by first appearance: source paths first, then added paths", () => {
    const lines = diff({ z: 1, y: 2 }, { y: 3, x: 4, z: 1 });
    expect(lines.map((l) => l.path)).toEqual(["y", "x"]);
  });

  it("shows strings bare and nullish values as words", () => {
    expect(show("trend")).toBe("trend");
    expect(show(undefined)).toBe("undefined");
    expect(show(1.25)).toBe("1.25");
  });
});
