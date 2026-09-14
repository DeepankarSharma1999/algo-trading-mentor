"use client";
import { LineChart } from "@/components/charts";
import { num, pct, r } from "@/lib/format";
import type { BacktestResult } from "@/lib/types";
import { conditionRows, equityPoints, skipRows, windowSentence } from "./quickTest.pure";

interface Props {
  /** The last reply, kept on screen while the next run is in flight. */
  result: BacktestResult | null;
  error: string | null;
  /** The spec on the left changed after `result` was produced. */
  stale: boolean;
  pending: boolean;
}

/**
 * "Quick test · in-sample": the in-sample backtest of the spec as it stands in the editor. A ledger of the headline
 * figures, the entry-condition hit rates (lowest row is the bottleneck), and the equity curve. Renders whatever
 * the engine sent and says so in a sentence when a piece is missing.
 */
export function QuickTest({ result, error, stale, pending }: Props) {
  const s = result?.stats ?? null;
  const conds = conditionRows(result?.condition_stats);
  const setups = result?.setup_bars;
  const eq = equityPoints(result?.equity);
  const skips = skipRows(s);
  return (
    <div className="section" data-testid="quick-test">
      <span className="label">Quick test · in-sample</span>
      {stale && result && <p className="help" style={{ margin: "8px 0 0" }} data-testid="quick-test-stale">Spec changed since this quick test.</p>}
      {pending && <p className="help" style={{ margin: "8px 0 0" }} role="status">Testing on the first part of the data{result ? "; the last result stays below until the new one lands" : ""}.</p>}
      {error && <p className="notice notice--watch" role="status" style={{ margin: "8px 0 0" }} data-testid="quick-test-error">{error}</p>}
      {!result && !error && !pending && (
        <p className="help" style={{ margin: "8px 0 0" }}>Nothing run yet. Quick test backtests what you see, saved or not, on the first 70% of the data; the rest stays locked for Validate.</p>
      )}
      {result && (
        <div className="stack" style={{ marginTop: 8 }}>
          <p className="help" style={{ margin: 0 }} data-testid="quick-test-window">{windowSentence(result.window)}</p>

          {s ? (
            <div className="ledger" data-testid="quick-test-ledger">
              <Row label="Trades" fig={String(Math.round(s.trades))} />
              <Row label="Win rate" fig={pct(s.win_rate * 100, 0)} />
              <Row label="Expectancy before costs" fig={r(s.gross_expectancy_r)} />
              <Row label="Cost per trade" fig={Number.isFinite(s.cost_per_trade_r) ? r(-s.cost_per_trade_r) : "–"} />
              <Row label="Expectancy after costs" fig={r(s.expectancy_r)} cls={s.expectancy_r > 0 ? "status--eligible" : "status--blocked"} testId="quick-test-net" />
              <Row label="Profit factor" fig={num(s.profit_factor)} />
              <Row label="Max drawdown" fig={`${pct(s.max_drawdown_pct)} · ${num(s.max_drawdown_r, 1)}R`} />
              {skips.map(([label, v]) => <Row key={label} label={label} fig={String(v)} />)}
            </div>
          ) : (
            <p className="muted" style={{ margin: 0 }}>The reply carried no statistics.</p>
          )}

          {(conds.length > 0 || setups) && (
            <div data-testid="quick-test-conditions">
              <span className="label">Entry conditions</span>
              {conds.length > 0 && (
                <>
                  <p className="help" style={{ margin: "4px 0 6px" }}>How often each condition held on its own. The lowest row is the bottleneck: it caps how many setups there can be.</p>
                  <div className="table-scroll">
                    <table className="ledger-table">
                      <thead><tr><th>Condition</th><th>Side</th><th className="num">True %</th><th className="num">Bars</th></tr></thead>
                      <tbody>
                        {conds.map((x, i) => (
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
              {setups && Number.isFinite(Number(setups.bars)) && (
                <p className="mono" style={{ margin: "8px 0 0", fontSize: "var(--fs-1)" }} data-testid="quick-test-setups">
                  All conditions together: {Math.round(Number(setups.long ?? 0))} long / {Math.round(Number(setups.short ?? 0))} short setups on {Math.round(Number(setups.bars))} bars
                </p>
              )}
            </div>
          )}

          <div>
            <span className="label">Equity</span>
            <div style={{ marginTop: 6 }}>
              {eq.pts.length > 1
                ? <LineChart points={eq.pts} yLabel="equity, ₹" xLabels={eq.labels} height={180} caption="Equity in rupees after costs, in-sample only" />
                : <p className="muted" style={{ margin: 0 }}>{s && s.trades === 0 ? "No trades in the window, so there is no curve to draw." : "Not enough points to draw."}</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, fig, cls, testId }: { label: string; fig: string; cls?: string; testId?: string }) {
  return (
    <div className="row row--tight">
      <span className="label">{label}</span>
      <span />
      <span className={`value value--fig ${cls ?? ""}`} data-testid={testId}>{fig}</span>
    </div>
  );
}
