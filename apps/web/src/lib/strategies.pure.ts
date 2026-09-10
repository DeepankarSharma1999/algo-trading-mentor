// Pure strategy helpers: no Prisma, no network. Everything here is unit-tested in strategies.test.ts;
// strategies.ts wraps these with database reads and writes.
import { bumpVersion, checkTestable, parseStrategyId, slugify, type Strategy, type StrategyStatus } from "@atm/schema";

export type SaveStatus = Extract<StrategyStatus, "draft" | "testable">;

/** Template metadata stored in strategies.plain_rules as JSON. Tolerates plain text and missing fields. */
export interface TemplateRules { rules: string; ambiguity_notes: string[]; regime: string }

export function parseTemplateRules(raw: string | null | undefined, fallbackRegime = ""): TemplateRules {
  if (!raw) return { rules: "", ambiguity_notes: [], regime: fallbackRegime };
  try {
    const j = JSON.parse(raw) as Partial<TemplateRules> | string;
    if (typeof j === "string") return { rules: j, ambiguity_notes: [], regime: fallbackRegime };
    return {
      rules: typeof j.rules === "string" ? j.rules : "",
      ambiguity_notes: Array.isArray(j.ambiguity_notes) ? j.ambiguity_notes.map(String) : [],
      regime: typeof j.regime === "string" && j.regime ? j.regime : fallbackRegime,
    };
  } catch {
    return { rules: raw, ambiguity_notes: [], regime: fallbackRegime };
  }
}

/** draft | testable, straight from the shared validator. */
export function statusFor(spec: unknown): SaveStatus {
  return checkTestable(spec).testable ? "testable" : "draft";
}

/** First free slug among `taken`: name, name_2, name_3 ... */
export function uniqueSlug(base: string, taken: Iterable<string>): string {
  const set = new Set(taken);
  const root = slugify(base);
  if (!set.has(root)) return root;
  for (let n = 2; ; n++) {
    const candidate = `${root.slice(0, 40 - `_${n}`.length)}_${n}`;
    if (!set.has(candidate)) return candidate;
  }
}

/** `slug_v1` for a new strategy, with the slug made unique against the user's existing slugs. */
export function deriveIdFromName(name: string, takenSlugs: Iterable<string>): string {
  return `${uniqueSlug(name, takenSlugs)}_v1`;
}

/** `bumpVersion(id)` unless that id is already taken, in which case the next free version of the same slug. */
export function nextFreeVersionId(id: string, takenIds: Iterable<string>): string {
  const set = new Set(takenIds);
  let next = bumpVersion(id);
  while (set.has(next)) next = bumpVersion(next);
  return next;
}

/** `new_strategy_vN` where N is one above the highest existing version of that slug. */
export function newDraftId(takenIds: Iterable<string>): string {
  let max = 0;
  for (const id of takenIds) {
    try { const { slug, version } = parseStrategyId(id); if (slug === "new_strategy") max = Math.max(max, version); } catch { /* not a strategy id */ }
  }
  return `new_strategy_v${max + 1}`;
}

export interface StrategyRowLike { id: string; status: string; version: number; parentId: string | null; spec: unknown }

export type SavePlan =
  | { mode: "update"; id: string; status: SaveStatus; spec: Strategy }
  | { mode: "bump"; id: string; previousId: string; version: number; status: "untested"; spec: Strategy };

/**
 * Decide what saving `spec` over `current` does. A validated (or version-locked) row is never edited in
 * place: the save becomes a new row, one version up, parented to the old one, status "untested".
 * Otherwise the row is updated and its status recomputed.
 */
export function planSave(current: StrategyRowLike, spec: Strategy, takenIds: Iterable<string>): SavePlan {
  const locked = current.status === "validated" || (current.spec as Partial<Strategy> | null)?.version_locked === true;
  if (locked) {
    const id = nextFreeVersionId(current.id, takenIds);
    const { version } = parseStrategyId(id);
    return { mode: "bump", id, previousId: current.id, version, status: "untested", spec: { ...spec, strategy_id: id, version, parent_id: current.id, version_locked: false } };
  }
  return { mode: "update", id: current.id, status: statusFor(spec), spec: { ...spec, strategy_id: current.id, version: current.version, parent_id: current.parentId } };
}

/** A blank draft. Session defaults come from the schema (09:15–15:30). */
export function emptyDraft(id: string, name = "New strategy"): Strategy {
  return {
    strategy_id: id, name, version: parseStrategyId(id).version, parent_id: null,
    market: "NSE_EQ", instruments: [], timeframe: "15m",
    session: { start: "09:15", end: "15:30", flat_at_close: true },
    regime_affinity: [], inputs: {}, entry_long: [], entry_short: null,
    trigger: { type: "next_bar_open" }, stop: null, targets: [], trailing: { type: "none", params: {} }, time_exit: {},
    risk: { min_rr_after_costs: 1.5, max_equity_risk_pct: 0.5, max_trades_per_day: 3 },
    automation_permission: "mentor_only", ambiguity_flags: [], version_locked: false,
  };
}

/** Clone a template spec into a user's own strategy row. Instruments are copied as they are. */
export function cloneSpec(template: Strategy, id: string, name: string, parentId: string): Strategy {
  return { ...template, strategy_id: id, name, version: 1, parent_id: parentId, instruments: [...template.instruments], version_locked: false };
}

/** Why a strategy cannot be validated or watched right now, or null when it can. */
export function validateBlockedReason(status: string): string | null {
  if (status === "testable" || status === "validated" || status === "untested") return null;
  return "Not testable yet. Open the strategy; the verdict lists what is missing.";
}
export function watchBlockedReason(status: string, permission: string): string | null {
  if (status !== "validated") return "Validate the strategy first. Watching needs a validated version.";
  if (permission !== "paper_only") return `Automation permission is ${permission}. Set it to paper_only in the Builder to watch.`;
  return null;
}
