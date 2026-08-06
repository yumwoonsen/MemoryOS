import type { MemoryEngineResult, MemoryPack } from "./types";

const readyResult: MemoryEngineResult = {
  schema_version: "1.0",
  pack_id: "memory-pack-worst-plan-001",
  status: "ready",
  discovery: {
    signal_score: 1,
    threshold: 0.45,
    reasons: [
      "4 grounded gameplay event(s)",
      "connected rescue-and-escape pattern",
      "player-authored caption",
      "player-selected memory tags",
      "player-confirmed meaning",
      "positive save or reaction signals",
    ],
    eligible: true,
  },
  memory: {
    title: "Worst Plan, Best Night",
    memory_type: "chaos",
    summary:
      "At Clock Tower, Mei revived Lee before Jo drove the squad out of danger.",
    confidence: 1,
    evidence: [
      { event_id: "evt-revive-01", event_type: "revive", significance: "Mei revived Lee" },
      {
        event_id: "evt-escape-01",
        event_type: "vehicle_escape",
        significance: "Jo completed the vehicle escape with 3 passenger(s)",
      },
      {
        event_id: "evt-survival-01",
        event_type: "final_zone_survival",
        significance: "Verified final zone survival event involving Lee",
      },
      {
        event_id: "evt-retreat-01",
        event_type: "retreat_ping",
        significance: "Amir called for retreat 3 time(s)",
      },
    ],
    human_confirmed: true,
  },
  player_perspectives: [
    {
      player_id: "lee",
      display_name: "Lee",
      message:
        "Verified revive #1 records Mei coming back for you at Clock Tower. That rescue became your part of \"Worst Plan, Best Night.\"",
      evidence_event_ids: ["evt-revive-01"],
    },
    {
      player_id: "mei",
      display_name: "Mei",
      message:
        "Verified revive #1 records you reviving Lee at Clock Tower. Your rescue is grounded evidence behind \"Worst Plan, Best Night.\"",
      evidence_event_ids: ["evt-revive-01"],
    },
    {
      player_id: "jo",
      display_name: "Jo",
      message:
        "You drove the squad out of Clock Tower with 3 passengers. The getaway is the chaotic turn in \"Worst Plan, Best Night.\"",
      evidence_event_ids: ["evt-escape-01"],
    },
    {
      player_id: "amir",
      display_name: "Amir",
      message:
        "You called for retreat 3 times. The squad's verified escape turned that call into part of \"Worst Plan, Best Night.\"",
      evidence_event_ids: ["evt-retreat-01"],
    },
  ],
  next_chapter: {
    title: "Worst Plan, Best Night II: Return the Favour",
    mission:
      "Reassemble the original squad and remix \"Worst Plan, Best Night\" at Clock Tower using roles grounded in the original match.",
    recipe: "remix",
    objectives: [
      {
        objective_id: "reassemble-original-squad",
        description: "Complete a match with the opted-in members of the original squad.",
        required: true,
        verification: {
          metric: "squad_member_ids",
          operator: "contains_all",
          target: ["lee", "mei", "jo", "amir"],
        },
        source_event_ids: [
          "evt-retreat-01",
          "evt-revive-01",
          "evt-escape-01",
          "evt-survival-01",
        ],
      },
      {
        objective_id: "return-to-location",
        description: "Return to Clock Tower during the new match.",
        required: true,
        verification: {
          metric: "visited_locations",
          operator: "contains_all",
          target: ["Clock Tower"],
        },
        source_event_ids: ["evt-retreat-01", "evt-revive-01", "evt-escape-01"],
      },
      {
        objective_id: "return-the-favour",
        description: "Lee revives Mei, reversing the original roles.",
        assigned_player_id: "lee",
        required: true,
        verification: {
          metric: "revives.lee.targets",
          operator: "contains_all",
          target: ["mei"],
        },
        source_event_ids: ["evt-revive-01"],
      },
      {
        objective_id: "driver-seat-open",
        description: "Jo drives at least 3 teammates out of Clock Tower.",
        assigned_player_id: "jo",
        required: false,
        verification: {
          metric: "vehicle_escape.jo.passengers",
          operator: "at_least",
          target: 3,
        },
        source_event_ids: ["evt-escape-01"],
      },
      {
        objective_id: "caller-chooses-route",
        description: "Amir chooses the squad's first rotation route.",
        assigned_player_id: "amir",
        required: false,
        verification: {
          metric: "initial_route_caller_id",
          operator: "equals",
          target: "amir",
        },
        source_event_ids: ["evt-retreat-01"],
      },
    ],
  },
  validation: {
    passed: true,
    human_review_required: false,
    scores: {
      specificity: 1,
      evidence_grounding: 1,
      perspective_distinctness: 1,
      quest_connection: 1,
    },
    issues: [],
  },
  metadata: {
    pipeline_version: "phase-1-v1",
    provider: "deterministic",
    model: "rules-v1",
    prose_renderer: "canonical-v1",
  },
};

const reviewResult: MemoryEngineResult = {
  schema_version: "1.0",
  pack_id: "memory-pack-comeback-001",
  status: "needs_human_confirmation",
  discovery: {
    signal_score: 0.86,
    threshold: 0.45,
    reasons: [
      "5 grounded gameplay event(s)",
      "last-player-alive comeback pattern",
      "player-authored caption",
      "player-selected memory tags",
      "positive save or reaction signals",
    ],
    eligible: true,
  },
  memory: {
    title: "One Hp Reset",
    memory_type: "comeback",
    summary:
      "At Command Post, Nia was the last squad member alive and brought Rafi back into the match.",
    confidence: 0.86,
    evidence: [
      {
        event_id: "evt-last-alive-01",
        event_type: "last_player_alive",
        significance: "Nia became the squad's last surviving player",
      },
      {
        event_id: "evt-revive-rafi-01",
        event_type: "revive",
        significance: "Nia revived Rafi",
      },
      {
        event_id: "evt-revive-sol-01",
        event_type: "revive",
        significance: "Rafi revived Sol",
      },
      {
        event_id: "evt-final-ten-01",
        event_type: "final_zone_survival",
        significance: "Verified final zone survival event involving Nia",
      },
    ],
    human_confirmed: false,
  },
  player_perspectives: [
    {
      player_id: "nia",
      display_name: "Nia",
      message:
        "Verified revive #1 records you reviving Rafi at Command Post. Your rescue is grounded evidence behind \"One Hp Reset.\"",
      evidence_event_ids: ["evt-revive-rafi-01"],
    },
    {
      player_id: "rafi",
      display_name: "Rafi",
      message:
        "Verified revive #1 records Nia coming back for you at Command Post. That rescue became your part of \"One Hp Reset.\"",
      evidence_event_ids: ["evt-revive-rafi-01"],
    },
    {
      player_id: "sol",
      display_name: "Sol",
      message:
        "Verified revive #2 records Rafi coming back for you at Command Post. That rescue became your part of \"One Hp Reset.\"",
      evidence_event_ids: ["evt-revive-sol-01"],
    },
    {
      player_id: "kay",
      display_name: "Kay",
      message:
        "Kay, evidence #4 records your squad's verified final zone survival at Final Zone. It anchors your recall of \"One Hp Reset.\"",
      evidence_event_ids: ["evt-final-ten-01"],
    },
  ],
  next_chapter: {
    title: "One Hp Reset II: Return the Favour",
    mission:
      "Reassemble the original squad and remix \"One Hp Reset\" at Command Post using roles grounded in the original match.",
    recipe: "remix",
    objectives: [
      {
        objective_id: "reassemble-original-squad",
        description: "Complete a match with the opted-in members of the original squad.",
        required: true,
        verification: {
          metric: "squad_member_ids",
          operator: "contains_all",
          target: ["nia", "rafi", "sol", "kay"],
        },
        source_event_ids: [
          "evt-last-alive-01",
          "evt-revive-rafi-01",
          "evt-revive-sol-01",
          "evt-final-ten-01",
        ],
      },
      {
        objective_id: "return-to-location",
        description: "Return to Command Post during the new match.",
        required: true,
        verification: {
          metric: "visited_locations",
          operator: "contains_all",
          target: ["Command Post"],
        },
        source_event_ids: [
          "evt-last-alive-01",
          "evt-revive-rafi-01",
          "evt-revive-sol-01",
        ],
      },
      {
        objective_id: "return-the-favour",
        description: "Rafi revives Nia, reversing the original roles.",
        assigned_player_id: "rafi",
        required: true,
        verification: {
          metric: "revives.rafi.targets",
          operator: "contains_all",
          target: ["nia"],
        },
        source_event_ids: ["evt-revive-rafi-01"],
      },
    ],
  },
  validation: {
    passed: true,
    human_review_required: true,
    scores: {
      specificity: 1,
      evidence_grounding: 1,
      perspective_distinctness: 1,
      quest_connection: 1,
    },
    issues: [
      {
        code: "human_confirmation_required",
        severity: "warning",
        message: "A player must confirm this candidate before re-engagement use.",
      },
    ],
  },
  metadata: {
    pipeline_version: "phase-1-v1",
    provider: "deterministic",
    model: "rules-v1",
    prose_renderer: "canonical-v1",
  },
};

const skippedResult: MemoryEngineResult = {
  schema_version: "1.0",
  pack_id: "memory-pack-insufficient-001",
  status: "rejected",
  discovery: {
    signal_score: 0.02,
    threshold: 0.45,
    reasons: ["1 grounded gameplay event(s)"],
    eligible: false,
  },
  player_perspectives: [],
  validation: {
    passed: true,
    human_review_required: false,
    scores: {
      specificity: 0,
      evidence_grounding: 1,
      perspective_distinctness: 0,
      quest_connection: 0,
    },
    issues: [
      {
        code: "insufficient_memory_signal",
        severity: "info",
        message:
          "Signal score 0.02 is below the 0.45 threshold; generation was safely skipped.",
      },
    ],
  },
  metadata: {
    pipeline_version: "phase-1-v1",
    provider: "deterministic",
    model: "rules-v1",
    prose_renderer: "canonical-v1",
  },
};

const results: Record<string, MemoryEngineResult> = {
  [readyResult.pack_id]: readyResult,
  [reviewResult.pack_id]: reviewResult,
  [skippedResult.pack_id]: skippedResult,
};

function titleCase(value: string) {
  return value.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 3).trimEnd()}...`;
}

export function getDemoResult(pack: MemoryPack): MemoryEngineResult | undefined {
  const source = results[pack.pack_id];
  if (!source) return undefined;

  const result = structuredClone(source);
  const confirmed = Boolean(pack.human_memory?.confirmed);

  if (result.status === "needs_human_confirmation" && confirmed && result.memory) {
    const previousTitle = result.memory.title;
    const nextTitle = truncateText(
      titleCase(pack.human_memory?.caption?.trim() || previousTitle),
      100,
    );
    result.status = "ready";
    result.discovery.signal_score = 1;
    if (!result.discovery.reasons.includes("player-confirmed meaning")) {
      result.discovery.reasons.push("player-confirmed meaning");
    }
    result.memory.title = nextTitle;
    result.memory.confidence = 1;
    result.memory.human_confirmed = true;
    result.player_perspectives = result.player_perspectives.map((perspective) => ({
      ...perspective,
      message: perspective.message.replaceAll(previousTitle, nextTitle),
    }));
    if (result.next_chapter) {
      result.next_chapter.title = truncateText(
        result.next_chapter.title.replace(previousTitle, nextTitle),
        120,
      );
      result.next_chapter.mission = truncateText(
        result.next_chapter.mission.replace(previousTitle, nextTitle),
        500,
      );
    }
    result.validation.human_review_required = false;
    result.validation.issues = result.validation.issues.filter(
      (issue) => issue.code !== "human_confirmation_required",
    );
  }

  return result;
}
