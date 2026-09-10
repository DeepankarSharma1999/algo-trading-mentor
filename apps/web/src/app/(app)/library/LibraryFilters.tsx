"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { REGIMES, TIMEFRAMES } from "@atm/schema";

/** Regime and timeframe filters, kept in the URL so a filtered Library can be linked. */
export function LibraryFilters({ regime, timeframe }: { regime: string; timeframe: string }) {
  const router = useRouter();
  const path = usePathname();
  const params = useSearchParams();
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value === "all") next.delete(key); else next.set(key, value);
    next.delete("notice");
    const qs = next.toString();
    router.replace(qs ? `${path}?${qs}` : path);
  };
  return (
    <div className="ledger">
      <div className="row row--wide">
        <label className="label" htmlFor="regime">Regime</label>
        <select id="regime" className="input input--inline" value={regime} onChange={(e) => set("regime", e.target.value)}>
          <option value="all">all</option>
          {REGIMES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <div className="row row--wide">
        <label className="label" htmlFor="timeframe">Timeframe</label>
        <select id="timeframe" className="input input--inline" value={timeframe} onChange={(e) => set("timeframe", e.target.value)}>
          <option value="all">all</option>
          {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
    </div>
  );
}
