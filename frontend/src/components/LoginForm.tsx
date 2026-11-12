"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ApiError, getMe, login } from "@/lib/api";
import { nextFromLocation, onboardingHref } from "@/lib/nav";

export default function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Keep ?next= (e.g. an invite link) when switching to the register page.
  function goToRegister(e: React.MouseEvent) {
    e.preventDefault();
    const next = nextFromLocation("");
    router.push(next ? `/register?next=${encodeURIComponent(next)}` : "/register");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      // Go back to ?next= (e.g. /join/<token>) or the dashboard — via the
      // face-scan step first if this account never enrolled a face.
      const next = nextFromLocation();
      const me = await getMe().catch(() => null);
      router.push(me && !me.has_face_profile ? onboardingHref(next) : next);
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
        No account? <a href="/register" onClick={goToRegister}>Create one</a>
      </p>
    </form>
  );
}
