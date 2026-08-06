import type { MemoryEngineResult, MemoryPack } from "./types";
import readyPack from "@/data/funny_memory.json";

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalize(item)]),
    );
  }
  return value;
}

const readyPackFingerprint = JSON.stringify(canonicalize(readyPack));

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

export function getDemoResult(pack: MemoryPack): MemoryEngineResult | undefined {
  if (JSON.stringify(canonicalize(pack)) !== readyPackFingerprint) return undefined;
  return structuredClone(readyResult);
}
