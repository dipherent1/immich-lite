"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ApiError, register } from "@/lib/api";

export default function RegisterForm() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(email, password, displayName);
      router.push("/login");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="auth-form">
      <div style={{ display: "grid", gap: 8 }}>
        <span className="eyebrow">Get started</span>
        <h1 className="h1">Create account</h1>
        <p className="muted">Takes a minute. Then scan your face and you&apos;re set.</p>
      </div>

      <div className="field">
        <label className="label" htmlFor="reg-name">
          Display name
        </label>
        <input
          id="reg-name"
          className="input"
          type="text"
          required
          autoComplete="name"
          placeholder="What should we call you?"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
      </div>

      <div className="field">
        <label className="label" htmlFor="reg-email">
          Email
        </label>
        <input
          id="reg-email"
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
        <label className="label" htmlFor="reg-password">
          Password
        </label>
        <input
          id="reg-password"
          className="input"
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          placeholder="At least 8 characters"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>

      {error && <p className="alert alert-error">{error}</p>}

      <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={submitting}>
        {submitting ? (
          <>
            <span className="spinner" /> Creating account…
          </>
        ) : (
          "Create account"
        )}
      </button>

      <p className="auth-switch">
        Have an account? <a href="/login">Log in</a>
      </p>
    </form>
  );
}
