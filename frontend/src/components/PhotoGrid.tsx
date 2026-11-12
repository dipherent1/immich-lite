"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  downloadEventPhotos,
  getEventPhotoObjectUrl,
  getEventPhotos,
  setEventCover,
  type EventResponse,
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
 * - "Select" turns tiles into checkboxes so a subset can be downloaded as a zip;
 *   "Download all" zips the whole event (including pages not loaded yet).
 *
 * Reusable later for the Phase 5 matched-photo feed.
 */
export default function PhotoGrid({
  eventId,
  eventName = "event",
  refreshKey = 0,
  isOwner = false,
  coverPhotoId = null,
  onCoverUpdated,
}: {
  eventId: string;
  eventName?: string;
  /** Bump to reload the first page (e.g. after a new upload). */
  refreshKey?: number;
  isOwner?: boolean;
  coverPhotoId?: string | null;
  onCoverUpdated?: (event: EventResponse) => void;
}) {
  // `loading` reflects the initial (mount) fetch and starts true.
  const [photos, setPhotos] = useState<PhotoResponse[]>([]);
  const [urls, setUrls] = useState<Record<string, string>>({});
  // Tiles whose image couldn't be fetched or decoded (shown as a placeholder).
  const [broken, setBroken] = useState<Record<string, true>>({});
  const [hasMore, setHasMore] = useState(false);
  const [nextOffset, setNextOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settingCoverId, setSettingCoverId] = useState<string | null>(null);
  const [coverError, setCoverError] = useState<string | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
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
            // One bad photo shouldn't break the grid — mark just this tile.
            setBroken((prev) => ({ ...prev, [photo.id]: true }));
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
        setBroken({});
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

  async function handleSetCover(photoId: string) {
    setSettingCoverId(photoId);
    setCoverError(null);
    try {
      const updated = await setEventCover(eventId, photoId);
      onCoverUpdated?.(updated);
    } catch (err) {
      setCoverError(
        err instanceof ApiError ? err.detail : "Could not update cover image.",
      );
    } finally {
      setSettingCoverId(null);
    }
  }

  function toggleChosen(photoId: string) {
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

  async function handleDownload(photoIds?: string[]) {
    setDownloading(true);
    setDownloadError(null);
    try {
      const safeName = eventName.replace(/[^\w\- ]+/g, "").trim() || "event";
      await downloadEventPhotos(eventId, photoIds, `${safeName}-photos.zip`);
      if (photoIds) exitSelecting();
    } catch (err) {
      setDownloadError(err instanceof ApiError ? err.detail : "Could not download photos.");
    } finally {
      setDownloading(false);
    }
  }

  const statusLabel: Record<string, string> = {
    pending: "Processing…",
    failed: "Failed to process",
  };

  const allLoadedChosen = photos.length > 0 && chosen.size === photos.length;

  return (
    <section style={{ marginTop: 32 }}>
      <div className="spread" style={{ marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <h2 className="h2">Photos</h2>
        <div className="row" style={{ gap: 10 }}>
          {photos.length > 0 && !selecting && (
            <span className="muted small">{photos.length} loaded</span>
          )}
          {photos.length > 0 && !selecting && (
            <>
              <button type="button" className="btn btn-sm" onClick={() => setSelecting(true)}>
                <Icon.Check size={15} /> Select
              </button>
              <button
                type="button"
                className="btn btn-sm"
                disabled={downloading}
                onClick={() => handleDownload()}
                title="Download every photo of this event as a zip"
              >
                {downloading ? <span className="spinner" /> : <Icon.Download size={15} />} Download all
              </button>
            </>
          )}
          {selecting && (
            <>
              <span className="small">
                <strong>{chosen.size}</strong> selected
              </span>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() =>
                  setChosen(allLoadedChosen ? new Set() : new Set(photos.map((p) => p.id)))
                }
              >
                {allLoadedChosen ? "Clear" : "Select all loaded"}
              </button>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                disabled={chosen.size === 0 || downloading}
                onClick={() => handleDownload([...chosen])}
              >
                {downloading ? <span className="spinner" /> : <Icon.Download size={15} />} Download
                {chosen.size > 0 ? ` ${chosen.size}` : ""}
              </button>
              <button type="button" className="btn btn-sm" onClick={exitSelecting}>
                Cancel
              </button>
            </>
          )}
        </div>
      </div>
      {error && <p className="alert alert-error">{error}</p>}
      {downloadError && (
        <p className="alert alert-error" style={{ marginBottom: 14 }}>
          {downloadError}
        </p>
      )}
      {coverError && (
        <p className="alert alert-error" style={{ marginBottom: 14 }}>
          {coverError}
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
            const isBroken = broken[photo.id] === true;
            const ready = url != null && !isBroken && photo.status === "processed";
            const isCover = coverPhotoId === photo.id;
            const isChosen = chosen.has(photo.id);
            return (
              <div
                key={photo.id}
                className={`photo${selecting ? " selectable" : ""}${isChosen ? " chosen" : ""}`}
                onClick={selecting ? () => toggleChosen(photo.id) : undefined}
                role={selecting ? "checkbox" : undefined}
                aria-checked={selecting ? isChosen : undefined}
                tabIndex={selecting ? 0 : undefined}
                onKeyDown={
                  selecting
                    ? (e) => {
                        if (e.key === " " || e.key === "Enter") {
                          e.preventDefault();
                          toggleChosen(photo.id);
                        }
                      }
                    : undefined
                }
              >
                {ready ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={url}
                    alt="Event photo"
                    loading="lazy"
                    onError={() => setBroken((prev) => ({ ...prev, [photo.id]: true }))}
                  />
                ) : (
                  <div
                    className={`photo-placeholder${
                      photo.status === "failed" || isBroken ? " failed" : ""
                    }`}
                  >
                    {photo.status !== "failed" && !isBroken && <span className="spinner" />}
                    {isBroken ? "Can't preview" : (statusLabel[photo.status] ?? "Loading…")}
                  </div>
                )}
                {isCover && <span className="photo-cover-badge">Cover</span>}
                {selecting && (
                  <span className={`photo-check${isChosen ? " on" : ""}`} aria-hidden>
                    {isChosen && <Icon.Check size={14} />}
                  </span>
                )}
                {!selecting && isOwner && !isCover && url != null && !isBroken && (
                  <button
                    type="button"
                    className="photo-cover-btn"
                    disabled={settingCoverId === photo.id}
                    onClick={() => handleSetCover(photo.id)}
                  >
                    {settingCoverId === photo.id ? "Saving…" : "Set as cover"}
                  </button>
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
