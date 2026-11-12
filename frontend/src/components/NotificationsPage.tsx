"use client";

// Full notification history page with pagination + mark-all-read. Reuses the
// shared SSE hook so new notifications stream in live.

import AppShell from "@/components/AppShell";
import { useRouter } from "next/navigation";
import { useState } from "react";

import RequireAuth from "@/components/RequireAuth";
import { useNotifications } from "@/lib/notifications";
import type { NotificationResponse } from "@/lib/api";
import { Icon } from "@/components/ui";

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

function iconFor(type: string): React.ReactNode {
  switch (type) {
    case "join_request":
      return <Icon.Users size={17} />;
    case "join_approved":
      return <Icon.Check size={17} />;
    case "join_denied":
      return <Icon.X size={17} />;
    case "photo_matched":
      return <Icon.Images size={17} />;
    case "photo_processed":
      return <Icon.Upload size={17} />;
    default:
      return <Icon.Bell size={17} />;
  }
}

function iconTone(type: string): React.CSSProperties {
  if (type === "photo_matched") return { background: "var(--accent-soft)", color: "var(--accent)" };
  if (type === "join_approved") return { background: "var(--ok-soft)", color: "var(--ok)" };
  if (type === "join_denied") return { background: "var(--danger-soft)", color: "var(--danger)" };
  return {};
}

function subjectHref(n: NotificationResponse): string {
  if (n.type === "photo_matched") return "/matches";
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
    <AppShell showBell={false}>
      <div style={{ maxWidth: 760, margin: "0 auto" }}>
        <div className="page-head">
          <div>
            <span className="eyebrow">Inbox</span>
            <h1 className="h1">Notifications</h1>
          </div>
          <button type="button" onClick={markAllRead} className="btn btn-sm">
            <Icon.Check size={15} /> Mark all read
          </button>
        </div>

        <div className="segmented" style={{ marginBottom: 16 }}>
          {(["all", "unread"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setReadFilter(f)}
              className={readFilter === f ? "active" : ""}
            >
              {f === "all" ? "All" : "Unread"}
            </button>
          ))}
        </div>

        {shown.length === 0 ? (
          <div className="empty">
            <Icon.Bell size={28} />
            <span>No {readFilter === "unread" ? "unread " : ""}notifications.</span>
          </div>
        ) : (
          <div className="notif-list">
            {shown.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => handleNavigate(n)}
                className={`notif${n.is_read ? "" : " unread"}`}
              >
                <span className="notif-icon" style={iconTone(n.type)}>
                  {iconFor(n.type)}
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span className="notif-title">{n.title}</span>
                  <span className="notif-body">{n.body}</span>
                  <span className="notif-time">{timeAgo(n.created_at)}</span>
                </span>
                {!n.is_read && <span className="unread-dot" />}
              </button>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}

export default function NotificationsPage() {
  return (
    <RequireAuth>
      <NotificationsContent />
    </RequireAuth>
  );
}
