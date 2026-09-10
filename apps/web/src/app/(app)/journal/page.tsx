import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { num, pct, r, rupees, ts } from "@/lib/format";
import { byRegime, netRupees, outcomeStrip, streaks, totals, type TradeLike } from "@/lib/journal";
import { LEXICON_SENTENCE, NoteForm } from "./NoteForm";
import { TradeLedger, type JournalNote, type JournalTrade } from "./TradeLedger";

export const dynamic = "force-dynamic";

const n = (v: unknown): number | null => (v === null || v === undefined ? null : Number.isFinite(Number(v)) ? Number(v) : null);
/** Sim-clock strings in the JSON columns are IST wall time with no zone; pin them to UTC so `simTs` prints them as written. */
const s = (v: unknown): string | null => (typeof v === "string" && v ? (/(Z|[+-]\d\d:?\d\d)$/.test(v) ? v : `${v}Z`) : null);

/** Closed paper trades as a ledger, aggregates as small mono tables, then the free notes. Reads Postgres only. */
export default async function JournalPage() {
  const user = await requireUser();
  const [rows, noteRows] = await Promise.all([
    db.paperTrade.findMany({ where: { userId: user.id, status: "closed" }, orderBy: { closedAt: "desc" } }),
    db.journalNote.findMany({ where: { userId: user.id }, orderBy: { createdAt: "desc" } }),
  ]);
  const trades: JournalTrade[] = rows.map((t) => {
    const p = (t.planned ?? {}) as Record<string, unknown>, a = (t.actual ?? {}) as Record<string, unknown>;
    return {
      id: t.id, strategyId: t.strategyId, symbol: t.symbol, side: t.side, qty: t.qty,
      planned: { entry: n(p.entry), stop: n(p.stop), targets: Array.isArray(p.targets) ? (p.targets as unknown[]).map(Number).filter(Number.isFinite) : [], risk_r: n(p.risk_r) },
      actual: { entry: n(a.entry), exit: n(a.exit), entry_ts: s(a.entry_ts), exit_ts: s(a.exit_ts) },
      slippage: t.slippage, costs: t.costs, mfeR: t.mfeR, maeR: t.maeR, exitReason: t.exitReason, regime: t.regime, outcomeR: t.outcomeR,
      rulesFollowed: t.rulesFollowed, rulesTotal: t.rulesTotal, openedAt: t.openedAt.toISOString(), closedAt: t.closedAt ? t.closedAt.toISOString() : null,
    };
  });
  const notes: JournalNote[] = noteRows.map((x) => ({ id: x.id, tradeId: x.tradeId, text: x.text, flags: Array.isArray(x.flags) ? (x.flags as unknown[]).map(String) : [], createdAt: x.createdAt.toISOString() }));
  const free = notes.filter((x) => !x.tradeId);

  const like: TradeLike[] = trades.map((t) => ({ outcomeR: t.outcomeR, regime: t.regime, rulesFollowed: t.rulesFollowed, rulesTotal: t.rulesTotal, closedAt: t.closedAt, side: t.side, qty: t.qty, costs: t.costs, actual: t.actual }));
  const tot = totals(like), regimes = byRegime(like), st = streaks(like), strip = outcomeStrip(like), net = netRupees(like);
  const signedTint = (v: number) => (v > 0 ? "status--eligible" : v < 0 ? "status--blocked" : "");

  return (
    <>
      <div className="page-head">
        <h1 className="h-display">Journal</h1>
        <span className="mono muted">{tot.trades} closed paper trade{tot.trades === 1 ? "" : "s"}</span>
      </div>

      <div className="section">
        <span className="label">Closed paper trades</span>
        <TradeLedger trades={trades} notes={notes} />
      </div>

      <div className="section">
        <span className="label">Aggregates</span>
        <div className="twocol" style={{ marginTop: 10 }}>
          <div>
            <div className="table-scroll">
              <table className="ledger-table" data-testid="by-regime">
                <thead><tr><th>Regime</th><th className="num">Trades</th><th className="num">Process</th><th className="num">Net R</th><th className="num">Avg R</th></tr></thead>
                <tbody>
                  {regimes.length === 0 && <tr><td colSpan={5} className="muted">Nothing to group yet.</td></tr>}
                  {regimes.map((g) => (
                    <tr key={g.regime}>
                      <td>{g.regime}</td>
                      <td className="num">{g.trades}</td>
                      <td className="num">{pct(g.processPct, 0)}</td>
                      <td className={`num ${signedTint(g.netR)}`}>{r(g.netR)}</td>
                      <td className="num">{r(g.avgR)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mono" style={{ marginTop: 14, fontSize: "var(--fs-1)" }}>
              <span className="label">Last {Math.min(30, tot.trades)} outcomes</span>
              <div data-testid="outcome-strip" style={{ letterSpacing: "0.18em", marginTop: 4, wordBreak: "break-all" }}>{strip || "–"}</div>
              <div className="faint" style={{ marginTop: 2 }}>+ win, − loss, · flat; oldest to newest</div>
            </div>
          </div>
          <div className="ledger" data-testid="totals">
            <div className="row row--tight"><span className="label">Trades</span><span /><span className="fig">{tot.trades}</span></div>
            <div className="row row--tight"><span className="label">Win rate</span><span className="muted">{tot.wins} of {tot.trades}</span><span className="fig">{pct(tot.winRate, 0)}</span></div>
            <div className="row row--tight"><span className="label">Net R</span><span className="muted">avg {r(tot.avgR)}</span><span className={`fig ${signedTint(tot.netR)}`}>{r(tot.netR)}</span></div>
            <div className="row row--tight"><span className="label">Process score</span><span className="muted">rules followed of rules total</span><span className="fig">{pct(tot.processPct, 0)}</span></div>
            <div className="row row--tight"><span className="label">Net after costs</span><span className="muted">paper, from actual fills</span><span className="fig">{net === null ? "–" : rupees(net)}</span></div>
            <div className="row row--tight"><span className="label">Current streak</span><span className="muted">{st.current > 0 ? "wins" : st.current < 0 ? "losses" : "flat"}</span><span className="fig">{st.current === 0 ? "0" : `${st.current > 0 ? "+" : "−"}${Math.abs(st.current)}`}</span></div>
            <div className="row row--tight"><span className="label">Longest win</span><span /><span className="fig">{st.longestWin}</span></div>
            <div className="row row--tight"><span className="label">Longest loss</span><span /><span className="fig">{st.longestLoss}</span></div>
          </div>
        </div>
      </div>

      <div className="section">
        <span className="label">Notes</span>
        <div className="stack" style={{ marginTop: 10 }}>
          <NoteForm />
          {free.length === 0 && <p className="muted">No free notes yet. Notes tied to a trade sit under that trade in the ledger above.</p>}
          {free.map((x) => (
            <div key={x.id} data-testid="note" style={{ borderBottom: "1px solid var(--rule)", paddingBottom: 8 }}>
              <div className="mono faint" style={{ fontSize: "var(--fs-1)" }}>{ts(x.createdAt)}</div>
              <div style={{ whiteSpace: "pre-wrap" }}>{x.text}</div>
              {x.flags.length > 0 && <div className="status--watch" style={{ fontSize: "var(--fs-1)", marginTop: 4 }}><span className="mono">{x.flags.join(", ")}</span> · {LEXICON_SENTENCE}</div>}
            </div>
          ))}
        </div>
        <p className="faint mono" style={{ marginTop: 10, fontSize: "var(--fs-1)" }}>{notes.length} note{notes.length === 1 ? "" : "s"} · {num(tot.trades ? notes.length / tot.trades : 0, 2)} per trade</p>
      </div>
    </>
  );
}
