import { conditionText, type Strategy } from "@atm/schema";

/** A spec as plain-language sentences. Expressions, figures and identifiers stay in mono. Server-safe. */
export function StrategyRules({ spec }: { spec: Partial<Strategy> }) {
  const lines: React.ReactNode[] = [];
  const conds = (cs: Strategy["entry_long"] | null | undefined) => (cs ?? []).map((c, i) => (
    <span key={i}>{i > 0 ? " and " : ""}<code>{conditionText(c)}</code></span>
  ));
  if (spec.entry_long?.length) lines.push(<>Go long when {conds(spec.entry_long)}.</>);
  if (spec.entry_short?.length) lines.push(<>Go short when {conds(spec.entry_short)}.</>);
  if (!spec.entry_long?.length && !spec.entry_short?.length) lines.push(<>No entry condition yet.</>);

  const t = spec.trigger;
  if (t?.type) {
    const offset = t.offset_pct ? <> with an offset of <code>{t.offset_pct}%</code></> : null;
    const how = { next_bar_open: "at the next bar open", break_of_signal_bar: "on a break of the signal bar", bar_close: "at the close of the signal bar", limit: "with a limit order" }[t.type] ?? t.type;
    lines.push(<>Enter {how}{offset}.</>);
  }
  const s = spec.stop;
  lines.push(s?.type ? <>Stop: <code>{s.type}</code>{params(s.params)}.</> : <>No stop rule yet.</>);

  const targets = spec.targets ?? [];
  if (targets.length) {
    lines.push(<>Target{targets.length > 1 ? "s" : ""}: {targets.map((g, i) => (
      <span key={i}>{i > 0 ? ", " : ""}<code>{g.type === "rr" ? `${g.value}R` : g.type === "fixed_pct" ? `${g.value}%` : `${g.ref ?? "indicator"} (${g.value})`}</code></span>
    ))}.</>);
  }
  const tr = spec.trailing;
  if (tr?.type && tr.type !== "none") lines.push(<>Trail with <code>{tr.type}</code>{params(tr.params)}.</>);
  const te = spec.time_exit ?? {};
  if (te.max_bars) lines.push(<>Exit after <code>{te.max_bars}</code> bars.</>);
  if (te.at_time) lines.push(<>Exit at <code>{te.at_time}</code>.</>);
  if (!targets.length && (!tr?.type || tr.type === "none") && !te.max_bars && !te.at_time) lines.push(<>No exit rule yet.</>);

  const se = spec.session;
  if (se) lines.push(<>Session <code>{se.start || "–"}</code> to <code>{se.end || "–"}</code>{se.flat_at_close ? ", flat at close" : ""}{spec.timeframe ? <> on <code>{spec.timeframe}</code> bars</> : null}.</>);
  const r = spec.risk;
  if (r) lines.push(<>At least <code>{r.min_rr_after_costs}</code> R:R after costs, at most <code>{r.max_equity_risk_pct}%</code> of equity at risk per trade, at most <code>{r.max_trades_per_day}</code> trades a day.</>);

  return (
    <div className="stack" data-testid="strategy-rules" style={{ fontSize: "var(--fs-2)" }}>
      {lines.map((l, i) => <p key={i} style={{ margin: 0 }}>{l}</p>)}
    </div>
  );
}

function params(p: object | undefined): React.ReactNode {
  const entries = Object.entries(p ?? {});
  if (!entries.length) return null;
  return <> ({entries.map(([k, v], i) => <span key={k}>{i > 0 ? ", " : ""}<code>{k}={String(v)}</code></span>)})</>;
}
