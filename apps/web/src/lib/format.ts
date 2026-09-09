const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

export const rupees = (n: number | string | null | undefined) => (n === null || n === undefined ? "–" : inr.format(Number(n)));
export const rupees2 = (n: number | string | null | undefined) => (n === null || n === undefined ? "–" : inr2.format(Number(n)));
export const r = (n: number | null | undefined, d = 2) => (n === null || n === undefined || Number.isNaN(n) ? "–" : `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(d)}R`);
export const rAbs = (n: number | null | undefined, d = 1) => (n === null || n === undefined ? "–" : `${n.toFixed(d)}R`);
export const pct = (n: number | null | undefined, d = 1) => (n === null || n === undefined || Number.isNaN(n) ? "–" : `${n.toFixed(d)}%`);
export const num = (n: number | null | undefined, d = 2) => (n === null || n === undefined || Number.isNaN(n) ? "–" : n.toFixed(d));
export const ts = (s: string | Date | null | undefined) => {
  if (!s) return "–";
  const d = typeof s === "string" ? new Date(s) : s;
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};
export const day = (s: string | Date | null | undefined) => ts(s).slice(0, 10);
export const clock = (s: string | Date | null | undefined) => ts(s).slice(11);
/** Simulated-clock timestamps are stored as IST wall time in a UTC-naive column; format with UTC getters. */
export const simTs = (s: string | Date | null | undefined) => {
  if (!s) return "–";
  const d = typeof s === "string" ? new Date(s) : s;
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
};
