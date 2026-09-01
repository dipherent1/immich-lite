"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import RequireAuth from "@/components/RequireAuth";
import { ApiError, getEvent, type EventDetailResponse } from "@/lib/api";

function joinLinkFor(token: string): string {
  return `${window.location.origin}/join/${token}`;
}

function EventPreviewContent() {
  const params = useParams<{ id: string }>();
  const eventId = params?.id ?? "";

  const [event, setEvent] = useState<EventDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!eventId) return;
    getEvent(eventId)
      .then(setEvent)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Could not load this event."),
      );
  }, [eventId]);

  async function copyLink(token: string) {
    try {
      await navigator.clipboard.writeText(joinLinkFor(token));
    } catch {
      // Clipboard may be unavailable; ignore.
    }
  }

  const styles = {
    card: {
      border: "1px solid #e2e2e2",
      borderRadius: 8,
      padding: 16,
      maxWidth: 520,
    } as const,
    muted: { color: "#666", margin: "6px 0" } as const,
    badge: (active: boolean) => ({
      display: "inline-block",
      padding: "2px 10px",
      borderRadius: 12,
      fontSize: "0.8rem",
      fontWeight: 600,
      background: active ? "#e6f6ee" : "#f1f1f1",
      color: active ? "#1a7f37" : "#666",
    }),
  } as const;

  return (
    <main style={{ padding: 40 }}>
      <p>
        <Link href="/dashboard">← Dashboard</Link>
      </p>

      {error && <p style={{ color: "#cf222e" }}>{error}</p>}

      {!event && !error ? <p>Loading event…</p> : null}

      {event && (
        <>
          <h1 style={{ marginTop: 8 }}>{event.name}</h1>
          <p>
            {event.expires_at ? (
              <span style={styles.badge(event.active)}>
                {event.active ? "Open" : "Closed"}
              </span>
            ) : (
              <span style={styles.badge(true)}>Open (no end)</span>
            )}
          </p>

          <dl style={{ marginTop: 16 }}>
            <dt style={{ fontWeight: 600 }}>Created</dt>
            <dd style={{ margin: "0 0 12px" }}>
              {new Date(event.created_at).toLocaleString()}
            </dd>
            <dt style={{ fontWeight: 600 }}>Starts</dt>
            <dd style={{ margin: "0 0 12px" }}>
              {new Date(event.starts_at).toLocaleString()}
            </dd>
            <dt style={{ fontWeight: 600 }}>Closes</dt>
            <dd style={{ margin: "0 0 12px" }}>
              {event.expires_at
                ? new Date(event.expires_at).toLocaleString()
                : "No closing time set"}
            </dd>
            <dt style={{ fontWeight: 600 }}>Attendees</dt>
            <dd style={{ margin: "0 0 12px" }}>
              {event.attendee_count}
            </dd>
          </dl>

          <div style={{ marginTop: 16, ...styles.card }}>
            <p style={{ margin: 0, fontWeight: 600 }}>Invite link</p>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
              <code
                style={{
                  background: "#f4f4f4",
                  padding: "6px 8px",
                  borderRadius: 6,
                  flex: 1,
                  fontSize: "0.85rem",
                  wordBreak: "break-all",
                }}
              >
                {joinLinkFor(event.join_token)}
              </code>
              <button onClick={() => copyLink(event.join_token)}>Copy</button>
            </div>
          </div>
        </>
      )}
    </main>
  );
}

export default function EventPreviewPage() {
  return (
    <RequireAuth>
      <EventPreviewContent />
    </RequireAuth>
  );
}
