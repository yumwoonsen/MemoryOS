"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { PlayerShell } from "./player-shell";
import { usePlayerFlow } from "./player-flow-provider";
import type { DeliveryDeclineReasonV2 } from "@/lib/ai-memory-contract";
import {
  challengeTitle,
  decisionPayload,
  deliveryModeLabel,
  isDeliveryBoundToSeed,
  isDecisionConfirmation,
  parsePlayerDelivery,
  playerPreparationError,
  playerPreparationRetryable,
} from "@/lib/delivery-flow";
import type { DecisionRequest, PendingDelivery } from "@/lib/delivery-flow";
import type { PlayerExperienceSeedV2 } from "@/lib/player-delivery";

type View =
  | { kind: "unrevealed" }
  | { kind: "loading" }
  | { kind: "no_memory" }
  | { kind: "error"; message: string; retryable: boolean }
  | { kind: "ready"; delivery: PendingDelivery }
  | { kind: "decline"; delivery: PendingDelivery }
  | { kind: "sending"; delivery: PendingDelivery; request: DecisionRequest }
  | { kind: "decision_error"; delivery: PendingDelivery; request: DecisionRequest; message: string }
  | { kind: "accepted"; delivery: PendingDelivery }
  | { kind: "declined"; reason: DeliveryDeclineReasonV2 };

const avatarClasses = ["avatar-lime", "avatar-gold", "avatar-blue", "avatar-pink"];

function formatWords(value?: string | null) {
  if (!value) return "Squadmate";
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatClock(seconds?: number | null) {
  if (seconds == null) return "Match event";
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function MatchArtwork({ members }: { members: PlayerExperienceSeedV2["display_roster"] }) {
  return (
    <div className="player-memory-art" aria-hidden="true">
      <picture className="player-artwork">
        <source media="(max-width: 650px)" srcSet="/art/heroes/free-fire-map-mobile-v2.webp" />
        {/* This local WebP is already optimized for the fixed decorative map treatment. */}
        <img src="/art/heroes/free-fire-map-v2.webp" alt="" width="1440" height="520" fetchPriority="high" />
      </picture>
      <div className="player-route" />
      {members.slice(0, 4).map((member, index) => (
        <span className={`player-map-dot map-dot-${index + 1} ${avatarClasses[index]}`} key={member.recipient_ref}>
          {member.display_name.slice(0, 1)}
        </span>
      ))}
    </div>
  );
}

export function MemoryExperience({ seed }: { seed: PlayerExperienceSeedV2 }) {
  const router = useRouter();
  const {
    flow,
    setPreparedDelivery,
    acceptMission,
    declineMission,
  } = usePlayerFlow();
  const [view, setView] = useState<View>(() => flow.declineReason
    ? { kind: "declined", reason: flow.declineReason }
    : flow.delivery
      ? (flow.missionAccepted
        ? { kind: "accepted", delivery: flow.delivery }
        : { kind: "ready", delivery: flow.delivery })
      : { kind: "unrevealed" });
  const [announcement, setAnnouncement] = useState("A squad memory is waiting to be opened.");
  const requestSequence = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => {
    requestSequence.current += 1;
    activeRequest.current?.abort();
  }, []);

  const featuredMatch = seed.match_preview;
  const featuredMembers = seed.display_roster;
  const activeDelivery = "delivery" in view ? view.delivery : null;
  const modeLabel = activeDelivery ? deliveryModeLabel(activeDelivery) : undefined;

  const prepare = useCallback(async () => {
    if (activeRequest.current) return;
    const requestId = ++requestSequence.current;
    const controller = new AbortController();
    const minimumDelay = new Promise<void>((resolve) => window.setTimeout(resolve, 650));
    activeRequest.current = controller;
    setView({ kind: "loading" });
    setAnnouncement("AI preparation is in progress; evidence and consent validation are pending.");

    try {
      const response = await fetch("/api/delivery/prepare", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ request_id: seed.request_id }),
        signal: controller.signal,
      });
      const payload: unknown = await response.json();
      await minimumDelay;
      if (controller.signal.aborted || requestId !== requestSequence.current) return;
      const parsed = parsePlayerDelivery(payload);
      if (!response.ok || !parsed) {
        const failure = new Error(playerPreparationError(payload)) as Error & {
          retryable?: boolean;
        };
        failure.retryable = playerPreparationRetryable(payload);
        throw failure;
      }
      if (parsed.status === "not_generated") {
        setView({ kind: "no_memory" });
        setAnnouncement("No meaningful squad memory was generated from this telemetry.");
        return;
      }
      if (!isDeliveryBoundToSeed(parsed, seed)) {
        throw new Error("The prepared memory did not match the opted-in squad safely.");
      }

      setPreparedDelivery(parsed);
      setView({ kind: "ready", delivery: parsed });
      setAnnouncement(`${parsed.memory.title} is ready for your decision.`);
    } catch (error) {
      if (controller.signal.aborted || requestId !== requestSequence.current) return;
      setView({
        kind: "error",
        message: error instanceof Error
          ? error.message
          : "Your squad memory is not available right now.",
        retryable: error instanceof Error
          ? (error as Error & { retryable?: boolean }).retryable === true
          : true,
      });
      setAnnouncement("The squad memory could not be prepared.");
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }, [seed, setPreparedDelivery]);

  async function decide(request: DecisionRequest) {
    if (view.kind !== "ready" && view.kind !== "decline" && view.kind !== "decision_error") return;
    const delivery = view.delivery;
    setView({ kind: "sending", delivery, request });
    setAnnouncement("Saving your decision.");
    try {
      const response = await fetch("/api/delivery/decision", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ delivery_id: delivery.delivery_id, ...decisionPayload(request) }),
      });
      const payload: unknown = await response.json();
      if (!response.ok || !isDecisionConfirmation(payload, delivery.delivery_id, request)) {
        throw new Error("Your choice could not be saved safely.");
      }

      if (request.decision === "accepted") {
        acceptMission(delivery);
        setView({ kind: "accepted", delivery });
        setAnnouncement("Mission accepted. Your reunion mission is ready.");
        router.push("/mission");
      } else {
        declineMission(request.decline_reason);
        setView({ kind: "declined", reason: request.decline_reason });
        setAnnouncement("The mission was dismissed and your feedback was recorded.");
      }
    } catch (error) {
      setView({
        kind: "decision_error",
        delivery,
        request,
        message: error instanceof Error ? error.message : "Your choice could not be saved safely.",
      });
      setAnnouncement("Your decision could not be saved.");
    }
  }

  const busy = view.kind === "loading" || view.kind === "sending";
  const status = view.kind === "unrevealed"
    ? "Memory waiting"
      : view.kind === "loading"
      ? "Opening memory"
      : view.kind === "no_memory"
        ? "No memory surfaced"
      : view.kind === "error"
        ? "Memory unavailable"
        : view.kind === "decision_error"
          ? "Decision not saved"
      : view.kind === "accepted"
        ? "Mission accepted"
        : view.kind === "declined"
          ? "Decision complete"
          : busy
            ? "Saving decision"
            : "Current memory";

  return (
    <PlayerShell
      active="memory"
      status={status}
      announcement={announcement}
      busy={busy}
      modeLabel={modeLabel}
      modeHeading="Battle Royale"
    >
      {view.kind === "unrevealed" ? (
        <section className="demo-input-card" aria-labelledby="current-memory-title">
          <MatchArtwork members={featuredMembers} />
          <div className="demo-input-copy">
            <p className="demo-kicker">Memory not loaded</p>
            <h1 id="current-memory-title">A squad memory is waiting.</h1>
            <p className="demo-match-context">
              {formatWords(featuredMatch.game)} <span>/</span> {formatWords(featuredMatch.mode)} <span>/</span> {featuredMatch.map_name ?? "Battle Royale"}
            </p>
            <p className="reveal-teaser">Your original squad left a story behind. Open it when you are ready.</p>
            <div className="reveal-squad">
              <div className="player-avatar-stack" aria-label={`${featuredMembers.length} opted-in squad members`}>
                {featuredMembers.slice(0, 4).map((member, index) => (
                  <span className={`player-mini-avatar ${avatarClasses[index]}`} key={member.recipient_ref} aria-hidden="true">
                    {member.display_name.slice(0, 1)}
                  </span>
                ))}
              </div>
              <span><strong>The consent-safe squad</strong><small>{seed.recent_session_count} recent sessions available</small></span>
            </div>
            <button className="reveal-memory-button" type="button" onClick={() => void prepare()}>
              Open current memory
            </button>
          </div>
        </section>
      ) : null}

      {view.kind === "loading" && (
        <ProcessingCard
          kicker="AI preparation"
          title="Interpreting one squad moment."
          message="AI preparation is in progress. Evidence, consent, and mission validation are still pending before display."
        />
      )}

      {view.kind === "no_memory" && (
        <NoMemoryCard />
      )}

      {view.kind === "error" && (
        <StateCard
          title="Your memory is unavailable"
          message={view.message}
          onRetry={view.retryable ? () => void prepare() : undefined}
        />
      )}

      {view.kind === "ready" && (
        <MemoryDetail
          delivery={view.delivery}
          onAccept={() => void decide({ decision: "accepted" })}
          onDecline={() => setView({ kind: "decline", delivery: view.delivery })}
        />
      )}

      {view.kind === "decline" && (
        <DeclineCard
          onKeep={() => setView({ kind: "ready", delivery: view.delivery })}
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

      {view.kind === "accepted" && (
        <MemoryDetail delivery={view.delivery} accepted />
      )}

      {view.kind === "declined" && (
        <DeclinedCard reason={view.reason} />
      )}

      {view.kind === "decision_error" && (
        <DecisionErrorCard
          message={view.message}
          onRetry={() => void decide(view.request)}
          onBack={() => setView({ kind: "ready", delivery: view.delivery })}
        />
      )}
    </PlayerShell>
  );
}

function MemoryDetail({
  delivery,
  onAccept,
  onDecline,
  accepted = false,
}: {
  delivery: PendingDelivery;
  onAccept?: () => void;
  onDecline?: () => void;
  accepted?: boolean;
}) {
  const members = delivery.invitation_roster;
  const currentPlayer = members.find((member) => member.is_current_player);
  const requiredObjectives = delivery.next_chapter.objectives.filter((objective) => objective.required);

  return (
    <>
      <section className="player-hero" aria-labelledby="player-memory-title">
        <MatchArtwork members={members} />
        <div className="player-memory-copy">
          <div className="player-context-strip">
            <strong>{formatWords(delivery.source.game)}</strong>
            <span>{formatWords(delivery.source.mode)}</span>
            <span>{delivery.source.map_name ?? "Battle Royale"}</span>
          </div>
          <h1 id="player-memory-title">{delivery.memory.title}</h1>
          <p>{delivery.memory.summary}</p>
          <div className="player-squad-row">
            <div className="player-avatar-stack" aria-label={`${members.length} opted-in players`}>
              {members.map((member, index) => (
                <span className={`player-mini-avatar ${avatarClasses[index % avatarClasses.length]}`} key={member.recipient_ref} aria-hidden="true">
                  {member.display_name.slice(0, 1)}
                </span>
              ))}
            </div>
            <span><strong>{members.length} players can be invited</strong><small>Consent-safe squad roster</small></span>
          </div>
        </div>
      </section>

      <section className="memory-return-reason" aria-labelledby="return-reason-title">
        <p className="demo-kicker">Why this memory returned</p>
        <h2 id="return-reason-title">Your squad has unfinished business.</h2>
        <p>{delivery.memory.why_this_matters_now}</p>
      </section>

      <details className="player-evidence">
        <summary><span>What actually happened</span><small>{delivery.verified_moments.length} verified moments</small></summary>
        <div className="player-evidence-list">
          <p className="player-evidence-intro">The match moments behind this memory, in the order they happened.</p>
          {delivery.verified_moments.map((moment) => {
            return (
              <article key={moment.sequence}>
                <span aria-hidden="true">{moment.sequence}</span>
                <div>
                  <strong>{moment.label}</strong>
                  <small>{moment.location ?? "Match"} / {formatClock(moment.timestamp_seconds)}</small>
                </div>
              </article>
            );
          })}
        </div>
      </details>

      {currentPlayer ? (
        <details className="player-section your-perspective-card" open>
          <summary><span>Your side of the story</span><small>{currentPlayer.display_name} / Player perspective</small></summary>
          <div className="your-perspective-body">
            <span className="your-avatar avatar-lime" aria-hidden="true">{currentPlayer.display_name?.slice(0, 1) ?? "Y"}</span>
            <div>
              <p className="your-identity"><strong>{currentPlayer.display_name}</strong><span>Player perspective</span></p>
              <p className="your-message">{delivery.perspective.message}</p>
            </div>
          </div>
        </details>
      ) : null}

      <section className="player-section player-next" aria-labelledby="reunion-idea-title">
        <div className="next-chapter-label">Reunion idea / {formatWords(delivery.next_chapter.family)}</div>
        <h2 id="reunion-idea-title">{challengeTitle(delivery.next_chapter.title)}</h2>
        <p className="player-next-mission">{delivery.next_chapter.mission}</p>
        <ol className="player-objectives" aria-label="Reunion mission steps">
          {requiredObjectives.map((objective, index) => (
            <li key={objective.objective_ref}>
              <span>{index + 1}</span>
              <p>{objective.description}</p>
            </li>
          ))}
        </ol>
        {/* This local WebP is already optimized for the fixed decorative landmark treatment. */}
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

      {accepted ? (
        <section className="mission-handoff-card" aria-labelledby="accepted-title">
          <h2 id="accepted-title">Your reunion path is open.</h2>
          <p>The memory stays here for review. Continue when your squad is ready.</p>
          <Link className="reveal-memory-button history-home-action" href="/mission">Open reunion mission</Link>
        </section>
      ) : (
        <div className="review-actions history-decision-actions">
          <button className="reveal-memory-button" type="button" onClick={onAccept}>Accept mission</button>
          <button className="secondary-action" type="button" onClick={onDecline}>Decline</button>
        </div>
      )}
    </>
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

function DeclineCard({
  onKeep,
  onReason,
}: {
  onKeep: () => void;
  onReason: (reason: DeliveryDeclineReasonV2) => void;
}) {
  return (
    <section className="history-intro history-choice-card" aria-labelledby="decline-title">
      <p className="demo-kicker">Decline mission</p>
      <h1 id="decline-title">Why are you passing on this reunion?</h1>
      <p>Choose one reason. The mission will be suppressed, and your trusted match history will not be edited.</p>
      <div className="review-actions history-choice-actions">
        <button className="secondary-action" type="button" onClick={() => onReason("not_relevant")}>Not relevant to me</button>
        <button className="secondary-action" type="button" onClick={() => onReason("details_wrong")}>Details are wrong</button>
      </div>
      <button className="history-text-action" type="button" onClick={onKeep}>Keep reviewing</button>
    </section>
  );
}

function DeclinedCard({ reason }: { reason: DeliveryDeclineReasonV2 }) {
  const detailsWrong = reason === "details_wrong";
  return (
    <section className="history-intro history-completion" aria-labelledby="declined-title">
      <p className="demo-kicker">Decision complete</p>
      <h1 id="declined-title">{detailsWrong ? "Thanks for flagging the source." : "Thanks for letting us know."}</h1>
      <p>{detailsWrong
        ? "This mission is closed for the current session, and a source-quality signal was recorded for operations review. Your match history was not edited."
        : "This mission is closed for the current session. The relevance signal can help MemoryOS choose a better moment after durable storage is approved."}</p>
      <Link className="reveal-memory-button history-home-action" href="/history">View squad history</Link>
    </section>
  );
}

function DecisionErrorCard({
  message,
  onRetry,
  onBack,
}: {
  message: string;
  onRetry: () => void;
  onBack: () => void;
}) {
  return (
    <section className="player-state-card" role="alert">
      <span>Decision not saved</span>
      <h1>Your memory is still here.</h1>
      <p>{message}</p>
      <div className="review-actions">
        <button className="reveal-memory-button" type="button" onClick={onRetry}>Try saving again</button>
        <button className="secondary-action" type="button" onClick={onBack}>Back to memory</button>
      </div>
    </section>
  );
}

function NoMemoryCard() {
  return (
    <section className="player-state-card" role="status">
      <span>No memory generated</span>
      <h1>Nothing meaningful surfaced this time.</h1>
      <p>MemoryOS reviewed the available squad activity and chose not to force a story from ordinary evidence.</p>
      <p>A different result needs new match activity or updated eligible context, so the same telemetry will not be rerun from this screen.</p>
      <Link className="reveal-memory-button history-home-action" href="/history">View squad history</Link>
    </section>
  );
}

function StateCard({
  title,
  message,
  onRetry,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <section className="player-state-card" role="alert">
      <span>Current memory</span>
      <h1>{title}</h1>
      <p>{message}</p>
      {onRetry ? <button type="button" onClick={onRetry}>Try again</button> : null}
    </section>
  );
}
