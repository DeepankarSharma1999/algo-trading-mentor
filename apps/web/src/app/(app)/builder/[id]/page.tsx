import Link from "next/link";
import { notFound } from "next/navigation";
import { requireUser } from "@/lib/auth";
import { getStrategy } from "@/lib/strategies";
import { BuilderEditor } from "./BuilderEditor";

export const dynamic = "force-dynamic";

export default async function BuilderPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const user = await requireUser();
  const { id } = await params;
  const sp = await searchParams;
  const notice = Array.isArray(sp.notice) ? sp.notice[0] : sp.notice;
  const s = await getStrategy(id, user.id);
  if (!s) notFound();
  return (
    <>
      <div className="page-head">
        <h1 className="h-display">Builder</h1>
        <span className="mono muted"><Link href="/builder">all strategies</Link> · {s.id}</span>
      </div>
      <BuilderEditor
        key={s.id}
        initial={{ id: s.id, version: s.version, parentId: s.parentId, status: s.status, spec: s.spec }}
        notice={notice ?? null}
      />
    </>
  );
}
