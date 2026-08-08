import {
  consentSafeTelemetryView,
  type GroundedClaimV2,
  type RawTelemetryBatchV2,
  type StudioInterpretDeliveryResultV2,
} from "@/lib/ai-memory-contract";

export function createStudioDemoResult(
  telemetry: RawTelemetryBatchV2,
): StudioInterpretDeliveryResultV2 | null {
  const safeTelemetry = consentSafeTelemetryView(telemetry);
  const match = safeTelemetry.matches.find((item) => item.match_id === "ff-match-01J4Y7M8W2");
  const eligible = safeTelemetry.squad.players.filter((player) =>
    player.consent.memory_appearance && player.display_name,
  );
  if (!match || eligible.length < 2) return null;

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
  const returnCandidateId = "return_with_squad:window_ff-match-01J4Y7M8W2_2";
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
    ...eligible.map((player): GroundedClaimV2 => {
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
    {
      claim_id: `claim:objective:${returnCandidateId}`,
      output_section: `objective:${returnCandidateId}`,
      subject_id: "squad",
      predicate: "mission_rule",
      supporting_event_ids: [],
      supporting_context_ids: [],
      supporting_mission_candidate_ids: [returnCandidateId],
    },
    {
      claim_id: "claim:mission",
      output_section: "mission",
      subject_id: "squad",
      predicate: "mission_rule",
      supporting_event_ids: [],
      supporting_context_ids: [],
      supporting_mission_candidate_ids: [returnCandidateId],
    },
  ];
  return {
    schema_version: "2.0",
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
    player_perspectives: eligible.map((player) => {
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
      title: "Return Together",
      mission: "Bring this squad back for one verifiable match.",
      recipe: "recreate",
      objectives: [
        {
          objective_id: returnCandidateId,
          description: "Play a new match with the invited squad members.",
          required: true,
          verification: {
            metric: "squad.participant_ids",
            operator: "contains_all",
            target: eligible.map((player) => player.player_id),
          },
          source_event_ids: selectedEventIds,
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
      privacy_redaction_count: telemetry.squad.players.filter((player) => !player.consent.identity_display).length,
      eligible_windows: [
        {
          window_id: windowId,
          match_id: match.match_id,
          event_ids: selectedEventIds,
          participant_ids: eligible.map((player) => player.player_id),
          start_seconds: 1088,
          end_seconds: 1120,
        },
      ],
      mission_candidates: [
        {
          candidate_id: returnCandidateId,
          window_id: windowId,
          recipe: "recreate",
          source_event_ids: selectedEventIds,
          verification: {
            metric: "squad.participant_ids",
            operator: "contains_all",
            target: eligible.map((player) => player.player_id),
          },
        },
      ],
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
          summary: "Telemetry was normalized, consent was applied, and two neutral event windows were formed.",
          issue_codes: [],
        },
        {
          stage: "ai_interpretation",
          status: "complete",
          summary: `A saved demonstration proposal selected ${windowId} and one feasible mission candidate.`,
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
      model: "precomputed-studio-fixture",
      mode: "deterministic",
      prompt_version: "memory-interpreter-v2-demo",
    },
  };
}
