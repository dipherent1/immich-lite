"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import RequireAuth from "@/components/RequireAuth";
import { ApiError, getMe, logout, type UserResponse } from "@/lib/api";

function DashboardContent() {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Failed to load profile."),
      );
  }, []);

  function handleLogout() {
    logout(); // clears the stored token via lib/api
    router.push("/login");
  }

  return (
    <main style={{ padding: 40 }}>
      <h1>Dashboard</h1>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {user && (
        <dl>
          <dt>Name</dt>
          <dd>{user.display_name}</dd>
          <dt>Email</dt>
          <dd>{user.email}</dd>
          <dt>ID</dt>
          <dd>{user.id}</dd>
        </dl>
      )}
      <button onClick={handleLogout}>Log out</button>
    </main>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardContent />
    </RequireAuth>
  );
}
