"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  GroundedClaimV2,
  StudioInterpretDeliveryResultV2,
  StudioInterpretationTraceV2,
} from "@/lib/ai-memory-contract";
import { parseStudioTraceV2 } from "@/lib/ai-memory-contract";
import {
  parseStudioScenarioCatalog,
  parseStudioScenarioPreparation,
  parseStudioScenarioRun,
  sameStudioScenarioVersion,
  studioScenarioActual,
} from "@/lib/studio-scenarios";
import type {
  StudioScenarioCatalogV2,
  StudioScenarioPreparationV2,
  StudioScenarioRunV2,
} from "@/lib/studio-scenarios";
import {
  parseSafeStudioProviderFailure,
  studioProviderFailureMessage,
} from "@/lib/studio-provider-error";
import {
  studioInitialResultTab,
  studioInspectionDecision,
} from "@/lib/studio-inspection-decision-core.mjs";
import { usePlayerFlow } from "../player-flow-provider";

type ResultTab = "summary" | "grounding" | "mission";
type RunSource = "waiting" | "live" | "saved_replay";
type HealthState = {
  status: "checking" | "ok" | "sample" | "error";
  provider: string;
  model: string;
  message: string;
};
type StudioValidationIssue = { code: string; message?: string };
type StudioIssueDisplay = { code: string; message: string; sections: string[] };
type StudioRunFailure = { code: string; message: string; retryable: boolean };

const safeStudioIssueMessages = new Map<string, string>([
  ["action_role_mismatch", "A described player action did not match the consent-safe telemetry role."],
  ["claim_evidence_outside_episode", "A claim referenced evidence outside the selected episode."],
  ["invented_mission_affordance", "The selected mission option was not offered by the backend."],
  ["mission_affordance_ranking_invalid", "The mission ranking did not match the offered options."],
  ["mission_copy_compilation_failed", "The backend could not safely compile the selected mission requirements."],
  ["privacy_identity_leak", "The proposal did not pass the privacy boundary."],
  ["provider_input_too_large", "The consent-safe provider input exceeded its configured limit."],
  ["secret_exposure", "The proposal did not pass the secret-safety boundary."],
  ["unsafe_generated_content", "The proposal did not pass the content-safety boundary."],
  ["unsupported_categorical_detail", "A described detail was not supported by the cited telemetry."],
]);

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
    description: "Chooses one connected episode and writes the memory, perspectives, mission title, and story bridge.",
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

function safeIssueSection(message?: string) {
  const rawSection = message?.match(/^Section ([A-Za-z0-9:_-]{1,128})\s/)?.[1]?.toLowerCase();
  if (!rawSection) return null;
  if (rawSection.startsWith("perspective:")) return "Player perspective";
  if (rawSection.startsWith("objective:")) return "Mission objective";
  return ({
    title: "Title",
    notification_teaser: "Notification teaser",
    summary: "Summary",
    why_this_matters_now: "Why this matters now",
    mission: "Mission",
  } as Record<string, string>)[rawSection] ?? null;
}

function studioIssueItems(reasonCodes: string[], validationIssues: StudioValidationIssue[]) {
  const sectionsByCode = new Map<string, Set<string>>();
  for (const issue of validationIssues) {
    const code = issue.code.trim();
    if (!code) continue;
    const sections = sectionsByCode.get(code) ?? new Set<string>();
    const section = safeIssueSection(issue.message);
    if (section) sections.add(section);
    sectionsByCode.set(code, sections);
  }
  for (const rawCode of reasonCodes) {
    const code = rawCode.trim();
    if (code && !sectionsByCode.has(code)) sectionsByCode.set(code, new Set());
  }
  return [...sectionsByCode].map<StudioIssueDisplay>(([code, sections]) => ({
    code,
    sections: [...sections],
    message: safeStudioIssueMessages.get(code) ?? "Validation stopped this proposal before delivery.",
  }));
}

function safeSubject(subjectId: string, result: StudioInterpretDeliveryResultV2) {
  if (subjectId === "squad") return "Eligible squad";
  if (subjectId.startsWith("anonymous:")) return "Anonymous squadmate";
  if (result.status !== "pending_player_decision") return "Consent-safe subject";
  return result.player_perspectives.find((player) => player.player_id === subjectId)?.display_name
    ?? "Consent-safe subject";
}

function safeRuleTarget(
  target: string | number | boolean | string[],
  result: StudioInterpretDeliveryResultV2,
) {
  if (!Array.isArray(target)) return String(target);
  return target.map((item) => safeSubject(item, result)).join(", ");
}

function claimSupport(claim: GroundedClaimV2) {
  return [
    ...claim.supporting_event_ids.map((item) => `event ${item}`),
    ...claim.supporting_context_ids.map((item) => formatWords(item)),
    ...claim.supporting_mission_candidate_ids.map((item) => `mission rule ${formatWords(item)}`),
  ];
}

function safeResponseMessage(value: unknown, fallback: string) {
  return value && typeof value === "object" && !Array.isArray(value)
    && "message" in value && typeof value.message === "string"
    ? value.message
    : fallback;
}

function safeStudioRunFailure(value: unknown): StudioRunFailure {
  const providerFailure = parseSafeStudioProviderFailure(value);
  if (providerFailure) {
    return {
      code: providerFailure.code,
      message: studioProviderFailureMessage(providerFailure.code),
      retryable: providerFailure.retryable,
    };
  }
  return {
    code: "studio_live_run_withheld",
    message: "The live interpretation stopped safely. No generated artifacts were returned.",
    retryable: false,
  };
}

export function StudioDashboard() {
  const { flow } = usePlayerFlow();
  const [health, setHealth] = useState<HealthState>({
    status: "checking",
    provider: "Checking",
    model: "Checking",
    message: "Checking the configured MemoryOS backend.",
  });
  const [catalog, setCatalog] = useState<StudioScenarioCatalogV2 | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("");
  const [preparation, setPreparation] = useState<StudioScenarioPreparationV2 | null>(null);
  const [preparationError, setPreparationError] = useState<string | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [run, setRun] = useState<StudioScenarioRunV2 | null>(null);
  const [runSource, setRunSource] = useState<RunSource>("waiting");
  const [runError, setRunError] = useState<StudioRunFailure | null>(null);
  const [running, setRunning] = useState(false);
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [resultTab, setResultTab] = useState<ResultTab>("summary");
  const [playerTraceRecord, setPlayerTraceRecord] = useState<{
    deliveryId: string;
    trace: StudioInterpretationTraceV2;
  } | null>(null);
  const preparationSequence = useRef(0);
  const runSequence = useRef(0);
  const preparationRequest = useRef<AbortController | null>(null);
  const runRequest = useRef<AbortController | null>(null);
  const runningLock = useRef(false);

  const selectedScenario = useMemo(
    () => catalog?.scenarios.find((scenario) => scenario.scenario_id === selectedScenarioId) ?? null,
    [catalog, selectedScenarioId],
  );
  const result = run?.result ?? null;
  const pending = result?.status === "pending_player_decision" ? result : null;
  const studioDecision = studioInspectionDecision(run?.content_origin ?? null, result?.status ?? null);
  const acceptedForInspection = studioDecision === "accepted";
  const effectiveTrace = result?.studio_trace ?? null;
  const missionAffordances = effectiveTrace?.mission_affordances
    ?? preparation?.mission_affordances
    ?? [];
  const missionSelection = effectiveTrace?.mission_selection ?? null;
  const traceByStage = new Map(effectiveTrace?.stages.map((stage) => [stage.stage, stage]) ?? []);
  const activePlayerCount = preparation?.telemetry_summary.active_player_count ?? 0;
  const invitationEligibleCount = preparation?.telemetry_summary.invitation_eligible_count ?? 0;
  const rejectedIssues = result?.status === "rejected"
    ? studioIssueItems(result.reason_codes, result.validation.issues)
    : [];
  const connectionLabel = health.status === "checking"
    ? "Provider check"
    : health.status === "ok"
      ? "Backend configured"
      : health.status === "sample"
        ? "Backend not configured"
        : "Backend unavailable";
  const preparationCurrent = Boolean(
    selectedScenario
    && preparation
    && sameStudioScenarioVersion(selectedScenario, preparation.scenario),
  );
  const canRun = preparationCurrent && preparation?.status === "ready" && !preparing && !running;
  const actual = result ? studioScenarioActual(result) : null;
  const statusMatches = Boolean(selectedScenario && actual
    && selectedScenario.expected_status === actual.status);
  const familyMatches = Boolean(selectedScenario && actual
    && selectedScenario.expected_mission_family === actual.mission_family);
  const expectationMatches = Boolean(actual && statusMatches && familyMatches);
  const latestPlayerTrace = playerTraceRecord
    && playerTraceRecord.deliveryId === flow.delivery?.delivery_id
    ? playerTraceRecord.trace
    : null;
  const playerDecision = flow.declineReason
    ? "Declined"
    : flow.missionAccepted
      ? "Accepted"
      : flow.delivery
        ? "Awaiting decision"
        : "No player delivery this session";
  const playerSourceQualityFlag = latestPlayerTrace?.source_quality_flag === true
    || flow.declineReason === "details_wrong";

  useEffect(() => {
    const healthController = new AbortController();
    const catalogController = new AbortController();
    void fetch("/api/studio/health", { cache: "no-store", signal: healthController.signal })
      .then(async (response) => {
        const payload = await response.json() as Record<string, unknown>;
        setHealth({
          status: response.ok ? (payload.mode === "sample" ? "sample" : "ok") : "error",
          provider: typeof payload.provider === "string" ? payload.provider : "Unavailable",
          model: typeof payload.model === "string" ? payload.model : "Unavailable",
          message: typeof payload.message === "string" ? payload.message : "The backend state could not be read.",
        });
      })
      .catch(() => {
        if (!healthController.signal.aborted) {
          setHealth({
            status: "error",
            provider: "Unavailable",
            model: "Unavailable",
            message: "The backend health check could not be completed.",
          });
        }
      });
    void fetch("/api/studio/scenarios", { cache: "no-store", signal: catalogController.signal })
      .then(async (response) => {
        const payload: unknown = await response.json();
        const parsed = parseStudioScenarioCatalog(payload);
        if (!response.ok || !parsed) {
          throw new Error(safeResponseMessage(payload, "The versioned Studio scenario catalog is unavailable."));
        }
        setCatalog(parsed);
        setSelectedScenarioId((current) => current || parsed.scenarios[0].scenario_id);
        setCatalogError(null);
      })
      .catch((error) => {
        if (!catalogController.signal.aborted) {
          setCatalogError(error instanceof Error ? error.message : "The Studio scenario catalog is unavailable.");
        }
      });
    return () => {
      healthController.abort();
      catalogController.abort();
    };
  }, []);

  useEffect(() => () => {
    preparationSequence.current += 1;
    runSequence.current += 1;
    preparationRequest.current?.abort();
    runRequest.current?.abort();
  }, []);

  useEffect(() => {
    if (!flow.delivery?.delivery_id) return;
    const deliveryId = flow.delivery.delivery_id;
    const controller = new AbortController();
    void fetch("/api/studio/delivery-trace", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ delivery_id: deliveryId }),
      signal: controller.signal,
    }).then(async (response) => {
      if (!response.ok) return;
      const trace = parseStudioTraceV2(await response.json());
      if (trace) setPlayerTraceRecord({ deliveryId, trace });
    }).catch(() => undefined);
    return () => controller.abort();
  }, [flow.delivery?.delivery_id, flow.declineReason, flow.missionAccepted]);

  function selectScenario(scenarioId: string) {
    if (runningLock.current || preparing) return;
    preparationSequence.current += 1;
    preparationRequest.current?.abort();
    setSelectedScenarioId(scenarioId);
    setPreparation(null);
    setPreparationError(null);
    setRun(null);
    setRunError(null);
    setRunSource("waiting");
    setDurationMs(null);
  }

  async function prepareScenario() {
    if (!selectedScenario || preparationRequest.current || runningLock.current) return;
    const sequence = ++preparationSequence.current;
    const controller = new AbortController();
    preparationRequest.current = controller;
    setPreparing(true);
    setPreparationError(null);
    setPreparation(null);
    setRun(null);
    setRunError(null);
    setRunSource("waiting");
    setDurationMs(null);
    try {
      const response = await fetch("/api/studio/scenarios/prepare", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ scenario: selectedScenario }),
        signal: controller.signal,
      });
      const payload: unknown = await response.json();
      if (controller.signal.aborted || sequence !== preparationSequence.current) return;
      const parsed = parseStudioScenarioPreparation(payload);
      if (!response.ok || !parsed || !sameStudioScenarioVersion(selectedScenario, parsed.scenario)) {
        throw new Error(safeResponseMessage(payload, "Deterministic preparation stopped safely."));
      }
      setPreparation(parsed);
    } catch (error) {
      if (!controller.signal.aborted && sequence === preparationSequence.current) {
        setPreparationError(error instanceof Error ? error.message : "Deterministic preparation stopped safely.");
      }
    } finally {
      if (!controller.signal.aborted && sequence === preparationSequence.current) setPreparing(false);
      if (preparationRequest.current === controller) preparationRequest.current = null;
    }
  }

  async function runInterpretation() {
    if (!selectedScenario || !canRun || runningLock.current) return;
    runningLock.current = true;
    const sequence = ++runSequence.current;
    const controller = new AbortController();
    runRequest.current = controller;
    const startedAt = performance.now();
    setRunning(true);
    setRun(null);
    setRunError(null);
    setRunSource("waiting");
    try {
      const response = await fetch("/api/studio/scenarios/interpret", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ scenario: selectedScenario }),
        signal: controller.signal,
      });
      const payload: unknown = await response.json();
      if (controller.signal.aborted || sequence !== runSequence.current) return;
      if (!response.ok) {
        setRunError(safeStudioRunFailure(payload));
        return;
      }
      const parsed = parseStudioScenarioRun(payload);
      if (!parsed || !sameStudioScenarioVersion(selectedScenario, parsed.scenario)) {
        throw new Error("The live interpretation stopped safely. No generated artifacts were returned.");
      }
      if (preparation?.telemetry_summary.request_id !== parsed.result.request_id) {
        throw new Error("The live result did not match the deterministically prepared request.");
      }
      setRun(parsed);
      setRunSource(parsed.content_origin === "saved_live_replay" ? "saved_replay" : "live");
      setResultTab(studioInitialResultTab(parsed.content_origin, parsed.result.status));
    } catch (error) {
      if (!controller.signal.aborted && sequence === runSequence.current) {
        setRunError({
          code: "studio_live_run_withheld",
          message: error instanceof Error
            ? error.message
            : "The live interpretation stopped safely. No generated artifacts were returned.",
          retryable: false,
        });
      }
    } finally {
      if (!controller.signal.aborted && sequence === runSequence.current) {
        setDurationMs(performance.now() - startedAt);
        setRunning(false);
      }
      runningLock.current = false;
      if (runRequest.current === controller) runRequest.current = null;
    }
  }

  const runtimeTitle = runSource === "saved_replay"
    ? "Saved live replay — not a fresh AI run"
    : result?.status === "not_generated"
      ? "AI abstained from forcing a memory"
      : pending
        ? "Live AI memory interpretation"
        : preparationCurrent
          ? "Deterministic checkpoint complete"
          : "Select and prepare a Studio scenario";
  const runtimeDetail = runSource === "saved_replay"
    ? "This reviewed capture matched the exact scenario fixture hash and schema version. It cannot enter the player decision or continuation flow."
    : result?.status === "not_generated"
      ? "The supplied evidence did not support a meaningful episode, so no player-facing memory or mission was created."
      : pending
        ? "Player delivery is allowed only after the AI proposal passes deterministic evidence and safety validation."
        : "Preparation is local and deterministic. A live provider is contacted only when you press the quota-labelled run button.";

  return (
    <main className="studio-app">
      <a className="skip-link" href="#studio-workspace">Skip to interpretation workspace</a>
      <p className="sr-only" aria-live="polite">
        {running
          ? "Live memory interpretation in progress."
          : preparing
            ? "Deterministic scenario preparation in progress."
            : runError
              ? `Audit error: ${runError.message}. Safe code: ${runError.code}.`
              : result
                ? `Audit finished with ${result.status}.`
                : "MemoryOS Studio ready."}
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
            Compare five versioned telemetry scenarios, inspect their deterministic preparation,
            then deliberately start one bounded live interpretation.
          </p>
        </div>
        <dl className="studio-hero-metrics">
          <div><dt>Provider</dt><dd>{pending?.metadata.provider ?? health.provider}</dd></div>
          <div><dt>Model</dt><dd>{pending?.metadata.model ?? health.model}</dd></div>
          <div><dt>Prompt</dt><dd>{result?.metadata.prompt_version ?? "--"}</dd></div>
          <div><dt>End-to-end</dt><dd>{durationMs == null ? "--" : `${Math.round(durationMs)} ms`}</dd></div>
        </dl>
      </section>

      <section className={`studio-runtime-banner runtime-${runSource === "saved_replay" ? "replay" : "live-ai"}`} aria-label="Active generation mode" aria-live="polite">
        <div className="studio-runtime-copy">
          <span>{runSource === "saved_replay" ? "Studio replay only" : "Versioned Studio checkpoint"}</span>
          <strong>{runtimeTitle}</strong>
          <p>{runtimeDetail}</p>
          {run?.replay_provenance ? (
            <small>
              Captured {new Date(run.replay_provenance.captured_at).toLocaleString("en-SG")} / {run.replay_provenance.provider} / {run.replay_provenance.model} / {run.replay_provenance.prompt_version}
            </small>
          ) : null}
        </div>
        <dl className="studio-runtime-metrics">
          <div><dt>Matches</dt><dd>{preparation?.telemetry_summary.match_count ?? "--"}</dd></div>
          <div><dt>Raw events</dt><dd>{preparation?.telemetry_summary.raw_event_count ?? "--"}</dd></div>
          <div><dt>Active / invite-ready</dt><dd>{preparation ? `${activePlayerCount} / ${invitationEligibleCount}` : "--"}</dd></div>
          <div><dt>Validation</dt><dd>{result ? (result.validation.passed ? "Passed" : "Withheld") : "--"}</dd></div>
        </dl>
      </section>

      <section className="studio-player-session-status" aria-label="Player app state in this tab">
        <div><span>Player app state in this tab</span><strong>{playerDecision}</strong></div>
        <p>
          {playerSourceQualityFlag
            ? "Details-wrong source-quality flag recorded for operations."
            : "No source-quality dispute is recorded for the latest player delivery."}
          {runSource === "saved_replay" ? " This status is separate from the inspection-only replay." : ""}
        </p>
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
            <div><p className="studio-panel-index">Scenario</p><h2 id="studio-input-title">Deterministic checkpoint</h2></div>
            <span className={`studio-validity ${preparationCurrent && preparation?.status === "ready" ? "valid" : ""}`}>
              {preparing ? "Preparing" : preparationCurrent ? formatWords(preparation!.status) : "Not prepared"}
            </span>
          </div>
          <div className="studio-scenario-picker">
            <label htmlFor="studio-scenario">Evaluation scenario</label>
            <select
              id="studio-scenario"
              value={selectedScenarioId}
              disabled={running || preparing || !catalog}
              onChange={(event) => selectScenario(event.target.value)}
            >
              {!catalog ? <option value="">Loading scenario catalog...</option> : null}
              {catalog?.scenarios.map((scenario) => (
                <option key={scenario.scenario_id} value={scenario.scenario_id}>{scenario.title}</option>
              ))}
            </select>
            <p>{selectedScenario?.purpose ?? catalogError ?? "Choose one registered synthetic telemetry scenario."}</p>
          </div>
          {catalogError ? <div className="studio-error-card" role="alert"><strong>Scenario catalog unavailable</strong><p>{catalogError}</p></div> : null}
          {preparation ? (
            <>
              <div className="studio-input-stats">
                <span><strong>{preparation.telemetry_summary.match_count}</strong> matches</span>
                <span><strong>{preparation.telemetry_summary.raw_event_count}</strong> events</span>
                <span><strong>{preparation.telemetry_summary.consent_safe_player_count}</strong> consent-safe</span>
                <span><strong>{activePlayerCount}/{invitationEligibleCount}</strong> active / invite-ready</span>
              </div>
              <p className="studio-panel-note">
                The backend normalized this exact fixture and applied privacy rules without calling the AI provider.
              </p>
              <div className="studio-grounding-list">
                {preparation.telemetry_summary.matches.map((match) => (
                  <article key={match.match_id}>
                    <div><span>{formatWords(match.game)}</span><strong>{match.map_name ?? formatWords(match.mode)}</strong></div>
                    <p>{match.event_count} sparse events / placement {match.placement ? `#${match.placement}` : "not supplied"}</p>
                    <dl>
                      <div><dt>Mode</dt><dd>{formatWords(match.mode)}</dd></div>
                      <div><dt>Started</dt><dd>{new Date(match.started_at).toLocaleDateString("en-SG")}</dd></div>
                      <div><dt>Fixture</dt><dd>{preparation.scenario.fixture_revision}</dd></div>
                    </dl>
                  </article>
                ))}
              </div>
              <details className="studio-stage-preview studio-event-disclosure">
                <summary>Inspect prepared windows and mission affordances</summary>
                <div className="studio-grounding-list">
                  {preparation.eligible_windows.map((window) => (
                    <article key={window.window_id}>
                      <div><span>Neutral window</span><strong>{window.event_ids.length} connected events</strong></div>
                      <p>{window.start_seconds}s to {window.end_seconds}s / {window.participant_ids.length} consent-safe participants</p>
                    </article>
                  ))}
                  {preparation.mission_affordances.map((affordance) => (
                    <article key={affordance.affordance_id}>
                      <div><span>Feasible continuation</span><strong>{formatWords(affordance.family)}</strong></div>
                      <p>{affordance.objective_candidate_ids.length} backend-owned requirements</p>
                    </article>
                  ))}
                </div>
              </details>
            </>
          ) : (
            <p className="studio-panel-note">Prepare the selected fixture to inspect normalization, consent, neutral windows, and feasible missions.</p>
          )}
          {preparationError ? <div className="studio-error-card" role="alert"><strong>Preparation withheld</strong><p>{preparationError}</p></div> : null}
          <div className="studio-input-actions">
            <button
              className="studio-secondary-button"
              type="button"
              disabled={!selectedScenario || preparing || running}
              onClick={() => void prepareScenario()}
            >
              {preparing ? "Preparing scenario..." : "Prepare scenario — no AI call"}
            </button>
            <button
              className="studio-run-button"
              type="button"
              disabled={!canRun}
              onClick={() => void runInterpretation()}
            >
              {running ? "Live interpretation running..." : "Run new live interpretation — uses provider quota"}
            </button>
            <p className="studio-quota-note">One correction attempt may use a second provider call. Scenario switching and duplicate clicks are locked while a run is active.</p>
          </div>
        </section>

        <section className="studio-panel studio-trace-panel" aria-labelledby="studio-trace-title">
          <div className="studio-panel-heading studio-trace-heading">
            <div><p className="studio-panel-index">Judge trace</p><h2 id="studio-trace-title">Responsibility path</h2></div>
            <span className={`studio-run-source source-${runSource}`}>
              {runSource === "waiting" ? "Not run" : runSource === "saved_replay" ? "Replay" : "Live"}
            </span>
          </div>
          <p className="studio-panel-note">This is an auditable stage record, not hidden model reasoning.</p>
          <ol className="studio-stage-list">
            {stageDefinitions.map((definition) => {
              const trace = traceByStage.get(definition.id);
              const isPreparedStage = definition.id === "deterministic_preparation" && preparationCurrent;
              const isStudioAcceptedStage = definition.id === "player_decision" && acceptedForInspection;
              const status = isStudioAcceptedStage
                ? "complete"
                : trace?.status ?? (isPreparedStage
                  ? preparation?.status === "ready" ? "complete" : "rejected"
                  : running ? "pending" : "idle");
              const summary = isStudioAcceptedStage
                ? "Accepted by default for Studio inspection only. No player-app decision or backend telemetry was recorded."
                : trace?.summary ?? (isPreparedStage
                  ? `${preparation!.normalization.normalized_event_count} normalized events formed ${preparation!.eligible_windows.length} neutral windows and ${preparation!.mission_affordances.length} feasible mission affordances.`
                  : null);
              const issueCodes = trace?.issue_codes ?? (isPreparedStage ? preparation!.normalization.issue_codes : []);
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
                      {summary ? <small>{summary}</small> : null}
                      {issueCodes.length ? <ul className="studio-issue-list">{issueCodes.map((code) => <li key={code}>{formatWords(code)}</li>)}</ul> : null}
                    </div>
                    <span className="studio-stage-status">{isStudioAcceptedStage ? studioDecision : status}</span>
                  </article>
                </li>
              );
            })}
          </ol>
          {runError ? (
            <div className="studio-error-card" role="alert">
              <strong>Run withheld</strong>
              <p>{runError.message}</p>
              <small>
                Safe code: <code>{runError.code}</code>
                {runError.retryable
                  ? " / Retryable after the provider becomes available."
                  : " / Review the provider configuration before another run."}
              </small>
            </div>
          ) : null}
        </section>

        <section className="studio-panel studio-output-panel" aria-labelledby="studio-output-title">
          <div className="studio-panel-heading">
            <div><p className="studio-panel-index">Validated output</p><h2 id="studio-output-title">Delivery inspector</h2></div>
            <span className={`studio-result-status result-${result?.status ?? "waiting"}`}>
              {acceptedForInspection ? "Accepted for inspection" : result ? formatWords(result.status) : "No result"}
            </span>
          </div>
          <div className="studio-output-metrics">
            <div><span>Selected events</span><strong>{pending?.memory.selected_event_ids.length ?? "--"}</strong></div>
            <div><span>Affordances</span><strong>{result ? missionAffordances.length : "--"}</strong></div>
            <div><span>Content origin</span><strong>{run ? formatWords(run.content_origin) : "--"}</strong></div>
            <div><span>Correction used</span><strong>{result ? (result.validation.correction_attempted ? "Yes" : "No") : "--"}</strong></div>
          </div>
          {result && selectedScenario && actual ? (
            <section className={`studio-expectation ${expectationMatches ? "matches" : "differs"}`} aria-label="Offline expectation comparison">
              <div><span>Expected status</span><strong>{formatWords(selectedScenario.expected_status)}</strong></div>
              <div><span>Actual status</span><strong>{formatWords(actual.status)}</strong></div>
              <div><span>Expected mission</span><strong>{selectedScenario.expected_mission_family ? formatWords(selectedScenario.expected_mission_family) : "None"}</strong></div>
              <div><span>Actual mission</span><strong>{actual.mission_family ? formatWords(actual.mission_family) : "None"}</strong></div>
              <p>{expectationMatches ? "Actual behavior matched the offline evaluation label." : "Actual behavior differed from the offline evaluation label; review it rather than hiding the mismatch."}</p>
            </section>
          ) : null}
          <div className="studio-tabs" role="tablist" aria-label="Delivery inspector views">
            {(["summary", "grounding", "mission"] as ResultTab[]).map((tab) => (
              <button key={tab} type="button" role="tab" aria-selected={resultTab === tab} onClick={() => setResultTab(tab)}>{formatWords(tab)}</button>
            ))}
          </div>

          {!result ? (
            <div className="studio-empty-output"><span aria-hidden="true">M</span><h3>Prepare, then run one scenario.</h3><p>Expected labels remain hidden until an actual result exists. Rejected prose is always withheld.</p></div>
          ) : result.status === "rejected" ? (
            <div className="studio-result-stack">
              <article className="studio-result-card result-validation">
                <p>Fail-closed result</p><h3>Generated proposal withheld</h3>
                <span>No title, summary, perspective, or mission is available to this interface.</span>
                <ul className="studio-issue-list">
                  {rejectedIssues.map((issue) => (
                    <li key={issue.code}>{issue.sections.length ? `${issue.sections.join(", ")} / ` : ""}{issue.message} ({formatWords(issue.code)})</li>
                  ))}
                </ul>
              </article>
            </div>
          ) : result.status === "not_generated" ? (
            <div className="studio-result-stack">
              <article className="studio-result-card result-validation">
                <p>Valid AI abstention</p><h3>No memory generated</h3>
                <span>The evidence did not support a meaningful squad episode. No player-facing title, perspective, or mission was created.</span>
                <ul className="studio-issue-list">{result.reason_codes.map((code) => <li key={code}>{formatWords(code)}</li>)}</ul>
              </article>
            </div>
          ) : resultTab === "summary" ? (
            <div className="studio-result-stack">
              <article className="studio-result-card result-memory"><p>AI-prepared memory</p><h3>{result.memory.title}</h3><span>{formatWords(result.memory.memory_type)} / {result.memory.selected_event_ids.length} evidence events</span><blockquote>{result.memory.summary}</blockquote></article>
              <article className="studio-result-card"><p>Player perspectives</p><h3>{result.player_perspectives.length} consent-safe views</h3><ul className="studio-perspective-list">{result.player_perspectives.map((perspective) => <li key={perspective.player_id}><strong>{perspective.display_name}</strong><span>{perspective.message}</span></li>)}</ul></article>
              <article className="studio-result-card result-validation">
                <p>{runSource === "saved_replay" ? "Replay boundary" : "Delivery state"}</p>
                <h3>{runSource === "saved_replay" ? "Inspection only" : "Accepted for Studio inspection"}</h3>
                <span>{runSource === "saved_replay"
                  ? "Player decisions, invitations, and continuation are disabled for saved replays."
                  : "This Studio-only default reveals the validated delivery without recording a player decision or changing backend telemetry."}</span>
              </article>
            </div>
          ) : resultTab === "grounding" ? (
            <div className="studio-grounding-list">
              {result.grounded_claims.map((claim) => (
                <article key={claim.claim_id}>
                  <div><span>{formatWords(claim.output_section)}</span><strong>{safeSubject(claim.subject_id, result)} / {formatWords(claim.predicate)}</strong></div>
                  <p>{claimSupport(claim).join(" / ")}</p>
                  <dl><div><dt>Target</dt><dd>{claim.target_id ? safeSubject(claim.target_id, result) : "--"}</dd></div><div><dt>Location</dt><dd>{claim.location ?? "--"}</dd></div></dl>
                </article>
              ))}
            </div>
          ) : (
            <div className="studio-result-stack">
              <article className="studio-result-card result-validation">
                <p>AI mission selection</p>
                <h3>{missionSelection ? formatWords(missionSelection.selected_family) : formatWords(result.next_chapter.family)}</h3>
                <span>{missionSelection
                  ? `${missionSelection.ranked_affordance_ids.length} ranked / ${formatWords(missionSelection.reason_codes.join(", "))}`
                  : "Mission selection metadata was not supplied."}</span>
              </article>
              {missionAffordances.map((affordance) => (
                <article className="studio-result-card" key={affordance.affordance_id}>
                  <p>{missionSelection?.selected_affordance_id === affordance.affordance_id ? "Selected affordance" : "Offered affordance"}</p>
                  <h3>{formatWords(affordance.family)}</h3>
                  <span>{affordance.objective_candidate_ids.length} compiled rules / {affordance.source_event_ids.length + affordance.source_match_ids.length + affordance.source_context_ids.length} source references</span>
                </article>
              ))}
              <article className="studio-result-card result-quest"><p>AI-authored mission framing</p><h3>{result.next_chapter.title}</h3><span>{result.next_chapter.mission}</span></article>
              {result.next_chapter.objectives.map((objective) => (
                <article className={`studio-result-card${objective.objective_role === "bonus" ? " result-bonus" : ""}`} key={objective.objective_id}>
                  <p>{objective.objective_role === "bonus"
                    ? "Optional bonus"
                    : objective.objective_role === "primary"
                      ? "Required objective"
                      : `${formatWords(objective.objective_role)} objective`}</p>
                  <h3>{objective.description}</h3>
                  <span>{formatWords(objective.verification.metric)} / {formatWords(objective.verification.operator)} / {safeRuleTarget(objective.verification.target, result)}</span>
                </article>
              ))}
              {runSource === "saved_replay" ? (
                <article className="studio-result-card result-validation"><p>Replay boundary</p><h3>No player handoff</h3><span>Saved results cannot start invitations, decisions, or continuation.</span></article>
              ) : (
                <article className="studio-result-card"><p>Post-accept demonstration</p><h3>Scripted prototype sequence</h3><span>Invites sent -&gt; squad joins -&gt; game starts -&gt; selected mission completes. No live post-match telemetry is claimed.</span></article>
              )}
            </div>
          )}
        </section>
      </section>

      <footer className="studio-footer">
        <div><strong>Safe inspection boundary</strong><p>Studio shows sanitized summaries, structured claims, issue codes, and verification rules. It never shows opted-out identities, prompts, secrets, or rejected prose.</p></div>
        <div><strong>{health.message}</strong><p>A configured backend does not prove available provider quota. Feedback never rewrites prompts, models, or trusted telemetry automatically.</p></div>
      </footer>
    </main>
  );
}
