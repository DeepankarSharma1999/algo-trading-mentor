import { linear, tick } from "./scale";

const PAD = { left: 36, right: 12, top: 10, bottom: 20 };

/**
 * Bars for a Monte Carlo distribution. `bins` are [left edge, count] pairs from numpy.histogram
 * (equal width). Drawn in the drawdown style: blocked-tint fill with a thin blocked outline, since
 * the only histogram in the app is of max drawdown. Optional `marks` print vertical reference lines.
 * `caption` prints a plain sentence under the chart saying what is plotted and in what units.
 */
export function Histogram({ bins, width = 640, height = 160, xUnit = "%", marks = [], caption }: {
  bins: [number, number][]; width?: number; height?: number; xUnit?: string; marks?: { x: number; label: string }[]; caption?: string;
}) {
  if (bins.length === 0) return <p className="muted">No distribution to draw.</p>;
  const edges = bins.map((b) => b[0]);
  const step = bins.length > 1 ? edges[1] - edges[0] : 1;
  const x0 = edges[0], x1 = edges[edges.length - 1] + step;
  const maxCount = Math.max(1, ...bins.map((b) => b[1]));
  const x = linear([x0, x1], [PAD.left, width - PAD.right]);
  const y = linear([0, maxCount], [height - PAD.bottom, PAD.top]);
  const base = height - PAD.bottom;
  return (
    <figure style={{ margin: 0 }}>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={caption ?? "histogram"}>
        <line className="grid" x1={PAD.left} x2={width - PAD.right} y1={base} y2={base} />
        <line className="grid" x1={PAD.left} x2={width - PAD.right} y1={y(maxCount)} y2={y(maxCount)} />
        <text x={PAD.left - 6} y={y(maxCount) + 3} textAnchor="end">{maxCount}</text>
        <text x={PAD.left - 6} y={base + 3} textAnchor="end">0</text>
        {bins.map(([left, count]) => (
          <rect key={left} className="dd-fill" stroke="var(--blocked)" strokeWidth={0.5} x={x(left)} y={y(count)} width={Math.max(0.5, x(left + step) - x(left) - 1)} height={base - y(count)} />
        ))}
        {marks.map((m) => (
          <g key={m.label}>
            <line className="dd-line" x1={x(m.x)} x2={x(m.x)} y1={PAD.top} y2={base} strokeDasharray="2 3" />
            <text x={x(m.x) + 3} y={PAD.top + 8}>{m.label}</text>
          </g>
        ))}
        <text x={PAD.left} y={height - 5}>{tick(x0)}{xUnit}</text>
        <text x={width - PAD.right} y={height - 5} textAnchor="end">{tick(x1)}{xUnit}</text>
      </svg>
      {caption && <figcaption className="help help--tight">{caption}</figcaption>}
    </figure>
  );
}
