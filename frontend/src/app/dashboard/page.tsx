"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import EventsView from "@/components/EventsView";
import FaceScan from "@/components/FaceScan";
import RequireAuth from "@/components/RequireAuth";
import { Icon } from "@/components/ui";
import { ApiError, getMe, type UserResponse } from "@/lib/api";

function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase())
      .join("") || "?"
  );
}

function DashboardContent() {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Failed to load profile."),
      );
  }, []);

  const firstName = user?.display_name.split(/\s+/)[0];

  return (
    <AppShell>
      <section className="welcome">
        <div style={{ display: "grid", gap: 12 }}>
          <span className="eyebrow">Dashboard</span>
          <h1 className="display">
            Hey{firstName ? "," : ""}{" "}
            <span className="accent-text">{firstName ?? "there"}</span>
          </h1>
          <p className="muted">Create an event, join one, or check what photos found you.</p>
        </div>
        {user && (
          <div className="user-chip">
            <span className="avatar">{initials(user.display_name)}</span>
            <span className="user-name">
              <strong style={{ display: "block" }}>{user.display_name}</strong>
              <span className="muted small">{user.email}</span>
            </span>
          </div>
        )}
      </section>

      {error && (
        <p className="alert alert-error" style={{ marginBottom: 20 }}>
          {error}
        </p>
      )}

      <div className="tiles">
        <Link href="/matches" className="tile">
          <span className="tile-icon">
            <Icon.Images size={22} />
          </span>
          <span style={{ flex: 1 }}>
            <span className="tile-title" style={{ display: "block" }}>
              Your matched photos
            </span>
            <span className="muted small">Every shot you were found in</span>
          </span>
          <Icon.Arrow />
        </Link>
        <a href="#events" className="tile">
          <span className="tile-icon">
            <Icon.Ticket size={22} />
          </span>
          <span style={{ flex: 1 }}>
            <span className="tile-title" style={{ display: "block" }}>
              Your events
            </span>
            <span className="muted small">Hosted &amp; joined</span>
          </span>
          <Icon.Arrow />
        </a>
        <Link href="/notifications" className="tile">
          <span className="tile-icon">
            <Icon.Bell size={22} />
          </span>
          <span style={{ flex: 1 }}>
            <span className="tile-title" style={{ display: "block" }}>
              Notifications
            </span>
            <span className="muted small">Requests &amp; new matches</span>
          </span>
          <Icon.Arrow />
        </Link>
      </div>

      <EventsView leading={<FaceScan />} />
    </AppShell>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardContent />
    </RequireAuth>
  );
}
