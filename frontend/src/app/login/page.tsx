import type { Metadata } from "next";

import LoginForm from "@/components/LoginForm";

export const metadata: Metadata = {
  title: "Log in | Immich Lite",
};

export default function LoginPage() {
  return (
    <main style={{ padding: 40 }}>
      <LoginForm />
    </main>
  );
}
