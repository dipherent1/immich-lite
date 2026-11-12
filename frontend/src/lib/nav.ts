// Small navigation helpers shared by the auth / onboarding / join flow.

/**
 * Returns `raw` only if it's a same-origin path ("/foo"), otherwise `fallback`.
 * Guards the `?next=` param against open redirects ("//evil.com", "https://…").
 */
export function safeNext(raw: string | null | undefined, fallback = "/dashboard"): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) {
    return fallback;
  }
  return raw;
}

/** Reads `?next=` from the current URL (client only), sanitised. */
export function nextFromLocation(fallback = "/dashboard"): string {
  if (typeof window === "undefined") return fallback;
  return safeNext(new URLSearchParams(window.location.search).get("next"), fallback);
}

/** `/onboarding?next=<next>` — the face-scan step, returning to `next` afterwards. */
export function onboardingHref(next: string): string {
  return `/onboarding?next=${encodeURIComponent(safeNext(next))}`;
}

export function joinLinkFor(token: string): string {
  return `${window.location.origin}/join/${token}`;
}

export function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join("") || "?"
  );
}
