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

  const isForm = typeof FormData !== "undefined" && body instanceof FormData;

  const headers: Record<string, string> = {};
  if (!isForm && body !== undefined) headers["Content-Type"] = "application/json";
  if (authenticated) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body:
      body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });

  console.log(`[api] ${method} ${path} -> ${res.status}`);

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
  email: string;
  display_name: string;
  created_at: string;
  has_face_profile: boolean;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface ScanResponse {
  images_processed: number;
  faces_found: number;
  profile_upserted: boolean;
}

export interface EventResponse {
  id: string;
  name: string;
  join_token: string;
  starts_at: string;
  expires_at: string | null;
  created_at: string;
  active: boolean;
}

export interface EventPublicResponse {
  id: string;
  name: string;
  starts_at: string;
  expires_at: string | null;
  created_at: string;
  active: boolean;
}

export interface EventDetailResponse extends EventResponse {
  attendee_count: number;
}

export interface EventJoinResponse {
  event: EventResponse;
  joined: boolean;
}

export interface CreateEventInput {
  name: string;
  starts_at?: string;
  expires_at?: string | null;
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

/** Uploads 1–3 face images and enrolls them as the user's profile vector. */
export async function scanFace(images: File[]): Promise<ScanResponse> {
  if (images.length < 1 || images.length > 3) {
    throw new ApiError(422, "Please choose between 1 and 3 images.");
  }
  const form = new FormData();
  for (const image of images) form.append("files", image);
  return request<ScanResponse>("/api/v1/users/me/scan", {
    method: "POST",
    body: form,
    authenticated: true,
  });
}

// --- Events ----------------------------------------------------------------

/** Creates an event (owner must already have a face profile). */
export async function createEvent(
  input: CreateEventInput,
): Promise<EventResponse> {
  const body: Record<string, unknown> = { name: input.name };
  if (input.starts_at) body.starts_at = input.starts_at;
  if (input.expires_at) body.expires_at = input.expires_at;
  return request<EventResponse>("/api/v1/events", {
    method: "POST",
    body,
    authenticated: true,
  });
}

/** Lists the current user's owned/attended events (includes join_token). */
export async function listMyEvents(): Promise<EventResponse[]> {
  return request<EventResponse[]>("/api/v1/events", { authenticated: true });
}

/** Searches all events by partial name. Returns public details (no token). */
export async function searchEvents(
  q: string,
): Promise<EventPublicResponse[]> {
  return request<EventPublicResponse[]>(
    `/api/v1/events/search?q=${encodeURIComponent(q)}`,
    { authenticated: true },
  );
}

/** Joins an event via its shareable join token/link. */
export async function joinEvent(joinToken: string): Promise<EventJoinResponse> {
  return request<EventJoinResponse>(
    `/api/v1/events/join/${encodeURIComponent(joinToken)}`,
    { authenticated: true },
  );
}

/** Fetches details for one event (owner/attendee only). */
export async function getEvent(eventId: string): Promise<EventDetailResponse> {
  return request<EventDetailResponse>(
    `/api/v1/events/${encodeURIComponent(eventId)}`,
    { authenticated: true },
  );
}
