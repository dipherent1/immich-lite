"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import { Icon } from "@/components/ui";
import PhotoGrid from "@/components/PhotoGrid";
import { endsWithin, parseUtc, timeLeftLabel } from "@/lib/lifetime";
import {
  ApiError,
  approveRequest,
  denyRequest,
  getEvent,
  getEventPhotoObjectUrl,
  listPendingRequests,
  uploadEventCover,
  uploadEventPhotosBatch,
  MAX_BATCH_FILES,
  type EventDetailResponse,
  type EventResponse,
  type JoinRequestResponse,
} from "@/lib/api";

function joinLinkFor(token: string): string {
  return `${window.location.origin}/join/${token}`;
}

// Thumbnails rendered for the queue; the rest are summarised as "+N".
const QUEUE_PREVIEW_LIMIT = 30;

interface SelectedImage {
  file: File;
  url: string;
}

function EventPreviewContent() {
  const params = useParams<{ id: string }>();
  const eventId = params?.id ?? "";

  const [event, setEvent] = useState<EventDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedImage[]>([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [joinRequests, setJoinRequests] = useState<JoinRequestResponse[]>([]);
  const [requestsNote, setRequestsNote] = useState<string | null>(null);
  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [coverUploading, setCoverUploading] = useState(false);
  const [coverError, setCoverError] = useState<string | null>(null);
  const coverUrlRef = useRef<string | null>(null);
  const previewUrlsRef = useRef<string[]>([]);

  useEffect(() => {
    const urls = previewUrlsRef.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
      if (coverUrlRef.current) URL.revokeObjectURL(coverUrlRef.current);
    };
  }, []);

  useEffect(() => {
    const id = event?.id;
    const coverPhotoId = event?.cover_photo_id;
    if (!id || !coverPhotoId) return;
    let cancelled = false;
    getEventPhotoObjectUrl(id, coverPhotoId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        if (coverUrlRef.current) URL.revokeObjectURL(coverUrlRef.current);
        coverUrlRef.current = url;
        setCoverUrl(url);
      })
      .catch(() => {
        // Ignore cover fetch failure; fallback hero gradient remains visible.
      });
    return () => {
      cancelled = true;
    };
  }, [event?.id, event?.cover_photo_id]);

  useEffect(() => {
    if (!eventId) return;
    getEvent(eventId)
      .then((ev) => {
        setEvent(ev);
        if (ev.is_owner) loadJoinRequests(ev.id);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Could not load this event."),
      );
  }, [eventId]);

  function loadJoinRequests(id: string) {
    listPendingRequests(id)
      .then(setJoinRequests)
      .catch(() => setJoinRequests([]));
  }

  async function handleApprove(requestId: string) {
    try {
      await approveRequest(eventId, requestId);
      setRequestsNote("Request approved — they're now an attendee.");
      loadJoinRequests(eventId);
    } catch (err) {
      setRequestsNote(
        err instanceof ApiError ? err.detail : "Could not approve that request.",
      );
    }
  }

  async function handleDeny(requestId: string) {
    try {
      await denyRequest(eventId, requestId);
      setRequestsNote("Request denied.");
      loadJoinRequests(eventId);
    } catch (err) {
      setRequestsNote(
        err instanceof ApiError ? err.detail : "Could not deny that request.",
      );
    }
  }

  // Selecting files only queues them (with thumbnails) — upload happens when the
  // button is hit. Up to MAX_BATCH_FILES (100) can be queued at once.
  function onFilesSelected(list: FileList | null) {
    if (!list) return;
    previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    const all = Array.from(list);
    const next: SelectedImage[] = all.slice(0, MAX_BATCH_FILES).map((file) => ({
      file,
      url: URL.createObjectURL(file),
    }));
    previewUrlsRef.current = next.map((s) => s.url);
    setSelected(next);
    setUploadNote(
      all.length > MAX_BATCH_FILES
        ? `Only the first ${MAX_BATCH_FILES} of ${all.length} photos were queued — upload these, then add the rest.`
        : null,
    );
  }

  // "Cancel" an individual queued photo: drop it from the batch and free its link.
  function removeSelected(index: number) {
    const item = selected[index];
    if (item) {
      URL.revokeObjectURL(item.url);
      previewUrlsRef.current = previewUrlsRef.current.filter(
        (url) => url !== item.url,
      );
    }
    setSelected((prev) => prev.filter((_, i) => i !== index));
  }

  async function onUploadSelected() {
    if (selected.length === 0 || !eventId) return;
    setUploading(true);
    setUploadNote(null);

    // Send in chunks so progress is visible and one network hiccup only costs a
    // chunk, not all 100 photos. The API accepts up to 100 per request.
    const CHUNK = 10;
    const files = selected.map((s) => s.file);
    const errors: string[] = [];
    let succeeded = 0;
    setProgress({ done: 0, total: files.length });
    for (let i = 0; i < files.length; i += CHUNK) {
      const chunk = files.slice(i, i + CHUNK);
      try {
        const res = await uploadEventPhotosBatch(eventId, chunk);
        succeeded += res.succeeded;
        for (const item of res.items) {
          if (!item.ok) errors.push(`${item.filename}: ${item.error ?? "failed"}`);
        }
      } catch (err) {
        const why = err instanceof ApiError ? err.detail : "network error";
        for (const f of chunk) errors.push(`${f.name}: ${why}`);
      }
      setProgress({ done: Math.min(i + CHUNK, files.length), total: files.length });
    }

    setUploading(false);
    setProgress(null);
    previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    previewUrlsRef.current = [];
    setSelected([]);
    // Reload the grid and event details (first upload sets the default cover).
    setRefreshKey((k) => k + 1);
    getEvent(eventId)
      .then(setEvent)
      .catch(() => {});
    if (errors.length > 0) {
      const shown = errors.slice(0, 3).join("; ");
      const more = errors.length > 3 ? ` (+${errors.length - 3} more)` : "";
      setUploadNote(
        `${succeeded} of ${files.length} uploaded; ${errors.length} failed — ${shown}${more}`,
      );
    } else {
      setUploadNote(`${succeeded} photo${succeeded === 1 ? "" : "s"} uploaded.`);
    }
  }

  function applyCoverUpdate(updated: EventResponse) {
    setEvent((prev) =>
      prev
        ? {
            ...prev,
            cover_photo_id: updated.cover_photo_id,
            cover_url: updated.cover_url,
          }
        : prev,
    );
  }

  async function onCoverFileSelected(file: File | null) {
    if (!file || !eventId) return;
    setCoverUploading(true);
    setCoverError(null);
    try {
      const updated = await uploadEventCover(eventId, file);
      applyCoverUpdate(updated);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setCoverError(
        err instanceof ApiError ? err.detail : "Could not upload cover image.",
      );
    } finally {
      setCoverUploading(false);
    }
  }

  async function copyLink(token: string) {
    try {
      await navigator.clipboard.writeText(joinLinkFor(token));
    } catch {
      // Clipboard may be unavailable; ignore.
    }
  }

  const [copied, setCopied] = useState(false);

  async function copyWithFeedback(token: string) {
    await copyLink(token);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  const fmt = (iso: string) =>
    parseUtc(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });

  return (
    <AppShell>
      <Link href="/dashboard" className="back-link" style={{ marginBottom: 20 }}>
        <Icon.ArrowLeft size={16} /> Dashboard
      </Link>

      {error && (
        <p className="alert alert-error" style={{ marginTop: 16 }}>
          {error}
        </p>
      )}

      {!event && !error ? (
        <div className="row muted" style={{ marginTop: 24 }}>
          <span className="spinner" /> Loading event…
        </div>
      ) : null}

      {event && (
        <>
          <section
            className={`event-hero grain${coverUrl ? " has-cover" : ""}`}
            style={{ marginTop: 16 }}
          >
            {coverUrl ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={coverUrl}
                  alt={`${event.name} cover`}
                  className="event-hero-cover"
                />
                <div className="event-hero-scrim" />
              </>
            ) : (
              <div className="stars" />
            )}
            <div className="row" style={{ justifyContent: "center", position: "relative", zIndex: 2 }}>
              {event.expires_at ? (
                <span className={`badge ${event.active ? "badge-open" : "badge-closed"}`}>
                  {event.active ? "Open" : "Ended"}
                </span>
              ) : (
                <span className="badge badge-open">Open</span>
              )}
              {event.is_owner && <span className="badge">You&apos;re the host</span>}
            </div>
            <h1 className="display" style={{ position: "relative", zIndex: 2 }}>
              {event.name}
            </h1>
            <p className="muted" style={{ position: "relative", zIndex: 2 }}>
              Starts {fmt(event.starts_at)}
            </p>
            {event.is_owner && (
              <label className={`event-hero-edit${coverUploading ? " disabled" : ""}`}>
                <input
                  type="file"
                  accept="image/*"
                  disabled={coverUploading}
                  onChange={(e) => {
                    const file = e.target.files?.[0] ?? null;
                    onCoverFileSelected(file);
                    e.target.value = "";
                  }}
                />
                {coverUploading ? (
                  <>
                    <span className="spinner" /> Updating cover…
                  </>
                ) : (
                  <>
                    <Icon.Images size={15} /> {coverUrl ? "Change cover" : "Add cover image"}
                  </>
                )}
              </label>
            )}
          </section>

          {coverError && (
            <p className="alert alert-error" style={{ marginBottom: 16 }}>
              {coverError}
            </p>
          )}

          {event.expires_at && (
            <div
              className={`expiry-banner${endsWithin(event.expires_at, 20) ? " urgent" : ""}`}
              role="status"
            >
              <Icon.Clock size={18} />
              <span>
                <strong>This event is deleted in {timeLeftLabel(event.expires_at)}</strong>{" "}
                ({fmt(event.expires_at)}). Its photos and matches are removed with it, so
                download what you want to keep.
              </span>
            </div>
          )}

          <div className="facts">
            <div className="fact">
              <div className="fact-label">
                <Icon.Users size={13} /> Attendees
              </div>
              <div className="fact-value big">{event.attendee_count}</div>
            </div>
            <div className="fact">
              <div className="fact-label">
                <Icon.Calendar size={13} /> Starts
              </div>
              <div className="fact-value">{fmt(event.starts_at)}</div>
            </div>
            <div className="fact">
              <div className="fact-label">
                <Icon.Clock size={13} /> Deleted
              </div>
              <div className="fact-value">
                {event.expires_at ? fmt(event.expires_at) : "Never (older event)"}
              </div>
            </div>
            <div className="fact">
              <div className="fact-label">
                <Icon.Plus size={13} /> Created
              </div>
              <div className="fact-value">{fmt(event.created_at)}</div>
            </div>
          </div>

          <div className="grid-2">
            {/* Upload */}
            <section className="card">
              <div className="card-header">
                <h2 className="h2">Add photos</h2>
                {selected.length > 0 && (
                  <span className="muted small">{selected.length} ready</span>
                )}
              </div>

              <label className={`dropzone${uploading ? " disabled" : ""}`}>
                <input
                  type="file"
                  accept="image/*,.heic,.heif"
                  multiple
                  disabled={uploading}
                  onChange={(e) => {
                    onFilesSelected(e.target.files);
                    // Allow re-selecting the same file(s) after an upload.
                    e.target.value = "";
                  }}
                />
                <span className="tile-icon">
                  <Icon.Upload size={22} />
                </span>
                <strong>Choose photos</strong>
                <span className="muted small">
                  Up to 100 at a time · JPG, PNG or HEIC · 20 MB each. We&apos;ll match faces automatically.
                </span>
              </label>

              {selected.length > 0 && (
                <div className="queue">
                  {selected.slice(0, QUEUE_PREVIEW_LIMIT).map((img, i) => (
                    <div key={img.url} className="queue-item">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={img.url}
                        alt={`Selected photo ${i + 1}`}
                        loading="lazy"
                        decoding="async"
                        onError={(e) => {
                          // Browsers can't preview HEIC; it still uploads fine.
                          e.currentTarget.style.visibility = "hidden";
                        }}
                      />
                      <button
                        type="button"
                        aria-label={`Remove photo ${i + 1}`}
                        onClick={() => removeSelected(i)}
                        disabled={uploading}
                      >
                        <Icon.X size={12} />
                      </button>
                    </div>
                  ))}
                  {selected.length > QUEUE_PREVIEW_LIMIT && (
                    <div className="queue-item queue-more">
                      +{selected.length - QUEUE_PREVIEW_LIMIT}
                    </div>
                  )}
                </div>
              )}

              <button
                type="button"
                className="btn btn-primary btn-block"
                style={{ marginTop: 14 }}
                disabled={uploading || selected.length === 0}
                onClick={onUploadSelected}
              >
                {uploading ? (
                  <>
                    <span className="spinner" /> Uploading{progress ? ` ${progress.done}/${progress.total}` : "…"}
                  </>
                ) : selected.length === 0 ? (
                  "Upload photos"
                ) : (
                  `Upload ${selected.length} ${selected.length === 1 ? "photo" : "photos"}`
                )}
              </button>

              {uploadNote && (
                <p
                  className={`alert ${uploadNote.includes("failed") ? "alert-error" : "alert-ok"}`}
                  style={{ marginTop: 12 }}
                >
                  {uploadNote}
                </p>
              )}
            </section>

            <div className="stack">
              {/* Invite */}
              <section className="card">
                <div className="card-header">
                  <h2 className="h2">Invite people</h2>
                  <Icon.Link />
                </div>
                <div className="input-group">
                  <code className="code-chip">{joinLinkFor(event.join_token)}</code>
                  <button className="btn btn-sm" onClick={() => copyWithFeedback(event.join_token)}>
                    {copied ? (
                      <>
                        <Icon.Check size={15} /> Copied
                      </>
                    ) : (
                      <>
                        <Icon.Copy size={15} /> Copy
                      </>
                    )}
                  </button>
                </div>
                <p className="hint" style={{ marginTop: 10 }}>
                  Anyone with this link can join while the event is open.
                </p>
              </section>

              {/* Join requests */}
              {event.is_owner && (
                <section className="card">
                  <div className="card-header">
                    <h2 className="h2">Join requests</h2>
                    {joinRequests.length > 0 && (
                      <span className="badge" style={{ color: "var(--accent)", background: "var(--accent-soft)" }}>
                        {joinRequests.length} pending
                      </span>
                    )}
                  </div>
                  {requestsNote && (
                    <p
                      className={`alert ${requestsNote.startsWith("Could") ? "alert-error" : "alert-ok"}`}
                      style={{ marginBottom: 12 }}
                    >
                      {requestsNote}
                    </p>
                  )}
                  {joinRequests.length === 0 ? (
                    <p className="muted small">No pending join requests.</p>
                  ) : (
                    <div>
                      {joinRequests.map((req) => (
                        <div key={req.id} className="request">
                          <div className="row" style={{ flexWrap: "nowrap", minWidth: 0 }}>
                            <span className="avatar" style={{ width: 34, height: 34, fontSize: "0.8rem" }}>
                              {req.requester_name.trim()[0]?.toUpperCase() ?? "?"}
                            </span>
                            <div style={{ minWidth: 0 }}>
                              <strong style={{ display: "block" }}>{req.requester_name}</strong>
                              <span className="muted small">
                                Requested {new Date(req.created_at).toLocaleString()}
                              </span>
                            </div>
                          </div>
                          <div className="row" style={{ flexWrap: "nowrap" }}>
                            <button
                              type="button"
                              className="btn btn-sm btn-ok"
                              onClick={() => handleApprove(req.id)}
                            >
                              Approve
                            </button>
                            <button
                              type="button"
                              className="btn btn-sm btn-danger"
                              onClick={() => handleDeny(req.id)}
                            >
                              Deny
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}
            </div>
          </div>

          <PhotoGrid
            eventId={eventId}
            eventName={event.name}
            refreshKey={refreshKey}
            isOwner={event.is_owner}
            coverPhotoId={event.cover_photo_id}
            onCoverUpdated={applyCoverUpdate}
          />
        </>
      )}
    </AppShell>
  );
}

export default function EventPreviewPage() {
  return (
    <RequireAuth>
      <EventPreviewContent />
    </RequireAuth>
  );
}
