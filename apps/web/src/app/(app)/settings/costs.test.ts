import { describe, expect, it } from "vitest";
import { COST_KEYS, readOverrides } from "./costs";

describe("cost overrides", () => {
  it("keeps only the documented keys with finite numbers", () => {
    expect(readOverrides({ brokerage_per_order: 15, slippage_bps: "4", slippage_stress: NaN, other: 1 })).toEqual({ brokerage_per_order: 15 });
    expect(readOverrides(null)).toEqual({});
    expect(readOverrides("{}")).toEqual({});
  });
  it("documents exactly the three keys the engine reads", () => {
    expect([...COST_KEYS]).toEqual(["brokerage_per_order", "slippage_bps", "slippage_stress"]);
  });
});
