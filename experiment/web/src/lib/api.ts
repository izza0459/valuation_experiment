const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  /** Parsed JSON error body when the API sent one (`{code, detail, errors, current}`). */
  body: Record<string, unknown> | null;
  constructor(message: string, status: number, body: Record<string, unknown> | null = null) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

/** Absolute URL for an API path, for links that open outside the app (reports). */
export const apiUrl = (path: string) => `${API_BASE_URL}${path}`;

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

let csrfToken: string | null = null;

/**
 * Session auth makes Django require a CSRF token on every unsafe request.
 * The cookie is the usual source; the token is also returned in the body so
 * this keeps working when the API sits on a different domain from the app
 * and the cookie isn't readable here.
 */
async function getCsrfToken(forceFresh = false): Promise<string> {
  if (!forceFresh) {
    const fromCookie = readCookie("csrftoken");
    if (fromCookie) return fromCookie;
    if (csrfToken) return csrfToken;
  }
  const res = await fetch(`${API_BASE_URL}/api/csrf/`, { credentials: "include" });
  const body = (await res.json()) as { csrfToken: string };
  csrfToken = body.csrfToken;
  return readCookie("csrftoken") ?? csrfToken;
}

/**
 * Thin fetch wrapper. `credentials: "include"` carries the Django session
 * cookie — SSO (Google Workspace OIDC, CLAUDE.md §8) will replace the dev
 * login flow later without changing this contract.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  // A file upload sets its own Content-Type (with the multipart boundary).
  if (!headers.has("Content-Type") && !(init?.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (!SAFE_METHODS.has(method)) headers.set("X-CSRFToken", await getCsrfToken());

  let res = await fetch(`${API_BASE_URL}${path}`, { ...init, credentials: "include", headers });

  // Signing in or out rotates Django's CSRF token, so a token held from before
  // is refused. Fetch a fresh one and retry once.
  if (res.status === 403 && !SAFE_METHODS.has(method) && /CSRF/i.test(await res.clone().text())) {
    headers.set("X-CSRFToken", await getCsrfToken(true));
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, credentials: "include", headers });
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let body: Record<string, unknown> | null = null;
    try {
      const parsed: unknown = JSON.parse(text);
      if (parsed && typeof parsed === "object") body = parsed as Record<string, unknown>;
    } catch {
      /* not JSON — keep the raw text as the message */
    }
    const detail = body && typeof body.detail === "string" ? body.detail : null;
    throw new ApiError(detail ?? (text || res.statusText), res.status, body);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}
