"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  createEvent,
  joinEvent,
  listMyEvents,
  searchEvents,
  type EventPublicResponse,
  type EventResponse,
} from "@/lib/api";

function joinLinkFor(token: string): string {
  return `${window.location.origin}/join/${token}`;
}

/** Pulls a raw join token out of whatever the user pasted (raw token or a url). */
function extractToken(input: string): string {
  const trimmed = input.trim();
  const lastSegment = trimmed.split("/").filter(Boolean).pop() ?? "";
  return lastSegment || trimmed;
}

/**
 * Events hub for a signed-in user:
 *   - Create an event and get a shareable join link.
 *   - List the user's own/attended events.
 *   - Search public events by name (results intentionally carry no token).
 *   - Join via a shared link/token.
 */
export default function EventsView() {
  const router = useRouter();
  const [mine, setMine] = useState<EventResponse[] | null>(null);
  const [mineError, setMineError] = useState<string | null>(null);

  // Create
  const [name, setName] = useState("");
  const [expires, setExpires] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Search
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<EventPublicResponse[]>([]);
  const [searching, setSearching] = useState(false);

  // Join
  const [joinInput, setJoinInput] = useState("");
  const [joining, setJoining] = useState(false);
  const [joinMessage, setJoinMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const refreshMine = useCallback(() => {
    listMyEvents()
      .then(setMine)
      .catch((err) =>
        setMineError(err instanceof ApiError ? err.detail : "Failed to load your events."),
      );
  }, []);

  useEffect(() => {
    refreshMine();
  }, [refreshMine]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const input: { name: string; expires_at?: string | null } = { name };
      if (expires) input.expires_at = new Date(expires).toISOString();
      const event = await createEvent(input);
      router.push(`/events/${event.id}`);
    } catch (err) {
      setCreateError(
        err instanceof ApiError ? err.detail : "Failed to create the event.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setSearching(true);
    try {
      setResults(await searchEvents(query));
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  async function handleJoin(e: React.FormEvent) {
    e.preventDefault();
    setJoining(true);
    setJoinMessage(null);
    try {
      const res = await joinEvent(extractToken(joinInput));
      setJoinInput("");
      refreshMine();
      router.push(`/events/${res.event.id}`);
    } catch (err) {
      setJoinMessage({
        ok: false,
        text: err instanceof ApiError ? err.detail : "Could not join that event.",
      });
    } finally {
      setJoining(false);
    }
  }

  async function copyLink(token: string) {
    try {
      await navigator.clipboard.writeText(joinLinkFor(token));
    } catch {
      // Clipboard may be unavailable; ignore.
    }
  }

  const activeCount = useMemo(
    () => (mine ?? []).filter((ev) => ev.active).length,
    [mine],
  );

  const styles = {
    section: {
      marginTop: 24,
      border: "1px solid #ddd",
      borderRadius: 8,
      padding: 16,
      maxWidth: 640,
    } as const,
    title: { marginTop: 0, fontSize: "1.1rem" } as const,
    field: { display: "flex", flexDirection: "column" as const, gap: 6, marginBottom: 12 } as const,
    label: { fontWeight: 600, fontSize: "0.85rem" } as const,
    input: {
      padding: 8,
      borderRadius: 6,
      border: "1px solid #ccc",
      fontSize: "0.95rem",
    } as const,
    row: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" as const } as const,
    card: {
      border: "1px solid #e2e2e2",
      borderRadius: 8,
      padding: 12,
      marginBottom: 10,
    } as const,
    error: { color: "#cf222e", margin: "8px 0 0" } as const,
    ok: { color: "#1a7f37", margin: "8px 0 0", fontWeight: 600 } as const,
    muted: { color: "#666", fontSize: "0.85rem", margin: "4px 0 0" } as const,
    badge: (active: boolean) => ({
      display: "inline-block",
      padding: "2px 10px",
      borderRadius: 12,
      fontSize: "0.78rem",
      fontWeight: 600,
      background: active ? "#e6f6ee" : "#f1f1f1",
      color: active ? "#1a7f37" : "#666",
    }),
  } as const;

  return (
    <>
      {/* Create */}
      <section style={styles.section}>
        <h2 style={styles.title}>Create an event</h2>
        <form onSubmit={handleCreate}>
          <div style={styles.field}>
            <label style={styles.label} htmlFor="event-name">
              Name
            </label>
            <input
              id="event-name"
              style={styles.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="e.g. Birthday Bash"
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label} htmlFor="event-expires">
              Close after (optional)
            </label>
            <input
              id="event-expires"
              type="datetime-local"
              style={styles.input}
              value={expires}
              onChange={(e) => setExpires(e.target.value)}
            />
            <span style={styles.muted}>
              Leave empty to keep the event open. Once closed, the link stops
              accepting new attendees.
            </span>
          </div>
          <button type="submit" disabled={creating || !name.trim()}>
            {creating ? "Creating…" : "Create event"}
          </button>
        </form>
        {createError && <p style={styles.error}>{createError}</p>}
      </section>

      {/* My events */}
      <section style={styles.section}>
        <h2 style={styles.title}>
          Your events{mine != null ? ` (${activeCount} active)` : ""}
        </h2>
        {mineError && <p style={styles.error}>{mineError}</p>}
        {mine === null && !mineError ? <p style={styles.muted}>Loading…</p> : null}
        {mine && mine.length === 0 ? (
          <p style={styles.muted}>
            You haven’t created or joined any events yet.
          </p>
        ) : null}
        {mine?.map((ev) => (
          <div key={ev.id} style={styles.card}>
            <div style={{ ...styles.row, justifyContent: "space-between" }}>
              <Link
                href={`/events/${ev.id}`}
                style={{ fontWeight: 600, textDecoration: "underline" }}
              >
                {ev.name}
              </Link>
              {ev.expires_at ? (
                <span style={styles.badge(ev.active)}>
                  {ev.active ? "Open" : "Closed"}
                </span>
              ) : (
                <span style={styles.badge(true)}>Open (no end)</span>
              )}
            </div>
            <p style={styles.muted}>
              {ev.expires_at
                ? `Closes ${new Date(ev.expires_at).toLocaleString()}`
                : "No closing time set"}
            </p>
            <div style={{ ...styles.row, marginTop: 6 }}>
              <code
                style={{
                  background: "#f4f4f4",
                  padding: "4px 6px",
                  borderRadius: 6,
                  fontSize: "0.8rem",
                  flex: 1,
                  wordBreak: "break-all",
                }}
              >
                {joinLinkFor(ev.join_token)}
              </code>
              <button onClick={() => copyLink(ev.join_token)}>Copy</button>
            </div>
          </div>
        ))}
      </section>

      {/* Search */}
      <section style={styles.section}>
        <h2 style={styles.title}>Search public events</h2>
        <form onSubmit={handleSearch} style={{ ...styles.row }}>
          <input
            style={{ ...styles.input, flex: 1 }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name…"
          />
          <button type="submit" disabled={searching || !query.trim()}>
            Search
          </button>
        </form>
        {results.map((ev) => (
          <div key={ev.id} style={styles.card}>
            <div style={{ ...styles.row, justifyContent: "space-between" }}>
              <span style={{ fontWeight: 600 }}>{ev.name}</span>
              {ev.expires_at ? (
                <span style={styles.badge(ev.active)}>
                  {ev.active ? "Open" : "Closed"}
                </span>
              ) : (
                <span style={styles.badge(true)}>Open</span>
              )}
            </div>
            <p style={styles.muted}>
              {ev.expires_at
                ? `Closes ${new Date(ev.expires_at).toLocaleString()}`
                : "No closing time set"}
            </p>
            <p style={styles.muted}>
              Requesting to join is coming soon — you can join if the owner
              shares their link with you.
            </p>
          </div>
        ))}
        {searching ? <p style={styles.muted}>Searching…</p> : null}
      </section>

      {/* Join */}
      <section style={styles.section}>
        <h2 style={styles.title}>Join an event</h2>
        <form onSubmit={handleJoin} style={{ ...styles.row }}>
          <input
            style={{ ...styles.input, flex: 1 }}
            value={joinInput}
            onChange={(e) => setJoinInput(e.target.value)}
            placeholder="Paste a join link or token"
          />
          <button type="submit" disabled={joining || !joinInput.trim()}>
            {joining ? "Joining…" : "Join"}
          </button>
        </form>
        {joinMessage && (
          <p style={joinMessage.ok ? styles.ok : styles.error}>
            {joinMessage.text}
          </p>
        )}
      </section>
    </>
  );
}
