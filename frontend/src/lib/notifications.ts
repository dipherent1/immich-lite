"use client";

// SSE hook for live notifications. Owns the EventSource connection to the
// backend's /api/v1/notifications/stream and exposes the list of live events so
// the notification bell/pages can react in real time without polling.

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  getNotifications,
  getUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationResponse,
} from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("immich_lite_token");
}

/** Fetches the first page of notifications for the current user. */
async function fetchInitial(): Promise<NotificationResponse[]> {
  try {
    const data = await getNotifications(0, 24);
    return data.items;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return [];
    throw err;
  }
}

export function useNotifications() {
  const [notifications, setNotifications] = useState<NotificationResponse[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const tokenRef = useRef<string | null>(null);

  // Load the initial snapshot + unread count once.
  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchInitial(), getUnreadCount()])
      .then(([items, count]) => {
        if (cancelled) return;
        setNotifications(items);
        setUnreadCount(count.count);
      })
      .catch(() => {
        if (cancelled) return;
        setNotifications([]);
        setUnreadCount(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Open the SSE stream (auto-reconnect).
  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    function open() {
      const token = getToken();
      if (!token) {
        setConnected(false);
        return;
      }
      tokenRef.current = token;
      // The backend uses HTTPBearer; EventSource can't send a Bearer header, so
      // pass the token as a query param (dev-local: acceptable; tokens are
      // short-lived JWTs).
      es = new EventSource(
        `${API_BASE_URL}/api/v1/notifications/stream?token=${encodeURIComponent(token)}`,
      );
      es.onopen = () => setConnected(true);
      es.onerror = () => {
        setConnected(false);
        // Auto-reconnect handled by EventSource; also schedule a manual retry.
        if (!closed) {
          retryTimer = setTimeout(() => open(), 3000);
        }
      };
      es.addEventListener("notification", (event) => {
        try {
          const notif = JSON.parse((event as MessageEvent).data) as NotificationResponse;
          setNotifications((prev) => [notif, ...prev]);
          if (!notif.is_read) setUnreadCount((n) => n + 1);
        } catch {
          // ignore malformed events
        }
      });
    }

    open();

    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      es?.close();
    };
  }, []);

  const markRead = useCallback(async (id: string) => {
    // Optimistically flip to read.
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
    );
    setUnreadCount((n) => Math.max(0, n - 1));
    try {
      await markNotificationRead(id);
    } catch {
      // revert on failure
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: false } : n)),
      );
      setUnreadCount((n) => n + 1);
    }
  }, []);

  const markAllRead = useCallback(async () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
    try {
      await markAllNotificationsRead();
    } catch {
      // best-effort; the badge may be stale until next poll
    }
  }, []);

  return {
    notifications,
    unreadCount,
    connected,
    loading,
    markRead,
    markAllRead,
    setNotifications,
  };
}
