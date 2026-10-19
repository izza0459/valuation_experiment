"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Input } from "@/design-system";
import { ApiError, apiUrl } from "@/lib/api";
import { safeNext, signIn } from "@/lib/auth";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waking, setWaking] = useState(false);

  /** On the free hosting the API sleeps when idle and takes up to a minute
   * to start; until then requests time out. Wait for it (up to 2 minutes)
   * instead of failing the sign-in. */
  async function serverAwake(): Promise<boolean> {
    const deadline = Date.now() + 120_000;
    let first = true;
    while (Date.now() < deadline) {
      try {
        const res = await fetch(apiUrl("/api/health/"), { cache: "no-store" });
        if (res.ok) return true;
      } catch {
        /* still starting */
      }
      if (first) setWaking(true);
      first = false;
      await new Promise((r) => setTimeout(r, 4000));
    }
    return false;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (!(await serverAwake())) {
        setWaking(false);
        setError("The server didn't start. Check your connection and try again in a minute.");
        setBusy(false);
        return;
      }
      setWaking(false);
      const me = await signIn(email, password);
      qc.setQueryData(["me"], me);
      // Anything fetched while signed out (or as someone else) is stale.
      await qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? "Too many attempts. Wait a minute and try again."
          : err instanceof ApiError
            ? err.message
            : "Couldn't reach the server. Try again.",
      );
      setWaking(false);
      setBusy(false);
    }
  }

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <form onSubmit={submit} className="card" style={{ width: 380, maxWidth: "100%", padding: 32 }}>
        <div style={{ fontSize: 24, fontWeight: 500, marginBottom: 4 }}>
          Bayut <span style={{ color: "var(--brand-red)" }}>valuations</span>
        </div>
        <div style={{ color: "var(--text-muted)", fontSize: 14, marginBottom: 24 }}>Sign in to continue</div>

        <label style={{ display: "block", fontSize: 14, color: "var(--text-secondary)", marginBottom: 6 }}>Email</label>
        <Input
          type="email"
          autoComplete="username"
          autoFocus
          required
          value={email}
          invalid={Boolean(error)}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label style={{ display: "block", fontSize: 14, color: "var(--text-secondary)", margin: "16px 0 6px" }}>
          Password
        </label>
        <Input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          invalid={Boolean(error)}
          onChange={(e) => setPassword(e.target.value)}
        />

        {waking && !error && (
          <div role="status" style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 12 }}>
            The server was asleep and is starting up. This can take up to a minute; you&apos;ll be signed in
            automatically.
          </div>
        )}
        {error && (
          <div role="alert" style={{ color: "var(--text-error)", fontSize: 14, marginTop: 12 }}>
            {error}
          </div>
        )}

        <Button type="submit" block disabled={busy || !email || !password} style={{ marginTop: 22 }}>
          {waking ? "Starting the server…" : busy ? "Signing in…" : "Sign in"}
        </Button>
        <div style={{ color: "var(--text-muted)", fontSize: 12, marginTop: 14 }}>
          Google Workspace sign-in will replace this.
        </div>
      </form>
    </main>
  );
}
