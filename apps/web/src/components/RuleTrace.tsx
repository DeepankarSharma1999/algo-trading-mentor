import { num, pct, rupees2 } from "@/lib/format";
import type { Signal } from "@/lib/types";

const VERDICT_CLASS = { eligible: "status--eligible", watch: "status--watch", blocked: "status--blocked" } as const;

/**
 * A signal rendered as a rule trace: the sentence, the conditions checklist, the figures ledger, the gate
 * list (square gates, red ones carry their reason) and the verdict. The caller decides whether it sits inside
 * the one elevated `.trace` panel. Server-safe.
 */
export function RuleTrace({ signal, compact = false }: { signal: Signal; compact?: boolean }) {
  const verdict = signal.verdict ?? "watch";
  return (
    <div data-testid="rule-trace" data-verdict={verdict}>
      <div className="spread">
        <span className="mono muted">{signal.strategy_id} · {signal.symbol} · {signal.regime} · {signal.side ?? "no side"}</span>
        <span className={`status ${VERDICT_CLASS[verdict]}`}>{verdict}</span>
      </div>
      <p style={{ fontSize: "var(--fs-3)", margin: "10px 0 0", maxWidth: 760 }}>{signal.sentence}</p>

      {!compact && (
        <>
          <div className="section" style={{ marginTop: 20 }}>
            <span className="label">Conditions</span>
            <div className="ledger">
              {signal.conditions_passed.map((c) => <div className="gate-line" key={`p-${c}`}><span className="gate gate--pass" aria-label="passed" /><span>{c}</span></div>)}
              {signal.conditions_failed.map((c) => <div className="gate-line" key={`f-${c}`}><span className="gate gate--fail" aria-label="failed" /><span>{c}</span></div>)}
              {!signal.conditions_passed.length && !signal.conditions_failed.length && <div className="gate-line muted">No conditions evaluated on this bar.</div>}
            </div>
          </div>

          <div className="section" style={{ marginTop: 20 }}>
            <span className="label">Figures</span>
            <div className="ledger">
              <Fig label="Trigger" value={`${signal.trigger?.type ?? "–"}${signal.trigger?.price != null ? ` @ ${num(signal.trigger.price)}` : ""}`} note={signal.trigger?.description} />
              <Fig label="Stop" value={signal.stop == null ? "–" : num(signal.stop)} />
              <Fig label="Targets" value={signal.targets?.length ? signal.targets.map((t) => num(t)).join(" / ") : "–"} />
              <Fig label="Quantity" value={String(signal.quantity ?? "–")} />
              <Fig label="Rupee risk" value={rupees2(signal.rupee_risk)} />
              <Fig label="Portfolio risk" value={pct(signal.portfolio_risk_pct, 2)} />
              <Fig label="Estimated costs" value={rupees2(signal.estimated_costs)} />
              <Fig label="Post-cost R:R" value={signal.post_cost_rr == null ? "–" : num(signal.post_cost_rr)} />
            </div>
          </div>

          <div className="section" style={{ marginTop: 20 }}>
            <span className="label">Gates</span>
            <div className="ledger">
              {signal.gates.map((g) => (
                <div className="gate-line" key={g.name}>
                  <span className={`gate ${g.pass ? "gate--pass" : "gate--fail"}`} aria-label={g.pass ? "pass" : "fail"} />
                  <span>{g.name}</span>
                  {!g.pass && <span className="why">{g.reason ?? "Gate did not pass."}</span>}
                </div>
              ))}
            </div>
            {signal.ambiguity_flags?.length > 0 && (
              <p className="muted" style={{ marginTop: 8 }}>Ambiguity flags: {signal.ambiguity_flags.map((f, i) => <code key={i}>{i > 0 ? "; " : ""}{f}</code>)}</p>
            )}
          </div>

          <div className="spread" style={{ marginTop: 18 }}>
            <span className="label">Verdict</span>
            <span className={`status ${VERDICT_CLASS[verdict]}`} data-testid="verdict">{verdict}</span>
          </div>
        </>
      )}
    </div>
  );
}

function Fig({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="row row--tight">
      <span className="label">{label}</span>
      <span className="muted" style={{ fontSize: "var(--fs-1)" }}>{note ?? ""}</span>
      <span className="value value--fig">{value}</span>
    </div>
  );
}
