import { conditionText, type Strategy } from "@atm/schema";

/** A spec as plain-language sentences. Expressions, figures and identifiers stay in mono. Server-safe. */
export function StrategyRules({ spec }: { spec: Partial<Strategy> }) {
  const lines: React.ReactNode[] = [];
  const conds = (cs: Strategy["entry_long"] | null | undefined) => joinAnd((cs ?? []).map((c) => <code>{conditionText(c)}</code>));
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
  if (s?.type) {
    const where = {
      signal_bar: "just beyond the signal bar", swing: "beyond the last swing", atr: "an ATR multiple away", indicator: "at an indicator level", fixed_pct: "a fixed percentage away",
    }[s.type] ?? s.type;
    lines.push(<>Place the stop {where} using <code>{s.type}</code>{params(s.params)}.</>);
  } else {
    lines.push(<>No stop rule yet.</>);
  }

  const targets = spec.targets ?? [];
  if (targets.length) {
    lines.push(<>Take profit at {joinAnd(targets.map((g) => (
      <code>{g.type === "rr" ? `${g.value}R` : g.type === "fixed_pct" ? `${g.value}%` : `${g.ref || "an indicator"} (${g.value})`}</code>
    )))}.</>);
  }
  const tr = spec.trailing;
  if (tr?.type && tr.type !== "none") lines.push(<>Trail the stop using <code>{tr.type}</code>{params(tr.params)}.</>);
  const te = spec.time_exit ?? {};
  if (te.max_bars) lines.push(<>Exit after <code>{te.max_bars}</code> bars in the trade.</>);
  if (te.at_time) lines.push(<>Exit at <code>{te.at_time}</code> if still in the trade.</>);
  if (!targets.length && (!tr?.type || tr.type === "none") && !te.max_bars && !te.at_time) lines.push(<>No exit rule yet.</>);

  const se = spec.session;
  if (se) {
    lines.push(<>
      Trade from <code>{se.start || "–"}</code> to <code>{se.end || "–"}</code>
      {spec.timeframe ? <> on <code>{spec.timeframe}</code> bars</> : null}
      {se.flat_at_close ? " and go flat at the close" : ""}.
    </>);
  }
  const r = spec.risk;
  if (r) {
    lines.push(<>
      Require at least <code>{r.min_rr_after_costs}</code> R:R after costs, risk at most <code>{r.max_equity_risk_pct}%</code> of equity per trade and take at most <code>{r.max_trades_per_day}</code> {r.max_trades_per_day === 1 ? "trade" : "trades"} a day.
    </>);
  }

  return (
    <div className="stack" data-testid="strategy-rules" style={{ fontSize: "var(--fs-2)" }}>
      {lines.map((l, i) => <p key={i} style={{ margin: 0 }}>{l}</p>)}
    </div>
  );
}

/** "a", "a and b", "a, b and c". */
function joinAnd(parts: React.ReactNode[]): React.ReactNode {
  return parts.map((p, i) => (
    <span key={i}>{i === 0 ? "" : i === parts.length - 1 ? " and " : ", "}{p}</span>
  ));
}

function params(p: object | undefined): React.ReactNode {
  const entries = Object.entries(p ?? {}).filter(([, v]) => v !== "" && v !== null && v !== undefined);
  if (!entries.length) return null;
  return <> ({joinAnd(entries.map(([k, v]) => <code>{k}={String(v)}</code>))})</>;
}
