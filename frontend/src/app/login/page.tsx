import type { Metadata } from "next";

import AuthShell from "@/components/AuthShell";
import LoginForm from "@/components/LoginForm";

export const metadata: Metadata = {
  title: "Log in | Immich Lite",
};

export default function LoginPage() {
  return (
    <AuthShell
      headline={
        <>
          Your photos
          <br />
          <span className="accent-text">found you.</span>
        </>
      }
      sub="Log in to see every shot you appeared in across the events you joined."
    >
      <LoginForm />
    </AuthShell>
  );
}
