"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button, Input } from "@/design-system";
import { ApiError, apiFetch, apiUrl } from "@/lib/api";
import { safeNext, signIn, signInWithGoogle, type Me } from "@/lib/auth";

type GoogleId = {
  accounts: {
    id: {
      initialize: (o: { client_id: string; callback: (r: { credential: string }) => void }) => void;
      renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
    };
  };
};

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [waking, setWaking] = useState(false);
  const [googleId, setGoogleId] = useState<string | null>(null);
  const googleBox = useRef<HTMLDivElement>(null);

  /** Whichever way they signed in, land them where they were going. */
  async function finish(attempt: () => Promise<Me>) {
    setBusy(true);
    setError(null);
    try {
      const me = await attempt();
      qc.setQueryData(["me"], me);
      await qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Try again.");
      setBusy(false);
    }
  }

  // Google sign-in, when the API has a client ID for it.
  useEffect(() => {
    apiFetch<{ google_client_id: string }>("/api/auth/config/")
      .then((c) => setGoogleId(c.google_client_id || null))
      .catch(() => setGoogleId(null));
  }, []);

  useEffect(() => {
    if (!googleId) return;
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      const google = (window as unknown as { google?: GoogleId }).google;
      if (!google || !googleBox.current) return;
      google.accounts.id.initialize({ client_id: googleId, callback: (r) => void finish(() => signInWithGoogle(r.credential)) });
      google.accounts.id.renderButton(googleBox.current, { theme: "outline", size: "large", width: 316, text: "signin_with" });
    };
    document.head.appendChild(script);
    return () => script.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per client ID
  }, [googleId]);

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

        {googleId && (
          <>
            <div ref={googleBox} style={{ minHeight: 44, display: "flex", justifyContent: "center" }} />
            <div className="row" style={{ gap: 10, margin: "18px 0", color: "var(--text-muted)", fontSize: 13 }}>
              <span style={{ flex: 1, height: 1, background: "var(--border-divider)" }} />
              or with a password
              <span style={{ flex: 1, height: 1, background: "var(--border-divider)" }} />
            </div>
          </>
        )}

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
      </form>
    </main>
  );
}
