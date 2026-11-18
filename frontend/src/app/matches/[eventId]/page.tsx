"use client";

import { useParams } from "next/navigation";

import AppShell from "@/components/AppShell";
import MatchEventPhotos from "@/components/MatchEventPhotos";
import RequireAuth from "@/components/RequireAuth";

function AlbumContent() {
  const params = useParams<{ eventId: string }>();
  const eventId = params?.eventId ?? "";
  return <AppShell>{eventId ? <MatchEventPhotos eventId={eventId} /> : null}</AppShell>;
}

export default function AlbumPage() {
  return (
    <RequireAuth>
      <AlbumContent />
    </RequireAuth>
  );
}
