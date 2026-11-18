"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  downloadEventPhotos,
  getEventPhotoObjectUrl,
  getMyMatches,
  type MatchFeedItemResponse,
} from "@/lib/api";
import { endsWithin, timeLeftLabel } from "@/lib/lifetime";
import { zipName } from "@/lib/nav";
import { Icon } from "@/components/ui";

const PAGE_SIZE = 24;
const URGENT_MINUTES = 20;

interface PageResult {
  items: MatchFeedItemResponse[];
  has_more: boolean;
  next_offset: number;
}

/**
 * The photos of ONE event that matched the current user (an album).
 *
 * - Paginated with "Load more"; photos are fetched through the API client
 *   (Bearer header) as blob URLs, revoked on unmount.
 * - "Download all" zips every matched photo of this event (all pages, not just
 *   the loaded ones); "Select" downloads just the ones you tap.
 * - Shows when the event is deleted, as a red alert in its last 20 minutes.
 */
export default function MatchEventPhotos({ eventId }: { eventId: string }) {
  const [items, setItems] = useState<MatchFeedItemResponse[]>([]);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [broken, setBroken] = useState<Record<string, true>>({});
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"all" | "sel" | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const objectUrlsRef = useRef<string[]>([]);

  useEffect(() => {
    const urls = objectUrlsRef.current;
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  // Fetches a page but does NOT set state — callers apply results via .then
  // callbacks (the only pattern this repo's lint rule allows inside effects).
  const fetchPage = useCallback(
    async (offset: number): Promise<PageResult> => {
      const data = await getMyMatches(offset, PAGE_SIZE, eventId);
      for (const item of data.items) {
        getEventPhotoObjectUrl(item.event_id, item.photo_id)
          .then((url) => {
            objectUrlsRef.current.push(url);
            setUrls((prev) => ({ ...prev, [item.photo_id]: url }));
          })
          .catch(() => {
            // One bad photo shouldn't break the album — mark just this tile.
            setBroken((prev) => ({ ...prev, [item.photo_id]: true }));
          });
      }
      return { items: data.items, has_more: data.has_more, next_offset: data.next_offset };
    },
    [eventId],
  );

  useEffect(() => {
    fetchPage(0)
      .then((page) => {
        setItems(page.items);
        setHasMore(page.has_more);
        setNextOffset(page.next_offset);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.detail : "Could not load these photos.");
        setLoading(false);
      });
  }, [fetchPage]);

  function loadMore() {
    setLoadingMore(true);
    fetchPage(nextOffset)
      .then((page) => {
        setItems((prev) => [...prev, ...page.items]);
        setHasMore(page.has_more);
        setNextOffset(page.next_offset);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.detail : "Could not load these photos.");
      })
      .finally(() => setLoadingMore(false));
  }

  function toggle(photoId: string) {
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(photoId)) next.delete(photoId);
      else next.add(photoId);
      return next;
    });
  }

  function exitSelecting() {
    setSelecting(false);
    setChosen(new Set());
  }

  const eventName = items[0]?.event_name ?? "Event";
  const expiresAt = items[0]?.event_expires_at ?? null;
  const ended = expiresAt != null && new Date(`${expiresAt}Z`).getTime() <= now;
  const urgent = expiresAt != null && !ended && endsWithin(expiresAt, URGENT_MINUTES, now);

  async function downloadAll() {
    setBusy("all");
    setDownloadError(null);
    try {
      // Every matched photo of this event, including pages not loaded yet.
      const ids: string[] = [];
      let offset = 0;
      for (;;) {
        const page = await getMyMatches(offset, 100, eventId);
        ids.push(...page.items.map((i) => i.photo_id));
        if (!page.has_more) break;
        offset = page.next_offset;
      }
      await downloadEventPhotos(eventId, ids, zipName(eventName));
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.detail : "Could not download photos.");
    } finally {
      setBusy(null);
    }
  }

  async function downloadSelected() {
    setBusy("sel");
    setDownloadError(null);
    try {
      await downloadEventPhotos(eventId, [...chosen], zipName(eventName));
      exitSelecting();
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.detail : "Could not download photos.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section>
      <Link href="/matches" className="back-link" style={{ marginBottom: 16 }}>
        <Icon.ArrowLeft size={16} /> My photos
      </Link>

      {error && <p className="alert alert-error">{error}</p>}

      {items.length > 0 && (
        <>
          <div className="album-head">
            <div style={{ minWidth: 0 }}>
              <span className="eyebrow">Album</span>
              <h1 className="h1">{eventName}</h1>
              <p className="muted small" style={{ marginTop: 6 }}>
                {items.length}
                {hasMore ? "+" : ""} photo{items.length === 1 && !hasMore ? "" : "s"} of you
                {expiresAt && (
                  <>
                    {" · "}
                    <span className={`expiry-chip${urgent || ended ? " urgent" : ""}`}>
                      <Icon.Clock size={12} />{" "}
                      {ended ? "Being deleted" : `Deleted in ${timeLeftLabel(expiresAt, now)}`}
                    </span>
                  </>
                )}
              </p>
            </div>

            <div className="album-actions">
              {!selecting ? (
                <>
                  <button type="button" className="btn btn-sm" onClick={() => setSelecting(true)}>
                    <Icon.Check size={15} /> Select
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    disabled={busy !== null}
                    onClick={downloadAll}
                    title="Download all your photos from this event as a zip"
                  >
                    {busy === "all" ? <span className="spinner" /> : <Icon.Download size={15} />}{" "}
                    Download all
                  </button>
                </>
              ) : (
                <>
                  <span className="small">
                    <strong>{chosen.size}</strong> selected
                  </span>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() =>
                      setChosen(
                        chosen.size === items.length
                          ? new Set()
                          : new Set(items.map((i) => i.photo_id)),
                      )
                    }
                  >
                    {chosen.size === items.length ? "Clear" : "Select all loaded"}
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    disabled={chosen.size === 0 || busy !== null}
                    onClick={downloadSelected}
                  >
                    {busy === "sel" ? <span className="spinner" /> : <Icon.Download size={15} />}{" "}
                    Download{chosen.size > 0 ? ` ${chosen.size}` : ""}
                  </button>
                  <button type="button" className="btn btn-sm" onClick={exitSelecting}>
                    Cancel
                  </button>
                </>
              )}
            </div>
          </div>

          {(urgent || ended) && (
            <div className="expiry-banner urgent" role="alert">
              <Icon.Clock size={18} />
              <span>
                <strong>
                  {ended
                    ? `${eventName} is being deleted right now.`
                    : `${eventName} is deleted in ${timeLeftLabel(expiresAt!, now)}.`}
                </strong>{" "}
                Download your photos now or they&apos;re gone for good.
              </span>
            </div>
          )}
        </>
      )}

      {downloadError && (
        <p className="alert alert-error" style={{ marginBottom: 14 }}>
          {downloadError}
        </p>
      )}

      {loading && !error && (
        <div className="photo-grid">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="photo">
              <div className="photo-placeholder" />
            </div>
          ))}
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="empty" style={{ padding: "72px 24px" }}>
          <strong style={{ color: "var(--text)", fontSize: "1.05rem" }}>
            No photos of you here
          </strong>
          <span style={{ maxWidth: 360 }}>
            This event may have ended (its photos are deleted), or none matched your face.
          </span>
          <Link href="/matches" className="btn btn-sm" style={{ marginTop: 6 }}>
            Back to my photos
          </Link>
        </div>
      )}

      {items.length > 0 && (
        <div className="photo-grid">
          {items.map((item) => {
            const url = urls[item.photo_id];
            const isBroken = broken[item.photo_id] === true;
            const isChosen = chosen.has(item.photo_id);
            return (
              <div
                key={item.photo_id}
                className={`photo${selecting ? " selectable" : ""}${isChosen ? " chosen" : ""}`}
                onClick={selecting ? () => toggle(item.photo_id) : undefined}
                role={selecting ? "checkbox" : undefined}
                aria-checked={selecting ? isChosen : undefined}
                tabIndex={selecting ? 0 : undefined}
                onKeyDown={
                  selecting
                    ? (e) => {
                        if (e.key === " " || e.key === "Enter") {
                          e.preventDefault();
                          toggle(item.photo_id);
                        }
                      }
                    : undefined
                }
              >
                {url && !isBroken ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={url}
                    alt={`Photo from ${item.event_name}`}
                    loading="lazy"
                    onError={() => setBroken((prev) => ({ ...prev, [item.photo_id]: true }))}
                  />
                ) : (
                  <div className={`photo-placeholder${isBroken ? " failed" : ""}`}>
                    {isBroken ? "Can't preview" : null}
                  </div>
                )}
                {selecting && (
                  <span className={`photo-check${isChosen ? " on" : ""}`} aria-hidden>
                    {isChosen && <Icon.Check size={14} />}
                  </span>
                )}
              </div>
            );
          })}
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
    </section>
  );
}
