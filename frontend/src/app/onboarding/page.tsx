"use client";

import { useRouter } from "next/navigation";

import FaceScan from "@/components/FaceScan";
import RequireAuth from "@/components/RequireAuth";
import { Brand } from "@/components/ui";
import { nextFromLocation } from "@/lib/nav";

/**
 * One-time face enrollment step, shown right after registration (and after
 * login for accounts that never scanned). Also reachable from the profile
 * menu as "Rescan face". When done — or skipped — the user continues to
 * `?next=` (e.g. /join/<token> so an invite link finishes joining), else the
 * dashboard.
 */
function OnboardingContent() {
  const router = useRouter();

  function proceed() {
    router.push(nextFromLocation());
  }

  return (
    <main className="center-page grain">
      <div className="stars" />
      <div className="onboarding">
        <Brand href="/dashboard" />
        <div style={{ display: "grid", gap: 8, textAlign: "center" }}>
          <span className="eyebrow" style={{ justifySelf: "center" }}>
            One last step
          </span>
          <h1 className="h1" style={{ fontSize: "1.9rem" }}>
            Let photos find you
          </h1>
          <p className="muted">
            Scan your face once. Whenever someone uploads a photo you&apos;re in, it lands in
            your gallery automatically.
          </p>
        </div>
        <FaceScan onComplete={() => setTimeout(proceed, 900)} />
        <button type="button" className="link-btn" style={{ justifySelf: "center" }} onClick={proceed}>
          Skip for now
        </button>
      </div>
    </main>
  );
}

export default function OnboardingPage() {
  return (
    <RequireAuth>
      <OnboardingContent />
    </RequireAuth>
  );
}
