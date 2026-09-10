import { extent, linear, tick, ticks } from "./scale";

const PAD = { left: 44, right: 12, top: 10, bottom: 18 };

/** Drawdown from peak, in percent, one value per equity point. Always <= 0. */
export function drawdownSeries(equity: number[]): number[] {
  let peak = -Infinity;
  return equity.map((e) => {
    if (e > peak) peak = e;
    return peak > 0 ? ((e - peak) / peak) * 100 : 0;
  });
}

/**
 * The one chart in the app with an area fill: drawdown from the running peak, filled downward in
 * blocked-tint (`.dd-fill`) with a thin blocked outline. `equity` is a plain series or [x, y] pairs.
 */
export function DrawdownChart({ equity, width = 640, height = 140 }: { equity: number[] | [number, number][]; width?: number; height?: number }) {
  const values = equity.map((e) => (Array.isArray(e) ? e[1] : e));
  if (values.length < 2) return <p className="muted">Not enough points to draw.</p>;
  const dd = drawdownSeries(values);
  const [lo] = extent(dd);
  const yd: [number, number] = [Math.min(lo, -0.01), 0];
  const x = linear([0, dd.length - 1], [PAD.left, width - PAD.right]);
  const y = linear(yd, [height - PAD.bottom, PAD.top]);
  const line = dd.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(dd.length - 1).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="drawdown from peak, percent">
      {ticks(yd, 2).map((v) => (
        <g key={v}>
          <line className="grid" x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} />
          <text x={PAD.left - 6} y={y(v) + 3} textAnchor="end">{tick(v)}%</text>
        </g>
      ))}
      <path className="dd-fill" d={area} />
      <path className="dd-line" d={line} />
      <text x={PAD.left} y={height - 4}>drawdown from peak</text>
    </svg>
  );
}
