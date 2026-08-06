"use client";

import { useRef, useState } from "react";

import { roleLabels, scenarioByKey, scenarios } from "@/lib/fixtures";
import type {
  MemoryApiError,
  MemoryEngineResult,
  MemoryPack,
  QuestObjective,
  Scenario,
  ScenarioKey,
} from "@/lib/types";

type ViewState = "idle" | "loading" | "loaded" | "error";

const scoreLabels = {
  specificity: "Specificity",
  evidence_grounding: "Evidence grounding",
  perspective_distinctness: "Distinct perspectives",
  quest_connection: "Quest connection",
} as const;

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function isMemoryEngineResult(value: unknown): value is MemoryEngineResult {
  return Boolean(
    value &&
      typeof value === "object" &&
      "status" in value &&
      ["ready", "needs_human_confirmation", "rejected"].includes(
        String((value as { status?: unknown }).status),
      ),
  );
}

function isOptedIn(member: MemoryPack["squad"]["members"][number]) {
  return member.opted_in !== false;
}

function formatRuleValue(value: QuestObjective["verification"]["target"]) {
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function formatRole(role?: string | null) {
  return role ? roleLabels[role] ?? role.replaceAll("_", " ") : "Squadmate";
}

function formatMode(mode: string) {
  return mode.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatClock(seconds?: number | null) {
  if (seconds == null) return "Match event";
  const minutes = Math.floor(seconds / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  return `+${minutes}:${remainder}`;
}

function formatMatchDate(value?: string | null) {
  if (!value) return "Archived match";
  return new Intl.DateTimeFormat("en-SG", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function eventDescription(event: MemoryPack["match_events"][number], pack: MemoryPack) {
  const name = (playerId?: string | null) =>
    pack.squad.members.find((member) => member.player_id === playerId)?.display_name ??
    "The squad";

  if (event.type === "retreat_ping") {
    return `${name(event.actor_id)} called retreat ${event.details?.count ?? "several"} times.`;
  }
  if (event.type === "revive") {
    const zone = event.details?.zone_state === "closing" ? " while the zone was closing" : "";
    return `${name(event.actor_id)} revived ${name(event.target_id)}${zone}.`;
  }
  if (event.type === "vehicle_escape") {
    return `${name(event.actor_id)} drove ${event.details?.passengers ?? "the"} teammates out with the squad at ${event.details?.health_state ?? "low"} health.`;
  }
  if (event.type === "last_player_alive") {
    return `${name(event.actor_id)} became the last squad member alive.`;
  }
  if (event.type === "cover_fire") {
    return `${name(event.actor_id)} held cover fire for ${event.details?.duration_seconds ?? "several"} seconds.`;
  }
  if (event.type === "final_zone_survival") {
    return `${name(event.actor_id)} carried the squad into the final zone.`;
  }
  return `${name(event.actor_id)} recorded a verified ${event.type.replaceAll("_", " ")} event.`;
}

function statusMark(key: ScenarioKey) {
  if (key === "ready") return "✓";
  if (key === "review") return "?";
  return "—";
}

export function MemoryExperience() {
  const [selectedKey, setSelectedKey] = useState<ScenarioKey>("ready");
  const [viewState, setViewState] = useState<ViewState>("idle");
  const [result, setResult] = useState<MemoryEngineResult | null>(null);
  const [error, setError] = useState("");
  const [engineMode, setEngineMode] = useState<"live" | "sample" | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [caption, setCaption] = useState(
    scenarioByKey.ready.pack.human_memory?.caption ?? "",
  );
  const [announcement, setAnnouncement] = useState("Ready to discover a memory.");
  const resultRef = useRef<HTMLElement>(null);
  const inviteButtonRef = useRef<HTMLButtonElement>(null);
  const inviteDialogRef = useRef<HTMLDialogElement>(null);

  const selected = scenarioByKey[selectedKey];
  const optedInMembers = selected.pack.squad.members.filter(isOptedIn);

  async function discover(pack: MemoryPack, shouldScroll = true) {
    setViewState("loading");
    setError("");
    setDismissed(false);
    setEditing(false);
    setAnnouncement(`Reading ${pack.match.match_id}.`);

    try {
      const requestOptions: RequestInit = {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(pack),
      };
      const response = await fetch("/api/discover", requestOptions);
      const responseMode =
        response.headers.get("x-memoryos-mode") === "live" ? "live" : "sample";
      const responseText = await response.text();
      let body: MemoryEngineResult | MemoryApiError;
      try {
        body = JSON.parse(responseText) as MemoryEngineResult | MemoryApiError;
      } catch {
        throw new Error("MemoryOS returned an unreadable response. Please refresh and try again.");
      }

      if (!response.ok || !isMemoryEngineResult(body)) {
        throw new Error(
          "message" in body && body.message
            ? body.message
            : "The engine could not read this pack.",
        );
      }

      setResult(body);
      setEngineMode(responseMode);
      setViewState("loaded");
      setAnnouncement(
        body.status === "ready"
          ? `${body.memory?.title ?? "Memory"} is ready.`
          : body.status === "needs_human_confirmation"
            ? `${body.memory?.title ?? "This memory"} needs your confirmation.`
            : "The engine safely skipped this match.",
      );
      if (shouldScroll) {
        window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
      }
    } catch (caught) {
      setViewState("error");
      setError(caught instanceof Error ? caught.message : "MemoryOS is unavailable.");
      setAnnouncement("Memory discovery failed. You can try again.");
    }
  }

  function chooseScenario(scenario: Scenario) {
    setSelectedKey(scenario.key);
    setResult(null);
    setViewState("idle");
    setDismissed(false);
    setEditing(false);
    setEngineMode(null);
    setCaption(scenario.pack.human_memory?.caption ?? "");
    setAnnouncement(`${scenario.title} selected.`);
  }

  function confirmMemory() {
    const confirmedPack: MemoryPack = {
      ...selected.pack,
      human_memory: {
        ...(selected.pack.human_memory ?? {}),
        caption: caption.trim() || selected.pack.human_memory?.caption,
        confirmed: true,
      },
    };
    void discover(confirmedPack, false);
  }

  function showInvite() {
    inviteDialogRef.current?.showModal();
  }

  function closeInvite() {
    inviteDialogRef.current?.close();
    inviteButtonRef.current?.focus();
  }

  return (
    <main>
      <a className="skip-link" href="#story">Skip to the memory story</a>
      <header className="site-header shell">
        <a className="brand" href="#top" aria-label="Next Chapter home">
          <span className="brand-mark">NC</span>
          <span>
            <strong>NEXT CHAPTER</strong>
            <small>Powered by MemoryOS</small>
          </span>
        </a>
        <div className="header-meta">
          <span className="status-dot" aria-hidden="true" />
          Guardrails active · {engineMode === "live" ? "Live local engine" : engineMode === "sample" ? "Safe sample mode" : "Waiting to run"}
        </div>
        <a className="text-link" href="#grounding">How it stays grounded</a>
      </header>

      <section className="hero shell" id="top">
        <div className="hero-copy">
          <p className="eyebrow">Garena Next Chapter</p>
          <h1>Your squad has <em>unfinished stories.</em></h1>
          <p className="hero-lede">
            MemoryOS turns verified match evidence into one shared memory, distinct
            player perspectives, and a verifiable next chapter—without letting AI invent
            the facts.
          </p>
          <div className="hero-actions">
            <button
              className="primary-button"
              onClick={() => void discover(selected.pack)}
              disabled={viewState === "loading"}
            >
              <span>{viewState === "loading" ? "Reading the match…" : "Discover the memory"}</span>
              <span aria-hidden="true">↗</span>
            </button>
            <span className="trust-note">Grounded gameplay required · At least two players opted in</span>
          </div>
        </div>

        <aside className="pack-card" aria-label="Selected Memory Pack">
          <div className="pack-topline">
            <span>Memory Pack</span>
            <span>{selected.pack.match.match_id}</span>
          </div>
          <div className="pack-scan" aria-hidden="true"><span /></div>
          <p className="pack-kicker">{selected.pack.squad.squad_id.replaceAll("-", " ")}</p>
          <h2>{selected.pack.match.map_name}</h2>
          <p>{formatMode(selected.pack.match.mode)} · Placement #{selected.pack.match.placement}</p>
          <div className="pack-stat-row">
            <div><strong>{selected.pack.squad.matches_together}</strong><span>matches together</span></div>
            <div><strong>{selected.pack.squad.days_since_full_squad ?? 0}</strong><span>days apart</span></div>
          </div>
          <div className="member-list">
            {selected.pack.squad.members.map((member) => (
              <span
                className={`member-chip ${isOptedIn(member) ? "" : "member-opted-out"}`}
                key={member.player_id}
              >
                <b>{member.display_name.slice(0, 1)}</b>
                {member.display_name} · {isOptedIn(member) ? formatRole(member.role) : "Opted out"}
              </span>
            ))}
          </div>
          <div className="pack-footer">
            <span>Schema v{selected.pack.schema_version}</span>
            <span>{optedInMembers.length} of {selected.pack.squad.members.length} opted in</span>
          </div>
        </aside>
      </section>

      <section className="pipeline-section shell" aria-labelledby="pipeline-heading">
        <div className="section-heading compact-heading">
          <div>
            <p className="eyebrow">One guarded path</p>
            <h2 id="pipeline-heading">Facts in. Verified chapter out.</h2>
          </div>
          <p>AI proposes structure. MemoryOS rebuilds the wording and checks every important link.</p>
        </div>
        <div className="pipeline-flow">
          <article className="pipeline-card pipeline-input">
            <span className="pipeline-index">01 · Input</span>
            <h3>Verified signals</h3>
            <ul>
              <li>Match-event IDs and player roles</li>
              <li>Player-authored captions and reactions</li>
              <li>Opted-in squad members only</li>
            </ul>
          </article>
          <span className="pipeline-arrow" aria-hidden="true">→</span>
          <article className="pipeline-card pipeline-transform">
            <span className="pipeline-index">02 · Guarded AI</span>
            <h3>Canonical transformation</h3>
            <ul>
              <li>Memory discovery and safe abstention</li>
              <li>Role-specific player perspectives</li>
              <li>Fact-based wording rebuilt by code</li>
            </ul>
          </article>
          <span className="pipeline-arrow" aria-hidden="true">→</span>
          <article className="pipeline-card pipeline-output">
            <span className="pipeline-index">03 · Output</span>
            <h3>Validated next chapter</h3>
            <ul>
              <li>One grounded shared memory</li>
              <li>One view per opted-in player</li>
              <li>Machine-checkable quest rules</li>
            </ul>
          </article>
        </div>
      </section>

      <section className="scenario-section shell" aria-labelledby="scenario-heading">
        <div className="section-heading compact-heading">
          <div><p className="eyebrow">Three decisions, one standard</p><h2 id="scenario-heading">Choose a memory signal</h2></div>
          <p>See what MemoryOS continues, pauses, and refuses to invent.</p>
        </div>
        <div className="scenario-grid" role="list">
          {scenarios.map((scenario) => (
            <button
              type="button"
              className={`scenario-card scenario-${scenario.key}`}
              aria-pressed={selectedKey === scenario.key}
              key={scenario.key}
              onClick={() => chooseScenario(scenario)}
            >
              <span className="scenario-mark" aria-hidden="true">{statusMark(scenario.key)}</span>
              <span className="scenario-copy"><small>{scenario.label}</small><strong>{scenario.title}</strong><span>{scenario.subtitle}</span></span>
              <span className="scenario-arrow" aria-hidden="true">→</span>
            </button>
          ))}
        </div>
      </section>

      <p className="sr-only" aria-live="polite">{announcement}</p>

      <section className="result-shell shell" id="story" ref={resultRef} aria-busy={viewState === "loading"}>
        {viewState === "idle" && <IdleStory selected={selected} onDiscover={() => void discover(selected.pack)} />}
        {viewState === "loading" && <LoadingStory />}
        {viewState === "error" && <ErrorStory message={error} onRetry={() => void discover(selected.pack)} />}
        {viewState === "loaded" && result?.status === "rejected" && (
          <RejectedStory result={result} onTryReady={() => chooseScenario(scenarioByKey.ready)} />
        )}
        {viewState === "loaded" && result && result.status !== "rejected" && result.memory && (
          <>
            {result.status === "needs_human_confirmation" && !dismissed && (
              <ReviewCheckpoint
                caption={caption}
                editing={editing}
                onCaptionChange={setCaption}
                onConfirm={confirmMemory}
                onDismiss={() => { setDismissed(true); setAnnouncement("Memory dismissed. Undo is available."); }}
                onEdit={() => setEditing((value) => !value)}
              />
            )}
            {dismissed ? (
              <DismissedStory onUndo={() => { setDismissed(false); setAnnouncement("Memory restored for review."); }} />
            ) : (
              <MemoryStory result={result} pack={selected.pack} onInvite={showInvite} inviteButtonRef={inviteButtonRef} />
            )}
          </>
        )}
      </section>

      <footer className="site-footer shell">
        <span>Next Chapter / MemoryOS</span>
        <p>Built with synthetic Memory Packs. No live Free Fire data or player messages.</p>
        <a href="#top">Back to top ↑</a>
      </footer>

      <dialog className="invite-dialog" ref={inviteDialogRef} onCancel={closeInvite}>
        <button className="dialog-close" aria-label="Close invite preview" onClick={closeInvite}>×</button>
        <p className="eyebrow">Squad invite preview · Demo simulation</p>
        <h2>The opted-in squad.<br />One more run.</h2>
        <p>
          {selected.pack.player_profile.player_id
            ? selected.pack.squad.members.find((member) => member.player_id === selected.pack.player_profile.player_id)?.display_name
            : "A squadmate"} wants the squad back for “{result?.next_chapter?.title}”.
        </p>
        <div className="dialog-squad">
          {optedInMembers.map((member) => <span key={member.player_id}>{member.display_name.slice(0, 1)}</span>)}
        </div>
        <p className="dialog-note">Invite delivery is not connected in this prototype.</p>
        <button className="secondary-button" onClick={closeInvite}>Close preview</button>
      </dialog>
    </main>
  );
}

function IdleStory({ selected, onDiscover }: { selected: Scenario; onDiscover: () => void }) {
  return (
    <div className="idle-story panel-dashed">
      <span className="idle-number">01</span>
      <div><p className="eyebrow">Selected for review</p><h2>{selected.title}</h2><p>The evidence is assembled. Let MemoryOS decide whether this match deserves a next chapter.</p></div>
      <button className="secondary-button" onClick={onDiscover}>Run this Memory Pack</button>
    </div>
  );
}

function LoadingStory() {
  return (
    <div className="loading-story">
      <div className="loading-orbit" aria-hidden="true"><span /></div>
      <p className="eyebrow">MemoryOS is reading the signal</p>
      <h2>Separating the story from the noise.</h2>
      <div className="loading-steps" aria-hidden="true"><span className="active">Discover</span><span>Perspective</span><span>Quest</span><span>Validate</span></div>
    </div>
  );
}

function ErrorStory({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error-story">
      <span className="status-icon">!</span>
      <p className="eyebrow">The connection dropped</p>
      <h2>The memory is still safe.</h2>
      <p>{message}</p>
      <button className="secondary-button" onClick={onRetry}>Try again</button>
    </div>
  );
}

function RejectedStory({ result, onTryReady }: { result: MemoryEngineResult; onTryReady: () => void }) {
  const safeAbstention = !result.memory && result.validation.passed;
  const leadIssue =
    result.validation.issues.find((issue) => issue.severity === "error") ??
    result.validation.issues[0];

  return (
    <article className="rejected-story">
      <div className="rejected-copy">
        <span className="decision-seal" aria-hidden="true">—</span>
        <p className="eyebrow">{safeAbstention ? "Safely skipped" : "Validation blocked"}</p>
        <h2>{safeAbstention ? "Not enough grounded evidence." : "This story did not pass."}</h2>
        <p>
          {safeAbstention
            ? "Nothing was generated. MemoryOS leaves weak, eventless, or consent-insufficient inputs in match history instead of manufacturing nostalgia."
            : "The candidate was stopped because one or more deterministic evidence, identity, consent, safety, or quest checks failed."}
        </p>
        <ul className="decision-reasons">
          {result.discovery.reasons.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
        <button className="secondary-button" onClick={onTryReady}>Try a stronger memory pack</button>
      </div>
      <aside className="threshold-card">
        <div className="threshold-score"><strong>{percent(result.discovery.signal_score)}</strong><span>memory signal</span></div>
        <div className="meter" style={{ "--score": `${result.discovery.signal_score * 100}%` } as React.CSSProperties}><span /></div>
        <div className="threshold-labels"><span>0%</span><b>{percent(result.discovery.threshold)} required</b><span>100%</span></div>
        <div className="safe-skip"><span>{safeAbstention ? "✓" : "!"}</span><div><strong>{safeAbstention ? "Generation safely skipped" : "Deterministic validation failed"}</strong><p>{leadIssue?.message ?? "The output did not meet the MemoryOS contract."}</p></div></div>
      </aside>
    </article>
  );
}

function ReviewCheckpoint({
  caption,
  editing,
  onCaptionChange,
  onConfirm,
  onDismiss,
  onEdit,
}: {
  caption: string;
  editing: boolean;
  onCaptionChange: (value: string) => void;
  onConfirm: () => void;
  onDismiss: () => void;
  onEdit: () => void;
}) {
  return (
    <section className="review-checkpoint" aria-labelledby="review-title">
      <div className="review-icon" aria-hidden="true">?</div>
      <div className="review-copy">
        <p className="eyebrow">Grounding passed—you decide if it matters</p>
        <h2 id="review-title">Does “{caption || "this moment"}” belong in your squad story?</h2>
        <p>The facts are grounded, but nothing becomes a reunion prompt until a player confirms it.</p>
        {editing && (
          <label className="caption-field">Memory caption<input value={caption} maxLength={120} onChange={(event) => onCaptionChange(event.target.value)} /></label>
        )}
      </div>
      <div className="review-actions">
        <button className="primary-button" onClick={onConfirm}>Yes, keep this memory</button>
        <button className="secondary-button" onClick={onEdit}>{editing ? "Done editing" : "Edit caption"}</button>
        <button className="quiet-button" onClick={onDismiss}>Not this one</button>
      </div>
    </section>
  );
}

function DismissedStory({ onUndo }: { onUndo: () => void }) {
  return (
    <div className="dismissed-story">
      <span className="status-icon">✓</span>
      <p className="eyebrow">Decision recorded locally</p>
      <h2>This memory won’t become a reunion prompt.</h2>
      <p>No data was saved or sent. This prototype keeps the decision in your current session only.</p>
      <button className="secondary-button" onClick={onUndo}>Undo dismissal</button>
    </div>
  );
}

function MemoryStory({
  result,
  pack,
  onInvite,
  inviteButtonRef,
}: {
  result: MemoryEngineResult;
  pack: MemoryPack;
  onInvite: () => void;
  inviteButtonRef: React.RefObject<HTMLButtonElement | null>;
}) {
  const memory = result.memory!;
  const quest = result.next_chapter;
  const evidenceIds = new Set(memory.evidence.map((item) => item.event_id));
  const evidenceEvents = pack.match_events
    .filter((event) => evidenceIds.has(event.event_id))
    .sort((a, b) => (a.timestamp_seconds ?? 0) - (b.timestamp_seconds ?? 0));

  return (
    <article className="memory-story">
      <section className="memory-reveal">
        <div className="memory-main">
          <div className="status-row">
            <span className={`status-pill ${result.status === "ready" ? "status-ready" : "status-review"}`}>
              {result.status === "ready" ? "✓ Player-confirmed memory" : "? Awaiting player confirmation"}
            </span>
            <span className="memory-type">{memory.memory_type}</span>
          </div>
          <p className="chapter-index">Memory / {pack.match.match_id}</p>
          <h2>{memory.title}</h2>
          <p className="memory-summary">{memory.summary}</p>
          <div className="match-meta">
            <span>{pack.match.map_name}</span><span>{evidenceEvents[0]?.location ?? "Match location"}</span><span>Placement #{pack.match.placement}</span><span>{formatMatchDate(pack.match.played_at)}</span>
          </div>
        </div>
        <aside className="signal-card">
          <div className="signal-ring" style={{ "--score": `${result.discovery.signal_score * 360}deg` } as React.CSSProperties}>
            <div><strong>{percent(result.discovery.signal_score)}</strong><span>memory signal</span></div>
          </div>
          <p>This cleared the {percent(result.discovery.threshold)} discovery threshold.</p>
          <ul>{result.discovery.reasons.slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}</ul>
        </aside>
      </section>

      <section className="evidence-section" id="grounding">
        <div className="section-heading">
          <div><p className="eyebrow">Evidence ledger</p><h2>What actually happened</h2></div>
          <p>Every factual beat cites a match-event ID. Captions and reactions can add meaning, but cannot replace gameplay evidence.</p>
        </div>
        <ol className="timeline">
          {evidenceEvents.map((event, index) => (
            <li key={event.event_id}>
              <div className="timeline-marker"><span>{String(index + 1).padStart(2, "0")}</span></div>
              <div className="timeline-time"><strong>{formatClock(event.timestamp_seconds)}</strong><span>{event.location ?? pack.match.map_name}</span></div>
              <div className="timeline-event"><h3>{event.type.replaceAll("_", " ")}</h3><p>{eventDescription(event, pack)}</p><details><summary>View source event</summary><code>{event.event_id}</code><span>{event.importance ?? "medium"} importance</span></details></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="perspectives-section">
        <div className="section-heading">
          <div><p className="eyebrow">One night · {result.player_perspectives.length} points of view</p><h2>Same memory. Different meaning.</h2></div>
          <p>Each opted-in player receives exactly one recall, using their canonical name and evidence from this memory.</p>
        </div>
        <div className="perspective-grid">
          {result.player_perspectives.map((perspective, index) => {
            const member = pack.squad.members.find((item) => item.player_id === perspective.player_id);
            return (
              <article className="perspective-card" key={perspective.player_id}>
                <div className="perspective-top"><span className="avatar">{perspective.display_name.slice(0, 1)}</span><div><h3>{perspective.display_name}</h3><p>{formatRole(member?.role)}</p></div><span className="perspective-number">0{index + 1}</span></div>
                <blockquote>“{perspective.message.replace(/^“|”$/g, "")}</blockquote>
                <div className="evidence-chip"><span aria-hidden="true">⌁</span> {perspective.evidence_event_ids.join(" · ")}</div>
              </article>
            );
          })}
        </div>
      </section>

      {quest && (
        <section className="quest-section">
          <div className="quest-gridline" aria-hidden="true" />
          <div className="quest-header"><div><p className="eyebrow">Chapter 02 · The {quest.recipe}</p><h2>{quest.title}</h2><p>{quest.mission}</p></div><span className="quest-stamp">NEXT<br />CHAPTER</span></div>
          {quest.objectives.find((objective) => objective.objective_id === "return-the-favour") && (
            <div className="twist-card"><span>The twist</span><strong>{quest.objectives.find((objective) => objective.objective_id === "return-the-favour")?.description}</strong><p>Same place. Reversed roles.</p></div>
          )}
          <div className="objective-columns">
            <ObjectiveList title="Mission objectives" objectives={quest.objectives.filter((objective) => objective.required)} />
            <ObjectiveList title="Bonus objectives" objectives={quest.objectives.filter((objective) => !objective.required)} />
          </div>
          <div className="quest-action"><button ref={inviteButtonRef} className="primary-button light-button" onClick={onInvite}>Preview squad invite <span aria-hidden="true">↗</span></button><span>Rules are machine-checkable · Live match verification is not connected</span></div>
        </section>
      )}

      <section className="validation-section">
        <div className="section-heading">
          <div><p className="eyebrow">{result.status === "ready" ? "Validation passed" : "Grounding passed · Confirmation pending"}</p><h2>Grounded before it becomes a story.</h2></div>
          <p>AI may suggest structure; MemoryOS rebuilds factual wording and checks evidence, identity, consent, safety, and quest rules.</p>
        </div>
        <div className="score-grid">
          {(Object.keys(scoreLabels) as Array<keyof typeof scoreLabels>).map((key) => (
            <div className="score-card" key={key}><span>{scoreLabels[key]}</span><strong>{percent(result.validation.scores[key])}</strong><div><i style={{ width: percent(result.validation.scores[key]) }} /></div></div>
          ))}
        </div>
        <div className="validation-note"><span>✓</span><p><strong>{result.validation.passed ? "All deterministic checks passed" : "Human review required"}</strong> · {result.metadata.prose_renderer === "canonical-v1" ? "Canonical wording rebuilt from verified fields" : "Verified wording renderer"} · Provider: {result.metadata.provider} / {result.metadata.model}</p></div>
      </section>
    </article>
  );
}

function ObjectiveList({ title, objectives }: { title: string; objectives: NonNullable<MemoryEngineResult["next_chapter"]>["objectives"] }) {
  return (
    <div className="objective-list"><h3>{title}</h3><ol>{objectives.map((objective, index) => <li key={objective.objective_id}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{objective.description}</strong><small>Rule · {objective.verification.metric.replaceAll("_", " ")} · {objective.verification.operator.replaceAll("_", " ")} · {formatRuleValue(objective.verification.target)}</small><small>Source · {objective.source_event_ids.join(" · ")}</small></div></li>)}</ol></div>
  );
}
