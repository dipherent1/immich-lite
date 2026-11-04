"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import NotificationBell from "@/components/NotificationBell";
import { Brand, Icon } from "@/components/ui";
import { logout } from "@/lib/api";

const LINKS = [
  { href: "/dashboard", label: "Dashboard", icon: Icon.Ticket },
  { href: "/matches", label: "My photos", icon: Icon.Images },
  { href: "/notifications", label: "Alerts", icon: Icon.Bell },
];

/**
 * Chrome for signed-in pages: sticky top bar (brand, nav, bell, logout) and a
 * floating tab bar on mobile. `showBell` is off on the notifications page so it
 * doesn't open a second live stream next to the page's own.
 */
export default function AppShell({
  children,
  showBell = true,
}: {
  children: ReactNode;
  showBell?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();

  function isActive(href: string) {
    return pathname === href || (href === "/dashboard" && pathname.startsWith("/events"));
  }

  function handleLogout() {
    logout(); // clears the stored token via lib/api
    router.push("/login");
  }

  return (
    <>
      <div className="app-bg" aria-hidden />
      <header className="site-header">
        <div className="container site-header-inner">
          <Brand href="/dashboard" />
          <nav className="nav hide-mobile">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`nav-link${isActive(l.href) ? " active" : ""}`}
              >
                {l.label}
              </Link>
            ))}
          </nav>
          <div className="header-actions">
            {showBell && <NotificationBell />}
            <button
              type="button"
              className="icon-btn"
              onClick={handleLogout}
              aria-label="Log out"
              title="Log out"
            >
              <Icon.Logout />
            </button>
          </div>
        </div>
      </header>

      <main className="page">{children}</main>

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
