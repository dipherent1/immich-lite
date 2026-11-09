import type { Metadata } from "next";

import AuthShell from "@/components/AuthShell";
import RegisterForm from "@/components/RegisterForm";

export const metadata: Metadata = {
  title: "Register | Immich Lite",
};

export default function RegisterPage() {
  return (
    <AuthShell
      headline={
        <>
          Be in the
          <br />
          <span className="accent-text">picture.</span>
        </>
      }
      sub="One quick face scan and every event you join sends you the photos you're in."
    >
      <RegisterForm />
    </AuthShell>
  );
}
