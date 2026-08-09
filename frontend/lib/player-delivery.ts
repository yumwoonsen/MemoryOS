import type {
  MissionFamilyV2,
  MissionObjectiveRoleV2,
  PendingDeliveryV2,
  RawSquadPlayerV2,
  RawTelemetryBatchV2,
  RawTelemetryEventV2,
} from "@/lib/ai-memory-contract";
import type { PlayerExperienceRef } from "@/lib/player-scenarios";

export type PlayerActivityV2 = "online" | "away";

export type PlayerRosterMemberV2 = {
  recipient_ref: string;
  display_name: string;
  activity: PlayerActivityV2;
  is_current_player: boolean;
};

export type PlayerExperienceSeedV2 = {
  schema_version: "2.1";
  experience_ref: PlayerExperienceRef;
  request_id: string;
  current_recipient_ref: string;
  match_preview: {
    game: string;
    mode: string;
    map_name: string | null;
  };
  recent_session_count: number;
  display_roster: Array<Pick<PlayerRosterMemberV2, "recipient_ref" | "display_name" | "activity" | "is_current_player">>;
};

export type PlayerVerifiedMomentV2 = {
  sequence: number;
  label: string;
  location: string | null;
  timestamp_seconds: number;
};

export type PlayerPendingDeliveryProjectionV2 = {
  schema_version: "2.1";
  request_id: string;
  delivery_id: string;
  status: "pending_player_decision";
  memory: {
    title: string;
    memory_type: string;
    summary: string;
    notification_teaser: string;
    why_this_matters_now: string;
  };
  source: {
    game: string;
    mode: string;
    map_name: string | null;
  };
  verified_moments: PlayerVerifiedMomentV2[];
  perspective: {
    recipient_ref: string;
    display_name: string;
    message: string;
  };
  next_chapter: {
    title: string;
    mission: string;
    family: MissionFamilyV2;
    objectives: Array<{
      objective_ref: string;
      description: string;
      objective_role: MissionObjectiveRoleV2;
      required: boolean;
      assigned_recipient_ref?: string;
    }>;
  };
  invitation_roster: PlayerRosterMemberV2[];
  metadata: {
    provider: string;
    model: string;
    prompt_version: string;
    content_origin: "live_ai_validated";
  };
};

export type PlayerNotGeneratedV2 = {
  schema_version: "2.1";
  request_id: string;
  status: "not_generated";
  reason_code: "ai_no_meaningful_episode";
};

export type PlayerDeliveryResultV2 = PlayerPendingDeliveryProjectionV2 | PlayerNotGeneratedV2;
type PlayerMissionObjectiveV2 = PlayerPendingDeliveryProjectionV2["next_chapter"]["objectives"][number];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function scopedRoster(telemetry: RawTelemetryBatchV2) {
  const activeIds = new Set(telemetry.current_context.active_player_ids);
  const visiblePlayers = telemetry.squad.players
    .map((player, rosterIndex) => ({ player, rosterIndex }))
    .filter(({ player }) => player.consent.memory_appearance);
  const refByPlayerId = new Map<string, string>();
  const backendIdByRawId = new Map<string, string>();
  const backendIdByRecipientRef = new Map<string, string>();
  const rawIdByRecipientRef = new Map<string, string>();
  const backendPlayerId = (player: RawSquadPlayerV2, rosterIndex: number) =>
    player.consent.identity_display && player.display_name
      ? player.player_id
      : `anonymous:squadmate:${rosterIndex + 1}`;
  const safeName = (player: RawSquadPlayerV2, rosterIndex: number) =>
    player.consent.identity_display && player.display_name
      ? player.display_name
      : `Player ${rosterIndex + 1}`;

  visiblePlayers.forEach(({ player, rosterIndex }, visibleIndex) => {
    const recipientRef = `recipient-${visibleIndex + 1}`;
    const normalizedPlayerId = backendPlayerId(player, rosterIndex);
    refByPlayerId.set(player.player_id, recipientRef);
    refByPlayerId.set(normalizedPlayerId, recipientRef);
    backendIdByRawId.set(player.player_id, normalizedPlayerId);
    backendIdByRecipientRef.set(recipientRef, normalizedPlayerId);
    rawIdByRecipientRef.set(recipientRef, player.player_id);
  });

  return {
    refByPlayerId,
    backendIdByRawId,
    backendIdByRecipientRef,
    rawIdByRecipientRef,
    roster: visiblePlayers.map(({ player, rosterIndex }): PlayerRosterMemberV2 => ({
      recipient_ref: refByPlayerId.get(player.player_id)!,
      display_name: safeName(player, rosterIndex),
      activity: activeIds.has(player.player_id) ? "online" : "away",
      is_current_player: player.player_id === telemetry.target_player_id,
    })),
  };
}

export function projectTelemetryForPlayerStart(
  telemetry: RawTelemetryBatchV2,
  experienceRef: PlayerExperienceRef,
): PlayerExperienceSeedV2 {
  const { refByPlayerId, roster } = scopedRoster(telemetry);
  const previewMatch = telemetry.matches[0];
  return {
    schema_version: "2.1",
    experience_ref: experienceRef,
    request_id: telemetry.request_id,
    current_recipient_ref: refByPlayerId.get(telemetry.target_player_id) ?? "recipient-current",
    match_preview: {
      game: previewMatch?.game ?? "free_fire",
      mode: previewMatch?.mode ?? "battle_royale_squad",
      map_name: previewMatch?.map_name ?? null,
    },
    recent_session_count: telemetry.squad_history.previous_session_at.length,
    display_roster: roster,
  };
}

function eventDisplayName(playerId: string | undefined, players: RawSquadPlayerV2[]) {
  const player = players.find((candidate) => candidate.player_id === playerId);
  if (!player) return "A squadmate";
  if (!player.consent.memory_appearance || !player.consent.identity_display) return "A squadmate";
  return player.display_name ?? "A squadmate";
}

function verifiedMomentLabel(event: RawTelemetryEventV2, players: RawSquadPlayerV2[]) {
  const actor = eventDisplayName(event.actor_id, players);
  const target = eventDisplayName(event.target_id, players);
  switch (event.provider_event_type) {
    case "TEAMMATE_REVIVED":
      return `${actor} revived ${target}`;
    case "TACTICAL_PING_PLACED":
      return `${actor} placed a tactical signal`;
    case "SQUAD_ENTERED_VEHICLE":
      return "The squad entered a vehicle";
    case "SQUAD_EXITED_DAMAGE_ZONE":
      return "The squad reached safety together";
    case "PLAYER_KNOCKED":
      return `${actor} was knocked`;
    case "SQUAD_MEMBER_LANDED":
      return `${actor} landed with the squad`;
    case "KILL_ASSIST":
    case "ASSIST":
      return `${actor} assisted ${target}`;
    case "PLAYER_ELIMINATED_OPPONENT":
      return `${actor} secured an elimination`;
    case "MATCH_PLACEMENT_RECORDED":
      return typeof event.details.placement === "number"
        ? `The squad finished #${event.details.placement}`
        : "The match result was recorded";
    default:
      return event.provider_event_type
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }
}

function inferMissionFamily(delivery: PendingDeliveryV2): MissionFamilyV2 {
  const supplied = delivery.next_chapter.family;
  if ([
    "reunion",
    "role_reversal",
    "redemption",
    "return_to_place",
    "landing_rendezvous",
    "duo_assist",
  ].includes(supplied)) {
    return supplied as MissionFamilyV2;
  }
  const metrics = delivery.next_chapter.objectives.map((objective) => objective.verification.metric);
  if (metrics.includes("match.first_squad_revive_actor_id")) return "role_reversal";
  if (metrics.includes("match.top_three_reached")) return "redemption";
  if (metrics.includes("match.invited_squad_visits_location")) return "return_to_place";
  if (metrics.includes("match.invited_squad_lands_at_location")) return "landing_rendezvous";
  if (metrics.includes("match.assigned_player_assisted_elimination_player_ids")) return "duo_assist";
  return "reunion";
}

function projectPlayerMissionObjectives(
  delivery: PendingDeliveryV2,
  refByPlayerId: Map<string, string>,
): PlayerMissionObjectiveV2[] {
  return delivery.next_chapter.objectives.map((objective, index) => ({
    objective_ref: `objective-${index + 1}`,
    description: objective.description,
    objective_role: objective.objective_role,
    required: objective.required,
    ...(objective.assigned_player_id && refByPlayerId.has(objective.assigned_player_id)
      ? { assigned_recipient_ref: refByPlayerId.get(objective.assigned_player_id) }
      : {}),
  }));
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function playerFacingTextLeaksIdentity(
  delivery: PendingDeliveryV2,
  targetPerspective: PendingDeliveryV2["player_perspectives"][number],
  telemetry: RawTelemetryBatchV2,
) {
  const authoredText = [
    delivery.memory.title,
    delivery.memory.summary,
    delivery.memory.notification_teaser,
    delivery.memory.why_this_matters_now,
    targetPerspective.display_name,
    targetPerspective.message,
    delivery.next_chapter.title,
    delivery.next_chapter.mission,
    ...delivery.next_chapter.objectives.map((objective) => objective.description),
  ];
  const loweredText = authoredText.join("\n").toLocaleLowerCase("en");
  const forbiddenIds = telemetry.squad.players.flatMap((player, index) => [
    player.player_id,
    `anonymous:squadmate:${index + 1}`,
  ]);
  if (forbiddenIds.some((identifier) => loweredText.includes(identifier.toLocaleLowerCase("en")))) {
    return true;
  }

  const hiddenNames = telemetry.squad.players.flatMap((player) =>
    (!player.consent.memory_appearance || !player.consent.identity_display || !player.display_name)
      && player.display_name
      ? [player.display_name]
      : []);
  return hiddenNames.some((name) => {
    const pattern = new RegExp(`(?:^|[^\\p{L}\\p{N}])${escapeRegExp(name)}(?:$|[^\\p{L}\\p{N}])`, "iu");
    return authoredText.some((text) => pattern.test(text));
  });
}

export function projectPendingDeliveryForPlayer(
  delivery: PendingDeliveryV2,
  telemetry: RawTelemetryBatchV2,
): PlayerPendingDeliveryProjectionV2 | null {
  const sourceMatch = telemetry.matches.find((match) => match.match_id === delivery.memory.selected_match_id);
  const scoped = scopedRoster(telemetry);
  const backendTargetId = scoped.backendIdByRawId.get(telemetry.target_player_id);
  const targetPerspective = delivery.player_perspectives.find(
    (perspective) => perspective.player_id === backendTargetId,
  );
  if (!sourceMatch || !targetPerspective) return null;
  if (playerFacingTextLeaksIdentity(delivery, targetPerspective, telemetry)) return null;

  const contentOrigin = delivery.metadata.content_origin
    ?? (delivery.metadata.mode === "live_ai"
      && delivery.metadata.grounded_render !== true
      && delivery.metadata.narrative_fallback !== true
      ? "live_ai_validated"
      : null);
  if (contentOrigin !== "live_ai_validated") return null;

  const { refByPlayerId, roster, backendIdByRecipientRef, rawIdByRecipientRef } = scoped;
  const currentRef = refByPlayerId.get(telemetry.target_player_id);
  if (!currentRef) return null;
  const backendInvitationIds = delivery.next_chapter.invitation_player_ids?.length
    ? delivery.next_chapter.invitation_player_ids
    : telemetry.squad.players
      .filter((player) => player.consent.memory_appearance && player.consent.mission_invitation)
      .map((player) => player.player_id);
  const invitationIds = new Set(backendInvitationIds);
  const invitationRoster = roster.filter((member) => {
    const backendId = backendIdByRecipientRef.get(member.recipient_ref);
    const rawId = rawIdByRecipientRef.get(member.recipient_ref);
    return Boolean(
      (backendId && invitationIds.has(backendId))
      || (rawId && invitationIds.has(rawId)),
    );
  });
  if (!invitationRoster.some((member) => member.is_current_player)) return null;
  const currentRosterMember = invitationRoster.find((member) => member.is_current_player);
  if (!currentRosterMember || currentRosterMember.display_name !== targetPerspective.display_name) return null;

  const eventById = new Map(sourceMatch.events.map((event) => [event.event_id, event]));
  const verifiedMoments = delivery.memory.selected_event_ids
    .map((eventId) => eventById.get(eventId))
    .filter((event): event is RawTelemetryEventV2 => Boolean(event))
    .sort((left, right) => left.timestamp_seconds - right.timestamp_seconds)
    .map((event, index): PlayerVerifiedMomentV2 => ({
      sequence: index + 1,
      label: verifiedMomentLabel(event, telemetry.squad.players),
      location: event.location ?? null,
      timestamp_seconds: event.timestamp_seconds,
    }));
  if (verifiedMoments.length === 0) return null;

  return {
    schema_version: "2.1",
    request_id: delivery.request_id,
    delivery_id: delivery.delivery_id,
    status: "pending_player_decision",
    memory: {
      title: delivery.memory.title,
      memory_type: delivery.memory.memory_type,
      summary: delivery.memory.summary,
      notification_teaser: delivery.memory.notification_teaser,
      why_this_matters_now: delivery.memory.why_this_matters_now,
    },
    source: {
      game: sourceMatch.game,
      mode: sourceMatch.mode,
      map_name: sourceMatch.map_name ?? null,
    },
    verified_moments: verifiedMoments,
    perspective: {
      recipient_ref: currentRef,
      display_name: currentRosterMember.display_name,
      message: targetPerspective.message,
    },
    next_chapter: {
      title: delivery.next_chapter.title,
      mission: delivery.next_chapter.mission,
      family: inferMissionFamily(delivery),
      objectives: projectPlayerMissionObjectives(delivery, refByPlayerId),
    },
    invitation_roster: invitationRoster,
    metadata: {
      provider: delivery.metadata.provider,
      model: delivery.metadata.model,
      prompt_version: delivery.metadata.prompt_version,
      content_origin: "live_ai_validated",
    },
  };
}

export function projectNotGeneratedForPlayer(requestId: string): PlayerNotGeneratedV2 {
  return {
    schema_version: "2.1",
    request_id: requestId,
    status: "not_generated",
    reason_code: "ai_no_meaningful_episode",
  };
}

function isRosterMember(value: unknown): value is PlayerRosterMemberV2 {
  return isRecord(value)
    && hasOnlyKeys(value, ["recipient_ref", "display_name", "activity", "is_current_player"])
    && typeof value.recipient_ref === "string"
    && typeof value.display_name === "string"
    && ["online", "away"].includes(String(value.activity))
    && typeof value.is_current_player === "boolean";
}

function hasOnlyKeys(value: Record<string, unknown>, allowedKeys: readonly string[]) {
  const allowed = new Set(allowedKeys);
  return Object.keys(value).every((key) => allowed.has(key));
}

function hasValidProjectedObjectiveGrammar(
  objectives: PlayerPendingDeliveryProjectionV2["next_chapter"]["objectives"],
  family: MissionFamilyV2,
) {
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

export function parsePlayerDeliveryResultV2(value: unknown): PlayerDeliveryResultV2 | null {
  if (!isRecord(value)
    || value.schema_version !== "2.1"
    || typeof value.request_id !== "string"
    || !["pending_player_decision", "not_generated"].includes(String(value.status))) return null;

  if (value.status === "not_generated") {
    const allowed = new Set(["schema_version", "request_id", "status", "reason_code"]);
    return value.reason_code === "ai_no_meaningful_episode"
      && Object.keys(value).every((key) => allowed.has(key))
      ? value as PlayerNotGeneratedV2
      : null;
  }

  if (typeof value.delivery_id !== "string"
    || !isRecord(value.memory)
    || !hasOnlyKeys(value.memory, ["title", "memory_type", "summary", "notification_teaser", "why_this_matters_now"])
    || typeof value.memory.title !== "string"
    || typeof value.memory.memory_type !== "string"
    || typeof value.memory.summary !== "string"
    || typeof value.memory.notification_teaser !== "string"
    || typeof value.memory.why_this_matters_now !== "string"
    || !isRecord(value.source)
    || !hasOnlyKeys(value.source, ["game", "mode", "map_name"])
    || typeof value.source.game !== "string"
    || typeof value.source.mode !== "string"
    || (value.source.map_name !== null && typeof value.source.map_name !== "string")
    || !Array.isArray(value.verified_moments)
    || value.verified_moments.length === 0
    || !value.verified_moments.every((moment) => isRecord(moment)
      && hasOnlyKeys(moment, ["sequence", "label", "location", "timestamp_seconds"])
      && Number.isInteger(moment.sequence)
      && typeof moment.label === "string"
      && (moment.location === null || typeof moment.location === "string")
      && Number.isFinite(moment.timestamp_seconds))
    || !isRecord(value.perspective)
    || !hasOnlyKeys(value.perspective, ["recipient_ref", "display_name", "message"])
    || typeof value.perspective.recipient_ref !== "string"
    || typeof value.perspective.display_name !== "string"
    || typeof value.perspective.message !== "string"
    || !isRecord(value.next_chapter)
    || !hasOnlyKeys(value.next_chapter, ["title", "mission", "family", "objectives"])
    || typeof value.next_chapter.title !== "string"
    || typeof value.next_chapter.mission !== "string"
    || ![
      "reunion",
      "role_reversal",
      "redemption",
      "return_to_place",
      "landing_rendezvous",
      "duo_assist",
    ].includes(String(value.next_chapter.family))
    || !Array.isArray(value.next_chapter.objectives)
    || value.next_chapter.objectives.length < 2
    || value.next_chapter.objectives.length > 5
    || !value.next_chapter.objectives.every((objective) => isRecord(objective)
      && hasOnlyKeys(objective, [
        "objective_ref",
        "description",
        "objective_role",
        "required",
        "assigned_recipient_ref",
      ])
      && typeof objective.objective_ref === "string"
      && typeof objective.description === "string"
      && ["prerequisite", "primary", "support", "bonus", "completion"]
        .includes(String(objective.objective_role))
      && typeof objective.required === "boolean"
      && (objective.objective_role === "bonus" ? objective.required === false : objective.required === true)
      && (objective.assigned_recipient_ref === undefined || typeof objective.assigned_recipient_ref === "string"))
    || !Array.isArray(value.invitation_roster)
    || value.invitation_roster.length < 2
    || !value.invitation_roster.every(isRosterMember)
    || !isRecord(value.metadata)
    || !hasOnlyKeys(value.metadata, ["provider", "model", "prompt_version", "content_origin"])
    || typeof value.metadata.provider !== "string"
    || typeof value.metadata.model !== "string"
    || typeof value.metadata.prompt_version !== "string"
    || value.metadata.content_origin !== "live_ai_validated") return null;

  const allowedTopLevel = new Set([
    "schema_version",
    "request_id",
    "delivery_id",
    "status",
    "memory",
    "source",
    "verified_moments",
    "perspective",
    "next_chapter",
    "invitation_roster",
    "metadata",
  ]);
  if (Object.keys(value).some((key) => !allowedTopLevel.has(key))) return null;
  if (new Set(value.invitation_roster.map((member) => member.recipient_ref)).size !== value.invitation_roster.length) return null;
  const recipientRefs = new Set(value.invitation_roster.map((member) => member.recipient_ref));
  if (!hasValidProjectedObjectiveGrammar(
    value.next_chapter.objectives as PlayerPendingDeliveryProjectionV2["next_chapter"]["objectives"],
    value.next_chapter.family as MissionFamilyV2,
  )) return null;
  if (value.next_chapter.objectives.some((objective) =>
    objective.assigned_recipient_ref && !recipientRefs.has(objective.assigned_recipient_ref))) return null;
  const currentPlayers = value.invitation_roster.filter((member) => member.is_current_player);
  if (currentPlayers.length !== 1 || currentPlayers[0].recipient_ref !== value.perspective.recipient_ref) return null;
  return value as PlayerPendingDeliveryProjectionV2;
}

export function isPlayerDeliveryBoundToSeed(
  delivery: PlayerPendingDeliveryProjectionV2,
  seed: PlayerExperienceSeedV2,
) {
  const seedRoster = new Map(seed.display_roster.map((member) => [member.recipient_ref, member]));
  return delivery.request_id === seed.request_id
    && delivery.perspective.recipient_ref === seed.current_recipient_ref
    && delivery.invitation_roster.some((member) =>
      member.is_current_player && member.recipient_ref === seed.current_recipient_ref)
    && delivery.invitation_roster.every((member) => {
      const seeded = seedRoster.get(member.recipient_ref);
      return seeded?.display_name === member.display_name
        && seeded.activity === member.activity
        && seeded.is_current_player === member.is_current_player;
    });
}
