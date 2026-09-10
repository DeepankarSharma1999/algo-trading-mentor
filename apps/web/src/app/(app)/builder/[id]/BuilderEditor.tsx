"use client";
import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AUTOMATION_PERMISSIONS, INDICATORS, OPS, REGIMES, TIMEFRAMES, checkTestable, type Condition, type Input, type Strategy } from "@atm/schema";
import { PlainChip } from "@/components/Chip";
import { StrategyRules } from "@/components/StrategyRules";
import { formaliseAction, requestValidation, saveSpecAction } from "../actions";
import { INPUT_NAME_RE, INSTRUMENT_RE, MARKETS, PARAM_KEYS, STOP_PARAM_KEYS, STOP_TYPES, TARGET_TYPES, TIME_RE, TRAILING_PARAM_KEYS, TRAILING_TYPES, TRIGGER_TYPES, operandsFor, type Indicator } from "../schemaMeta";

type Note = { kind: "plain" | "watch" | "blocked" | "eligible"; text: string };
type Params = Record<string, number | string>;
const asParams = (p: object | undefined): Params => (p ?? {}) as Params;

interface Props {
  initial: { id: string; version: number; parentId: string | null; status: string; spec: Strategy };
  notice: string | null;
}

/** Two-column ledger: the schema as editable rows on the left, the live testable verdict on the right. */
export function BuilderEditor({ initial, notice }: Props) {
  const router = useRouter();
  const [spec, setSpec] = useState<Strategy>(initial.spec);
  const [status, setStatus] = useState(initial.status);
  const [dirty, setDirty] = useState(false);
  const [note, setNote] = useState<Note | null>(notice ? { kind: "watch", text: notice } : null);
  const [pending, start] = useTransition();
  const [instrumentsText, setInstrumentsText] = useState(initial.spec.instruments.join(", "));
  const [formText, setFormText] = useState("");
  const [formalised, setFormalised] = useState<{ prose?: string; flags?: string[] } | null>(null);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});

  const verdict = useMemo(() => checkTestable(spec), [spec]);
  const operands = useMemo(() => operandsFor(spec.inputs), [spec.inputs]);
  const patch = (p: Partial<Strategy>) => { setSpec((s) => ({ ...s, ...p })); setDirty(true); };

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
  const validateReason = !verdict.testable ? "Not testable yet; the verdict lists what is missing." : dirty ? "Save first; validation runs on the saved version." : status === "draft" ? "Save first." : null;

  const save = () => start(async () => {
    if (formErrors.length) { setNote({ kind: "blocked", text: formErrors.join(" ") }); return; }
    const r = await saveSpecAction(initial.id, spec);
    if (r.error) { setNote({ kind: "blocked", text: r.error }); return; }
    if (r.created && r.id) { router.push(`/builder/${r.id}?notice=${encodeURIComponent(`Saved as ${r.id} (untested).`)}`); return; }
    setStatus(r.status ?? status); setDirty(false); setNote({ kind: "eligible", text: `Saved. Status is ${r.status}.` }); router.refresh();
  });
  const validate = () => start(async () => {
    const r = await requestValidation(initial.id);
    if (r.jobId) { router.push(`/validation/${r.jobId}`); return; }
    setNote({ kind: "watch", text: r.error ?? "Validation could not start." });
  });
  const formalise = () => start(async () => {
    const r = await formaliseAction(formText);
    if (r.error || !r.draft) { setNote({ kind: "watch", text: r.error ?? "Mentor unavailable." }); return; }
    const d = r.draft;
    setSpec((s) => ({ ...s, ...d, strategy_id: s.strategy_id, version: s.version, parent_id: s.parent_id, name: d.name || s.name, ambiguity_flags: r.ambiguity_flags ?? d.ambiguity_flags ?? [] }));
    setInstrumentsText((d.instruments ?? []).join(", "));
    setDirty(true);
    setFormalised({ prose: r.prose, flags: r.ambiguity_flags ?? [] });
    setNote({ kind: "plain", text: "The draft on the left now holds the formalised rules. Check every row, then Save." });
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
    <div className="twocol">
      {/* ---------------------------------------------------------------- LEFT: the schema as rows */}
      <div>
        <div className="section" style={{ marginTop: 0 }}>
          <span className="label">Identity</span>
          <div className="ledger">
            <Row label="Name"><input className="input" value={spec.name} maxLength={80} onChange={(e) => patch({ name: e.target.value })} /></Row>
            <Row label="Market">
              <select className="input input--inline" value={spec.market} onChange={(e) => patch({ market: e.target.value as Strategy["market"] })}>{MARKETS.map((m) => <option key={m}>{m}</option>)}</select>
            </Row>
            <Row label="Instruments" hint="Comma-separated symbols, in capitals. You type every symbol; nothing is suggested.">
              <input className="input" value={instrumentsText} placeholder="e.g. your own symbols, separated by commas" spellCheck={false}
                onChange={(e) => { const v = e.target.value.toUpperCase(); setInstrumentsText(v); patch({ instruments: v.split(",").map((t) => t.trim()).filter((t) => INSTRUMENT_RE.test(t)) }); }} />
              {badInstruments.length > 0 && <div className="field-error">Not a valid symbol: {badInstruments.join(", ")}. Allowed: A-Z, 0-9, &amp; and -, up to 20 characters.</div>}
            </Row>
            <Row label="Timeframe">
              <select className="input input--inline" value={spec.timeframe} onChange={(e) => patch({ timeframe: e.target.value as Strategy["timeframe"] })}>{TIMEFRAMES.map((t) => <option key={t}>{t}</option>)}</select>
            </Row>
            <Row label="Session">
              <span className="cluster">
                <input className="input input--inline" style={{ width: 80 }} value={spec.session.start} placeholder="09:15" onChange={(e) => patch({ session: { ...spec.session, start: e.target.value } })} />
                <span className="muted">to</span>
                <input className="input input--inline" style={{ width: 80 }} value={spec.session.end} placeholder="15:30" onChange={(e) => patch({ session: { ...spec.session, end: e.target.value } })} />
                <label className="cluster" style={{ gap: 6 }}><input type="checkbox" checked={spec.session.flat_at_close} onChange={(e) => patch({ session: { ...spec.session, flat_at_close: e.target.checked } })} /> flat at close</label>
              </span>
            </Row>
            <Row label="Regime affinity">
              <span className="cluster">
                {REGIMES.map((r) => (
                  <label key={r} className="cluster mono" style={{ gap: 6, fontSize: "var(--fs-1)" }}>
                    <input type="checkbox" checked={spec.regime_affinity.includes(r)} onChange={(e) => patch({ regime_affinity: e.target.checked ? [...spec.regime_affinity, r] : spec.regime_affinity.filter((x) => x !== r) })} /> {r}
                  </label>
                ))}
              </span>
            </Row>
          </div>
        </div>

        <div className="section">
          <span className="label">Inputs</span>
          <div className="ledger">
            {Object.entries(spec.inputs).map(([name, inp]) => (
              <Row key={name} label={<code>{name}</code>}>
                <div className="stack">
                  <span className="cluster">
                    <input className="input input--inline" style={{ width: 120 }} defaultValue={name} spellCheck={false} onBlur={(e) => renameInput(name, e.target.value.trim())} aria-label="input name" />
                    <select className="input input--inline" value={inp.indicator} onChange={(e) => { const ind = e.target.value as Indicator; setInput(name, { indicator: ind, params: { ...PARAM_KEYS[ind] } }); }}>
                      {INDICATORS.map((i) => <option key={i}>{i}</option>)}
                    </select>
                    <button type="button" className="btn btn--sm" onClick={() => removeInput(name)}>Remove</button>
                  </span>
                  <ParamsEditor params={asParams(inp.params)} suggested={PARAM_KEYS[inp.indicator]} onChange={(p) => setInput(name, { ...inp, params: p })} />
                </div>
              </Row>
            ))}
            {badInputNames.length > 0 && <div className="field-error" style={{ padding: "6px 0" }}>Input names must be lowercase letters, digits and underscores, starting with a letter: {badInputNames.join(", ")}.</div>}
            <div style={{ padding: "8px 0" }}><button type="button" className="btn btn--sm" onClick={addInput}>Add input</button></div>
          </div>
        </div>

        <div className="section">
          <span className="label">Entry</span>
          <div className="ledger">
            <Row label="Long when" hint="Every condition must hold on the closed bar.">
              <ConditionList list={spec.entry_long} operands={operands} onChange={(l) => patch({ entry_long: l })} />
            </Row>
            <Row label="Short when" hint="Leave empty for a long-only strategy.">
              <ConditionList list={spec.entry_short ?? []} operands={operands} onChange={(l) => patch({ entry_short: l.length ? l : null })} />
            </Row>
          </div>
        </div>

        <div className="section">
          <span className="label">Execution</span>
          <div className="ledger">
            <Row label="Trigger">
              <span className="cluster">
                <select className="input input--inline" value={spec.trigger.type} onChange={(e) => patch({ trigger: { ...spec.trigger, type: e.target.value as Strategy["trigger"]["type"] } })}>{TRIGGER_TYPES.map((t) => <option key={t}>{t}</option>)}</select>
                <label className="cluster mono" style={{ gap: 6, fontSize: "var(--fs-1)" }}>offset_pct
                  <input className="input input--inline" style={{ width: 80 }} type="number" step="0.01" value={spec.trigger.offset_pct ?? ""} onChange={(e) => { const t = { ...spec.trigger }; if (e.target.value === "") delete t.offset_pct; else t.offset_pct = Number(e.target.value); patch({ trigger: t }); }} />
                </label>
              </span>
            </Row>
            <Row label="Stop">
              <div className="stack">
                <select className="input input--inline" value={spec.stop?.type ?? ""} onChange={(e) => { const t = e.target.value as (typeof STOP_TYPES)[number] | ""; patch({ stop: t ? { type: t, params: { ...STOP_PARAM_KEYS[t] } } : null }); }}>
                  <option value="">none yet</option>{STOP_TYPES.map((t) => <option key={t}>{t}</option>)}
                </select>
                {spec.stop && <ParamsEditor params={asParams(spec.stop.params)} suggested={STOP_PARAM_KEYS[spec.stop.type]} onChange={(p) => patch({ stop: { ...spec.stop!, params: p } })} />}
              </div>
            </Row>
            <Row label="Targets">
              <div className="stack">
                {spec.targets.map((t, i) => (
                  <span className="cluster" key={i}>
                    <select className="input input--inline" value={t.type} onChange={(e) => patch({ targets: spec.targets.map((x, j) => j === i ? { ...x, type: e.target.value as typeof x.type } : x) })}>{TARGET_TYPES.map((x) => <option key={x}>{x}</option>)}</select>
                    <input className="input input--inline" style={{ width: 90 }} type="number" step="0.1" value={t.value} aria-label="target value" onChange={(e) => patch({ targets: spec.targets.map((x, j) => j === i ? { ...x, value: Number(e.target.value) } : x) })} />
                    {t.type === "indicator" && <input className="input input--inline" style={{ width: 120 }} list="operands" placeholder="input name" value={t.ref ?? ""} onChange={(e) => patch({ targets: spec.targets.map((x, j) => j === i ? { ...x, ref: e.target.value } : x) })} />}
                    <button type="button" className="btn btn--sm" onClick={() => patch({ targets: spec.targets.filter((_, j) => j !== i) })}>Remove</button>
                  </span>
                ))}
                <span><button type="button" className="btn btn--sm" onClick={() => patch({ targets: [...spec.targets, { type: "rr", value: 2 }] })}>Add target</button></span>
              </div>
            </Row>
            <Row label="Trailing">
              <div className="stack">
                <select className="input input--inline" value={spec.trailing.type} onChange={(e) => { const t = e.target.value as (typeof TRAILING_TYPES)[number]; patch({ trailing: { type: t, params: { ...TRAILING_PARAM_KEYS[t] } } }); }}>{TRAILING_TYPES.map((t) => <option key={t}>{t}</option>)}</select>
                {spec.trailing.type !== "none" && <ParamsEditor params={asParams(spec.trailing.params)} suggested={TRAILING_PARAM_KEYS[spec.trailing.type]} onChange={(p) => patch({ trailing: { ...spec.trailing, params: p } })} />}
              </div>
            </Row>
            <Row label="Time exit">
              <span className="cluster">
                <label className="cluster mono" style={{ gap: 6, fontSize: "var(--fs-1)" }}>max_bars
                  <input className="input input--inline" style={{ width: 80 }} type="number" min={1} step={1} value={spec.time_exit.max_bars ?? ""} onChange={(e) => { const t = { ...spec.time_exit }; if (e.target.value === "") delete t.max_bars; else t.max_bars = Math.max(1, Math.floor(Number(e.target.value))); patch({ time_exit: t }); }} />
                </label>
                <label className="cluster mono" style={{ gap: 6, fontSize: "var(--fs-1)" }}>at_time
                  <input className="input input--inline" style={{ width: 80 }} placeholder="15:15" value={spec.time_exit.at_time ?? ""} onChange={(e) => { const t = { ...spec.time_exit }; if (e.target.value === "") delete t.at_time; else t.at_time = e.target.value; patch({ time_exit: t }); }} />
                </label>
              </span>
            </Row>
          </div>
        </div>

        <div className="section">
          <span className="label">Risk and permission</span>
          <div className="ledger">
            <Row label="Risk">
              <span className="cluster">
                <NumField label="min_rr_after_costs" value={spec.risk.min_rr_after_costs} step={0.1} min={0} onChange={(v) => patch({ risk: { ...spec.risk, min_rr_after_costs: v } })} />
                <NumField label="max_equity_risk_pct" value={spec.risk.max_equity_risk_pct} step={0.05} min={0} max={1} onChange={(v) => patch({ risk: { ...spec.risk, max_equity_risk_pct: v } })} />
                <NumField label="max_trades_per_day" value={spec.risk.max_trades_per_day} step={1} min={1} onChange={(v) => patch({ risk: { ...spec.risk, max_trades_per_day: Math.max(1, Math.floor(v)) } })} />
              </span>
            </Row>
            <Row label="Automation permission" hint="paper_only replays on the Desk after validation; mentor_only only explains; blocked does neither.">
              <select className="input input--inline" value={spec.automation_permission} onChange={(e) => patch({ automation_permission: e.target.value as Strategy["automation_permission"] })}>{AUTOMATION_PERMISSIONS.map((p) => <option key={p}>{p}</option>)}</select>
            </Row>
            <Row label="Ambiguity flags" hint="Set by the mentor. Each one blocks testable until you resolve it in your own words.">
              {spec.ambiguity_flags.length === 0 ? <span className="muted">None.</span> : (
                <div className="stack">
                  {spec.ambiguity_flags.map((f, i) => (
                    <div key={`${i}-${f}`}>
                      <div className="mono" style={{ fontSize: "var(--fs-1)" }}>{f}</div>
                      <span className="cluster" style={{ marginTop: 4 }}>
                        <input className="input" style={{ maxWidth: 420 }} placeholder="One line on how your rule settles this" value={resolutions[f] ?? ""} onChange={(e) => setResolutions({ ...resolutions, [f]: e.target.value })} />
                        <button type="button" className="btn btn--sm" disabled={!(resolutions[f] ?? "").trim()} title={(resolutions[f] ?? "").trim() ? "Remove this flag" : "Type a one-line resolution first"} onClick={() => patch({ ambiguity_flags: spec.ambiguity_flags.filter((_, j) => j !== i) })}>Resolve</button>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Row>
            <Row label="Version locked"><span className="mono">{spec.version_locked ? "yes" : "no"}</span></Row>
          </div>
        </div>
        <datalist id="operands">{operands.map((o) => <option key={o} value={o} />)}</datalist>
      </div>

      {/* ---------------------------------------------------------------- RIGHT: the verdict */}
      <div>
        <div className="section" style={{ marginTop: 0 }}>
          <span className="label">Testable</span>
          <div style={{ padding: "12px 0" }}>
            <span className={`status ${verdict.testable ? "status--eligible" : "status--blocked"}`} style={{ fontSize: "var(--fs-3)" }} data-testid="testable-verdict">{verdict.testable ? "TESTABLE" : "NOT TESTABLE"}</span>
            {!verdict.testable && (
              <ul className="mono" style={{ margin: "10px 0 0", paddingLeft: 18, fontSize: "var(--fs-1)" }} data-testid="missing">
                {verdict.missing.map((m) => <li key={m}>{m}</li>)}
              </ul>
            )}
            {verdict.testable && <p className="muted" style={{ margin: "8px 0 0" }}>Every required piece is present. Save, then Validate.</p>}
          </div>
        </div>

        <div className="section">
          <span className="label">Version</span>
          <div className="ledger">
            <div className="row row--tight"><span className="label">id</span><span /><span className="value value--fig">{initial.id}</span></div>
            <div className="row row--tight"><span className="label">version</span><span /><span className="value value--fig">{initial.version}</span></div>
            <div className="row row--tight"><span className="label">parent_id</span><span /><span className="value value--fig">{initial.parentId ?? "–"}</span></div>
            <div className="row row--tight"><span className="label">status</span><span /><span><PlainChip>{status}</PlainChip></span></div>
          </div>
          {(status === "validated" || spec.version_locked) && <p className="muted" style={{ marginTop: 10 }}>Any parameter change on a validated strategy creates a new version and drops it to untested.</p>}
          {dirty && <p className="mono muted" style={{ marginTop: 6, fontSize: "var(--fs-1)" }}>Unsaved changes.</p>}
        </div>

        {note && <p className={`notice ${note.kind === "plain" ? "" : `notice--${note.kind}`}`} role="status" data-testid="editor-notice">{note.text}</p>}

        <div className="cluster" style={{ marginTop: 16 }}>
          <button type="button" className="btn btn--primary" disabled={pending} onClick={save}>Save</button>
          <button type="button" className="btn" disabled={pending || !!validateReason} title={validateReason ?? "Start the validation pipeline"} onClick={validate}>Validate</button>
        </div>
        {validateReason && <p className="muted" style={{ marginTop: 6, fontSize: "var(--fs-1)" }}>Validate: {validateReason}</p>}

        <div className="section">
          <span className="label">As sentences</span>
          <div style={{ paddingTop: 10 }}><StrategyRules spec={spec} /></div>
        </div>

        <div className="section">
          <span className="label">Formalise from text</span>
          <p className="muted" style={{ margin: "8px 0" }}>Write your rules in your own words. The mentor turns them into a draft, replaces the rows on the left, and flags anything it could read two ways.</p>
          <textarea className="input" value={formText} onChange={(e) => setFormText(e.target.value)} placeholder="Your rules, in plain words." />
          <div className="cluster" style={{ marginTop: 8 }}>
            <button type="button" className="btn" disabled={pending || !formText.trim()} onClick={formalise}>Formalise</button>
          </div>
          {formalised?.prose && <p className="notice" data-testid="formalise-prose">{formalised.prose}</p>}
          {formalised && formalised.flags && formalised.flags.length > 0 && (
            <ul className="mono" style={{ paddingLeft: 18, fontSize: "var(--fs-1)" }}>{formalised.flags.map((f, i) => <li key={i}>{f}</li>)}</ul>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- small pieces -------------------------------------------------------------------------------------------

function Row({ label, hint, children }: { label: React.ReactNode; hint?: string; children: React.ReactNode }) {
  return (
    <div className="row row--wide">
      <span className="label">{label}</span>
      <div className="value">
        {children}
        {hint && <div className="muted" style={{ fontSize: "var(--fs-1)", marginTop: 4 }}>{hint}</div>}
      </div>
    </div>
  );
}

function NumField({ label, value, step, min, max, onChange }: { label: string; value: number; step: number; min?: number; max?: number; onChange: (v: number) => void }) {
  return (
    <label className="cluster mono" style={{ gap: 6, fontSize: "var(--fs-1)" }}>{label}
      <input className="input input--inline" style={{ width: 90 }} type="number" step={step} min={min} max={max} value={Number.isFinite(value) ? value : ""} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

/** key=value editor. Suggested keys appear first; existing keys are kept. Numeric text becomes a number. */
function ParamsEditor({ params, suggested, onChange }: { params: Params; suggested: Record<string, number | string>; onChange: (p: Params) => void }) {
  const keys = Array.from(new Set([...Object.keys(suggested), ...Object.keys(params)]));
  if (keys.length === 0) return <span className="muted" style={{ fontSize: "var(--fs-1)" }}>No parameters.</span>;
  return (
    <span className="cluster">
      {keys.map((k) => (
        <label key={k} className="cluster mono" style={{ gap: 6, fontSize: "var(--fs-1)" }}>{k}=
          <input className="input input--inline" style={{ width: 90 }} value={params[k] ?? ""} spellCheck={false} onChange={(e) => onChange({ ...params, [k]: parseOperand(e.target.value) })} />
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
          <input className="input input--inline" style={{ width: 130 }} list="operands" value={String(c.lhs)} spellCheck={false} aria-label="left operand" onChange={(e) => set(i, { ...c, lhs: parseOperand(e.target.value) })} />
          <select className="input input--inline" value={c.op} aria-label="operator" onChange={(e) => set(i, { ...c, op: e.target.value as Condition["op"] })}>{OPS.map((o) => <option key={o}>{o}</option>)}</select>
          <input className="input input--inline" style={{ width: 130 }} list="operands" value={String(c.rhs)} spellCheck={false} aria-label="right operand" onChange={(e) => set(i, { ...c, rhs: parseOperand(e.target.value) })} />
          <label className="cluster mono" style={{ gap: 6, fontSize: "var(--fs-1)" }}>lookback
            <input className="input input--inline" style={{ width: 64 }} type="number" min={1} step={1} value={c.lookback ?? ""} aria-label="lookback" onChange={(e) => { const n = { ...c }; if (e.target.value === "") delete n.lookback; else n.lookback = Math.max(1, Math.floor(Number(e.target.value))); set(i, n); }} />
          </label>
          <button type="button" className="btn btn--sm" onClick={() => onChange(list.filter((_, j) => j !== i))}>Remove</button>
        </span>
      ))}
      <span><button type="button" className="btn btn--sm" onClick={() => onChange([...list, { lhs: "close", op: ">", rhs: operands.find((o) => !["open", "high", "low", "close", "volume"].includes(o)) ?? "open" }])}>Add condition</button></span>
      {operands.length <= 5 && <span className="muted" style={{ fontSize: "var(--fs-1)" }}>Add an input above to reference an indicator here; bar fields are open, high, low, close, volume.</span>}
    </div>
  );
}
