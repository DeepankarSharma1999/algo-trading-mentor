import Link from "next/link";

const TERMS: [string, string][] = [
  ["1R", "One unit of risk: the rupees you lose if a trade hits its stop. It is your trading bucket times the per-trade percentage of your profile. Every figure on the Desk and in the Journal is in R so trades of different sizes compare fairly."],
  ["Trading bucket", "The only one of your three capital buckets that ever sizes a paper position. Safety and long-term money are never touched."],
  ["Daily risk left", "How many R you may still lose today before the daily brake stops new entries. Losses count; wins do not refill it."],
  ["Weekly brake", "The same idea over a Monday-to-Friday week. When it is reached, no new exposure until next week."],
  ["State: CALM", "Normal. Entries allowed under your rules."],
  ["State: ELEVATED", "Two override attempts in a session, or a journal note that matched the revenge/FOMO word list. Entries still allowed; the mentor becomes stricter."],
  ["State: COOLDOWN", "A rule breach or the daily brake. Journal only until the next session opens."],
  ["State: RESEARCH", "Market closed. The only state in which parameters and profile loosening are allowed."],
  ["Market (sim)", "Prices are synthetic, so the app runs on a simulated clock. You can pause, resume and speed it up in Settings."],
  ["Template", "A complete, testable rule set that exists to show what the schema looks like. Templates carry no performance figures and are not recommendations."],
  ["Testable", "A strategy has at least one entry, a stop, at least one exit, a timeframe, a session and no open ambiguity flags. The Builder lists exactly what is missing."],
  ["Validated", "The strategy passed all eight validation stages. Only validated, paper-only strategies can be watched."],
  ["Untested", "A validated strategy whose parameters changed. Every change makes a new version and drops it to untested."],
  ["Watcher", "A validated strategy being paper-traded on the simulated feed. It moves through WATCHING, SETUP_FOUND, ARMED, ORDER_PENDING, OPEN, EXIT_PENDING and CLOSED; a hard failure goes to BLOCKED."],
  ["Rule trace", "The Desk's account of the latest bar: which conditions passed and failed, the trigger, stop, targets, quantity, cost estimate, post-cost R:R and every gate with its reason."],
  ["Gate", "One yes/no check a setup must clear: entry conditions, regime, post-cost R:R, session window, daily and weekly brakes, concurrent risk, trades per day, behavioural state."],
  ["Post-cost R:R", "Reward-to-risk after brokerage, taxes, exchange fees and slippage. Your risk block sets the minimum."],
  ["Regime", "The market condition on the last closed bar: trend, range, compression, high volatility or an event day. Strategies declare which regimes they are built for."],
  ["Validation stages", "1 In-sample coherence, 2 Out-of-sample, 3 Walk-forward, 4 Cost stress, 5 Parameter sensitivity, 6 Regime breakdown, 7 Monte Carlo, 8 Paper-trading agreement. The pipeline stops at the first hard failure and names the weakest stage in one sentence."],
  ["Process score", "Rules followed divided by rules total for a trade. The Journal ranks process above P&L because process is the only thing you control."],
  ["MFE / MAE", "Maximum favourable and adverse excursion: how far the trade went for and against you before it closed, in R."],
  ["Paper only / mentor only / blocked", "The three automation permissions. Paper-only strategies can be watched; mentor-only strategies are discussed but never traded; blocked strategies do nothing. There is no broker and no live order anywhere in this product."],
];

export default function HelpPage() {
  return (
    <>
      <div className="page-head"><h1 className="h-display">Help</h1></div>
      <p className="page-intro">Every term that appears on a screen, in the order you meet it. This tool is educational, not SEBI-registered, and never recommends an instrument or a trade.</p>

      <div className="section">
        <span className="label">How a strategy moves through the app</span>
        <ol className="steps">
          <li><span><span className="steps__title">Clone a template or write your own</span><br /><span className="steps__hint">Library → Clone, or Builder → New strategy. The Builder shows what is still missing before it is testable.</span></span><Link className="btn btn--sm" href="/library">Library</Link></li>
          <li><span><span className="steps__title">Validate it</span><br /><span className="steps__hint">Eight stages run in order. The weakest stage is named in one sentence with the next step inside your rules.</span></span><Link className="btn btn--sm" href="/validation">Validation</Link></li>
          <li><span><span className="steps__title">Watch it in paper mode</span><br /><span className="steps__hint">Builder → Watch on a validated, paper-only strategy. The Desk shows every rule trace as it happens.</span></span><Link className="btn btn--sm" href="/desk">Desk</Link></li>
          <li><span><span className="steps__title">Journal the trades</span><br /><span className="steps__hint">Closed paper trades arrive with planned vs actual, slippage and a process score. Notes feed the behavioural state.</span></span><Link className="btn btn--sm" href="/journal">Journal</Link></li>
          <li><span><span className="steps__title">Change parameters only in Research</span><br /><span className="steps__hint">When the market is closed. Every change creates a new version you can diff.</span></span><Link className="btn btn--sm" href="/research">Research</Link></li>
        </ol>
      </div>

      <div className="section">
        <span className="label">Glossary</span>
        <dl className="glossary">
          {TERMS.map(([t, d]) => (<div key={t}><dt>{t}</dt><dd>{d}</dd></div>))}
        </dl>
      </div>
    </>
  );
}
