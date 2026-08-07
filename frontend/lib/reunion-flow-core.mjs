/** Pure Phase 3 reunion helpers. The demo is synthetic; the rule evaluation is deterministic. */

export function buildInvitees(perspectives, currentPlayerId) {
  const seen = new Set();
  return perspectives.flatMap((perspective) => {
    if (
      !perspective
      || typeof perspective.player_id !== "string"
      || typeof perspective.display_name !== "string"
      || seen.has(perspective.player_id)
    ) {
      return [];
    }
    seen.add(perspective.player_id);
    return [{
      player_id: perspective.player_id,
      display_name: perspective.display_name,
      is_current_player: perspective.player_id === currentPlayerId,
    }];
  });
}

export function createSyntheticRematch(invitees) {
  return {
    schema_version: "1.0",
    match_id: "synthetic-clock-tower-rematch-001",
    label: "Clock Tower rematch",
    metrics: {
      squad_member_ids: invitees.map((invitee) => invitee.player_id),
      visited_locations: ["Clock Tower", "Final Zone"],
      "revives.lee.targets": ["mei"],
    },
  };
}

export function evaluateRule(rule, metrics) {
  if (!rule || typeof rule.metric !== "string") return false;
  const actual = metrics[rule.metric];

  if (rule.operator === "equals") {
    return JSON.stringify(actual) === JSON.stringify(rule.target);
  }
  if (rule.operator === "at_least") {
    return typeof actual === "number"
      && typeof rule.target === "number"
      && actual >= rule.target;
  }
  if (rule.operator === "contains_all") {
    return Array.isArray(actual)
      && Array.isArray(rule.target)
      && rule.target.every((target) => actual.includes(target));
  }
  return false;
}

export function verifyMission(objectives, matchResult) {
  const objective_results = objectives.map((objective) => ({
    objective_id: objective.objective_id,
    description: objective.description,
    required: objective.required,
    passed: evaluateRule(objective.verification, matchResult.metrics),
  }));
  const required = objective_results.filter((objective) => objective.required);
  const required_passed = required.filter((objective) => objective.passed).length;
  return {
    match_id: matchResult.match_id,
    label: matchResult.label,
    objective_results,
    required_passed,
    required_total: required.length,
    complete: required.length > 0 && required_passed === required.length,
  };
}

export function createContinuationChapter(memory, nextChapter, verification) {
  if (!verification.complete) return null;
  const title = nextChapter.title.split(":").at(-1)?.trim() || nextChapter.title;
  const highlights = verification.objective_results
    .filter((objective) => objective.required && objective.passed)
    .map((objective) => objective.description);
  return {
    title,
    summary: `In the verified synthetic rematch, the squad completed every required step of ${title}. The old memory now has a grounded sequel.`,
    highlights,
    original_memory_title: memory.title,
  };
}
