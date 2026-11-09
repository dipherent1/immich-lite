"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  getEventPhotoObjectUrl,
  getEventPhotos,
  type PhotoResponse,
} from "@/lib/api";
import { Icon } from "@/components/ui";

const PAGE_SIZE = 24;

interface PageResult {
  items: PhotoResponse[];
  has_more: boolean;
  next_offset: number;
}

/**
 * Reusable, self-contained paginated grid of an event's uploaded photos.
 *
 * - Fetches page 1 on mount (and whenever `refreshKey` changes) and appends
 *   pages via a "Load more" button.
 * - Each photo's raw bytes are fetched through the single API client (auth is
 *   handled there) and rendered as an object URL; URLs are revoked on unmount.
 * - Photos that aren't `processed` yet show a placeholder instead of an image.
 *
 * Reusable later for the Phase 5 matched-photo feed.
 */
export default function PhotoGrid({
  eventId,
  refreshKey = 0,
}: {
  eventId: string;
  /** Bump to reload the first page (e.g. after a new upload). */
  refreshKey?: number;
}) {
  // `loading` reflects the initial (mount) fetch and starts true.
  const [photos, setPhotos] = useState<PhotoResponse[]>([]);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const objectUrlsRef = useRef<string[]>([]);

  useEffect(() => {
    const urls = objectUrlsRef.current;
    return () => {
      // Revoke all object URLs we created so the browser frees the blobs.
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  // Fetches a page but does NOT set state — callers apply results via .then
  // callbacks (the only pattern this repo's lint rule allows inside effects).
  const fetchPage = useCallback(
    async (offset: number): Promise<PageResult> => {
      const data = await getEventPhotos(eventId, offset, PAGE_SIZE);

      // Kick off object-URL materialization for each new photo (fire and forget).
      for (const photo of data.items) {
        getEventPhotoObjectUrl(eventId, photo.id)
          .then((url) => {
            objectUrlsRef.current.push(url);
            setUrls((prev) => ({ ...prev, [photo.id]: url }));
          })
          .catch(() => {
            // Individual photo failing shouldn't break the grid.
          });
      }
      return {
        items: data.items,
        has_more: data.has_more,
        next_offset: data.next_offset,
      };
    },
    [eventId],
  );

  // Loads the first page on mount and reloads it whenever `refreshKey` changes
  // (e.g. after an upload). All state updates happen in .then/.catch callbacks,
  // which is the pattern this repo's lint rule allows inside effects.
  useEffect(() => {
    if (!eventId) return;
    fetchPage(0)
      .then((page) => {
        // Drop stale blob URLs from a previous page before replacing the list.
        objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
        objectUrlsRef.current = [];
        setUrls({});
        setPhotos(page.items);
        setHasMore(page.has_more);
        setNextOffset(page.next_offset);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.detail : "Could not load photos.");
        setLoading(false);
      });
  }, [eventId, refreshKey, fetchPage]);

  // "Load more" is triggered by a click handler, which is exempt from the lint
  // rule, so it owns its own spinner and appends the page.
  function loadMore() {
    setLoadingMore(true);
    fetchPage(nextOffset)
      .then((page) => {
        setPhotos((prev) => [...prev, ...page.items]);
        setHasMore(page.has_more);
        setNextOffset(page.next_offset);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.detail : "Could not load photos.");
      })
      .finally(() => setLoadingMore(false));
  }

  const statusLabel: Record<string, string> = {
    pending: "Processing…",
    failed: "Failed to process",
  };

  return (
    <section style={{ marginTop: 32 }}>
      <div className="spread" style={{ marginBottom: 16 }}>
        <h2 className="h2">Photos</h2>
        {photos.length > 0 && <span className="muted small">{photos.length} loaded</span>}
      </div>
      {error && <p className="alert alert-error">{error}</p>}
      {loading && !error && (
        <div className="photo-grid">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="photo">
              <div className="photo-placeholder" />
            </div>
          ))}
        </div>
      )}
      {!error && photos.length === 0 && !loading && (
        <div className="empty">
          <Icon.Images size={30} />
          <span>No photos uploaded yet.</span>
        </div>
      )}
      {photos.length > 0 && (
        <div className="photo-grid">
          {photos.map((photo) => {
            const url = urls[photo.id];
            const ready = url != null && photo.status === "processed";
            return (
              <div key={photo.id} className="photo">
                {ready ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={url} alt="Event photo" loading="lazy" />
                ) : (
                  <div className={`photo-placeholder${photo.status === "failed" ? " failed" : ""}`}>
                    {photo.status !== "failed" && <span className="spinner" />}
                    {statusLabel[photo.status] ?? "Loading…"}
                  </div>
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
