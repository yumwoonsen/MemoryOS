export type ConsentPermissionsV2 = {
  memory_appearance: boolean;
  identity_display: boolean;
  media_use: boolean;
  mission_invitation: boolean;
};

export type RawSquadPlayerV2 = {
  player_id: string;
  display_name?: string;
  consent: ConsentPermissionsV2;
};

export type RawTelemetryEventV2 = {
  event_id: string;
  provider_event_type: string;
  actor_id?: string;
  target_id?: string;
  timestamp_seconds: number;
  location?: string;
  details: Record<string, string | number | boolean | string[]>;
};

export type RawTelemetryMatchV2 = {
  match_id: string;
  game: string;
  mode: string;
  map_name?: string;
  started_at: string;
  ended_at?: string;
  placement?: number;
  result?: string;
  events: RawTelemetryEventV2[];
};

export type RawTelemetryBatchV2 = {
  schema_version: "2.0" | "2.1";
  request_id: string;
  target_player_id: string;
  squad: {
    squad_id: string;
    players: RawSquadPlayerV2[];
  };
  matches: RawTelemetryMatchV2[];
  squad_history: {
    previous_session_at: string[];
    days_since_full_squad?: number;
    recent_rematch_count: number;
  };
  current_context: {
    active_player_ids: string[];
    available_modes: string[];
    reunion_eligible: boolean;
  };
  social_context?: {
    reaction_counts: Record<string, number>;
    saved_clip: boolean;
    event_tags: string[];
    player_caption?: string;
    caption_author_player_id?: string;
  };
  media_references: Array<{
    media_id: string;
    kind: "clip" | "thumbnail" | "keyframe";
    event_ids: string[];
    consented_player_ids: string[];
  }>;
};

export type DeliveryDeclineReasonV2 = "not_relevant" | "details_wrong";

export type MissionFamilyV2 =
  | "reunion"
  | "role_reversal"
  | "redemption"
  | "return_to_place"
  | "landing_rendezvous"
  | "duo_assist";

export type MissionObjectiveRoleV2 =
  | "prerequisite"
  | "primary"
  | "support"
  | "bonus"
  | "completion";

export type MissionCompatibilityTagV2 =
  | "squad_entry"
  | "location"
  | "individual_assignment"
  | "squad_coordination"
  | "combat"
  | "support_action"
  | "tactical"
  | "vehicle"
  | "placement"
  | "match_completion";

export type MissionAffordanceV2 = {
  affordance_id: string;
  family: MissionFamilyV2;
  window_id: string;
  source_event_ids: string[];
  source_match_ids: string[];
  source_context_ids: string[];
  parameters: Record<string, string | number | boolean | string[]>;
  objective_candidate_ids: string[];
  allowed_reason_codes: string[];
};

export type MissionSelectionV2 = {
  ranked_affordance_ids: string[];
  selected_affordance_id: string;
  selected_family: MissionFamilyV2;
  reason_codes: string[];
};

export type GroundedClaimV2 = {
  claim_id: string;
  output_section: string;
  subject_id: string;
  predicate: string;
  target_id?: string | null;
  location?: string | null;
  value?: string | number | boolean | string[] | null;
  supporting_event_ids: string[];
  supporting_context_ids: string[];
  supporting_mission_candidate_ids: string[];
};

export type PlayerPerspectiveV2 = {
  player_id: string;
  display_name: string;
  message: string;
  evidence_event_ids: string[];
};

export type MissionObjectiveV2 = {
  objective_id: string;
  description: string;
  assigned_player_id?: string | null;
  objective_role: MissionObjectiveRoleV2;
  required: boolean;
  verification: {
    metric: string;
    operator: "equals" | "at_least" | "contains_all";
    target: string | number | boolean | string[];
  };
  source_event_ids: string[];
};

export type StudioTraceStageV2 = {
  stage: "deterministic_preparation" | "ai_interpretation" | "deterministic_validation" | "player_decision";
  status: "complete" | "rejected" | "withheld" | "pending";
  summary: string;
  issue_codes: string[];
};

export type StudioInterpretationTraceV2 = {
  trace_id: string;
  stages: StudioTraceStageV2[];
  normalized_match_count: number;
  normalized_event_count: number;
  privacy_redaction_count: number;
  eligible_windows: Array<{
    window_id: string;
    match_id: string;
    event_ids: string[];
    participant_ids: string[];
    start_seconds: number;
    end_seconds: number;
  }>;
  mission_candidates: Array<{
    candidate_id: string;
    window_id: string;
    recipe: string;
    objective_role: MissionObjectiveRoleV2;
    required: boolean;
    compatibility_tags: MissionCompatibilityTagV2[];
    assigned_player_id?: string | null;
    source_event_ids: string[];
    verification: MissionObjectiveV2["verification"];
  }>;
  mission_affordances: MissionAffordanceV2[];
  mission_selection: MissionSelectionV2 | null;
  active_player_count: number;
  invitation_eligible_count: number;
  claim_mappings: Array<{
    claim_id: string;
    output_section: string;
    predicate: string;
    evidence_ids: string[];
  }>;
  correction_attempted: boolean;
  source_quality_flag: boolean;
};

export type PendingDeliveryV2 = {
  schema_version: "2.1";
  request_id: string;
  delivery_id: string;
  status: "pending_player_decision";
  reason_codes: string[];
  memory: {
    title: string;
    memory_type: string;
    summary: string;
    notification_teaser: string;
    why_this_matters_now: string;
    selected_match_id: string;
    selected_event_ids: string[];
    media_reference?: {
      media_id: string;
      kind: "clip" | "thumbnail" | "keyframe";
      event_ids: string[];
      consented_player_ids: string[];
    } | null;
  };
  player_perspectives: PlayerPerspectiveV2[];
  next_chapter: {
    title: string;
    mission: string;
    recipe: "recreate" | "remix" | "resolve" | string;
    family: MissionFamilyV2;
    invitation_player_ids: string[];
    objectives: MissionObjectiveV2[];
  };
  grounded_claims: GroundedClaimV2[];
  validation: {
    passed: true;
    correction_attempted: boolean;
    issues: Array<{ code: string; severity?: string; message?: string }>;
  };
  studio_trace: StudioInterpretationTraceV2;
  metadata: {
    provider: string;
    model: string;
    mode: "live_ai";
    prompt_version: string;
    content_origin: "live_ai_validated";
    grounded_render: boolean;
    narrative_fallback: boolean;
  };
};

export type RejectedInterpretationV2 = {
  schema_version: "2.1";
  request_id: string;
  status: "rejected";
  reason_codes: string[];
  player_perspectives: [];
  validation: {
    passed: false;
    correction_attempted: boolean;
    issues: Array<{ code: string; severity?: string; message?: string }>;
  };
  studio_trace: StudioInterpretationTraceV2;
  metadata: {
    provider: string;
    model: string;
    mode: "live_ai" | "deterministic";
    prompt_version: string;
    content_origin: "no_player_content";
    grounded_render: boolean;
    narrative_fallback: boolean;
  };
};

export type NotGeneratedInterpretationV2 = {
  schema_version: "2.1";
  request_id: string;
  status: "not_generated";
  reason_codes: ["ai_no_meaningful_episode"] | string[];
  player_perspectives: [];
  validation: {
    passed: true;
    correction_attempted: boolean;
    issues: Array<{ code: string; severity?: string; message?: string }>;
  };
  studio_trace: StudioInterpretationTraceV2;
  metadata: {
    provider: string;
    model: string;
    mode: "live_ai";
    prompt_version: string;
    content_origin: "no_player_content";
    grounded_render: boolean;
    narrative_fallback: boolean;
  };
};

export type InterpretDeliveryResultV2 = PendingDeliveryV2 | RejectedInterpretationV2 | NotGeneratedInterpretationV2;

export type StudioPendingDeliveryV2 = Omit<PendingDeliveryV2, "metadata"> & {
  metadata: Omit<PendingDeliveryV2["metadata"], "mode" | "content_origin"> & {
    mode: "live_ai" | "deterministic";
    content_origin: "live_ai_validated" | "deterministic_studio_sample" | "saved_live_replay";
  };
};

export type StudioInterpretDeliveryResultV2 = StudioPendingDeliveryV2 | RejectedInterpretationV2 | NotGeneratedInterpretationV2;

export type DecisionRequestV2 =
  | { schema_version: "2.0"; decision: "accepted" }
  | { schema_version: "2.0"; decision: "declined"; decline_reason: DeliveryDeclineReasonV2 };

export type DeliveryDecisionRecordV2 = {
  schema_version: "2.0";
  delivery_id: string;
  decision: "accepted" | "declined";
  decline_reason?: DeliveryDeclineReasonV2 | null;
  delivery_status: "mission_started" | "suppressed";
  source_quality_flag: boolean;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isRuleTarget(value: unknown) {
  return typeof value === "string"
    || (typeof value === "number" && Number.isFinite(value))
    || typeof value === "boolean"
    || (Array.isArray(value) && value.every((item) => typeof item === "string"));
}

function isMissionObjective(value: unknown): value is MissionObjectiveV2 {
  return isRecord(value)
    && typeof value.objective_id === "string"
    && typeof value.description === "string"
    && (value.assigned_player_id == null || typeof value.assigned_player_id === "string")
    && ["prerequisite", "primary", "support", "bonus", "completion"]
      .includes(String(value.objective_role))
    && typeof value.required === "boolean"
    && (value.objective_role === "bonus" ? value.required === false : value.required === true)
    && isRecord(value.verification)
    && typeof value.verification.metric === "string"
    && ["equals", "at_least", "contains_all"].includes(String(value.verification.operator))
    && isRuleTarget(value.verification.target)
    && isStringArray(value.source_event_ids);
}

function hasValidMissionObjectiveGrammar(value: unknown, family: unknown) {
  if (!isMissionFamily(family)
    || !Array.isArray(value)
    || value.length < 2
    || value.length > 5
    || !value.every(isMissionObjective)) return false;
  const objectives = value as MissionObjectiveV2[];
  const roles = objectives.map((objective) => objective.objective_role);
  const expectedPrimaryCount = family === "reunion" ? 0 : 1;
  return roles[0] === "prerequisite"
    && roles.at(-1) === "completion"
    && roles.filter((role) => role === "prerequisite").length === 1
    && roles.filter((role) => role === "completion").length === 1
    && roles.filter((role) => role === "primary").length === expectedPrimaryCount
    && roles.filter((role) => role === "support").length <= 2
    && roles.filter((role) => role === "bonus").length <= 2;
}

function isGroundedClaim(value: unknown): value is GroundedClaimV2 {
  return isRecord(value)
    && typeof value.claim_id === "string"
    && typeof value.output_section === "string"
    && typeof value.subject_id === "string"
    && typeof value.predicate === "string"
    && (value.target_id == null || typeof value.target_id === "string")
    && (value.location == null || typeof value.location === "string")
    && (value.value == null || isRuleTarget(value.value))
    && isStringArray(value.supporting_event_ids)
    && isStringArray(value.supporting_context_ids)
    && isStringArray(value.supporting_mission_candidate_ids)
    && (value.supporting_event_ids.length > 0
      || value.supporting_context_ids.length > 0
      || value.supporting_mission_candidate_ids.length > 0);
}

function isPerspective(value: unknown): value is PlayerPerspectiveV2 {
  return isRecord(value)
    && typeof value.player_id === "string"
    && typeof value.display_name === "string"
    && typeof value.message === "string"
    && isStringArray(value.evidence_event_ids)
    && value.evidence_event_ids.length > 0;
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

function isMissionCandidate(
  value: unknown,
): value is StudioInterpretationTraceV2["mission_candidates"][number] {
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
    && isRecord(value.verification)
    && typeof value.verification.metric === "string"
    && ["equals", "at_least", "contains_all"].includes(String(value.verification.operator))
    && isRuleTarget(value.verification.target);
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
function isMissionSelection(value: unknown): value is MissionSelectionV2 {
  return isRecord(value)
    && isStringArray(value.ranked_affordance_ids)
    && typeof value.selected_affordance_id === "string"
    && isMissionFamily(value.selected_family)
    && isStringArray(value.reason_codes);
}

function isTrace(value: unknown) {
  return isRecord(value)
    && typeof value.trace_id === "string"
    && Number.isInteger(value.normalized_match_count)
    && Number.isInteger(value.normalized_event_count)
    && Number.isInteger(value.privacy_redaction_count)
    && Array.isArray(value.eligible_windows)
    && Array.isArray(value.mission_candidates)
    && value.mission_candidates.every(isMissionCandidate)
    && Array.isArray(value.mission_affordances)
    && value.mission_affordances.every(isMissionAffordance)
    && (value.mission_selection == null || isMissionSelection(value.mission_selection))
    && Number.isInteger(value.active_player_count)
    && Number.isInteger(value.invitation_eligible_count)
    && Array.isArray(value.claim_mappings)
    && typeof value.correction_attempted === "boolean"
    && typeof value.source_quality_flag === "boolean"
    && Array.isArray(value.stages)
    && value.stages.every((stage) => isRecord(stage)
      && ["deterministic_preparation", "ai_interpretation", "deterministic_validation", "player_decision"]
        .includes(String(stage.stage))
      && ["complete", "rejected", "withheld", "pending"].includes(String(stage.status))
      && typeof stage.summary === "string"
      && isStringArray(stage.issue_codes));
}

export function parseStudioTraceV2(value: unknown): StudioInterpretationTraceV2 | null {
  return isTrace(value) ? value as StudioInterpretationTraceV2 : null;
}

function isRawSquadPlayer(value: unknown): value is RawSquadPlayerV2 {
  if (!isRecord(value)
    || typeof value.player_id !== "string"
    || (value.display_name !== undefined && typeof value.display_name !== "string")
    || !isRecord(value.consent)) return false;
  const consent = value.consent;
  return ["memory_appearance", "identity_display", "media_use", "mission_invitation"]
    .every((permission) => typeof consent[permission] === "boolean");
}

export function parseRawTelemetryBatchV2(value: unknown): RawTelemetryBatchV2 | null {
  if (!isRecord(value)
    || !["2.0", "2.1"].includes(String(value.schema_version))
    || typeof value.request_id !== "string"
    || typeof value.target_player_id !== "string"
    || !isRecord(value.squad)
    || typeof value.squad.squad_id !== "string"
    || !Array.isArray(value.squad.players)
    || value.squad.players.length < 2
    || !Array.isArray(value.matches)
    || value.matches.length < 1
    || value.matches.length > 50
    || !isRecord(value.squad_history)
    || !isRecord(value.current_context)
    || !Array.isArray(value.media_references)) return null;

  const players = value.squad.players;
  if (!players.every(isRawSquadPlayer)) return null;

  const playerIds = players.map((player) => String((player as Record<string, unknown>).player_id));
  if (new Set(playerIds).size !== playerIds.length || !playerIds.includes(value.target_player_id)) return null;

  const allEventIds: string[] = [];
  for (const match of value.matches) {
    if (!isRecord(match)
      || typeof match.match_id !== "string"
      || typeof match.game !== "string"
      || typeof match.mode !== "string"
      || typeof match.started_at !== "string"
      || !Array.isArray(match.events)) return null;
    for (const event of match.events) {
      if (!isRecord(event)
        || typeof event.event_id !== "string"
        || typeof event.provider_event_type !== "string"
        || !Number.isFinite(event.timestamp_seconds)
        || !isRecord(event.details)) return null;
      allEventIds.push(event.event_id);
    }
  }
  if (new Set(allEventIds).size !== allEventIds.length) return null;

  return value as RawTelemetryBatchV2;
}

function hasPendingPlayerContent(value: Record<string, unknown>) {
  return typeof value.delivery_id === "string"
    && isRecord(value.memory)
    && typeof value.memory.title === "string"
    && typeof value.memory.memory_type === "string"
    && typeof value.memory.summary === "string"
    && typeof value.memory.notification_teaser === "string"
    && typeof value.memory.why_this_matters_now === "string"
    && typeof value.memory.selected_match_id === "string"
    && isStringArray(value.memory.selected_event_ids)
    && value.memory.selected_event_ids.length > 0
    && (value.memory.media_reference == null
      || (isRecord(value.memory.media_reference)
        && typeof value.memory.media_reference.media_id === "string"
        && ["clip", "thumbnail", "keyframe"].includes(String(value.memory.media_reference.kind))
        && isStringArray(value.memory.media_reference.event_ids)
        && isStringArray(value.memory.media_reference.consented_player_ids)))
    && Array.isArray(value.player_perspectives)
    && value.player_perspectives.length >= 2
    && value.player_perspectives.every(isPerspective)
    && isRecord(value.next_chapter)
    && typeof value.next_chapter.title === "string"
    && typeof value.next_chapter.mission === "string"
    && typeof value.next_chapter.recipe === "string"
    && isMissionFamily(value.next_chapter.family)
    && isStringArray(value.next_chapter.invitation_player_ids)
    && new Set(value.next_chapter.invitation_player_ids).size === value.next_chapter.invitation_player_ids.length
    && hasValidMissionObjectiveGrammar(value.next_chapter.objectives, value.next_chapter.family);
}

export function parseStudioInterpretDeliveryV2(value: unknown): StudioInterpretDeliveryResultV2 | null {
  if (!isRecord(value)
    || value.schema_version !== "2.1"
    || typeof value.request_id !== "string"
    || !["pending_player_decision", "not_generated", "rejected"].includes(String(value.status))
    || !isStringArray(value.reason_codes)
    || !isRecord(value.validation)
    || typeof value.validation.passed !== "boolean"
    || typeof value.validation.correction_attempted !== "boolean"
    || !Array.isArray(value.validation.issues)
    || !isTrace(value.studio_trace)
    || !isRecord(value.metadata)
    || typeof value.metadata.provider !== "string"
    || typeof value.metadata.model !== "string"
    || typeof value.metadata.prompt_version !== "string"
    || typeof value.metadata.grounded_render !== "boolean"
    || typeof value.metadata.narrative_fallback !== "boolean") return null;

  if (value.status === "not_generated") {
    if (value.delivery_id != null
      || value.memory != null
      || value.next_chapter != null
      || (Array.isArray(value.player_perspectives) && value.player_perspectives.length > 0)
      || value.validation.passed !== true
      || value.metadata.mode !== "live_ai"
      || value.metadata.content_origin !== "no_player_content"
      || value.metadata.grounded_render !== false
      || value.metadata.narrative_fallback !== false
      || !value.reason_codes.includes("ai_no_meaningful_episode")) return null;
    return value as NotGeneratedInterpretationV2;
  }

  if (value.status === "rejected") {
    if (value.delivery_id != null
      || value.memory != null
      || value.next_chapter != null
      || (Array.isArray(value.player_perspectives) && value.player_perspectives.length > 0)
      || value.validation.passed !== false
      || value.metadata.content_origin !== "no_player_content"
      || value.metadata.grounded_render !== false
      || value.metadata.narrative_fallback !== false) return null;
    return value as RejectedInterpretationV2;
  }

  if (!hasPendingPlayerContent(value)
    || value.validation.passed !== true
    || !["live_ai", "deterministic"].includes(String(value.metadata.mode))
    || !["live_ai_validated", "deterministic_studio_sample", "saved_live_replay"]
      .includes(String(value.metadata.content_origin))
    || value.metadata.grounded_render !== false
    || value.metadata.narrative_fallback !== false
    || !Array.isArray(value.grounded_claims)
    || value.grounded_claims.length === 0
    || !value.grounded_claims.every(isGroundedClaim)) return null;
  if (!isRecord(value.next_chapter)
    || !isMissionFamily(value.next_chapter.family)
    || !isStringArray(value.next_chapter.invitation_player_ids)
    || !isRecord(value.studio_trace)
    || !isMissionSelection(value.studio_trace.mission_selection)) return null;

  const nextChapter = value.next_chapter as PendingDeliveryV2["next_chapter"];
  const trace = value.studio_trace as unknown as StudioInterpretationTraceV2;
  const selection = trace.mission_selection;
  const selectedAffordance = selection
    ? trace.mission_affordances.find(
        (affordance) => affordance.affordance_id === selection.selected_affordance_id,
      )
    : null;
  const deliveredObjectiveIds = new Set(
    nextChapter.objectives.map((objective) => objective.objective_id),
  );
  if (!selection
    || !selection.ranked_affordance_ids.includes(selection.selected_affordance_id)
    || selection.selected_family !== nextChapter.family
    || selectedAffordance?.family !== nextChapter.family
    || selectedAffordance.objective_candidate_ids.length !== deliveredObjectiveIds.size
    || !selectedAffordance.objective_candidate_ids.every(
      (candidateId) => deliveredObjectiveIds.has(candidateId),
    )) return null;

  return value as StudioPendingDeliveryV2;
}

export function parseInterpretDeliveryV2(value: unknown): InterpretDeliveryResultV2 | null {
  const parsed = parseStudioInterpretDeliveryV2(value);
  if (parsed?.status === "pending_player_decision"
    && (parsed.metadata.mode !== "live_ai"
      || parsed.metadata.grounded_render === true
      || parsed.metadata.narrative_fallback === true
      || parsed.metadata.content_origin !== "live_ai_validated")) return null;
  return parsed as InterpretDeliveryResultV2 | null;
}

type PlayerVisibleDeliveryV2 = PendingDeliveryV2;

function validatePlayerVisibleBinding(
  delivery: PlayerVisibleDeliveryV2,
  telemetry: RawTelemetryBatchV2,
) {
  if (delivery.request_id !== telemetry.request_id) return false;
  const selectedMatch = telemetry.matches.find((match) => match.match_id === delivery.memory.selected_match_id);
  if (!selectedMatch) return false;
  const eventIds = new Set(selectedMatch.events.map((event) => event.event_id));
  if (new Set(delivery.memory.selected_event_ids).size !== delivery.memory.selected_event_ids.length
    || !delivery.memory.selected_event_ids.every((eventId) => eventIds.has(eventId))) return false;

  const eligiblePlayers = telemetry.squad.players.filter((player) => player.consent.memory_appearance);
  const eligibleById = new Map(eligiblePlayers.map((player) => [player.player_id, player]));
  if (!eligibleById.has(telemetry.target_player_id)) return false;
  if (delivery.player_perspectives.length !== eligibleById.size) return false;
  const perspectiveIds = new Set<string>();
  for (const perspective of delivery.player_perspectives) {
    const player = eligibleById.get(perspective.player_id);
    if (!player
      || player.display_name !== perspective.display_name
      || perspectiveIds.has(perspective.player_id)
      || !perspective.evidence_event_ids.every((eventId) => eventIds.has(eventId))) return false;
    perspectiveIds.add(perspective.player_id);
  }

  const objectiveIds = new Set<string>();
  for (const objective of delivery.next_chapter.objectives) {
    if (objectiveIds.has(objective.objective_id)) return false;
    objectiveIds.add(objective.objective_id);
    if (objective.assigned_player_id) {
      const assignee = eligibleById.get(objective.assigned_player_id);
      if (!assignee?.consent.mission_invitation) return false;
    }
    if (!objective.source_event_ids.every((eventId) => eventIds.has(eventId))) return false;
  }

  if (delivery.memory.media_reference) {
    const deliveredMedia = delivery.memory.media_reference;
    const media = telemetry.media_references.find((item) => item.media_id === deliveredMedia.media_id);
    if (!media
      || media.kind !== deliveredMedia.kind
      || media.event_ids.join("|") !== deliveredMedia.event_ids.join("|")
      || media.consented_player_ids.join("|") !== deliveredMedia.consented_player_ids.join("|")
      || !deliveredMedia.event_ids.some((eventId) => delivery.memory.selected_event_ids.includes(eventId))
      || !deliveredMedia.consented_player_ids.every((playerId) => eligibleById.get(playerId)?.consent.media_use)) return false;
  }

  return { selectedMatch, eventIds, eligibleById, objectiveIds };
}

export function isDeliveryBoundToTelemetryV2(
  delivery: PendingDeliveryV2,
  telemetry: RawTelemetryBatchV2,
) {
  const binding = validatePlayerVisibleBinding(delivery, telemetry);
  if (!binding) return false;

  const allowedContextIds = new Set([
    "context:days_since_full_squad",
    "context:previous_session_at",
    "context:recent_rematch_count",
    "context:active_player_ids",
    "context:available_modes",
    "context:reunion_eligible",
    `match:${binding.selectedMatch.match_id}:game`,
    `match:${binding.selectedMatch.match_id}:mode`,
  ]);
  if (binding.selectedMatch.map_name) allowedContextIds.add(`match:${binding.selectedMatch.match_id}:map`);
  if (binding.selectedMatch.placement !== undefined) allowedContextIds.add(`match:${binding.selectedMatch.match_id}:placement`);
  if (binding.selectedMatch.result) allowedContextIds.add(`match:${binding.selectedMatch.match_id}:result`);
  const allowedClaimIdentity = (playerId: string) =>
    playerId === "squad" || playerId.startsWith("anonymous:") || binding.eligibleById.has(playerId);

  for (const claim of delivery.grounded_claims) {
    if (!claim.supporting_event_ids.every((eventId) => binding.eventIds.has(eventId))) return false;
    if (!allowedClaimIdentity(claim.subject_id)) return false;
    if (claim.target_id && !allowedClaimIdentity(claim.target_id)) return false;
    if (!claim.supporting_context_ids.every((contextId) => allowedContextIds.has(contextId))) return false;
    if (!claim.supporting_mission_candidate_ids.every((candidateId) => binding.objectiveIds.has(candidateId))) return false;
  }
  return true;
}

export function parseDecisionConfirmationV2(
  value: unknown,
  deliveryId: string,
  request: DecisionRequestV2,
): DeliveryDecisionRecordV2 | null {
  if (!isRecord(value)
    || value.schema_version !== "2.0"
    || value.delivery_id !== deliveryId
    || value.decision !== request.decision
    || !["mission_started", "suppressed"].includes(String(value.delivery_status))
    || typeof value.source_quality_flag !== "boolean") return null;
  if (request.decision === "accepted") {
    if (value.decline_reason != null || value.delivery_status !== "mission_started") return null;
  } else if (value.decline_reason !== request.decline_reason || value.delivery_status !== "suppressed") {
    return null;
  }
  return value as DeliveryDecisionRecordV2;
}

export function eligibleDisplayPlayers(telemetry: RawTelemetryBatchV2) {
  return telemetry.squad.players.filter((player) => player.consent.memory_appearance);
}

export function eligibleInvitationPlayers(telemetry: RawTelemetryBatchV2) {
  return telemetry.squad.players.filter((player) =>
    player.consent.memory_appearance
    && player.consent.mission_invitation);
}

export function consentSafeTelemetryView(telemetry: RawTelemetryBatchV2): RawTelemetryBatchV2 {
  const anonymousById = new Map(
    telemetry.squad.players.flatMap((player, index) =>
      !player.consent.memory_appearance || !player.consent.identity_display || !player.display_name
        ? [[player.player_id, `anonymous:squadmate:${index + 1}`] as const]
        : [],
    ),
  );
  const safeId = (playerId?: string) => playerId ? (anonymousById.get(playerId) ?? playerId) : undefined;

  return {
    ...telemetry,
    target_player_id: safeId(telemetry.target_player_id) ?? telemetry.target_player_id,
    squad: {
      ...telemetry.squad,
      players: telemetry.squad.players.map((player, index) => anonymousById.has(player.player_id)
        ? {
            player_id: anonymousById.get(player.player_id)!,
            ...(player.consent.memory_appearance ? { display_name: `Player ${index + 1}` } : {}),
            consent: { ...player.consent },
          }
        : { ...player, consent: { ...player.consent } }),
    },
    matches: telemetry.matches.map((match) => ({
      ...match,
      events: match.events.map((event) => ({
        ...event,
        ...(event.actor_id ? { actor_id: safeId(event.actor_id) } : {}),
        ...(event.target_id ? { target_id: safeId(event.target_id) } : {}),
        details: { ...event.details },
      })),
    })),
    current_context: {
      ...telemetry.current_context,
      active_player_ids: telemetry.current_context.active_player_ids.map((playerId) => safeId(playerId)!),
      available_modes: [...telemetry.current_context.available_modes],
    },
    ...(telemetry.social_context
      ? {
          social_context: {
            ...telemetry.social_context,
            reaction_counts: { ...telemetry.social_context.reaction_counts },
            event_tags: [...telemetry.social_context.event_tags],
            ...(telemetry.social_context.caption_author_player_id
              ? { caption_author_player_id: safeId(telemetry.social_context.caption_author_player_id) }
              : {}),
          },
        }
      : {}),
    media_references: telemetry.media_references.map((media) => ({
      ...media,
      event_ids: [...media.event_ids],
      consented_player_ids: media.consented_player_ids.map((playerId) => safeId(playerId)!),
    })),
  };
}
