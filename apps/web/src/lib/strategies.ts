// Server-side strategy access (never import from client components). Reads and writes go through Prisma;
// the pure decisions live in strategies.pure.ts.
import type { Strategy } from "@atm/schema";
import { db } from "./db";
import { cloneSpec, deriveIdFromName, emptyDraft, newDraftId, parseTemplateRules, planSave, statusFor, type TemplateRules } from "./strategies.pure";

export type { TemplateRules } from "./strategies.pure";
export { statusFor, deriveIdFromName } from "./strategies.pure";

export interface StrategyRow {
  id: string; userId: string | null; name: string; slug: string; version: number; parentId: string | null;
  status: string; spec: Strategy; plainRules: string; createdAt: Date;
}
export interface TemplateRow extends StrategyRow { rules: TemplateRules }

const asRow = (r: { id: string; userId: string | null; name: string; slug: string; version: number; parentId: string | null; status: string; spec: unknown; plainRules: string; createdAt: Date }): StrategyRow =>
  ({ ...r, spec: r.spec as Strategy });

/** Templates: rows with user_id NULL. plain_rules holds JSON {rules, ambiguity_notes, regime}. */
export async function listTemplates(): Promise<TemplateRow[]> {
  const rows = await db.strategy.findMany({ where: { userId: null }, orderBy: [{ name: "asc" }] });
  return rows.map((r) => {
    const row = asRow(r);
    return { ...row, rules: parseTemplateRules(r.plainRules, row.spec.regime_affinity?.[0] ?? "") };
  });
}

export async function listMine(userId: string): Promise<StrategyRow[]> {
  const rows = await db.strategy.findMany({ where: { userId }, orderBy: [{ slug: "asc" }, { version: "desc" }] });
  return rows.map(asRow);
}

export async function getStrategy(id: string, userId: string): Promise<StrategyRow | null> {
  const r = await db.strategy.findFirst({ where: { id, userId } });
  return r ? asRow(r) : null;
}

export async function getTemplate(id: string): Promise<TemplateRow | null> {
  const r = await db.strategy.findFirst({ where: { id, userId: null } });
  if (!r) return null;
  const row = asRow(r);
  return { ...row, rules: parseTemplateRules(r.plainRules, row.spec.regime_affinity?.[0] ?? "") };
}

async function mySlugs(userId: string) {
  return (await db.strategy.findMany({ where: { userId }, select: { slug: true } })).map((s) => s.slug);
}
async function myIds(userId: string) {
  return (await db.strategy.findMany({ where: { userId }, select: { id: true } })).map((s) => s.id);
}

/** Copy a template into the user's strategies as `slug_v1`, parented to the template. */
export async function cloneTemplate(userId: string, templateId: string, name?: string): Promise<string> {
  const t = await getTemplate(templateId);
  if (!t) throw new Error("That template does not exist.");
  const finalName = (name ?? t.name).trim() || t.name;
  const id = deriveIdFromName(finalName, await mySlugs(userId));
  const spec = cloneSpec(t.spec, id, finalName, t.id);
  await db.strategy.create({ data: {
    id, userId, name: finalName, slug: id.replace(/_v1$/, ""), version: 1, parentId: t.id,
    status: statusFor(spec), spec: spec as object, plainRules: t.rules.rules,
  } });
  return id;
}

/** An empty draft `new_strategy_vN`. */
export async function createDraft(userId: string): Promise<string> {
  const id = newDraftId(await myIds(userId));
  const spec = emptyDraft(id);
  await db.strategy.create({ data: { id, userId, name: spec.name, slug: "new_strategy", version: spec.version, parentId: null, status: "draft", spec: spec as object } });
  return id;
}

/**
 * Save a spec. A validated or version-locked row becomes a new `untested` version (returned id differs);
 * anything else is updated in place with its status recomputed. Returns the id that now holds the spec.
 */
export async function saveSpec(userId: string, id: string, spec: Strategy): Promise<{ id: string; created: boolean; status: string }> {
  const current = await db.strategy.findFirst({ where: { id, userId } });
  if (!current) throw new Error("That strategy does not exist.");
  const plan = planSave(current, spec, await myIds(userId));
  if (plan.mode === "bump") {
    await db.strategy.create({ data: {
      id: plan.id, userId, name: plan.spec.name, slug: current.slug, version: plan.version, parentId: plan.previousId,
      status: plan.status, spec: plan.spec as object, plainRules: current.plainRules,
    } });
    return { id: plan.id, created: true, status: plan.status };
  }
  await db.strategy.update({ where: { id: plan.id }, data: { name: plan.spec.name, status: plan.status, spec: plan.spec as object } });
  return { id: plan.id, created: false, status: plan.status };
}
