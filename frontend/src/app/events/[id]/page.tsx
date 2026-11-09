"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import AppShell from "@/components/AppShell";
import RequireAuth from "@/components/RequireAuth";
import { Icon } from "@/components/ui";
import PhotoGrid from "@/components/PhotoGrid";
import {
  ApiError,
  approveRequest,
  denyRequest,
  getEvent,
  listPendingRequests,
  uploadEventPhoto,
  type EventDetailResponse,
  type JoinRequestResponse,
} from "@/lib/api";

function joinLinkFor(token: string): string {
  return `${window.location.origin}/join/${token}`;
}

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
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [joinRequests, setJoinRequests] = useState<JoinRequestResponse[]>([]);
  const [requestsNote, setRequestsNote] = useState<string | null>(null);
  const previewUrlsRef = useRef<string[]>([]);

  useEffect(() => {
    const urls = previewUrlsRef.current;
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, []);

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
  // button is hit.
  function onFilesSelected(list: FileList | null) {
    if (!list) return;
    previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    const next: SelectedImage[] = Array.from(list).map((file) => ({
      file,
      url: URL.createObjectURL(file),
    }));
    previewUrlsRef.current = next.map((s) => s.url);
    setSelected(next);
    setUploadNote(null);
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
    const results = await Promise.allSettled(
      selected.map((s) => uploadEventPhoto(eventId, s.file)),
    );
    const failed = results.filter((r) => r.status === "rejected").length;
    const succeeded = results.length - failed;
    setUploading(false);
    previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    previewUrlsRef.current = [];
    setSelected([]);
    // Reload the grid so the new photos show up (as "pending" then processed).
    setRefreshKey((k) => k + 1);
    if (failed > 0) {
      setUploadNote(
        `${succeeded} of ${results.length} uploaded; ${failed} failed. Check that each file is an image under 20 MB.`,
      );
    } else {
      setUploadNote(`${results.length} photo${results.length === 1 ? "" : "s"} uploaded.`);
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
    new Date(iso).toLocaleString(undefined, {
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
          <section className="event-hero grain" style={{ marginTop: 16 }}>
            <div className="stars" />
            <div className="row" style={{ justifyContent: "center", position: "relative" }}>
              {event.expires_at ? (
                <span className={`badge ${event.active ? "badge-open" : "badge-closed"}`}>
                  {event.active ? "Open" : "Closed"}
                </span>
              ) : (
                <span className="badge badge-open">Open · no end</span>
              )}
              {event.is_owner && <span className="badge">You&apos;re the host</span>}
            </div>
            <h1 className="display" style={{ position: "relative" }}>
              {event.name}
            </h1>
            <p className="muted" style={{ position: "relative" }}>
              Starts {fmt(event.starts_at)}
            </p>
          </section>

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
                <Icon.Clock size={13} /> Closes
              </div>
              <div className="fact-value">
                {event.expires_at ? fmt(event.expires_at) : "No closing time"}
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
                  accept="image/*"
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
                  JPG or PNG, up to 20 MB each. We&apos;ll match faces automatically.
                </span>
              </label>

              {selected.length > 0 && (
                <div className="queue">
                  {selected.map((img, i) => (
                    <div key={img.url} className="queue-item">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={img.url} alt={`Selected photo ${i + 1}`} />
                      <button
                        type="button"
                        aria-label={`Remove photo ${i + 1}`}
                        onClick={() => removeSelected(i)}
                      >
                        <Icon.X size={12} />
                      </button>
                    </div>
                  ))}
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
                    <span className="spinner" /> Uploading…
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

          <PhotoGrid eventId={eventId} refreshKey={refreshKey} />
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
