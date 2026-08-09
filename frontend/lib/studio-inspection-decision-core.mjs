export function studioInspectionDecision(contentOrigin, resultStatus) {
  return contentOrigin === "live_ai_validated" && resultStatus === "pending_player_decision"
    ? "accepted"
    : null;
}

export function studioInitialResultTab(contentOrigin, resultStatus) {
  return studioInspectionDecision(contentOrigin, resultStatus) === "accepted"
    ? "mission"
    : "summary";
}
