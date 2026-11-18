"use client";

import AppShell from "@/components/AppShell";
import MatchAlbums from "@/components/MatchAlbums";
import RequireAuth from "@/components/RequireAuth";
import { EVENT_LIFETIME_HOURS } from "@/lib/lifetime";

function MatchesContent() {
  return (
    <AppShell>
      <div className="page-head">
        <div>
          <span className="eyebrow">Your gallery</span>
          <h1 className="h1">
            Photos that <span className="accent-text">found you</span>
          </h1>
          <p className="muted" style={{ marginTop: 8 }}>
            One album per event. Open one to see your photos and download them. Events are
            deleted {EVENT_LIFETIME_HOURS} hours after they&apos;re created, photos included.
          </p>
        </div>
      </div>
      <MatchAlbums />
    </AppShell>
  );
}

export default function MatchesPage() {
  return (
    <RequireAuth>
      <MatchesContent />
    </RequireAuth>
  );
}
