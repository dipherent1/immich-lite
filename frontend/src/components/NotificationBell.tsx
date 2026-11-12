"use client";

// Bell icon + unread-count badge + dropdown of recent notifications. Uses the
// shared SSE hook (`useNotifications`) so it updates live. Clicking a
// notification marks it read and navigates to its subject.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useNotifications } from "@/lib/notifications";
import type { NotificationResponse } from "@/lib/api";
import { Icon } from "@/components/ui";

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

function iconFor(type: string): React.ReactNode {
  switch (type) {
    case "join_request":
      return <Icon.Users size={17} />;
    case "join_approved":
      return <Icon.Check size={17} />;
    case "join_denied":
      return <Icon.X size={17} />;
    case "event_expiring":
      return <Icon.Clock size={17} />;
    case "photo_matched":
      return <Icon.Images size={17} />;
    case "photo_processed":
      return <Icon.Upload size={17} />;
    default:
      return <Icon.Bell size={17} />;
  }
}

function iconTone(type: string): React.CSSProperties {
  if (type === "event_expiring") return { background: "var(--danger-soft)", color: "var(--danger)" };
  if (type === "photo_matched") return { background: "var(--accent-soft)", color: "var(--accent)" };
  if (type === "join_approved") return { background: "var(--ok-soft)", color: "var(--ok)" };
  if (type === "join_denied") return { background: "var(--danger-soft)", color: "var(--danger)" };
  return {};
}

function subjectHref(n: NotificationResponse): string {
  // "You were found in a photo" → your gallery is the useful destination.
  if (n.type === "photo_matched") return "/matches";
  // Join requests / approvals / processed uploads all carry the event id.
  if (n.subject_type === "event" && n.subject_id) return `/events/${n.subject_id}`;
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
      className={`notif${notif.is_read ? "" : " unread"}`}
    >
      <span className="notif-icon" style={iconTone(notif.type)}>
        {iconFor(notif.type)}
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span className="notif-title">{notif.title}</span>
        <span className="notif-body">{notif.body}</span>
        <span className="notif-time">{timeAgo(notif.created_at)}</span>
      </span>
      {!notif.is_read && (
        <span
          className="unread-dot"
          onClick={(e) => {
            e.stopPropagation();
            onMarkRead(notif.id);
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
        className="icon-btn"
        onClick={() => setOpen((o) => !o)}
        style={{ position: "relative" }}
      >
        <Icon.Bell />
        {unreadCount > 0 && <span className="count-badge">{unreadCount}</span>}
      </button>

      {open && (
        <div className="notif-pop">
          <div className="notif-pop-head">
            <strong>Notifications</strong>
            <span className="row" style={{ gap: 14 }}>
              <button type="button" onClick={markAllRead} className="link-btn">
                Mark all read
              </button>
              <Link href="/notifications" className="link-btn">
                View all
              </Link>
            </span>
          </div>
          {recent.length === 0 ? (
            <p className="muted small" style={{ padding: 20, textAlign: "center" }}>
              No notifications yet.
            </p>
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
