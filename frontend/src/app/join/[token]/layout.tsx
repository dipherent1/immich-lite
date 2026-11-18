import type { Metadata } from "next";
import type { ReactNode } from "react";

// A share link is a secret: keep it out of search indexes and don't leak it to
// other sites through the Referer header.
export const metadata: Metadata = {
  title: "You're invited | Immich Lite",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function JoinLayout({ children }: { children: ReactNode }) {
  return children;
}
