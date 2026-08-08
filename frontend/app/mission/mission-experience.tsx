"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { PlayerShell } from "../player-shell";
import { usePlayerFlow } from "../player-flow-provider";
import { challengeTitle, deliveryModeLabel } from "@/lib/delivery-flow";
import type { PendingDelivery } from "@/lib/delivery-flow";
import {
  areInviteesReady,
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

type MissionView =
  | { kind: "ready" }
  | { kind: "invitation"; readyIds: string[] }
  | { kind: "verifying" }
  | { kind: "continuation"; verification: MissionVerification; chapter: ContinuationChapter }
  | { kind: "error"; message: string };

const avatarClasses = ["avatar-lime", "avatar-gold", "avatar-blue", "avatar-pink"];

export function MissionExperience() {
  const {
    flow,
    completeMission,
    setChapterFeedback,
    setInvitationReadyIds,
  } = usePlayerFlow();
  const [view, setView] = useState<MissionView>(() => flow.invitationReadyIds
    ? { kind: "invitation", readyIds: flow.invitationReadyIds }
    : { kind: "ready" });
  const [announcement, setAnnouncement] = useState("Reunion mission screen ready.");
  const simulationSequence = useRef(0);
  const delivery = flow.missionAccepted ? flow.delivery : null;
  const invitees = useMemo(
    () => delivery
      ? buildInvitees(
          delivery.player_perspectives,
          flow.currentPlayerId ?? undefined,
          flow.invitationPlayerIds ?? [],
        )
      : [],
    [delivery, flow.currentPlayerId, flow.invitationPlayerIds],
  );

  useEffect(() => () => {
    simulationSequence.current += 1;
  }, []);

  if (!delivery) {
    return (
      <PlayerShell
        active="mission"
        status="No active mission"
        announcement="No accepted reunion mission is available in this prototype session."
        modeHeading="Battle Royale"
      >
        <section className="player-state-card mission-empty-state" role="status">
          <span>No active mission</span>
          <h1>Accept a reunion mission first.</h1>
          <p>Open your current memory and accept its reunion idea. This prototype keeps the handoff only in the current app session.</p>
          <Link className="reveal-memory-button history-home-action" href="/">View current memory</Link>
        </section>
      </PlayerShell>
    );
  }

  const continuation = view.kind === "continuation"
    ? { verification: view.verification, chapter: view.chapter }
    : flow.continuation;
  const busy = view.kind === "verifying";
  const status = continuation
    ? "Story continued"
    : view.kind === "invitation"
      ? "Squad invitation"
      : busy
        ? "Checking match"
        : view.kind === "error"
          ? "Mission paused"
        : "Active mission";

  function beginInvitation() {
    if (invitees.length < 2) {
      setView({ kind: "error", message: "There are not enough opted-in squad members to continue." });
      return;
    }
    const currentPlayer = invitees.find((invitee) => invitee.is_current_player);
    if (!currentPlayer) {
      setView({ kind: "error", message: "The current player is not eligible for this reunion lobby." });
      return;
    }
    const readyIds = [currentPlayer.player_id];
    setInvitationReadyIds(readyIds);
    setView({ kind: "invitation", readyIds });
    setAnnouncement("The privacy-safe squad lobby is open.");
  }

  function acceptInvitations() {
    if (view.kind !== "invitation") return;
    const readyIds = invitees.map((invitee) => invitee.player_id);
    setInvitationReadyIds(readyIds);
    setView({ kind: "invitation", readyIds });
    setAnnouncement("Every invited squad member accepted and joined the lobby.");
  }

  async function simulateMatch() {
    if (view.kind !== "invitation" || !delivery) return;
    if (!areInviteesReady(invitees, view.readyIds)) {
      setView({ kind: "error", message: "Every invited squad member must accept before the game can start." });
      setAnnouncement("The game is waiting for every invited squad member to accept.");
      return;
    }
    const simulationId = ++simulationSequence.current;
    setView({ kind: "verifying" });
    setAnnouncement("The prototype game has started with the accepted squad.");
    await new Promise<void>((resolve) => window.setTimeout(resolve, 700));
    if (simulationId !== simulationSequence.current) return;
    const matchResult = createSyntheticRematch(invitees);
    const verification = verifyMission(delivery.next_chapter.objectives, matchResult);
    const chapter = createContinuationChapter(delivery.memory, delivery.next_chapter, verification);
    if (!chapter) {
      setView({ kind: "error", message: "The rematch did not complete every required mission objective." });
      setAnnouncement("The reunion mission is still in progress.");
      return;
    }
    completeMission(verification, chapter);
    setView({ kind: "continuation", verification, chapter });
    setAnnouncement("All required objectives were verified. The story continues.");
  }

  function hideChapter() {
    setChapterFeedback("hidden");
    setAnnouncement("This chapter is hidden from the session timeline without disputing match facts.");
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
          verification={continuation.verification}
          chapter={continuation.chapter}
          feedback={flow.continuation?.feedback ?? null}
          onHide={hideChapter}
        />
      ) : view.kind === "ready" ? (
        <MissionReadyCard delivery={delivery} invitees={invitees} onContinue={beginInvitation} />
      ) : view.kind === "invitation" ? (
        <InvitationCard
          delivery={delivery}
          invitees={invitees}
          readyIds={view.readyIds}
          onAccept={acceptInvitations}
          onSimulate={() => void simulateMatch()}
        />
      ) : view.kind === "verifying" ? (
        <ProcessingCard />
      ) : view.kind === "error" ? (
        <section className="player-state-card" role="alert">
          <span>Mission paused</span>
          <h1>The reunion could not continue.</h1>
          <p>{view.message}</p>
          <button
            type="button"
            onClick={() => setView(flow.invitationReadyIds
              ? { kind: "invitation", readyIds: flow.invitationReadyIds }
              : { kind: "ready" })}
          >
            Return to mission
          </button>
        </section>
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
  return (
    <section className="history-intro mission-start-card" aria-labelledby="mission-title">
      <p className="demo-kicker">Active mission</p>
      <h1 id="mission-title">{challengeTitle(delivery.next_chapter.title)}</h1>
      <p className="mission-source-memory">From “{delivery.memory.title}”</p>
      <p>{delivery.next_chapter.mission}</p>
      <ObjectiveList objectives={requiredObjectives} />
      <div className="safe-squad-block">
        <span className="next-chapter-label">Opted-in squad only</span>
        <div className="player-squad-row mission-eligible-summary">
          <div className="player-avatar-stack" aria-label={`${invitees.length} eligible opted-in players`}>
            {invitees.slice(0, 4).map((invitee, index) => (
              <span className={`player-mini-avatar ${avatarClasses[index % avatarClasses.length]}`} key={invitee.player_id} aria-hidden="true">
                {invitee.display_name.slice(0, 1)}
              </span>
            ))}
          </div>
          <span><strong>{invitees.length} eligible players</strong><small>Full roster appears with the invitation</small></span>
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
  const allReady = areInviteesReady(invitees, readyIds);
  const waitingNames = invitees
    .filter((invitee) => !readyIds.includes(invitee.player_id))
    .map((invitee) => invitee.display_name);
  return (
    <section className="history-intro invitation-card" aria-labelledby="invitation-title">
      <p className="demo-kicker">Squad invite</p>
      <h1 id="invitation-title">Bring the squad back.</h1>
      <p>{challengeTitle(delivery.next_chapter.title)} is ready for the players who opted in.</p>
      <InviteeList invitees={invitees} readyIds={readyIds} />
      <div className="squad-ready-count" aria-live="polite">
        <strong>{readyIds.length}/{invitees.length}</strong>
        <span>squad ready</span>
      </div>
      {allReady ? (
        <button className="reveal-memory-button" type="button" onClick={onSimulate}>Start game</button>
      ) : (
        <button className="reveal-memory-button" type="button" onClick={onAccept}>
          {waitingNames.length === 1 ? `Simulate ${waitingNames[0]} accepting` : "Simulate squad accepting"}
        </button>
      )}
      <p className="prototype-boundary">This remains a labelled demo; no live match telemetry is being claimed.</p>
    </section>
  );
}

function ContinuationCard({
  verification,
  chapter,
  feedback,
  onHide,
}: {
  verification: MissionVerification;
  chapter: ContinuationChapter;
  feedback: "hidden" | null;
  onHide: () => void;
}) {
  return (
    <>
      <section className="story-continues-card" aria-labelledby="story-continues-title">
        <p className="demo-kicker">Mission complete</p>
        <h1 id="story-continues-title">Story Continues: {chapter.title}</h1>
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

      <section className="chapter-feedback-card" aria-labelledby="chapter-action-title">
        <p className="demo-kicker">Chapter complete</p>
        <h2 id="chapter-action-title">What should happen to this sequel?</h2>
        {feedback === "hidden" ? (
          <>
            <p className="feedback-complete" role="status">Hidden from this session timeline. This does not dispute the verified match result.</p>
            <Link className="secondary-action history-home-action" href="/history#latest">View squad history</Link>
          </>
        ) : (
          <div className="review-actions">
            <Link
              className="reveal-memory-button history-home-action"
              href="/history#latest"
            >
              View squad history
            </Link>
            <button className="secondary-action" type="button" onClick={onHide}>Hide this chapter</button>
          </div>
        )}
        <p className="prototype-boundary">Hiding a chapter is optional feedback. “Details are wrong” remains a separate source-quality signal on the memory screen.</p>
      </section>
    </>
  );
}

function ProcessingCard() {
  return (
    <section className="demo-processing-card" role="status">
      <div className="demo-processing-mark" aria-hidden="true">M</div>
      <p className="demo-kicker">Prototype match</p>
      <h1>Game in progress.</h1>
      <p className="reveal-loading-copy">The squad is completing the AI-generated objectives. The labelled result will be checked against every required mission rule.</p>
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
