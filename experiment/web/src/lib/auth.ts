import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

/**
 * Who is signed in (backend/apps/accounts/auth_views.py). Email + password for
 * now; Google Workspace SSO (CLAUDE.md §8) will replace the form but keep this
 * contract, so nothing that reads `useMe()` changes.
 */
export type Me =
  | { authenticated: false }
  | {
      authenticated: true;
      user: { id: number; name: string; email: string; roles: string[]; is_admin: boolean;
        /** Ops and platform admins take instructions in. */
        can_create_jobs?: boolean;
        /** Someone reports to them: they see their team on the dashboard. */
        is_manager?: boolean };
    };

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<Me>("/api/auth/me/"),
    staleTime: 60 * 1000,
  });
}

/** A sign-out still on its way (the page doesn't wait for it). */
let signingOut: Promise<unknown> = Promise.resolve();

export async function signIn(email: string, password: string) {
  // Never let a late sign-out end the session this sign-in starts.
  await signingOut;
  return apiFetch<Me>("/api/auth/login/", { method: "POST", body: JSON.stringify({ email, password }) });
}

/** Signs in with the ID token Google's button hands back. Someone not yet
 * added gets a 403 saying an admin needs to approve them. */
export async function signInWithGoogle(credential: string) {
  await signingOut;
  return apiFetch<Me>("/api/auth/google/", { method: "POST", body: JSON.stringify({ credential }) });
}

/** Ends the session; retried once. keepalive: the request finishes even
 * though the page moves on straight away. */
export function signOut(): Promise<void> {
  const send = () => apiFetch<void>("/api/auth/logout/", { method: "POST", keepalive: true });
  const done = send().catch(() => send()).catch(() => undefined);
  signingOut = done;
  return done;
}

/** Only follow a same-site path after sign-in: `?next=https://evil.example`
 * must not turn the login page into an open redirect. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/jobs";
}

export const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  ops: "Ops",
  inspector: "Inspector",
  valuer: "Valuer",
  peer_reviewer: "Peer reviewer",
  counter_signatory: "Counter-signatory",
};
