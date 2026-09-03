"use client";

import Link from "next/link";

import MatchesGrid from "@/components/MatchesGrid";
import RequireAuth from "@/components/RequireAuth";

function MatchesContent() {
  return (
    <main style={{ padding: 40 }}>
      <p>
        <Link href="/dashboard">← Dashboard</Link>
      </p>
      <h1 style={{ marginTop: 8 }}>Matched photos</h1>
      <p style={{ color: "#666" }}>
        Photos from events you attended where your face was found.
      </p>
      <MatchesGrid />
    </main>
  );
}

export default function MatchesPage() {
  return (
    <RequireAuth>
      <MatchesContent />
    </RequireAuth>
  );
}
