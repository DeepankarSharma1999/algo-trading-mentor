import { Suspense } from "react";
import { requireUser } from "@/lib/auth";
import { listTemplates } from "@/lib/strategies";
import { LibraryBrowser, type TemplateItem } from "./LibraryBrowser";

export const dynamic = "force-dynamic";

const TAGLINE = "Templates to learn the schema";

/** Templates grouped by regime: a name, one mono line, one summary sentence, the full rules folded away, a Clone button. No numbers, no ranking. */
export default async function LibraryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireUser();
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? null;
  const notice = one(sp.notice);
  const all = await listTemplates();
  const templates: TemplateItem[] = all.map((t) => ({ id: t.id, name: t.name, spec: t.spec, rules: t.rules }));

  return (
    <>
      <div className="page-head">
        <h1 className="h-display">Library</h1>
        <span className="muted">{TAGLINE}</span>
      </div>
      <p className="page-intro">
        A template is a worked example of the strategy schema: one complete set of rules, written in plain words and as a spec, with the
        places where the wording could be read two ways noted underneath. It is not a recommendation and carries no performance figures.
        Clone copies a template into your own strategies, where you change every symbol and rule before it can be validated.
      </p>
      <Suspense fallback={null}>
        <LibraryBrowser templates={templates} notice={notice} />
      </Suspense>
    </>
  );
}
