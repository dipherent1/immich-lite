"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Brand, Icon } from "@/components/ui";
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

  return (
    <main className="center-page grain">
      <div className="stars" />
      <div
        className="glow"
        style={{
          width: 520,
          height: 520,
          left: "50%",
          top: "50%",
          transform: "translate(-50%,-50%)",
          background: "radial-gradient(circle, rgba(255,150,30,0.45), transparent 65%)",
          zIndex: -1,
        }}
      />
      <div className="center-card card">
        <Brand />
        <span className={`scan-ring ${error ? "error" : "missing"}`} style={{ marginTop: 8 }}>
          {error ? <Icon.X size={30} /> : authed === false ? <Icon.Ticket size={30} /> : <span className="spinner" />}
        </span>
        <h1 className="h1" style={{ fontSize: "1.8rem" }}>
          {error ? "Couldn't join" : authed === false ? "You're invited" : "Joining event…"}
        </h1>

        {authed === false && (
          <>
            <p className="muted">Log in or create an account to join this event and get your photos.</p>
            <div className="row" style={{ justifyContent: "center", marginTop: 4 }}>
              <Link href={loginHref} className="btn btn-primary">
                Log in
              </Link>
              <Link
                href={`/register?next=${encodeURIComponent(`/join/${token}`)}`}
                className="btn"
              >
                Create account
              </Link>
            </div>
          </>
        )}

        {busy && authed && !error ? <p className="muted">Hang tight, adding you to the guest list.</p> : null}

        {error && (
          <>
            <p className="alert alert-error">{error}</p>
            <Link href="/dashboard" className="btn">
              Back to your dashboard
            </Link>
          </>
        )}
      </div>
    </main>
  );
}
