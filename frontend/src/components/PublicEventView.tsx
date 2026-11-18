"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Brand, Icon } from "@/components/ui";
import {
  ApiError,
  getPublicEvent,
  getPublicPhotos,
  publicPreviewUrl,
  type PublicEventView as PublicEventData,
} from "@/lib/api";
import { timeLeftLabel } from "@/lib/lifetime";

const PAGE_SIZE = 24;

type LoadError = { status: number; message: string };

/**
 * What a visitor sees when they open an event's share link without an account:
 * the event's photos as small read-only previews (no select, no download) and a
 * sticky call-to-action to sign up / log in. Both links carry ?next=/join/<token>,
 * so after sign-up the visitor goes through the face scan and is then joined.
 *
 * Previews are plain `<img src>` (no auth header needed), so the browser lazy-
 * loads and caches them. Only processed photos are listed by the API.
 */
export default function PublicEventView({ token }: { token: string }) {
  const [event, setEvent] = useState<PublicEventData | null>(null);
  const [ids, setIds] = useState<string[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<LoadError | null>(null);
  const [broken, setBroken] = useState<Record<string, true>>({});
  const [now, setNow] = useState(() => Date.now());
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  // State is only set inside promise callbacks (this repo's lint rule).
  useEffect(() => {
    Promise.all([getPublicEvent(token), getPublicPhotos(token, 0, PAGE_SIZE)])
      .then(([ev, page]) => {
        setEvent(ev);
        setIds(page.items.map((p) => p.id));
        setHasMore(page.has_more);
        setNextOffset(page.next_offset);
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        setError({
          status: err instanceof ApiError ? err.status : 0,
          message: err instanceof ApiError ? err.detail : "Could not load this event.",
        });
        setLoading(false);
      });
  }, [token, reloadKey]);

  const loadMore = useCallback(() => {
    setLoadingMore(true);
    getPublicPhotos(token, nextOffset, PAGE_SIZE)
      .then((page) => {
        setIds((prev) => [...prev, ...page.items.map((p) => p.id)]);
        setHasMore(page.has_more);
        setNextOffset(page.next_offset);
      })
      .catch(() => {
        // Leave the button in place so they can try again.
      })
      .finally(() => setLoadingMore(false));
  }, [token, nextOffset]);

  const next = encodeURIComponent(`/join/${token}`);
  const registerHref = `/register?next=${next}`;
  const loginHref = `/login?next=${next}`;

  return (
    <>
      <div className="app-bg" aria-hidden />
      <header className="site-header">
        <div className="container site-header-inner">
          <Brand />
          <div className="header-actions">
            <Link className="btn btn-ghost btn-sm" href={loginHref}>
              Log in
            </Link>
            <Link className="btn btn-primary btn-sm hide-mobile" href={registerHref}>
              Sign up
            </Link>
          </div>
        </div>
      </header>

      <main className="public-page">
        {loading && !error && (
          <>
            <div className="public-hero">
              <div className="event-card skeleton" style={{ minHeight: 90 }} aria-hidden />
            </div>
            <div className="photo-grid">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="photo">
                  <div className="photo-placeholder" />
                </div>
              ))}
            </div>
          </>
        )}

        {error && (
          <div className="public-state">
            <span className="scan-ring error">
              <Icon.X size={30} />
            </span>
            <h2>
              {error.status === 404
                ? "We can't find that event"
                : error.status === 410
                  ? "This event has ended"
                  : "Couldn't load this event"}
            </h2>
            <p style={{ maxWidth: 380 }}>
              {error.status === 404
                ? "The link may be mistyped, or the event was deleted. Events are deleted automatically a few hours after they start."
                : error.status === 410
                  ? "Its photos have been or are about to be deleted. Ask the host for a new event link next time."
                  : error.message}
            </p>
            {error.status !== 404 && error.status !== 410 && (
              <button className="btn btn-sm" onClick={() => {
                setLoading(true);
                setReloadKey((k) => k + 1);
              }}>
                Try again
              </button>
            )}
          </div>
        )}

        {event && !error && (
          <>
            <div className="public-hero">
              <span className="eyebrow">You&apos;re invited</span>
              <h1 className="h1">{event.name}</h1>
              <div className="public-meta">
                <span>
                  {event.photo_count} photo{event.photo_count === 1 ? "" : "s"}
                </span>
                {event.expires_at && (
                  <span className="expiry-chip">
                    <Icon.Clock size={12} /> Deleted in {timeLeftLabel(event.expires_at, now)}
                  </span>
                )}
              </div>
            </div>

            <p className="public-notice">
              <Icon.Images size={16} />
              <span>
                You&apos;re viewing small previews. Sign up and we&apos;ll find the photos you&apos;re
                in, in full quality, ready to download.
              </span>
            </p>

            {ids.length === 0 ? (
              <div className="public-state">
                <h2>No photos yet</h2>
                <p>Photos show up here as the host uploads them and they finish processing.</p>
                <button
                  className="btn btn-sm"
                  onClick={() => {
                    setLoading(true);
                    setReloadKey((k) => k + 1);
                  }}
                >
                  Check again
                </button>
              </div>
            ) : (
              <div className="photo-grid">
                {ids.map((id) => (
                  <div key={id} className="photo">
                    {broken[id] ? (
                      <div className="photo-placeholder failed">Can&apos;t preview</div>
                    ) : (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={publicPreviewUrl(token, id)}
                        alt="Event photo"
                        loading="lazy"
                        decoding="async"
                        onError={() => setBroken((prev) => ({ ...prev, [id]: true }))}
                      />
                    )}
                  </div>
                ))}
              </div>
            )}

            {hasMore && (
              <div className="load-more">
                <button className="btn" onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? (
                    <>
                      <span className="spinner" /> Loading…
                    </>
                  ) : (
                    "Load more"
                  )}
                </button>
              </div>
            )}
          </>
        )}
      </main>

      {/* Nothing to get matched in on a dead link, so no call-to-action there
          (the header still offers Log in / Sign up). */}
      {error?.status !== 404 && (
      <div className="public-cta" role="region" aria-label="Sign up to get matched">
        <div className="public-cta-inner">
          <p className="public-cta-copy">
            <strong>Want the photos you&apos;re in?</strong>
            Sign up, scan your face once, and they&apos;re matched to you automatically.
          </p>
          <div className="public-cta-actions">
            <Link className="btn btn-primary" href={registerHref}>
              Sign up to get matched
            </Link>
            <Link className="btn" href={loginHref}>
              Log in
            </Link>
          </div>
        </div>
      </div>
      )}
    </>
  );
}
