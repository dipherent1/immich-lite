import type { Metadata } from "next";
import Link from "next/link";

import { Brand, Icon } from "@/components/ui";

export const metadata: Metadata = {
  title: "Immich Lite — like Google Photos, but worse",
  description:
    "Everyone uploads, faces get matched, you get your photos. Then everything self-destructs after 6 hours. Like Google Photos, but worse.",
};

const STEPS = [
  {
    n: "01",
    icon: <Icon.Face size={44} />,
    meta: ["~20 seconds", "3 poses"],
    title: "Scan your face once",
    body: "Front, left, right. Yes, we're judging your angles. We keep a private face profile (a bunch of numbers, not your selfies) and you never do this again.",
  },
  {
    n: "02",
    icon: <Icon.Ticket size={44} />,
    meta: ["One link", "Zero codes"],
    title: "Open the invite link",
    body: "That's the whole join flow. If the host is picky, you can also ask to get in and hope for the best.",
  },
  {
    n: "03",
    icon: <Icon.Images size={44} />,
    meta: ["Live alerts", "Only your face"],
    title: "Receive your photos",
    body: "Someone uploads 400 pictures. Our robots find the ones with you in them and hand them over. The other 396 are not your problem.",
  },
];

type Win = "them" | "us" | "tie";

const COMPARE: { what: string; them: string; us: string; win: Win }[] = [
  {
    what: "How long your photos live",
    them: "Forever (or until the storage bill)",
    us: "6 hours. We have commitment issues.",
    win: "them",
  },
  {
    what: "Finds the photos you're in",
    them: "Yes, quietly",
    us: "Yes, annoyingly well",
    win: "tie",
  },
  {
    what: "Photos from someone else's event",
    them: "A shared album and a prayer",
    us: "One link. No prayer needed.",
    win: "us",
  },
  {
    what: "Videos",
    them: "Of course",
    us: "No. They're heavy and we're cheap.",
    win: "them",
  },
  {
    what: "Polish",
    them: "Billions of dollars of it",
    us: "A dark theme and good intentions",
    win: "them",
  },
  {
    what: "Your data after the party",
    them: "Lives on, indefinitely",
    us: "Deleted. Actually deleted.",
    win: "us",
  },
];

const QUIPS = [
  "“Found me in the background of a stranger's photo. Impressive. Concerning.”",
  "“Deleted my event after exactly 6 hours. Respect.”",
  "“It's like Google Photos,” said the founder, repeatedly.",
];

const FINE_PRINT = [
  {
    q: "Why does everything vanish after 6 hours?",
    a: "Storage costs money and our bank account has feelings. Download your photos before the timer hits zero. We'll nag you 20 minutes before, and the event page counts down so you can't claim surprise.",
  },
  {
    q: "Where are the videos?",
    a: "Not here. Photos only (JPG, PNG, HEIC and friends, up to 20 MB each). Videos are enormous, and so is the invoice.",
  },
  {
    q: "Do I really need an account?",
    a: "To get your photos, yes. We need to know which face is yours. One scan, once, then you're done.",
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
            <a className="nav-link" href="#compare">Vs. Google Photos</a>
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
                <span className="dot" /> 12 photos found (3 blurry)
              </span>
              <span className="match-pill p2">
                <Icon.Face size={14} /> Face judged. Profile ready.
              </span>
            </div>

            <h1 className="display hero-title snark">
              <span className="snark-small">It&apos;s like</span>
              <span className="accent-text">Google Photos</span>
              <span className="outline">but worse.</span>
            </h1>

            <p className="hero-sub">
              Everyone uploads. Faces get matched. You get the photos you&apos;re in.
              Then everything self-destructs after 6 hours, because storage isn&apos;t
              free and neither is our rent.
            </p>

            <div className="hero-cta">
              <Link className="btn btn-primary btn-lg" href="/register">
                Lower your expectations <Icon.Arrow />
              </Link>
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="section">
          <div className="container">
            <div className="section-head center">
              <span className="eyebrow">How it works</span>
              <h2 className="h1">Three steps. We kept it short on purpose.</h2>
              <p className="muted">
                The photos come to you, instead of you scrolling through 2,000 pictures of
                strangers&apos; brunch.
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

        {/* Vs Google Photos */}
        <section id="compare" className="section" style={{ paddingTop: 20 }}>
          <div className="container">
            <div className="section-head center">
              <span className="eyebrow">The honest comparison</span>
              <h2 className="h1">Google Photos vs. us</h2>
              <p className="muted">
                We did the math. Google Photos wins more rows. We win the ones that matter
                to people at parties.
              </p>
            </div>

            <table className="compare">
              <thead>
                <tr>
                  <th scope="col" />
                  <th scope="col">Google Photos</th>
                  <th scope="col" className="us">
                    Immich Lite
                  </th>
                </tr>
              </thead>
              <tbody>
                {COMPARE.map((row) => (
                  <tr key={row.what}>
                    <th scope="row">{row.what}</th>
                    <td data-label="Google Photos" className={row.win === "them" || row.win === "tie" ? "win" : "lose"}>
                      {row.win === "us" ? <Icon.X size={16} /> : <Icon.Check size={16} />}
                      <span>{row.them}</span>
                    </td>
                    <td data-label="Immich Lite" className={`us ${row.win === "us" || row.win === "tie" ? "win" : "lose"}`}>
                      {row.win === "them" ? <Icon.X size={16} /> : <Icon.Check size={16} />}
                      <span>{row.us}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="quips" aria-label="Reviews we wrote ourselves">
              <span className="quips-label">Reviews (we wrote them)</span>
              {QUIPS.map((q) => (
                <p className="quip" key={q}>
                  {q}
                </p>
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
                  <Icon.Check /> Create an event, get one link, drop it in the group chat. Ignore the
                  &quot;who&apos;s in this one?&quot; replies.
                </li>
                <li>
                  <Icon.Check /> Throw in up to 100 photos at a time. Matching happens in the
                  background while you do literally anything else.
                </li>
                <li>
                  <Icon.Check /> Approve or deny join requests. Yes, you may say no to Karen.
                </li>
                <li>
                  <Icon.Download /> Grab everything as a zip. The event is deleted 6 hours after it
                  starts, and we are not sorry.
                </li>
              </ul>
              <Link className="btn btn-primary" href="/register">
                Host an event <Icon.Arrow />
              </Link>
            </div>
          </div>
        </section>

        {/* Fine print */}
        <section className="section" style={{ paddingTop: 20 }}>
          <div className="container">
            <div className="section-head center">
              <span className="eyebrow">The fine print</span>
              <h2 className="h1">Questions you were about to ask</h2>
            </div>
            <div className="fineprint">
              {FINE_PRINT.map((f) => (
                <article className="fineprint-card" key={f.q}>
                  <h3>{f.q}</h3>
                  <p className="muted">{f.a}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="section" style={{ paddingTop: 20 }}>
          <div className="container">
            <div className="cta-band">
              <span className="eyebrow">Last chance to leave</span>
              <h2 className="display">
                Lower your
                <br />
                <span className="accent-text">expectations.</span>
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
          <span>Face-based photo matching for events. Not affiliated with Google. Obviously.</span>
        </div>
      </footer>
    </>
  );
}
