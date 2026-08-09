"use client";

import Link from "next/link";

import { PlayerShell } from "../player-shell";
import { usePlayerFlow } from "../player-flow-provider";
import { challengeTitle } from "@/lib/delivery-flow";
import type { SafeHistoryItem } from "@/lib/history-timeline";

function formatWords(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "Asia/Singapore",
  }).format(new Date(value));
}

export function HistoryExperience({ items }: { items: SafeHistoryItem[] }) {
  const { flow } = usePlayerFlow();
  const visibleContinuation = flow.continuation?.feedback !== "hidden"
    ? flow.continuation
    : null;
  const pastItems = items;
  const status = flow.continuation
    ? (visibleContinuation ? "Story continued" : "Chapter hidden")
    : flow.missionAccepted
      ? "Mission in progress"
      : "Squad history";
  const announcement = flow.continuation
    ? (visibleContinuation
        ? "The latest completed chapter is in your squad history."
        : "The completed chapter is hidden without disputing the original memory.")
    : "Squad history shows privacy-safe retained memories only.";

  return (
    <PlayerShell active="history" status={status} announcement={announcement}>
      <section className="history-archive-heading" aria-labelledby="history-title">
        <p className="demo-kicker">Squad history</p>
        <h1 id="history-title">The stories your squad kept.</h1>
        <p>A compact archive of verified past matches and completed Next Chapters—without reopening the current decision flow.</p>
      </section>

      {flow.missionAccepted && flow.delivery ? (
        <section className="history-session-card" id="latest" aria-labelledby="latest-title">
          <div className="history-section-heading">
            <div>
              <p className="demo-kicker">{flow.continuation ? "This prototype session" : "Active journey"}</p>
              <h2 id="latest-title">{visibleContinuation
                ? "Latest chapter"
                : flow.continuation?.feedback === "hidden"
                  ? "Chapter hidden"
                  : "Mission in progress"}</h2>
            </div>
            <span className="history-session-badge">Session only</span>
          </div>

          <ol className="memory-timeline history-route-timeline">
            <li>
              <span>1</span>
              <div><small>Original memory</small><strong>{flow.delivery.memory.title}</strong></div>
            </li>
            <li>
              <span>2</span>
              <div><small>Accepted mission</small><strong>{challengeTitle(flow.delivery.next_chapter.title)}</strong></div>
            </li>
            {visibleContinuation ? (
              <li>
                <span>3</span>
                <div><small>New chapter</small><strong>{visibleContinuation.chapter.title}</strong></div>
              </li>
            ) : null}
          </ol>

          {flow.continuation?.feedback === "hidden" ? (
            <p className="history-session-note">The completed sequel is hidden from this timeline. The original memory was not disputed.</p>
          ) : visibleContinuation ? (
            <p className="history-session-note">{visibleContinuation.outcome.objective_results.filter((objective) => objective.completed).length} of {visibleContinuation.outcome.objective_results.length} prototype objectives completed in the scripted match simulation.</p>
          ) : (
            <Link className="reveal-memory-button history-home-action" href="/mission">Continue mission</Link>
          )}
        </section>
      ) : null}

      <section className="past-memory-section" aria-labelledby="past-memory-title">
        <div className="history-section-heading">
          <div>
            <p className="demo-kicker">Retained memories</p>
            <h2 id="past-memory-title">Past squad matches</h2>
          </div>
          <span>{pastItems.length}</span>
        </div>
        {pastItems.length > 0 ? (
          <div className="past-memory-list">
            {pastItems.map((item, index) => (
              <details className="past-memory-item" key={`${item.played_at}-${item.map_name}-${index}`}>
                <summary>
                  <span className="past-memory-icon" aria-hidden="true">M</span>
                  <span className="past-memory-heading">
                    <small>{item.game} / {formatDate(item.played_at)}</small>
                    <strong>{item.map_name} squad match</strong>
                  </span>
                  <span className="past-memory-state">Match details<i aria-hidden="true" /></span>
                </summary>
                <div className="past-match-details">
                  <dl>
                    <div><dt>Mode</dt><dd>{formatWords(item.mode)}</dd></div>
                    <div><dt>Placement</dt><dd>{item.placement != null ? `#${item.placement}` : "Not recorded"}</dd></div>
                    <div><dt>Consent-safe moments</dt><dd>{item.consent_safe_moments}</dd></div>
                    <div><dt>Opted-in players</dt><dd>{item.opted_in_count}</dd></div>
                  </dl>
                  <p>Privacy-safe summary only. Player identities, captions, and raw event data stay hidden.</p>
                </div>
              </details>
            ))}
          </div>
        ) : (
          <div className="history-empty-state history-empty-compact">
            <h3>No retained matches yet.</h3>
            <p>Verified, confirmed squad matches will appear here without private captions or opted-out identities.</p>
          </div>
        )}
        <p className="prototype-boundary">Only retained, consent-safe, deduplicated matches are listed. Raw captions and opted-out identities are excluded.</p>
      </section>
    </PlayerShell>
  );
}
