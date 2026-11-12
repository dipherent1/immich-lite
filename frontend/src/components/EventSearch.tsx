"use client";

import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui";
import { ApiError, requestToJoin, searchEvents, type EventPublicResponse } from "@/lib/api";

/**
 * Compact "find a public event" search. Results drop down under the input;
 * each active event offers "Request to join" (the owner approves it).
 * Search results intentionally carry no join token.
 */
export default function EventSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<EventPublicResponse[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [requesting, setRequesting] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, { ok: boolean; text: string }>>({});
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setResults(null);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      setResults(await searchEvents(query.trim()));
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  async function handleRequest(eventId: string) {
    setRequesting(eventId);
    try {
      await requestToJoin(eventId);
      setNotes((n) => ({ ...n, [eventId]: { ok: true, text: "Request sent" } }));
    } catch (err) {
      setNotes((n) => ({
        ...n,
        [eventId]: {
          ok: false,
          text: err instanceof ApiError ? err.detail : "Could not send the request.",
        },
      }));
    } finally {
      setRequesting(null);
    }
  }

  return (
    <div className="event-search" ref={ref}>
      <form onSubmit={handleSearch} className="input-icon">
        {searching ? <span className="spinner" /> : <Icon.Search />}
        <input
          className="input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Find a public event…"
          aria-label="Search public events"
        />
      </form>

      {results && (
        <div className="search-pop">
          {results.length === 0 ? (
            <p className="muted small" style={{ padding: 16, textAlign: "center" }}>
              No events match “{query}”.
            </p>
          ) : (
            results.map((ev) => {
              const note = notes[ev.id];
              return (
                <div key={ev.id} className="search-row">
                  <div style={{ minWidth: 0 }}>
                    <span className="event-name">{ev.name}</span>
                    {note && (
                      <span
                        className="small"
                        style={{ color: note.ok ? "var(--ok)" : "var(--danger)" }}
                      >
                        {note.text}
                      </span>
                    )}
                  </div>
                  {!ev.active ? (
                    <span className="muted small">Closed</span>
                  ) : note?.ok ? (
                    <Icon.Check size={18} style={{ color: "var(--ok)" }} />
                  ) : (
                    <button
                      type="button"
                      className="btn btn-sm btn-primary"
                      onClick={() => handleRequest(ev.id)}
                      disabled={requesting === ev.id}
                    >
                      {requesting === ev.id ? "Sending…" : "Request to join"}
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
