export type MemoryEngineResult = typeof demoResult;

export const demoMemoryPack = {
  schema_version: "1.0",
  pack_id: "memory-pack-worst-plan-001",
  player_profile: { player_id: "lee", preferred_role: "aggressive_entry" },
  squad: {
    squad_id: "original-four",
    members: [
      { player_id: "lee", display_name: "Lee", role: "aggressive_entry", opted_in: true },
      { player_id: "mei", display_name: "Mei", role: "support_rescuer", opted_in: true },
      { player_id: "jo", display_name: "Jo", role: "driver", opted_in: true },
      { player_id: "amir", display_name: "Amir", role: "caller", opted_in: true },
    ],
    matches_together: 87,
    days_since_full_squad: 37,
  },
  match: { match_id: "FF-M218", mode: "battle_royale", map_name: "Bermuda", placement: 6, played_at: "2026-06-26T20:14:00+08:00" },
  match_events: [
    { event_id: "evt-retreat-01", type: "retreat_ping", actor_id: "amir", timestamp_seconds: 1110, location: "Clock Tower", importance: "medium", details: { count: 3 } },
    { event_id: "evt-revive-01", type: "revive", actor_id: "mei", target_id: "lee", timestamp_seconds: 1115, location: "Clock Tower", importance: "high", details: { zone_state: "closing" } },
    { event_id: "evt-escape-01", type: "vehicle_escape", actor_id: "jo", timestamp_seconds: 1118, location: "Clock Tower", importance: "high", details: { passengers: 3, health_state: "critical" } },
    { event_id: "evt-survival-01", type: "final_zone_survival", actor_id: "lee", timestamp_seconds: 1210, location: "Final Zone", importance: "high", details: { squad_alive: 4 } },
  ],
  human_memory: { caption: "Worst plan, best night", tags: ["funny", "chaos"], author_player_id: "amir", confirmed: true },
  reactions: { laugh_count: 12, fire_count: 3, saved: true },
  current_context: { active_member_ids: ["lee", "mei"], resurfacing_reason: "Two original squad members are active and Bermuda is available.", original_mode_available: true },
} as const;

export const demoResult = {
  schema_version: "1.0",
  pack_id: "memory-pack-worst-plan-001",
  status: "ready",
  discovery: { signal_score: 1, threshold: 0.45, reasons: ["4 grounded gameplay events", "connected rescue-and-escape pattern", "player-confirmed meaning"], eligible: true },
  memory: {
    title: "Worst Plan, Best Night",
    memory_type: "chaos",
    summary: "At Clock Tower, Mei revived Lee before Jo drove the squad out of danger.",
    confidence: 1,
    evidence: [
      { event_id: "evt-revive-01", event_type: "revive", significance: "Mei revived Lee while the zone was closing." },
      { event_id: "evt-escape-01", event_type: "vehicle_escape", significance: "Jo drove three passengers away from Clock Tower." },
      { event_id: "evt-survival-01", event_type: "final_zone_survival", significance: "Lee survived with the full squad into the final zone." },
      { event_id: "evt-retreat-01", event_type: "retreat_ping", significance: "Amir called for retreat three times before the escape." },
    ],
    human_confirmed: true,
  },
  player_perspectives: [
    { player_id: "lee", display_name: "Lee", message: "Mei came back for you at Clock Tower. That verified revive became your part of “Worst Plan, Best Night.”", evidence_event_ids: ["evt-revive-01"] },
    { player_id: "mei", display_name: "Mei", message: "You revived Lee at Clock Tower. Your rescue is one of the grounded events behind “Worst Plan, Best Night.”", evidence_event_ids: ["evt-revive-01"] },
    { player_id: "jo", display_name: "Jo", message: "You drove the squad out of Clock Tower with 3 passengers. The getaway is the chaotic turn in “Worst Plan, Best Night.”", evidence_event_ids: ["evt-escape-01"] },
    { player_id: "amir", display_name: "Amir", message: "You called for retreat 3 times. The squad’s verified escape turned that call into part of “Worst Plan, Best Night.”", evidence_event_ids: ["evt-retreat-01"] },
  ],
  next_chapter: {
    title: "Worst Plan, Best Night II: Return the Favour",
    mission: "Reassemble the original squad and remix Worst Plan, Best Night at Clock Tower using roles grounded in the original match.",
    recipe: "remix",
    objectives: [
      { objective_id: "reassemble-original-squad", description: "Complete a match with the opted-in members of the original squad.", required: true },
      { objective_id: "return-to-location", description: "Return to Clock Tower during the new match.", required: true },
      { objective_id: "return-the-favour", description: "Lee revives Mei, reversing the original roles.", required: true },
      { objective_id: "driver-seat-open", description: "Jo drives at least 3 teammates out of Clock Tower.", required: false },
      { objective_id: "caller-chooses-route", description: "Amir chooses the squad’s first rotation route.", required: false },
    ],
  },
  validation: { passed: true, human_review_required: false, scores: { specificity: 1, evidence_grounding: 1, perspective_distinctness: 1, quest_connection: 1 }, issues: [] },
  metadata: { pipeline_version: "phase-1-v1", provider: "deterministic", model: "rules-v1" },
};
