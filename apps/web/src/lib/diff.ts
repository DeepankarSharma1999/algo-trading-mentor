// Flat JSON path diff for the Research version history. No library: flatten both documents to
// `path -> primitive`, then compare. Paths use dots for keys and [i] for array indices.

export type DiffLine = { path: string; kind: "add" | "del" | "change"; from?: string; to?: string };

/** `{a:{b:[1,2]}}` → `{ "a.b[0]": 1, "a.b[1]": 2 }`. Empty containers keep a marker so their removal shows. */
export function flatten(v: unknown, prefix = "", out: Record<string, unknown> = {}): Record<string, unknown> {
  if (Array.isArray(v)) {
    if (v.length === 0 && prefix) out[prefix] = "[]";
    v.forEach((x, i) => flatten(x, prefix ? `${prefix}[${i}]` : `[${i}]`, out));
  } else if (v !== null && typeof v === "object") {
    const keys = Object.keys(v as Record<string, unknown>);
    if (keys.length === 0 && prefix) out[prefix] = "{}";
    for (const k of keys) flatten((v as Record<string, unknown>)[k], prefix ? `${prefix}.${k}` : k, out);
  } else {
    out[prefix] = v;
  }
  return out;
}

/** Renders a leaf value for the diff line. Strings print bare; null and undefined print as words. */
export function show(v: unknown): string {
  if (v === null) return "null";
  if (v === undefined) return "undefined";
  return typeof v === "string" ? v : String(v);
}

/** Lines in first-seen order: every path of `a` (deleted or changed), then paths only `b` has (added). */
export function diff(a: unknown, b: unknown): DiffLine[] {
  const fa = flatten(a), fb = flatten(b);
  const lines: DiffLine[] = [];
  for (const path of Object.keys(fa)) {
    if (!(path in fb)) lines.push({ path, kind: "del", from: show(fa[path]) });
    else if (!Object.is(fa[path], fb[path])) lines.push({ path, kind: "change", from: show(fa[path]), to: show(fb[path]) });
  }
  for (const path of Object.keys(fb)) if (!(path in fa)) lines.push({ path, kind: "add", to: show(fb[path]) });
  return lines;
}
