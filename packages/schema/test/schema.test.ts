import { describe, expect, it } from "vitest";
import Ajv from "ajv";
import addFormats from "ajv-formats";
import schema from "../strategy.schema.json";
import cases from "../fixtures/testable.cases.json";
import { AUTOMATION_PERMISSIONS, bumpVersion, parseStrategyId } from "../src";

const ajv = addFormats(new Ajv({ allErrors: true, strict: false }));
const validate = ajv.compile(schema);

describe("strategy JSON schema", () => {
  it("accepts the fixture base strategy", () => {
    expect(validate(cases.base)).toBe(true);
  });
  it("rejects automation permissions outside the three allowed values", () => {
    expect(AUTOMATION_PERMISSIONS).toEqual(["paper_only", "mentor_only", "blocked"]);
    expect(validate({ ...cases.base, automation_permission: "auto" })).toBe(false);
    expect(validate({ ...cases.base, automation_permission: "confirm" })).toBe(false);
  });
  it("rejects unknown top-level keys (no broker fields can sneak in)", () => {
    expect(validate({ ...cases.base, broker_api_key: "x" })).toBe(false);
  });
  it("rejects a malformed strategy_id", () => {
    expect(validate({ ...cases.base, strategy_id: "Bad Id" })).toBe(false);
  });
});

describe("strategy id helpers", () => {
  it("parses and bumps", () => {
    expect(parseStrategyId("bb_squeeze_v3")).toEqual({ slug: "bb_squeeze", version: 3 });
    expect(bumpVersion("bb_squeeze_v3")).toBe("bb_squeeze_v4");
  });
});
