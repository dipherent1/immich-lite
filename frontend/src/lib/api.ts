/**
 * Single reusable API client — the ONLY place that talks to FastAPI.
 *
 * - Owns the FastAPI base URL (components never hardcode it).
 * - Stores the JWT in localStorage and attaches it as `Authorization: Bearer <token>`
 *   (components never touch localStorage or build headers themselves).
 *
 * Later-secure seam: to switch to HttpOnly cookies + a Next.js proxy, only this
 * module changes — the base URL becomes relative and the token is read from a
 * cookie. Application components are untouched.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

const TOKEN_KEY = "immich_lite_token";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// --- Token storage (private to this module) -------------------------------

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

export function logout(): void {
  clearToken();
}

// --- Internal transport (the actual API client) ---------------------------

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; authenticated?: boolean } = {},
): Promise<T> {
  const { method = "GET", body, authenticated = false } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (authenticated) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = `${method} ${path} failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // ignore unparseable bodies
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}

// --- Domain types ----------------------------------------------------------

export interface UserResponse {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

// --- Auth actions ----------------------------------------------------------

/** Logs in and stores the returned JWT. Resolves once authenticated. */
export async function login(email: string, password: string): Promise<void> {
  const data = await request<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
  });
  setToken(data.access_token);
}

/** Creates an account. The backend returns the user (no token) — the caller
 *  should then log in. */
export async function register(
  email: string,
  password: string,
  displayName: string,
): Promise<UserResponse> {
  return request<UserResponse>("/api/v1/auth/register", {
    method: "POST",
    body: { email, password, display_name: displayName },
  });
}

// --- Authenticated data actions -------------------------------------------

/** Returns the currently authenticated user. */
export async function getMe(): Promise<UserResponse> {
  return request<UserResponse>("/api/v1/users/me", { authenticated: true });
}
