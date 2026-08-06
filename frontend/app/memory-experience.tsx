"use client";

import { useEffect, useRef, useState } from "react";

import type {
  MemoryEngineResult,
  MemoryPack,
  PlayerPerspective,
} from "@/lib/types";

type ReadyResult = MemoryEngineResult & {
  status: "ready";
  memory: NonNullable<MemoryEngineResult["memory"]>;
  next_chapter: NonNullable<MemoryEngineResult["next_chapter"]>;
};

type ViewState =
  | { kind: "unrevealed" }
  | { kind: "loading" }
  | { kind: "ready"; result: ReadyResult }
  | { kind: "unavailable" };

const avatarClasses = ["avatar-lime", "avatar-gold", "avatar-blue", "avatar-pink"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isUnitScore(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
}

function isRuleTarget(value: unknown) {
  return (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean" ||
    (Array.isArray(value) && value.every((item) => typeof item === "string"))
  );
}

function isOptedIn(member: MemoryPack["squad"]["members"][number]) {
  return member.opted_in !== false;
}

function formatWords(value?: string | null) {
  if (!value) return "Squadmate";
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatClock(seconds?: number | null) {
  if (seconds == null) return "Match event";
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function assertEngineSource(response: Response) {
  const source = response.headers.get("x-memoryos-mode");
  if (source === "live" || source === "sample") return;
  throw new Error("MemoryOS returned an unidentified response source.");
}

function parseMemoryResult(value: unknown, pack: MemoryPack): MemoryEngineResult {
  if (!isRecord(value)) throw new Error("MemoryOS returned an unreadable result.");

  const validStatuses = ["ready", "needs_human_confirmation", "rejected"];
  if (
    value.schema_version !== "1.0" ||
    value.pack_id !== pack.pack_id ||
    typeof value.status !== "string" ||
    !validStatuses.includes(value.status)
  ) {
    throw new Error("MemoryOS returned a result for the wrong match or contract version.");
  }

  const discovery = value.discovery;
  const validation = value.validation;
  const metadata = value.metadata;
  if (
    !isRecord(discovery) ||
    !isUnitScore(discovery.signal_score) ||
    !isUnitScore(discovery.threshold) ||
    typeof discovery.eligible !== "boolean" ||
    !Array.isArray(discovery.reasons) ||
    !discovery.reasons.every((reason) => typeof reason === "string") ||
    !isRecord(validation) ||
    typeof validation.passed !== "boolean" ||
    typeof validation.human_review_required !== "boolean" ||
    !isRecord(validation.scores) ||
    !isUnitScore(validation.scores.specificity) ||
    !isUnitScore(validation.scores.evidence_grounding) ||
    !isUnitScore(validation.scores.perspective_distinctness) ||
    !isUnitScore(validation.scores.quest_connection) ||
    !Array.isArray(validation.issues) ||
    !validation.issues.every(
      (issue) =>
        isRecord(issue) &&
        typeof issue.code === "string" &&
        ["info", "warning", "error"].includes(String(issue.severity)) &&
        typeof issue.message === "string",
    ) ||
    !isRecord(metadata) ||
    typeof metadata.pipeline_version !== "string" ||
    typeof metadata.provider !== "string" ||
    typeof metadata.model !== "string" ||
    typeof metadata.prose_renderer !== "string" ||
    !Array.isArray(value.player_perspectives)
  ) {
    throw new Error("MemoryOS returned an incomplete validation result.");
  }

  const eventIds = new Set(pack.match_events.map((event) => event.event_id));
  const optedInIds = new Set(pack.squad.members.filter(isOptedIn).map((member) => member.player_id));
  const perspectiveIds = new Set<string>();
  const perspectivesAreValid = value.player_perspectives.every((perspective) => {
    if (!isRecord(perspective)) return false;
    const canonicalMember = pack.squad.members.find((member) => member.player_id === perspective.player_id);
    if (
      typeof perspective.player_id !== "string" ||
      typeof perspective.display_name !== "string" ||
      perspective.display_name !== canonicalMember?.display_name ||
      typeof perspective.message !== "string" ||
      !Array.isArray(perspective.evidence_event_ids) ||
      !perspective.evidence_event_ids.every((eventId) => typeof eventId === "string" && eventIds.has(eventId)) ||
      !optedInIds.has(perspective.player_id) ||
      perspectiveIds.has(perspective.player_id)
    ) {
      return false;
    }
    perspectiveIds.add(perspective.player_id);
    return true;
  });
  if (!perspectivesAreValid) throw new Error("MemoryOS returned an ungrounded player perspective.");

  if (value.status === "ready" || value.status === "needs_human_confirmation") {
    const memory = value.memory;
    const quest = value.next_chapter;
    if (
      !isRecord(memory) ||
      typeof memory.title !== "string" ||
      typeof memory.summary !== "string" ||
      typeof memory.human_confirmed !== "boolean" ||
      !Array.isArray(memory.evidence) ||
      !memory.evidence.every(
        (evidence) =>
          isRecord(evidence) &&
          typeof evidence.event_id === "string" &&
          eventIds.has(evidence.event_id) &&
          typeof evidence.event_type === "string" &&
          typeof evidence.significance === "string",
      ) ||
      !isRecord(quest) ||
      typeof quest.title !== "string" ||
      typeof quest.mission !== "string" ||
      !["recreate", "remix", "resolve"].includes(String(quest.recipe)) ||
      !Array.isArray(quest.objectives) ||
      !quest.objectives.every(
        (objective) =>
          isRecord(objective) &&
          typeof objective.objective_id === "string" &&
          typeof objective.description === "string" &&
          typeof objective.required === "boolean" &&
          isRecord(objective.verification) &&
          typeof objective.verification.metric === "string" &&
          ["equals", "at_least", "contains_all"].includes(String(objective.verification.operator)) &&
          isRuleTarget(objective.verification.target) &&
          Array.isArray(objective.source_event_ids) &&
          objective.source_event_ids.every((eventId) => typeof eventId === "string" && eventIds.has(eventId)),
      ) ||
      !quest.objectives.some((objective) => isRecord(objective) && objective.required === true)
    ) {
      throw new Error("MemoryOS returned a story without grounded memory or challenge data.");
    }

    if (perspectiveIds.size !== optedInIds.size) {
      throw new Error("MemoryOS did not return one grounded perspective for every opted-in player.");
    }

    if (value.status === "ready" && (!validation.passed || validation.human_review_required)) {
      throw new Error("MemoryOS marked an unapproved memory as ready.");
    }
    if (value.status === "needs_human_confirmation" && (!validation.passed || !validation.human_review_required)) {
      throw new Error("MemoryOS returned an inconsistent review state.");
    }
  }

  return value as MemoryEngineResult;
}

function preferredPerspective(result: ReadyResult, pack: MemoryPack): PlayerPerspective | undefined {
  return result.player_perspectives.find(
    (perspective) => perspective.player_id === pack.player_profile.player_id,
  );
}

function challengeTitle(title: string) {
  return title.split(":").at(-1)?.trim() || title;
}

function MatchArtwork({ members }: { members: MemoryPack["squad"]["members"] }) {
  return (
    <div className="player-memory-art" aria-hidden="true">
      <picture className="player-artwork">
        <source media="(max-width: 650px)" srcSet="/art/heroes/free-fire-map-mobile-v2.webp" />
        {/* The map is a pre-optimized, decorative WebP. */}
        <img src="/art/heroes/free-fire-map-v2.webp" alt="" width="1440" height="520" fetchPriority="high" />
      </picture>
      <div className="player-route" />
      {members.slice(0, 4).map((member, index) => (
        <span className={`player-map-dot map-dot-${index + 1} ${avatarClasses[index]}`} key={member.player_id}>
          {member.display_name.slice(0, 1)}
        </span>
      ))}
    </div>
  );
}

export function MemoryExperience({ initialPack }: { initialPack: MemoryPack }) {
  const [view, setView] = useState<ViewState>({ kind: "unrevealed" });
  const [announcement, setAnnouncement] = useState("A squad memory is waiting to be loaded.");
  const requestSequence = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);
  const playButtonRef = useRef<HTMLButtonElement>(null);
  const challengeDialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    return () => {
      requestSequence.current += 1;
      activeRequest.current?.abort();
    };
  }, []);

  const storyResult = view.kind === "ready" ? view.result : null;
  const memory = storyResult?.memory;
  const quest = storyResult?.next_chapter;
  const optedInMembers = initialPack.squad.members.filter(isOptedIn);
  const perspective = storyResult ? preferredPerspective(storyResult, initialPack) : undefined;
  const currentPlayer = perspective
    ? optedInMembers.find((member) => member.player_id === perspective.player_id)
    : undefined;
  const requiredObjectives = quest?.objectives.filter((objective) => objective.required) ?? [];
  const eventMap = new Map(initialPack.match_events.map((event) => [event.event_id, event]));
  const chronologicalEvidence = memory
    ? [...memory.evidence].sort((left, right) => {
        const leftTime = eventMap.get(left.event_id)?.timestamp_seconds ?? Number.MAX_SAFE_INTEGER;
        const rightTime = eventMap.get(right.event_id)?.timestamp_seconds ?? Number.MAX_SAFE_INTEGER;
        return leftTime - rightTime;
      })
    : [];
  const canPlay =
    view.kind === "ready" &&
    view.result.validation.passed &&
    !view.result.validation.human_review_required;
  const statusLabel =
    view.kind === "unrevealed"
      ? "Memory waiting"
      : view.kind === "loading"
        ? "Opening memory"
        : view.kind === "ready"
          ? "Memory ready"
          : "Not available";

  function showChallenge() {
    if (!canPlay) return;
    setAnnouncement("Challenge preview ready. No real invitation was sent.");
    challengeDialogRef.current?.showModal();
  }

  function closeChallenge() {
    challengeDialogRef.current?.close();
  }

  function resetReveal() {
    requestSequence.current += 1;
    activeRequest.current?.abort();
    activeRequest.current = null;
    if (challengeDialogRef.current?.open) challengeDialogRef.current.close();
    setView({ kind: "unrevealed" });
    setAnnouncement("The squad memory is ready to load again.");
  }

  async function revealMemory() {
    if (view.kind === "loading") return;

    const requestId = ++requestSequence.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    const minimumDelay = new Promise<void>((resolve) => window.setTimeout(resolve, 850));
    activeRequest.current = controller;
    if (challengeDialogRef.current?.open) challengeDialogRef.current.close();
    setView({ kind: "loading" });
    setAnnouncement("Opening your squad memory.");

    try {
      const response = await fetch("/api/discover", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(initialPack),
        signal: controller.signal,
      });
      const responseText = await response.text();
      let payload: unknown;
      try {
        payload = JSON.parse(responseText) as unknown;
      } catch {
        throw new Error("MemoryOS returned an unreadable response.");
      }

      if (!response.ok) throw new Error("MemoryOS could not read this match.");
      assertEngineSource(response);
      const result = parseMemoryResult(payload, initialPack);
      await minimumDelay;
      if (controller.signal.aborted || requestId !== requestSequence.current) return;

      if (result.status === "ready") {
        setView({ kind: "ready", result: result as ReadyResult });
        setAnnouncement(`${result.memory?.title ?? "Memory"} is ready.`);
      } else {
        setView({ kind: "unavailable" });
        setAnnouncement(
          result.status === "needs_human_confirmation"
            ? "This memory still needs player confirmation."
            : "This match was safely skipped.",
        );
      }
    } catch {
      if (controller.signal.aborted || requestId !== requestSequence.current) return;
      await minimumDelay;
      if (controller.signal.aborted || requestId !== requestSequence.current) return;
      setView({ kind: "unavailable" });
      setAnnouncement("Memory discovery failed. You can retry safely.");
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }

  return (
    <main className="player-app" data-theme="light" data-game="free-fire">
      <a className="skip-link" href="#player-story">Skip to your story</a>
      <p className="sr-only" aria-live="polite">{announcement}</p>

      <div className="player-mode-heading">Battle Royale</div>

      <div className="player-shell">
        <header className="player-topbar">
          <a className="player-brand" href="#player-story" aria-label="MemoryOS player home">
            <span className="player-brand-mark">M</span>
            <span>MemoryOS</span>
          </a>
          <span className={`engine-badge ${view.kind === "loading" ? "checking" : ""}`}>
            <i aria-hidden="true" />
            {statusLabel}
          </span>
        </header>

        <div className="player-page" id="player-story" aria-busy={view.kind === "loading"}>
          {view.kind === "unrevealed" ? (
            <section className="demo-input-card" aria-labelledby="demo-input-title">
              <MatchArtwork members={optedInMembers} />
              <div className="demo-input-copy">
                <p className="demo-kicker">Memory not loaded</p>
                <h1 id="demo-input-title">A squad memory is waiting.</h1>
                <p className="demo-match-context">
                  Free Fire <span>·</span> {formatWords(initialPack.match.mode)} <span>·</span> {initialPack.match.map_name ?? "Bermuda"}
                </p>
                <p className="reveal-teaser">Your original squad left a story behind. Open it when you are ready.</p>
                <div className="reveal-squad">
                  <div className="player-avatar-stack" aria-label={`${optedInMembers.length} squad members`}>
                    {optedInMembers.slice(0, 4).map((member, index) => (
                      <span className={`player-mini-avatar ${avatarClasses[index]}`} key={member.player_id} aria-hidden="true">
                        {member.display_name.slice(0, 1)}
                      </span>
                    ))}
                  </div>
                  <span><strong>The original squad</strong><small>{initialPack.squad.matches_together} matches together</small></span>
                </div>
                <button className="reveal-memory-button" type="button" onClick={() => void revealMemory()}>
                  Load this memory
                </button>
              </div>
            </section>
          ) : view.kind === "loading" ? (
            <section className="demo-processing-card" aria-labelledby="demo-processing-title" role="status">
              <div className="demo-processing-mark" aria-hidden="true">M</div>
              <p className="demo-kicker">Loading squad memory</p>
              <h1 id="demo-processing-title">Pulling the night back together.</h1>
              <p className="reveal-loading-copy">Loading the shared memory, your side of the story, and what comes next.</p>
              <div className="reveal-loading-lines" aria-hidden="true"><span /><span /><span /></div>
            </section>
          ) : storyResult && memory && quest ? (
            <>
              <section className="player-hero" aria-labelledby="player-memory-title">
                <MatchArtwork members={optedInMembers} />

                <div className="player-memory-copy">
                  <div className="memory-gist-label">The gist</div>
                  <div className="player-context-strip">
                    <strong>Free Fire</strong>
                    <span>{formatWords(initialPack.match.mode)}</span>
                    <span>{initialPack.match.map_name ?? "Bermuda"}</span>
                  </div>
                  <h1 id="player-memory-title">{memory.title}</h1>
                  <p>{memory.summary}</p>
                  <div className="player-squad-row">
                    <div className="player-avatar-stack" aria-label={`${optedInMembers.length} players joined`}>
                      {optedInMembers.slice(0, 4).map((member, index) => (
                        <span
                          className={`player-mini-avatar ${avatarClasses[index]}`}
                          key={member.player_id}
                          aria-hidden="true"
                        >
                          {member.display_name.slice(0, 1)}
                        </span>
                      ))}
                    </div>
                    <span>
                      <strong>{optedInMembers.length} players joined</strong>
                      <small>{initialPack.squad.squad_id.replaceAll("-", " ")}</small>
                    </span>
                  </div>
                </div>
              </section>

              <details className="player-evidence">
                <summary>
                  <span>What actually happened</span>
                  <small>{chronologicalEvidence.length} verified moments</small>
                </summary>
                <div className="player-evidence-list">
                  <p className="player-evidence-intro">The match moments behind the shared memory, in the order they happened.</p>
                  {chronologicalEvidence.map((evidence, index) => {
                    const event = eventMap.get(evidence.event_id);
                    return (
                      <article key={evidence.event_id}>
                        <span aria-hidden="true">{index + 1}</span>
                        <div>
                          <strong>{evidence.significance}</strong>
                          <small>{event ? `${event.location ?? "Match"} · ${formatClock(event.timestamp_seconds)}` : "Match moment"}</small>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </details>

              {perspective && currentPlayer && (
                <details className="player-section your-perspective-card" open>
                  <summary id="your-perspective-title">
                    <span>Your side of the story</span>
                    <small>{currentPlayer.display_name} · {formatWords(currentPlayer.role)}</small>
                  </summary>
                  <div className="your-perspective-body">
                    <span className="your-avatar avatar-lime" aria-hidden="true">{currentPlayer.display_name.slice(0, 1)}</span>
                    <div>
                      <p className="your-identity">
                        <strong>{currentPlayer.display_name}</strong>
                        <span>{formatWords(currentPlayer.role)}</span>
                      </p>
                      <p className="your-message">{perspective.message}</p>
                    </div>
                  </div>
                </details>
              )}

              <section className="player-section player-next" aria-labelledby="next-chapter-title">
                <div className="next-chapter-label">Next Chapter</div>
                <h2 id="next-chapter-title">{challengeTitle(quest.title)}</h2>
                <p className="player-next-mission">{quest.mission}</p>
                <ol className="player-objectives">
                  {requiredObjectives.map((objective, index) => (
                    <li key={objective.objective_id}>
                      <span>{index + 1}</span>
                      <p>{objective.description}</p>
                    </li>
                  ))}
                </ol>
                {/* The landmark is a pre-optimized, decorative WebP. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  className="chapter-landmark"
                  src="/art/landmarks/clock-tower-town-v2.webp"
                  alt=""
                  width="760"
                  height="448"
                  loading="lazy"
                  aria-hidden="true"
                />
              </section>

              <button
                ref={playButtonRef}
                className="play-challenge"
                type="button"
                onClick={showChallenge}
                disabled={!canPlay}
              >
                <span aria-hidden="true">▶</span>
                Play this challenge
              </button>
            </>
          ) : (
            <section className="player-state-card" role="alert">
              <span>Memory unavailable</span>
              <h1>This memory is not ready to reveal.</h1>
              <p>It may still need review, or there may not be enough approved context to share it yet.</p>
              <button type="button" onClick={() => void revealMemory()}>Try again</button>
            </section>
          )}

          <footer className="player-footer">
            <span>MemoryOS</span>
            <p>Your squad decides what is worth remembering.</p>
            {(view.kind === "ready" || view.kind === "unavailable") && (
              <button type="button" onClick={resetReveal}>View from the start</button>
            )}
          </footer>
        </div>
      </div>

      {storyResult && quest && (
        <dialog
          ref={challengeDialogRef}
          className="challenge-dialog"
          aria-labelledby="challenge-dialog-title"
          aria-describedby="challenge-dialog-description"
          onClose={() => playButtonRef.current?.focus()}
        >
          <button className="dialog-close" type="button" onClick={closeChallenge} aria-label="Close challenge preview">×</button>
          <p className="dialog-kicker">Demo simulation</p>
          <h2 id="challenge-dialog-title">{challengeTitle(quest.title)}</h2>
          <p id="challenge-dialog-description">This challenge is ready for the opted-in squad. No real invitation has been sent.</p>
          <div className="dialog-squad" aria-label="Opted-in squad members">
            {optedInMembers.map((member, index) => (
              <span
                className={avatarClasses[index % avatarClasses.length]}
                key={member.player_id}
                role="img"
                aria-label={member.display_name}
                title={member.display_name}
              >
                {member.display_name.slice(0, 1)}
              </span>
            ))}
          </div>
          <button className="dialog-done" type="button" onClick={closeChallenge}>Done</button>
        </dialog>
      )}
    </main>
  );
}
