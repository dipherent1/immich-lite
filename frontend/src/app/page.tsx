import Link from "next/link";

import { Brand, Icon } from "@/components/ui";

const STEPS = [
  {
    n: "01",
    icon: <Icon.Face size={44} />,
    meta: ["~20 seconds", "3 quick poses"],
    title: "Scan your face once",
    body: "Front, left, right. We turn it into a private face profile — no selfies stored, just a vector.",
  },
  {
    n: "02",
    icon: <Icon.Ticket size={44} />,
    meta: ["Share link", "Or request to join"],
    title: "Join the event",
    body: "Tap the invite link from the host, or find the event and ask to get in. Hosts approve who's on the list.",
  },
  {
    n: "03",
    icon: <Icon.Images size={44} />,
    meta: ["Live notifications", "Only your shots"],
    title: "Get every photo you're in",
    body: "As the photographer uploads, we find you in the crowd and drop those shots straight into your feed.",
  },
];

// Abstract "photo" tiles for the mosaic — gradients that read like stage light.
const TILES: { cls: string; bg: string; tag?: string }[] = [
  { cls: "tall matched", bg: "linear-gradient(160deg,#3a1d06 0%,#a8501a 55%,#ffb347 100%)", tag: "98% match" },
  { cls: "", bg: "linear-gradient(200deg,#0b1a33 0%,#1d4b8f 70%,#7fb2ff 100%)" },
  { cls: "", bg: "linear-gradient(140deg,#1a0f12 0%,#5a1c2a 60%,#e2565f 100%)" },
  { cls: "wide matched", bg: "linear-gradient(110deg,#141008 0%,#5c3a0b 50%,#ffc94d 100%)", tag: "94% match" },
  { cls: "", bg: "linear-gradient(180deg,#0f1512 0%,#1f4a3a 70%,#3ddc97 120%)" },
  { cls: "wide", bg: "linear-gradient(60deg,#120d1a 0%,#2b2238 50%,#ff8a5b 130%)" },
];

export default function Home() {
  return (
    <>
      <header className="site-header transparent">
        <div className="container site-header-inner">
          <Brand />
          <nav className="nav hide-mobile">
            <a className="nav-link" href="#how">How it works</a>
            <a className="nav-link" href="#features">For hosts</a>
          </nav>
          <div className="header-actions">
            <Link className="btn btn-ghost btn-sm" href="/login">
              Log in
            </Link>
            <Link className="btn btn-primary btn-sm" href="/register">
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main style={{ flex: 1 }}>
        {/* Hero */}
        <section className="hero grain">
          <div className="stars" />
          <div className="glow glow-a" />
          <div className="glow glow-b" />
          <div className="orbits" aria-hidden>
            <span />
            <span />
            <span />
            <span />
          </div>

          <div className="container hero-inner">
            <div className="viewfinder" aria-hidden>
              <span className="corner tl" />
              <span className="corner tr" />
              <span className="corner bl" />
              <span className="corner br" />
              <div className="viewfinder-core">
                <svg className="viewfinder-face" viewBox="0 0 100 100" fill="none" stroke="currentColor" strokeWidth="1.2">
                  <ellipse cx="50" cy="46" rx="26" ry="32" opacity=".7" />
                  <path d="M38 40h6M56 40h6" strokeWidth="2.2" strokeLinecap="round" />
                  <path d="M50 44v10l-4 2" opacity=".7" />
                  <path d="M41 63c5 4 13 4 18 0" strokeLinecap="round" />
                  <path d="M20 96c4-14 16-20 30-20s26 6 30 20" opacity=".5" />
                </svg>
                <span className="scanline" />
              </div>
              <span className="match-pill p1">
                <span className="dot" /> 12 photos found
              </span>
              <span className="match-pill p2">
                <Icon.Face size={14} /> Face profile ready
              </span>
            </div>

            <h1 className="display hero-title">
              Find <span className="outline">your</span>
              <br />
              <span className="accent-text">shots</span>
            </h1>

            <p className="hero-sub">
              Every event photo you&apos;re in — found by your face and delivered to
              you. No scrolling through 2,000 pictures of strangers.
            </p>

            <div className="hero-cta">
              <Link className="btn btn-primary btn-lg" href="/register">
                Get started <Icon.Arrow />
              </Link>
              <a className="btn btn-lg" href="#how">
                See how it works
              </a>
            </div>
          </div>
        </section>

        {/* Stats */}
        <section className="container" style={{ marginTop: -20 }}>
          <div className="stats">
            <div className="stats-label">
              One scan.
              <br />
              Every event.
            </div>
            <div className="stats-values">
              <div className="stat">
                <div className="stat-value">3</div>
                <div className="stat-label">Poses to enroll</div>
              </div>
              <div className="stat">
                <div className="stat-value">1</div>
                <div className="stat-label">Face profile</div>
              </div>
              <div className="stat">
                <div className="stat-value">20MB</div>
                <div className="stat-label">Per photo upload</div>
              </div>
              <div className="stat">
                <div className="stat-value">Live</div>
                <div className="stat-label">Match alerts</div>
              </div>
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="section">
          <div className="container">
            <div className="section-head center">
              <span className="eyebrow">How it works</span>
              <h2 className="h1">From the crowd to your camera roll</h2>
              <p className="muted">
                Three steps, and the photos come to you instead of the other way around.
              </p>
            </div>
            <div className="steps">
              {STEPS.map((s) => (
                <article className="step" key={s.n}>
                  <div className="step-visual">{s.icon}</div>
                  <div>
                    <div className="step-meta">
                      {s.meta.map((m) => (
                        <span key={m}>{m}</span>
                      ))}
                    </div>
                    <h3 className="step-title">{s.title}</h3>
                    <p className="muted">{s.body}</p>
                  </div>
                  <div className="step-num">{s.n}</div>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* For hosts */}
        <section id="features" className="section" style={{ paddingTop: 20 }}>
          <div className="container split">
            <div className="mosaic" aria-hidden>
              {TILES.map((t, i) => (
                <div key={i} className={`mosaic-tile ${t.cls}`} style={{ background: t.bg }}>
                  {t.tag && <span className="tag">{t.tag}</span>}
                </div>
              ))}
            </div>
            <div>
              <span className="eyebrow">For hosts &amp; photographers</span>
              <h2 className="h1" style={{ marginTop: 14 }}>
                Upload once. Everyone gets their own album.
              </h2>
              <ul className="check-list">
                <li>
                  <Icon.Check /> Create an event and share a single invite link.
                </li>
                <li>
                  <Icon.Check /> Approve or deny join requests — only guests see the photos.
                </li>
                <li>
                  <Icon.Check /> Drop in a batch of shots; matching runs in the background.
                </li>
                <li>
                  <Icon.Shield /> Close the event when you&apos;re done and the link stops working.
                </li>
              </ul>
              <Link className="btn btn-primary" href="/register">
                Host an event <Icon.Arrow />
              </Link>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="section" style={{ paddingTop: 20 }}>
          <div className="container">
            <div className="cta-band">
              <span className="eyebrow">Ready when you are</span>
              <h2 className="display">
                Stop searching.
                <br />
                <span className="accent-text">Start finding.</span>
              </h2>
              <div className="hero-cta">
                <Link className="btn btn-primary btn-lg" href="/register">
                  Create free account
                </Link>
                <Link className="btn btn-lg" href="/login">
                  I have an account
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="container spread">
          <Brand />
          <span>Face-based photo matching for events.</span>
        </div>
      </footer>
    </>
  );
}
