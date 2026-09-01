"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { ApiError, isAuthenticated, joinEvent } from "@/lib/api";

function subscribe() {
  return () => {};
}

/**
 * Shareable join landing page: /join/<token>.
 *
 * - If the visitor isn't logged in they're pointed to the login page (which
 *   returns them here via the ?next= param).
 * - Otherwise it joins the event by token and redirects to the event preview.
 * - On error, shows the message with a link back to the dashboard.
 *
 * Auth state is read via useSyncExternalStore so the server-rendered HTML and
 * the client's first render agree during hydration (server snapshot = null),
 * avoiding a hydration mismatch.
 */
export default function JoinPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token ?? "";
  const router = useRouter();

  const authed = useSyncExternalStore(
    subscribe,
    () => isAuthenticated(),
    () => null,
  );

  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authed !== true || !token) return;
    joinEvent(token)
      .then((res) => {
        router.push(`/events/${res.event.id}`);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.detail : "Could not join that event.");
        setBusy(false);
      });
  }, [authed, token, router]);

  const loginHref = `/login?next=${encodeURIComponent(`/join/${token}`)}`;

  if (authed === false) {
    return (
      <main style={{ padding: 40, maxWidth: 520 }}>
        <h1>Join an event</h1>
        <p>You need to be logged in to join this event.</p>
        <p style={{ marginTop: 16 }}>
          <Link href={loginHref}>Log in</Link>&nbsp;·&nbsp;
          <Link href={`/register?next=${encodeURIComponent(`/join/${token}`)}`}>
            Register
          </Link>
        </p>
      </main>
    );
  }

  return (
    <main style={{ padding: 40, maxWidth: 520 }}>
      <h1>Join an event</h1>
      {busy && authed ? <p>Joining…</p> : null}
      {error && (
        <>
          <p style={{ margin: "16px 0", color: "#cf222e" }}>{error}</p>
          <p>
            <Link href="/dashboard">Back to your dashboard</Link>
          </p>
        </>
      )}
    </main>
  );
}
