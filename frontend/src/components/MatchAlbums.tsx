"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  ApiError,
  getEventPhotoObjectUrl,
  getMyMatchEvents,
  type MatchEventResponse,
} from "@/lib/api";
import { endsWithin, timeLeftLabel } from "@/lib/lifetime";
import { Icon } from "@/components/ui";

const URGENT_MINUTES = 20;

function Album({
  album,
  coverUrl,
  now,
}: {
  album: MatchEventResponse;
  coverUrl?: string;
  now: number;
}) {
  const [coverBroken, setCoverBroken] = useState(false);
  const showCover = coverUrl && !coverBroken;
  const urgent = album.event_expires_at != null && endsWithin(album.event_expires_at, URGENT_MINUTES, now);
  return (
    <Link href={`/matches/${album.event_id}`} className="event-card album-card">
      <div className="event-cover">
        {showCover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={coverUrl} alt="" onError={() => setCoverBroken(true)} />
        ) : (
          <span className="event-cover-letter">{album.event_name.trim()[0]?.toUpperCase() ?? "?"}</span>
        )}
        <span className="album-count">
          {album.photo_count} photo{album.photo_count === 1 ? "" : "s"}
        </span>
      </div>
      <div className="event-card-body">
        <div style={{ minWidth: 0 }}>
          <span className="event-name">{album.event_name}</span>
          {album.event_expires_at && (
            <div className="album-meta">
              <span className={`expiry-chip${urgent ? " urgent" : ""}`}>
                <Icon.Clock size={12} /> Deleted in {timeLeftLabel(album.event_expires_at, now)}
              </span>
            </div>
          )}
        </div>
        <Icon.Arrow />
      </div>
    </Link>
  );
}

/**
 * "My photos": one album per event you have matched photos in. Click an album
 * to see (and download) its photos. Events ending within 20 minutes get a red
 * alert at the top, since their photos are about to be deleted.
 */
export default function MatchAlbums() {
  const [albums, setAlbums] = useState<MatchEventResponse[] | null>(null);
  const [coverUrls, setCoverUrls] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const objectUrlsRef = useRef<string[]>([]);

  useEffect(() => {
    const urls = objectUrlsRef.current;
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  // Keep the "deleted in …" labels fresh without a reload.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    getMyMatchEvents()
      .then((items) => {
        setAlbums(items);
        for (const a of items) {
          getEventPhotoObjectUrl(a.event_id, a.cover_photo_id)
            .then((url) => {
              objectUrlsRef.current.push(url);
              setCoverUrls((prev) => ({ ...prev, [a.event_id]: url }));
            })
            .catch(() => {
              // A failing cover falls back to the letter tile.
            });
        }
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Could not load your photos."),
      );
  }, []);

  const urgent = (albums ?? []).filter(
    (a) => a.event_expires_at != null && endsWithin(a.event_expires_at, URGENT_MINUTES, now),
  );

  return (
    <section>
      {error && <p className="alert alert-error">{error}</p>}

      {urgent.length > 0 && (
        <div className="album-alerts" role="alert">
          {urgent.map((a) => (
            <Link key={a.event_id} href={`/matches/${a.event_id}`} className="expiry-banner urgent">
              <Icon.Clock size={18} />
              <span>
                <strong>
                  {a.event_name} is deleted in {timeLeftLabel(a.event_expires_at!, now)}.
                </strong>{" "}
                Open it and download your photos before they&apos;re gone.
              </span>
            </Link>
          ))}
        </div>
      )}

      {albums === null && !error && (
        <div className="event-grid">
          {[0, 1, 2].map((i) => (
            <div key={i} className="event-card skeleton" aria-hidden />
          ))}
        </div>
      )}

      {albums && albums.length === 0 && (
        <div className="empty" style={{ padding: "72px 24px" }}>
          <span className="scan-ring missing">
            <Icon.Face size={30} />
          </span>
          <strong style={{ color: "var(--text)", fontSize: "1.05rem" }}>No matches yet</strong>
          <span style={{ maxWidth: 360 }}>
            When photos with your face are uploaded to events you&apos;ve joined, they&apos;ll
            show up here, one album per event.
          </span>
          <Link href="/dashboard" className="btn btn-sm" style={{ marginTop: 6 }}>
            Go to dashboard
          </Link>
        </div>
      )}

      {albums && albums.length > 0 && (
        <div className="event-grid">
          {albums.map((a) => (
            <Album key={a.event_id} album={a} coverUrl={coverUrls[a.event_id]} now={now} />
          ))}
        </div>
      )}
    </section>
  );
}
