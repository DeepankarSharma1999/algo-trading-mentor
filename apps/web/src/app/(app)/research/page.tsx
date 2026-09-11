import Link from "next/link";
import { Diff } from "@/components/Diff";
import { requireUser } from "@/lib/auth";
import { db } from "@/lib/db";
import { diff } from "@/lib/diff";
import { ts } from "@/lib/format";

export const dynamic = "force-dynamic";

const BLOCKED = "Parameter changes are closed right now. Research mode opens when your state is RESEARCH, which the app sets whenever the simulated market is closed: before 09:15, after 15:30, and on non-trading days, all on the simulated clock in IST. Until then you can still read every version and its diff below, queue a validation run, and tighten your risk profile in Settings. You cannot edit parameters or loosen the profile.";

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
      <p className="page-intro">
        Every strategy you own and every version it has been through. A save that changes parameters makes a new version; older versions stay on file, nothing is overwritten, and any two neighbours can be compared line by line. Parameters can only change while the market is closed. <Link href="/help">States and versions are explained in Help.</Link>
      </p>

      {!research ? (
        <div className="notice notice--blocked" role="status" data-testid="research-blocked">{BLOCKED}</div>
      ) : (
        <p className="notice" role="status" style={{ margin: "0 0 8px" }}>
          Research mode is open: the simulated market is closed, so parameters may change. Pick a version below, then <Link href={selected ? `/builder/${selected.id}` : "/builder"}>edit parameters in the Builder</Link>. Loosening a risk profile also opens now, in <Link href="/settings">Settings</Link>.
        </p>
      )}

      <div className="section">
        <span className="label">Your strategies · all versions</span>
        <p className="help help--tight">Versions share a name and count up from v1; the newest is listed first under each name. Select a row to see what changed between each version and the one before it, as a diff.</p>
        {mine.length === 0 ? (
          <div className="empty">
            <p>You have no strategies yet. Clone a template in the Library or write one in the Builder; every save that changes parameters becomes a new version here.</p>
            <span className="cluster"><Link className="btn" href="/library">Open the Library</Link><Link className="btn" href="/builder">Open the Builder</Link></span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="ledger-table" data-testid="versions">
              <thead><tr><th>Strategy</th><th>Id</th><th className="num">Version</th><th title="untested: parameters changed since the last run; testable: complete and ready to validate; validated: passed all eight stages">Status</th><th>Created</th><th title="The version this one was saved from; a template id for a fresh clone">Parent</th><th></th></tr></thead>
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
          <p className="help help--tight">
            Each version against its parent, newest first. A line reads <span className="mono">path: old → new</span>; struck values are gone, tinted values are new.
            {research && <> <Link href={`/builder/${selected.id}`}>Edit parameters in the Builder</Link>.</>}
          </p>
          {chain.length === 1 && (
            <p className="help" style={{ margin: "8px 0 0" }} data-testid="single-version">This is version 1; a diff between your own versions appears once you save a change in Research mode.</p>
          )}
          <div className="stack" style={{ marginTop: 12 }}>
            {chain.map((s) => {
              const parent = s.parentId ? byId.get(s.parentId) : undefined;
              const lines = parent ? diff(parent.spec, s.spec) : [];
              const fromTemplate = !!parent && !mine.some((m) => m.id === parent.id);
              return (
                <div key={s.id} style={{ borderBottom: "1px solid var(--rule)", paddingBottom: 12 }} data-testid="version-diff">
                  <div className="spread">
                    <span className="mono">{s.id} <span className="faint">v{s.version}</span>{s.id === selected.id && <span className="faint"> · selected</span>}</span>
                    <span className="mono faint">{parent ? `vs ${parent.id}${fromTemplate ? " (template)" : ""}` : "no parent"} · {ts(s.createdAt)}</span>
                  </div>
                  <div style={{ marginTop: 6 }}>
                    {parent ? (
                      <>
                        {fromTemplate && <p className="help" style={{ margin: "0 0 6px" }}>Compared with the template it was cloned from.</p>}
                        <Diff lines={lines} emptyText="No parameter changes from the parent; this version was saved with the same spec." />
                      </>
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
