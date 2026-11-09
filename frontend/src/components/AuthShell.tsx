import type { ReactNode } from "react";

import { Brand } from "@/components/ui";

/** Split-screen layout for login / register: cinematic art left, form right. */
export default function AuthShell({
  children,
  headline,
  sub,
}: {
  children: ReactNode;
  headline: ReactNode;
  sub: string;
}) {
  return (
    <main className="auth">
      <aside className="auth-art grain">
        <div className="stars" />
        <div className="glow" />
        <Brand />
        <div style={{ display: "grid", gap: 18 }}>
          <h2 className="display">{headline}</h2>
          <p className="muted" style={{ maxWidth: 380 }}>
            {sub}
          </p>
        </div>
        <p className="muted small">Face-based photo matching for events.</p>
      </aside>

      <section className="auth-panel">
        <div className="auth-mobile-brand" style={{ marginBottom: 24 }}>
          <Brand />
        </div>
        <div className="auth-form-wrap">{children}</div>
      </section>
    </main>
  );
}
