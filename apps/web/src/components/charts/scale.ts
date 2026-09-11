// Shared helpers for the SVG charts. Pure, no DOM.

export interface Box { left: number; top: number; right: number; bottom: number }

export function extent(values: number[]): [number, number] {
  let lo = Infinity, hi = -Infinity;
  for (const v of values) if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
  if (lo === Infinity) return [0, 1];
  if (lo === hi) return [lo - 1, hi + 1];
  return [lo, hi];
}

export function linear([d0, d1]: [number, number], [r0, r1]: [number, number]) {
  const span = d1 - d0 || 1;
  return (v: number) => r0 + ((v - d0) / span) * (r1 - r0);
}

/** Round, short axis label. `extra` adds decimals, used when neighbouring ticks would otherwise print the same. */
export function tick(v: number, extra = 0): string {
  const a = Math.abs(v);
  if (a >= 1e7) return `${(v / 1e7).toFixed(1 + extra)}cr`;
  if (a >= 1e5) return `${(v / 1e5).toFixed(1 + extra)}L`;
  if (a >= 1e3) return `${(v / 1e3).toFixed(1 + extra)}k`;
  if (a >= 100) return v.toFixed(0 + extra);
  if (a >= 10) return v.toFixed(1 + extra);
  return v.toFixed(2 + extra);
}

/** Evenly spaced values between lo and hi, inclusive. */
export function ticks([lo, hi]: [number, number], n = 4): number[] {
  return Array.from({ length: n + 1 }, (_, i) => lo + ((hi - lo) * i) / n);
}

/** Labels for `ticks`, with enough decimals that no two neighbours read the same on a narrow range. */
export function tickLabels(values: number[]): string[] {
  for (let extra = 0; extra <= 3; extra++) {
    const labels = values.map((v) => tick(v, extra));
    if (new Set(labels).size === labels.length) return labels;
  }
  return values.map((v) => tick(v, 3));
}
