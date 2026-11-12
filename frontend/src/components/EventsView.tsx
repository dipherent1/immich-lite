"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import CreateEventDialog from "@/components/CreateEventDialog";
import { Icon } from "@/components/ui";
import {
  ApiError,
  getEventPhotoObjectUrl,
  listMyEvents,
  type EventResponse,
} from "@/lib/api";
import { joinLinkFor, onboardingHref } from "@/lib/nav";

const THUMBS = [
  "linear-gradient(135deg,#ffc94d,#ff6a3d)",
  "linear-gradient(135deg,#7fb2ff,#2d5fd1)",
  "linear-gradient(135deg,#3ddc97,#16865a)",
  "linear-gradient(135deg,#ff8a9a,#d1365a)",
  "linear-gradient(135deg,#f4f2ee,#9a9893)",
];

/** Stable gradient + initial for an event without a (loadable) cover. */
function thumbFor(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return { background: THUMBS[h % THUMBS.length], letter: name.trim()[0]?.toUpperCase() ?? "?" };
}

function closesLabel(expires: string | null, active: boolean): string {
  if (!expires) return "Open";
  if (!active) return "Closed";
  return `Closes ${new Date(expires).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })}`;
}

function EventCard({ ev, coverUrl }: { ev: EventResponse; coverUrl?: string }) {
  const [coverBroken, setCoverBroken] = useState(false);
  const [copied, setCopied] = useState(false);
  const t = thumbFor(ev.name);
  const showCover = coverUrl && !coverBroken;
  const isOpen = ev.active || !ev.expires_at;

  async function copy() {
    try {
      await navigator.clipboard.writeText(joinLinkFor(ev.join_token));
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard may be unavailable (insecure origin); nothing useful to do.
    }
  }

  return (
    <article className="event-card">
      <Link
        href={`/events/${ev.id}`}
        className="event-cover"
        style={showCover ? undefined : { background: t.background }}
        aria-label={`Open ${ev.name}`}
      >
        {showCover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={coverUrl} alt="" onError={() => setCoverBroken(true)} />
        ) : (
          <span className="event-cover-letter">{t.letter}</span>
        )}
      </Link>
      <div className="event-card-body">
        <div style={{ minWidth: 0 }}>
          <Link href={`/events/${ev.id}`} className="event-name">
            {ev.name}
          </Link>
          <span className={`event-status${isOpen ? " open" : ""}`}>
            {closesLabel(ev.expires_at, ev.active)}
          </span>
        </div>
        {isOpen && (
          <button
            type="button"
            className={`btn btn-sm${copied ? " btn-ok" : ""}`}
            onClick={copy}
            title="Copy the invite link — anyone who opens it joins this event"
          >
            {copied ? (
              <>
                <Icon.Check size={15} /> Copied
              </>
            ) : (
              <>
                <Icon.Link size={15} /> Copy link
              </>
            )}
          </button>
        )}
      </div>
    </article>
  );
}

/**
 * The dashboard body: a grid of large event cards (hosted + joined), led by a
 * "New event" tile. Each card opens the event; "Copy link" copies the invite
 * URL (/join/<token>) — opening that link is the whole join flow.
 */
export default function EventsView({ needsFaceScan = false }: { needsFaceScan?: boolean }) {
  const router = useRouter();
  const [mine, setMine] = useState<EventResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [coverUrls, setCoverUrls] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);
  const objectUrlsRef = useRef<string[]>([]);

  useEffect(() => {
    const urls = objectUrlsRef.current;
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  const load = useCallback(() => {
    listMyEvents()
      .then((events) => {
        setMine(events);
        for (const ev of events) {
          if (!ev.cover_photo_id) continue;
          getEventPhotoObjectUrl(ev.id, ev.cover_photo_id)
            .then((url) => {
              objectUrlsRef.current.push(url);
              setCoverUrls((prev) => ({ ...prev, [ev.id]: url }));
            })
            .catch(() => {
              // A failing cover falls back to the gradient tile.
            });
        }
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Failed to load your events."),
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      {error && <p className="alert alert-error" style={{ marginBottom: 16 }}>{error}</p>}

      <div className="event-grid">
        {/* Hosting requires a face profile (enforced by the API), so send
            un-enrolled users through the scan first instead of a failing form. */}
        <button
          type="button"
          className="event-card new-event-card"
          onClick={() =>
            needsFaceScan ? router.push(onboardingHref("/dashboard")) : setCreating(true)
          }
        >
          <span className="new-event-icon">
            <Icon.Plus size={26} />
          </span>
          <strong>New event</strong>
          <span className="muted small">
            {needsFaceScan ? "Scan your face first, then host" : "Get a link to share with guests"}
          </span>
        </button>

        {mine === null && !error
          ? [0, 1].map((i) => <div key={i} className="event-card skeleton" aria-hidden />)
          : null}

        {mine?.map((ev) => <EventCard key={ev.id} ev={ev} coverUrl={coverUrls[ev.id]} />)}
      </div>

      {mine?.length === 0 && (
        <p className="muted small" style={{ marginTop: 18 }}>
          No events yet. Create one, or open an invite link someone sent you.
        </p>
      )}

      {creating && <CreateEventDialog onClose={() => setCreating(false)} />}
    </>
  );
}
