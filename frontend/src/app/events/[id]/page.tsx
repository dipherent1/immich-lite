"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import RequireAuth from "@/components/RequireAuth";
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

  const styles = {
    card: {
      border: "1px solid #e2e2e2",
      borderRadius: 8,
      padding: 16,
      maxWidth: 520,
    } as const,
    muted: { color: "#666", margin: "6px 0" } as const,
    badge: (active: boolean) => ({
      display: "inline-block",
      padding: "2px 10px",
      borderRadius: 12,
      fontSize: "0.8rem",
      fontWeight: 600,
      background: active ? "#e6f6ee" : "#f1f1f1",
      color: active ? "#1a7f37" : "#666",
    }),
  } as const;

  return (
    <main style={{ padding: 40 }}>
      <p>
        <Link href="/dashboard">← Dashboard</Link>
      </p>

      {error && <p style={{ color: "#cf222e" }}>{error}</p>}

      {!event && !error ? <p>Loading event…</p> : null}

      {event && (
        <>
          <h1 style={{ marginTop: 8 }}>{event.name}</h1>
          <p>
            {event.expires_at ? (
              <span style={styles.badge(event.active)}>
                {event.active ? "Open" : "Closed"}
              </span>
            ) : (
              <span style={styles.badge(true)}>Open (no end)</span>
            )}
          </p>

          <dl style={{ marginTop: 16 }}>
            <dt style={{ fontWeight: 600 }}>Created</dt>
            <dd style={{ margin: "0 0 12px" }}>
              {new Date(event.created_at).toLocaleString()}
            </dd>
            <dt style={{ fontWeight: 600 }}>Starts</dt>
            <dd style={{ margin: "0 0 12px" }}>
              {new Date(event.starts_at).toLocaleString()}
            </dd>
            <dt style={{ fontWeight: 600 }}>Closes</dt>
            <dd style={{ margin: "0 0 12px" }}>
              {event.expires_at
                ? new Date(event.expires_at).toLocaleString()
                : "No closing time set"}
            </dd>
            <dt style={{ fontWeight: 600 }}>Attendees</dt>
            <dd style={{ margin: "0 0 12px" }}>
              {event.attendee_count}
            </dd>
          </dl>

          <div style={{ marginTop: 16, ...styles.card }}>
            <p style={{ margin: 0, fontWeight: 600 }}>Invite link</p>
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
              <code
                style={{
                  background: "#f4f4f4",
                  padding: "6px 8px",
                  borderRadius: 6,
                  flex: 1,
                  fontSize: "0.85rem",
                  wordBreak: "break-all",
                }}
              >
                {joinLinkFor(event.join_token)}
              </code>
              <button onClick={() => copyLink(event.join_token)}>Copy</button>
            </div>
          </div>

<div style={{ marginTop: 24 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
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
                style={{ maxWidth: 260 }}
              />
              <button
                type="button"
                disabled={uploading || selected.length === 0}
                onClick={onUploadSelected}
              >
                {uploading
                  ? "Uploading…"
                  : selected.length === 0
                    ? "Upload photos"
                    : `Upload ${selected.length} ${
                        selected.length === 1 ? "photo" : "photos"
                      }`}
              </button>
            </div>
            <p style={{ color: "#666", margin: "8px 0 0" }}>
              {selected.length > 0
                ? `${selected.length} file${selected.length === 1 ? "" : "s"} ready — click Upload, or press × on a thumbnail to cancel it.`
                : "Choose one or more photos to upload."}
            </p>
            {selected.length > 0 && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(72px, 1fr))",
                  gap: 8,
                  marginTop: 12,
                  maxWidth: 520,
                }}
              >
                {selected.map((img, i) => (
                  <div
                    key={img.url}
                    style={{
                      position: "relative",
                      aspectRatio: "1 / 1",
                      overflow: "hidden",
                      borderRadius: 6,
                      background: "#f0f0f0",
                    }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={img.url}
                      alt={`Selected photo ${i + 1}`}
                      style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                      }}
                    />
                    <button
                      type="button"
                      aria-label={`Remove photo ${i + 1}`}
                      onClick={() => removeSelected(i)}
                      style={{
                        position: "absolute",
                        top: 2,
                        right: 2,
                        width: 20,
                        height: 20,
                        borderRadius: "50%",
                        border: "none",
                        background: "rgba(0, 0, 0, 0.65)",
                        color: "#fff",
                        fontSize: 12,
                        lineHeight: 1,
                        cursor: "pointer",
                      }}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
            {uploadNote && (
              <p
                style={{
                  color: uploadNote.includes("failed") ? "#cf222e" : "#1a7f37",
                  margin: "8px 0 0",
                }}
              >
                {uploadNote}
              </p>
            )}
          </div>

          {event.is_owner && (
            <div style={{ marginTop: 24, border: "1px solid #ddd", borderRadius: 8, padding: 16, maxWidth: 520 }}>
              <h2 style={{ fontSize: 20, fontWeight: 600, marginTop: 0 }}>
                Join requests
                {joinRequests.length > 0 && ` (${joinRequests.length} pending)`}
              </h2>
              {requestsNote && (
                <p style={{ color: requestsNote.startsWith("Could") ? "#cf222e" : "#1a7f37", margin: "8px 0" }}>
                  {requestsNote}
                </p>
              )}
              {joinRequests.length === 0 ? (
                <p style={{ color: "#666", margin: 0 }}>No pending join requests.</p>
              ) : (
                <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {joinRequests.map((req) => (
                    <li
                      key={req.id}
                      style={{
                        display: "flex",
                        gap: 10,
                        alignItems: "center",
                        padding: "10px 0",
                        borderBottom: "1px solid #eee",
                        justifyContent: "space-between",
                      }}
                    >
                      <div>
                        <strong>{req.requester_name}</strong>
                        <p style={{ margin: "2px 0 0", color: "#666", fontSize: "0.85rem" }}>
                          Requested {new Date(req.created_at).toLocaleString()}
                        </p>
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button
                          type="button"
                          onClick={() => handleApprove(req.id)}
                          style={{ cursor: "pointer", padding: "4px 12px", background: "#e6f6ee", border: "1px solid #1a7f37", borderRadius: 6, color: "#1a7f37" }}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeny(req.id)}
                          style={{ cursor: "pointer", padding: "4px 12px", background: "#fff", border: "1px solid #cf222e", borderRadius: 6, color: "#cf222e" }}
                        >
                          Deny
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <PhotoGrid eventId={eventId} refreshKey={refreshKey} />
        </>
      )}
    </main>
  );
}

export default function EventPreviewPage() {
  return (
    <RequireAuth>
      <EventPreviewContent />
    </RequireAuth>
  );
}
