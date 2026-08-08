"use client";

import Link from "next/link";

type PlayerRoute = "memory" | "mission" | "history";

export function PlayerShell({
  active,
  status,
  announcement,
  busy = false,
  modeLabel,
  modeHeading,
  children,
}: {
  active: PlayerRoute;
  status: string;
  announcement: string;
  busy?: boolean;
  modeLabel?: string;
  modeHeading?: string;
  children: React.ReactNode;
}) {
  const needsAttention = /unavailable|paused|not saved|no active/i.test(status);
  return (
    <main className={`player-app player-route-${active}`} data-theme="light" data-game="free-fire">
      <a className="skip-link" href="#player-content">Skip to content</a>
      <p className="sr-only" aria-live="polite">{announcement}</p>

      {modeHeading ? <div className="player-mode-heading">{modeHeading}</div> : null}

      <div className="player-shell">
        <header className="player-topbar">
          <Link className="player-brand" href="/" aria-label="MemoryOS player home">
            <span className="player-brand-mark">M</span>
            <span>MemoryOS</span>
          </Link>
          <div className="player-topbar-actions">
            <span className={`engine-badge ${busy ? "checking" : ""} ${needsAttention ? "attention" : ""}`}>
              <i aria-hidden="true" />
              {status}
            </span>
            {modeLabel ? <span className="header-mode-badge">{modeLabel}</span> : null}
          </div>
        </header>

        <nav className="consumer-nav" aria-label="Player sections">
          <Link href="/" aria-current={active === "memory" ? "page" : undefined}>Memory</Link>
          <Link href="/mission" aria-current={active === "mission" ? "page" : undefined}>Mission</Link>
          <Link href="/history" aria-current={active === "history" ? "page" : undefined}>History</Link>
        </nav>

        <div className="player-page" id="player-content" aria-busy={busy}>
          {children}

          <footer className="player-footer">
            <span>MemoryOS</span>
            <p>Your squad decides what is worth remembering.</p>
            <Link className="footer-studio-link" href="/studio">Developer Studio</Link>
          </footer>
        </div>
      </div>
    </main>
  );
}
