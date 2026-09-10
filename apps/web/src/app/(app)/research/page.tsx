import Link from "next/link";
import { Diff } from "@/components/Diff";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { diff } from "@/lib/diff";
import { ts } from "@/lib/format";

export const dynamic = "force-dynamic";

const BLOCKED = "Research mode opens when your state is RESEARCH, which happens whenever the market is closed. Parameters cannot change during a session. You can read the version history below.";

type Row = { id: string; name: string; slug: string; version: number; parentId: string | null; status: string; spec: unknown; createdAt: Date };

/**
 * Version history for the user's strategies, grouped by slug, newest first, with a mono diff of each
 * version against its parent. Editing happens in the Builder and only in RESEARCH state; this page is
 * always readable. Reads Postgres only.
 */
export default async function ResearchPage({ searchParams }: { searchParams: Promise<{ id?: string | string[] }> }) {
  const user = await requireUser();
  const sp = await searchParams;
  const selectedId = Array.isArray(sp.id) ? sp.id[0] : sp.id;
  const research = user.profile?.behaviourState === "RESEARCH";

  const mine: Row[] = await db.strategy.findMany({
    where: { userId: user.id },
    orderBy: [{ slug: "asc" }, { version: "desc" }],
    select: { id: true, name: true, slug: true, version: true, parentId: true, status: true, spec: true, createdAt: true },
  });
  const byId = new Map(mine.map((s) => [s.id, s]));
  // Parents that are not the user's own rows are templates; fetch their specs so a clone's first diff is against the template.
  const missingParents = [...new Set(mine.map((s) => s.parentId).filter((p): p is string => !!p && !byId.has(p)))];
  const parents = missingParents.length ? await db.strategy.findMany({ where: { id: { in: missingParents }, userId: null }, select: { id: true, name: true, slug: true, version: true, parentId: true, status: true, spec: true, createdAt: true } }) : [];
  for (const p of parents) byId.set(p.id, p);

  const groups = new Map<string, Row[]>();
  for (const s of mine) groups.set(s.slug, [...(groups.get(s.slug) ?? []), s]);

  const selected = selectedId ? mine.find((s) => s.id === selectedId) : undefined;
  const chain = selected && selected.slug ? (groups.get(selected.slug) ?? [selected]) : [];

  return (
    <>
      <div className="page-head">
        <h1 className="h-display">Research</h1>
        <span className={`chip ${research ? "chip--research" : "chip--state-plain"}`} data-state={user.profile?.behaviourState}>{user.profile?.behaviourState ?? "RESEARCH"}</span>
      </div>

      {!research ? (
        <div className="notice notice--blocked" role="status" data-testid="research-blocked">{BLOCKED}</div>
      ) : (
        <p className="muted" style={{ margin: "0 0 8px" }}>
          The market is closed, so parameters may change. Pick a version below, then <Link href={selected ? `/builder/${selected.id}` : "/builder"}>edit parameters in the Builder</Link>. Loosening a risk profile also opens now, in <Link href="/settings">Settings</Link>.
        </p>
      )}

      <div className="section">
        <span className="label">Your strategies · all versions</span>
        {mine.length === 0 ? (
          <p className="muted">You have no strategies yet. Clone a template in the <Link href="/library">Library</Link> or write one in the <Link href="/builder">Builder</Link>; every save that changes parameters becomes a new version here.</p>
        ) : (
          <div className="table-scroll">
            <table className="ledger-table" data-testid="versions">
              <thead><tr><th>Strategy</th><th>Id</th><th className="num">Version</th><th>Status</th><th>Created</th><th>Parent</th><th></th></tr></thead>
              <tbody>
                {[...groups.entries()].map(([slug, rows]) => rows.map((s, i) => (
                  <tr key={s.id} className={s.id === selected?.id ? "row--tinted-eligible" : undefined} data-testid="version-row">
                    <td>{i === 0 ? <span>{s.name} <span className="faint">({slug})</span></span> : ""}</td>
                    <td>{s.id}</td>
                    <td className="num">v{s.version}</td>
                    <td><span className={`status ${s.status === "validated" ? "status--eligible" : s.status === "testable" ? "status--watch" : ""}`}>{s.status}</span></td>
                    <td style={{ whiteSpace: "nowrap" }}>{ts(s.createdAt)}</td>
                    <td>{s.parentId ?? "–"}</td>
                    <td><Link href={`/research?id=${encodeURIComponent(s.id)}`}>{s.id === selected?.id ? "Selected" : "Select"}</Link></td>
                  </tr>
                )))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && (
        <div className="section" data-testid="history">
          <span className="label">Version history with diffs · {selected.slug}</span>
          <p className="muted" style={{ margin: "8px 0 0" }}>
            Each version against its parent, newest first. A line reads <span className="mono">path: old → new</span>; struck values are gone, tinted values are new.
            {research && <> <Link href={`/builder/${selected.id}`}>Edit parameters in the Builder</Link>.</>}
          </p>
          <div className="stack" style={{ marginTop: 12 }}>
            {chain.map((s) => {
              const parent = s.parentId ? byId.get(s.parentId) : undefined;
              const lines = parent ? diff(parent.spec, s.spec) : [];
              return (
                <div key={s.id} style={{ borderBottom: "1px solid var(--rule)", paddingBottom: 12 }} data-testid="version-diff">
                  <div className="spread">
                    <span className="mono">{s.id} <span className="faint">v{s.version}</span>{s.id === selected.id && <span className="faint"> · selected</span>}</span>
                    <span className="mono faint">{parent ? `vs ${parent.id}${mine.some((m) => m.id === parent.id) ? "" : " (template)"}` : "no parent"} · {ts(s.createdAt)}</span>
                  </div>
                  <div style={{ marginTop: 6 }}>
                    {parent ? (
                      <Diff lines={lines} emptyText="No parameter changes from the parent; this version was saved with the same spec." />
                    ) : s.parentId ? (
                      <p className="muted" style={{ margin: 0 }}>The parent <span className="mono">{s.parentId}</span> is no longer on file, so there is nothing to diff against.</p>
                    ) : (
                      <p className="muted" style={{ margin: 0 }}>First version; written from scratch, so there is no parent to diff against.</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
