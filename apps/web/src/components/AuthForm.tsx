"use client";
import Link from "next/link";
import { useActionState, useState } from "react";
import type { AuthState } from "@/app/actions/auth";

export function AuthForm({ action, mode }: { action: (s: AuthState, f: FormData) => Promise<AuthState>; mode: "login" | "register" }) {
  const [state, formAction, pending] = useActionState(action, {});
  const [show, setShow] = useState(false);
  return (
    <main className="content" style={{ maxWidth: 520, paddingTop: 72 }}>
      <div className="label">Algo Trading Mentor</div>
      <h1 className="h-display h-display--xl" style={{ marginTop: 8 }}>{mode === "login" ? "Sign in" : "Create your account"}</h1>
      <p className="muted" style={{ marginTop: 10 }}>
        A quant-research supervisor for your own rules. It never names an instrument, never says buy or sell, and never talks to a broker.
      </p>
      <form action={formAction} className="ledger" style={{ marginTop: 28 }}>
        <div className="row row--wide"><label className="label" htmlFor="email">Email</label><input id="email" name="email" type="email" className="input" autoComplete="email" required /></div>
        <div className="row row--wide">
          <label className="label" htmlFor="password">Password</label>
          <div>
            <input id="password" name="password" type={show ? "text" : "password"} className="input" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={8} required aria-describedby={mode === "register" ? "password-help" : undefined} />
            {mode === "register" && <p id="password-help" className="help help--tight" style={{ margin: "4px 0 0" }}>At least 8 characters.</p>}
            <label className="cluster help" style={{ gap: 6, marginTop: 8, cursor: "pointer" }}>
              <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} /> Show what I typed
            </label>
          </div>
        </div>
        {state.error && <div className="field-error" style={{ padding: "10px 0" }} role="alert">{state.error}</div>}
        <div className="cluster" style={{ paddingTop: 16 }}>
          <button className="btn btn--primary" disabled={pending}>{mode === "login" ? "Sign in" : "Create account"}</button>
          {mode === "login" ? <Link href="/register">Create an account</Link> : <Link href="/login">Sign in instead</Link>}
        </div>
      </form>
      <p className="footer-note" style={{ padding: "28px 0 0", border: 0 }}>Educational tool. Not SEBI-registered. No recommendations.</p>
    </main>
  );
}
