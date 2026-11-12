"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui";
import { getMe, logout, type UserResponse } from "@/lib/api";
import { initials, onboardingHref } from "@/lib/nav";

/**
 * Avatar button + dropdown: who you are, rescan your face (the one-time
 * enrollment lives in /onboarding; this is the only way back to it), all
 * notifications, and log out.
 */
export default function ProfileMenu() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => {
        // RequireAuth handles auth failures; the menu just shows a placeholder.
      });
  }, []);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function handleLogout() {
    logout(); // clears the stored token via lib/api
    router.push("/login");
  }

  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button
        type="button"
        className="avatar avatar-btn"
        aria-label="Account menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {user ? initials(user.display_name) : ""}
      </button>

      {open && (
        <div className="menu-pop" role="menu">
          {user && (
            <div className="menu-head">
              <strong>{user.display_name}</strong>
              <span className="muted small">{user.email}</span>
            </div>
          )}
          <Link
            href={onboardingHref(pathname)}
            className="menu-item"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <Icon.Face size={17} /> {user?.has_face_profile === false ? "Scan your face" : "Rescan face"}
          </Link>
          <Link
            href="/notifications"
            className="menu-item"
            role="menuitem"
            onClick={() => setOpen(false)}
          >
            <Icon.Bell size={17} /> All notifications
          </Link>
          <button type="button" className="menu-item" role="menuitem" onClick={handleLogout}>
            <Icon.Logout size={17} /> Log out
          </button>
        </div>
      )}
    </div>
  );
}
