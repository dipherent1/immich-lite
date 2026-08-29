import type { Metadata } from "next";

import RegisterForm from "@/components/RegisterForm";

export const metadata: Metadata = {
  title: "Register | Immich Lite",
};

export default function RegisterPage() {
  return (
    <main style={{ padding: 40 }}>
      <RegisterForm />
    </main>
  );
}
