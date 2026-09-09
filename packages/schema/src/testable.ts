// The shared testable-validator. The rules live in ../testable.rules.json; this is a ~25-line interpreter.
// engine/schema/testable.py is the Python twin. Both run fixtures/testable.cases.json.
import rules from "../testable.rules.json";

type PathSpec = { path: string; not?: unknown };
type Rule = { id: string; kind: "present_any" | "empty"; paths: PathSpec[]; missing: string };

export interface TestableResult { testable: boolean; missing: string[]; missing_ids: string[] }

function resolve(doc: unknown, pointer: string): unknown {
  let cur: unknown = doc;
  for (const seg of pointer.split("/").slice(1)) {
    if (cur === null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[seg];
  }
  return cur;
}

function present(v: unknown, not?: unknown): boolean {
  if (v === null || v === undefined || v === "") return false;
  if (Array.isArray(v) && v.length === 0) return false;
  if (not !== undefined && v === not) return false;
  return true;
}

export function checkTestable(spec: unknown): TestableResult {
  const missing: string[] = [];
  const missing_ids: string[] = [];
  for (const rule of (rules as { rules: Rule[] }).rules) {
    const values = rule.paths.map((p) => resolve(spec, p.path));
    const ok = rule.kind === "present_any"
      ? rule.paths.some((p, i) => present(values[i], p.not))
      : !present(values[0]);
    if (!ok) {
      const vals = Array.isArray(values[0]) ? (values[0] as unknown[]).join("; ") : String(values[0] ?? "");
      missing.push(rule.missing.replace("{values}", vals));
      missing_ids.push(rule.id);
    }
  }
  return { testable: missing.length === 0, missing, missing_ids };
}
