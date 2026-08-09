const selectedEventIds = [
  "ffevt-02-knock-lee",
  "ffevt-03-ping-retreat",
  "ffevt-04-revive-lee",
  "ffevt-05-vehicle-enter",
  "ffevt-06-zone-exit",
];

function safePlayer(player, index) {
  const identityVisible = player.consent.identity_display && player.display_name;
  return {
    player_id: identityVisible ? player.player_id : `anonymous:squadmate:${index + 1}`,
    display_name: identityVisible ? player.display_name : `Player ${index + 1}`,
    consent: player.consent,
  };
}

export function createTestLiveDelivery(telemetry, { studioOrigin = false } = {}) {
  const match = telemetry.matches[0];
  const players = telemetry.squad.players
    .map(safePlayer)
    .filter((player) => player.consent.memory_appearance);
  const targetIndex = telemetry.squad.players.findIndex(
    (player) => player.player_id === telemetry.target_player_id,
  );
  const target = safePlayer(telemetry.squad.players[targetIndex], targetIndex);
  const invited = players.filter((player) => player.consent.mission_invitation);
  const windowId = `window:${match.match_id}:test`;
  const participantId = "test:participants";
  const matchId = "test:complete-match";
  const reviveId = "test:first-revive";
  const returnId = "test:return-location";
  const affordanceId = "test:role-reversal";
  const objectiveIds = [participantId, matchId, reviveId, returnId];
  const objectives = [
    {
      objective_id: participantId,
      description: "Play a match with the invited squad.",
      assigned_player_id: null,
      required: true,
      verification: {
        metric: "squad.participant_ids",
        operator: "contains_all",
        target: invited.map((player) => player.player_id),
      },
      source_event_ids: [],
    },
    {
      objective_id: matchId,
      description: "Complete at least 1 match.",
      assigned_player_id: null,
      required: true,
      verification: { metric: "squad.matches_completed", operator: "at_least", target: 1 },
      source_event_ids: [],
    },
    {
      objective_id: reviveId,
      description: `${target.display_name} completes the squad's first revive.`,
      assigned_player_id: target.player_id,
      required: true,
      verification: {
        metric: "match.first_squad_revive_actor_id",
        operator: "equals",
        target: target.player_id,
      },
      source_event_ids: ["ffevt-04-revive-lee"],
    },
    {
      objective_id: returnId,
      description: "Visit Clock Tower with the invited squad.",
      assigned_player_id: null,
      required: true,
      verification: {
        metric: "match.invited_squad_visits_location",
        operator: "equals",
        target: "Clock Tower",
      },
      source_event_ids: ["ffevt-04-revive-lee"],
    },
  ];
  const candidates = objectives.map((objective) => ({
    candidate_id: objective.objective_id,
    window_id: windowId,
    recipe: "remix",
    assigned_player_id: objective.assigned_player_id,
    source_event_ids: objective.source_event_ids,
    verification: objective.verification,
  }));
  const affordance = {
    affordance_id: affordanceId,
    family: "role_reversal",
    window_id: windowId,
    source_event_ids: ["ffevt-04-revive-lee"],
    source_match_ids: [match.match_id],
    source_context_ids: ["context:reunion_eligible"],
    parameters: {
      saved_player_id: target.player_id,
      return_location: "Clock Tower",
    },
    objective_candidate_ids: objectiveIds,
    allowed_reason_codes: ["directly_inverts_original_roles"],
  };
  const claim = {
    claim_id: "test:claim:episode",
    output_section: "summary",
    subject_id: target.player_id,
    predicate: "participated_in_episode",
    target_id: null,
    location: null,
    value: null,
    supporting_event_ids: [selectedEventIds[0]],
    supporting_context_ids: [],
    supporting_mission_candidate_ids: [],
  };

  return {
    schema_version: "2.1",
    request_id: telemetry.request_id,
    delivery_id: "test-live-delivery-001",
    status: "pending_player_decision",
    reason_codes: [],
    memory: {
      title: "A Squad Moment",
      memory_type: "rescue",
      summary: "The squad recovered from a difficult moment and escaped together.",
      notification_teaser: "Your squad left a story behind.",
      why_this_matters_now: "The original squad is eligible to reunite.",
      selected_match_id: match.match_id,
      selected_event_ids: [...selectedEventIds],
      media_reference: null,
    },
    player_perspectives: players.map((player) => ({
      player_id: player.player_id,
      display_name: player.display_name,
      message: "You were part of the squad's recovery and escape.",
      evidence_event_ids: [selectedEventIds[0]],
    })),
    next_chapter: {
      title: "Return the Favour",
      mission: "Reverse the rescue roles when the squad returns.",
      recipe: "remix",
      family: "role_reversal",
      invitation_player_ids: invited.map((player) => player.player_id),
      objectives,
    },
    grounded_claims: [claim],
    validation: { passed: true, correction_attempted: false, issues: [] },
    studio_trace: {
      trace_id: "test-live-trace-001",
      stages: [
        { stage: "deterministic_preparation", status: "complete", summary: "Test fixture prepared.", issue_codes: [] },
        { stage: "ai_interpretation", status: "complete", summary: "Test proposal interpreted.", issue_codes: [] },
        { stage: "deterministic_validation", status: "complete", summary: "Test proposal validated.", issue_codes: [] },
        { stage: "player_decision", status: "pending", summary: "Waiting for a player decision.", issue_codes: [] },
      ],
      normalized_match_count: telemetry.matches.length,
      normalized_event_count: telemetry.matches.reduce((total, item) => total + item.events.length, 0),
      privacy_redaction_count: telemetry.squad.players.length - players.length,
      eligible_windows: [{
        window_id: windowId,
        match_id: match.match_id,
        event_ids: [...selectedEventIds],
        participant_ids: players.map((player) => player.player_id),
        start_seconds: 1088,
        end_seconds: 1120,
      }],
      mission_candidates: candidates,
      mission_affordances: [affordance],
      mission_selection: {
        ranked_affordance_ids: [affordanceId],
        selected_affordance_id: affordanceId,
        selected_family: "role_reversal",
        reason_codes: ["directly_inverts_original_roles"],
      },
      active_player_count: telemetry.current_context.active_player_ids.length,
      invitation_eligible_count: invited.length,
      claim_mappings: [{
        claim_id: claim.claim_id,
        output_section: claim.output_section,
        predicate: claim.predicate,
        evidence_ids: [...claim.supporting_event_ids],
      }],
      correction_attempted: false,
      source_quality_flag: false,
    },
    metadata: studioOrigin
      ? {
          provider: "deterministic",
          model: "test-only-fixture",
          mode: "deterministic",
          prompt_version: "test-only",
          content_origin: "deterministic_studio_sample",
          grounded_render: false,
          narrative_fallback: false,
        }
      : {
          provider: "test-provider",
          model: "test-model",
          mode: "live_ai",
          prompt_version: "test-only",
          content_origin: "live_ai_validated",
          grounded_render: false,
          narrative_fallback: false,
        },
  };
}
