import { StateChip } from "./Chip";
import { rupees, rAbs, simTs } from "@/lib/format";
import type { StripData } from "@/lib/strip";

/** The 44px instrument panel on every screen. */
export function Strip({ d }: { d: StripData }) {
  const dailyLeft = Math.max(0, d.dailyLimitR - d.dailyUsedR);
  const weeklyLeft = Math.max(0, d.weeklyLimitR - d.weeklyUsedR);
  return (
    <header className="strip" data-testid="strip">
      <div className="strip__cell" title="The only bucket that sizes paper positions."><span className="label">Trading</span><span className="fig">{rupees(d.tradingBucket)}</span></div>
      <div className="strip__cell" title="One unit of risk: what one trade may lose at its stop."><span className="label">1R</span><span className="fig">{rupees(d.oneR)}</span></div>
      <div className="strip__cell" title={`${d.dailyUsedR.toFixed(2)}R of ${d.dailyLimitR}R used today`}>
        <span className="label">Daily left</span>
        <span className={`fig ${d.brakes.daily ? "status--blocked" : ""}`}>{rAbs(dailyLeft)} · {rupees(dailyLeft * d.oneR)}</span>
      </div>
      <div className="strip__cell" title={`${d.weeklyUsedR.toFixed(2)}R of ${d.weeklyLimitR}R used this week`}>
        <span className="label">Weekly</span>
        <span className={`fig ${d.brakes.weekly ? "status--blocked" : ""}`}>{d.brakes.weekly ? "REACHED" : `${rAbs(weeklyLeft)} left`}</span>
      </div>
      <div className="strip__cell" title={d.stateReason}><span className="label">State</span><StateChip state={d.state} title={d.stateReason} /></div>
      <div className="strip__cell" style={{ marginLeft: "auto" }} title="Simulated clock over synthetic prices. Pause or speed it up in Settings.">
        <span className="label">Market</span>
        <span className="fig">{d.marketOpen ? "OPEN" : "CLOSED"}</span>
        <span className="fig faint">{d.simNow ? `sim ${simTs(d.simNow)}` : "no clock"}</span>
      </div>
    </header>
  );
}
