"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  eligibleDisplayPlayers,
  eligibleInvitationPlayers,
  parseStudioTraceV2,
  parseStudioInterpretDeliveryV2,
} from "@/lib/ai-memory-contract";
import type {
  GroundedClaimV2,
  RawTelemetryBatchV2,
  StudioInterpretDeliveryResultV2,
  StudioInterpretationTraceV2,
} from "@/lib/ai-memory-contract";
import { usePlayerFlow } from "../player-flow-provider";

type ResultTab = "summary" | "grounding" | "mission";
type RunSource = "waiting" | "live" | "sample";
type HealthState = {
  status: "checking" | "ok" | "sample" | "error";
  provider: string;
  model: string;
  message: string;
};

const stageDefinitions = [
  {
    id: "deterministic_preparation",
    number: "01",
    label: "Deterministic preparation",
    owner: "Safety referee",
    description: "Normalizes telemetry, applies consent, filters media, and builds neutral event windows.",
  },
  {
    id: "ai_interpretation",
    number: "02",
    label: "AI interpretation",
    owner: "Memory intelligence",
    description: "Chooses one connected episode and proposes the memory, perspectives, and mission wording.",
  },
  {
    id: "deterministic_validation",
    number: "03",
    label: "Deterministic validation",
    owner: "Safety referee",
    description: "Checks claims, identities, media references, and backend-owned mission rules.",
  },
  {
    id: "player_decision",
    number: "04",
    label: "Player decision",
    owner: "Player",
    description: "Records accept or one decline reason without changing trusted telemetry.",
  },
] as const;

function formatWords(value: string) {
  return value.replaceAll("_", " ").replaceAll(":", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatClock(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function safeSubject(subjectId: string, telemetry: RawTelemetryBatchV2) {
  if (subjectId === "squad") return "Eligible squad";
  if (subjectId.startsWith("anonymous:")) return "Anonymous squadmate";
  return telemetry.squad.players.find((player) => player.player_id === subjectId)?.display_name ?? "Consent-safe player";
}

function safeRuleTarget(target: string | number | boolean | string[], telemetry: RawTelemetryBatchV2) {
  if (!Array.isArray(target)) return String(target);
  return target.map((item) => safeSubject(item, telemetry) === "Consent-safe player" ? item : safeSubject(item, telemetry)).join(", ");
}

function claimSupport(claim: GroundedClaimV2) {
  return [
    ...claim.supporting_event_ids.map((item) => `event ${item}`),
    ...claim.supporting_context_ids.map((item) => formatWords(item)),
    ...claim.supporting_mission_candidate_ids.map((item) => `mission rule ${formatWords(item)}`),
  ];
}

export function StudioDashboard({ telemetry }: { telemetry: RawTelemetryBatchV2 }) {
  const { flow } = usePlayerFlow();
  const [health, setHealth] = useState<HealthState>({
    status: "checking",
    provider: "Checking",
    model: "Checking",
    message: "Checking the configured MemoryOS backend.",
  });
  const [result, setResult] = useState<StudioInterpretDeliveryResultV2 | null>(null);
  const [runSource, setRunSource] = useState<RunSource>("waiting");
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [resultTab, setResultTab] = useState<ResultTab>("summary");
  const [latestDecisionTrace, setLatestDecisionTrace] = useState<StudioInterpretationTraceV2 | null>(null);
  const runSequence = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

  const eligiblePlayers = useMemo(() => eligibleDisplayPlayers(telemetry), [telemetry]);
  const invitationEligiblePlayers = useMemo(() => eligibleInvitationPlayers(telemetry), [telemetry]);
  const events = useMemo(() => telemetry.matches.flatMap((match) =>
    match.events.map((event) => ({ ...event, match_id: match.match_id }))), [telemetry]);
  const pending = result?.status === "pending_player_decision" ? result : null;
  const effectiveTrace = latestDecisionTrace ?? result?.studio_trace ?? null;
  const missionAffordances = effectiveTrace?.mission_affordances ?? [];
  const missionSelection = effectiveTrace?.mission_selection ?? null;
  const activePlayerCount = effectiveTrace?.active_player_count
    ?? telemetry.current_context.active_player_ids.length;
  const invitationEligibleCount = effectiveTrace?.invitation_eligible_count
    ?? invitationEligiblePlayers.length;
  const traceByStage = new Map(effectiveTrace?.stages.map((stage) => [stage.stage, stage]) ?? []);
  const sessionDecision = flow.declineReason ? "declined" : flow.missionAccepted ? "accepted" : null;
  const sourceQualityFlag = effectiveTrace?.source_quality_flag === true || flow.declineReason === "details_wrong";
  const contentOrigin = result?.metadata.content_origin
    ?? (pending?.metadata.mode === "live_ai"
      ? "live_ai_validated"
      : pending
        ? "deterministic_studio_sample"
        : null);
  const connectionLabel = health.status === "checking"
    ? "Provider check"
    : health.status === "ok"
      ? "Backend connected"
      : health.status === "sample"
        ? "Studio demo available"
        : "Backend unavailable";

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/studio/health", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json() as Record<string, unknown>;
        setHealth({
          status: response.ok
            ? (payload.mode === "sample" ? "sample" : "ok")
            : "error",
          provider: typeof payload.provider === "string" ? payload.provider : "Unavailable",
          model: typeof payload.model === "string" ? payload.model : "Unavailable",
          message: typeof payload.message === "string" ? payload.message : "The provider state could not be read.",
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setHealth({
            status: "error",
            provider: "Unavailable",
            model: "Unavailable",
            message: "The provider health check could not be completed.",
          });
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => () => {
    runSequence.current += 1;
    activeRequest.current?.abort();
  }, []);

  useEffect(() => {
    if (!flow.delivery?.delivery_id || (!flow.declineReason && !flow.missionAccepted)) return;
    const controller = new AbortController();
    void fetch("/api/studio/delivery-trace", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ delivery_id: flow.delivery.delivery_id }),
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) return;
      const trace = parseStudioTraceV2(await response.json());
      if (trace) setLatestDecisionTrace(trace);
    }).catch(() => undefined);
    return () => controller.abort();
  }, [flow.declineReason, flow.delivery?.delivery_id, flow.missionAccepted]);

  async function runInterpretation() {
    const requestId = ++runSequence.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const startedAt = performance.now();
    setRunning(true);
    setResult(null);
    setRunError(null);
    setFallbackReason(null);
    setRunSource("waiting");

    try {
      const response = await fetch("/api/studio/interpret", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ request_id: telemetry.request_id }),
        signal: controller.signal,
      });
      const payload: unknown = await response.json();
      if (controller.signal.aborted || requestId !== runSequence.current) return;
      const parsed = parseStudioInterpretDeliveryV2(payload);
      if (!response.ok || !parsed) {
        const message = payload && typeof payload === "object" && "message" in payload && typeof payload.message === "string"
          ? payload.message
          : "The v2 interpretation run stopped safely.";
        throw new Error(message);
      }
      setRunSource(response.headers.get("x-memoryos-mode") === "sample" ? "sample" : "live");
      setFallbackReason(response.headers.get("x-memoryos-fallback"));
      setResult(parsed);
      setResultTab("summary");
    } catch (error) {
      if (controller.signal.aborted || requestId !== runSequence.current) return;
      setRunError(error instanceof Error ? error.message : "The v2 interpretation run stopped safely.");
    } finally {
      if (!controller.signal.aborted && requestId === runSequence.current) {
        setDurationMs(performance.now() - startedAt);
        setRunning(false);
      }
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }

  const runtimeTitle = result?.status === "not_generated"
    ? "AI abstained from forcing a memory"
    : runSource === "sample"
    ? "Deterministic Studio demonstration"
    : pending?.metadata.mode === "live_ai"
      ? "Live AI memory interpretation"
      : "Ready for a v2 interpretation audit";
  const runtimeDetail = result?.status === "not_generated"
    ? "The supplied evidence did not support a meaningful episode, so no player-facing memory or mission was created."
    : runSource === "sample"
    ? "A clearly labelled saved result demonstrates the same privacy, claim, and mission-rule trace. It is never used in the player experience."
    : "Player delivery is allowed only after one AI proposal passes deterministic evidence and safety validation.";

  return (
    <main className="studio-app">
      <a className="skip-link" href="#studio-workspace">Skip to interpretation workspace</a>
      <p className="sr-only" aria-live="polite">
        {running ? "Memory interpretation audit in progress." : runError ? `Audit error: ${runError}` : result ? `Audit finished with ${result.status}.` : "MemoryOS Studio ready."}
      </p>

      <header className="studio-topbar">
        <Link className="studio-brand" href="/studio" aria-label="MemoryOS Studio home">
          <span className="studio-brand-mark">M</span>
          <span><strong>MemoryOS</strong><small>Studio</small></span>
        </Link>
        <div className="studio-topbar-actions">
          <span className={`studio-connection studio-connection-${health.status === "checking" ? "sample" : health.status}`}>
            <i aria-hidden="true" />{connectionLabel}
          </span>
          <Link className="studio-player-link" href="/">Open player view</Link>
        </div>
      </header>

      <section className="studio-hero" aria-labelledby="studio-title">
        <div>
          <p className="studio-kicker">Developer observability</p>
          <h1 id="studio-title">AI-grounded memory trace</h1>
          <p className="studio-intro">
            Inspect how sparse telemetry becomes one proposed memory, how every material claim is checked,
            and why only a fully validated delivery may reach the player.
          </p>
        </div>
        <dl className="studio-hero-metrics">
          <div><dt>Provider</dt><dd>{pending?.metadata.provider ?? health.provider}</dd></div>
          <div><dt>Model</dt><dd>{pending?.metadata.model ?? health.model}</dd></div>
          <div><dt>Prompt</dt><dd>{result?.metadata.prompt_version ?? "--"}</dd></div>
          <div><dt>End-to-end</dt><dd>{durationMs == null ? "--" : `${Math.round(durationMs)} ms`}</dd></div>
        </dl>
      </section>

      <section className={`studio-runtime-banner runtime-${runSource === "sample" ? "sample" : "live"}`} aria-label="Active generation mode" aria-live="polite">
        <div className="studio-runtime-copy">
          <span>{runSource === "sample" ? "Studio demo only" : "Player-safe v2 path"}</span>
          <strong>{runtimeTitle}</strong>
          <p>{runtimeDetail}</p>
          {fallbackReason ? <small>Demo reason: {formatWords(fallbackReason)}</small> : null}
          {sessionDecision ? (
            <small>
              Latest player decision: {formatWords(sessionDecision)}.
              {sourceQualityFlag
                ? " Details-wrong source-quality flag recorded for operations."
                : " No source-quality dispute was recorded."}
            </small>
          ) : null}
        </div>
        <dl className="studio-runtime-metrics">
          <div><dt>Matches</dt><dd>{telemetry.matches.length}</dd></div>
          <div><dt>Raw events</dt><dd>{events.length}</dd></div>
          <div><dt>Active / invite-ready</dt><dd>{activePlayerCount} / {invitationEligibleCount}</dd></div>
          <div><dt>Validation</dt><dd>{result ? (result.validation.passed ? "Passed" : "Withheld") : "--"}</dd></div>
        </dl>
      </section>

      <section className="studio-boundary" aria-label="MemoryOS responsibility boundary">
        {stageDefinitions.map((stage, index) => (
          <div key={stage.id} style={{ display: "contents" }}>
            {index > 0 ? <div className="studio-boundary-arrow" aria-hidden="true">-&gt;</div> : null}
            <div className={`studio-boundary-step boundary-${index === 1 ? "ai" : index === 3 ? "output" : "input"}`}>
              <span>{stage.owner}</span>
              <strong>{stage.label}</strong>
              <small>{index === 0 ? "Normalize + consent" : index === 1 ? "Select + author" : index === 2 ? "Ground + verify" : "Accept or decline"}</small>
            </div>
          </div>
        ))}
      </section>

      <section className="studio-workspace" id="studio-workspace">
        <section className="studio-panel studio-input-panel" aria-labelledby="studio-input-title">
          <div className="studio-panel-heading">
            <div><p className="studio-panel-index">Input</p><h2 id="studio-input-title">Sanitized telemetry summary</h2></div>
            <span className="studio-validity valid">Raw v2</span>
          </div>
          <div className="studio-input-stats">
            <span><strong>{telemetry.matches.length}</strong> matches</span>
            <span><strong>{events.length}</strong> events</span>
            <span><strong>{eligiblePlayers.length}</strong> consent-safe</span>
            <span><strong>{activePlayerCount}/{invitationEligibleCount}</strong> active / invite-ready</span>
          </div>
          <p className="studio-panel-note">
            The browser receives a consent-safe projection. Opted-out stable IDs, raw prompts, and provider secrets are not exposed here.
          </p>
          <div className="studio-grounding-list">
            {telemetry.matches.map((match) => (
              <article key={match.match_id}>
                <div><span>{formatWords(match.game)}</span><strong>{match.map_name ?? formatWords(match.mode)}</strong></div>
                <p>{match.events.length} sparse events / placement {match.placement ? `#${match.placement}` : "not supplied"}</p>
                <dl>
                  <div><dt>Mode</dt><dd>{formatWords(match.mode)}</dd></div>
                  <div><dt>Started</dt><dd>{new Date(match.started_at).toLocaleDateString("en-SG")}</dd></div>
                </dl>
              </article>
            ))}
          </div>
          <details className="studio-stage-preview studio-event-disclosure">
            <summary>Inspect consent-safe event vocabulary</summary>
            <div className="studio-grounding-list">
              {events.map((event) => (
                <article key={event.event_id}>
                  <div><span>{formatClock(event.timestamp_seconds)}</span><strong>{formatWords(event.provider_event_type)}</strong></div>
                  <p>{event.location ?? "No location supplied"}</p>
                </article>
              ))}
            </div>
          </details>
          <div className="studio-input-actions">
            <button className="studio-run-button" type="button" onClick={() => void runInterpretation()} disabled={running}>
              {running ? "Interpreting telemetry..." : "Run v2 interpretation audit"}
            </button>
          </div>
        </section>

        <section className="studio-panel studio-trace-panel" aria-labelledby="studio-trace-title">
          <div className="studio-panel-heading studio-trace-heading">
            <div><p className="studio-panel-index">Judge trace</p><h2 id="studio-trace-title">Responsibility path</h2></div>
            <span className={`studio-run-source source-${runSource}`}>{runSource === "waiting" ? "Not run" : runSource === "sample" ? "Demo" : "Live"}</span>
          </div>
          <p className="studio-panel-note">This is an auditable stage record, not hidden model reasoning.</p>
          <ol className="studio-stage-list">
            {stageDefinitions.map((definition) => {
              const trace = traceByStage.get(definition.id);
              const status = trace?.status ?? (running ? "pending" : "idle");
              return (
                <li key={definition.id}>
                  <article className={`studio-stage stage-${status}`}>
                    <div className="studio-stage-number">{definition.number}</div>
                    <div className="studio-stage-copy">
                      <div className="studio-stage-title-row">
                        <h3>{definition.label}</h3>
                        <span className={`studio-owner owner-${definition.owner === "Memory intelligence" ? "live-ai" : "deterministic"}`}>{definition.owner}</span>
                      </div>
                      <p>{definition.description}</p>
                      {trace ? <small>{trace.summary}</small> : null}
                      {trace?.issue_codes.length ? (
                        <ul className="studio-issue-list">
                          {trace.issue_codes.map((code) => <li key={code}>{formatWords(code)}</li>)}
                        </ul>
                      ) : null}
                    </div>
                    <span className="studio-stage-status">{status}</span>
                  </article>
                </li>
              );
            })}
          </ol>
          {runError ? <div className="studio-error-card" role="alert"><strong>Run withheld</strong><p>{runError}</p></div> : null}
        </section>

        <section className="studio-panel studio-output-panel" aria-labelledby="studio-output-title">
          <div className="studio-panel-heading">
            <div><p className="studio-panel-index">Validated output</p><h2 id="studio-output-title">Delivery inspector</h2></div>
            <span className={`studio-result-status result-${result?.status ?? "waiting"}`}>{result ? formatWords(result.status) : "No result"}</span>
          </div>
          <div className="studio-output-metrics">
            <div><span>Selected events</span><strong>{pending?.memory.selected_event_ids.length ?? "--"}</strong></div>
            <div><span>Affordances</span><strong>{result ? missionAffordances.length : "--"}</strong></div>
            <div><span>Content origin</span><strong>{contentOrigin ? formatWords(contentOrigin) : "--"}</strong></div>
            <div><span>Correction used</span><strong>{result ? (result.validation.correction_attempted ? "Yes" : "No") : "--"}</strong></div>
          </div>
          <div className="studio-tabs" role="tablist" aria-label="Delivery inspector views">
            {(["summary", "grounding", "mission"] as ResultTab[]).map((tab) => (
              <button key={tab} type="button" role="tab" aria-selected={resultTab === tab} onClick={() => setResultTab(tab)}>{formatWords(tab)}</button>
            ))}
          </div>

          {!result ? (
            <div className="studio-empty-output"><span aria-hidden="true">M</span><h3>Run the telemetry audit.</h3><p>Only a validated proposal will appear. Rejected prose is always withheld.</p></div>
          ) : result.status === "rejected" ? (
            <div className="studio-result-stack">
              <article className="studio-result-card result-validation">
                <p>Fail-closed result</p><h3>Generated proposal withheld</h3>
                <span>No title, summary, perspective, or mission is available to this interface.</span>
                <ul className="studio-issue-list">
                  {[...result.reason_codes, ...result.validation.issues.map((issue) => issue.code)].map((code, index) => <li key={`${code}-${index}`}>{formatWords(code)}</li>)}
                </ul>
              </article>
            </div>
          ) : result.status === "not_generated" ? (
            <div className="studio-result-stack">
              <article className="studio-result-card result-validation">
                <p>Valid AI abstention</p><h3>No memory generated</h3>
                <span>The evidence did not support a meaningful squad episode. No player-facing title, perspective, or mission was created.</span>
                <ul className="studio-issue-list">
                  {result.reason_codes.map((code) => <li key={code}>{formatWords(code)}</li>)}
                </ul>
              </article>
            </div>
          ) : resultTab === "summary" ? (
            <div className="studio-result-stack">
              <article className="studio-result-card result-memory"><p>AI-prepared memory</p><h3>{result.memory.title}</h3><span>{formatWords(result.memory.memory_type)} / {result.memory.selected_event_ids.length} evidence events</span><blockquote>{result.memory.summary}</blockquote></article>
              <article className="studio-result-card"><p>Player perspectives</p><h3>{result.player_perspectives.length} consent-safe views</h3><ul className="studio-perspective-list">{result.player_perspectives.map((perspective) => <li key={perspective.player_id}><strong>{perspective.display_name}</strong><span>{perspective.message}</span></li>)}</ul></article>
              <article className="studio-result-card result-validation"><p>Player decision</p><h3>{sessionDecision ? formatWords(sessionDecision) : "Awaiting player"}</h3><span>{sourceQualityFlag ? "Details-wrong source-quality flag recorded for operations." : "Relevance feedback remains separate from factual source disputes."}</span></article>
            </div>
          ) : resultTab === "grounding" ? (
            <div className="studio-grounding-list">
              {result.grounded_claims.map((claim) => (
                <article key={claim.claim_id}>
                  <div><span>{formatWords(claim.output_section)}</span><strong>{safeSubject(claim.subject_id, telemetry)} / {formatWords(claim.predicate)}</strong></div>
                  <p>{claimSupport(claim).join(" / ")}</p>
                  <dl><div><dt>Target</dt><dd>{claim.target_id ? safeSubject(claim.target_id, telemetry) : "--"}</dd></div><div><dt>Location</dt><dd>{claim.location ?? "--"}</dd></div></dl>
                </article>
              ))}
            </div>
          ) : (
            <div className="studio-result-stack">
              <article className="studio-result-card result-validation">
                <p>AI mission selection</p>
                <h3>{missionSelection ? formatWords(missionSelection.selected_family) : formatWords(result.next_chapter.family ?? "reunion")}</h3>
                <span>{missionSelection
                  ? `${missionSelection.ranked_affordance_ids.length} ranked / ${formatWords(missionSelection.reason_codes.join(", "))}`
                  : "Legacy v2 delivery: mission selection metadata was not supplied."}</span>
              </article>
              {missionAffordances.map((affordance) => (
                <article className="studio-result-card" key={affordance.affordance_id}>
                  <p>{missionSelection?.selected_affordance_id === affordance.affordance_id ? "Selected affordance" : "Offered affordance"}</p>
                  <h3>{formatWords(affordance.family)}</h3>
                  <span>{affordance.objective_candidate_ids.length} compiled rules / {affordance.source_event_ids.length + affordance.source_match_ids.length + affordance.source_context_ids.length} source references</span>
                </article>
              ))}
              <article className="studio-result-card result-quest"><p>AI-authored Next Chapter</p><h3>{result.next_chapter.title}</h3><span>{result.next_chapter.mission}</span></article>
              {result.next_chapter.objectives.map((objective) => (
                <article className="studio-result-card" key={objective.objective_id}>
                  <p>Backend-owned verification rule</p><h3>{objective.description}</h3>
                  <span>{formatWords(objective.verification.metric)} / {formatWords(objective.verification.operator)} / {safeRuleTarget(objective.verification.target, telemetry)}</span>
                </article>
              ))}
              <article className="studio-result-card">
                <p>Post-accept demonstration</p>
                <h3>Scripted prototype sequence</h3>
                <span>Invites sent → squad joins → game starts → selected mission completes. No live post-match telemetry is claimed.</span>
              </article>
            </div>
          )}
        </section>
      </section>

      <footer className="studio-footer">
        <div><strong>Safe inspection boundary</strong><p>Studio shows sanitized input summaries, structured claims, issue codes, and verification rules. It never shows opted-out identities, prompts, secrets, or rejected prose.</p></div>
        <div><strong>{health.message}</strong><p>Feedback is reviewed offline. It never rewrites prompts, models, or trusted telemetry automatically.</p></div>
      </footer>
    </main>
  );
}
