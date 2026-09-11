"use client";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { REGIMES, TIMEFRAMES, type Strategy } from "@atm/schema";
import { StrategyRules } from "@/components/StrategyRules";
import type { TemplateRules } from "@/lib/strategies.pure";
import { cloneAction } from "./actions";

/** What the browser needs from a template row; serialisable so the server page can hand it over. */
export interface TemplateItem { id: string; name: string; spec: Strategy; rules: TemplateRules }

const REGIME_HELP: Record<string, string> = {
  trend: "The market is making higher highs or lower lows; these templates follow the move and buy pullbacks or breakouts in its direction.",
  range: "Price is bouncing between a floor and a ceiling; these templates fade the edges and expect a return to the middle.",
  compression: "Volatility has dried up and bars are small; these templates wait for the squeeze to release and trade the first expansion.",
  high_vol: "Bars are large and fast; these templates use wider stops, smaller size and quick exits.",
  event: "A scheduled event (results, policy, expiry) is in play; these templates trade the reaction, not the anticipation.",
  unspecified: "The template does not name a regime; read its rules to decide when it applies.",
};

/** A labelled control in the toolbar: label above, control below. */
const FIELD: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4 };

const firstSentence = (text: string) => {
  const m = /^[\s\S]*?[.!?](?=\s|$)/.exec(text.trim());
  return (m ? m[0] : text).trim();
};

/** Search, filters, count and the grouped list. Filtering is client-side and mirrored into the URL (q, regime, timeframe). */
export function LibraryBrowser({ templates, notice }: { templates: TemplateItem[]; notice: string | null }) {
  const path = usePathname();
  const params = useSearchParams();
  const regime = params.get("regime") ?? "all";
  const timeframe = params.get("timeframe") ?? "all";
  const urlQ = params.get("q") ?? "";
  const [q, setQ] = useState(urlQ);
  useEffect(() => { setQ(urlQ); }, [urlQ]);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(window.location.search);
    if (value === "all" || value === "") next.delete(key); else next.set(key, value);
    next.delete("notice");
    const qs = next.toString();
    window.history.replaceState(null, "", qs ? `${path}?${qs}` : path);
  };
  const clear = () => { setQ(""); window.history.replaceState(null, "", path); };

  const regimeOf = (t: TemplateItem) => t.rules.regime || t.spec.regime_affinity?.[0] || "unspecified";
  const needle = q.trim().toLowerCase();
  const shown = useMemo(() => templates.filter((t) =>
    (regime === "all" || regimeOf(t) === regime)
    && (timeframe === "all" || t.spec.timeframe === timeframe)
    && (!needle || t.name.toLowerCase().includes(needle) || t.rules.rules.toLowerCase().includes(needle) || t.id.includes(needle)),
  ), [templates, regime, timeframe, needle]);
  const filtered = regime !== "all" || timeframe !== "all" || needle !== "";
  const order = [...REGIMES, "unspecified"] as string[];
  const groups = order.map((r) => [r, shown.filter((t) => regimeOf(t) === r)] as const).filter(([, ts]) => ts.length > 0);

  return (
    <>
      {notice && <p className="notice notice--watch" role="status">{notice}</p>}

      <div className="toolbar" role="search">
        <label style={{ ...FIELD, flex: "1 1 260px" }}>
          <span className="label">Search</span>
          <input className="input" style={{ width: "100%" }} type="search" value={q} placeholder="Name or rule text, e.g. pullback, VWAP, ADX" spellCheck={false}
            onChange={(e) => { setQ(e.target.value); setParam("q", e.target.value); }} />
        </label>
        <label style={FIELD}>
          <span className="label">Regime</span>
          <select className="input input--inline" value={regime} onChange={(e) => setParam("regime", e.target.value)}>
            <option value="all">all</option>
            {REGIMES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <label style={FIELD}>
          <span className="label">Timeframe</span>
          <select className="input input--inline" value={timeframe} onChange={(e) => setParam("timeframe", e.target.value)}>
            <option value="all">all</option>
            {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
      </div>
      <p className="mono muted" style={{ margin: "0 0 4px" }} aria-live="polite">
        {shown.length} of {templates.length} templates
        {filtered && <> · <a href={path} onClick={(e) => { e.preventDefault(); clear(); }}>Clear filters</a></>}
      </p>

      {templates.length === 0 && <p className="notice">No templates are seeded yet. Run the database seed and reload.</p>}
      {templates.length > 0 && shown.length === 0 && (
        <div className="empty">
          <p>No template matches {needle ? <>&ldquo;{q.trim()}&rdquo;</> : "these filters"}{regime !== "all" || timeframe !== "all" ? " with the current regime and timeframe" : ""}.</p>
          <button type="button" className="btn" onClick={clear}>Clear filters</button>
        </div>
      )}

      {groups.map(([r, ts]) => (
        <div className="section" key={r}>
          <span className="label">{r.replace("_", " ")}</span>
          <p className="help" style={{ margin: "6px 0 4px", maxWidth: "64ch" }}>{REGIME_HELP[r] ?? REGIME_HELP.unspecified}</p>
          {ts.map((t) => <TemplateEntry key={t.id} t={t} regime={r} />)}
        </div>
      ))}
    </>
  );
}

function TemplateEntry({ t, regime }: { t: TemplateItem; regime: string }) {
  const long = t.spec.entry_long?.length > 0, short = (t.spec.entry_short?.length ?? 0) > 0;
  const side = long && short ? "both" : short ? "short" : long ? "long" : "no entry";
  const summary = firstSentence(t.rules.rules);
  return (
    <div data-testid="template" style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 16, alignItems: "start", padding: "14px 0", borderBottom: "1px solid var(--rule)" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "var(--fs-3)" }}>{t.name}</div>
        <div className="mono muted" style={{ fontSize: "var(--fs-1)", marginTop: 2 }}>
          {t.spec.timeframe} · {t.spec.market} · {regime} · {side} · {t.spec.automation_permission}
        </div>
        <p style={{ margin: "8px 0 0", maxWidth: "72ch" }}>
          {summary || <span className="muted">No plain-language rules were written for this template.</span>}
        </p>
        <details className="fold" style={{ marginTop: 8 }}>
          <summary>Full rules and ambiguity notes</summary>
          <div className="ledger">
            <div className="row row--wide">
              <span className="label">Rules</span>
              <p style={{ margin: 0, maxWidth: "72ch" }}>{t.rules.rules || <span className="muted">None written.</span>}</p>
            </div>
            <div className="row row--wide">
              <span className="label">From the spec</span>
              <StrategyRules spec={t.spec} />
            </div>
            <div className="row row--wide">
              <span className="label">Ambiguity notes</span>
              {t.rules.ambiguity_notes.length ? (
                <ul style={{ margin: 0, paddingLeft: 18 }}>{t.rules.ambiguity_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
              ) : <span className="muted">None recorded.</span>}
            </div>
            <div className="row row--wide">
              <span className="label">Instruments</span>
              <span className="mono">{t.spec.instruments.length ? t.spec.instruments.join(", ") : <span className="muted">None listed; you type your own symbols after cloning.</span>}</span>
            </div>
          </div>
        </details>
      </div>
      <form action={cloneAction} style={{ textAlign: "right", maxWidth: 220 }}>
        <input type="hidden" name="template_id" value={t.id} />
        <button className="btn">Clone</button>
        <div className="help help--tight">Copies into your strategies as a new draft you can edit.</div>
      </form>
    </div>
  );
}
