"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type PropsWithChildren } from "react";

import { isAuthenticated } from "@/lib/api";

/**
 * Client guard for protected pages. If there's no stored JWT it redirects to
 * /login. Reads auth state only through lib/api (never localStorage directly).
 */
export default function RequireAuth({ children }: PropsWithChildren) {
  const router = useRouter();
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  useEffect(() => {
    if (authed === false) {
      router.replace("/login");
    }
  }, [authed, router]);

  if (authed !== true) {
    return null; // brief blank while checking / redirecting
  }

  return <>{children}</>;
}
