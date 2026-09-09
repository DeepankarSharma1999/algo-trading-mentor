import { describe, expect, it } from "vitest";
import { checkTestable } from "../src/testable";
import cases from "../fixtures/testable.cases.json";

describe("shared testable validator (fixtures shared with engine)", () => {
  for (const c of cases.cases) {
    it(c.name, () => {
      const spec = { ...cases.base, ...c.patch };
      const r = checkTestable(spec);
      expect(r.testable).toBe(c.testable);
      expect(r.missing_ids).toEqual(c.missing_ids);
      expect(r.missing.length).toBe(c.missing_ids.length);
    });
  }
  it("substitutes ambiguity flags into the message", () => {
    const r = checkTestable({ ...cases.base, ambiguity_flags: ["stop reads two ways"] });
    expect(r.missing[0]).toContain("stop reads two ways");
  });
});
