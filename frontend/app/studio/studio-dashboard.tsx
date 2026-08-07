"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  DeveloperErrorEvent,
  DeveloperHealth,
  DeveloperMemoryEngineResult,
  DeveloperStageEvent,
  DeveloperStageName,
  DeveloperStreamEvent,
  MemoryPack,
} from "@/lib/types";

type StageStatus = "idle" | "working" | "complete" | "stopped" | "failed" | "skipped";
type ResultTab = "summary" | "grounding" | "raw";
type RunMode = "waiting" | "live" | "sample";
type StudioMemoryPack = Omit<MemoryPack, "schema_version"> & {
  schema_version: "1.0" | "1.1";
};

type StageState = {
  status: StageStatus;
  message?: string;
  preview?: unknown;
};

const stageDefinitions: Array<{
  id: DeveloperStageName;
  number: string;
  label: string;
  fixedOwner?: string;
  description: string;
}> = [
  {
    id: "review_and_discovery",
    number: "01",
    label: "Evidence and consent",
    fixedOwner: "Deterministic",
    description: "Checks signal strength, review state, consent, and whether generation may continue.",
  },
  {
    id: "memory_discovery",
    number: "02",
    label: "Memory framing",
    description: "Selects a grounded memory shape from the allowed evidence ledger.",
  },
  {
    id: "perspectives",
    number: "03",
    label: "Player perspectives",
    description: "Builds one evidence-linked perspective for every opted-in squad member.",
  },
  {
    id: "quest_generation",
    number: "04",
    label: "Continuation mission",
    description: "Composes a bounded mission and objectives tied back to source events.",
  },
  {
    id: "validation",
    number: "05",
    label: "Grounding validator",
    fixedOwner: "Deterministic",
    description: "Fails closed on unsupported claims, consent leaks, or unverifiable objectives.",
  },
];

function freshStages(): Record<DeveloperStageName, StageState> {
  return {
    review_and_discovery: { status: "idle" },
    memory_discovery: { status: "idle" },
    perspectives: { status: "idle" },
    quest_generation: { status: "idle" },
    validation: { status: "idle" },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isOptionalString(value: unknown) {
  return value === undefined || value === null || typeof value === "string";
}

function isOptionalNumber(value: unknown) {
  return value === undefined || value === null || isFiniteNumber(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isSquadMember(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.player_id === "string" &&
    value.player_id.length > 0 &&
    typeof value.display_name === "string" &&
    value.display_name.length > 0 &&
    isOptionalString(value.role) &&
    (value.opted_in === undefined || typeof value.opted_in === "boolean")
  );
}

function isMatchEvent(value: unknown) {
  if (
    !isRecord(value) ||
    typeof value.event_id !== "string" ||
    value.event_id.length === 0 ||
    typeof value.type !== "string" ||
    value.type.length === 0 ||
    !isOptionalString(value.actor_id) ||
    !isOptionalString(value.target_id) ||
    !isOptionalNumber(value.timestamp_seconds) ||
    !isOptionalString(value.location) ||
    (value.importance !== undefined && !["low", "medium", "high"].includes(String(value.importance)))
  ) {
    return false;
  }

  return (
    value.details === undefined ||
    (isRecord(value.details) &&
      Object.values(value.details).every(
        (item) => ["string", "number", "boolean"].includes(typeof item) &&
          (typeof item !== "number" || Number.isFinite(item)),
      ))
  );
}

function isMemoryPack(value: unknown): value is StudioMemoryPack {
  if (
    !isRecord(value) ||
    !["1.0", "1.1"].includes(String(value.schema_version)) ||
    typeof value.pack_id !== "string" ||
    value.pack_id.length === 0 ||
    !isRecord(value.player_profile) ||
    typeof value.player_profile.player_id !== "string" ||
    value.player_profile.player_id.length === 0 ||
    !isOptionalString(value.player_profile.preferred_role) ||
    !isRecord(value.squad) ||
    typeof value.squad.squad_id !== "string" ||
    !Array.isArray(value.squad.members) ||
    value.squad.members.length < 2 ||
    value.squad.members.length > 4 ||
    !value.squad.members.every(isSquadMember) ||
    !isFiniteNumber(value.squad.matches_together) ||
    !isOptionalNumber(value.squad.days_since_full_squad) ||
    !isRecord(value.match) ||
    typeof value.match.match_id !== "string" ||
    typeof value.match.mode !== "string" ||
    !isOptionalString(value.match.map_name) ||
    !isOptionalNumber(value.match.placement) ||
    !isOptionalString(value.match.played_at) ||
    !Array.isArray(value.match_events) ||
    value.match_events.length > 100 ||
    !value.match_events.every(isMatchEvent)
  ) {
    return false;
  }

  if (
    value.human_memory !== undefined &&
    value.human_memory !== null &&
    (!isRecord(value.human_memory) ||
      !isOptionalString(value.human_memory.caption) ||
      (value.human_memory.tags !== undefined && !isStringArray(value.human_memory.tags)) ||
      !isOptionalString(value.human_memory.author_player_id) ||
      (value.human_memory.confirmed !== undefined && typeof value.human_memory.confirmed !== "boolean"))
  ) {
    return false;
  }

  if (
    value.reactions !== undefined &&
    (!isRecord(value.reactions) ||
      (value.reactions.laugh_count !== undefined && !isFiniteNumber(value.reactions.laugh_count)) ||
      (value.reactions.fire_count !== undefined && !isFiniteNumber(value.reactions.fire_count)) ||
      (value.reactions.saved !== undefined && typeof value.reactions.saved !== "boolean"))
  ) {
    return false;
  }

  if (
    value.current_context !== undefined &&
    (!isRecord(value.current_context) ||
      (value.current_context.active_member_ids !== undefined &&
        !isStringArray(value.current_context.active_member_ids)) ||
      !isOptionalString(value.current_context.resurfacing_reason) ||
      (value.current_context.original_mode_available !== undefined &&
        typeof value.current_context.original_mode_available !== "boolean"))
  ) {
    return false;
  }

  return true;
}

function parsePack(value: string): StudioMemoryPack | null {
  try {
    const parsed = JSON.parse(value) as unknown;
    return isMemoryPack(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function isStageName(value: unknown): value is DeveloperStageName {
  return stageDefinitions.some((stage) => stage.id === value);
}

function isDiscoveryAssessment(value: unknown) {
  return (
    isRecord(value) &&
    isFiniteNumber(value.signal_score) &&
    isFiniteNumber(value.threshold) &&
    isStringArray(value.reasons) &&
    typeof value.eligible === "boolean"
  );
}

function isMemoryRecord(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.title === "string" &&
    ["chaos", "comeback", "clutch", "ritual", "first", "other"].includes(
      String(value.memory_type),
    ) &&
    typeof value.summary === "string" &&
    isFiniteNumber(value.confidence) &&
    Array.isArray(value.evidence) &&
    value.evidence.every(
      (item) =>
        isRecord(item) &&
        typeof item.event_id === "string" &&
        typeof item.event_type === "string" &&
        typeof item.significance === "string",
    ) &&
    (value.human_confirmed === undefined || typeof value.human_confirmed === "boolean")
  );
}

function isPerspective(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.player_id === "string" &&
    typeof value.display_name === "string" &&
    typeof value.message === "string" &&
    isStringArray(value.evidence_event_ids)
  );
}

function isNextChapter(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.title === "string" &&
    typeof value.mission === "string" &&
    ["recreate", "remix", "resolve"].includes(String(value.recipe)) &&
    Array.isArray(value.objectives) &&
    value.objectives.every(
      (objective) =>
        isRecord(objective) &&
        typeof objective.objective_id === "string" &&
        typeof objective.description === "string" &&
        (objective.assigned_player_id === undefined ||
          objective.assigned_player_id === null ||
          typeof objective.assigned_player_id === "string") &&
        typeof objective.required === "boolean" &&
        isRecord(objective.verification) &&
        typeof objective.verification.metric === "string" &&
        ["equals", "at_least", "contains_all"].includes(
          String(objective.verification.operator),
        ) &&
        isStringArray(objective.source_event_ids),
    )
  );
}

function isValidationReport(value: unknown) {
  if (
    !isRecord(value) ||
    typeof value.passed !== "boolean" ||
    typeof value.human_review_required !== "boolean" ||
    !isRecord(value.scores)
  ) {
    return false;
  }

  const scores = value.scores;
  return (
    Object.values(scores).every(isFiniteNumber) &&
    ["specificity", "evidence_grounding", "perspective_distinctness", "quest_connection"].every(
      (key) => isFiniteNumber(scores[key]),
    ) &&
    Array.isArray(value.issues) &&
    value.issues.every(
      (issue) =>
        isRecord(issue) &&
        typeof issue.code === "string" &&
        ["info", "warning", "error"].includes(String(issue.severity)) &&
        typeof issue.message === "string",
    )
  );
}

function isPipelineMetadata(value: unknown) {
  if (
    !isRecord(value) ||
    typeof value.pipeline_version !== "string" ||
    typeof value.provider !== "string" ||
    typeof value.model !== "string" ||
    typeof value.factual_renderer !== "string" ||
    (value.redaction_count !== undefined && !isFiniteNumber(value.redaction_count))
  ) {
    return false;
  }

  return (
    value.usage === undefined ||
    (isRecord(value.usage) &&
      (value.usage.input_tokens === undefined || isFiniteNumber(value.usage.input_tokens)) &&
      (value.usage.output_tokens === undefined || isFiniteNumber(value.usage.output_tokens)))
  );
}

function isDeveloperResult(
  value: unknown,
  expectedPackId: string,
): value is DeveloperMemoryEngineResult {
  return (
    isRecord(value) &&
    ["1.0", "1.1"].includes(String(value.schema_version)) &&
    value.pack_id === expectedPackId &&
    [
      "ready",
      "needs_human_confirmation",
      "needs_source_verification",
      "needs_meaning_confirmation",
      "rejected",
    ].includes(String(value.status)) &&
    isDiscoveryAssessment(value.discovery) &&
    (value.memory === undefined || value.memory === null || isMemoryRecord(value.memory)) &&
    Array.isArray(value.player_perspectives) &&
    value.player_perspectives.every(isPerspective) &&
    (value.next_chapter === undefined ||
      value.next_chapter === null ||
      isNextChapter(value.next_chapter)) &&
    isValidationReport(value.validation) &&
    isPipelineMetadata(value.metadata)
  );
}

function parseHealth(value: unknown): DeveloperHealth | null {
  if (
    !isRecord(value) ||
    !["ok", "sample", "error"].includes(String(value.status)) ||
    !["live", "sample"].includes(String(value.mode)) ||
    typeof value.provider !== "string" ||
    typeof value.model !== "string" ||
    typeof value.message !== "string" ||
    (value.code !== undefined && typeof value.code !== "string")
  ) {
    return null;
  }

  return {
    status: value.status as DeveloperHealth["status"],
    mode: value.mode as DeveloperHealth["mode"],
    provider: value.provider,
    model: value.model,
    message: value.message,
    ...(typeof value.code === "string" ? { code: value.code } : {}),
  };
}

function parseStreamEvent(line: string, expectedPackId: string): DeveloperStreamEvent {
  const value = JSON.parse(line) as unknown;
  if (!isRecord(value) || typeof value.type !== "string") {
    throw new Error("The pipeline returned an invalid event.");
  }

  if (
    value.type === "stage" &&
    isStageName(value.stage) &&
    ["working", "complete", "stopped", "failed"].includes(String(value.status)) &&
    (value.message === undefined || value.message === null || typeof value.message === "string")
  ) {
    return {
      type: "stage",
      stage: value.stage,
      status: value.status as DeveloperStageEvent["status"],
      ...(typeof value.message === "string" ? { message: value.message } : {}),
      ...(Object.hasOwn(value, "preview") ? { preview: value.preview } : {}),
    };
  }

  if (
    value.type === "error" &&
    typeof value.stage === "string" &&
    typeof value.code === "string" &&
    typeof value.retryable === "boolean" &&
    (value.message === undefined || value.message === null || typeof value.message === "string")
  ) {
    return {
      type: "error",
      stage: value.stage,
      code: value.code,
      retryable: value.retryable,
      ...(typeof value.message === "string" ? { message: value.message } : {}),
    };
  }

  if (value.type === "result" && isDeveloperResult(value.result, expectedPackId)) {
    return { type: "result", result: value.result };
  }

  throw new Error("The pipeline returned an unsupported event.");
}

function formatWords(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDuration(value: number | null) {
  if (value === null) return "--";
  if (value < 1_000) return `${Math.round(value)} ms`;
  return `${(value / 1_000).toFixed(2)} s`;
}

function formatScore(value: number) {
  return `${Math.round(value * 100)}%`;
}

function sourceLabel(mode: RunMode) {
  if (mode === "live") return "Live backend";
  if (mode === "sample") return "Sample replay";
  return "Waiting to run";
}

function isConfiguredModelProvider(provider: string) {
  return ![
    "",
    "checking",
    "deterministic",
    "sample-replay",
    "unavailable",
    "unknown",
  ].includes(provider.trim().toLowerCase());
}

function settleStagesAfterError(
  current: Record<DeveloperStageName, StageState>,
  failedStage: string,
) {
  const next = { ...current };
  for (const definition of stageDefinitions) {
    const stage = next[definition.id];
    if (definition.id === failedStage) {
      next[definition.id] = { ...stage, status: "failed" };
    } else if (stage.status === "working") {
      next[definition.id] = { ...stage, status: "stopped" };
    } else if (stage.status === "idle") {
      next[definition.id] = { ...stage, status: "skipped" };
    }
  }
  return next;
}

export function StudioDashboard({ initialPack }: { initialPack: MemoryPack }) {
  const initialText = useMemo(() => JSON.stringify(initialPack, null, 2), [initialPack]);
  const [inputText, setInputText] = useState(initialText);
  const parsedPack = useMemo(() => parsePack(inputText), [inputText]);
  const [health, setHealth] = useState<DeveloperHealth>({
    status: "sample",
    mode: "sample",
    provider: "checking",
    model: "checking",
    message: "Checking the MemoryOS backend.",
  });
  const [stages, setStages] = useState<Record<DeveloperStageName, StageState>>(freshStages);
  const [result, setResult] = useState<DeveloperMemoryEngineResult | null>(null);
  const [submittedPack, setSubmittedPack] = useState<StudioMemoryPack | null>(null);
  const [resultTab, setResultTab] = useState<ResultTab>("summary");
  const [runMode, setRunMode] = useState<RunMode>("waiting");
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<DeveloperErrorEvent | null>(null);
  const runSequence = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/studio/health", { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        const payload = parseHealth(await response.json());
        if (!payload) throw new Error("The backend returned an invalid health response.");
        setHealth(payload);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setHealth({
          status: "error",
          mode: "sample",
          provider: "unavailable",
          model: "unavailable",
          message: "Studio could not check the MemoryOS backend.",
        });
      });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    return () => {
      runSequence.current += 1;
      activeRequest.current?.abort();
    };
  }, []);

  const optedInCount =
    parsedPack?.squad.members.filter((member) => member.opted_in !== false).length ?? 0;
  const provider = result?.metadata.provider ?? health.provider;
  const model = result?.metadata.model ?? health.model;
  const modelConfigured = isConfiguredModelProvider(provider);
  const semanticOwner =
    runMode === "sample"
      ? "Replay"
      : provider === "deterministic"
        ? "Rules engine"
        : modelConfigured
          ? "Model-capable"
          : "Unconfirmed";
  const usage = result?.metadata.usage;
  const inputTokens = usage?.input_tokens ?? 0;
  const outputTokens = usage?.output_tokens ?? 0;
  const totalTokens = inputTokens + outputTokens;
  const modelActivity =
    runMode === "sample"
      ? "Not invoked in replay"
      : provider === "deterministic"
        ? "No model configured"
        : totalTokens > 0
          ? `${totalTokens.toLocaleString()} tokens reported`
          : modelConfigured
            ? result
              ? "Configured; no invocation reported"
              : "Model-capable; invocation not observed"
            : "Model provider not confirmed";
  const groundingPack = submittedPack ?? parsedPack;
  const eventMap = new Map(
    (groundingPack?.match_events ?? []).map((event) => [event.event_id, event]),
  );

  function applyStreamEvent(event: DeveloperStreamEvent) {
    if (event.type === "stage") {
      setStages((current) => {
        const next = { ...current };
        if (
          event.stage !== "review_and_discovery" &&
          next.review_and_discovery.status === "working"
        ) {
          next.review_and_discovery = {
            ...next.review_and_discovery,
            status: "complete",
          };
        }
        next[event.stage] = {
          status: event.status,
          message: event.message,
          preview: event.preview,
        };
        return next;
      });
      return;
    }

    if (event.type === "error") {
      setRunError(event);
      setStages((current) => {
        const next = settleStagesAfterError(current, event.stage);
        if (isStageName(event.stage)) {
          next[event.stage] = {
            ...next[event.stage],
            message: event.message ?? event.code,
          };
        }
        return next;
      });
      return;
    }

    setResult(event.result);
    setStages((current) => {
      const next = { ...current };
      for (const definition of stageDefinitions) {
        const currentStage = next[definition.id];
        if (currentStage.status === "working") {
          next[definition.id] = { ...currentStage, status: "complete" };
        } else if (currentStage.status === "idle") {
          next[definition.id] = { ...currentStage, status: "skipped" };
        }
      }
      return next;
    });
  }

  async function runPipeline() {
    if (!parsedPack || running) return;

    const packForRun = parsedPack;
    const requestId = ++runSequence.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setStages(freshStages());
    setResult(null);
    setSubmittedPack(packForRun);
    setRunError(null);
    setDurationMs(null);
    setFallbackReason(null);
    setRunMode("waiting");
    setRunning(true);
    const startedAt = performance.now();
    let sawEvent = false;
    let sawError = false;

    try {
      const response = await fetch("/api/studio/generate-stream", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(packForRun),
        signal: controller.signal,
      });
      if (controller.signal.aborted || requestId !== runSequence.current) return;

      const mode = response.headers.get("x-memoryos-mode");
      setRunMode(mode === "live" ? "live" : "sample");
      setFallbackReason(response.headers.get("x-memoryos-fallback"));

      if (!response.body) throw new Error("The pipeline did not return a stream.");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const consumeLine = (line: string) => {
        if (!line.trim()) return;
        const event = parseStreamEvent(line, packForRun.pack_id);
        sawEvent = true;
        if (event.type === "error") sawError = true;
        applyStreamEvent(event);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (controller.signal.aborted || requestId !== runSequence.current) return;
        buffer += decoder.decode(value, { stream: !done });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() ?? "";
        for (const line of lines) consumeLine(line);
        if (done) break;
      }
      if (buffer.trim()) consumeLine(buffer);

      if (!sawEvent) throw new Error("The pipeline returned no readable snapshots.");
      if (!response.ok && !sawError) {
        throw new Error("The live backend rejected this Studio run.");
      }
    } catch (error) {
      if (controller.signal.aborted || requestId !== runSequence.current) return;
      setRunError({
        type: "error",
        stage: "connection",
        code: "studio_run_failed",
        retryable: true,
        message: error instanceof Error ? error.message : "The Studio run failed.",
      });
      setStages((current) => settleStagesAfterError(current, "connection"));
    } finally {
      if (!controller.signal.aborted && requestId === runSequence.current) {
        setDurationMs(performance.now() - startedAt);
        setRunning(false);
      }
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }

  function resetInput() {
    runSequence.current += 1;
    activeRequest.current?.abort();
    activeRequest.current = null;
    setInputText(initialText);
    setStages(freshStages());
    setResult(null);
    setSubmittedPack(null);
    setRunError(null);
    setDurationMs(null);
    setFallbackReason(null);
    setRunMode("waiting");
    setRunning(false);
  }

  function formatInput() {
    if (!parsedPack) return;
    setInputText(JSON.stringify(parsedPack, null, 2));
  }

  return (
    <main className="studio-app">
      <a className="skip-link" href="#studio-workspace">Skip to pipeline workspace</a>
      <p className="sr-only" aria-live="polite">
        {running
          ? "MemoryOS pipeline run in progress."
          : runError
            ? `Pipeline error: ${runError.code}.`
            : result
              ? `Pipeline finished with status ${result.status}.`
              : "MemoryOS Studio ready."}
      </p>

      <header className="studio-topbar">
        <Link className="studio-brand" href="/studio" aria-label="MemoryOS Studio home">
          <span className="studio-brand-mark">M</span>
          <span>
            <strong>MemoryOS</strong>
            <small>Studio</small>
          </span>
        </Link>
        <div className="studio-topbar-actions">
          <span className={`studio-connection studio-connection-${health.status}`}>
            <i aria-hidden="true" />
            {health.status === "ok" ? "Backend connected" : health.status === "sample" ? "Replay mode" : "Backend issue"}
          </span>
          <Link className="studio-player-link" href="/">Open player view</Link>
        </div>
      </header>

      <section className="studio-hero" aria-labelledby="studio-title">
        <div>
          <p className="studio-kicker">Developer observability</p>
          <h1 id="studio-title">Developer Dashboard</h1>
          <p className="studio-intro">
            Inspect the submitted evidence, model-capable stages, grounded outputs, and the
            deterministic checks that decide whether a memory is safe to ship.
          </p>
        </div>
        <dl className="studio-hero-metrics">
          <div>
            <dt>Provider</dt>
            <dd>{provider}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{model}</dd>
          </div>
          <div>
            <dt>Run source</dt>
            <dd>{sourceLabel(runMode)}</dd>
          </div>
          <div>
            <dt>End-to-end</dt>
            <dd>{formatDuration(durationMs)}</dd>
          </div>
        </dl>
      </section>

      <section className="studio-boundary" aria-label="MemoryOS responsibility boundary">
        <div className="studio-boundary-step boundary-input">
          <span>Deterministic</span>
          <strong>Consent + evidence</strong>
          <small>Gate, sanitize, score</small>
        </div>
        <div className="studio-boundary-arrow" aria-hidden="true">+</div>
        <div className="studio-boundary-step boundary-ai">
          <span>Model-capable</span>
          <strong>Semantic generation</strong>
          <small>Frame, personalize, compose</small>
        </div>
        <div className="studio-boundary-arrow" aria-hidden="true">+</div>
        <div className="studio-boundary-step boundary-output">
          <span>Deterministic</span>
          <strong>Validation + output</strong>
          <small>Ground, verify, abstain</small>
        </div>
      </section>

      <section className="studio-workspace" id="studio-workspace">
        <section className="studio-panel studio-input-panel" aria-labelledby="studio-input-title">
          <div className="studio-panel-heading">
            <div>
              <p className="studio-panel-index">Input</p>
              <h2 id="studio-input-title">Synthetic gameplay pack</h2>
            </div>
            <span className={`studio-validity ${parsedPack ? "valid" : "invalid"}`}>
              {parsedPack ? "Valid JSON" : "Needs attention"}
            </span>
          </div>

          <div className="studio-input-stats">
            <span><strong>{parsedPack?.match_events.length ?? 0}</strong> events</span>
            <span><strong>{parsedPack?.squad.members.length ?? 0}</strong> players</span>
            <span><strong>{optedInCount}</strong> opted in</span>
          </div>

          <label className="studio-json-label" htmlFor="studio-json-input">
            Submitted payload
          </label>
          <textarea
            id="studio-json-input"
            className="studio-json-input"
            value={inputText}
            onChange={(event) => setInputText(event.target.value)}
            spellCheck={false}
            aria-invalid={!parsedPack}
          />
          {!parsedPack ? (
            <p className="studio-input-error">Provide a JSON object with a pack ID, squad, match, and match events.</p>
          ) : null}

          <div className="studio-input-actions">
            <button className="studio-run-button" type="button" onClick={() => void runPipeline()} disabled={!parsedPack || running}>
              {running ? "Running pipeline..." : "Run pipeline audit"}
            </button>
            <button className="studio-secondary-button" type="button" onClick={formatInput} disabled={!parsedPack || running}>
              Format JSON
            </button>
            <button className="studio-text-button" type="button" onClick={resetInput}>
              Reset
            </button>
          </div>
        </section>

        <section className="studio-panel studio-trace-panel" aria-labelledby="studio-trace-title">
          <div className="studio-panel-heading studio-trace-heading">
            <div>
              <p className="studio-panel-index">Pipeline snapshots</p>
              <h2 id="studio-trace-title">Decision path</h2>
            </div>
            <span className={`studio-run-source source-${runMode}`}>{sourceLabel(runMode)}</span>
          </div>

          <p className="studio-panel-note">
            These are completed stage snapshots, not a live token stream. Provider selection remains server-side.
          </p>

          <ol className="studio-stage-list">
            {stageDefinitions.map((definition) => {
              const stage = stages[definition.id];
              const owner = definition.fixedOwner ?? semanticOwner;
              return (
                <li key={definition.id}>
                  <article className={`studio-stage stage-${stage.status}`}>
                    <div className="studio-stage-number">{definition.number}</div>
                    <div className="studio-stage-copy">
                      <div className="studio-stage-title-row">
                        <h3>{definition.label}</h3>
                        <span className={`studio-owner owner-${owner.toLowerCase().replaceAll(" ", "-")}`}>{owner}</span>
                      </div>
                      <p>{definition.description}</p>
                      {stage.message ? <small>{stage.message}</small> : null}
                      {stage.preview !== undefined ? (
                        <details className="studio-stage-preview">
                          <summary>Inspect structured snapshot</summary>
                          <pre>{JSON.stringify(stage.preview, null, 2)}</pre>
                        </details>
                      ) : null}
                    </div>
                    <span className="studio-stage-status">{stage.status}</span>
                  </article>
                </li>
              );
            })}
          </ol>

          {runError ? (
            <div className="studio-error-card" role="alert">
              <strong>{formatWords(runError.code)}</strong>
              <p>{runError.message ?? "The pipeline stopped safely."}</p>
              <small>Stage: {formatWords(runError.stage)} · Retryable: {runError.retryable ? "yes" : "no"}</small>
            </div>
          ) : null}
        </section>

        <section className="studio-panel studio-output-panel" aria-labelledby="studio-output-title">
          <div className="studio-panel-heading">
            <div>
              <p className="studio-panel-index">Output</p>
              <h2 id="studio-output-title">Generation inspector</h2>
            </div>
            <span className={`studio-result-status result-${result?.status ?? "waiting"}`}>
              {result ? formatWords(result.status) : "No result"}
            </span>
          </div>

          <div className="studio-output-metrics">
            <div>
              <span>Model activity</span>
              <strong>{modelActivity}</strong>
            </div>
            <div>
              <span>Redactions</span>
              <strong>{result?.metadata.redaction_count ?? 0}</strong>
            </div>
            <div>
              <span>Validation</span>
              <strong>{result ? (result.validation.passed ? "Passed" : "Stopped") : "--"}</strong>
            </div>
          </div>

          <div className="studio-tabs" role="tablist" aria-label="Generation inspector views">
            {(["summary", "grounding", "raw"] as ResultTab[]).map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={resultTab === tab}
                onClick={() => setResultTab(tab)}
              >
                {formatWords(tab)}
              </button>
            ))}
          </div>

          {!result ? (
            <div className="studio-empty-output">
              <span aria-hidden="true">M</span>
              <h3>Run the pack to inspect its output.</h3>
              <p>The Studio will keep the submitted data, stage snapshots, and final validation side by side.</p>
            </div>
          ) : resultTab === "summary" ? (
            <div className="studio-result-stack">
              <article className="studio-result-card result-memory">
                <p>Shared memory</p>
                <h3>{result.memory?.title ?? "No memory generated"}</h3>
                <span>
                  {result.memory
                    ? `${formatWords(result.memory.memory_type)} · ${formatScore(result.memory.confidence)} confidence`
                    : "The pipeline abstained before memory generation."}
                </span>
                {result.memory ? <blockquote>{result.memory.summary}</blockquote> : null}
              </article>

              <article className="studio-result-card">
                <p>Personalization</p>
                <h3>{result.player_perspectives.length} player perspectives</h3>
                <ul className="studio-perspective-list">
                  {result.player_perspectives.map((perspective) => (
                    <li key={perspective.player_id}>
                      <strong>{perspective.display_name}</strong>
                      <span>{perspective.message}</span>
                    </li>
                  ))}
                </ul>
              </article>

              <article className="studio-result-card result-quest">
                <p>Continuation</p>
                <h3>{result.next_chapter?.title ?? "No mission released"}</h3>
                {result.next_chapter ? (
                  <>
                    <span>{result.next_chapter.mission}</span>
                    <ol>
                      {result.next_chapter.objectives.map((objective) => (
                        <li key={objective.objective_id}>{objective.description}</li>
                      ))}
                    </ol>
                  </>
                ) : null}
              </article>

              <article className="studio-result-card result-validation">
                <p>Quality gates</p>
                <div className="studio-score-list">
                  {Object.entries(result.validation.scores).map(([name, score]) => (
                    <div key={name}>
                      <span>{formatWords(name)}</span>
                      <i><b style={{ width: formatScore(score) }} /></i>
                      <strong>{formatScore(score)}</strong>
                    </div>
                  ))}
                </div>
                {result.validation.issues.length ? (
                  <ul className="studio-issue-list">
                    {result.validation.issues.map((issue, index) => (
                      <li key={`${issue.code}-${index}`}>
                        <strong>{issue.severity}</strong> {issue.message}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span>No validation issues were reported.</span>
                )}
              </article>
            </div>
          ) : resultTab === "grounding" ? (
            <div className="studio-grounding-list">
              {result.memory?.evidence.length ? (
                result.memory.evidence.map((evidence) => {
                  const sourceEvent = eventMap.get(evidence.event_id);
                  return (
                    <article key={evidence.event_id}>
                      <div>
                        <span>{evidence.event_id}</span>
                        <strong>{formatWords(evidence.event_type)}</strong>
                      </div>
                      <p>{evidence.significance}</p>
                      <dl>
                        <div><dt>Actor</dt><dd>{sourceEvent?.actor_id ?? "--"}</dd></div>
                        <div><dt>Location</dt><dd>{sourceEvent?.location ?? "--"}</dd></div>
                        <div><dt>Importance</dt><dd>{sourceEvent?.importance ?? "--"}</dd></div>
                      </dl>
                    </article>
                  );
                })
              ) : (
                <p className="studio-no-grounding">No evidence links were produced for this run.</p>
              )}
            </div>
          ) : (
            <pre className="studio-raw-output">{JSON.stringify(result, null, 2)}</pre>
          )}
        </section>
      </section>

      <footer className="studio-footer">
        <div>
          <strong>Safe inspection boundary</strong>
          <p>
            Studio retains runs only in this browser session. It displays structured snapshots and never exposes API keys,
            system prompts, or raw provider exceptions.
          </p>
        </div>
        <div>
          <strong>{health.message}</strong>
          <p>
            {fallbackReason
              ? `Latest fallback: ${formatWords(fallbackReason)}.`
              : "The active provider is controlled by the backend configuration."}
          </p>
        </div>
      </footer>
    </main>
  );
}
