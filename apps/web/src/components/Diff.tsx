import type { DiffLine } from "@/lib/diff";

/** Flat path diff, one line per changed leaf: `path: old → new`. Deleted values strike through, added values tint eligible. */
export function Diff({ lines, emptyText = "No changes from the parent." }: { lines: DiffLine[]; emptyText?: string }) {
  if (lines.length === 0) return <p className="muted">{emptyText}</p>;
  return (
    <div className="diff" data-testid="diff">
      {lines.map((l) => (
        <div key={l.path}>
          {l.path}: {l.kind !== "add" && <span className="del">{l.from}</span>}
          {l.kind === "change" && " → "}
          {l.kind !== "del" && <span className="add">{l.to}</span>}
        </div>
      ))}
    </div>
  );
}
