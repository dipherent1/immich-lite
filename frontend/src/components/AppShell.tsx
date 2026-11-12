"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import NotificationBell from "@/components/NotificationBell";
import ProfileMenu from "@/components/ProfileMenu";
import { Brand, Icon } from "@/components/ui";

const LINKS = [
  { href: "/dashboard", label: "Events", icon: Icon.Ticket },
  { href: "/matches", label: "My photos", icon: Icon.Images },
];

/**
 * Chrome for signed-in pages.
 *   - Desktop: slim left sidebar (brand + Events / My photos) and a small
 *     top-right bar with the notification bell and the profile menu.
 *   - Mobile (≤720px): the sidebar hides, the top bar shows the brand, and a
 *     floating bottom tab bar carries the two destinations.
 * The bell and profile menu are rendered once (in the top bar) for both
 * layouts so only one live notification stream is ever opened.
 * `showBell` is off on the notifications page, which runs its own stream.
 */
export default function AppShell({
  children,
  showBell = true,
}: {
  children: ReactNode;
  showBell?: boolean;
}) {
  const pathname = usePathname();

  function isActive(href: string) {
    return pathname === href || (href === "/dashboard" && pathname.startsWith("/events"));
  }

  return (
    <>
      <div className="app-bg" aria-hidden />
      <div className="app-layout">
        <aside className="sidebar">
          <Brand href="/dashboard" />
          <nav className="side-nav" aria-label="Primary">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`side-link${isActive(l.href) ? " active" : ""}`}
              >
                <l.icon size={19} />
                {l.label}
              </Link>
            ))}
          </nav>
        </aside>

        <div className="app-main">
          <header className="topbar">
            <Brand href="/dashboard" />
            <div className="header-actions">
              {showBell && <NotificationBell />}
              <ProfileMenu />
            </div>
          </header>
          <main className="page">{children}</main>
        </div>
      </div>

      <nav className="tabbar" aria-label="Primary">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className={isActive(l.href) ? "active" : ""}>
            <l.icon size={20} />
            {l.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
