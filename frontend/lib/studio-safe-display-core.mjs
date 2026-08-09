function safeStudioSubject(subjectId, players) {
  if (subjectId === "squad") return "Eligible squad";
  if (subjectId.startsWith("anonymous:")) return "Anonymous squadmate";
  return players.find((player) => player.player_id === subjectId)?.display_name
    ?? "Consent-safe subject";
}

export function safeStudioRuleTarget(target, players) {
  if (Array.isArray(target)) {
    return target.map((item) => safeStudioSubject(item, players)).join(", ");
  }
  if (typeof target === "string"
    && (target === "squad"
      || target.startsWith("anonymous:")
      || players.some((player) => player.player_id === target))) {
    return safeStudioSubject(target, players);
  }
  return String(target);
}
