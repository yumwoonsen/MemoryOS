"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import type {
  DeliveryDeclineReason,
  MemoryDeliveryResult,
  MemoryPackV11,
  RecordDeliveryDecisionResponse,
} from "@/lib/history-types";
import {
  buildInvitees,
  createContinuationChapter,
  createSyntheticRematch,
  verifyMission,
} from "@/lib/reunion-flow";
import type {
  ContinuationChapter,
  Invitee,
  MissionVerification,
} from "@/lib/reunion-flow";

type PendingDelivery = MemoryDeliveryResult & {
  delivery_id: string;
  status: "pending_player_decision";
  source_status: "verified";
  meaning_status: "unreviewed";
  memory: NonNullable<MemoryDeliveryResult["memory"]>;
  player_perspectives: NonNullable<MemoryDeliveryResult["player_perspectives"]>;
  next_chapter: NonNullable<MemoryDeliveryResult["next_chapter"]>;
  narrative: NonNullable<MemoryDeliveryResult["narrative"]>;
};

type DecisionRequest =
  | { decision: "accepted" }
  | { decision: "declined"; decline_reason: DeliveryDeclineReason };

type ChapterFeedback = "worth_remembering" | "not_for_me";

type View =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "inbox"; delivery: PendingDelivery }
  | { kind: "decline"; delivery: PendingDelivery }
  | { kind: "sending"; delivery: PendingDelivery; request: DecisionRequest }
  | { kind: "mission_ready"; delivery: PendingDelivery }
  | { kind: "invitation"; delivery: PendingDelivery; readyIds: string[] }
  | { kind: "verifying"; delivery: PendingDelivery }
  | {
      kind: "continuation";
      delivery: PendingDelivery;
      verification: MissionVerification;
      chapter: ContinuationChapter;
      feedback: ChapterFeedback | null;
    }
  | { kind: "declined"; reason: DeliveryDeclineReason };

const avatarClasses = ["avatar-lime", "avatar-gold", "avatar-blue", "avatar-pink"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isRuleTarget(value: unknown) {
  return (
    typeof value === "string"
    || typeof value === "number"
    || typeof value === "boolean"
    || (Array.isArray(value) && value.every((item) => typeof item === "string"))
  );
}

function isPendingDelivery(value: unknown): value is PendingDelivery {
  if (
    !isRecord(value)
    || value.schema_version !== "1.1"
    || value.status !== "pending_player_decision"
    || value.source_status !== "verified"
    || value.meaning_status !== "unreviewed"
    || typeof value.delivery_id !== "string"
    || typeof value.pack_id !== "string"
    || !isRecord(value.memory)
    || typeof value.memory.title !== "string"
    || typeof value.memory.summary !== "string"
    || !Array.isArray(value.memory.evidence)
    || value.memory.evidence.length === 0
    || !value.memory.evidence.every(
      (evidence) => isRecord(evidence)
        && typeof evidence.event_id === "string"
        && typeof evidence.significance === "string",
    )
    || !Array.isArray(value.player_perspectives)
    || value.player_perspectives.length < 2
    || !value.player_perspectives.every(
      (perspective) => isRecord(perspective)
        && typeof perspective.player_id === "string"
        && typeof perspective.display_name === "string"
        && typeof perspective.message === "string",
    )
    || !isRecord(value.next_chapter)
    || typeof value.next_chapter.title !== "string"
    || typeof value.next_chapter.mission !== "string"
    || !Array.isArray(value.next_chapter.objectives)
    || !value.next_chapter.objectives.every(
      (objective) => isRecord(objective)
        && typeof objective.objective_id === "string"
        && typeof objective.description === "string"
        && typeof objective.required === "boolean"
        && isRecord(objective.verification)
        && typeof objective.verification.metric === "string"
        && ["equals", "at_least", "contains_all"].includes(String(objective.verification.operator))
        && isRuleTarget(objective.verification.target),
    )
    || !isRecord(value.narrative)
    || typeof value.narrative.teaser !== "string"
    || typeof value.narrative.why_this_surfaced !== "string"
    || !isRecord(value.validation)
    || value.validation.passed !== true
  ) {
    return false;
  }

  const perspectiveIds = value.player_perspectives.map((perspective) => perspective.player_id);
  return perspectiveIds.length === new Set(perspectiveIds).size;
}

function isDecisionConfirmation(
  value: unknown,
  deliveryId: string,
  request: DecisionRequest,
): value is RecordDeliveryDecisionResponse {
  if (
    !isRecord(value)
    || value.delivery_id !== deliveryId
    || value.decision !== request.decision
  ) {
    return false;
  }
  if (request.decision === "accepted") {
    return value.decline_reason == null;
  }
  return value.decline_reason === request.decline_reason;
}

function challengeTitle(title: string) {
  return title.split(":").at(-1)?.trim() || title;
}

export function HistoryExperience({ initialPacks }: { initialPacks: MemoryPackV11[] }) {
  const [view, setView] = useState<View>({ kind: "loading" });
  const [announcement, setAnnouncement] = useState("Preparing one squad memory.");

  const prepare = useCallback(async () => {
    setView({ kind: "loading" });
    setAnnouncement("Preparing one squad memory.");
    try {
      const response = await fetch("/api/delivery/prepare", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ schema_version: "1.1", memory_packs: initialPacks }),
      });
      const payload: unknown = await response.json();
      if (!response.ok || !isPendingDelivery(payload)) {
        throw new Error("Your squad memory is not available right now.");
      }
      setView({ kind: "inbox", delivery: payload });
      setAnnouncement(`${payload.memory.title} is ready for your decision.`);
    } catch (error) {
      setView({
        kind: "error",
        message: error instanceof Error
          ? error.message
          : "Your squad memory is not available right now.",
      });
      setAnnouncement("The squad memory could not be prepared.");
    }
  }, [initialPacks]);

  useEffect(() => {
    const timer = window.setTimeout(() => void prepare(), 0);
    return () => window.clearTimeout(timer);
  }, [prepare]);

  const activeDelivery = "delivery" in view ? view.delivery : null;
  const sourcePack = activeDelivery
    ? initialPacks.find((pack) => pack.pack_id === activeDelivery.pack_id)
    : undefined;
  const invitees = activeDelivery
    ? buildInvitees(activeDelivery.player_perspectives, sourcePack?.player_profile.player_id)
    : [];
  const isBusy = view.kind === "loading" || view.kind === "sending" || view.kind === "verifying";
  const statusLabel =
    view.kind === "mission_ready"
      ? "Mission ready"
      : view.kind === "invitation"
        ? "Squad invite"
        : view.kind === "verifying"
          ? "Checking match"
          : view.kind === "continuation"
            ? "Story continues"
            : view.kind === "declined"
              ? "Complete"
              : "Memory inbox";

  async function decide(request: DecisionRequest) {
    if (view.kind !== "inbox" && view.kind !== "decline") return;
    const delivery = view.delivery;
    setView({ kind: "sending", delivery, request });
    setAnnouncement("Saving your decision.");
    try {
      const response = await fetch("/api/delivery/decision", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ delivery_id: delivery.delivery_id, ...request }),
      });
      const payload: unknown = await response.json();
      if (!response.ok || !isDecisionConfirmation(payload, delivery.delivery_id, request)) {
        throw new Error("Your choice could not be saved safely.");
      }
      if (request.decision === "accepted") {
        setView({ kind: "mission_ready", delivery });
        setAnnouncement("Mission accepted. The squad-safe invitation is ready.");
      } else {
        setView({ kind: "declined", reason: request.decline_reason });
        setAnnouncement("The mission was dismissed and your feedback was recorded.");
      }
    } catch (error) {
      setView({
        kind: "error",
        message: error instanceof Error ? error.message : "Your choice could not be saved safely.",
      });
      setAnnouncement("Your decision could not be saved.");
    }
  }

  function beginInvitation(delivery: PendingDelivery) {
    const safeInvitees = buildInvitees(
      delivery.player_perspectives,
      initialPacks.find((pack) => pack.pack_id === delivery.pack_id)?.player_profile.player_id,
    );
    if (safeInvitees.length < 2) {
      setView({ kind: "error", message: "There are not enough opted-in squad members to continue." });
      return;
    }
    const currentPlayer = safeInvitees.find((invitee) => invitee.is_current_player) ?? safeInvitees[0];
    setView({ kind: "invitation", delivery, readyIds: [currentPlayer.player_id] });
    setAnnouncement("Invitations sent to the opted-in squad only.");
  }

  function acceptInvitations() {
    if (view.kind !== "invitation") return;
    setView({ ...view, readyIds: invitees.map((invitee) => invitee.player_id) });
    setAnnouncement("The opted-in squad is ready for the rematch.");
  }

  async function simulateMatch() {
    if (view.kind !== "invitation") return;
    const delivery = view.delivery;
    setView({ kind: "verifying", delivery });
    setAnnouncement("Checking the synthetic rematch against the mission rules.");
    await new Promise<void>((resolve) => window.setTimeout(resolve, 700));
    const matchResult = createSyntheticRematch(invitees);
    const verification = verifyMission(delivery.next_chapter.objectives, matchResult);
    const chapter = createContinuationChapter(delivery.memory, delivery.next_chapter, verification);
    if (!chapter) {
      setView({ kind: "error", message: "The rematch did not complete every required mission objective." });
      setAnnouncement("The mission is still in progress.");
      return;
    }
    setView({ kind: "continuation", delivery, verification, chapter, feedback: null });
    setAnnouncement("All required objectives were verified. The story continues.");
  }

  function recordChapterFeedback(feedback: ChapterFeedback) {
    if (view.kind !== "continuation") return;
    setView({ ...view, feedback });
    setAnnouncement(
      feedback === "worth_remembering"
        ? "Chapter saved as worth remembering for this prototype session."
        : "Chapter dismissed for this prototype session without disputing match facts.",
    );
  }

  return (
    <main className="player-app history-app" data-theme="light" data-game="free-fire">
      <a className="skip-link" href="#memory-inbox">Skip to your memory</a>
      <p className="sr-only" aria-live="polite">{announcement}</p>
      <div className="player-mode-heading">Battle Royale</div>

      <div className="player-shell">
        <header className="player-topbar">
          <Link className="player-brand" href="/" aria-label="MemoryOS player home">
            <span className="player-brand-mark">M</span>
            <span>MemoryOS</span>
          </Link>
          <div className="player-topbar-actions">
            <span className={`engine-badge ${isBusy ? "checking" : ""}`}>
              <i aria-hidden="true" />
              {statusLabel}
            </span>
            <Link className="player-studio-link" href="/studio" aria-label="Open the MemoryOS Developer Studio">
              <span className="player-studio-long">Developer </span>Studio
            </Link>
          </div>
        </header>

        <div className="player-page" id="memory-inbox" aria-busy={isBusy}>
          <Link className="history-back-link" href="/">← Back to player memory</Link>

          {view.kind === "loading" && (
            <ProcessingCard
              kicker="Memory inbox"
              title="Bringing a squad moment back."
              message="Preparing one grounded memory and a new chapter for your squad."
            />
          )}
          {view.kind === "error" && (
            <StateCard title="Your memory is unavailable" message={view.message} onRetry={() => void prepare()} />
          )}
          {view.kind === "inbox" && (
            <MemoryCard
              delivery={view.delivery}
              targetPlayerId={sourcePack?.player_profile.player_id}
              onAccept={() => void decide({ decision: "accepted" })}
              onDecline={() => setView({ kind: "decline", delivery: view.delivery })}
            />
          )}
          {view.kind === "decline" && (
            <DeclineCard
              onKeep={() => setView({ kind: "inbox", delivery: view.delivery })}
              onReason={(declineReason) => void decide({ decision: "declined", decline_reason: declineReason })}
            />
          )}
          {view.kind === "sending" && (
            <ProcessingCard
              kicker="Saving your choice"
              title={view.request.decision === "accepted"
                ? "Opening the reunion path."
                : "Closing this mission respectfully."}
              message="MemoryOS is confirming one clear player decision."
            />
          )}
          {view.kind === "mission_ready" && (
            <MissionReadyCard
              delivery={view.delivery}
              invitees={invitees}
              onContinue={() => beginInvitation(view.delivery)}
            />
          )}
          {view.kind === "invitation" && (
            <InvitationCard
              delivery={view.delivery}
              invitees={invitees}
              readyIds={view.readyIds}
              onAccept={acceptInvitations}
              onSimulate={() => void simulateMatch()}
            />
          )}
          {view.kind === "verifying" && (
            <ProcessingCard
              kicker="Deterministic mission check"
              title="Reading the new match result."
              message="The synthetic telemetry is being checked against every required mission rule."
            />
          )}
          {view.kind === "continuation" && (
            <ContinuationCard
              delivery={view.delivery}
              verification={view.verification}
              chapter={view.chapter}
              feedback={view.feedback}
              onFeedback={recordChapterFeedback}
            />
          )}
          {view.kind === "declined" && <DeclinedCard reason={view.reason} />}

          <footer className="player-footer">
            <span>MemoryOS</span>
            <p>Your squad’s history, made personal.</p>
          </footer>
        </div>
      </div>
    </main>
  );
}

function ProcessingCard({ kicker, title, message }: { kicker: string; title: string; message: string }) {
  return (
    <section className="demo-processing-card" role="status">
      <div className="demo-processing-mark" aria-hidden="true">M</div>
      <p className="demo-kicker">{kicker}</p>
      <h1>{title}</h1>
      <p className="reveal-loading-copy">{message}</p>
    </section>
  );
}

function MemoryCard({
  delivery,
  targetPlayerId,
  onAccept,
  onDecline,
}: {
  delivery: PendingDelivery;
  targetPlayerId?: string;
  onAccept: () => void;
  onDecline: () => void;
}) {
  const perspective = delivery.player_perspectives.find(
    (candidate) => candidate.player_id === targetPlayerId,
  );
  const clipMoment = delivery.memory.evidence[0];

  return (
    <>
      <section className="history-moment-clip" aria-label="Curated synthetic moment preview">
        <div className="history-clip-art" aria-hidden="true"><span>▶</span></div>
        <div>
          <p className="demo-kicker">Curated moment preview</p>
          <strong>{clipMoment.significance}</strong>
          <small>Synthetic clip · grounded by a verified event</small>
        </div>
      </section>

      <section className="player-hero" aria-labelledby="memory-title">
        <div className="player-memory-copy">
          <p className="demo-kicker">A memory from your squad</p>
          <div className="memory-gist-label">{delivery.narrative.teaser}</div>
          <h1 id="memory-title">{delivery.memory.title}</h1>
          <p>{delivery.memory.summary}</p>
          <p className="history-note">Why this resurfaced: {delivery.narrative.why_this_surfaced}</p>
        </div>
      </section>

      {perspective && (
        <section className="player-section your-perspective-card history-perspective">
          <h2>Your side of the story</h2>
          <p className="your-message">{perspective.message}</p>
        </section>
      )}

      <section className="player-section player-next">
        <div className="next-chapter-label">Reunion mission</div>
        <h2>{challengeTitle(delivery.next_chapter.title)}</h2>
        <p className="player-next-mission">{delivery.next_chapter.mission}</p>
      </section>

      <div className="review-actions history-decision-actions">
        <button className="reveal-memory-button" type="button" onClick={onAccept}>Accept mission</button>
        <button className="secondary-action" type="button" onClick={onDecline}>Decline</button>
      </div>
    </>
  );
}

function DeclineCard({
  onKeep,
  onReason,
}: {
  onKeep: () => void;
  onReason: (reason: DeliveryDeclineReason) => void;
}) {
  return (
    <section className="history-intro history-choice-card" aria-labelledby="decline-title">
      <p className="demo-kicker">Decline mission</p>
      <h1 id="decline-title">What should MemoryOS learn?</h1>
      <p>Choose one reason. The mission will be suppressed, and your trusted match history will not be edited.</p>
      <div className="review-actions history-choice-actions">
        <button className="secondary-action" type="button" onClick={() => onReason("not_relevant")}>
          Not relevant to me
        </button>
        <button className="secondary-action" type="button" onClick={() => onReason("details_wrong")}>
          Details are wrong
        </button>
      </div>
      <button className="history-text-action" type="button" onClick={onKeep}>Keep this mission</button>
    </section>
  );
}

function MissionReadyCard({
  delivery,
  invitees,
  onContinue,
}: {
  delivery: PendingDelivery;
  invitees: Invitee[];
  onContinue: () => void;
}) {
  const requiredObjectives = delivery.next_chapter.objectives.filter((objective) => objective.required);
  return (
    <section className="history-intro mission-start-card" aria-labelledby="mission-title">
      <p className="demo-kicker">Mission ready</p>
      <h1 id="mission-title">{challengeTitle(delivery.next_chapter.title)}</h1>
      <p>{delivery.next_chapter.mission}</p>
      <ObjectiveList objectives={requiredObjectives} />
      <div className="safe-squad-block">
        <span className="next-chapter-label">Opted-in squad only</span>
        <InviteeList invitees={invitees} />
        <p>Only these players can enter the invitation simulation.</p>
      </div>
      <button className="reveal-memory-button" type="button" onClick={onContinue}>
        Continue to squad invite
      </button>
    </section>
  );
}

function InvitationCard({
  delivery,
  invitees,
  readyIds,
  onAccept,
  onSimulate,
}: {
  delivery: PendingDelivery;
  invitees: Invitee[];
  readyIds: string[];
  onAccept: () => void;
  onSimulate: () => void;
}) {
  const allReady = invitees.length > 0 && invitees.every((invitee) => readyIds.includes(invitee.player_id));
  return (
    <section className="history-intro invitation-card" aria-labelledby="invitation-title">
      <p className="demo-kicker">Invitation simulation</p>
      <h1 id="invitation-title">Bring the squad back.</h1>
      <p>{challengeTitle(delivery.next_chapter.title)} is ready for the players who opted in.</p>
      <InviteeList invitees={invitees} readyIds={readyIds} />
      <div className="squad-ready-count" aria-live="polite">
        <strong>{readyIds.length}/{invitees.length}</strong>
        <span>squad ready</span>
      </div>
      {allReady ? (
        <button className="reveal-memory-button" type="button" onClick={onSimulate}>
          Simulate next match
        </button>
      ) : (
        <button className="reveal-memory-button" type="button" onClick={onAccept}>
          Simulate squad accepting
        </button>
      )}
      <p className="prototype-boundary">Prototype only — no real invitation or notification is sent.</p>
    </section>
  );
}

function ContinuationCard({
  delivery,
  verification,
  chapter,
  feedback,
  onFeedback,
}: {
  delivery: PendingDelivery;
  verification: MissionVerification;
  chapter: ContinuationChapter;
  feedback: ChapterFeedback | null;
  onFeedback: (feedback: ChapterFeedback) => void;
}) {
  return (
    <>
      <section className="story-continues-card" aria-labelledby="story-continues-title">
        <p className="demo-kicker">Story Continues</p>
        <h1 id="story-continues-title">{chapter.title}</h1>
        <p>{chapter.summary}</p>
        <div className="verification-summary">
          <strong>{verification.required_passed}/{verification.required_total}</strong>
          <span>required objectives verified</span>
        </div>
        <ul className="verification-list">
          {verification.objective_results.filter((objective) => objective.required).map((objective) => (
            <li className={objective.passed ? "passed" : "failed"} key={objective.objective_id}>
              <span aria-hidden="true">{objective.passed ? "✓" : "×"}</span>
              <p>{objective.description}</p>
            </li>
          ))}
        </ul>
        <p className="prototype-boundary">Verified against a labelled synthetic new-match result.</p>
      </section>

      <section className="memory-timeline-card" aria-labelledby="timeline-title">
        <p className="demo-kicker">Memory timeline</p>
        <h2 id="timeline-title">One memory, one reunion, one sequel.</h2>
        <ol className="memory-timeline">
          <li><span>1</span><div><small>Original memory</small><strong>{delivery.memory.title}</strong></div></li>
          <li><span>2</span><div><small>Reunion mission</small><strong>{challengeTitle(delivery.next_chapter.title)} accepted</strong></div></li>
          <li><span>3</span><div><small>Story Continues</small><strong>{verification.label} verified</strong></div></li>
        </ol>
      </section>

      <section className="chapter-feedback-card" aria-labelledby="feedback-title">
        <p className="demo-kicker">Optional chapter feedback</p>
        <h2 id="feedback-title">Was this sequel worth keeping?</h2>
        {feedback ? (
          <p className="feedback-complete" role="status">
            {feedback === "worth_remembering"
              ? "Saved as worth remembering for this prototype session."
              : "Marked not for me for this prototype session. This does not dispute the verified match result."}
          </p>
        ) : (
          <div className="review-actions">
            <button className="reveal-memory-button" type="button" onClick={() => onFeedback("worth_remembering")}>
              Worth remembering
            </button>
            <button className="secondary-action" type="button" onClick={() => onFeedback("not_for_me")}>
              Not for me
            </button>
          </div>
        )}
        <p className="prototype-boundary">Chapter feedback is separate from “Details are wrong,” which remains a source-quality signal.</p>
      </section>
    </>
  );
}

function DeclinedCard({ reason }: { reason: DeliveryDeclineReason }) {
  const detailsWrong = reason === "details_wrong";
  return (
    <section className="history-intro history-completion" aria-labelledby="declined-title">
      <p className="demo-kicker">Decision complete</p>
      <h1 id="declined-title">{detailsWrong ? "Thanks for flagging the source." : "Thanks for letting us know."}</h1>
      <p>
        {detailsWrong
          ? "The mission has been suppressed and a source-quality signal was recorded for operations review. Your match history was not edited."
          : "The mission has been dismissed. This relevance feedback will help MemoryOS choose a better moment next time."}
      </p>
      <Link className="reveal-memory-button history-home-action" href="/">Back to player memory</Link>
    </section>
  );
}

function ObjectiveList({ objectives }: { objectives: PendingDelivery["next_chapter"]["objectives"] }) {
  return (
    <ol className="mission-objective-list">
      {objectives.map((objective, index) => (
        <li key={objective.objective_id}><span>{index + 1}</span><p>{objective.description}</p></li>
      ))}
    </ol>
  );
}

function InviteeList({
  invitees,
  readyIds,
}: {
  invitees: Invitee[];
  readyIds?: string[];
}) {
  return (
    <ul className="invitee-list">
      {invitees.map((invitee, index) => {
        const ready = readyIds?.includes(invitee.player_id);
        return (
          <li key={invitee.player_id}>
            <span className={`invitee-avatar ${avatarClasses[index % avatarClasses.length]}`} aria-hidden="true">
              {invitee.display_name.slice(0, 1)}
            </span>
            <div><strong>{invitee.display_name}</strong><small>{invitee.is_current_player ? "You" : "Opted in"}</small></div>
            <span className={`invitee-status ${ready ? "ready" : ""}`}>
              {readyIds ? (ready ? "Ready" : "Invited") : "Eligible"}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function StateCard({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry: () => void;
}) {
  return (
    <section className="player-state-card" role="alert">
      <span>Memory inbox</span>
      <h1>{title}</h1>
      <p>{message}</p>
      <button type="button" onClick={onRetry}>Try again</button>
    </section>
  );
}
