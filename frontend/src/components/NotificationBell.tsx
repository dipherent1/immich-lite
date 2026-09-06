"use client";

// Bell icon + unread-count badge + dropdown of recent notifications. Uses the
// shared SSE hook (`useNotifications`) so it updates live. Clicking a
// notification marks it read and navigates to its subject.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useNotifications } from "@/lib/notifications";
import type { NotificationResponse } from "@/lib/api";

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function iconFor(type: string): string {
  switch (type) {
    case "join_request":
      return "👋";
    case "join_approved":
      return "✅";
    case "join_denied":
      return "🚫";
    case "photo_matched":
      return "📷";
    case "photo_processed":
      return "⚙️";
    default:
      return "🔔";
  }
}

function subjectHref(n: NotificationResponse): string {
  if (n.subject_type === "event" && n.subject_id) return `/events/${n.subject_id}`;
  if (n.subject_type === "photo" && n.subject_id) return `/events?focus=${n.subject_id}`;
  // join_request subject_id is the request row; route to events for a generic view.
  if (n.subject_type === "join_request") return `/events`;
  return "/dashboard";
}

function NotificationItem({
  notif,
  onMarkRead,
  onNavigate,
}: {
  notif: NotificationResponse;
  onMarkRead: (id: string) => void;
  onNavigate: (notif: NotificationResponse) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onNavigate(notif)}
      style={{
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
        width: "100%",
        border: "none",
        background: notif.is_read ? "transparent" : "#f4f8ff",
        padding: "10px 12px",
        cursor: "pointer",
        textAlign: "left",
        fontSize: "0.9rem",
        borderBottom: "1px solid #eee",
      }}
    >
      <span style={{ fontSize: "1.1rem" }}>{iconFor(notif.type)}</span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ fontWeight: 600, display: "block" }}>{notif.title}</span>
        <span style={{ color: "#555", display: "block" }}>{notif.body}</span>
        <span style={{ color: "#999", fontSize: "0.78rem" }}>{timeAgo(notif.created_at)}</span>
      </span>
      {!notif.is_read && (
        <span
          onClick={(e) => {
            e.stopPropagation();
            onMarkRead(notif.id);
          }}
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "#1a7f37",
            flexShrink: 0,
            marginTop: 4,
            cursor: "pointer",
          }}
          title="Mark as read"
        />
      )}
    </button>
  );
}

export default function NotificationBell() {
  const router = useRouter();
  const { notifications, unreadCount, markRead, markAllRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function handleNavigate(notif: NotificationResponse) {
    setOpen(false);
    // Mark read (fire and forget; the hook already optimistically flips it).
    if (!notif.is_read) markRead(notif.id);
    router.push(subjectHref(notif));
  }

  const recent = notifications.slice(0, 10);

  return (
    <div style={{ position: "relative" }} ref={panelRef}>
      <button
        type="button"
        aria-label="Notifications"
        onClick={() => setOpen((o) => !o)}
        style={{
          position: "relative",
          border: "1px solid #e2e2e2",
          background: "#fff",
          borderRadius: 8,
          padding: "8px 12px",
          cursor: "pointer",
          fontSize: "1.1rem",
        }}
      >
        🔔
        {unreadCount > 0 && (
          <span
            style={{
              position: "absolute",
              top: -6,
              right: -6,
              background: "#cf222e",
              color: "#fff",
              borderRadius: "50%",
              fontSize: "0.7rem",
              minWidth: 18,
              height: 18,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "0 4px",
              fontWeight: 700,
            }}
          >
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 8px)",
            width: 340,
            maxHeight: 420,
            overflowY: "auto",
            background: "#fff",
            border: "1px solid #ddd",
            borderRadius: 10,
            boxShadow: "0 6px 20px rgba(0,0,0,0.12)",
            zIndex: 50,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "10px 12px",
              borderBottom: "1px solid #eee",
            }}
          >
            <strong>Notifications</strong>
            <span style={{ display: "flex", gap: 10 }}>
              <button
                type="button"
                onClick={markAllRead}
                style={{ border: "none", background: "none", color: "#1a7f37", cursor: "pointer", fontSize: "0.85rem" }}
              >
                Mark all read
              </button>
              <Link href="/notifications" style={{ color: "#1a7f37", fontSize: "0.85rem" }}>
                View all
              </Link>
            </span>
          </div>
          {recent.length === 0 ? (
            <p style={{ padding: 16, color: "#666", margin: 0 }}>No notifications yet.</p>
          ) : (
            recent.map((n) => (
              <NotificationItem
                key={n.id}
                notif={n}
                onMarkRead={markRead}
                onNavigate={handleNavigate}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
