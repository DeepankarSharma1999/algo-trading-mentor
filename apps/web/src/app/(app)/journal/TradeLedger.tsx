"use client";
import Link from "next/link";
import { Fragment, useState } from "react";
import { num, r, rupees2, simTs, ts } from "@/lib/format";
import { LEXICON_SENTENCE, NoteForm } from "./NoteForm";

/** A closed paper trade, already serialised for the client (dates as ISO strings). */
export interface JournalTrade {
  id: string; strategyId: string; symbol: string; side: string; qty: number;
  planned: { entry: number | null; stop: number | null; targets: number[]; risk_r: number | null };
  actual: { entry: number | null; exit: number | null; entry_ts: string | null; exit_ts: string | null };
  slippage: number; costs: number; mfeR: number | null; maeR: number | null;
  exitReason: string | null; regime: string; outcomeR: number | null;
  rulesFollowed: number; rulesTotal: number; openedAt: string; closedAt: string | null;
}
export interface JournalNote { id: string; tradeId: string | null; text: string; flags: string[]; createdAt: string }

const price = (v: number | null | undefined) => (v === null || v === undefined ? "–" : num(v, 2));
const tint = (v: number | null) => (v === null ? "status" : v > 0 ? "status status--eligible" : v < 0 ? "status status--blocked" : "status");

/** Column headings with the sentence that appears on hover. Order matches the cells below. */
const COLUMNS: { head: string; title: string; num?: boolean }[] = [
  { head: "Closed", title: "Simulated-clock time when the paper position closed." },
  { head: "Strategy", title: "The strategy version whose rules produced this trade." },
  { head: "Symbol", title: "Instrument on the synthetic feed. Not a real quote." },
  { head: "Side", title: "long or short." },
  { head: "Qty", title: "Quantity, sized so a stop-out loses about 1R.", num: true },
  { head: "Outcome", title: "Result in R: profit or loss divided by the rupees risked. +1.00R means you made exactly what you risked; −1.00R means the stop was hit.", num: true },
  { head: "Process", title: "Process score: rules followed out of rules total on this trade.", num: true },
  { head: "Plan entry", title: "Entry price the rules asked for.", num: true },
  { head: "Fill entry", title: "Entry price the paper trade actually got.", num: true },
  { head: "Plan stop", title: "Stop price the rules placed.", num: true },
  { head: "Slippage", title: "Fill entry minus planned entry, in price points.", num: true },
  { head: "Costs", title: "Brokerage, taxes, exchange fees and the slippage estimate, in rupees.", num: true },
  { head: "MFE", title: "Maximum favourable excursion: the furthest the trade went in your favour before it closed, in R.", num: true },
  { head: "MAE", title: "Maximum adverse excursion: the furthest the trade went against you before it closed, in R.", num: true },
  { head: "Exit", title: "Why the trade closed: stop, target, time rule or session end." },
  { head: "Regime", title: "Market regime on the bar the trade opened." },
];

/**
 * Closed trades as one ledger table. "Details" on a row reveals the planned-vs-actual ledger, the
 * trade's notes and a note form. Plain client state; nothing here talks to the engine directly.
 */
export function TradeLedger({ trades, notes }: { trades: JournalTrade[]; notes: JournalNote[] }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const notesFor = (id: string) => notes.filter((n) => n.tradeId === id);
  if (trades.length === 0) {
    return (
      <div className="empty" data-testid="trades-empty">
        <p>No closed paper trades yet. Trades land here once a watcher on the Desk has opened and closed a paper position; a validated strategy set to Watch is all it takes.</p>
        <Link className="btn" href="/desk">Open the Desk</Link>
      </div>
    );
  }
  return (
    <div className="table-scroll">
      <table className="ledger-table" data-testid="trades">
        <thead>
          <tr>
            {COLUMNS.map((c) => <th key={c.head} className={c.num ? "num" : undefined} title={c.title}><abbr title={c.title} style={{ textDecoration: "none" }}>{c.head}</abbr></th>)}
            <th><span className="faint" style={{ textTransform: "none", letterSpacing: 0 }}>Details</span></th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const isOpen = !!open[t.id];
            const tn = notesFor(t.id);
            return (
              <Fragment key={t.id}>
                <tr data-testid="trade-row">
                  <td style={{ whiteSpace: "nowrap" }}>{simTs(t.closedAt)}</td>
                  <td>{t.strategyId}</td>
                  <td>{t.symbol}</td>
                  <td>{t.side}</td>
                  <td className="num">{t.qty}</td>
                  <td className={`num ${tint(t.outcomeR)}`}>{r(t.outcomeR)}</td>
                  <td className="num">{t.rulesFollowed}/{t.rulesTotal}</td>
                  <td className="num">{price(t.planned.entry)}</td>
                  <td className="num">{price(t.actual.entry)}</td>
                  <td className="num">{price(t.planned.stop)}</td>
                  <td className="num">{num(t.slippage, 2)}</td>
                  <td className="num">{rupees2(t.costs)}</td>
                  <td className="num">{r(t.mfeR)}</td>
                  <td className="num">{r(t.maeR)}</td>
                  <td>{t.exitReason ?? "–"}</td>
                  <td>{t.regime}</td>
                  <td>
                    <button type="button" className="btn btn--sm" aria-expanded={isOpen} aria-controls={`trade-detail-${t.id}`} onClick={() => setOpen((o) => ({ ...o, [t.id]: !isOpen }))}>
                      {isOpen ? "Hide details" : "Details"}
                    </button>
                  </td>
                </tr>
                {isOpen && (
                  <tr data-testid="trade-detail" id={`trade-detail-${t.id}`}>
                    <td colSpan={COLUMNS.length + 1} style={{ paddingBottom: 16 }}>
                      <div className="twocol" style={{ gap: 28 }}>
                        <div>
                          <span className="label">Planned vs actual</span>
                          <p className="help help--tight" style={{ margin: "4px 0 6px" }}>Left is what the rules asked for; right is what the paper fill got. The gap between them is your slippage and your discipline.</p>
                          <div className="ledger">
                            <Row label="Entry" planned={price(t.planned.entry)} actual={price(t.actual.entry)} />
                            <Row label="Stop" planned={price(t.planned.stop)} actual="–" />
                            <Row label="Targets / exit" planned={t.planned.targets.length ? t.planned.targets.map((x) => num(x, 2)).join(" / ") : "–"} actual={price(t.actual.exit)} />
                            <Row label="Risk" planned={t.planned.risk_r === null ? "–" : `${num(t.planned.risk_r, 2)}R`} actual={r(t.outcomeR)} />
                            <Row label="Entry time" planned={simTs(t.openedAt)} actual={simTs(t.actual.entry_ts)} />
                            <Row label="Exit time" planned="–" actual={simTs(t.actual.exit_ts ?? t.closedAt)} />
                            <Row label="Slippage" planned="0.00" actual={num(t.slippage, 2)} />
                            <Row label="Costs" planned="–" actual={rupees2(t.costs)} />
                            <Row label="Rules" planned={`${t.rulesTotal}/${t.rulesTotal}`} actual={`${t.rulesFollowed}/${t.rulesTotal}`} />
                          </div>
                        </div>
                        <div className="stack">
                          <span className="label">Notes on this trade</span>
                          {tn.length === 0 ? <p className="muted" style={{ margin: 0 }}>No notes on this trade yet.</p> : tn.map((n) => (
                            <div key={n.id} style={{ borderBottom: "1px solid var(--rule)", paddingBottom: 8 }}>
                              <div className="mono faint" style={{ fontSize: "var(--fs-1)" }}>{ts(n.createdAt)}</div>
                              <div style={{ whiteSpace: "pre-wrap" }}>{n.text}</div>
                              {n.flags.length > 0 && <div className="status--watch" style={{ fontSize: "var(--fs-1)", marginTop: 4 }}><span className="mono">{n.flags.join(", ")}</span> · {LEXICON_SENTENCE}</div>}
                            </div>
                          ))}
                          <NoteForm tradeId={t.id} />
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Row({ label, planned, actual }: { label: string; planned: string; actual: string }) {
  return (
    <div className="row row--tight" style={{ gridTemplateColumns: "110px 1fr 1fr" }}>
      <span className="label">{label}</span>
      <span className="fig"><span className="faint">planned </span>{planned}</span>
      <span className="fig"><span className="faint">actual </span>{actual}</span>
    </div>
  );
}
