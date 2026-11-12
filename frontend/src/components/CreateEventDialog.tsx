"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "@/components/ui";
import { ApiError, createEvent } from "@/lib/api";
import { EVENT_LIFETIME_HOURS } from "@/lib/lifetime";

/** Modal form for hosting a new event. On success navigates to the event. */
export default function CreateEventDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      // The server sets the expiry (EVENT_LIFETIME_HOURS after creation).
      const event = await createEvent({ name: name.trim() });
      router.push(`/events/${event.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create the event.");
      setCreating(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <form
        className="modal card stack"
        onSubmit={handleCreate}
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-event-title"
      >
        <div className="card-header" style={{ marginBottom: 4 }}>
          <h2 className="h2" id="new-event-title">
            New event
          </h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <Icon.X />
          </button>
        </div>

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
            autoFocus
            placeholder="e.g. Birthday Bash"
          />
        </div>

        <p className="lifetime-note">
          <Icon.Clock size={16} />
          <span>
            Events last <strong>{EVENT_LIFETIME_HOURS} hours</strong>. After that the event and
            all its photos are permanently deleted, so guests should download what they want to
            keep. Everyone gets a reminder 20 minutes before.
          </span>
        </p>

        {error && <p className="alert alert-error">{error}</p>}

        <button type="submit" className="btn btn-primary btn-lg" disabled={creating || !name.trim()}>
          {creating ? (
            <>
              <span className="spinner" /> Creating…
            </>
          ) : (
            "Create event"
          )}
        </button>
      </form>
    </div>
  );
}
