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
      user: { id: number; name: string; email: string; roles: string[]; is_admin: boolean };
    };

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<Me>("/api/auth/me/"),
    staleTime: 60 * 1000,
  });
}

export const signIn = (email: string, password: string) =>
  apiFetch<Me>("/api/auth/login/", { method: "POST", body: JSON.stringify({ email, password }) });

export const signOut = () => apiFetch<void>("/api/auth/logout/", { method: "POST" });

/** Only follow a same-site path after sign-in: `?next=https://evil.example`
 * must not turn the login page into an open redirect. */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/jobs";
}

export const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  inspector: "Inspector",
  valuer: "Valuer",
  peer_reviewer: "Peer reviewer",
  counter_signatory: "Counter-signatory",
};
