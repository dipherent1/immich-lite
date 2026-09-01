"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  getEventPhotoObjectUrl,
  getEventPhotos,
  type PhotoResponse,
} from "@/lib/api";

const PAGE_SIZE = 24;

interface PageResult {
  items: PhotoResponse[];
  has_more: boolean;
  next_offset: number;
}

const tileStyle: React.CSSProperties = {
  position: "relative",
  aspectRatio: "1 / 1",
  overflow: "hidden",
  borderRadius: 8,
  background: "#f0f0f0",
};

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
    <section style={{ marginTop: 24 }}>
      <h2 style={{ fontSize: 20, fontWeight: 600 }}>Photos</h2>
      {error && <p style={{ color: "#cf222e" }}>{error}</p>}
      {!error && photos.length === 0 && !loading && (
        <p style={{ color: "#666" }}>No photos uploaded yet.</p>
      )}
      {photos.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
            gap: 12,
            marginTop: 12,
          }}
        >
          {photos.map((photo) => {
            const url = urls[photo.id];
            const ready = url != null && photo.status === "processed";
            return (
              <div key={photo.id} style={tileStyle}>
                {ready ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={url}
                    alt="Event photo"
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                    loading="lazy"
                  />
                ) : (
                  <div
                    style={{
                      width: "100%",
                      height: "100%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "#888",
                      fontSize: "0.8rem",
                      textAlign: "center",
                      padding: 8,
                    }}
                  >
                    {statusLabel[photo.status] ?? "Pending"}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {hasMore && (
        <button
          onClick={loadMore}
          disabled={loadingMore}
          style={{ marginTop: 16 }}
        >
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </section>
  );
}
