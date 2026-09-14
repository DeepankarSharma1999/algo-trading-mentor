"use client";
import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AUTOMATION_PERMISSIONS, INDICATORS, OPS, REGIMES, TIMEFRAMES, checkTestable, type Condition, type Input, type Strategy } from "@atm/schema";
import { PlainChip } from "@/components/Chip";
import { StrategyRules } from "@/components/StrategyRules";
import { watchBlockedReason } from "@/lib/strategies.pure";
import type { BacktestResult } from "@/lib/types";
import { formaliseAction, quickTest, requestValidation, saveSpecAction, watchForm } from "../actions";
import { QuickTest } from "./QuickTest";
import {
  INPUT_NAME_RE, INSTRUMENT_RE, MARKETS, OPERAND_HELP, OPS_HELP, PARAM_KEYS, PERMISSION_HELP, RISK_HELP, STOP_HELP, STOP_PARAM_KEYS, STOP_TYPES,
  TARGET_HELP, TARGET_TYPES, TIME_RE, TRAILING_HELP, TRAILING_PARAM_KEYS, TRAILING_TYPES, TRIGGER_HELP, TRIGGER_TYPES, indicatorHelp, operandsFor, type Indicator,
} from "../schemaMeta";

type Note = { kind: "plain" | "watch" | "blocked" | "eligible"; text: string };
type Params = Record<string, number | string>;
const asParams = (p: object | undefined): Params => (p ?? {}) as Params;

interface Props {
  initial: { id: string; version: number; parentId: string | null; status: string; spec: Strategy };
  notice: string | null;
  /** A `SECTION` key from `?section=`; that fold opens, scrolls under the sticky bar and takes focus on mount. */
  section?: string | null;
}

/** Section ids, in the order they appear. The testable verdict links each missing piece to the section that fixes it. */
const SECTION = { identity: "sec-identity", timeframe: "sec-timeframe", inputs: "sec-inputs", entry: "sec-entry", exits: "sec-exits", risk: "sec-risk" } as const;
const MISSING_SECTION: Record<string, string> = {
  entry: SECTION.entry, stop: SECTION.exits, exit: SECTION.exits, timeframe: SECTION.timeframe, session_start: SECTION.timeframe, session_end: SECTION.timeframe, ambiguity: SECTION.risk,
};
function openSection(id: string) {
  const el = document.getElementById(id) as HTMLDetailsElement | null;
  if (!el) return;
  el.open = true;
  el.scrollIntoView({ block: "start" });
  el.querySelector("summary")?.focus({ preventScroll: true });
}

const FORMALISE_EXAMPLE = "Example: On 15-minute bars of my own two symbols, go long when the close crosses above the 20 EMA while RSI(14) is above 50. Enter at the next bar open. Stop just below the signal bar. Take profit at 2R or exit at 15:15, whichever comes first. Risk half a percent per trade, at most three trades a day.";

/** Two-column ledger: the schema as folded, numbered sections on the left; the live testable verdict on the right. */
export function BuilderEditor({ initial, notice, section }: Props) {
  const router = useRouter();
  const [spec, setSpec] = useState<Strategy>(initial.spec);
  const [saved, setSaved] = useState<string>(() => JSON.stringify(initial.spec));
  const [status, setStatus] = useState(initial.status);
  const [note, setNote] = useState<Note | null>(notice ? { kind: notice.startsWith("Saved") ? "eligible" : "watch", text: notice } : null);
  const [pending, start] = useTransition();
  const [instrumentsText, setInstrumentsText] = useState(initial.spec.instruments.join(", "));
  const [formText, setFormText] = useState("");
  const [formalised, setFormalised] = useState<{ prose?: string; flags?: string[] } | null>(null);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});
  // Quick test: per-run client state. `specKey` is the spec the result came from, so a later edit reads as stale.
  const [quick, setQuick] = useState<{ result: BacktestResult | null; error: string | null; specKey: string | null }>({ result: null, error: null, specKey: null });
  const [testing, startTest] = useTransition();

  const verdict = useMemo(() => checkTestable(spec), [spec]);
  const operands = useMemo(() => operandsFor(spec.inputs), [spec.inputs]);
  const dirty = useMemo(() => JSON.stringify(spec) !== saved, [spec, saved]);
  const quickStale = useMemo(() => quick.specKey !== null && JSON.stringify(spec) !== quick.specKey, [spec, quick.specKey]);
  const patch = (p: Partial<Strategy>) => setSpec((s) => ({ ...s, ...p }));

  // Deep link from a validation finding: /builder/<id>?section=entry. Unknown keys do nothing.
  useEffect(() => {
    if (section && Object.prototype.hasOwnProperty.call(SECTION, section)) openSection(SECTION[section as keyof typeof SECTION]);
  }, [section]);

  const instrumentTokens = instrumentsText.split(",").map((t) => t.trim()).filter(Boolean);
  const badInstruments = instrumentTokens.filter((t) => !INSTRUMENT_RE.test(t));
  const badInputNames = Object.keys(spec.inputs).filter((n) => !INPUT_NAME_RE.test(n));
  const badTimes = [spec.session.start, spec.session.end, spec.time_exit.at_time ?? "09:15"].filter((t) => t && !TIME_RE.test(t));
  const formErrors = [
    ...(badInstruments.length ? [`Instruments must match A-Z 0-9 & - (1 to 20 characters): ${badInstruments.join(", ")}.`] : []),
    ...(badInputNames.length ? [`Input names must be lowercase letters, digits and underscores, starting with a letter: ${badInputNames.join(", ")}.`] : []),
    ...(badTimes.length ? [`Times must be HH:MM: ${badTimes.join(", ")}.`] : []),
    ...(spec.name.trim() ? [] : ["The strategy needs a name."]),
  ];
  const validateReason = !verdict.testable ? "Validate needs a testable strategy; the verdict on the right lists what is missing." : dirty ? "Save first; validation runs on the saved version." : status === "draft" ? "Save first." : null;
  const watchReason = watchBlockedReason(status, spec.automation_permission);
  const quickReason = !verdict.testable ? "Quick test needs a testable strategy." : null;
  const showWatch = status === "validated";

  const save = () => start(async () => {
    if (formErrors.length) { setNote({ kind: "blocked", text: formErrors.join(" ") }); return; }
    const r = await saveSpecAction(initial.id, spec);
    if (r.error) { setNote({ kind: "blocked", text: r.error }); return; }
    if (r.created && r.id) { router.push(`/builder/${r.id}?notice=${encodeURIComponent(`Saved as ${r.id} (untested): parameters changed on a validated strategy.`)}`); return; }
    setStatus(r.status ?? status); setSaved(JSON.stringify(spec)); setNote({ kind: "eligible", text: `Saved. Status is ${r.status}.` }); router.refresh();
  });
  const validate = () => start(async () => {
    const r = await requestValidation(initial.id);
    if (r.jobId) { router.push(`/validation/${r.jobId}`); return; }
    setNote({ kind: "watch", text: r.error ?? "Validation could not start." });
  });
  const runQuickTest = () => startTest(async () => {
    if (formErrors.length) { setQuick((q) => ({ ...q, error: formErrors.join(" ") })); return; }
    const key = JSON.stringify(spec);
    const r = await quickTest(spec);
    if ("error" in r) { setQuick((q) => ({ ...q, error: r.error })); return; }
    setQuick({ result: r, error: null, specKey: key });
  });
  const formalise = () => start(async () => {
    const r = await formaliseAction(formText);
    if (r.error || !r.draft) { setNote({ kind: "watch", text: r.error ?? "Mentor unavailable." }); return; }
    const d = r.draft;
    setSpec((s) => ({ ...s, ...d, strategy_id: s.strategy_id, version: s.version, parent_id: s.parent_id, name: d.name || s.name, ambiguity_flags: r.ambiguity_flags ?? d.ambiguity_flags ?? [] }));
    setInstrumentsText((d.instruments ?? []).join(", "));
    setFormalised({ prose: r.prose, flags: r.ambiguity_flags ?? [] });
    setNote({ kind: "plain", text: "The sections on the left now hold the formalised rules. Check every row, then Save." });
  });

  // ---- inputs -------------------------------------------------------------------------------------------
  const setInput = (name: string, inp: Input) => patch({ inputs: { ...spec.inputs, [name]: inp } });
  const renameInput = (from: string, to: string) => {
    if (from === to || !to) return;
    const next: Record<string, Input> = {};
    for (const [k, v] of Object.entries(spec.inputs)) next[k === from ? to : k] = v;
    patch({ inputs: next });
  };
  const removeInput = (name: string) => { const next = { ...spec.inputs }; delete next[name]; patch({ inputs: next }); };
  const addInput = () => {
    let n = 1; while (spec.inputs[`input${n}`]) n++;
    setInput(`input${n}`, { indicator: "ema", params: { ...PARAM_KEYS.ema } });
  };

  return (
    <>
      {/* ---------------------------------------------------------------- sticky primary actions */}
      <div className="sticky-actions" data-testid="editor-actions">
        <PlainChip>{status}</PlainChip>
        <button type="button" className="btn btn--primary" disabled={pending} onClick={save}>Save</button>
        <button type="button" className="btn" disabled={pending || !!validateReason} onClick={validate}>Validate</button>
        <button type="button" className="btn" disabled={testing || !!quickReason} onClick={runQuickTest} data-testid="quick-test-button">{testing ? "Testing…" : "Quick test"}</button>
        <span className="help" style={{ maxWidth: "26ch" }} data-testid="quick-test-help">{quickReason ?? "Runs on what you see, saved or not."}</span>
        {showWatch && (
          <form action={watchForm}>
            <input type="hidden" name="strategy_id" value={initial.id} /><input type="hidden" name="back" value={`/builder/${initial.id}`} />
            <button className="btn" disabled={pending || !!watchReason}>Watch</button>
          </form>
        )}
        {dirty && <span className="status status--watch" data-testid="unsaved">Unsaved changes</span>}
        <span className="help" style={{ marginLeft: "auto", textAlign: "right", maxWidth: "44ch" }}>
          {validateReason ? validateReason : showWatch && watchReason ? `Watch needs a paper-only permission; this one is ${spec.automation_permission}.` : "Testable and saved. Validate runs the pipeline."}
        </span>
      </div>
      {note && <p className={`notice ${note.kind === "plain" ? "" : `notice--${note.kind}`}`} role="status" data-testid="editor-notice">{note.text}</p>}

      <div className="twocol" style={{ marginTop: 18 }}>
        {/* ---------------------------------------------------------------- LEFT: the schema as folded sections */}
        <div>
          <Section id={SECTION.identity} title="1 Identity & market" open>
            <Field label="Name" htmlFor="f-name">
              <input id="f-name" className="input" value={spec.name} maxLength={80} onChange={(e) => patch({ name: e.target.value })} />
            </Field>
            <Field label="Market" htmlFor="f-market" help="NSE_EQ is cash equities; NSE_FO is futures and options.">
              <select id="f-market" className="input input--inline" value={spec.market} onChange={(e) => patch({ market: e.target.value as Strategy["market"] })}>{MARKETS.map((m) => <option key={m}>{m}</option>)}</select>
            </Field>
            <Field label="Instruments" htmlFor="f-instruments" help="Type each symbol yourself, comma-separated, e.g. RELIANCE, INFY. The mentor never suggests one.">
              <input id="f-instruments" className="input" value={instrumentsText} placeholder="RELIANCE, INFY" spellCheck={false}
                onChange={(e) => { const v = e.target.value.toUpperCase(); setInstrumentsText(v); patch({ instruments: v.split(",").map((t) => t.trim()).filter((t) => INSTRUMENT_RE.test(t)) }); }} />
              {badInstruments.length > 0 && <div className="field-error">Not a valid symbol: {badInstruments.join(", ")}. Allowed: A-Z, 0-9, &amp; and -, up to 20 characters.</div>}
            </Field>
          </Section>

          <Section id={SECTION.timeframe} title="2 Timeframe & session" open>
            <Field label="Timeframe" htmlFor="f-timeframe" help="The bar size every rule is read on. Conditions are checked once per closed bar.">
              <select id="f-timeframe" className="input input--inline" value={spec.timeframe} onChange={(e) => patch({ timeframe: e.target.value as Strategy["timeframe"] })}>{TIMEFRAMES.map((t) => <option key={t}>{t}</option>)}</select>
            </Field>
            <Field label="Session" help="Signals are only taken between these times (HH:MM, exchange time). NSE cash trades 09:15 to 15:30.">
              <span className="cluster">
                <label className="cluster" style={{ gap: 6 }}><span className="help">from</span>
                  <input className="input input--inline" style={{ width: 84 }} value={spec.session.start} placeholder="09:15" aria-label="session start" onChange={(e) => patch({ session: { ...spec.session, start: e.target.value } })} />
                </label>
                <label className="cluster" style={{ gap: 6 }}><span className="help">to</span>
                  <input className="input input--inline" style={{ width: 84 }} value={spec.session.end} placeholder="15:30" aria-label="session end" onChange={(e) => patch({ session: { ...spec.session, end: e.target.value } })} />
                </label>
                <label className="cluster" style={{ gap: 6 }}><input type="checkbox" checked={spec.session.flat_at_close} onChange={(e) => patch({ session: { ...spec.session, flat_at_close: e.target.checked } })} /> Flat at close</label>
              </span>
              {badTimes.length > 0 && <div className="field-error">Times must be HH:MM: {badTimes.join(", ")}.</div>}
              <div className="help help--tight">Flat at close exits any open position before the session ends, so nothing is held overnight.</div>
            </Field>
            <Field label="Regime affinity" help="Which market conditions this strategy is meant for. Informational: it groups the strategy and shows in the validation report; it does not gate signals.">
              <span className="cluster">
                {REGIMES.map((r) => (
                  <label key={r} className="cluster mono" style={{ gap: 6, fontSize: "var(--fs-1)" }}>
                    <input type="checkbox" checked={spec.regime_affinity.includes(r)} onChange={(e) => patch({ regime_affinity: e.target.checked ? [...spec.regime_affinity, r] : spec.regime_affinity.filter((x) => x !== r) })} /> {r}
                  </label>
                ))}
              </span>
            </Field>
          </Section>

          <Section id={SECTION.inputs} title="3 Inputs (indicators)" count={Object.keys(spec.inputs).length}>
            <p className="help" style={{ margin: "8px 0 0", maxWidth: "64ch" }}>
              An input is a named indicator computed on every bar. The name you give it becomes an operand in your conditions; indicators with several outputs are addressed as name.field, e.g. bb.upper or macd.hist.
            </p>
            {Object.entries(spec.inputs).map(([name, inp]) => (
              <Field key={name} label={<code>{name}</code>} help={indicatorHelp(name, inp.indicator)}>
                <div className="stack">
                  <span className="cluster">
                    <label className="stack" style={{ gap: 2 }}><span className="help">Name</span>
                      <input className="input input--inline" style={{ width: 130 }} defaultValue={name} spellCheck={false} onBlur={(e) => renameInput(name, e.target.value.trim())} />
                    </label>
                    <label className="stack" style={{ gap: 2 }}><span className="help">Indicator</span>
                      <select className="input input--inline" value={inp.indicator} onChange={(e) => { const ind = e.target.value as Indicator; setInput(name, { indicator: ind, params: { ...PARAM_KEYS[ind] } }); }}>
                        {INDICATORS.map((i) => <option key={i}>{i}</option>)}
                      </select>
                    </label>
                    <span className="stack" style={{ gap: 2 }}><span className="help">&nbsp;</span>
                      <button type="button" className="btn" onClick={() => removeInput(name)}>Remove</button>
                    </span>
                  </span>
                  <ParamsEditor params={asParams(inp.params)} suggested={PARAM_KEYS[inp.indicator]} onChange={(p) => setInput(name, { ...inp, params: p })} />
                </div>
              </Field>
            ))}
            {badInputNames.length > 0 && <div className="field-error" style={{ padding: "6px 0" }}>Input names must be lowercase letters, digits and underscores, starting with a letter: {badInputNames.join(", ")}.</div>}
            <div style={{ padding: "10px 0" }}>
              <button type="button" className="btn" onClick={addInput}>Add input</button>
              {Object.keys(spec.inputs).length === 0 && <span className="help" style={{ marginLeft: 10 }}>Without an input, conditions can only compare bar fields and numbers.</span>}
            </div>
          </Section>

          <Section id={SECTION.entry} title="4 Entry conditions" count={spec.entry_long.length + (spec.entry_short?.length ?? 0)}>
            <p className="help" style={{ margin: "8px 0 0", maxWidth: "64ch" }}>{OPS_HELP}</p>
            <Field label="Long when" help="Every condition in the list must hold on the same closed bar. Leave empty for a short-only strategy.">
              <ConditionList list={spec.entry_long} operands={operands} onChange={(l) => patch({ entry_long: l })} />
            </Field>
            <Field label="Short when" help="Leave empty for a long-only strategy.">
              <ConditionList list={spec.entry_short ?? []} operands={operands} onChange={(l) => patch({ entry_short: l.length ? l : null })} />
            </Field>
          </Section>

          <Section id={SECTION.exits} title="5 Trigger, stop and exits">
            <Field label="Trigger" htmlFor="f-trigger" help={TRIGGER_HELP[spec.trigger.type]}>
              <span className="cluster">
                <select id="f-trigger" className="input input--inline" value={spec.trigger.type} onChange={(e) => patch({ trigger: { ...spec.trigger, type: e.target.value as Strategy["trigger"]["type"] } })}>{TRIGGER_TYPES.map((t) => <option key={t}>{t}</option>)}</select>
                <label className="cluster" style={{ gap: 6 }}><span className="help">offset_pct</span>
                  <input className="input input--inline" style={{ width: 84 }} type="number" inputMode="decimal" step="0.01" value={spec.trigger.offset_pct ?? ""} placeholder="none" onChange={(e) => { const t = { ...spec.trigger }; if (e.target.value === "") delete t.offset_pct; else t.offset_pct = Number(e.target.value); patch({ trigger: t }); }} />
                </label>
              </span>
            </Field>
            <Field label="Stop" htmlFor="f-stop" help={spec.stop ? STOP_HELP[spec.stop.type] : "Required. Where the trade is wrong and gets closed. Every strategy needs one before it is testable."}>
              <div className="stack">
                <select id="f-stop" className="input input--inline" value={spec.stop?.type ?? ""} onChange={(e) => { const t = e.target.value as (typeof STOP_TYPES)[number] | ""; patch({ stop: t ? { type: t, params: { ...STOP_PARAM_KEYS[t] } } : null }); }}>
                  <option value="">none yet</option>{STOP_TYPES.map((t) => <option key={t}>{t}</option>)}
                </select>
                {spec.stop && <ParamsEditor params={asParams(spec.stop.params)} suggested={STOP_PARAM_KEYS[spec.stop.type]} onChange={(p) => patch({ stop: { ...spec.stop!, params: p } })} />}
              </div>
            </Field>
            <Field label="Targets" help="Where profit is taken. At least one exit is required: a target, a trailing rule or a time exit.">
              <div className="stack">
                {spec.targets.map((t, i) => (
                  <div key={i}>
                    <span className="cluster">
                      <label className="stack" style={{ gap: 2 }}><span className="help">Type</span>
                        <select className="input input--inline" value={t.type} onChange={(e) => patch({ targets: spec.targets.map((x, j) => j === i ? { ...x, type: e.target.value as typeof x.type } : x) })}>{TARGET_TYPES.map((x) => <option key={x}>{x}</option>)}</select>
                      </label>
                      <label className="stack" style={{ gap: 2 }}><span className="help">Value</span>
                        <input className="input input--inline" style={{ width: 90 }} type="number" inputMode="decimal" step="0.1" value={t.value} onChange={(e) => patch({ targets: spec.targets.map((x, j) => j === i ? { ...x, value: Number(e.target.value) } : x) })} />
                      </label>
                      {t.type === "indicator" && (
                        <label className="stack" style={{ gap: 2 }}><span className="help">Input (ref)</span>
                          <input className="input input--inline" style={{ width: 130 }} list="operands" placeholder="e.g. bb.upper" value={t.ref ?? ""} onChange={(e) => patch({ targets: spec.targets.map((x, j) => j === i ? { ...x, ref: e.target.value } : x) })} />
                        </label>
                      )}
                      <span className="stack" style={{ gap: 2 }}><span className="help">&nbsp;</span>
                        <button type="button" className="btn" onClick={() => patch({ targets: spec.targets.filter((_, j) => j !== i) })}>Remove</button>
                      </span>
                    </span>
                    <div className="help help--tight">{TARGET_HELP[t.type]}</div>
                  </div>
                ))}
                <span><button type="button" className="btn" onClick={() => patch({ targets: [...spec.targets, { type: "rr", value: 2 }] })}>Add target</button></span>
              </div>
            </Field>
            <Field label="Trailing stop" htmlFor="f-trailing" help={TRAILING_HELP[spec.trailing.type]}>
              <div className="stack">
                <select id="f-trailing" className="input input--inline" value={spec.trailing.type} onChange={(e) => { const t = e.target.value as (typeof TRAILING_TYPES)[number]; patch({ trailing: { type: t, params: { ...TRAILING_PARAM_KEYS[t] } } }); }}>{TRAILING_TYPES.map((t) => <option key={t}>{t}</option>)}</select>
                {spec.trailing.type !== "none" && <ParamsEditor params={asParams(spec.trailing.params)} suggested={TRAILING_PARAM_KEYS[spec.trailing.type]} onChange={(p) => patch({ trailing: { ...spec.trailing, params: p } })} />}
              </div>
            </Field>
            <Field label="Time exit" help="Close the trade after a number of bars, at a clock time, or both. Leave both empty for none.">
              <span className="cluster">
                <label className="cluster" style={{ gap: 6 }}><span className="help">After (bars)</span>
                  <input className="input input--inline" style={{ width: 84 }} type="number" inputMode="numeric" min={1} step={1} value={spec.time_exit.max_bars ?? ""} placeholder="none" onChange={(e) => { const t = { ...spec.time_exit }; if (e.target.value === "") delete t.max_bars; else t.max_bars = Math.max(1, Math.floor(Number(e.target.value))); patch({ time_exit: t }); }} />
                </label>
                <label className="cluster" style={{ gap: 6 }}><span className="help">At time (HH:MM)</span>
                  <input className="input input--inline" style={{ width: 84 }} placeholder="15:15" value={spec.time_exit.at_time ?? ""} onChange={(e) => { const t = { ...spec.time_exit }; if (e.target.value === "") delete t.at_time; else t.at_time = e.target.value; patch({ time_exit: t }); }} />
                </label>
              </span>
            </Field>
          </Section>

          <Section id={SECTION.risk} title="6 Risk & permission" count={spec.ambiguity_flags.length || undefined}>
            <Field label="Min R:R after costs" htmlFor="f-rr" help={RISK_HELP.min_rr_after_costs}>
              <NumInput id="f-rr" value={spec.risk.min_rr_after_costs} step={0.1} min={0} onChange={(v) => patch({ risk: { ...spec.risk, min_rr_after_costs: v } })} />
            </Field>
            <Field label="Max equity risk %" htmlFor="f-risk-pct" help={RISK_HELP.max_equity_risk_pct}>
              <NumInput id="f-risk-pct" value={spec.risk.max_equity_risk_pct} step={0.05} min={0} max={1} onChange={(v) => patch({ risk: { ...spec.risk, max_equity_risk_pct: v } })} />
            </Field>
            <Field label="Max trades per day" htmlFor="f-max-trades" help={RISK_HELP.max_trades_per_day}>
              <NumInput id="f-max-trades" value={spec.risk.max_trades_per_day} step={1} min={1} integer onChange={(v) => patch({ risk: { ...spec.risk, max_trades_per_day: Math.max(1, Math.floor(v)) } })} />
            </Field>
            <Field label="Automation permission" htmlFor="f-permission" help={`${PERMISSION_HELP[spec.automation_permission]} There is no live trading anywhere in this product.`}>
              <select id="f-permission" className="input input--inline" value={spec.automation_permission} onChange={(e) => patch({ automation_permission: e.target.value as Strategy["automation_permission"] })}>{AUTOMATION_PERMISSIONS.map((p) => <option key={p}>{p}</option>)}</select>
              <dl className="glossary" style={{ margin: "8px 0 0" }}>
                {AUTOMATION_PERMISSIONS.map((p) => <div key={p}><dt style={{ marginTop: 6, fontSize: "var(--fs-1)" }}>{p}</dt><dd className="help">{PERMISSION_HELP[p]}</dd></div>)}
              </dl>
            </Field>
            <Field label="Ambiguity flags" help="Set by the mentor when a rule could be read two ways. Each one blocks testable until you write, in your own words, how your rule settles it, then press Resolve.">
              {spec.ambiguity_flags.length === 0 ? <span className="muted">None.</span> : (
                <div className="stack">
                  {spec.ambiguity_flags.map((f, i) => (
                    <div key={`${i}-${f}`}>
                      <div className="mono" style={{ fontSize: "var(--fs-1)" }}>{f}</div>
                      <span className="cluster" style={{ marginTop: 4 }}>
                        <input className="input" style={{ maxWidth: 420 }} placeholder="One line on how your rule settles this" aria-label={`Resolution for: ${f}`} value={resolutions[f] ?? ""} onChange={(e) => setResolutions({ ...resolutions, [f]: e.target.value })} />
                        <button type="button" className="btn" disabled={!(resolutions[f] ?? "").trim()} title={(resolutions[f] ?? "").trim() ? "Remove this flag" : "Type a one-line resolution first"} onClick={() => patch({ ambiguity_flags: spec.ambiguity_flags.filter((_, j) => j !== i) })}>Resolve</button>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Field>
            <Field label="Version locked" help="Set once a version has been validated. A locked version is never edited in place; saving creates the next version.">
              <span className="mono">{spec.version_locked ? "yes" : "no"}</span>
            </Field>
          </Section>
          <datalist id="operands">{operands.map((o) => <option key={o} value={o} />)}</datalist>
        </div>

        {/* ---------------------------------------------------------------- RIGHT: the verdict */}
        <div>
          <div className="section" style={{ marginTop: 0 }}>
            <span className="label">Testable</span>
            <div style={{ padding: "12px 0" }}>
              <span className={`status ${verdict.testable ? "status--eligible" : "status--blocked"}`} style={{ fontSize: "var(--fs-3)" }} data-testid="testable-verdict">{verdict.testable ? "TESTABLE" : "NOT TESTABLE"}</span>
              {!verdict.testable && (
                <>
                  <p className="help" style={{ margin: "8px 0 4px" }}>Still missing. Each line opens the section that fixes it.</p>
                  <ul style={{ margin: 0, padding: 0, listStyle: "none" }} data-testid="missing">
                    {verdict.missing.map((m, i) => {
                      const target = MISSING_SECTION[verdict.missing_ids[i]] ?? SECTION.identity;
                      return (
                        <li key={m} style={{ padding: "4px 0", borderBottom: "1px solid var(--rule)" }}>
                          <button type="button" className="mono" style={{ background: "none", border: 0, padding: 0, color: "var(--accent)", font: "inherit", fontFamily: "var(--font-mono)", fontSize: "var(--fs-1)", textAlign: "left", cursor: "pointer" }} onClick={() => openSection(target)}>
                            <span className="gate gate--fail" aria-hidden="true" />{m}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
              {verdict.testable && <p className="muted" style={{ margin: "8px 0 0" }}>Every required piece is present. {dirty ? "Save, then Validate." : status === "validated" ? "This version has been validated." : "Validate when ready."}</p>}
            </div>
          </div>

          <QuickTest result={quick.result} error={quick.error} stale={quickStale} pending={testing} />

          <div className="section">
            <span className="label">Version</span>
            <div className="ledger">
              <div className="row row--tight"><span className="label">id</span><span /><span className="value value--fig">{initial.id}</span></div>
              <div className="row row--tight"><span className="label">version</span><span /><span className="value value--fig">{initial.version}</span></div>
              <div className="row row--tight"><span className="label">parent_id</span><span /><span className="value value--fig">{initial.parentId ?? "–"}</span></div>
              <div className="row row--tight"><span className="label">status</span><span /><span><PlainChip>{status}</PlainChip></span></div>
            </div>
            {(status === "validated" || spec.version_locked) && <p className="help" style={{ marginTop: 10 }}>This version is {status === "validated" ? "validated" : "locked"}: saving any change creates the next version, marked untested, and leaves this one as it is.</p>}
          </div>

          <div className="section">
            <span className="label">As sentences</span>
            <p className="help" style={{ margin: "6px 0 0" }}>The spec on the left, read back in plain words. Check it says what you mean.</p>
            <div style={{ paddingTop: 10 }}><StrategyRules spec={spec} /></div>
          </div>

          <div className="section">
            <span className="label">Formalise from text</span>
            <p className="muted" style={{ margin: "8px 0" }}>Write your rules in your own words. The mentor turns them into a draft that replaces the sections on the left.</p>
            <label className="stack" htmlFor="f-formalise" style={{ display: "block" }}>
              <span className="label">Your rules</span>
              <textarea id="f-formalise" className="input" value={formText} onChange={(e) => setFormText(e.target.value)} placeholder={FORMALISE_EXAMPLE} rows={6} />
            </label>
            <p className="help help--tight">The mentor drafts the schema and lists every ambiguity; it never picks instruments.</p>
            <div className="cluster" style={{ marginTop: 8 }}>
              <button type="button" className="btn" disabled={pending || !formText.trim()} onClick={formalise}>Formalise</button>
              {!formText.trim() && <span className="help">Write the rules first.</span>}
            </div>
            {formalised?.prose && <p className="notice" data-testid="formalise-prose">{formalised.prose}</p>}
            {formalised && formalised.flags && formalised.flags.length > 0 && (
              <>
                <p className="help" style={{ margin: "8px 0 4px" }}>Ambiguities the mentor found. Resolve each one in section 6.</p>
                <ul className="mono" style={{ margin: 0, paddingLeft: 18, fontSize: "var(--fs-1)" }}>{formalised.flags.map((f, i) => <li key={i}>{f}</li>)}</ul>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// ---- small pieces -------------------------------------------------------------------------------------------

/** A numbered, collapsible section of the schema. `open` sets the initial state only; the verdict links can open it later. */
function Section({ id, title, count, open, children }: { id: string; title: string; count?: number; open?: boolean; children: React.ReactNode }) {
  return (
    <details className="fold" id={id} open={open} style={{ marginTop: 14, scrollMarginTop: "calc(var(--strip-h) + 72px)" }}>
      <summary>
        <span style={{ fontSize: "var(--fs-3)" }}>{title}{count !== undefined && <span className="mono muted" style={{ fontSize: "var(--fs-1)", marginLeft: 8 }}>{count}</span>}</span>
      </summary>
      <div className="ledger">{children}</div>
    </details>
  );
}

function Field({ label, htmlFor, help, children }: { label: React.ReactNode; htmlFor?: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="row row--wide">
      {htmlFor ? <label className="label" htmlFor={htmlFor}>{label}</label> : <span className="label">{label}</span>}
      <div className="value">
        {children}
        {help && <div className="help help--tight">{help}</div>}
      </div>
    </div>
  );
}

function NumInput({ id, value, step, min, max, integer, onChange }: { id?: string; value: number; step: number; min?: number; max?: number; integer?: boolean; onChange: (v: number) => void }) {
  return (
    <input id={id} className="input input--inline" style={{ width: 110 }} type="number" inputMode={integer ? "numeric" : "decimal"} step={step} min={min} max={max} value={Number.isFinite(value) ? value : ""} onChange={(e) => onChange(Number(e.target.value))} />
  );
}

/** key=value editor. Suggested keys appear first; existing keys are kept. Numeric text becomes a number. */
function ParamsEditor({ params, suggested, onChange }: { params: Params; suggested: Record<string, number | string>; onChange: (p: Params) => void }) {
  const keys = Array.from(new Set([...Object.keys(suggested), ...Object.keys(params)]));
  if (keys.length === 0) return <span className="help">No parameters.</span>;
  return (
    <span className="cluster">
      {keys.map((k) => (
        <label key={k} className="cluster mono" style={{ gap: 6, fontSize: "var(--fs-1)" }}>{k}=
          <input className="input input--inline" style={{ width: 96 }} inputMode={k === "ref" ? undefined : "decimal"} list={k === "ref" ? "operands" : undefined} value={params[k] ?? ""} spellCheck={false} aria-label={k} onChange={(e) => onChange({ ...params, [k]: parseOperand(e.target.value) })} />
        </label>
      ))}
    </span>
  );
}

const parseOperand = (v: string): string | number => (v.trim() !== "" && !Number.isNaN(Number(v)) ? Number(v) : v);

function ConditionList({ list, operands, onChange }: { list: Condition[]; operands: string[]; onChange: (l: Condition[]) => void }) {
  const set = (i: number, c: Condition) => onChange(list.map((x, j) => (j === i ? c : x)));
  return (
    <div className="stack">
      {list.map((c, i) => (
        <span className="cluster" key={i} data-testid="condition">
          <label className="stack" style={{ gap: 2 }}><span className="help">Left</span>
            <input className="input input--inline" style={{ width: 130 }} list="operands" value={String(c.lhs)} spellCheck={false} onChange={(e) => set(i, { ...c, lhs: parseOperand(e.target.value) })} />
          </label>
          <label className="stack" style={{ gap: 2 }}><span className="help">Op</span>
            <select className="input input--inline" value={c.op} onChange={(e) => set(i, { ...c, op: e.target.value as Condition["op"] })}>{OPS.map((o) => <option key={o}>{o}</option>)}</select>
          </label>
          <label className="stack" style={{ gap: 2 }}><span className="help">Right</span>
            <input className="input input--inline" style={{ width: 130 }} list="operands" value={String(c.rhs)} spellCheck={false} onChange={(e) => set(i, { ...c, rhs: parseOperand(e.target.value) })} />
          </label>
          <label className="stack" style={{ gap: 2 }}><span className="help">Lookback (bars)</span>
            <input className="input input--inline" style={{ width: 84 }} type="number" inputMode="numeric" min={1} step={1} value={c.lookback ?? ""} placeholder="none" onChange={(e) => { const n = { ...c }; if (e.target.value === "") delete n.lookback; else n.lookback = Math.max(1, Math.floor(Number(e.target.value))); set(i, n); }} />
          </label>
          <span className="stack" style={{ gap: 2 }}><span className="help">&nbsp;</span>
            <button type="button" className="btn" onClick={() => onChange(list.filter((_, j) => j !== i))}>Remove</button>
          </span>
        </span>
      ))}
      {list.length > 0 && <span className="help">{OPERAND_HELP} Lookback only matters for rising and falling.</span>}
      <span><button type="button" className="btn" onClick={() => onChange([...list, { lhs: "close", op: ">", rhs: operands.find((o) => !["open", "high", "low", "close", "volume"].includes(o)) ?? "open" }])}>Add condition</button></span>
      {operands.length <= 5 && <span className="help">Add an input in section 3 to reference an indicator here; bar fields are open, high, low, close, volume.</span>}
    </div>
  );
}
