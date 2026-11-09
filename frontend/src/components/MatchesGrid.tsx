"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  getEventPhotoObjectUrl,
  getMyMatches,
  type MatchFeedItemResponse,
} from "@/lib/api";
import { Icon } from "@/components/ui";

const PAGE_SIZE = 24;

interface PageResult {
  items: MatchFeedItemResponse[];
  has_more: boolean;
  next_offset: number;
}

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
    <section>
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
      {!error && items.length === 0 && !loading && (
        <div className="empty" style={{ padding: "72px 24px" }}>
          <span className="scan-ring missing">
            <Icon.Face size={30} />
          </span>
          <strong style={{ color: "var(--text)", fontSize: "1.05rem" }}>No matches yet</strong>
          <span style={{ maxWidth: 360 }}>
            When photos with your face are uploaded to events you&apos;ve joined, they&apos;ll
            show up here.
          </span>
          <Link href="/dashboard" className="btn btn-sm" style={{ marginTop: 6 }}>
            Go to dashboard
          </Link>
        </div>
      )}
      {items.length > 0 && (
        <div className="photo-grid">
          {items.map((item) => {
            const url = urls[item.photo_id];
            return (
              <div key={item.photo_id} className="photo">
                {url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={url} alt={`Matched photo from ${item.event_name}`} loading="lazy" />
                ) : (
                  <div className="photo-placeholder" />
                )}
                <div className="photo-overlay">
                  <span className="event-label">{item.event_name}</span>
                  <span className="match-score">{similarityLabel(item.similarity)}</span>
                </div>
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
