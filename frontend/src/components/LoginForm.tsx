"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ApiError, login } from "@/lib/api";

export default function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      // If the user came here to join an event (e.g. /login?next=/join/<token>),
      // send them back there; otherwise go to the dashboard.
      const next = new URLSearchParams(window.location.search).get("next");
      router.push(next ?? "/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="auth-form">
      <div style={{ display: "grid", gap: 8 }}>
        <span className="eyebrow">Welcome back</span>
        <h1 className="h1">Log in</h1>
        <p className="muted">Pick up where you left off — your matches are waiting.</p>
      </div>

      <div className="field">
        <label className="label" htmlFor="login-email">
          Email
        </label>
        <input
          id="login-email"
          className="input"
          type="email"
          required
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      <div className="field">
        <label className="label" htmlFor="login-password">
          Password
        </label>
        <input
          id="login-password"
          className="input"
          type="password"
          required
          autoComplete="current-password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>

      {error && <p className="alert alert-error">{error}</p>}

      <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={submitting}>
        {submitting ? (
          <>
            <span className="spinner" /> Logging in…
          </>
        ) : (
          "Log in"
        )}
      </button>

      <p className="auth-switch">
        No account? <a href="/register">Create one</a>
      </p>
    </form>
  );
}
