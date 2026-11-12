"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AppShell from "@/components/AppShell";
import EventSearch from "@/components/EventSearch";
import EventsView from "@/components/EventsView";
import RequireAuth from "@/components/RequireAuth";
import { Icon } from "@/components/ui";
import { getMe, type UserResponse } from "@/lib/api";
import { onboardingHref } from "@/lib/nav";

function DashboardContent() {
  const [user, setUser] = useState<UserResponse | null>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => {
        // RequireAuth handles auth failures; the greeting falls back to "there".
      });
  }, []);

  const firstName = user?.display_name.split(/\s+/)[0];

  return (
    <AppShell>
      <section className="dash-head">
        <div>
          <h1 className="h1">
            Hey{firstName ? "," : ""} <span className="accent-text">{firstName ?? "there"}</span>
          </h1>
          <p className="muted">Your events</p>
        </div>
        <EventSearch />
      </section>

      {user && !user.has_face_profile && (
        <Link href={onboardingHref("/dashboard")} className="face-banner">
          <span className="tile-icon">
            <Icon.Face size={22} />
          </span>
          <span style={{ flex: 1 }}>
            <strong style={{ display: "block" }}>Scan your face so photos can find you</strong>
            <span className="muted small">Takes about 20 seconds. You only do it once.</span>
          </span>
          <Icon.Arrow />
        </Link>
      )}

      <EventsView needsFaceScan={user?.has_face_profile === false} />
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
