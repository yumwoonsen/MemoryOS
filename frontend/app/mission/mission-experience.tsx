"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { PlayerShell } from "../player-shell";
import { usePlayerFlow } from "../player-flow-provider";
import { challengeTitle, deliveryModeLabel } from "@/lib/delivery-flow";
import type { PendingDelivery } from "@/lib/delivery-flow";
import {
  areInviteesJoined,
  buildInvitees,
  createContinuationChapter,
  createPrototypeMatchOutcome,
} from "@/lib/reunion-flow";
import type {
  ContinuationChapter,
  InvitationResponse,
  Invitee,
  PrototypeMatchOutcome,
} from "@/lib/reunion-flow";

const avatarClasses = ["avatar-lime", "avatar-gold", "avatar-blue", "avatar-pink"];

function formatWords(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function MissionExperience() {
  const {
    flow,
    acceptAllInvitees,
    completeMission,
    openInvitation,
    setChapterFeedback,
    startPrototypeMatch,
  } = usePlayerFlow();
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("Next Chapter mission screen ready.");
  const simulationSequence = useRef(0);
  const delivery = flow.missionAccepted ? flow.delivery : null;
  const invitees = useMemo(
    () => delivery ? buildInvitees(delivery.invitation_roster) : [],
    [delivery],
  );

  useEffect(() => () => {
    simulationSequence.current += 1;
  }, []);

  if (!delivery) {
    return (
      <PlayerShell
        active="mission"
        status="No active mission"
        announcement="No accepted mission is available in this prototype session."
        modeHeading="Battle Royale"
      >
        <section className="player-state-card mission-empty-state" role="status">
          <span>No active mission</span>
          <h1>Accept a Next Chapter mission first.</h1>
          <p>Open your current memory and accept its Next Chapter. This prototype keeps the handoff only in the current app session.</p>
          <Link className="reveal-memory-button history-home-action" href="/">View current memory</Link>
        </section>
      </PlayerShell>
    );
  }

  const session = flow.invitationSession;
  const continuation = flow.continuation;
  const busy = session?.state === "match_started" && !continuation;
  const status = continuation
    ? "Story continued"
    : error
      ? "Mission paused"
      : session?.state === "sent" || session?.state === "lobby_ready"
        ? "Squad invitation"
        : busy
          ? "Prototype game"
          : "Active mission";

  function beginInvitation() {
    if (invitees.length < 2) {
      setError("There are not enough invitation-eligible squad members to continue.");
      return;
    }
    if (!invitees.some((invitee) => invitee.is_current_player)) {
      setError("The current player is not eligible for this mission lobby.");
      return;
    }
    setError(null);
    openInvitation();
    setAnnouncement("Invitations were sent. You joined first while your squad responses are pending.");
  }

  function simulateAcceptances() {
    if (session?.state !== "sent") return;
    acceptAllInvitees();
    setAnnouncement("Every invitation-eligible squad member accepted and joined the lobby.");
  }

  async function simulatePrototypeMatch() {
    if (session?.state !== "lobby_ready" || !delivery) return;
    const selectedDelivery = delivery;
    if (!areInviteesJoined(invitees, session.recipients)) {
      setError("Every invited squad member must join before the game can start.");
      return;
    }
    const simulationId = ++simulationSequence.current;
    setError(null);
    startPrototypeMatch();
    setAnnouncement("Prototype match simulation started.");
    await new Promise<void>((resolve) => window.setTimeout(resolve, 900));
    if (simulationId !== simulationSequence.current) return;

    const outcome = createPrototypeMatchOutcome(
      selectedDelivery.next_chapter.family,
      invitees,
      selectedDelivery.next_chapter.objectives,
    );
    const chapter = createContinuationChapter(selectedDelivery.memory, selectedDelivery.next_chapter, outcome);
    if (!chapter) {
      setError("The prototype completion state could not be created.");
      return;
    }
    completeMission(outcome, chapter);
    setAnnouncement(`${outcome.completion_copy} The story continues.`);
  }

  function hideChapter() {
    setChapterFeedback("hidden");
    setAnnouncement("This chapter is hidden from the session timeline without disputing the original match facts.");
  }

  return (
    <PlayerShell
      active="mission"
      status={status}
      announcement={announcement}
      busy={busy}
      modeLabel={deliveryModeLabel(delivery)}
      modeHeading="Battle Royale"
    >
      {continuation ? (
        <ContinuationCard
          outcome={continuation.outcome}
          chapter={continuation.chapter}
          acceptedMissionTitle={challengeTitle(delivery.next_chapter.title)}
          feedback={continuation.feedback}
          onHide={hideChapter}
        />
      ) : error ? (
        <section className="player-state-card" role="alert">
          <span>Mission paused</span>
          <h1>The mission could not continue.</h1>
          <p>{error}</p>
          <button type="button" onClick={() => setError(null)}>Return to mission</button>
        </section>
      ) : !session ? (
        <MissionReadyCard delivery={delivery} invitees={invitees} onContinue={beginInvitation} />
      ) : session.state === "sent" || session.state === "lobby_ready" ? (
        <InvitationCard
          delivery={delivery}
          invitees={invitees}
          recipients={session.recipients}
          onAccept={simulateAcceptances}
          onStart={() => void simulatePrototypeMatch()}
        />
      ) : session.state === "match_started" ? (
        <ProcessingCard family={delivery.next_chapter.family} />
      ) : null}
    </PlayerShell>
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
  const awayCount = invitees.filter((invitee) => invitee.activity === "away").length;
  return (
    <section className="history-intro mission-start-card" aria-labelledby="mission-title">
      <p className="demo-kicker">Active mission / {formatWords(delivery.next_chapter.family)}</p>
      <h1 id="mission-title">{challengeTitle(delivery.next_chapter.title)}</h1>
      <p className="mission-source-memory">From “{delivery.memory.title}”</p>
      <p>{delivery.next_chapter.mission}</p>
      <ObjectiveList objectives={requiredObjectives} />
      <div className="safe-squad-block">
        <span className="next-chapter-label">Invitation-eligible squad</span>
        <div className="player-squad-row mission-eligible-summary">
          <div className="player-avatar-stack" aria-label={`${invitees.length} invitation-eligible players`}>
            {invitees.slice(0, 4).map((invitee, index) => (
              <span className={`player-mini-avatar ${avatarClasses[index % avatarClasses.length]}`} key={invitee.recipient_ref} aria-hidden="true">
                {invitee.display_name.slice(0, 1)}
              </span>
            ))}
          </div>
          <span>
            <strong>{invitees.length} players can be invited</strong>
            <small>{awayCount ? `${awayCount} away player${awayCount === 1 ? "" : "s"} can still rejoin` : "Everyone is currently online"}</small>
          </span>
        </div>
      </div>
      <button className="reveal-memory-button" type="button" onClick={onContinue}>Send squad invite</button>
      <p className="prototype-boundary">Prototype only — no real invitation or notification is sent.</p>
    </section>
  );
}

function InvitationCard({
  delivery,
  invitees,
  recipients,
  onAccept,
  onStart,
}: {
  delivery: PendingDelivery;
  invitees: Invitee[];
  recipients: InvitationResponse[];
  onAccept: () => void;
  onStart: () => void;
}) {
  const allJoined = areInviteesJoined(invitees, recipients);
  const joinedCount = recipients.filter((recipient) => recipient.response !== "pending").length;
  const waitingNames = invitees
    .filter((invitee) => recipients.find((recipient) => recipient.recipient_ref === invitee.recipient_ref)?.response === "pending")
    .map((invitee) => invitee.display_name);
  return (
    <section className="history-intro invitation-card" aria-labelledby="invitation-title">
      <p className="demo-kicker">Squad invite</p>
      <h1 id="invitation-title">Bring the squad back.</h1>
      <p>{challengeTitle(delivery.next_chapter.title)} is ready for every player who allowed mission invitations.</p>
      <InviteeList invitees={invitees} recipients={recipients} />
      <div className="squad-ready-count" aria-live="polite">
        <strong>{joinedCount}/{invitees.length}</strong>
        <span>in lobby</span>
      </div>
      {allJoined ? (
        <button className="reveal-memory-button" type="button" onClick={onStart}>Start game</button>
      ) : (
        <button className="reveal-memory-button" type="button" onClick={onAccept}>
          {waitingNames.length === 1 ? `Simulate ${waitingNames[0]} accepting` : "Simulate squad accepting"}
        </button>
      )}
      <p className="prototype-boundary">Prototype only — invitation responses and lobby joining are simulated.</p>
    </section>
  );
}

function ContinuationCard({
  outcome,
  chapter,
  acceptedMissionTitle,
  feedback,
  onHide,
}: {
  outcome: PrototypeMatchOutcome;
  chapter: ContinuationChapter;
  acceptedMissionTitle: string;
  feedback: "hidden" | null;
  onHide: () => void;
}) {
  const completedObjectives = outcome.objective_results.filter((objective) => objective.completed);
  return (
    <>
      <section className="story-continues-card" aria-labelledby="story-continues-title">
        <p className="demo-kicker">Story continued / {formatWords(outcome.family)}</p>
        <h1 id="story-continues-title">{chapter.title}</h1>
        <p>{chapter.summary}</p>
        <ol className="chapter-relationship" aria-label="How the memory became a new chapter">
          <li><small>Original memory</small><strong>{chapter.original_memory_title}</strong></li>
          <li><small>Accepted mission</small><strong>{acceptedMissionTitle}</strong></li>
          <li><small>New chapter</small><strong>{chapter.title}</strong></li>
        </ol>
        <div className="verification-summary">
          <strong>{completedObjectives.length}/{outcome.objective_results.length}</strong>
          <span>prototype objectives completed</span>
        </div>
        <ul className="verification-list">
          {outcome.objective_results.map((objective) => (
            <li className={objective.completed ? "passed" : undefined} key={objective.objective_ref}>
              <span aria-hidden="true">{objective.completed ? "✓" : "–"}</span>
              <p>{objective.description}</p>
            </li>
          ))}
        </ul>
        <p className="prototype-boundary">Prototype match simulation — this successful outcome is scripted and does not claim real or live match telemetry.</p>
      </section>

      <section className="chapter-feedback-card" aria-labelledby="chapter-action-title">
        <p className="demo-kicker">Chapter complete</p>
        <h2 id="chapter-action-title">What should happen to this sequel?</h2>
        {feedback === "hidden" ? (
          <>
            <p className="feedback-complete" role="status">Hidden from this session timeline. This does not dispute the original memory facts.</p>
            <Link className="secondary-action history-home-action" href="/history#latest">View squad history</Link>
          </>
        ) : (
          <div className="review-actions">
            <Link className="reveal-memory-button history-home-action" href="/history#latest">View squad history</Link>
            <button className="secondary-action" type="button" onClick={onHide}>Hide this chapter</button>
          </div>
        )}
        <p className="prototype-boundary">Hiding a chapter is optional feedback. “Details are wrong” remains a separate source-quality signal on the memory screen.</p>
      </section>
    </>
  );
}

function ProcessingCard({ family }: { family: PendingDelivery["next_chapter"]["family"] }) {
  return (
    <section className="demo-processing-card" role="status">
      <div className="demo-processing-mark" aria-hidden="true">M</div>
      <p className="demo-kicker">Prototype match simulation / {formatWords(family)}</p>
      <h1>Game in progress.</h1>
      <p className="reveal-loading-copy">The squad is playing the selected Next Chapter. This demonstration will move to its scripted successful completion state.</p>
    </section>
  );
}

function ObjectiveList({ objectives }: { objectives: PendingDelivery["next_chapter"]["objectives"] }) {
  return (
    <ol className="mission-objective-list">
      {objectives.map((objective, index) => (
        <li key={objective.objective_ref}><span>{index + 1}</span><p>{objective.description}</p></li>
      ))}
    </ol>
  );
}

function InviteeList({
  invitees,
  recipients,
}: {
  invitees: Invitee[];
  recipients: InvitationResponse[];
}) {
  return (
    <ul className="invitee-list">
      {invitees.map((invitee, index) => {
        const response = recipients.find((recipient) => recipient.recipient_ref === invitee.recipient_ref)?.response ?? "pending";
        const joined = response !== "pending";
        return (
          <li key={invitee.recipient_ref}>
            <span className={`invitee-avatar ${avatarClasses[index % avatarClasses.length]}`} aria-hidden="true">
              {invitee.display_name.slice(0, 1)}
            </span>
            <div>
              <strong>{invitee.display_name}</strong>
              <small>{invitee.is_current_player ? "You" : invitee.activity === "online" ? "Online" : "Away"}</small>
            </div>
            <span className={`invitee-status ${joined ? "ready" : ""}`}>{joined ? "Joined" : "Invited"}</span>
          </li>
        );
      })}
    </ul>
  );
}
