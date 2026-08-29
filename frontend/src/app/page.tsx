import Link from "next/link";

export default function Home() {
  return (
    <main style={{ padding: 40 }}>
      <h1>Immich Lite</h1>
      <p>Face-based photo matching for events.</p>
      <nav style={{ display: "grid", gap: 8, marginTop: 20 }}>
        <Link href="/login">Log in</Link>
        <Link href="/register">Register</Link>
        <Link href="/dashboard">Dashboard</Link>
      </nav>
    </main>
  );
}
