import rawTelemetryFixture from "@/data/raw_telemetry_v2.json";
import {
  consentSafeTelemetryView,
  parseRawTelemetryBatchV2,
  type GroundedClaimV2,
  type StudioInterpretDeliveryResultV2,
} from "@/lib/ai-memory-contract";

const studioSampleTelemetry = parseRawTelemetryBatchV2(rawTelemetryFixture as unknown);

export function createStudioDemoResult(): StudioInterpretDeliveryResultV2 | null {
  // Hosted/offline replay is intentionally isolated from the submitted batch.
  // It may demonstrate the pipeline, but it must never replay submitted identities.
  if (!studioSampleTelemetry) return null;
  const safeTelemetry = consentSafeTelemetryView(studioSampleTelemetry);
  const match = safeTelemetry.matches.find((item) => item.match_id === "ff-match-01J4Y7M8W2");
  const perspectivePlayers = safeTelemetry.squad.players.filter((player) =>
    player.consent.memory_appearance && player.display_name,
  );
  const invitationPlayers = perspectivePlayers.filter((player) => player.consent.mission_invitation);
  if (!match || perspectivePlayers.length < 2 || invitationPlayers.length < 2) return null;

  const selectedEventIds = [
    "ffevt-02-knock-lee",
    "ffevt-03-ping-retreat",
    "ffevt-04-revive-lee",
    "ffevt-05-vehicle-enter",
    "ffevt-06-zone-exit",
  ];
  if (!selectedEventIds.every((eventId) => match.events.some((event) => event.event_id === eventId))) {
    return null;
  }

  const windowId = "window:ff-match-01J4Y7M8W2:2";
  const reunionParticipantCandidateId = "reunion_participants:recreate:window_ff-match-01J4Y7M8W2_2";
  const reunionMatchCandidateId = "complete_match:recreate:window_ff-match-01J4Y7M8W2_2";
  const reversalParticipantCandidateId = "reunion_participants:remix:window_ff-match-01J4Y7M8W2_2";
  const reversalMatchCandidateId = "complete_match:remix:window_ff-match-01J4Y7M8W2_2";
  const reversalCandidateId = "first_revive_by_saved_player:window_ff-match-01J4Y7M8W2_2";
  const reunionAffordanceId = "affordance:reunion:window_ff-match-01J4Y7M8W2_2";
  const reversalAffordanceId = "affordance:role_reversal:window_ff-match-01J4Y7M8W2_2";
  const groundedClaims: GroundedClaimV2[] = [
    {
      claim_id: "claim:title",
      output_section: "title",
      subject_id: "squad",
      predicate: "connected_episode",
      location: "Clock Tower",
      supporting_event_ids: selectedEventIds,
      supporting_context_ids: [],
      supporting_mission_candidate_ids: [],
    },
    {
      claim_id: "claim:notification_teaser",
      output_section: "notification_teaser",
      subject_id: "squad",
      predicate: "connected_episode",
      location: "Clock Tower",
      supporting_event_ids: selectedEventIds,
      supporting_context_ids: [],
      supporting_mission_candidate_ids: [],
    },
    {
      claim_id: "claim:summary:1",
      output_section: "summary",
      subject_id: "ff-player-lee",
      predicate: "was_knocked",
      location: "Clock Tower",
      supporting_event_ids: ["ffevt-02-knock-lee"],
      supporting_context_ids: [],
      supporting_mission_candidate_ids: [],
    },
    {
      claim_id: "claim:summary:2",
      output_section: "summary",
      subject_id: "ff-player-amir",
      predicate: "signalled",
      location: "Clock Tower",
      supporting_event_ids: ["ffevt-03-ping-retreat"],
      supporting_context_ids: [],
      supporting_mission_candidate_ids: [],
    },
    {
      claim_id: "claim:summary:3",
      output_section: "summary",
      subject_id: "ff-player-mei",
      predicate: "revived",
      target_id: "ff-player-lee",
      location: "Clock Tower",
      supporting_event_ids: ["ffevt-04-revive-lee"],
      supporting_context_ids: [],
      supporting_mission_candidate_ids: [],
    },
    {
      claim_id: "claim:why-now",
      output_section: "why_this_matters_now",
      subject_id: "squad",
      predicate: "current_reunion_opportunity",
      value: 21,
      supporting_event_ids: [],
      supporting_context_ids: ["context:days_since_full_squad"],
      supporting_mission_candidate_ids: [],
    },
    ...perspectivePlayers.map((player): GroundedClaimV2 => {
      const byPlayer: Record<string, Pick<GroundedClaimV2, "predicate" | "location" | "target_id" | "supporting_event_ids">> = {
        "ff-player-lee": {
          predicate: "was_knocked",
          location: "Clock Tower",
          supporting_event_ids: ["ffevt-02-knock-lee"],
        },
        "ff-player-mei": {
          predicate: "revived",
          target_id: "ff-player-lee",
          location: "Clock Tower",
          supporting_event_ids: ["ffevt-04-revive-lee"],
        },
        "ff-player-amir": {
          predicate: "signalled",
          location: "Clock Tower",
          supporting_event_ids: ["ffevt-03-ping-retreat"],
        },
      };
      const grounding = byPlayer[player.player_id] ?? {
        predicate: "participated_match",
        supporting_event_ids: ["ffevt-06-zone-exit"],
      };
      return {
        claim_id: `claim:perspective:${player.player_id}`,
        output_section: `perspective:${player.player_id}`,
        subject_id: player.player_id,
        ...grounding,
        supporting_context_ids: [],
        supporting_mission_candidate_ids: [],
      };
    }),
    ...[reversalParticipantCandidateId, reversalMatchCandidateId, reversalCandidateId].map((candidateId): GroundedClaimV2 => ({
      claim_id: `claim:objective:${candidateId}`,
      output_section: `objective:${candidateId}`,
      subject_id: candidateId === reversalCandidateId ? "ff-player-lee" : "squad",
      predicate: "mission_rule",
      supporting_event_ids: candidateId === reversalCandidateId ? ["ffevt-04-revive-lee"] : [],
      supporting_context_ids: [],
      supporting_mission_candidate_ids: [candidateId],
    })),
    {
      claim_id: "claim:mission",
      output_section: "mission",
      subject_id: "squad",
      predicate: "mission_rule",
      supporting_event_ids: [],
      supporting_context_ids: [],
      supporting_mission_candidate_ids: [
        reversalParticipantCandidateId,
        reversalMatchCandidateId,
        reversalCandidateId,
      ],
    },
  ];
  return {
    schema_version: "2.1",
    request_id: safeTelemetry.request_id,
    delivery_id: "studio-demo-delivery-001",
    status: "pending_player_decision",
    reason_codes: [],
    memory: {
      title: "A Squad Moment at Clock Tower",
      memory_type: "comeback",
      summary: "Lee was knocked at Clock Tower. Amir signalled at Clock Tower. Mei revived Lee at Clock Tower.",
      notification_teaser: "Your squad shared a connected moment at Clock Tower.",
      why_this_matters_now: "It has been 21 days since the full squad played.",
      selected_match_id: match.match_id,
      selected_event_ids: selectedEventIds,
      media_reference: safeTelemetry.media_references[0],
    },
    player_perspectives: perspectivePlayers.map((player) => {
      const byPlayer: Record<string, { message: string; evidence: string[] }> = {
        "ff-player-lee": {
          message: "You were knocked at Clock Tower; that event became part of this moment.",
          evidence: ["ffevt-02-knock-lee"],
        },
        "ff-player-mei": {
          message: "You revived Lee at Clock Tower; that action became part of this moment.",
          evidence: ["ffevt-04-revive-lee"],
        },
        "ff-player-amir": {
          message: "You signalled at Clock Tower; that action became part of this moment.",
          evidence: ["ffevt-03-ping-retreat"],
        },
      };
      const perspective = byPlayer[player.player_id] ?? {
        message: "You were part of the squad that made it out together.",
        evidence: ["ffevt-06-zone-exit"],
      };
      return {
        player_id: player.player_id,
        display_name: player.display_name ?? "Squadmate",
        message: perspective.message,
        evidence_event_ids: perspective.evidence,
      };
    }),
    next_chapter: {
      title: "Return the Favour",
      mission: "Bring the squad back and let Lee complete the squad's first revival.",
      recipe: "remix",
      family: "role_reversal",
      invitation_player_ids: invitationPlayers.map((player) => player.player_id),
      objectives: [
        {
          objective_id: reversalParticipantCandidateId,
          description: "Bring the invitation-eligible squad into one lobby.",
          required: true,
          verification: {
            metric: "squad.participant_ids",
            operator: "contains_all",
            target: invitationPlayers.map((player) => player.player_id),
          },
          source_event_ids: selectedEventIds,
        },
        {
          objective_id: reversalMatchCandidateId,
          description: "Complete one match together.",
          required: true,
          verification: {
            metric: "squad.matches_completed",
            operator: "at_least",
            target: 1,
          },
          source_event_ids: selectedEventIds,
        },
        {
          objective_id: reversalCandidateId,
          description: "Lee completes the squad's first revival.",
          assigned_player_id: "ff-player-lee",
          required: true,
          verification: {
            metric: "match.first_squad_revive_actor_id",
            operator: "equals",
            target: "ff-player-lee",
          },
          source_event_ids: ["ffevt-04-revive-lee"],
        },
      ],
    },
    grounded_claims: groundedClaims,
    validation: {
      passed: true,
      correction_attempted: false,
      issues: [],
    },
    studio_trace: {
      trace_id: "studio-demo-trace-001",
      normalized_match_count: safeTelemetry.matches.length,
      normalized_event_count: safeTelemetry.matches.reduce((total, item) => total + item.events.length, 0),
      privacy_redaction_count: studioSampleTelemetry.squad.players.filter(
        (player) => !player.consent.identity_display,
      ).length,
      eligible_windows: [
        {
          window_id: windowId,
          match_id: match.match_id,
          event_ids: selectedEventIds,
          participant_ids: perspectivePlayers.map((player) => player.player_id),
          start_seconds: 1088,
          end_seconds: 1120,
        },
      ],
      mission_candidates: [
        {
          candidate_id: reunionParticipantCandidateId,
          window_id: windowId,
          recipe: "recreate",
          source_event_ids: selectedEventIds,
          verification: {
            metric: "squad.participant_ids",
            operator: "contains_all",
            target: invitationPlayers.map((player) => player.player_id),
          },
        },
        {
          candidate_id: reunionMatchCandidateId,
          window_id: windowId,
          recipe: "recreate",
          source_event_ids: selectedEventIds,
          verification: {
            metric: "squad.matches_completed",
            operator: "at_least",
            target: 1,
          },
        },
        {
          candidate_id: reversalParticipantCandidateId,
          window_id: windowId,
          recipe: "remix",
          source_event_ids: selectedEventIds,
          verification: {
            metric: "squad.participant_ids",
            operator: "contains_all",
            target: invitationPlayers.map((player) => player.player_id),
          },
        },
        {
          candidate_id: reversalMatchCandidateId,
          window_id: windowId,
          recipe: "remix",
          source_event_ids: selectedEventIds,
          verification: {
            metric: "squad.matches_completed",
            operator: "at_least",
            target: 1,
          },
        },
        {
          candidate_id: reversalCandidateId,
          window_id: windowId,
          recipe: "remix",
          assigned_player_id: "ff-player-lee",
          source_event_ids: ["ffevt-04-revive-lee"],
          verification: {
            metric: "match.first_squad_revive_actor_id",
            operator: "equals",
            target: "ff-player-lee",
          },
        },
      ],
      mission_affordances: [
        {
          affordance_id: reunionAffordanceId,
          family: "reunion",
          window_id: windowId,
          source_event_ids: selectedEventIds,
          source_match_ids: [match.match_id],
          source_context_ids: ["context:days_since_full_squad"],
          parameters: {},
          objective_candidate_ids: [reunionParticipantCandidateId, reunionMatchCandidateId],
          allowed_reason_codes: ["shared_squad_reunion"],
        },
        {
          affordance_id: reversalAffordanceId,
          family: "role_reversal",
          window_id: windowId,
          source_event_ids: ["ffevt-04-revive-lee"],
          source_match_ids: [match.match_id],
          source_context_ids: [],
          parameters: {
            original_rescuer_id: "ff-player-mei",
            original_saved_player_id: "ff-player-lee",
          },
          objective_candidate_ids: [
            reversalParticipantCandidateId,
            reversalMatchCandidateId,
            reversalCandidateId,
          ],
          allowed_reason_codes: ["directly_inverts_original_roles", "player_specific", "deterministically_verifiable"],
        },
      ],
      mission_selection: {
        ranked_affordance_ids: [reversalAffordanceId, reunionAffordanceId],
        selected_affordance_id: reversalAffordanceId,
        selected_family: "role_reversal",
        reason_codes: ["directly_inverts_original_roles", "player_specific", "deterministically_verifiable"],
      },
      active_player_count: safeTelemetry.current_context.active_player_ids.length,
      invitation_eligible_count: invitationPlayers.length,
      claim_mappings: groundedClaims.map((claim) => ({
        claim_id: claim.claim_id,
        output_section: claim.output_section,
        predicate: claim.predicate,
        evidence_ids: [
          ...claim.supporting_event_ids,
          ...claim.supporting_context_ids,
          ...claim.supporting_mission_candidate_ids,
        ],
      })),
      correction_attempted: false,
      source_quality_flag: false,
      stages: [
        {
          stage: "deterministic_preparation",
          status: "complete",
          summary: "The fixed synthetic telemetry was normalized, consent was applied, and one neutral event window was formed.",
          issue_codes: [],
        },
        {
          stage: "ai_interpretation",
          status: "complete",
          summary: `A saved demonstration proposal from the fixed synthetic fixture compared two mission affordances, selected ${windowId}, and chose role reversal.`,
          issue_codes: [],
        },
        {
          stage: "deterministic_validation",
          status: "complete",
          summary: "Claims, identities, media, and mission rules passed the evidence checks.",
          issue_codes: [],
        },
        {
          stage: "player_decision",
          status: "pending",
          summary: "The validated delivery is awaiting one player decision.",
          issue_codes: [],
        },
      ],
    },
    metadata: {
      provider: "deterministic",
      model: "fixed-synthetic-studio-fixture",
      mode: "deterministic",
      prompt_version: "memory-interpreter-v2-demo",
      content_origin: "deterministic_studio_sample",
      grounded_render: false,
      narrative_fallback: false,
    },
  };
}
