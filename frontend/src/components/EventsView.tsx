"use client";

import Link from "next/link";

import { Icon } from "@/components/ui";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  createEvent,
  joinEvent,
  listMyEvents,
  requestToJoin,
  searchEvents,
  type EventPublicResponse,
  type EventResponse,
} from "@/lib/api";

const THUMBS = [
  "linear-gradient(135deg,#ffc94d,#ff6a3d)",
  "linear-gradient(135deg,#7fb2ff,#2d5fd1)",
  "linear-gradient(135deg,#3ddc97,#16865a)",
  "linear-gradient(135deg,#ff8a9a,#d1365a)",
  "linear-gradient(135deg,#f4f2ee,#9a9893)",
];

/** Stable gradient + initial for an event "cover" tile. */
function thumbFor(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return { background: THUMBS[h % THUMBS.length], letter: name.trim()[0]?.toUpperCase() ?? "?" };
}

function closesLabel(expires: string | null): string {
  return expires ? `Closes ${new Date(expires).toLocaleString()}` : "No closing time";
}

function StatusBadge({ active, expires }: { active: boolean; expires: string | null }) {
  if (!expires) return <span className="badge badge-open">Open</span>;
  return (
    <span className={`badge ${active ? "badge-open" : "badge-closed"}`}>
      {active ? "Open" : "Closed"}
    </span>
  );
}

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
export default function EventsView({ leading }: { leading?: React.ReactNode }) {
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

  // Request-to-join (searcher): track per-event submission state.
  const [requestingEvent, setRequestingEvent] = useState<string | null>(null);
  const [requestNote, setRequestNote] = useState<Record<string, { ok: boolean; text: string }>>(
    {},
  );

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

  async function handleRequestToJoin(eventId: string) {
    setRequestingEvent(eventId);
    setRequestNote((prev) => ({ ...prev, [eventId]: undefined as never }));
    try {
      await requestToJoin(eventId);
      setRequestNote((prev) => ({
        ...prev,
        [eventId]: { ok: true, text: "Request sent! The owner will be notified." },
      }));
    } catch (err) {
      setRequestNote((prev) => ({
        ...prev,
        [eventId]: {
          ok: false,
          text: err instanceof ApiError ? err.detail : "Could not send the request.",
        },
      }));
    } finally {
      setRequestingEvent(null);
    }
  }

  const activeCount = useMemo(
    () => (mine ?? []).filter((ev) => ev.active).length,
    [mine],
  );

  const [copied, setCopied] = useState<string | null>(null);

  async function copyWithFeedback(token: string) {
    await copyLink(token);
    setCopied(token);
    setTimeout(() => setCopied((c) => (c === token ? null : c)), 1600);
  }

  return (
    <div className="grid-dash" id="events">
      {/* Left column */}
      <div className="stack">
        {leading}

        {/* Create */}
        <section className="card">
          <div className="card-header">
            <h2 className="h2">Host an event</h2>
            <span className="tile-icon" style={{ width: 36, height: 36, borderRadius: 10 }}>
              <Icon.Plus />
            </span>
          </div>
          <form onSubmit={handleCreate} className="stack">
            <div className="field">
              <label className="label" htmlFor="event-name">
                Event name
              </label>
              <input
                id="event-name"
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder="e.g. Birthday Bash"
              />
            </div>
            <div className="field">
              <label className="label" htmlFor="event-expires">
                Close after (optional)
              </label>
              <input
                id="event-expires"
                type="datetime-local"
                className="input"
                value={expires}
                onChange={(e) => setExpires(e.target.value)}
              />
              <span className="hint">
                Leave empty to keep it open. Once closed, the link stops accepting new
                attendees.
              </span>
            </div>
            <button type="submit" className="btn btn-primary" disabled={creating || !name.trim()}>
              {creating ? (
                <>
                  <span className="spinner" /> Creating…
                </>
              ) : (
                <>
                  Create event <Icon.Arrow />
                </>
              )}
            </button>
          </form>
          {createError && (
            <p className="alert alert-error" style={{ marginTop: 14 }}>
              {createError}
            </p>
          )}
        </section>

        {/* Join */}
        <section className="card">
          <div className="card-header">
            <h2 className="h2">Got an invite?</h2>
            <span className="tile-icon" style={{ width: 36, height: 36, borderRadius: 10 }}>
              <Icon.Link />
            </span>
          </div>
          <form onSubmit={handleJoin} className="input-group">
            <div className="input-icon">
              <Icon.Link />
              <input
                className="input"
                value={joinInput}
                onChange={(e) => setJoinInput(e.target.value)}
                placeholder="Paste a join link or token"
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={joining || !joinInput.trim()}>
              {joining ? "Joining…" : "Join"}
            </button>
          </form>
          {joinMessage && (
            <p
              className={`alert ${joinMessage.ok ? "alert-ok" : "alert-error"}`}
              style={{ marginTop: 14 }}
            >
              {joinMessage.text}
            </p>
          )}
        </section>
      </div>

      {/* Right column */}
      <div className="stack">
        {/* My events */}
        <section className="card">
          <div className="card-header">
            <h2 className="h2">Your events</h2>
            {mine != null && <span className="badge badge-open">{activeCount} active</span>}
          </div>
          {mineError && <p className="alert alert-error">{mineError}</p>}
          {mine === null && !mineError ? (
            <div className="row muted small">
              <span className="spinner" /> Loading…
            </div>
          ) : null}
          {mine && mine.length === 0 ? (
            <div className="empty">
              <Icon.Ticket size={28} />
              <span>You haven&apos;t created or joined any events yet.</span>
            </div>
          ) : null}
          {mine?.map((ev) => {
            const t = thumbFor(ev.name);
            return (
              <div key={ev.id} className="event-row">
                <Link href={`/events/${ev.id}`} className="event-thumb" style={{ background: t.background }}>
                  {t.letter}
                </Link>
                <div style={{ minWidth: 0 }}>
                  <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
                    <Link href={`/events/${ev.id}`} className="event-name">
                      {ev.name}
                    </Link>
                    <StatusBadge active={ev.active} expires={ev.expires_at} />
                  </div>
                  <div className="meta">
                    <span>
                      <Icon.Clock size={13} /> {closesLabel(ev.expires_at)}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => copyWithFeedback(ev.join_token)}
                  title={joinLinkFor(ev.join_token)}
                >
                  {copied === ev.join_token ? (
                    <>
                      <Icon.Check size={15} /> Copied
                    </>
                  ) : (
                    <>
                      <Icon.Copy size={15} /> Invite link
                    </>
                  )}
                </button>
              </div>
            );
          })}
        </section>

        {/* Search */}
        <section className="card">
          <div className="card-header">
            <h2 className="h2">Find an event</h2>
          </div>
          <form onSubmit={handleSearch} className="input-group">
            <div className="input-icon">
              <Icon.Search />
              <input
                className="input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search public events by name…"
              />
            </div>
            <button type="submit" className="btn" disabled={searching || !query.trim()}>
              {searching ? <span className="spinner" /> : "Search"}
            </button>
          </form>
          {results.length > 0 && (
            <div style={{ marginTop: 14 }}>
              {results.map((ev) => {
                const t = thumbFor(ev.name);
                return (
                  <div key={ev.id} className="event-row">
                    <span className="event-thumb" style={{ background: t.background }}>
                      {t.letter}
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
                        <span className="event-name">{ev.name}</span>
                        <StatusBadge active={ev.active} expires={ev.expires_at} />
                      </div>
                      <div className="meta">
                        <span>
                          <Icon.Clock size={13} /> {closesLabel(ev.expires_at)}
                        </span>
                      </div>
                      {requestNote[ev.id] && (
                        <p
                          className="small"
                          style={{
                            marginTop: 6,
                            color: requestNote[ev.id]?.ok ? "var(--ok)" : "var(--danger)",
                          }}
                        >
                          {requestNote[ev.id]?.text}
                        </p>
                      )}
                    </div>
                    {ev.active ? (
                      <button
                        type="button"
                        className="btn btn-sm btn-primary"
                        onClick={() => handleRequestToJoin(ev.id)}
                        disabled={requestingEvent === ev.id}
                      >
                        {requestingEvent === ev.id ? "Requesting…" : "Request to join"}
                      </button>
                    ) : (
                      <span className="muted small">Not accepting members</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
