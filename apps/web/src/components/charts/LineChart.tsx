import { extent, linear, tick, ticks } from "./scale";

const PAD = { left: 44, right: 12, top: 14, bottom: 18 };

/**
 * Single-hue line on a faint grid with an emphasised endpoint. Server-renderable SVG; width is
 * responsive through the viewBox and `.chart { width: 100% }`. `points` are [x, y] pairs, x already
 * numeric (index or epoch ms); the x axis prints `xLabels` (first and last) when given.
 */
export function LineChart({ points, width = 640, height = 200, yLabel, xLabels }: {
  points: [number, number][]; width?: number; height?: number; yLabel?: string; xLabels?: [string, string];
}) {
  if (points.length < 2) return <p className="muted">Not enough points to draw.</p>;
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const xd = extent(xs), yd = extent(ys);
  const x = linear(xd, [PAD.left, width - PAD.right]);
  const y = linear(yd, [height - PAD.bottom, PAD.top]);
  const d = points.map(([px, py], i) => `${i ? "L" : "M"}${x(px).toFixed(1)},${y(py).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={yLabel ?? "line chart"}>
      {ticks(yd).map((v) => (
        <g key={v}>
          <line className="grid" x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} />
          <text x={PAD.left - 6} y={y(v) + 3} textAnchor="end">{tick(v)}</text>
        </g>
      ))}
      {yLabel && <text x={PAD.left} y={9}>{yLabel}</text>}
      {xLabels && (
        <>
          <text x={PAD.left} y={height - 4}>{xLabels[0]}</text>
          <text x={width - PAD.right} y={height - 4} textAnchor="end">{xLabels[1]}</text>
        </>
      )}
      <path className="line" d={d} />
      <circle className="endpoint" cx={x(last[0])} cy={y(last[1])} r={3} />
    </svg>
  );
}
