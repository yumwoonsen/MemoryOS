"use client";

import { useMemo, useReducer, useRef, useState } from "react";
import Link from "next/link";

import { mayGenerate, selectCandidate, updateReview, type HistoryState } from "@/lib/history-flow";
import type {
  HistoricalDiscoveryResponse,
  MemoryPackV11,
  ReadyMemoryResult,
} from "@/lib/history-types";

const avatarClasses = ["avatar-lime", "avatar-gold", "avatar-blue", "avatar-pink"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isDiscovery(value: unknown): value is HistoricalDiscoveryResponse {
  return isRecord(value)
    && value.schema_version === "1.1"
    && Array.isArray(value.candidates)
    && value.candidates.every((candidate) => isRecord(candidate)
      && typeof candidate.pack_id === "string"
      && typeof candidate.title === "string"
      && typeof candidate.summary === "string"
      && Array.isArray(candidate.reasons)
      && Array.isArray(candidate.redactions))
    && isRecord(value.filters);
}

function isReady(value: unknown): value is ReadyMemoryResult {
  return isRecord(value)
    && value.schema_version === "1.1"
    && value.status === "ready"
    && isRecord(value.memory)
    && typeof value.memory.title === "string"
    && typeof value.memory.summary === "string"
    && Array.isArray(value.memory.evidence)
    && Array.isArray(value.player_perspectives)
    && isRecord(value.next_chapter)
    && typeof value.next_chapter.title === "string"
    && Array.isArray(value.next_chapter.objectives)
    && isRecord(value.validation)
    && value.validation.passed === true;
}

function formatWords(value?: string | null) {
  return value ? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) : "Squad memory";
}

function formatDate(value?: string | null) {
  if (!value) return "Earlier this season";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Earlier this season" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function eventLabel(type: string) {
  return formatWords(type);
}

function reducer(_state: HistoryState, next: HistoryState): HistoryState {
  return next;
}

export function HistoryExperience({ initialPacks }: { initialPacks: MemoryPackV11[] }) {
  const [state, dispatch] = useReducer(reducer, { kind: "history_idle" });
  const [announcement, setAnnouncement] = useState("MemoryOS can review your squad history when you are ready.");
  const abortRef = useRef<AbortController | null>(null);
  const packs = useMemo(() => new Map(initialPacks.map((pack) => [pack.pack_id, pack])), [initialPacks]);

  async function discoverHistory() {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    dispatch({ kind: "history_loading" });
    setAnnouncement("Reviewing the evidence-backed moments in your squad history.");
    try {
      const response = await fetch("/api/history", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ schema_version: "1.1", memory_packs: initialPacks, limit: 3 }),
        signal: controller.signal,
      });
      const payload: unknown = await response.json();
      if (!response.ok || !isDiscovery(payload)) throw new Error("We could not safely review this squad history.");
      dispatch({ kind: "candidates_ready", discovery: payload });
      setAnnouncement(`${payload.candidates.length} squad memories are ready for your review.`);
    } catch (error) {
      if (controller.signal.aborted) return;
      dispatch({ kind: "history_error", message: error instanceof Error ? error.message : "We could not safely review this squad history." });
      setAnnouncement("Squad history could not be loaded safely.");
    }
  }

  function choose(packId: string) {
    if (state.kind !== "candidates_ready") return;
    const candidate = state.discovery.candidates.find((item) => item.pack_id === packId);
    if (!candidate) return;
    const next = selectCandidate(candidate, packs);
    dispatch(next);
    setAnnouncement(next.kind === "source_review" ? "Review the match events before continuing." : "The selected match could not be loaded safely.");
  }

  function verifySource(verified: boolean) {
    if (state.kind !== "source_review") return;
    const pack = updateReview(state.pack, { source_status: verified ? "verified" : "disputed" });
    dispatch(verified
      ? { kind: "meaning_review", candidate: state.candidate, pack }
      : { kind: "source_disputed" });
    setAnnouncement(verified ? "Source verified. You can now decide whether this memory matters." : "This memory was disputed and will not be generated.");
  }

  async function reviewMeaning(confirmed: boolean) {
    if (!mayGenerate(state)) return;
    const pack = updateReview(state.pack, { meaning_status: confirmed ? "confirmed" : "dismissed" });
    if (!confirmed) {
      dispatch({ kind: "meaning_dismissed" });
      setAnnouncement("This memory was dismissed and will not be generated.");
      return;
    }
    await generateMemory(state.candidate, pack);
  }

  async function generateMemory(candidate: Extract<HistoryState, { kind: "meaning_review" }>["candidate"] | Extract<HistoryState, { kind: "generation_error" }>["candidate"], pack: MemoryPackV11) {
    dispatch({ kind: "generation_loading", candidate, pack });
    setAnnouncement("Building your verified squad memory.");
    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ schema_version: "1.1", memory_pack: pack }),
      });
      const payload: unknown = await response.json();
      if (isReady(payload) && response.ok) {
        dispatch({ kind: "ready", result: payload, pack });
        setAnnouncement(`${payload.memory.title} is ready.`);
      } else if (isRecord(payload) && payload.status === "rejected") {
        dispatch({ kind: "rejected", message: "This memory could not be safely generated." });
        setAnnouncement("This memory was safely skipped.");
      } else {
        throw new Error("MemoryOS did not return a ready, validated memory.");
      }
    } catch (error) {
      dispatch({ kind: "generation_error", candidate, pack, message: error instanceof Error ? error.message : "Memory generation failed safely." });
      setAnnouncement("Memory generation could not be completed safely.");
    }
  }

  function restart() {
    abortRef.current?.abort();
    dispatch({ kind: "history_idle" });
    setAnnouncement("You can review your squad history again.");
  }

  const status = state.kind === "history_loading" || state.kind === "generation_loading" ? "Reviewing" : state.kind === "ready" ? "Memory ready" : "Review required";

  return (
    <main className="player-app history-app" data-theme="light" data-game="free-fire">
      <a className="skip-link" href="#squad-history">Skip to squad history</a>
      <p className="sr-only" aria-live="polite">{announcement}</p>
      <div className="player-mode-heading">Battle Royale</div>
      <div className="player-shell">
        <header className="player-topbar">
          <Link className="player-brand" href="/" aria-label="MemoryOS player home"><span className="player-brand-mark">M</span><span>MemoryOS</span></Link>
          <span className={`engine-badge ${status === "Reviewing" ? "checking" : ""}`}><i aria-hidden="true" />{status}</span>
        </header>
        <div className="player-page" id="squad-history" aria-busy={status === "Reviewing"}>
          {state.kind === "history_idle" && (
            <section className="history-intro" aria-labelledby="history-title">
              <p className="demo-kicker">Your squad history</p>
              <h1 id="history-title">A few moments may be worth another look.</h1>
              <p>MemoryOS uses match evidence and squad context to surface moments for you to review. It does not decide what matters to you.</p>
              <button className="reveal-memory-button" type="button" onClick={() => void discoverHistory()}>Review squad memories</button>
            </section>
          )}
          {state.kind === "history_loading" && <section className="demo-processing-card" role="status"><div className="demo-processing-mark" aria-hidden="true">M</div><p className="demo-kicker">Reviewing squad history</p><h1>Finding evidence-backed moments.</h1><p className="reveal-loading-copy">Looking for the few matches your squad may want to revisit.</p></section>}
          {state.kind === "history_error" && <StateCard title="Squad history is unavailable" message={state.message} action="Try again" onAction={() => void discoverHistory()} />}
          {state.kind === "candidates_ready" && (
            <section className="history-candidates" aria-labelledby="candidate-title">
              <p className="demo-kicker">Your squad history</p><h1 id="candidate-title">Here are the moments that surfaced.</h1>
              <p className="history-note">These are reviewable match moments, not judgments about your feelings.</p>
              {state.discovery.candidates.map((candidate) => {
                const pack = packs.get(candidate.pack_id);
                return <article className="history-candidate" key={candidate.pack_id}>
                  <div className="candidate-topline"><span>#{candidate.rank}</span><small>{formatWords(candidate.memory_type)} · {formatDate(pack?.match.played_at)}</small><strong>Strong signal</strong></div>
                  <h2>{candidate.title}</h2><p>{candidate.summary}</p>
                  <ul>{candidate.reasons.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}</ul>
                  {(candidate.redactions?.length ?? 0) > 0 && <p className="redaction-notice">Some squad identities are hidden because they opted out.</p>}
                  <div className="review-badges"><span>Facts: {candidate.source_status}</span><span>Meaning: {candidate.meaning_status}</span></div>
                  <button type="button" onClick={() => choose(candidate.pack_id)}>Review this moment</button>
                </article>;
              })}
            </section>
          )}
          {state.kind === "source_review" && <ReviewEvidence candidateTitle={state.candidate.title} pack={state.pack} onVerify={() => verifySource(true)} onDispute={() => verifySource(false)} />}
          {state.kind === "meaning_review" && <section className="history-intro" aria-labelledby="meaning-title"><p className="demo-kicker">Step 2 of 2 · your meaning</p><h1 id="meaning-title">Is this a memory worth keeping or continuing?</h1><p>You have verified the match events. Only you can decide whether this shared moment matters to your squad.</p><div className="review-actions"><button className="reveal-memory-button" type="button" onClick={() => void reviewMeaning(true)}>Keep this memory</button><button className="secondary-action" type="button" onClick={() => void reviewMeaning(false)}>Dismiss this moment</button></div></section>}
          {state.kind === "generation_loading" && <section className="demo-processing-card" role="status"><div className="demo-processing-mark" aria-hidden="true">M</div><p className="demo-kicker">Verified chapter</p><h1>Turning the match into your next chapter.</h1><p className="reveal-loading-copy">The evidence remains the source of truth.</p></section>}
          {state.kind === "source_disputed" && <StateCard title="Thanks for checking." message="This match will not become a memory or reunion prompt." action="Back to squad history" onAction={restart} />}
          {state.kind === "meaning_dismissed" && <StateCard title="This moment stays in the past." message="It will not be generated as a memory or reunion prompt." action="Back to squad history" onAction={restart} />}
          {state.kind === "generation_error" && <StateCard title="Memory generation is unavailable" message={state.message} action="Try again" onAction={() => void generateMemory(state.candidate, state.pack)} />}
          {state.kind === "rejected" && <StateCard title="This moment was safely skipped" message={state.message} action="Back to squad history" onAction={restart} />}
          {state.kind === "ready" && <ReadyStory result={state.result} pack={state.pack} />}
          <footer className="player-footer"><span>MemoryOS</span><p>Your squad decides what is worth remembering.</p>{state.kind !== "history_idle" && <button type="button" onClick={restart}>View from the start</button>}</footer>
        </div>
      </div>
    </main>
  );
}

function ReviewEvidence({ candidateTitle, pack, onVerify, onDispute }: { candidateTitle: string; pack: MemoryPackV11; onVerify: () => void; onDispute: () => void }) {
  return <section className="history-review" aria-labelledby="source-title"><p className="demo-kicker">Step 1 of 2 · source check</p><h1 id="source-title">Did this gameplay event happen as described?</h1><p>{candidateTitle}</p><ol className="review-timeline">{[...(pack.match_events ?? [])].sort((a, b) => (a.timestamp_seconds ?? 0) - (b.timestamp_seconds ?? 0)).map((event) => <li key={event.event_id}><strong>{eventLabel(event.type)}</strong><small>{event.location ?? "Match"} · {event.timestamp_seconds ?? 0}s</small></li>)}</ol><div className="review-actions"><button className="reveal-memory-button" type="button" onClick={onVerify}>Yes, these events happened</button><button className="secondary-action" type="button" onClick={onDispute}>No, dispute this source</button></div></section>;
}

function StateCard({ title, message, action, onAction }: { title: string; message: string; action: string; onAction: () => void }) {
  return <section className="player-state-card" role="alert"><span>Memory review</span><h1>{title}</h1><p>{message}</p><button type="button" onClick={onAction}>{action}</button></section>;
}

function ReadyStory({ result, pack }: { result: ReadyMemoryResult; pack: MemoryPackV11 }) {
  const eventMap = new Map((pack.match_events ?? []).map((event) => [event.event_id, event]));
  const optedIn = pack.squad.members.filter((member) => member.opted_in);
  const perspective = (result.player_perspectives ?? []).find((item) => item.player_id === pack.player_profile.player_id);
  return <><section className="player-hero" aria-labelledby="player-memory-title"><div className="player-memory-copy"><div className="memory-gist-label">The gist</div><div className="player-context-strip"><strong>Free Fire</strong><span>{formatWords(pack.match.mode)}</span><span>{pack.match.map_name ?? "Bermuda"}</span></div><h1 id="player-memory-title">{result.memory.title}</h1><p>{result.memory.summary}</p><div className="player-squad-row"><div className="player-avatar-stack" aria-label={`${optedIn.length} players joined`}>{optedIn.map((member, index) => <span className={`player-mini-avatar ${avatarClasses[index % avatarClasses.length]}`} key={member.player_id} aria-hidden="true">{member.display_name.slice(0, 1)}</span>)}</div><span><strong>{optedIn.length} players joined</strong><small>Verified squad memory</small></span></div></div></section><details className="player-evidence" open><summary><span>What actually happened</span><small>{result.memory.evidence.length} verified moments</small></summary><div className="player-evidence-list">{result.memory.evidence.map((evidence, index) => { const event = eventMap.get(evidence.event_id); return <article key={evidence.event_id}><span>{index + 1}</span><div><strong>{evidence.significance}</strong><small>{event ? `${event.location ?? "Match"} · ${event.timestamp_seconds ?? 0}s` : "Match moment"}</small></div></article>; })}</div></details>{perspective && <section className="player-section your-perspective-card"><h2>Your side of the story</h2><p className="your-message">{perspective.message}</p></section>}<section className="player-section player-next"><div className="next-chapter-label">Next Chapter</div><h2>{result.next_chapter.title}</h2><p className="player-next-mission">{result.next_chapter.mission}</p><ol className="player-objectives">{result.next_chapter.objectives.filter((item) => item.required).map((objective, index) => <li key={objective.objective_id}><span>{index + 1}</span><p>{objective.description}</p></li>)}</ol></section></>;
}
