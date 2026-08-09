import {
  parseStudioInterpretDeliveryV2,
  type MissionAffordanceV2,
  type MissionFamilyV2,
  type MissionObjectiveV2,
  type StudioInterpretDeliveryResultV2,
  type StudioInterpretationTraceV2,
} from "@/lib/ai-memory-contract";

export const studioScenarioIds = [
  "rescue-role-reversal",
  "repeated-near-miss",
  "landing-rendezvous",
  "duo-assist",
  "ordinary-sparse-telemetry",
] as const;

export type StudioScenarioId = (typeof studioScenarioIds)[number];
export type StudioScenarioExpectedStatus = "pending_player_decision" | "not_generated";

export type StudioScenarioDescriptorV2 = {
  scenario_id: StudioScenarioId;
  title: string;
  purpose: string;
  fixture_sha256: string;
  fixture_revision: string;
  expected_status: StudioScenarioExpectedStatus;
  expected_mission_family: MissionFamilyV2 | null;
  label_source: "offline_evaluation_manifest";
};

export type StudioScenarioCatalogV2 = {
  schema_version: "2.1";
  scenarios: StudioScenarioDescriptorV2[];
};

export type StudioScenarioTelemetrySummaryV2 = {
  request_id: string;
  target_player_id: string;
  match_count: number;
  raw_event_count: number;
  consent_safe_player_count: number;
  invitation_eligible_count: number;
  active_player_count: number;
  matches: Array<{
    match_id: string;
    game: string;
    mode: string;
    map_name: string | null;
    started_at: string;
    placement: number | null;
    event_count: number;
  }>;
};

export type StudioScenarioPreparationV2 = {
  schema_version: "2.1";
  scenario: StudioScenarioDescriptorV2;
  status: "ready" | "rejected";
  telemetry_summary: StudioScenarioTelemetrySummaryV2;
  normalization: {
    normalized_match_count: number;
    normalized_event_count: number;
    issue_codes: string[];
  };
  privacy: {
    redaction_count: number;
    anonymous_player_count: number;
  };
  eligible_windows: StudioInterpretationTraceV2["eligible_windows"];
  mission_candidates: StudioInterpretationTraceV2["mission_candidates"];
  mission_affordances: MissionAffordanceV2[];
};

export type StudioScenarioInterpretationV2 = {
  schema_version: "2.1";
  scenario: StudioScenarioDescriptorV2;
  result: StudioInterpretDeliveryResultV2;
};

export type StudioScenarioRunV2 = StudioScenarioInterpretationV2 & {
  content_origin: "live_ai_validated" | "no_player_content" | "saved_live_replay";
  replay_provenance: null | {
    provider: string;
    model: string;
    prompt_version: string;
    result_schema_version: "2.1";
    captured_at: string;
  };
};

type RecordValue = Record<string, unknown>;

function isRecord(value: unknown): value is RecordValue {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNonNegativeInteger(value: unknown) {
  return Number.isInteger(value) && Number(value) >= 0;
}

function isMissionFamily(value: unknown): value is MissionFamilyV2 {
  return [
    "reunion",
    "role_reversal",
    "redemption",
    "return_to_place",
    "landing_rendezvous",
    "duo_assist",
  ].includes(String(value));
}

function isRuleTarget(value: unknown) {
  return typeof value === "string"
    || (typeof value === "number" && Number.isFinite(value))
    || typeof value === "boolean"
    || (Array.isArray(value) && value.every((item) => typeof item === "string"));
}

function isVerification(value: unknown): value is MissionObjectiveV2["verification"] {
  return isRecord(value)
    && typeof value.metric === "string"
    && ["equals", "at_least", "contains_all"].includes(String(value.operator))
    && isRuleTarget(value.target);
}

function isEligibleWindow(value: unknown): value is StudioInterpretationTraceV2["eligible_windows"][number] {
  return isRecord(value)
    && typeof value.window_id === "string"
    && typeof value.match_id === "string"
    && isStringArray(value.event_ids)
    && isStringArray(value.participant_ids)
    && isNonNegativeInteger(value.start_seconds)
    && isNonNegativeInteger(value.end_seconds)
    && Number(value.end_seconds) >= Number(value.start_seconds);
}

function isMissionCandidate(value: unknown): value is StudioInterpretationTraceV2["mission_candidates"][number] {
  return isRecord(value)
    && typeof value.candidate_id === "string"
    && typeof value.window_id === "string"
    && typeof value.recipe === "string"
    && ["prerequisite", "primary", "support", "bonus", "completion"]
      .includes(String(value.objective_role))
    && typeof value.required === "boolean"
    && (value.objective_role === "bonus" ? value.required === false : value.required === true)
    && isStringArray(value.compatibility_tags)
    && value.compatibility_tags.length > 0
    && value.compatibility_tags.length <= 4
    && new Set(value.compatibility_tags).size === value.compatibility_tags.length
    && value.compatibility_tags.every((tag) => [
      "squad_entry",
      "location",
      "individual_assignment",
      "squad_coordination",
      "combat",
      "support_action",
      "tactical",
      "vehicle",
      "placement",
      "match_completion",
    ].includes(tag))
    && (value.assigned_player_id == null || typeof value.assigned_player_id === "string")
    && isStringArray(value.source_event_ids)
    && isVerification(value.verification);
}

function isMissionAffordance(value: unknown): value is MissionAffordanceV2 {
  if (!isRecord(value)
    || typeof value.affordance_id !== "string"
    || !isMissionFamily(value.family)
    || typeof value.window_id !== "string"
    || !isStringArray(value.source_event_ids)
    || !isStringArray(value.source_match_ids)
    || !isStringArray(value.source_context_ids)
    || !isRecord(value.parameters)
    || !Object.values(value.parameters).every(isRuleTarget)
    || !isStringArray(value.objective_candidate_ids)
    || !isStringArray(value.allowed_reason_codes)) return false;
  const uniqueNonEmpty = (items: string[]) => items.length > 0 && new Set(items).size === items.length;
  return uniqueNonEmpty(value.source_event_ids)
    && uniqueNonEmpty(value.source_match_ids)
    && new Set(value.source_context_ids).size === value.source_context_ids.length
    && uniqueNonEmpty(value.objective_candidate_ids)
    && value.objective_candidate_ids.length >= 2
    && value.objective_candidate_ids.length <= 5
    && uniqueNonEmpty(value.allowed_reason_codes);
}

function hasValidAffordanceObjectiveGrammar(
  affordance: MissionAffordanceV2,
  candidateById: Map<string, StudioInterpretationTraceV2["mission_candidates"][number]>,
) {
  const objectives = affordance.objective_candidate_ids.map((candidateId) => candidateById.get(candidateId));
  if (objectives.some((objective) => !objective)) return false;
  const roles = objectives.map((objective) => objective!.objective_role);
  const expectedPrimaryCount = affordance.family === "reunion" ? 0 : 1;
  return roles[0] === "prerequisite"
    && roles.at(-1) === "completion"
    && roles.filter((role) => role === "prerequisite").length === 1
    && roles.filter((role) => role === "completion").length === 1
    && roles.filter((role) => role === "primary").length === expectedPrimaryCount
    && roles.filter((role) => role === "support").length <= 2
    && roles.filter((role) => role === "bonus").length <= 2;
}

export function parseStudioScenarioDescriptor(value: unknown): StudioScenarioDescriptorV2 | null {
  if (!isRecord(value)
    || !studioScenarioIds.includes(value.scenario_id as StudioScenarioId)
    || typeof value.title !== "string"
    || typeof value.purpose !== "string"
    || typeof value.fixture_sha256 !== "string"
    || !/^[a-f0-9]{64}$/.test(value.fixture_sha256)
    || typeof value.fixture_revision !== "string"
    || !/^2\.1:[a-f0-9]{12}$/.test(value.fixture_revision)
    || !["pending_player_decision", "not_generated"].includes(String(value.expected_status))
    || (value.expected_mission_family !== null && !isMissionFamily(value.expected_mission_family))
    || value.label_source !== "offline_evaluation_manifest") return null;

  if ((value.expected_status === "not_generated") !== (value.expected_mission_family === null)) {
    return null;
  }
  return value as StudioScenarioDescriptorV2;
}

export function sameStudioScenarioVersion(
  expected: StudioScenarioDescriptorV2,
  actual: StudioScenarioDescriptorV2,
) {
  return expected.scenario_id === actual.scenario_id
    && expected.fixture_sha256 === actual.fixture_sha256
    && expected.fixture_revision === actual.fixture_revision;
}

export function parseStudioScenarioCatalog(value: unknown): StudioScenarioCatalogV2 | null {
  if (!isRecord(value) || value.schema_version !== "2.1" || !Array.isArray(value.scenarios)) {
    return null;
  }
  const scenarios = value.scenarios.map(parseStudioScenarioDescriptor);
  if (scenarios.some((scenario) => scenario === null)) return null;
  const parsed = scenarios as StudioScenarioDescriptorV2[];
  if (parsed.length !== studioScenarioIds.length
    || new Set(parsed.map((scenario) => scenario.scenario_id)).size !== parsed.length
    || !studioScenarioIds.every((scenarioId) => parsed.some((scenario) => scenario.scenario_id === scenarioId))) {
    return null;
  }
  return { schema_version: "2.1", scenarios: parsed };
}

function isTelemetryMatchSummary(value: unknown): value is StudioScenarioTelemetrySummaryV2["matches"][number] {
  return isRecord(value)
    && typeof value.match_id === "string"
    && typeof value.game === "string"
    && typeof value.mode === "string"
    && (value.map_name === null || typeof value.map_name === "string")
    && typeof value.started_at === "string"
    && Number.isFinite(Date.parse(value.started_at))
    && (value.placement === null || isNonNegativeInteger(value.placement))
    && isNonNegativeInteger(value.event_count);
}

function isTelemetrySummary(value: unknown): value is StudioScenarioTelemetrySummaryV2 {
  return isRecord(value)
    && typeof value.request_id === "string"
    && typeof value.target_player_id === "string"
    && isNonNegativeInteger(value.match_count)
    && isNonNegativeInteger(value.raw_event_count)
    && isNonNegativeInteger(value.consent_safe_player_count)
    && isNonNegativeInteger(value.invitation_eligible_count)
    && isNonNegativeInteger(value.active_player_count)
    && Array.isArray(value.matches)
    && value.matches.every(isTelemetryMatchSummary)
    && value.matches.length === value.match_count;
}

export function parseStudioScenarioPreparation(value: unknown): StudioScenarioPreparationV2 | null {
  if (!isRecord(value)
    || value.schema_version !== "2.1"
    || !parseStudioScenarioDescriptor(value.scenario)
    || !["ready", "rejected"].includes(String(value.status))
    || !isTelemetrySummary(value.telemetry_summary)
    || !isRecord(value.normalization)
    || !isNonNegativeInteger(value.normalization.normalized_match_count)
    || !isNonNegativeInteger(value.normalization.normalized_event_count)
    || !isStringArray(value.normalization.issue_codes)
    || !isRecord(value.privacy)
    || !isNonNegativeInteger(value.privacy.redaction_count)
    || !isNonNegativeInteger(value.privacy.anonymous_player_count)
    || !Array.isArray(value.eligible_windows)
    || !value.eligible_windows.every(isEligibleWindow)
    || !Array.isArray(value.mission_candidates)
    || !value.mission_candidates.every(isMissionCandidate)
    || !Array.isArray(value.mission_affordances)
    || !value.mission_affordances.every(isMissionAffordance)) return null;

  const candidates = value.mission_candidates as StudioInterpretationTraceV2["mission_candidates"];
  const candidateById = new Map(candidates.map((item) => [item.candidate_id, item]));
  const candidateIds = new Set(candidateById.keys());
  const windowIds = new Set(value.eligible_windows.map((item) => item.window_id));
  const issueCodes = value.normalization.issue_codes as string[];
  if ((value.status === "ready"
      && (issueCodes.length > 0
        || value.eligible_windows.length === 0
        || value.mission_candidates.length === 0
        || value.mission_affordances.length === 0))
    || (value.status === "rejected" && issueCodes.length === 0)
    || value.mission_candidates.some((candidate) => !windowIds.has(candidate.window_id))) {
    return null;
  }
  if ((value.mission_affordances as MissionAffordanceV2[]).some((affordance) =>
    !windowIds.has(affordance.window_id)
    || affordance.objective_candidate_ids.some((candidateId) => !candidateIds.has(candidateId))
    || !hasValidAffordanceObjectiveGrammar(affordance, candidateById))) {
    return null;
  }
  return value as StudioScenarioPreparationV2;
}

export function parseStudioScenarioInterpretation(value: unknown): StudioScenarioInterpretationV2 | null {
  if (!isRecord(value) || value.schema_version !== "2.1") return null;
  const scenario = parseStudioScenarioDescriptor(value.scenario);
  const result = parseStudioInterpretDeliveryV2(value.result);
  if (!scenario || !result) return null;
  return { schema_version: "2.1", scenario, result };
}

export function parseStudioScenarioRun(value: unknown): StudioScenarioRunV2 | null {
  const interpreted = parseStudioScenarioInterpretation(value);
  if (!interpreted || !isRecord(value)) return null;
  const origin = value.content_origin;
  if (!["live_ai_validated", "no_player_content", "saved_live_replay"].includes(String(origin))) {
    return null;
  }
  const expectedOrigin = interpreted.result.status === "pending_player_decision"
    ? "live_ai_validated"
    : "no_player_content";
  if (origin !== "saved_live_replay" && origin !== expectedOrigin) return null;
  if (origin === "saved_live_replay") {
    const expectedReplayInnerOrigin = interpreted.result.status === "pending_player_decision"
      ? "saved_live_replay"
      : "no_player_content";
    if (interpreted.result.metadata.content_origin !== expectedReplayInnerOrigin) return null;
    if (!isRecord(value.replay_provenance)
      || typeof value.replay_provenance.provider !== "string"
      || typeof value.replay_provenance.model !== "string"
      || typeof value.replay_provenance.prompt_version !== "string"
      || value.replay_provenance.result_schema_version !== "2.1"
      || typeof value.replay_provenance.captured_at !== "string"
      || !Number.isFinite(Date.parse(value.replay_provenance.captured_at))) return null;
  } else if (value.replay_provenance !== null) {
    return null;
  } else if (interpreted.result.status === "pending_player_decision"
    && (interpreted.result.metadata.mode !== "live_ai"
      || interpreted.result.metadata.content_origin !== "live_ai_validated")) {
    return null;
  }
  return {
    ...interpreted,
    content_origin: origin as StudioScenarioRunV2["content_origin"],
    replay_provenance: value.replay_provenance as StudioScenarioRunV2["replay_provenance"],
  };
}

export function studioScenarioActual(result: StudioInterpretDeliveryResultV2) {
  return {
    status: result.status === "pending_player_decision" ? result.status : result.status,
    mission_family: result.status === "pending_player_decision"
      ? result.next_chapter.family
      : null,
  };
}
