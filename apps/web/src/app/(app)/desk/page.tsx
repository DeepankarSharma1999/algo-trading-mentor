import Link from "next/link";
import { PlainChip } from "@/components/Chip";
import { RuleTrace } from "@/components/RuleTrace";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { simTs } from "@/lib/format";
import type { Signal } from "@/lib/types";
import { stopWatching } from "./actions";
import { SignalActions } from "./SignalActions";

export const dynamic = "force-dynamic";

/** Watchers as rows; the latest signal as the one elevated rule trace. Everything here reads Postgres only. */
export default async function DeskPage() {
  const user = await requireUser();
  const watchers = await db.watcher.findMany({ where: { userId: user.id }, orderBy: { updatedAt: "desc" } });
  const strategies = await db.strategy.findMany({ where: { id: { in: watchers.map((w) => w.strategyId) } }, select: { id: true, name: true, status: true } });
  const nameOf = new Map(strategies.map((s) => [s.id, s.name]));
  const simNow = (await db.simClock.findFirst())?.now;
  // Signals dated after the simulated now come from a replayed loop of the feed; never show them as latest.
  const latest = await Promise.all(watchers.map((w) => db.signal.findFirst({ where: { watcherId: w.id, ...(simNow ? { ts: { lte: simNow } } : {}) }, orderBy: { ts: "desc" } })));
  const traces = watchers
    .map((w, i) => ({ watcher: w, row: latest[i], signal: latest[i]?.payload as Signal | undefined }))
    .filter((t): t is { watcher: (typeof watchers)[number]; row: NonNullable<(typeof latest)[number]>; signal: Signal } => !!t.row && !!t.signal);
  const [active, ...others] = traces;
  const mine = await db.strategy.findMany({ where: { userId: user.id }, select: { id: true, status: true } });
  const progress = { cloned: mine.length > 0, validated: mine.some((m) => m.status === "validated"), watching: watchers.length > 0 };

  return (
    <>
      <div className="page-head">
        <h1 className="h-display">Desk</h1>
        <span className="mono muted">{watchers.length} watcher{watchers.length === 1 ? "" : "s"}</span>
      </div>
      <p className="page-intro">Your strategies being paper-traded on the simulated feed, and the latest rule trace: what passed, what failed, and every gate with its reason. Nothing here is a recommendation; it is your own rules, evaluated.</p>

      {!progress.watching && (
        <div className="section">
          <span className="label">Start here</span>
          <ol className="steps" data-testid="getting-started">
            <li data-done={progress.cloned}><span><span className="steps__title">Clone a template or write a strategy</span><br /><span className="steps__hint">Templates exist to show the schema. You choose every instrument and every rule.</span></span><Link className="btn btn--sm" href="/library">Open Library</Link></li>
            <li data-done={progress.validated}><span><span className="steps__title">Validate it through the eight stages</span><br /><span className="steps__hint">The pipeline stops at the first failure and tells you the weakest gate in one sentence.</span></span><Link className="btn btn--sm" href="/builder">Open Builder</Link></li>
            <li data-done={progress.watching}><span><span className="steps__title">Watch it in paper mode</span><br /><span className="steps__hint">Only a validated, paper-only strategy can be watched. Its rule traces land here.</span></span><Link className="btn btn--sm" href="/builder">Choose a strategy</Link></li>
          </ol>
        </div>
      )}

      <div className="section">
        <span className="label">Watchers</span>
        <div className="ledger" data-testid="watchers">
          {watchers.length === 0 && (
            <div className="empty">
              <p>Nothing is being watched yet. Once a strategy is validated and set to paper-only, press <strong>Watch</strong> on it in the Builder and it appears here within one closed bar.</p>
              <Link className="btn" href="/builder">Go to the Builder</Link>
            </div>
          )}
          {watchers.map((w) => (
            <div className="row" key={w.id} data-testid="watcher-row">
              <span className="label" style={{ textTransform: "none", letterSpacing: 0 }}>{w.strategyId}</span>
              <span>
                <span>{nameOf.get(w.strategyId) ?? w.strategyId}</span>
                <span className="muted" style={{ display: "block", fontSize: "var(--fs-1)" }}>{w.stateReason || "No state reason yet."} <span className="mono faint">since {simTs(w.updatedAt)}</span></span>
              </span>
              <span className="cluster" style={{ gap: 10 }}>
                <PlainChip>{w.execState}</PlainChip>
                <form action={stopWatching}>
                  <input type="hidden" name="watcher_id" value={w.id} />
                  <button className="btn btn--sm btn--danger" title="Stops paper-trading this strategy. Closed trades stay in the Journal.">Stop watching</button>
                </form>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <span className="label">Latest signal</span>
        {!active ? (
          <div className="empty"><p>No signal has been evaluated yet. The rule trace appears here after the first closed bar a watcher evaluates. If the market is closed on the simulated clock, resume or speed it up in <Link href="/settings">Settings</Link>.</p></div>
        ) : (
          <div className="trace" data-testid="active-trace">
            <div className="spread"><span className="mono muted">{nameOf.get(active.watcher.strategyId) ?? active.watcher.strategyId}</span><span className="mono muted">{simTs(active.row.ts)}</span></div>
            <RuleTrace signal={active.signal} />
            <SignalActions signalId={active.signal.id} dbSignalId={active.row.id} verdict={active.signal.verdict} strategyId={active.signal.strategy_id} />
          </div>
        )}
        {others.length > 0 && (
          <div className="ledger" style={{ marginTop: 18 }}>
            {others.map((t) => (
              <details className="row row--wide" key={t.watcher.id} style={{ display: "block" }}>
                <summary className="spread" style={{ cursor: "pointer", listStyle: "none" }}>
                  <span className="mono">{t.watcher.strategyId} <span className="faint">{simTs(t.row.ts)}</span></span>
                  <span className={`status status--${t.signal.verdict}`}>{t.signal.verdict}</span>
                </summary>
                <p style={{ margin: "8px 0 0" }}>{t.signal.sentence}</p>
                <div style={{ marginTop: 12 }}><RuleTrace signal={t.signal} /></div>
              </details>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
