"use client";

// Full notification history page with pagination + mark-all-read. Reuses the
// shared SSE hook so new notifications stream in live.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import RequireAuth from "@/components/RequireAuth";
import { useNotifications } from "@/lib/notifications";
import type { NotificationResponse } from "@/lib/api";

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} minutes ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hours ago`;
  const days = Math.floor(hrs / 24);
  return `${days} days ago`;
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
  if (n.subject_type === "photo" && n.subject_id) return `/matches`;
  return "/dashboard";
}

function NotificationsContent() {
  const router = useRouter();
  const { notifications, markRead, markAllRead } = useNotifications();
  const [readFilter, setReadFilter] = useState<"all" | "unread">("all");

  const shown = readFilter === "unread" ? notifications.filter((n) => !n.is_read) : notifications;

  function handleNavigate(notif: NotificationResponse) {
    if (!notif.is_read) markRead(notif.id);
    router.push(subjectHref(notif));
  }

  return (
    <main style={{ padding: 40, maxWidth: 720, margin: "0 auto" }}>
      <p>
        <Link href="/dashboard">← Dashboard</Link>
      </p>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 8,
        }}
      >
        <h1 style={{ margin: 0 }}>Notifications</h1>
        <button
          type="button"
          onClick={markAllRead}
          style={{
            border: "1px solid #e2e2e2",
            background: "#fff",
            borderRadius: 6,
            padding: "6px 12px",
            cursor: "pointer",
          }}
        >
          Mark all read
        </button>
      </div>

      <div style={{ display: "flex", gap: 8, margin: "16px 0" }}>
        {(["all", "unread"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setReadFilter(f)}
            style={{
              border: "1px solid #e2e2e2",
              background: readFilter === f ? "#eef4ff" : "#fff",
              borderRadius: 20,
              padding: "4px 14px",
              cursor: "pointer",
              fontWeight: readFilter === f ? 700 : 400,
            }}
          >
            {f === "all" ? "All" : "Unread"}
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <p style={{ color: "#666" }}>No {readFilter === "unread" ? "unread " : ""}notifications.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {shown.map((n) => (
            <li
              key={n.id}
              onClick={() => handleNavigate(n)}
              style={{
                display: "flex",
                gap: 12,
                alignItems: "flex-start",
                padding: 12,
                borderBottom: "1px solid #eee",
                borderRadius: 8,
                background: n.is_read ? "transparent" : "#f4f8ff",
                cursor: "pointer",
              }}
            >
              <span style={{ fontSize: "1.3rem" }}>{iconFor(n.type)}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600 }}>{n.title}</div>
                <div style={{ color: "#555", marginTop: 2 }}>{n.body}</div>
                <div style={{ color: "#999", fontSize: "0.8rem", marginTop: 4 }}>
                  {timeAgo(n.created_at)}
                </div>
              </div>
              {!n.is_read && (
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    background: "#1a7f37",
                    flexShrink: 0,
                    marginTop: 6,
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

export default function NotificationsPage() {
  return (
    <RequireAuth>
      <NotificationsContent />
    </RequireAuth>
  );
}
