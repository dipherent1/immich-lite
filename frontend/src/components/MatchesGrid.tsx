"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  getEventPhotoObjectUrl,
  getMyMatches,
  type MatchFeedItemResponse,
} from "@/lib/api";

const PAGE_SIZE = 24;

interface PageResult {
  items: MatchFeedItemResponse[];
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

function similarityLabel(value: number): string {
  const pct = Math.round(value * 100);
  return `${pct}%`;
}

/**
 * The current user's matched-photo feed.
 *
 * Mirrors the event `PhotoGrid` pattern: fetches page 1 on mount (and whenever
 * `refreshKey` changes), appends pages via a "Load more" button, and renders each
 * matched photo as a blob object URL (fetched through the single API client so
 * the Bearer header is attached). Each tile is overlaid with the event it came
 * from and the match confidence. Object URLs are revoked on unmount.
 */
export default function MatchesGrid({ refreshKey = 0 }: { refreshKey?: number }) {
  const [items, setItems] = useState<MatchFeedItemResponse[]>([]);
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
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  // Fetches a page but does NOT set state — callers apply results via .then
  // callbacks (the only pattern this repo's lint rule allows inside effects).
  const fetchPage = useCallback(async (offset: number): Promise<PageResult> => {
    const data = await getMyMatches(offset, PAGE_SIZE);

    for (const item of data.items) {
      getEventPhotoObjectUrl(item.event_id, item.photo_id)
        .then((url) => {
          objectUrlsRef.current.push(url);
          setUrls((prev) => ({ ...prev, [item.photo_id]: url }));
        })
        .catch(() => {
          // Individual photo failing shouldn't break the feed.
        });
    }
    return {
      items: data.items,
      has_more: data.has_more,
      next_offset: data.next_offset,
    };
  }, []);

  useEffect(() => {
    fetchPage(0)
      .then((page) => {
        objectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
        objectUrlsRef.current = [];
        setUrls({});
        setItems(page.items);
        setHasMore(page.has_more);
        setNextOffset(page.next_offset);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.detail : "Could not load your matches.");
        setLoading(false);
      });
  }, [refreshKey, fetchPage]);

  function loadMore() {
    setLoadingMore(true);
    fetchPage(nextOffset)
      .then((page) => {
        setItems((prev) => [...prev, ...page.items]);
        setHasMore(page.has_more);
        setNextOffset(page.next_offset);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.detail : "Could not load your matches.");
      })
      .finally(() => setLoadingMore(false));
  }

  return (
    <section style={{ marginTop: 24 }}>
      <h2 style={{ fontSize: 20, fontWeight: 600 }}>Your matches</h2>
      {error && <p style={{ color: "#cf222e" }}>{error}</p>}
      {!error && items.length === 0 && !loading && (
        <p style={{ color: "#666" }}>
          No matched photos yet. Photos containing your face will appear here.
        </p>
      )}
      {items.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
            gap: 12,
            marginTop: 12,
          }}
        >
          {items.map((item) => {
            const url = urls[item.photo_id];
            return (
              <div key={item.photo_id} style={tileStyle}>
                {url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={url}
                    alt={`Matched photo from ${item.event_name}`}
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
                    Loading…
                  </div>
                )}
                <div
                  style={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    right: 0,
                    padding: "10px 8px 6px",
                    background: "linear-gradient(transparent, rgba(0,0,0,0.7))",
                    color: "#fff",
                    fontSize: "0.75rem",
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{item.event_name}</div>
                  <div>{similarityLabel(item.similarity)} match</div>
                </div>
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
