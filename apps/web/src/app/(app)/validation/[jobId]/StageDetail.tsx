import { DrawdownChart, Heatmap, Histogram, LineChart } from "@/components/charts";
import { day, num, pct, r, rupees } from "@/lib/format";
import type { SkipCounter, StageResult, Stats } from "@/lib/types";
import { SKIP_MEANING, costBreakdown, formatMetric } from "../report";

type Rec = Record<string, unknown>;
const rec = (v: unknown): Rec => (v && typeof v === "object" && !Array.isArray(v) ? (v as Rec) : {});
const stats = (v: unknown): Stats | null => (v && typeof v === "object" ? (v as Stats) : null);

/** Per-stage detail panel. Every branch tolerates a missing or partial payload and says so in a sentence. */
export function StageDetail({ stage }: { stage: StageResult }) {
  const d = rec(stage.detail);
  switch (stage.stage) {
    case 1: return <Stage1 d={d} metrics={stage.metrics} />;
    case 2: return <Stage2 d={d} />;
    case 3: return <Stage3 d={d} />;
    case 4: return <Stage4 d={d} />;
    case 5: return <Stage5 d={d} />;
    case 6: return <Stage6 d={d} />;
    case 7: return <Stage7 d={d} />;
    case 8: return <Stage8 d={d} summary={stage.summary} status={stage.status} />;
    default: return <p className="muted">No detail for this stage.</p>;
  }
}

/** Stats side by side: one column per named Stats object. */
function StatsTable({ cols }: { cols: { label: string; s: Stats | null }[] }) {
  const present = cols.filter((c) => c.s);
  if (present.length === 0) return <p className="muted">No statistics in this payload.</p>;
  const rows: [string, (s: Stats) => string][] = [
    ["Trades", (s) => String(s.trades)],
    ["Win rate", (s) => pct(s.win_rate * 100, 0)],
    ["Expectancy", (s) => r(s.expectancy_r)],
    ["Avg win / loss", (s) => `${r(s.avg_win_r)} / ${r(s.avg_loss_r)}`],
    ["Profit factor", (s) => num(s.profit_factor)],
    ["Max drawdown", (s) => `${pct(s.max_drawdown_pct)} · ${num(s.max_drawdown_r, 1)}R`],
    ["Largest trade share", (s) => pct(s.largest_trade_share * 100, 0)],
    ["Net after costs", (s) => rupees(s.net_pnl)],
  ];
  return (
    <div className="table-scroll">
      <table className="ledger-table">
        <thead><tr><th></th>{present.map((c) => <th key={c.label} className="num">{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map(([label, f]) => (
            <tr key={label}><td>{label}</td>{present.map((c) => <td key={c.label} className="num">{f(c.s!)}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Gross expectancy, cost per trade and net expectancy in R for one Stats object. Nothing when the payload predates the split. */
function CostLedger({ s, label }: { s: Stats | null; label: string }) {
  const c = costBreakdown(s);
  if (!c) return null;
  return (
    <div data-testid="cost-ledger">
      <span className="label">{label}</span>
      <div className="ledger">
        <div className="row row--tight"><span className="label">Gross expectancy</span><span className="muted">per trade, before brokerage, taxes and fees</span><span className="fig">{r(c.gross)}</span></div>
        <div className="row row--tight"><span className="label">Cost per trade</span><span className="muted">what brokerage, taxes and fees take from each trade</span><span className="fig">{r(-c.cost)}</span></div>
        <div className="row row--tight"><span className="label">Net expectancy</span><span className="muted">after costs; the number the gate reads</span><span className={`fig ${c.net < 0 ? "status--blocked" : ""}`}>{r(c.net)}</span></div>
      </div>
      {c.exceeds && <p className="muted" style={{ margin: "6px 0 0" }} data-testid="costs-exceed">Costs exceed the gross edge.</p>}
    </div>
  );
}

/** Stage-1 extras: how often each entry condition held, the setups they made together, and the setups the backtester skipped. */
function EntryConditions({ d }: { d: Rec }) {
  const rows = Object.entries(rec(d.condition_stats)).map(([name, v]) => {
    const o = rec(v);
    return { name, side: typeof o.side === "string" ? o.side : "–", truePct: Number(o.true_pct), bars: Number(o.true_bars) };
  }).filter((x) => Number.isFinite(x.truePct)).sort((a, b) => a.truePct - b.truePct);
  const setups = rec(d.setup_bars);
  const hasSetups = Number.isFinite(Number(setups.bars));
  if (rows.length === 0 && !hasSetups) return null;
  return (
    <div data-testid="entry-conditions">
      <span className="label">Entry conditions</span>
      {rows.length > 0 && (
        <>
          <p className="help" style={{ margin: "4px 0 6px" }}>How often each condition held on its own over every bar after warm-up. The lowest row is the bottleneck: it caps how many setups there can be.</p>
          <div className="table-scroll">
            <table className="ledger-table">
              <thead><tr><th>Condition</th><th>Side</th><th className="num">True %</th><th className="num">Bars</th></tr></thead>
              <tbody>
                {rows.map((x, i) => (
                  <tr key={x.name} className={i === 0 ? "row--tinted-watch" : undefined}>
                    <td>{x.name}</td>
                    <td>{x.side}</td>
                    <td className={`num ${i === 0 ? "status--watch" : ""}`}>{pct(x.truePct)}</td>
                    <td className="num">{Number.isFinite(x.bars) ? Math.round(x.bars) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {hasSetups && (
        <p className="mono" style={{ margin: "8px 0 0", fontSize: "var(--fs-1)" }} data-testid="setup-bars">
          All conditions together: {Math.round(Number(setups.long ?? 0))} long / {Math.round(Number(setups.short ?? 0))} short setups on {Math.round(Number(setups.bars))} bars
        </p>
      )}
    </div>
  );
}

function SkippedSetups({ d }: { d: Rec }) {
  const st = rec(d.stats);
  const rows = (Object.keys(SKIP_MEANING) as SkipCounter[])
    .map((k) => ({ k, v: Number(d[k] ?? st[k]) }))
    .filter((x) => Number.isFinite(x.v));
  if (rows.length === 0) return null;
  return (
    <div data-testid="skipped-setups">
      <span className="label">Skipped setups</span>
      <p className="help" style={{ margin: "4px 0 0" }}>Setups the rules found that never became a trade, and why. Each reason is one of your own settings.</p>
      <div className="ledger">
        {rows.map(({ k, v }) => (
          <div key={k} className="row row--tight">
            <span className="label">{SKIP_MEANING[k].label}</span>
            <span className="muted">{SKIP_MEANING[k].meaning}</span>
            <span className={`fig ${v > 0 ? "" : "faint"}`}>{Math.round(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Stage1({ d, metrics }: { d: Rec; metrics: Record<string, number> }) {
  const problems = Array.isArray(d.problems) ? (d.problems as string[]) : [];
  return (
    <div className="stack">
      <div className="ledger">
        {Object.entries(metrics).filter(([k]) => k !== "margin").map(([k, v]) => (
          <div key={k} className="row row--tight"><span className="label">{k.replace(/_/g, " ")}</span><span /><span className="fig">{formatMetric(k, v)}</span></div>
        ))}
      </div>
      {problems.length > 0 && (
        <ul className="mono" style={{ margin: 0, paddingLeft: 18, fontSize: "var(--fs-1)" }}>
          {problems.map((p) => <li key={p} className="status--blocked">{p}</li>)}
        </ul>
      )}
      <EntryConditions d={d} />
      <SkippedSetups d={d} />
      <StatsTable cols={[{ label: "In-sample", s: stats(d.stats) }]} />
    </div>
  );
}

function equityPoints(v: unknown): { pts: [number, number][]; labels?: [string, string] } {
  if (!Array.isArray(v)) return { pts: [] };
  const rows = v as [string | number, number][];
  const pts = rows.map((row, i) => [i, Number(row[1])] as [number, number]).filter((p) => Number.isFinite(p[1]));
  const first = rows[0]?.[0], last = rows[rows.length - 1]?.[0];
  const labels = typeof first === "string" && typeof last === "string" ? ([day(first), day(last)] as [string, string]) : undefined;
  return { pts, labels };
}

function Stage2({ d }: { d: Rec }) {
  const oos = equityPoints(d.equity);
  const ins = equityPoints(d.in_sample_equity ?? d.equity_in_sample);
  return (
    <div className="stack">
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <div>
          <span className="label">In-sample equity</span>
          {ins.pts.length > 1 ? <LineChart points={ins.pts} yLabel="equity, ₹" xLabels={ins.labels} height={180} caption="Equity in rupees after costs, one point per trade in order, in-sample (the first 70% of the data)." /> : <p className="muted">The engine reports in-sample statistics only; the curve on the right is the out-of-sample run.</p>}
        </div>
        <div>
          <span className="label">Out-of-sample equity</span>
          {oos.pts.length > 1 ? <LineChart points={oos.pts} yLabel="equity, ₹" xLabels={oos.labels} height={180} caption="Equity in rupees after costs, one point per trade in order, out-of-sample (the last 30%, never seen while building)." /> : <p className="muted">No out-of-sample equity in this payload.</p>}
        </div>
      </div>
      <StatsTable cols={[{ label: "In-sample", s: stats(d.in_sample) }, { label: "Out-of-sample", s: stats(d.oos) }]} />
      <CostLedger s={stats(d.oos)} label="Out-of-sample edge before and after costs" />
    </div>
  );
}

function Stage3({ d }: { d: Rec }) {
  const windows = Array.isArray(d.windows) ? (d.windows as Rec[]) : [];
  if (windows.length === 0) return <p className="muted">No walk-forward windows in this payload.</p>;
  return (
    <div className="table-scroll">
      <table className="ledger-table">
        <thead><tr><th>#</th><th>Train</th><th>Test</th><th className="num">Train trades</th><th className="num">Test trades</th><th className="num">Test expectancy</th><th className="num">Test net</th></tr></thead>
        <tbody>
          {windows.map((w, i) => {
            const tr = rec(w.train), te = rec(w.test), s = stats(w.stats);
            return (
              <tr key={i}>
                <td>{i + 1}</td>
                <td>{day(String(tr.start ?? ""))} – {day(String(tr.end ?? ""))}</td>
                <td>{day(String(te.start ?? ""))} – {day(String(te.end ?? ""))}</td>
                <td className="num">{String(tr.trades ?? "–")}</td>
                <td className="num">{String(te.trades ?? s?.trades ?? "–")}</td>
                <td className="num">{r(Number(te.expectancy_r ?? s?.expectancy_r))}</td>
                <td className="num">{s ? rupees(s.net_pnl) : "–"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Stage4({ d }: { d: Rec }) {
  const m = rec(d.multipliers);
  const keys = Object.keys(m).sort((a, b) => Number(a) - Number(b));
  if (keys.length === 0) return <p className="muted">No cost multipliers in this payload.</p>;
  const baseKey = keys.find((k) => Number(k) === 1) ?? keys[0];
  return (
    <div className="stack">
      <div className="table-scroll">
        <table className="ledger-table">
          <thead><tr><th>Cost multiplier</th><th className="num">Trades</th><th className="num">Expectancy</th><th className="num">Profit factor</th><th className="num">Net after costs</th></tr></thead>
          <tbody>
            {keys.map((k) => {
              const s = stats(m[k]);
              return (
                <tr key={k}>
                  <td>×{k}</td>
                  <td className="num">{s?.trades ?? "–"}</td>
                  <td className={`num ${s && s.expectancy_r <= 0 ? "status--blocked" : ""}`}>{r(s?.expectancy_r)}</td>
                  <td className="num">{num(s?.profit_factor)}</td>
                  <td className="num">{s ? rupees(s.net_pnl) : "–"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <CostLedger s={stats(m[baseKey])} label={`Edge before and after costs at ×${baseKey}`} />
    </div>
  );
}

function Stage5({ d }: { d: Rec }) {
  const params = Array.isArray(d.params) ? (d.params as Rec[]) : [];
  if (params.length === 0) return <p className="muted">No parameter grid in this payload.</p>;
  const deltas = Array.from(new Set(params.flatMap((p) => (Array.isArray(p.grid) ? (p.grid as Rec[]).map((g) => Number(g.delta)) : [])))).sort((a, b) => a - b);
  const rows = params.map((p) => `${String(p.name)} (${String(p.base)})`);
  const values = params.map((p) => deltas.map((dl) => {
    const g = (Array.isArray(p.grid) ? (p.grid as Rec[]) : []).find((x) => Number(x.delta) === dl);
    const e = g ? Number(g.expectancy) : NaN;
    return Number.isFinite(e) ? e : null;
  }));
  return (
    <div className="stack">
      <Heatmap rows={rows} cols={deltas.map((x) => `${x > 0 ? "+" : ""}${x}%`)} values={values} labelW={240} caption="Rows are numeric parameters (base value in brackets); columns move each one by that percentage; each cell is the expectancy in R at that setting. A tinted cell keeps the edge (positive) or loses it (negative); read the number, not the shade." />
    </div>
  );
}

function Stage6({ d }: { d: Rec }) {
  const regimes = rec(d.regimes);
  const keys = Object.keys(regimes);
  if (keys.length === 0) return <p className="muted">No regime breakdown in this payload.</p>;
  const weakest = typeof d.weakest === "string" ? d.weakest : null;
  return (
    <div className="table-scroll">
      <table className="ledger-table">
        <thead><tr><th>Regime</th><th className="num">Trades</th><th className="num">Win rate</th><th className="num">Expectancy</th><th className="num">Max drawdown</th><th className="num">Net after costs</th></tr></thead>
        <tbody>
          {keys.map((k) => {
            const s = stats(regimes[k]);
            return (
              <tr key={k} className={k === weakest ? "row--tinted-watch" : undefined}>
                <td>{k}{k === weakest ? " (weakest)" : ""}</td>
                <td className="num">{s?.trades ?? "–"}</td>
                <td className="num">{s ? pct(s.win_rate * 100, 0) : "–"}</td>
                <td className={`num ${s && s.expectancy_r < 0 ? "status--blocked" : ""}`}>{r(s?.expectancy_r)}</td>
                <td className="num">{s ? pct(s.max_drawdown_pct) : "–"}</td>
                <td className="num">{s ? rupees(s.net_pnl) : "–"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Stage7({ d }: { d: Rec }) {
  const hist = Array.isArray(d.histogram) ? (d.histogram as [number, number][]).filter((b) => Array.isArray(b) && b.length === 2) : [];
  const p5 = Number(d.dd_p5), p50 = Number(d.dd_p50), p95 = Number(d.dd_p95);
  const marks = [[p5, "p5"], [p50, "p50"], [p95, "p95"]].filter(([x]) => Number.isFinite(x as number)).map(([x, label]) => ({ x: x as number, label: label as string }));
  return (
    <div className="stack">
      {hist.length ? <Histogram bins={hist} marks={marks} caption="Max drawdown in % of starting equity across 1000 shuffles of the trade order: left to right is drawdown size, bar height is how many shuffles landed there. Dashed lines mark p5, p50 and p95; the gate is on p95." /> : <p className="muted">No distribution in this payload.</p>}
      <div className="ledger">
        {[["p5", p5], ["p50", p50], ["p95 (gated)", p95]].map(([k, v]) => (
          <div key={String(k)} className="row row--tight"><span className="label">Max drawdown {k}</span><span className="muted">of starting equity</span><span className="fig">{pct(Number(v))}</span></div>
        ))}
      </div>
      {Array.isArray(d.equity) && <DrawdownChart equity={(d.equity as [number, number][]).map((e) => Number(e[1]))} caption="Drawdown from the running peak in %, one point per trade in the original order. The fill shows how far below the last high the account sat." />}
    </div>
  );
}

function Stage8({ d, summary, status }: { d: Rec; summary: string; status: StageResult["status"] }) {
  const paper = stats(d.paper), bt = stats(d.backtest);
  if (status === "skip" || !paper) {
    return <p className="muted">{summary || "Skipped: not enough closed paper trades to compare yet."} Keep paper trading; this stage runs itself once the count is reached.</p>;
  }
  return (
    <div className="stack">
      <StatsTable cols={[{ label: "Paper", s: paper }, { label: "Backtest", s: bt }]} />
      <p className="mono" style={{ margin: 0, fontSize: "var(--fs-1)" }}>agreement: {d.agreement === true ? "yes" : d.agreement === false ? "no" : "–"}</p>
    </div>
  );
}
