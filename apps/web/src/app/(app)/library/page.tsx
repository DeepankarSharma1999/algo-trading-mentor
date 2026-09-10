import { Suspense } from "react";
import { REGIMES } from "@atm/schema";
import { StrategyRules } from "@/components/StrategyRules";
import { requireUser } from "@/lib/auth";
import { listTemplates, type TemplateRow } from "@/lib/strategies";
import { cloneAction } from "./actions";
import { LibraryFilters } from "./LibraryFilters";

export const dynamic = "force-dynamic";

const TAGLINE = "Templates to learn the schema";

/** Templates grouped by regime. Plain-language rules, ambiguity notes, a Clone button. No numbers, no ranking. */
export default async function LibraryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  await requireUser();
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "all";
  const regime = one(sp.regime), timeframe = one(sp.timeframe), notice = one(sp.notice);
  const all = await listTemplates();
  const regimeOf = (t: TemplateRow) => t.rules.regime || t.spec.regime_affinity?.[0] || "unspecified";
  const shown = all.filter((t) => (regime === "all" || regimeOf(t) === regime) && (timeframe === "all" || t.spec.timeframe === timeframe));
  const order = [...REGIMES, "unspecified"] as string[];
  const groups = order.map((r) => [r, shown.filter((t) => regimeOf(t) === r)] as const).filter(([, ts]) => ts.length > 0);

  return (
    <>
      <div className="page-head">
        <h1 className="h-display">Library</h1>
        <span className="muted">{TAGLINE}</span>
      </div>
      {notice !== "all" && <p className="notice notice--watch" role="status">{notice}</p>}

      <Suspense fallback={null}><LibraryFilters regime={regime} timeframe={timeframe} /></Suspense>
      <p className="mono muted" style={{ marginTop: 10 }}>{shown.length} of {all.length} templates</p>

      {all.length === 0 && <p className="notice">No templates are seeded yet. Run the database seed and reload.</p>}
      {all.length > 0 && shown.length === 0 && <p className="notice">No template matches these filters. Set a filter back to all.</p>}

      {groups.map(([r, ts]) => (
        <div className="section" key={r}>
          <span className="label">{r.replace("_", " ")}</span>
          {ts.map((t) => (
            <div className="ledger" key={t.id} data-testid="template" style={{ marginBottom: 22 }}>
              <div className="row">
                <span className="label" style={{ textTransform: "none", letterSpacing: 0 }}>{t.id}</span>
                <span>
                  <span style={{ fontSize: "var(--fs-3)" }}>{t.name}</span>
                  <span className="mono muted" style={{ display: "block", fontSize: "var(--fs-1)", marginTop: 2 }}>
                    {t.spec.timeframe} · {t.spec.market} · instruments: {t.spec.instruments.length ? t.spec.instruments.join(", ") : "none listed; you type your own symbols"}
                  </span>
                  <span className="faint" style={{ display: "block", fontSize: "var(--fs-1)", marginTop: 2 }}>{TAGLINE}</span>
                </span>
                <form action={cloneAction}>
                  <input type="hidden" name="template_id" value={t.id} />
                  <button className="btn btn--sm">Clone</button>
                </form>
              </div>
              <div className="row row--wide">
                <span className="label">Rules</span>
                <p style={{ margin: 0, maxWidth: 720 }}>{t.rules.rules || <span className="muted">No plain-language rules were written for this template.</span>}</p>
              </div>
              <div className="row row--wide">
                <span className="label">From the spec</span>
                <StrategyRules spec={t.spec} />
              </div>
              <div className="row row--wide">
                <span className="label">Ambiguity notes</span>
                {t.rules.ambiguity_notes.length ? (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: "var(--fs-1)" }}>{t.rules.ambiguity_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
                ) : <span className="muted" style={{ fontSize: "var(--fs-1)" }}>None recorded.</span>}
              </div>
            </div>
          ))}
        </div>
      ))}
    </>
  );
}
