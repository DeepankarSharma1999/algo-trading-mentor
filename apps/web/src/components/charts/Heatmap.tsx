/**
 * Parameter-sensitivity grid. Rows are parameter paths, columns are deltas, `values[r][c]` is the
 * expectancy in R. Cells are tinted eligible (positive) or blocked (negative) with intensity by
 * magnitude, and the number is printed in mono inside every cell, so no colour legend is needed.
 * NaN values (a perturbation that failed to run) print as a dash on a plain cell.
 */
export function Heatmap({ rows, cols, values, cellW = 78, cellH = 26, labelW = 200, digits = 2 }: {
  rows: string[]; cols: string[]; values: (number | null)[][]; cellW?: number; cellH?: number; labelW?: number; digits?: number;
}) {
  if (rows.length === 0 || cols.length === 0) return <p className="muted">No grid to draw.</p>;
  const finite = values.flat().filter((v): v is number => v !== null && Number.isFinite(v));
  const maxAbs = Math.max(1e-9, ...finite.map((v) => Math.abs(v)));
  const width = labelW + cols.length * cellW + 8, height = 22 + rows.length * cellH + 4;
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} style={{ maxWidth: width }} role="img" aria-label="parameter sensitivity">
      {cols.map((c, j) => (
        <text key={c} x={labelW + j * cellW + cellW / 2} y={14} textAnchor="middle">{c}</text>
      ))}
      {rows.map((rname, i) => (
        <g key={rname}>
          <text x={labelW - 8} y={22 + i * cellH + cellH / 2 + 3} textAnchor="end">{rname}</text>
          {cols.map((c, j) => {
            const v = values[i]?.[j];
            const ok = v !== null && v !== undefined && Number.isFinite(v);
            const tone = ok ? (v > 0 ? "var(--eligible)" : v < 0 ? "var(--blocked)" : "var(--rule)") : "var(--rule)";
            const alpha = ok ? 0.08 + 0.42 * Math.min(1, Math.abs(v) / maxAbs) : 0.15;
            const cx = labelW + j * cellW, cy = 22 + i * cellH;
            return (
              <g key={c}>
                <rect x={cx} y={cy} width={cellW - 2} height={cellH - 2} fill={tone} fillOpacity={alpha} />
                <text x={cx + cellW / 2 - 1} y={cy + cellH / 2 + 3} textAnchor="middle" fill="var(--ink)">
                  {ok ? `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(digits)}` : "–"}
                </text>
              </g>
            );
          })}
        </g>
      ))}
    </svg>
  );
}
