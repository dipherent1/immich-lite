"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import PublicEventView from "@/components/PublicEventView";
import { Brand, Icon } from "@/components/ui";
import { ApiError, isAuthenticated, joinEvent } from "@/lib/api";

function subscribe() {
  return () => {};
}

/**
 * Shareable join landing page: /join/<token>.
 *
 * - Logged out: shows the event's photos as small previews (no account needed)
 *   with a call-to-action to sign up / log in so they get matched. Both links
 *   return here via ?next= and, after the face scan, the visitor is joined.
 * - Logged in: joins the event by token and redirects to the event page.
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

  if (authed === false && token) {
    return <PublicEventView token={token} />;
  }

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
          {error ? <Icon.X size={30} /> : <span className="spinner" />}
        </span>
        <h1 className="h1" style={{ fontSize: "1.8rem" }}>
          {error ? "Couldn't join" : "Joining event…"}
        </h1>

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
