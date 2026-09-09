// Server-side client for the engine. Never import from client components.
const BASE = process.env.ENGINE_URL ?? "http://localhost:8000";

export class EngineError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function engine<T = unknown>(path: string, opts: { method?: string; body?: unknown; userId?: string } = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: opts.method ?? (opts.body ? "POST" : "GET"),
    headers: { "content-type": "application/json", ...(opts.userId ? { "x-user-id": opts.userId } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });
  const text = await res.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { error: text }; }
  if (!res.ok) throw new EngineError(res.status, (data as { error?: string; detail?: string })?.error ?? (data as { detail?: string })?.detail ?? `Engine ${res.status}`);
  return data as T;
}

/** Returns null instead of throwing when the engine is unreachable, so pages degrade. */
export async function engineOrNull<T>(path: string, opts: Parameters<typeof engine>[1] = {}): Promise<T | null> {
  try { return await engine<T>(path, opts); } catch { return null; }
}
