"use client";

import AppShell from "@/components/AppShell";
import MatchesGrid from "@/components/MatchesGrid";
import RequireAuth from "@/components/RequireAuth";

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
            Shots from events you attended where your face was recognised.
          </p>
        </div>
      </div>
      <MatchesGrid />
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
