// JSON-pointer patches from the mentor (docs/ARCHITECTURE.md §4b), applied on the web side only. The engine
// never applies anything; "Apply" here writes the result as the next strategy version. Pure; unit-tested.
import type { Strategy } from "@atm/schema";
import type { Section, SpecPatch } from "./types";

/** Roots a patch may never touch: identity, instruments and bookkeeping stay the user's. Same list as the engine. */
export const PROTECTED_ROOTS: readonly string[] = ["instruments", "market", "automation_permission", "strategy_id", "version", "parent_id", "name", "version_locked", "ambiguity_flags"];

const SECTION_FOR_ROOT: Record<string, Section> = {
  inputs: "inputs", entry_long: "entry", entry_short: "entry", timeframe: "timeframe", session: "timeframe",
  stop: "exits", targets: "exits", trailing: "exits", time_exit: "exits", trigger: "exits", risk: "risk", regime_affinity: "risk",
};

/** `/a~1b/0` → ["a/b", "0"]. Throws on anything that is not a JSON pointer. */
export function parsePointer(path: string): string[] {
  if (typeof path !== "string" || !path.startsWith("/")) throw new Error(`Not a JSON pointer: ${JSON.stringify(path)}`);
  return path.slice(1).split("/").map((s) => s.replace(/~1/g, "/").replace(/~0/g, "~"));
}

/** The Builder section a patch lands in, from the first segment of its path. Unknown roots open the entry section. */
export function sectionForPath(path: string): Section {
  const root = path.replace(/^\//, "").split("/")[0];
  return SECTION_FOR_ROOT[root] ?? "entry";
}

const isIndex = (s: string) => /^(0|[1-9]\d*)$/.test(s);
const container = (next: string): unknown[] | Record<string, unknown> => (isIndex(next) || next === "-" ? [] : {});

/** Sets `to` at `segments`, creating intermediate objects, or arrays when the next segment is an index or "-". */
function set(root: Record<string, unknown>, segments: string[], to: unknown): void {
  let cur: unknown = root;
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i], last = i === segments.length - 1, here = `/${segments.slice(0, i + 1).join("/")}`;
    if (Array.isArray(cur)) {
      const idx = seg === "-" ? cur.length : isIndex(seg) ? Number(seg) : NaN;
      if (!Number.isFinite(idx) || idx > cur.length) throw new Error(`No such array position: ${here} (the array has ${cur.length} items).`);
      if (last) { cur[idx] = to; return; }
      if (cur[idx] === undefined || cur[idx] === null) cur[idx] = container(segments[i + 1]);
      cur = cur[idx];
    } else if (cur !== null && typeof cur === "object") {
      const obj = cur as Record<string, unknown>;
      if (last) { obj[seg] = to; return; }
      if (obj[seg] === undefined || obj[seg] === null) obj[seg] = container(segments[i + 1]);
      cur = obj[seg];
    } else {
      throw new Error(`Cannot set ${here}: the parent is a ${cur === null ? "null" : typeof cur}, not an object.`);
    }
  }
}

/**
 * Applies every patch in order to a copy of `spec` and returns the copy. Throws, applying nothing, when a
 * path is not a JSON pointer, names a protected root, or points past the end of an array. `from` is ignored.
 */
export function applyPatch(spec: Strategy, patches: SpecPatch[]): Strategy {
  const out = structuredClone(spec) as unknown as Record<string, unknown>;
  for (const p of patches) {
    const segs = parsePointer(p.path);
    if (segs[0] === "") throw new Error("A patch must name a field; the whole spec cannot be replaced.");
    if (PROTECTED_ROOTS.includes(segs[0])) throw new Error(`Patches may not change /${segs[0]}; that stays yours.`);
    set(out, segs, p.to === undefined ? undefined : structuredClone(p.to));
  }
  return out as unknown as Strategy;
}
